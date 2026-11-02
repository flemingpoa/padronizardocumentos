"""Fluxo de trabalho: recebimento, análise, padronização, prévia, histórico e limpeza."""
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from docx import Document

from . import analyzer, converters, formatter, integrity, pdf_import, perfis
from .config import HISTORY_FILE, JOBS_DIR, LOGOS_DIR, PREVIEWS_DIR, RETENTION_HOURS
from .default_templates import deep_merge
from .errors import UserError
from .templates_store import get_template, sanitize_settings

_hist_lock = threading.Lock()
_job_locks = {}
_job_locks_guard = threading.Lock()

FORMAT_LABEL = {"docx": "DOCX", "doc": "DOC", "odt": "ODT", "pdf": "PDF"}


def _job_lock(job_id):
    with _job_locks_guard:
        return _job_locks.setdefault(job_id, threading.Lock())


def _valid_id(job_id):
    return isinstance(job_id, str) and len(job_id) == 32 and all(c in "0123456789abcdef" for c in job_id)


def job_dir(job_id) -> Path:
    if not _valid_id(job_id):
        raise UserError("Documento não encontrado.", 404)
    return JOBS_DIR / job_id


def load_job(job_id):
    p = job_dir(job_id) / "job.json"
    if not p.exists():
        raise UserError("Documento não encontrado ou já expirado.", 404)
    return json.loads(p.read_text(encoding="utf-8"))


def save_job(job):
    d = job_dir(job["id"])
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "job.tmp"
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, d / "job.json")


def public_job(job):
    keys = ("id", "nome", "formato", "tamanho", "criado", "expira", "status", "analise",
            "estrutura", "pdf_info", "modelo_id", "modelo_nome", "saida", "relatorio",
            "integridade", "paginas_original", "paginas_resultado", "erro", "precisa_ocr",
            "ocr_relatorio", "avisos", "nome_saida", "perfil")
    return {k: job.get(k) for k in keys}


# ----------------------------------------------------------------------------- histórico

def _read_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return []


def _write_history(items):
    tmp = HISTORY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, HISTORY_FILE)


def upsert_history(job):
    rec = {"id": job["id"], "nome": job["nome"], "data": job.get("processado") or job["criado"],
           "modelo": job.get("modelo_nome"), "entrada": FORMAT_LABEL.get(job["formato"]),
           "saida": job.get("saida"), "status": job["status"], "expira": job["expira"],
           "integridade": (job.get("integridade") or {}).get("status")}
    with _hist_lock:
        items = [h for h in _read_history() if h["id"] != job["id"]]
        items.insert(0, rec)
        _write_history(items[:500])


def history():
    now = time.time()
    items = _read_history()
    for h in items:
        h["disponivel"] = h.get("expira", 0) > now and (JOBS_DIR / h["id"] / "job.json").exists()
        if not h["disponivel"] and h["status"] in ("confirmado", "processado"):
            h["status"] = "expirado"
    return items


