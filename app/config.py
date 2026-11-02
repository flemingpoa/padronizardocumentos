"""Configurações gerais. Podem ser alteradas por variáveis de ambiente."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
DATA_DIR = Path(os.environ.get("PRUMO_DADOS", BASE_DIR / "dados"))
JOBS_DIR = DATA_DIR / "trabalhos"
LOGOS_DIR = DATA_DIR / "logos"
PREVIEWS_DIR = DATA_DIR / "previas_modelos"
TEMPLATES_FILE = DATA_DIR / "modelos.json"
HISTORY_FILE = DATA_DIR / "historico.json"

# Limites
MAX_FILE_MB = int(os.environ.get("PRUMO_TAMANHO_MAX_MB", "25"))
MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
MAX_FILES_PER_UPLOAD = 10
MAX_UNZIPPED_BYTES = 300 * 1024 * 1024
MAX_ZIP_ENTRIES = 5000
PDF_MAX_PAGES = 150
OCR_MAX_PAGES = 40
LOGO_MAX_BYTES = 2 * 1024 * 1024

# Privacidade: por quanto tempo os arquivos ficam guardados
RETENTION_HOURS = float(os.environ.get("PRUMO_RETENCAO_HORAS", "24"))

# Senha de acesso opcional (recomendado ao publicar na internet)
ACCESS_PASSWORD = os.environ.get("PRUMO_SENHA", "")

for d in (DATA_DIR, JOBS_DIR, LOGOS_DIR, PREVIEWS_DIR):
    d.mkdir(parents=True, exist_ok=True)
