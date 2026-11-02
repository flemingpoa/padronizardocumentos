"""Leitura de PDFs: diagnóstico (texto, digitalizado ou misto) e reconstrução como DOCX editável.

PDF não guarda parágrafos, estilos ou tabelas como o Word. Por isso o documento é
RECONSTRUÍDO a partir do texto, das imagens e das tabelas encontradas, e o resultado
sempre é marcado como "precisa de conferência".
"""
import csv
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import fitz
from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.shared import Cm, Pt

from .analyzer import ALT_RE, BULLET_RE, QUESTION_RE
from .config import OCR_MAX_PAGES, PDF_MAX_PAGES
from .errors import UserError


# ----------------------------------------------------------------------------- OCR

def find_tesseract():
    env = os.environ.get("PRUMO_TESSERACT")
    if env and Path(env).exists():
        return env
    found = shutil.which("tesseract")
    if found:
        return found
    if sys.platform.startswith("win"):
        for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", ""),
                     os.environ.get("ProgramFiles(x86)", "")):
            for sub in (Path(base) / "Programs" / "Tesseract-OCR", Path(base) / "Tesseract-OCR"):
                exe = sub / "tesseract.exe"
                if exe.exists():
                    return str(exe)
    return None


TESSERACT = find_tesseract()


def ocr_languages():
    if not TESSERACT:
        return []
    try:
        out = subprocess.run([TESSERACT, "--list-langs"], capture_output=True, text=True,
                             timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        langs = [l.strip() for l in out.stdout.splitlines()[1:] if l.strip()]
        return langs
    except Exception:
        return []


OCR_LANGS = ocr_languages()


def ocr_available():
    return bool(TESSERACT) and "por" in OCR_LANGS


def _run_tesseract(png_path: Path):
    lang = "por" if "por" in OCR_LANGS else "eng"
    cmd = [TESSERACT, str(png_path), "stdout", "-l", lang, "--psm", "3", "tsv"]
    res = subprocess.run(cmd, capture_output=True, timeout=180,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if res.returncode != 0:
        raise UserError("O reconhecimento de texto (OCR) falhou nesta página.")
    text = res.stdout.decode("utf-8", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text), delimiter="\t", quoting=csv.QUOTE_NONE))
    return rows


# ----------------------------------------------------------------------------- diagnóstico

def inspect(pdf_path: Path):
    """Classifica as páginas do PDF sem alterá-lo."""
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        raise UserError("Não foi possível abrir o PDF. O arquivo pode estar danificado.")
    with doc:
        if doc.needs_pass or doc.is_encrypted:
            raise UserError("Este PDF está protegido por senha. Remova a proteção e envie novamente.")
        if doc.page_count == 0:
            raise UserError("O PDF não tem páginas.")
        if doc.page_count > PDF_MAX_PAGES:
            raise UserError(f"O PDF tem {doc.page_count} páginas. O limite é {PDF_MAX_PAGES}.")
        kinds = []
        for page in doc:
            txt = page.get_text("text").strip()
            area = abs(page.rect)
            img_area = 0.0
            for info in page.get_image_info():
                r = fitz.Rect(info["bbox"]) & page.rect
                img_area += abs(r)
            if len(txt) >= 30:
                kinds.append("misto" if img_area > 0.6 * area else "texto")
            elif img_area > 0.3 * area:
                kinds.append("digitalizado")
            else:
                kinds.append("vazio" if not txt else "texto")
        c = Counter(kinds)
        if c.get("digitalizado") and (c.get("texto") or c.get("misto")):
            overall = "misto"
        elif c.get("digitalizado"):
            overall = "digitalizado"
        else:
            overall = "texto"
        return {"paginas": doc.page_count, "tipos_paginas": kinds, "tipo": overall,
                "paginas_digitalizadas": [i + 1 for i, k in enumerate(kinds) if k == "digitalizado"]}


# ----------------------------------------------------------------------------- reconstrução

def _new_paragraph_line(text):
    return bool(QUESTION_RE.match(text) or ALT_RE.match(text) or BULLET_RE.match(text))


def _join(prev, nxt):
    if prev.endswith("-") and nxt[:1].islower() and len(prev) > 1 and prev[-2].isalpha():
        return prev[:-1] + nxt, True  # hifenização de fim de linha
    return (prev + " " + nxt) if prev else nxt, False


