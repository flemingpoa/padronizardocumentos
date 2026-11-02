"""Validação de segurança dos arquivos enviados (tipo real, tamanho e estrutura)."""
import re
import unicodedata
import zipfile
from pathlib import Path

from .config import MAX_FILE_BYTES, MAX_FILE_MB, MAX_UNZIPPED_BYTES, MAX_ZIP_ENTRIES
from .errors import UserError

ACCEPTED = {".docx": "DOCX", ".doc": "DOC", ".odt": "ODT", ".pdf": "PDF"}


def safe_display_name(name: str) -> str:
    name = unicodedata.normalize("NFC", Path(name or "documento").name)
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]", "_", name).strip(" .")
    return name[:150] or "documento"


def detect_format(filename: str, head: bytes, path: Path) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ACCEPTED:
        raise UserError("Formato não aceito. Envie arquivos DOCX, DOC, ODT ou PDF.")
    size = path.stat().st_size
    if size == 0:
        raise UserError("O arquivo está vazio.")
    if size > MAX_FILE_BYTES:
        raise UserError(f"O arquivo é maior que o limite de {MAX_FILE_MB} MB.")

    if ext == ".pdf":
        if b"%PDF-" not in head[:1024]:
            raise UserError("O arquivo não é um PDF válido.")
        return "pdf"
    if ext == ".doc":
        if not head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            raise UserError("O arquivo .doc não é um documento do Word válido.")
        return "doc"
    # DOCX e ODT são pacotes ZIP
    if not head.startswith(b"PK"):
        raise UserError("O arquivo está danificado ou não é um documento válido.")
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise UserError("O documento tem estrutura interna suspeita e foi recusado.")
            if sum(i.file_size for i in infos) > MAX_UNZIPPED_BYTES:
                raise UserError("O documento é grande demais depois de descompactado e foi recusado.")
            names = {i.filename for i in infos}
            for n in names:
                if n.startswith("/") or ".." in n.split("/"):
                    raise UserError("O documento tem estrutura interna inválida e foi recusado.")
            if ext == ".docx":
                if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                    raise UserError("O arquivo .docx não é um documento do Word válido.")
                if any(n.lower().endswith("vbaproject.bin") for n in names):
                    raise UserError("O documento contém macros e foi recusado por segurança. "
                                    "Salve-o como .docx comum (sem macros) e envie novamente.")
                return "docx"
            mt = z.read("mimetype")[:100] if "mimetype" in names else b""
            if b"opendocument.text" not in mt:
                raise UserError("O arquivo .odt não é um documento de texto OpenDocument válido.")
            return "odt"
    except zipfile.BadZipFile:
        raise UserError("O arquivo está danificado ou não é um documento válido.")
