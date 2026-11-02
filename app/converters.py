"""Conversões com o LibreOffice (DOC/ODT -> DOCX e DOCX -> PDF) e renderização de páginas."""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path

import fitz  # PyMuPDF

from .errors import UserError

_lock = threading.Lock()
_PROFILE_DIR = Path(tempfile.gettempdir()) / "prumo_lo_perfil"


def find_soffice():
    env = os.environ.get("PRUMO_SOFFICE")
    if env and Path(env).exists():
        return env
    candidates = []
    if sys.platform.startswith("win"):
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            candidates += [Path(base) / "LibreOffice" / "program" / "soffice.com",
                           Path(base) / "LibreOffice" / "program" / "soffice.exe"]
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"))
    for c in candidates:
        if c.exists():
            return str(c)
    return shutil.which("soffice") or shutil.which("libreoffice")


SOFFICE = find_soffice()


def available():
    return SOFFICE is not None


def convert(src: Path, target_ext: str, dest: Path, timeout=180):
    """Converte `src` para `target_ext` ('docx' ou 'pdf') e grava em `dest`.

    A conversão roda em uma pasta temporária com nomes simples (evita problemas com
    acentos no caminho) e com um perfil isolado do LibreOffice.
    """
    if not SOFFICE:
        raise UserError("O conversor de documentos (LibreOffice) não está instalado no servidor.")
    filters = {"docx": 'docx:MS Word 2007 XML', "pdf": "pdf:writer_pdf_Export"}
    with _lock, tempfile.TemporaryDirectory(prefix="prumo_conv_") as tmp:
        tmp = Path(tmp)
        work_in = tmp / f"entrada{src.suffix.lower()}"
        shutil.copyfile(src, work_in)
        out_dir = tmp / "saida"
        out_dir.mkdir()
        cmd = [SOFFICE, "--headless", "--norestore", "--nolockcheck", "--nodefault",
               "--nologo", f"-env:UserInstallation={_PROFILE_DIR.as_uri()}",
               "--convert-to", filters[target_ext], "--outdir", str(out_dir), str(work_in)]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout, check=False,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            raise UserError("A conversão demorou demais e foi interrompida. "
                            "Tente um arquivo menor ou divida o documento.")
        produced = out_dir / f"entrada.{target_ext}"
        if not produced.exists() or produced.stat().st_size == 0:
            raise UserError("Não foi possível converter o arquivo. Ele pode estar danificado "
                            "ou protegido por senha.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(produced), dest)
    return dest


def page_count(pdf_path: Path) -> int:
    with fitz.open(pdf_path) as d:
        return d.page_count


def render_page(pdf_path: Path, page_no: int, out_png: Path, dpi=110):
    """Gera a imagem PNG de uma página (1 = primeira) para a prévia."""
    if out_png.exists():
        return out_png
    with fitz.open(pdf_path) as d:
        if page_no < 1 or page_no > d.page_count:
            raise UserError("Página inexistente.")
        pix = d[page_no - 1].get_pixmap(dpi=dpi, alpha=False)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_png.with_suffix(f".{uuid.uuid4().hex}.tmp")
        pix.save(str(tmp), output="png")
        os.replace(tmp, out_png)
    return out_png