def _repeated_margin_lines(doc):
    """Linhas que se repetem no topo/rodapé de muitas páginas (cabeçalhos do PDF)."""
    if doc.page_count < 2:
        return set()
    counter = Counter()
    for page in doc:
        h = page.rect.height
        seen = set()
        for b in page.get_text("blocks"):
            x0, y0, x1, y1, text = b[:5]
            t = re.sub(r"\s+", " ", text).strip()
            t_norm = re.sub(r"\d+", "#", t)
            if t and (y1 < h * 0.08 or y0 > h * 0.92) and t_norm not in seen:
                seen.add(t_norm)
                counter[t_norm] += 1
    return {t for t, n in counter.items() if n >= max(2, doc.page_count * 0.6)}


def _add_runs(par, spans, hl_low=None):
    for sp in spans:
        text = sp["text"]
        if not text:
            continue
        r = par.add_run(text)
        flags = sp.get("flags", 0)
        font = sp.get("font", "")
        if flags & 16 or "bold" in font.lower() or "black" in font.lower():
            r.bold = True
        if flags & 2 or "italic" in font.lower() or "oblique" in font.lower():
            r.italic = True
        if flags & 1:
            r.font.superscript = True
        size = sp.get("size")
        if size:
            r.font.size = Pt(max(6, round(size * 2) / 2))
        if hl_low and sp.get("low"):
            r.font.highlight_color = WD_COLOR_INDEX.YELLOW


