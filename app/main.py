"""Servidor web do Prumo (API + interface)."""
import asyncio
import hashlib
import hmac
import io
import secrets
import shutil
import tempfile
import time
import urllib.parse
import uuid
import warnings
import zipfile
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)

from fastapi import FastAPI, File, Request, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from PIL import Image  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

from . import analyzer, converters, jobs, pdf_import, perfis, templates_store  # noqa: E402
from .config import (ACCESS_PASSWORD, LOGO_MAX_BYTES, LOGOS_DIR, MAX_FILE_BYTES,  # noqa: E402
                     MAX_FILE_MB, MAX_FILES_PER_UPLOAD, RETENTION_HOURS, WEB_DIR)
from .errors import UserError  # noqa: E402
from .validation import ACCEPTED, detect_format, safe_display_name  # noqa: E402

app = FastAPI(title="Prumo", docs_url=None, redoc_url=None, openapi_url=None)

_SESSION_SECRET = secrets.token_bytes(32)
_PASSWORD_HASH = hashlib.sha256(ACCESS_PASSWORD.encode()).digest() if ACCESS_PASSWORD else None


def _session_token():
    return hmac.new(_SESSION_SECRET, b"prumo-sessao", hashlib.sha256).hexdigest()


@app.on_event("startup")
def _startup():
    jobs.cleanup_expired()
    jobs.start_cleanup_thread()


@app.middleware("http")
async def security(request: Request, call_next):
    path = request.url.path
    if _PASSWORD_HASH and path.startswith("/api/") and path not in ("/api/login", "/api/status"):
        token = request.cookies.get("prumo_sessao", "")
        if not hmac.compare_digest(token, _session_token()):
            return JSONResponse({"erro": "Acesso restrito. Informe a senha da plataforma.",
                                 "login": True}, status_code=401)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    if path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    else:
        # sempre confere se a interface mudou (evita versões antigas após atualizações)
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(UserError)
async def user_error_handler(request, exc: UserError):
    return JSONResponse({"erro": exc.message}, status_code=exc.status)


@app.exception_handler(Exception)
async def generic_error_handler(request, exc: Exception):
    return JSONResponse({"erro": "Ocorreu um erro inesperado. Tente novamente."}, status_code=500)


def _download(path: Path, filename: str, media: str):
    quoted = urllib.parse.quote(filename)
    ascii_name = filename.encode("ascii", "replace").decode().replace("?", "_").replace('"', "")
    return FileResponse(path, media_type=media, headers={
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted}"})


MEDIA = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "pdf": "application/pdf"}


# ----------------------------------------------------------------------------- geral

@app.get("/api/status")
def status():
    return {
        "conversor": converters.available(),
        "ocr": pdf_import.ocr_available(),
        "retencao_horas": RETENTION_HOURS,
        "tamanho_max_mb": MAX_FILE_MB,
        "max_arquivos": MAX_FILES_PER_UPLOAD,
        "formatos": list(ACCEPTED.values()),
        "senha": bool(_PASSWORD_HASH),
        "tipos": analyzer.TYPE_LABELS,
        "perfis": perfis.opcoes(),
        **templates_store.meta_options(),
    }


@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    if not _PASSWORD_HASH:
        return {"ok": True}
    given = hashlib.sha256(str(body.get("senha", "")).encode()).digest()
    if not hmac.compare_digest(given, _PASSWORD_HASH):
        await asyncio.sleep(1)  # dificulta tentativas em sequência
        raise UserError("Senha incorreta.", 401)
    resp = JSONResponse({"ok": True})
    resp.set_cookie("prumo_sessao", _session_token(), httponly=True, samesite="strict",
                    secure=request.url.scheme == "https", max_age=12 * 3600)
    return resp


# ----------------------------------------------------------------------------- documentos

async def _save_upload(upload: UploadFile):
    name = safe_display_name(upload.filename)
    ext = Path(name).suffix.lower()
    if ext not in ACCEPTED:
        raise UserError(f"“{name}”: formato não aceito. Envie DOCX, DOC, ODT ou PDF.")
    tmp = Path(tempfile.gettempdir()) / f"prumo_up_{uuid.uuid4().hex}{ext}"
    size = 0
    head = b""
    with open(tmp, "wb") as fh:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                fh.close()
                tmp.unlink(missing_ok=True)
                raise UserError(f"“{name}” é maior que o limite de {MAX_FILE_MB} MB.")
            if len(head) < 2048:
                head += chunk[:2048]
            fh.write(chunk)
    try:
        fmt = detect_format(name, head, tmp)
    except UserError as e:
        tmp.unlink(missing_ok=True)
        raise UserError(f"“{name}”: {e.message}")
    return tmp, name, fmt


@app.post("/api/documentos")
async def upload(arquivo: UploadFile = File(...)):
    tmp, name, fmt = await _save_upload(arquivo)
    job = await run_in_threadpool(jobs.create_job, tmp, name, fmt)
    return jobs.public_job(job)


@app.get("/api/documentos/{job_id}")
def get_job(job_id: str):
    return jobs.public_job(jobs.load_job(job_id))


@app.delete("/api/documentos/{job_id}")
def remove_job(job_id: str, manter_historico: bool = False):
    jobs.delete_job(job_id, keep_history=manter_historico)
    return {"ok": True}


