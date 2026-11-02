"""Teste rápido do motor: padroniza o documento de exemplo com cada modelo."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document  # noqa: E402

from app import analyzer, converters  # noqa: E402
from app.jobs import resolve_settings, standardize_file  # noqa: E402
from app.sample import build_sample  # noqa: E402

out = Path(__file__).resolve().parent / "saida"
out.mkdir(exist_ok=True)
src = build_sample(out / "exemplo.docx")
items, summary = analyzer.analyze(Document(src))
for it in items:
    if it["type"] != "empty":
        print(f"{it['type']:<13} | {it['text'][:70]}")
print(summary)
ids = sys.argv[1:] or ["prova"]
for tid in ids:
    _, s = resolve_settings(tid, {"header": {"institution": "Escola Estadual Exemplo",
                                              "discipline": "Ciências", "teacher": "Ana Souza"}})
    t = time.time()
    rep, check, _ = standardize_file(src, out / f"{tid}.docx", s)
    print(tid, rep, check["status"], check["palavras_antes"], check["palavras_depois"],
          check["diferencas"], check["midia_perdida"])
    converters.convert(out / f"{tid}.docx", "pdf", out / f"{tid}.pdf")
    print("pdf ok", converters.page_count(out / f"{tid}.pdf"), f"{time.time() - t:.1f}s")