def _text_page(page, docx, tmpdir, skip_lines, report):
    tables = []
    try:
        for t in page.find_tables().tables:
            tables.append(t)
    except Exception:
        pass
    table_rects = [fitz.Rect(t.bbox) for t in tables]

    # gráficos vetoriais (desenhos) viram imagem para não se perderem
    vector_rects = []
    try:
        for r in page.cluster_drawings():
            r = fitz.Rect(r)
            if r.width < 40 or r.height < 40:
                continue
            if any(abs(r & tr) > 0.5 * abs(r) for tr in table_rects):
                continue
            vector_rects.append(r)
    except Exception:
        pass

    def inside_any(rect, rects, frac=0.6):
        return any(abs(rect & r) > frac * max(abs(rect), 1) for r in rects)

    items = []  # (y, x, kind, payload)
    flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES
    blocks = [b for b in page.get_text("dict", sort=True, flags=flags)["blocks"] if b.get("type") == 0]

    # fórmulas: blocos com fontes matemáticas (e pedaços vizinhos, como numerador e
    # denominador) são mantidos como imagem, pois o texto solto embaralharia a fórmula
    math_rects = []
    for b in blocks:
        fonts = {s["font"].lower() for ln in b["lines"] for s in ln["spans"]}
        if any(re.search(r"math|symbol|mt extra|cmsy|cmmi|cmex|euclid", f) for f in fonts):
            math_rects.append(fitz.Rect(b["bbox"]))
    absorbed = set()
    for mr in math_rects:
        grew = True
        while grew:
            grew = False
            for i, b in enumerate(blocks):
                r = fitz.Rect(b["bbox"])
                if i in absorbed:
                    continue
                txt = "".join(s["text"] for ln in b["lines"] for s in ln["spans"]).strip()
                near = fitz.Rect(mr.x0 - 30, mr.y0 - 14, mr.x1 + 30, mr.y1 + 14)
                close = not (r & near).is_empty and len(txt) <= 25
                if close or abs(r & mr) > 0.5 * max(abs(r), 1):
                    if not mr.contains(r):
                        mr |= r
                        grew = True
                    absorbed.add(i)
    merged_math = []
    for mr in math_rects:
        if not any(abs(mr & m) > 0.5 * abs(mr) for m in merged_math):
            merged_math.append(mr)
    for mr in merged_math:
        items.append((mr.y0, mr.x0, "formula", mr))

    for i, b in enumerate(blocks):
        rect = fitz.Rect(b["bbox"])
        if i in absorbed or inside_any(rect, table_rects) or inside_any(rect, vector_rects, 0.8):
            continue
        items.append((rect.y0, rect.x0, "text", b))

    # imagens: usa a lista de imagens da página (inclui imagens maiores que a folha)
    seen_xrefs = set()
    for info in page.get_image_info(xrefs=True):
        rect = fitz.Rect(info["bbox"]) & page.rect
        if rect.is_empty or rect.width < 8 or rect.height < 8 or inside_any(rect, vector_rects):
            continue
        key = (info.get("xref"), tuple(round(v) for v in rect))
        if key in seen_xrefs:
            continue
        seen_xrefs.add(key)
        items.append((rect.y0, rect.x0, "image", (info, rect)))
    for t, tr in zip(tables, table_rects):
        items.append((tr.y0, tr.x0, "table", t))
    for vr in vector_rects:
        items.append((vr.y0, vr.x0, "vector", vr))
    items.sort(key=lambda x: (round(x[0], 0), x[1]))

    for _, _, kind, payload in items:
        if kind == "text":
            paragraphs = []  # lista de listas de spans
            cur, cur_text = [], ""
            last_y1, last_h = None, None
            for line in payload["lines"]:
                spans = [dict(s) for s in line["spans"] if s["text"].strip() or s["text"] == " "]
                if not spans:
                    continue
                ltext = "".join(s["text"] for s in spans).strip()
                if re.sub(r"\d+", "#", re.sub(r"\s+", " ", ltext)) in skip_lines:
                    report["linhas_repetidas_ignoradas"] += 1
                    continue
                y0, y1 = line["bbox"][1], line["bbox"][3]
                h = y1 - y0
                gap = (y0 - last_y1) if last_y1 is not None else 0
                start_new = not cur or _new_paragraph_line(ltext) or \
                    (last_h and gap > 0.9 * last_h)
                if start_new and cur:
                    paragraphs.append(cur)
                    cur, cur_text = [], ""
                if cur:
                    joined, dehyph = _join(cur_text, ltext)
                    if dehyph:
                        last = cur[-1]
                        last["text"] = last["text"].rstrip()
                        if last["text"].endswith("-"):
                            last["text"] = last["text"][:-1]
                        report["hifenizacoes_desfeitas"] += 1
                    else:
                        cur[-1]["text"] = cur[-1]["text"].rstrip() + " "
                    cur_text = joined
                else:
                    cur_text = ltext
                spans[0]["text"] = spans[0]["text"].lstrip()
                cur.extend(spans)
                last_y1, last_h = y1, h
            if cur:
                paragraphs.append(cur)
            for spans in paragraphs:
                par = docx.add_paragraph()
                if spans:
                    spans[-1]["text"] = spans[-1]["text"].rstrip()
                _add_runs(par, spans)
        elif kind == "image":
            info, rect = payload
            n = report["imagens"]
            path = None
            full = fitz.Rect(info["bbox"])
            tr = info.get("transform") or (1, 0, 0, 1, 0, 0)
            simple = abs(tr[1]) < 1e-3 and abs(tr[2]) < 1e-3 and not info.get("has-mask")
            if info.get("xref") and simple and abs(abs(full) - abs(rect)) < 1:
                # imagem inteira e sem transparência: usa o arquivo original (melhor qualidade)
                try:
                    img = page.parent.extract_image(info["xref"])
                    if img and img.get("ext") in ("png", "jpeg", "jpg", "gif", "bmp"):
                        path = Path(tmpdir) / f"img_{page.number}_{n}.{img['ext']}"
                        path.write_bytes(img["image"])
                except Exception:
                    path = None
            if path is None:
                # recorta a área visível da página (respeita cortes, rotações e transparências)
                pix = page.get_pixmap(clip=rect, dpi=200, alpha=False)
                path = Path(tmpdir) / f"img_{page.number}_{n}.png"
                pix.save(str(path))
            try:
                docx.add_paragraph().add_run().add_picture(str(path), width=Pt(max(20, rect.width)))
                report["imagens"] += 1
            except Exception:
                report["avisos"].append(f"Uma imagem da página {page.number + 1} não pôde ser convertida.")
        elif kind == "formula":
            pix = page.get_pixmap(clip=payload, dpi=300, alpha=False)
            path = Path(tmpdir) / f"formula_{page.number}_{report['formulas_imagem']}.png"
            pix.save(str(path))
            par = docx.add_paragraph()
            par.alignment = 1
            par.add_run().add_picture(str(path), width=Pt(payload.width))
            report["formulas_imagem"] += 1
        elif kind == "vector":
            pix = page.get_pixmap(clip=payload, dpi=200, alpha=False)
            path = Path(tmpdir) / f"graf_{report['graficos_rasterizados']}_{page.number}.png"
            pix.save(str(path))
            docx.add_paragraph().add_run().add_picture(str(path), width=Pt(payload.width))
            report["graficos_rasterizados"] += 1
        elif kind == "table":
            try:
                data = payload.extract()
            except Exception:
                data = []
            if not data:
                continue
            ncols = max(len(r) for r in data)
            tbl = docx.add_table(rows=len(data), cols=ncols)
            tbl.style = "Table Grid"
            for ri, row in enumerate(data):
                for ci in range(ncols):
                    val = row[ci] if ci < len(row) else None
                    if val:
                        tbl.cell(ri, ci).paragraphs[0].add_run(str(val).replace("\n", " "))
            report["tabelas"] += 1
            docx.add_paragraph()