@app.post("/api/documentos/{job_id}/pdf")
async def convert_pdf(job_id: str, request: Request):
    body = await request.json()
    use_ocr = bool(body.get("ocr"))
    highlight = bool(body.get("destacar", True))
    job = await run_in_threadpool(jobs.run_pdf_conversion, job_id, use_ocr, highlight)
    return jobs.public_job(job)


@app.post("/api/documentos/{job_id}/processar")
async def process(job_id: str, request: Request):
    body = await request.json()
    job = await run_in_threadpool(
        jobs.process_job, job_id, str(body.get("modelo") or ""), body.get("saida", "ambos"),
        body.get("cabecalho") and {"header": body.get("cabecalho")},
        {str(k): str(v) for k, v in (body.get("correcoes") or {}).items()},
        body.get("perfil"))
    return jobs.public_job(job)


@app.post("/api/documentos/{job_id}/confirmar")
def confirm(job_id: str):
    return jobs.public_job(jobs.confirm_job(job_id))


@app.get("/api/documentos/{job_id}/previa/{tipo}/{pagina}")
async def preview(job_id: str, tipo: str, pagina: int):
    if tipo not in ("resultado", "original"):
        raise UserError("Tipo de prévia inválido.")
    path = await run_in_threadpool(jobs.preview_image, job_id, tipo, pagina)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@app.get("/api/documentos/{job_id}/baixar/{fmt}")
def download(job_id: str, fmt: str):
    path, name = jobs.result_file(job_id, fmt)
    return _download(path, name, MEDIA[fmt])


@app.get("/api/documentos/{job_id}/original")
def download_original(job_id: str):
    path, name = jobs.original_file(job_id)
    return _download(path, name, "application/octet-stream")


@app.get("/api/baixar-varios")
def download_many(ids: str, fmt: str = "ambos"):
    id_list = [i for i in ids.split(",") if i][:50]
    buf = io.BytesIO()
    used = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for jid in id_list:
            job = jobs.load_job(jid)
            fmts = ["docx", "pdf"] if fmt == "ambos" else [fmt]
            fmts = [f for f in fmts if job.get("saida") in (f, "ambos") or fmt != "ambos"]
            for f in fmts:
                try:
                    path, name = jobs.result_file(jid, f)
                except UserError:
                    continue
                base, n = name, 1
                while name in used:
                    n += 1
                    name = f"{Path(base).stem} ({n}){Path(base).suffix}"
                used.add(name)
                z.write(path, name)
    if not used:
        raise UserError("Nenhum arquivo confirmado para baixar.")
    return Response(buf.getvalue(), media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="documentos_padronizados.zip"'})


# ----------------------------------------------------------------------------- histórico

@app.get("/api/historico")
def get_history():
    return {"itens": jobs.history(), "retencao_horas": RETENTION_HOURS}


@app.delete("/api/historico")
def delete_history():
    jobs.clear_history()
    return {"ok": True}


# ----------------------------------------------------------------------------- modelos

@app.get("/api/modelos")
def list_models():
    return {"modelos": templates_store.list_templates()}


@app.get("/api/modelos/{tid}")
def get_model(tid: str):
    return templates_store.get_template(tid)


@app.post("/api/modelos")
async def create_model(request: Request):
    body = await request.json()
    return templates_store.create_template(body, body.get("base"))


@app.put("/api/modelos/{tid}")
async def update_model(tid: str, request: Request):
    return templates_store.save_template(tid, await request.json())


@app.post("/api/modelos/{tid}/duplicar")
def duplicate_model(tid: str):
    return templates_store.create_template({}, tid)


@app.post("/api/modelos/{tid}/restaurar")
def reset_model(tid: str):
    return templates_store.reset_template(tid)


@app.delete("/api/modelos/{tid}")
def delete_model(tid: str):
    templates_store.delete_template(tid)
    return {"ok": True}


@app.post("/api/modelos/{tid}/previa")
async def model_preview(tid: str, request: Request):
    body = await request.json()
    return await run_in_threadpool(jobs.template_preview, tid, body.get("settings"))


@app.get("/api/previa-modelo/{pid}/{pagina}")
async def model_preview_image(pid: str, pagina: int):
    path = await run_in_threadpool(jobs.template_preview_image, pid, pagina)
    return FileResponse(path, media_type="image/png")


@app.post("/api/logos")
async def upload_logo(arquivo: UploadFile = File(...)):
    data = await arquivo.read(LOGO_MAX_BYTES + 1)
    if len(data) > LOGO_MAX_BYTES:
        raise UserError("O logotipo deve ter no máximo 2 MB.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        if img.width * img.height > 40_000_000:
            raise UserError("Imagem grande demais.")
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        img.thumbnail((1200, 1200))
    except UserError:
        raise
    except Exception:
        raise UserError("Envie o logotipo em PNG ou JPG.")
    logo_id = uuid.uuid4().hex
    img.save(LOGOS_DIR / f"{logo_id}.png", "PNG")  # regravar elimina conteúdo oculto
    return {"id": logo_id}


@app.get("/api/logos/{logo_id}")
def get_logo(logo_id: str):
    if len(logo_id) != 32 or not all(c in "0123456789abcdef" for c in logo_id):
        raise UserError("Logotipo não encontrado.", 404)
    p = LOGOS_DIR / f"{logo_id}.png"
    if not p.exists():
        raise UserError("Logotipo não encontrado.", 404)
    return FileResponse(p, media_type="image/png")


# ----------------------------------------------------------------------------- interface

app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