def delete_job(job_id, keep_history=False):
    d = job_dir(job_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    if not keep_history:
        with _hist_lock:
            _write_history([h for h in _read_history() if h["id"] != job_id])


def clear_history():
    with _hist_lock:
        items = _read_history()
        _write_history([])
    for h in items:
        d = JOBS_DIR / h["id"]
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


def cleanup_expired():
    """Apaga arquivos vencidos (privacidade). O registro no histórico permanece sem os arquivos."""
    now = time.time()
    for d in JOBS_DIR.iterdir() if JOBS_DIR.exists() else []:
        try:
            job = json.loads((d / "job.json").read_text(encoding="utf-8"))
            expired = job.get("expira", 0) < now
        except Exception:
            expired = (now - d.stat().st_mtime) > RETENTION_HOURS * 3600
        if expired:
            shutil.rmtree(d, ignore_errors=True)
    for d in PREVIEWS_DIR.iterdir() if PREVIEWS_DIR.exists() else []:
        if now - d.stat().st_mtime > 3600:
            shutil.rmtree(d, ignore_errors=True)


def start_cleanup_thread():
    def loop():
        while True:
            try:
                cleanup_expired()
            except Exception:
                pass
            time.sleep(1800)
    threading.Thread(target=loop, daemon=True, name="limpeza").start()


# ----------------------------------------------------------------------------- análise

def _analyze_docx(job, d):
    doc = Document(d / "normalizado.docx")
    items, summary = analyzer.analyze(doc)
    job["analise"] = summary
    job["estrutura"] = analyzer.structure_list(items)


def create_job(tmp_path: Path, display_name: str, fmt: str):
    job_id = uuid.uuid4().hex
    d = job_dir(job_id)
    d.mkdir(parents=True)
    original = d / f"original.{fmt}"
    shutil.move(str(tmp_path), original)
    now = time.time()
    job = {"id": job_id, "nome": display_name, "formato": fmt, "tamanho": original.stat().st_size,
           "criado": now, "expira": now + RETENTION_HOURS * 3600, "status": "analisando",
           "avisos": [], "precisa_ocr": False}
    save_job(job)
    try:
        if fmt == "docx":
            shutil.copyfile(original, d / "normalizado.docx")
        elif fmt in ("doc", "odt"):
            converters.convert(original, "docx", d / "normalizado.docx")
            job["avisos"].append(f"O arquivo {FORMAT_LABEL[fmt]} foi convertido para DOCX para a "
                                 "padronização. O original continua guardado sem alterações.")
        elif fmt == "pdf":
            info = pdf_import.inspect(original)
            job["pdf_info"] = info
            if info["paginas_digitalizadas"]:
                job["precisa_ocr"] = True
                job["status"] = "aguardando_ocr"
                save_job(job)
                return job
            rep = pdf_import.pdf_to_docx(original, d / "normalizado.docx", use_ocr=False)
            job["ocr_relatorio"] = rep
            job["avisos"].extend(rep["avisos"])
        _validate_docx(d / "normalizado.docx")
        _analyze_docx(job, d)
        job["status"] = "analisado"
    except UserError as e:
        job["status"] = "erro"
        job["erro"] = e.message
    except Exception:
        job["status"] = "erro"
        job["erro"] = ("Não foi possível ler este documento. Verifique se ele abre normalmente "
                       "no Word e tente novamente.")
    save_job(job)
    return job


def _validate_docx(path):
    try:
        Document(path)
    except Exception:
        raise UserError("O documento não pôde ser lido. Ele pode estar danificado.")


def run_pdf_conversion(job_id, use_ocr, highlight=True):
    with _job_lock(job_id):
        job = load_job(job_id)
        if job["formato"] != "pdf":
            raise UserError("Esta opção vale apenas para PDFs.")
        d = job_dir(job_id)
        rep = pdf_import.pdf_to_docx(d / "original.pdf", d / "normalizado.docx",
                                     use_ocr=use_ocr, highlight_doubtful=highlight)
        job["ocr_relatorio"] = rep
        job["avisos"] = [a for a in job.get("avisos", []) if "PDF" not in a] + rep["avisos"]
        job["precisa_ocr"] = False
        job["ocr_feito"] = bool(use_ocr)
        _analyze_docx(job, d)
        job["status"] = "analisado"
        save_job(job)
        return job


# ----------------------------------------------------------------------------- padronização

HEADER_OVERRIDE_KEYS = ("institution", "discipline", "teacher", "class_name", "date", "extra")


def resolve_settings(template_id, overrides=None, settings=None):
    tpl = get_template(template_id)
    s = settings if settings is not None else tpl["settings"]
    if overrides:
        hdr = {k: str(v)[:200] for k, v in (overrides.get("header") or {}).items()
               if k in HEADER_OVERRIDE_KEYS and v is not None}
        s = deep_merge(s, {"header": hdr})
    return tpl, sanitize_settings(s)


def _logo_path(s):
    logo = s["header"].get("logo")
    if logo:
        p = LOGOS_DIR / f"{logo}.png"
        if p.exists():
            return p
    return None


def standardize_file(src_docx: Path, out_docx: Path, s, type_overrides=None):
    doc = Document(src_docx)
    before = integrity.snapshot(doc)
    items, _ = analyzer.analyze(doc)
    if type_overrides:
        for it in items:
            new = type_overrides.get(str(it["index"]))
            if new in analyzer.TYPE_LABELS and new != it["type"]:
                it["type"] = new
                if new == "question":
                    m = analyzer.QUESTION_RE.match(it["text"])
                    it["meta"] = {"label": m.group("label"), "number": m.group("n1") or m.group("n2"),
                                  "worded": bool(m.group("word"))} if m else {}
                elif new == "alternative":
                    m = analyzer.ALT_RE.match(it["text"])
                    it["meta"] = {"label": m.group("label"),
                                  "letter": m.group("l1") or m.group("l2") or m.group("l3")} if m else {}
                else:
                    it["meta"] = {}
    report = formatter.apply(doc, items, s, _logo_path(s))
    doc.save(out_docx)
    after = integrity.snapshot(Document(out_docx))
    extra = report.get("palavras_grade") or 0
    if extra:
        # a grade de respostas acrescentada no fim não faz parte do conteúdo original
        after["palavras"] = after["palavras"][:-extra]
        after["midia"]["tabelas"] -= 1
    check = integrity.compare(before, after)
    return report, check, before


def process_job(job_id, template_id, output, overrides=None, type_overrides=None, perfil=None):
    if output not in ("docx", "pdf", "ambos"):
        output = "ambos"
    if perfil:
        perfil = perfis.validar(perfil)
    with _job_lock(job_id):
        job = load_job(job_id)
        if job["status"] in ("erro",):
            raise UserError(job.get("erro") or "Este documento não pode ser processado.")
        if job.get("precisa_ocr"):
            raise UserError("Este PDF é digitalizado. Escolha primeiro como convertê-lo.")
        d = job_dir(job_id)
        if perfil:
            # perfis do Fleming (Prova / Lista de exercícios)
            tpl = {"id": perfil["tipo"], "name": perfis.rotulo(perfil)}
            s = sanitize_settings(perfis.settings(perfil))
            job["perfil"] = perfil
            job["nome_saida"] = perfis.nome_arquivo(perfil)
        else:
            tpl, s = resolve_settings(template_id, overrides)
            job.pop("nome_saida", None)
        try:
            report, check, before = standardize_file(d / "normalizado.docx", d / "resultado.docx", s,
                                                     type_overrides)
            converters.convert(d / "resultado.docx", "pdf", d / "resultado.pdf")
        except UserError:
            raise
        except Exception:
            raise UserError("Ocorreu um erro inesperado ao padronizar este documento. "
                            "O arquivo original não foi alterado.", 500)
        check["cobertura_pdf"] = integrity.pdf_coverage(before["palavras"], d / "resultado.pdf")
        if check["cobertura_pdf"] < 97 and check["palavras_antes"] > 20:
            check["status"] = "alerta"
        # prévia do original para comparação
        orig_pdf = d / "original_previa.pdf"
        if not orig_pdf.exists():
            try:
                if job["formato"] == "pdf":
                    shutil.copyfile(d / "original.pdf", orig_pdf)
                else:
                    converters.convert(d / f"original.{job['formato']}", "pdf", orig_pdf)
            except Exception:
                pass
        shutil.rmtree(d / "previa", ignore_errors=True)
        job.update({
            "status": "processado", "modelo_id": tpl["id"], "modelo_nome": tpl["name"],
            "saida": output, "relatorio": report, "integridade": check,
            "paginas_resultado": converters.page_count(d / "resultado.pdf"),
            "paginas_original": converters.page_count(orig_pdf) if orig_pdf.exists() else None,
            "processado": time.time(), "type_overrides": type_overrides or {},
        })
        save_job(job)
        upsert_history(job)
        return job


def confirm_job(job_id):
    with _job_lock(job_id):
        job = load_job(job_id)
        if job["status"] not in ("processado", "confirmado"):
            raise UserError("O documento ainda não foi padronizado.")
        job["status"] = "confirmado"
        save_job(job)
        upsert_history(job)
        return job


def preview_image(job_id, kind, page):
    d = job_dir(job_id)
    pdf = d / ("resultado.pdf" if kind == "resultado" else "original_previa.pdf")
    if not pdf.exists():
        raise UserError("Prévia indisponível.", 404)
    return converters.render_page(pdf, page, d / "previa" / f"{kind}-{page}.png")


def result_file(job_id, fmt):
    job = load_job(job_id)
    if job["status"] != "confirmado":
        raise UserError("Confirme a padronização antes de baixar o arquivo.")
    if fmt not in ("docx", "pdf"):
        raise UserError("Formato inválido.")
    path = job_dir(job_id) / f"resultado.{fmt}"
    if not path.exists():
        raise UserError("Arquivo não disponível.", 404)
    stem = job.get("nome_saida") or f"{Path(job['nome']).stem}_padronizado"
    return path, f"{stem}.{fmt}"


def original_file(job_id):
    job = load_job(job_id)
    path = job_dir(job_id) / f"original.{job['formato']}"
    if not path.exists():
        raise UserError("Arquivo não disponível.", 404)
    return path, job["nome"]


# ----------------------------------------------------------------------------- prévia de modelos

def template_preview(template_id, settings):
    """Aplica configurações (ainda não salvas) a um documento de exemplo e gera a prévia."""
    from .sample import ensure_sample
    tpl, s = resolve_settings(template_id, None, settings)
    pid = uuid.uuid4().hex
    d = PREVIEWS_DIR / pid
    d.mkdir(parents=True)
    standardize_file(ensure_sample(), d / "exemplo.docx", s)
    converters.convert(d / "exemplo.docx", "pdf", d / "exemplo.pdf")
    return {"id": pid, "paginas": converters.page_count(d / "exemplo.pdf")}


def template_preview_image(pid, page):
    if not _valid_id(pid):
        raise UserError("Prévia não encontrada.", 404)
    d = PREVIEWS_DIR / pid
    if not (d / "exemplo.pdf").exists():
        raise UserError("Prévia expirada. Gere novamente.", 404)
    return converters.render_page(d / "exemplo.pdf", page, d / f"p{page}.png")