def _ocr_rows(page, tmpdir):
    pix = page.get_pixmap(dpi=300, alpha=False)
    png = Path(tmpdir) / f"ocr_{page.number}.png"
    pix.save(str(png))
    return _run_tesseract(png), pix.width, pix.height


def _norm_line(text):
    return re.sub(r"[^0-9a-zà-ú#]", "", re.sub(r"\d+", "#", text.lower()))


def _ocr_lines(rows):
    """{(bloco, parágrafo, linha): (texto, topo, base)} a partir da saída do Tesseract."""
    words, boxes = {}, {}
    for row in rows:
        try:
            level = int(row.get("level") or 0)
            key = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        except (ValueError, KeyError, TypeError):
            continue
        if level == 4:
            boxes[key] = (int(row["top"]), int(row["top"]) + int(row["height"]))
        elif level == 5 and (row.get("text") or "").strip():
            words.setdefault(key, []).append(row["text"].strip())
    return {k: (" ".join(w), *boxes.get(k, (0, 0))) for k, w in words.items()}


def _ocr_margin_repeats(pages_rows):
    """Linhas no topo/rodapé que se repetem nas páginas digitalizadas (cabeçalhos antigos)."""
    if len(pages_rows) < 2:
        return set()
    counter = Counter()
    for rows, _, height in pages_rows:
        seen = set()
        for text, top, bottom in _ocr_lines(rows).values():
            n = _norm_line(text)
            if n and (top < height * 0.08 or bottom > height * 0.92) and n not in seen:
                seen.add(n)
                counter[n] += 1
    return {t for t, n in counter.items() if n >= max(2, 0.6 * len(pages_rows))}


