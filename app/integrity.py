"""Conferência de integridade: compara o conteúdo antes e depois da padronização."""
import difflib
import re
import unicodedata
from collections import Counter
from pathlib import Path

import fitz

from .docxutil import body_text_words, media_counts

LABEL_TOKEN = re.compile(
    r"^(\(?[a-jA-J0-9]{1,3}[\.\)\-–—:]*\)?|[\-–—:.)(]+|quest[ãa]o|questão|QUESTÃO|exerc[íi]cio|n[º°o]\.?)$",
    re.I)


def snapshot(doc):
    body = doc.element.body
    return {"palavras": body_text_words(body), "midia": media_counts(body)}


def compare(before, after):
    a, b = before["palavras"], after["palavras"]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    label_changes = 0
    other = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        old, new = a[i1:i2], b[j1:j2]
        if old and new and all(LABEL_TOKEN.match(w) for w in old + new) and len(old) <= 4 \
                and len(new) <= 4:
            label_changes += 1
            continue
        other.append({"tipo": {"replace": "alterado", "delete": "removido", "insert": "inserido"}[op],
                      "antes": " ".join(old)[:160], "depois": " ".join(new)[:160]})
    media_diff = {k: (before["midia"][k], after["midia"][k]) for k in before["midia"]
                  if before["midia"][k] > after["midia"][k]}
    ok = not other and not media_diff
    return {
        "status": "preservado" if ok else "alerta",
        "palavras_antes": len(a),
        "palavras_depois": len(b),
        "rotulos_alterados": label_changes,
        "diferencas": other[:30],
        "total_diferencas": len(other),
        "midia_antes": before["midia"],
        "midia_depois": after["midia"],
        "midia_perdida": media_diff,
    }


def _norm_words(text):
    text = unicodedata.normalize("NFC", text).lower()
    return [w for w in re.findall(r"\w+", text) if w]


def pdf_coverage(words, pdf_path: Path):
    """Percentual das palavras do documento que aparecem no PDF gerado."""
    want = Counter(_norm_words(" ".join(words)))
    if not want:
        return 100.0
    with fitz.open(pdf_path) as d:
        text = " ".join(page.get_text("text") for page in d)
    have = Counter(_norm_words(text.replace("­", "")))
    found = sum(min(n, have.get(w, 0)) for w, n in want.items())
    return round(100.0 * found / sum(want.values()), 1)