def _ocr_page(page, docx, tmpdir, report, highlight, ocr=None, skip=frozenset()):
    rows, pw, ph = ocr or _ocr_rows(page, tmpdir)
    scale = 72 / 300
    skip_keys = {k for k, (text, top, bottom) in _ocr_lines(rows).items()
                 if (top < ph * 0.08 or bottom > ph * 0.92) and _norm_line(text) in skip}
    if skip_keys:
        report["linhas_repetidas_ignoradas"] += len(skip_keys)
    blocks = {}
    block_boxes = {}
    line_h = {}
    for row in rows:
        try:
            level = int(row.get("level") or 0)
            conf = float(row.get("conf") or -1)
        except ValueError:
            continue
        key_b = row.get("block_num")
        box = tuple(int(row.get(k) or 0) for k in ("left", "top", "width", "height"))
        if level == 2:
            block_boxes[key_b] = box
        if level == 4:
            line_h[(int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))] = box[3]
        if level != 5:
            continue
        word = (row.get("text") or "").strip()
        if not word:
            continue
        key = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        if key in skip_keys:
            continue
        blocks.setdefault(key, []).append((word, conf))
        report["_conf_sum"] += conf
        report["_conf_n"] += 1
        if conf < 60:
            report["palavras_duvidosas"] += 1

    # regiões sem texto grandes = figuras da página digitalizada
    words_blocks = {str(k[0]) for k in blocks}
    page_area = pw * ph
    figures = []
    for b, (l, t, w, h) in block_boxes.items():
        if b not in words_blocks and w * h > 0.02 * page_area and w > 60 and h > 60:
            figures.append((t, l, w, h))

    # agrupa linhas em parágrafos (bloco + parágrafo do Tesseract)
    paras = {}
    sizes = {}
    for (b, p, ln), words in sorted(blocks.items()):
        paras.setdefault((b, p), []).append(words)
        if (b, p, ln) in line_h:
            sizes.setdefault((b, p), []).append(line_h[(b, p, ln)])
    entries = []
    for (b, p), lines in paras.items():
        top = block_boxes.get(str(b), (0, 0, 0, 0))[1]
        hs = sorted(sizes.get((b, p), []))
        # altura da linha (pixels a 300 dpi) -> tamanho aproximado da letra em pontos
        est = round(hs[len(hs) // 2] * 72 / 300 / 0.95 * 2) / 2 if hs else None
        entries.append((top, b, p, "text", (lines, est)))
    for (t, l, w, h) in figures:
        entries.append((t, -1, 0, "figure", (l, t, w, h)))
    entries.sort(key=lambda e: (e[0], e[1], e[2]) if e[3] == "figure" else (0, e[1], e[2]))
    # mantém a ordem de leitura do Tesseract e intercala figuras pela posição vertical
    text_entries = [e for e in entries if e[3] == "text"]
    fig_entries = sorted([e for e in entries if e[3] == "figure"], key=lambda e: e[0])
    merged = []
    for e in text_entries:
        while fig_entries and fig_entries[0][0] <= e[0]:
            merged.append(fig_entries.pop(0))
        merged.append(e)
    merged.extend(fig_entries)

    for e in merged:
        if e[3] == "figure":
            l, t, w, h = e[4]
            clip = fitz.Rect(l * scale, t * scale, (l + w) * scale, (t + h) * scale)
            fpix = page.get_pixmap(clip=clip, dpi=200, alpha=False)
            fpath = Path(tmpdir) / f"fig_{page.number}_{l}_{t}.png"
            fpix.save(str(fpath))
            docx.add_paragraph().add_run().add_picture(str(fpath), width=Pt(clip.width))
            report["imagens"] += 1
            continue
        lines, est = e[4]
        cur = []
        for words in lines:
            ltext = " ".join(w for w, _ in words)
            if cur and _new_paragraph_line(ltext):
                _emit_ocr_par(docx, cur, highlight, est)
                cur = []
            if cur:
                prev_word = cur[-1][0]
                if prev_word.endswith("-") and words and words[0][0][:1].islower():
                    cur[-1] = (prev_word[:-1] + words[0][0], min(cur[-1][1], words[0][1]))
                    words = words[1:]
                    report["hifenizacoes_desfeitas"] += 1
            cur.extend(words)
        if cur:
            _emit_ocr_par(docx, cur, highlight, est)


def _emit_ocr_par(docx, words, highlight, size=None):
    par = docx.add_paragraph()
    spans = []
    for i, (w, conf) in enumerate(words):
        sep = "" if i == len(words) - 1 else " "
        spans.append({"text": w + sep, "low": conf < 60, "size": size})
    # junta palavras vizinhas com a mesma marcação em um único trecho
    merged = []
    for sp in spans:
        if merged and merged[-1]["low"] == sp["low"]:
            merged[-1]["text"] += sp["text"]
        else:
            merged.append(dict(sp))
    _add_runs(par, merged, hl_low=highlight)


def pdf_to_docx(pdf_path: Path, out_docx: Path, use_ocr=False, highlight_doubtful=True):
    """Reconstrói o PDF como DOCX editável. Retorna relatório com avisos e qualidade do OCR."""
    report = {"imagens": 0, "tabelas": 0, "graficos_rasterizados": 0, "formulas_imagem": 0,
              "linhas_repetidas_ignoradas": 0,
              "hifenizacoes_desfeitas": 0, "paginas_ocr": 0, "palavras_duvidosas": 0,
              "_conf_sum": 0.0, "_conf_n": 0, "avisos": [], "ocr_qualidade": None}
    info = inspect(pdf_path)
    if use_ocr and not ocr_available():
        raise UserError("O reconhecimento de texto (OCR) não está instalado neste servidor.")
    scanned = info["paginas_digitalizadas"]
    if use_ocr and len(scanned) > OCR_MAX_PAGES:
        raise UserError(f"O PDF tem {len(scanned)} páginas digitalizadas. O limite para OCR é "
                        f"{OCR_MAX_PAGES} páginas por arquivo.")
    docx = Document()
    sec = docx.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    with fitz.open(pdf_path) as doc, tempfile.TemporaryDirectory(prefix="prumo_pdf_") as tmp:
        skip = _repeated_margin_lines(doc)
        ocr_data = {}
        if use_ocr:
            for n in scanned:
                ocr_data[n - 1] = _ocr_rows(doc[n - 1], tmp)
        ocr_skip = _ocr_margin_repeats(list(ocr_data.values()))
        for page in doc:
            kind = info["tipos_paginas"][page.number]
            if kind == "digitalizado":
                if use_ocr:
                    _ocr_page(page, docx, tmp, report, highlight_doubtful,
                              ocr_data.get(page.number), ocr_skip)
                    report["paginas_ocr"] += 1
                else:
                    # sem OCR: mantém a página como imagem para nada se perder
                    pix = page.get_pixmap(dpi=150, alpha=False)
                    p = Path(tmp) / f"pag_{page.number}.png"
                    pix.save(str(p))
                    docx.add_paragraph().add_run().add_picture(str(p), width=Cm(17))
                    report["imagens"] += 1
                    report["avisos"].append(f"A página {page.number + 1} é digitalizada e foi mantida "
                                            "como imagem (sem OCR).")
            elif kind != "vazio":
                _text_page(page, docx, tmp, skip, report)
        if not any(p.text.strip() for p in docx.paragraphs) and \
                report["imagens"] == 0 and report["tabelas"] == 0:
            raise UserError("Não foi encontrado conteúdo aproveitável neste PDF.")
        docx.save(out_docx)

    if report["_conf_n"]:
        q = report["_conf_sum"] / report["_conf_n"]
        report["ocr_qualidade"] = round(q, 1)
        if q < 55:
            report["avisos"].append(f"A qualidade da digitalização é BAIXA (confiança média {q:.0f}%). "
                                    "O texto reconhecido provavelmente tem muitos erros e precisa ser "
                                    "conferido com atenção.")
        elif q < 80:
            report["avisos"].append(f"Qualidade da digitalização moderada (confiança média {q:.0f}%). "
                                    "Confira o texto reconhecido.")
        else:
            report["avisos"].append(f"Qualidade da digitalização boa (confiança média {q:.0f}%). "
                                    "Mesmo assim, o texto reconhecido deve ser conferido.")
        if report["palavras_duvidosas"]:
            report["avisos"].append(
                f"{report['palavras_duvidosas']} palavra(s) com reconhecimento duvidoso"
                + (" foram destacadas em amarelo para conferência." if highlight_doubtful else "."))
    if report["paginas_ocr"]:
        report["avisos"].append("Em páginas digitalizadas, fórmulas matemáticas, símbolos, sublinhados "
                                "(ex.: “____”) e tabelas costumam ser reconhecidos com erros ou como texto "
                                "simples. Compare com o original antes de usar.")
    if skip or report["linhas_repetidas_ignoradas"]:
        report["avisos"].append("Cabeçalhos/rodapés repetidos em todas as páginas do PDF (ex.: número de "
                                "página) não foram copiados para o corpo do texto, pois o modelo cria "
                                "cabeçalho e rodapé próprios.")
    if report["formulas_imagem"]:
        report["avisos"].append(f"{report['formulas_imagem']} fórmula(s) matemática(s) do PDF foram mantidas "
                                "como imagem para não embaralhar os símbolos (não são editáveis).")
    if report["graficos_rasterizados"]:
        report["avisos"].append(f"{report['graficos_rasterizados']} gráfico(s)/desenho(s) do PDF foram "
                                "mantidos como imagem.")
    report["avisos"].insert(0, "O PDF foi reconstruído como documento editável. A disposição original "
                               "(colunas, posições exatas) pode mudar — confira o resultado.")
    report.pop("_conf_sum")
    report.pop("_conf_n")
    return report
