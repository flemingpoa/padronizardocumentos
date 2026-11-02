"""Motor de padronização: aplica as regras de um modelo a um documento DOCX.

Princípio central: só a APARÊNCIA muda. O texto dos parágrafos não é reescrito.
As únicas mudanças textuais possíveis são opcionais e explícitas (renumerar questões
e uniformizar rótulos de alternativas), e todas são registradas no relatório.
"""
import copy
import re
from pathlib import Path

from docx.enum.section import WD_ORIENT
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt, RGBColor
from PIL import Image
from docx.text.paragraph import Paragraph

from .analyzer import ALT_RE, QUESTION_RE
from .default_templates import PAPER_SIZES
from .docxutil import (A_NS, T_R, T_RPR, T_T, T_TAB, WP_NS, iter_runs, iter_tables, run_text,
                       table_paragraphs)

ALIGN = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
         "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}
SYMBOL_FONTS = {"symbol", "wingdings", "wingdings 2", "wingdings 3", "webdings", "cambria math",
                "mt extra", "marlett", "segoe ui symbol", "zapfdingbats"}

# nome do estilo do Word usado para cada tipo de parágrafo
STYLE_NAMES = {
    "title": "Title", "heading1": "Heading 1", "heading2": "Heading 2",
    "activity": "Prumo Atividade", "instruction": "Prumo Instruções",
    "question": "Prumo Questão", "alternative": "Prumo Alternativa",
    "body": "Prumo Corpo", "empty": "Prumo Corpo", "list": "Prumo Lista",
    "quote": "Prumo Citação", "caption": "Prumo Legenda", "reference": "Prumo Referência",
    "image": "Prumo Imagem", "equation": "Prumo Equação", "table": "Prumo Tabela",
    "student_info": "Prumo Corpo",
}

PPR_ORDER = ["w:pStyle", "w:keepNext", "w:keepLines", "w:pageBreakBefore", "w:framePr",
             "w:widowControl", "w:numPr", "w:suppressLineNumbers", "w:pBdr", "w:shd", "w:tabs",
             "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct",
             "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd",
             "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents",
             "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment",
             "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr",
             "w:sectPr", "w:pPrChange"]
TBLPR_ORDER = ["w:tblStyle", "w:tblpPr", "w:tblOverlap", "w:bidiVisual", "w:tblStyleRowBandSize",
               "w:tblStyleColBandSize", "w:tblW", "w:jc", "w:tblCellSpacing", "w:tblInd",
               "w:tblBorders", "w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook",
               "w:tblCaption", "w:tblDescription", "w:tblPrChange"]
SECTPR_AFTER_PGNUM = ["w:cols", "w:formProt", "w:vAlign", "w:noEndnote", "w:titlePg",
                      "w:textDirection", "w:bidi", "w:rtlGutter", "w:docGrid",
                      "w:printerSettings", "w:sectPrChange"]


def _insert_ordered(parent, child, order):
    """Insere `child` respeitando a ordem de elementos exigida pelo Word."""
    tag = child.tag
    names = [qn(n) for n in order]
    try:
        pos = names.index(tag)
    except ValueError:
        parent.append(child)
        return child
    successors = set(names[pos + 1:])
    for i, existing in enumerate(parent):
        if existing.tag in successors:
            parent.insert(i, child)
            return child
    parent.append(child)
    return child


def _ppr(p_el):
    ppr = p_el.find(qn("w:pPr"))
    if ppr is None:
        ppr = OxmlElement("w:pPr")
        p_el.insert(0, ppr)
    return ppr


def _hex(color, fallback="000000"):
    c = (color or "").strip().lstrip("#")
    return c.upper() if re.fullmatch(r"[0-9a-fA-F]{6}", c) else fallback


# ----------------------------------------------------------------------------- estilos

def _set_fonts(rpr_owner_font, rpr, name):
    rpr_owner_font.name = name
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        return
    for att in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        rfonts.attrib.pop(qn(att), None)
    for att in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(att), name)


def _get_style(doc, name):
    try:
        return doc.styles[name]
    except KeyError:
        return doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)


def _configure_style(style, cfg, body, base_style=None, next_style=None):
    font_name = cfg.get("font") or body["font"]
    style.hidden = False
    style.quick_style = True
    if base_style is not None:
        style.base_style = base_style
    if next_style is not None:
        style.next_paragraph_style = next_style
    rpr = style.element.get_or_add_rPr()
    _set_fonts(style.font, rpr, font_name)
    style.font.size = Pt(float(cfg.get("size") or body["size"]))
    style.font.color.rgb = RGBColor.from_string(_hex(cfg.get("color") or body["color"]))
    color_el = rpr.find(qn("w:color"))
    if color_el is not None:
        for att in ("w:themeColor", "w:themeShade", "w:themeTint"):
            color_el.attrib.pop(qn(att), None)
    style.font.bold = bool(cfg.get("bold"))
    style.font.italic = bool(cfg.get("italic"))
    style.font.underline = bool(cfg.get("underline"))
    style.font.all_caps = bool(cfg.get("caps"))
    pf = style.paragraph_format
    pf.alignment = ALIGN.get(cfg.get("align") or "left")
    pf.space_before = Pt(float(cfg.get("space_before") or 0))
    pf.space_after = Pt(float(cfg.get("space_after") or 0))
    ls = cfg.get("line_spacing") or body["line_spacing"]
    pf.line_spacing = float(ls)
    pf.left_indent = Cm(float(cfg.get("left_indent") or 0))
    pf.right_indent = Cm(float(cfg.get("right_indent") or 0))
    pf.first_line_indent = Cm(float(cfg.get("first_line_indent") or 0))
    pf.widow_control = True
    # remove bordas/sombreamento de estilos de título herdados de modelos antigos do Word
    ppr = style.element.get_or_add_pPr()
    for tag in ("w:pBdr", "w:contextualSpacing"):
        el = ppr.find(qn(tag))
        if el is not None:
            ppr.remove(el)


def setup_styles(doc, s):
    body = s["body"]
    styles = s["styles"]

    # padrões do documento e estilo Normal: só a família/tamanho/cor da fonte
    st_el = doc.styles.element
    for rfonts in st_el.iter(qn("w:rFonts")):
        has_theme = any(rfonts.get(qn(a)) for a in
                        ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"))
        if has_theme:
            for att in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
                rfonts.attrib.pop(qn(att), None)
            for att in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
                rfonts.set(qn(att), body["font"])
    normal = _get_style(doc, "Normal")
    rpr = normal.element.get_or_add_rPr()
    _set_fonts(normal.font, rpr, body["font"])
    normal.font.size = Pt(float(body["size"]))
    normal.font.color.rgb = RGBColor.from_string(_hex(body["color"]))

    body_cfg = {"font": body["font"], "size": body["size"], "color": body["color"],
                "bold": body["bold"], "italic": body["italic"], "underline": body["underline"],
                "align": body["align"], "space_before": body["space_before"],
                "space_after": body["space_after"], "line_spacing": body["line_spacing"],
                "left_indent": body["left_indent"], "right_indent": body["right_indent"],
                "first_line_indent": body["first_line_indent"]}
    corpo = _get_style(doc, STYLE_NAMES["body"])
    _configure_style(corpo, body_cfg, body, base_style=normal)
    corpo.next_paragraph_style = corpo

    lista = _get_style(doc, STYLE_NAMES["list"])
    _configure_style(lista, dict(body_cfg, first_line_indent=0, space_after=min(
        float(body["space_after"]), 3)), body, base_style=normal)

    for key in ("title", "heading1", "heading2", "activity", "instruction", "question",
                "quote", "caption", "reference"):
        st = _get_style(doc, STYLE_NAMES[key])
        cfg = dict(styles[key])
        _configure_style(st, cfg, body, base_style=normal, next_style=corpo)
        if key in ("title", "heading1", "heading2", "activity"):
            st.paragraph_format.keep_with_next = True

    q = s["questions"]
    alt = _get_style(doc, STYLE_NAMES["alternative"])
    alt_cfg = dict(styles["alternative"])
    hanging = float(q.get("alternative_hanging") or 0)
    alt_cfg["left_indent"] = float(q.get("alternative_indent") or 0) + hanging
    alt_cfg["first_line_indent"] = -hanging
    _configure_style(alt, alt_cfg, body, base_style=normal)
    alt.next_paragraph_style = alt

    img = _get_style(doc, STYLE_NAMES["image"])
    _configure_style(img, dict(body_cfg, align="center" if s["images"]["center"] else "left",
                               first_line_indent=0, left_indent=0, line_spacing=1.0,
                               space_before=6, space_after=6), body, base_style=normal,
                     next_style=corpo)
    eq = _get_style(doc, STYLE_NAMES["equation"])
    _configure_style(eq, dict(body_cfg, align="center", first_line_indent=0, left_indent=0,
                              space_before=6, space_after=6), body, base_style=normal,
                     next_style=corpo)
    tab = _get_style(doc, STYLE_NAMES["table"])
    _configure_style(tab, dict(body_cfg, size=s["tables"]["font_size"], align="left",
                               first_line_indent=0, left_indent=0, right_indent=0,
                               line_spacing=1.0, space_before=0, space_after=0), body,
                     base_style=normal)

    # notas de rodapé, cabeçalho e rodapé seguem a fonte do corpo
    for name, size in (("footnote text", max(8, float(body["size"]) - 2)),
                       ("Header", None), ("Footer", None)):
        try:
            st = doc.styles[name]
        except KeyError:
            continue
        r = st.element.get_or_add_rPr()
        _set_fonts(st.font, r, body["font"])
        if size:
            st.font.size = Pt(size)


# ----------------------------------------------------------------------------- parágrafos

def _clean_paragraph(p_el, keep_layout=False, keep_jc=False):
    ppr = p_el.find(qn("w:pPr"))
    if ppr is not None:
        drop = ["w:contextualSpacing"]
        if not keep_layout:
            drop += ["w:spacing", "w:ind"]
            if not keep_jc:
                drop.append("w:jc")
        for tag in drop:
            for el in ppr.findall(qn(tag)):
                ppr.remove(el)
        mark = ppr.find(qn("w:rPr"))
        if mark is not None:
            for tag in ("w:rFonts", "w:sz", "w:szCs", "w:color"):
                for el in mark.findall(qn(tag)):
                    mark.remove(el)


def _clean_runs(p_el, s, strip_emphasis=False, linked_char_styles=frozenset()):
    body = s["body"]
    for r in iter_runs(p_el):
        rpr = r.find(T_RPR)
        if rpr is None:
            continue
        rf = rpr.find(qn("w:rFonts"))
        if rf is not None:
            fname = (rf.get(qn("w:ascii")) or rf.get(qn("w:hAnsi")) or "").lower()
            if fname not in SYMBOL_FONTS:
                rpr.remove(rf)
        for tag in ("w:sz", "w:szCs"):
            for el in rpr.findall(qn(tag)):
                rpr.remove(el)
        if body.get("standardize_color", True):
            for el in rpr.findall(qn("w:color")):
                rpr.remove(el)
        rs = rpr.find(qn("w:rStyle"))
        if rs is not None and rs.get(qn("w:val")) in linked_char_styles:
            rpr.remove(rs)
        if strip_emphasis:
            for tag in ("w:b", "w:bCs", "w:i", "w:iCs", "w:u"):
                for el in rpr.findall(qn(tag)):
                    rpr.remove(el)
        else:
            # um "negrito desligado" explícito anularia o negrito do estilo de título
            for tag in ("w:b", "w:bCs"):
                for el in rpr.findall(qn(tag)):
                    if el.get(qn("w:val")) in ("0", "false", "off"):
                        rpr.remove(el)


def _simple_run(r):
    """Run que contém apenas propriedades e texto (pode ser dividido com segurança)."""
    for ch in r:
        if ch.tag not in (T_RPR, T_T, T_TAB):
            return False
    return True


def _isolate_prefix(p_el, n_chars):
    """Divide os runs para que os primeiros n_chars fiquem em runs próprios.

    Retorna a lista desses runs, ou None quando não é seguro dividir.
    """
    runs = list(iter_runs(p_el))
    out = []
    pos = 0
    for r in runs:
        if pos >= n_chars:
            break
        t = run_text(r)
        if not t:
            continue
        if pos + len(t) <= n_chars:
            out.append(r)
            pos += len(t)
            continue
        # o limite cai no meio deste run
        cut = n_chars - pos
        ts = r.findall(T_T)
        if not _simple_run(r) or len(ts) != 1 or len(r.findall(T_TAB)):
            return None
        first = copy.deepcopy(r)
        first.find(T_T).text = t[:cut]
        first.find(T_T).set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        ts[0].text = t[cut:]
        ts[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        r.addprevious(first)
        out.append(first)
        pos = n_chars
    return out if pos >= n_chars else None


def _set_run_bold(r):
    rpr = r.find(T_RPR)
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        r.insert(0, rpr)
    if rpr.find(qn("w:b")) is None:
        b = OxmlElement("w:b")
        # w:b deve vir logo após rStyle/rFonts
        anchor = None
        for tag in ("w:rStyle", "w:rFonts"):
            el = rpr.find(qn(tag))
            if el is not None:
                anchor = el
        if anchor is not None:
            anchor.addnext(b)
        else:
            rpr.insert(0, b)


def _replace_prefix(p_el, n_chars, new_text):
    runs = _isolate_prefix(p_el, n_chars)
    if not runs or not all(_simple_run(r) for r in runs):
        return False
    first = runs[0]
    for t in first.findall(T_TAB):
        first.remove(t)
    ts = first.findall(T_T)
    for extra in ts[1:]:
        first.remove(extra)
    ts[0].text = new_text
    ts[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for r in runs[1:]:
        r.getparent().remove(r)
    return True


QUESTION_FORMATS = {"1.": "{n}. ", "1)": "{n}) ", "1 –": "{n} – ", "Questão 1.": "Questão {n}. ",
                    "Questão 1 –": "Questão {n} – ", "QUESTÃO 1": "QUESTÃO {n} – ",
                    "Questão 01": "Questão {nn} – "}
ALT_FORMATS = {"a)": "{l}) ", "A)": "{L}) ", "(a)": "({l}) ", "(A)": "({L}) ", "a.": "{l}. ",
               "A.": "{L}. ", "a –": "{l} – "}


def _relabel(items, s, report):
    num = s["numbering"]
    qfmt = num.get("question_format", "keep")
    afmt = num.get("alternative_format", "keep")
    renumber = bool(num.get("renumber_questions"))
    counter = 0
    for it in items:
        if it["type"] == "question" and it["meta"].get("label"):
            counter += 1
            label = it["meta"]["label"]
            n = it["meta"].get("number")
            if qfmt == "keep" and not renumber:
                continue
            new_n = counter if renumber else int(n)
            if qfmt == "keep":
                new_label = re.sub(r"\d{1,3}", str(new_n).zfill(len(n)) if n.startswith("0")
                                   else str(new_n), label, count=1)
            else:
                new_label = QUESTION_FORMATS[qfmt].format(n=new_n, nn=str(new_n).zfill(2))
            if new_label != label and _replace_prefix(it["el"], len(label), new_label):
                report["rotulos_alterados"].append({"de": label.strip(), "para": new_label.strip()})
                it["meta"]["label"] = new_label
        elif it["type"] == "alternative" and it["meta"].get("letter") and afmt != "keep":
            label = it["meta"]["label"]
            letter = it["meta"]["letter"]
            new_label = ALT_FORMATS[afmt].format(l=letter.lower(), L=letter.upper())
            if new_label != label and _replace_prefix(it["el"], len(label), new_label):
                report["rotulos_alterados"].append({"de": label.strip(), "para": new_label.strip()})
                it["meta"]["label"] = new_label


def _linked_char_styles(doc):
    out = set()
    for st in doc.styles.element.findall(qn("w:style")):
        if st.get(qn("w:type")) == "character" and st.find(qn("w:link")) is not None:
            out.add(st.get(qn("w:styleId")))
    return frozenset(out)


def format_paragraphs(doc, items, s, report):
    body = s["body"]
    styles_cache = {k: _get_style(doc, v) for k, v in STYLE_NAMES.items()}
    linked = _linked_char_styles(doc)
    strip_emph = not body.get("keep_emphasis", True)

    _relabel(items, s, report)

    prev_empty = False
    to_remove = []
    for idx, it in enumerate(items):
        t = it["type"]
        p_el = it["el"]
        if t == "keep":
            _clean_runs(p_el, s, False, linked)
            continue
        if t == "empty":
            has_break = p_el.find(".//" + qn("w:br")) is not None or \
                p_el.find(".//" + qn("w:sectPr")) is not None
            if body.get("collapse_empty") and prev_empty and not has_break:
                to_remove.append(p_el)
                continue
            prev_empty = True
        else:
            prev_empty = False

        keep_layout = t == "student_info"
        keep_jc = False
        if t in ("body", "empty") and body.get("preserve_centered", True) and \
                it.get("jc") in ("center", "right", "end") and len(it["text"]) <= 100:
            keep_jc = True
        _clean_paragraph(p_el, keep_layout=keep_layout, keep_jc=keep_jc)
        _clean_runs(p_el, s, strip_emph, linked)
        _ppr(p_el).style = (styles_cache[t] if t in styles_cache else styles_cache["body"]).style_id

        if t == "question" and s["questions"].get("label_bold") and it["meta"].get("label"):
            label_len = len(it["meta"]["label"].rstrip())
            runs = _isolate_prefix(p_el, label_len)
            if runs:
                for r in runs:
                    _set_run_bold(r)

    for p_el in to_remove:
        p_el.getparent().remove(p_el)
        report["linhas_em_branco_removidas"] += 1

    if s["questions"].get("keep_together"):
        _keep_questions_together(items)

    # parágrafos dentro de tabelas
    for tbl in iter_tables(doc.element.body):
        for p_el in table_paragraphs(tbl):
            _clean_paragraph(p_el, keep_layout=False, keep_jc=True)
            _clean_runs(p_el, s, strip_emph, linked)
            _ppr(p_el).style = styles_cache["table"].style_id


def _set_keep_next(p_el):
    ppr = _ppr(p_el)
    if ppr.find(qn("w:keepNext")) is None:
        _insert_ordered(ppr, OxmlElement("w:keepNext"), PPR_ORDER)


def _keep_questions_together(items):
    """Mantém a questão junto da primeira linha seguinte e as alternativas juntas."""
    n = len(items)
    for i, it in enumerate(items):
        if it["type"] == "question":
            _set_keep_next(it["el"])
        elif it["type"] == "alternative":
            j = i + 1
            while j < n and items[j]["type"] == "empty":
                j += 1
            if j < n and items[j]["type"] == "alternative":
                _set_keep_next(it["el"])


# ----------------------------------------------------------------------------- página

def page_text_width(section):
    w = section.page_width - section.left_margin - section.right_margin
    cols = section._sectPr.find(qn("w:cols"))
    if cols is not None:
        try:
            num = int(cols.get(qn("w:num"), "1"))
        except ValueError:
            num = 1
        if num > 1:
            space = int(cols.get(qn("w:space"), "720")) * 635  # twips -> EMU
            w = (w - space * (num - 1)) // num
    return int(w)


def setup_pages(doc, s):
    pg = s["page"]
    w_cm, h_cm = PAPER_SIZES.get(pg["size"], PAPER_SIZES["A4"])
    landscape = pg.get("orientation") == "landscape"

    def is_land(sec):
        return sec.page_width is not None and sec.page_height is not None and \
            sec.page_width > sec.page_height

    first_land = is_land(doc.sections[0])
    for sec in doc.sections:
        # uma seção com orientação diferente da primeira (ex.: página deitada para uma
        # tabela larga) é intencional: mantém essa diferença
        flipped = is_land(sec) != first_land
        if landscape != flipped:
            sec.orientation = WD_ORIENT.LANDSCAPE
            sec.page_width, sec.page_height = Cm(h_cm), Cm(w_cm)
        else:
            sec.orientation = WD_ORIENT.PORTRAIT
            sec.page_width, sec.page_height = Cm(w_cm), Cm(h_cm)
        sec.top_margin = Cm(float(pg["margin_top"]))
        sec.bottom_margin = Cm(float(pg["margin_bottom"]))
        sec.left_margin = Cm(float(pg["margin_left"]))
        sec.right_margin = Cm(float(pg["margin_right"]))
        sec.header_distance = Cm(float(pg["header_distance"]))
        sec.footer_distance = Cm(float(pg["footer_distance"]))
        sec.gutter = Cm(0)
        _set_columns(sec, int(pg.get("columns") or 1))


def _set_columns(sec, num):
    """Número de colunas do texto (com linha divisória discreta quando houver mais de uma)."""
    sp = sec._sectPr
    for el in sp.findall(qn("w:cols")):
        sp.remove(el)
    cols = OxmlElement("w:cols")
    cols.set(qn("w:num"), str(num))
    cols.set(qn("w:space"), str(int(Cm(0.8)) // 635))
    if num > 1:
        cols.set(qn("w:sep"), "1")
    sp.insert_element_before(cols, *SECTPR_AFTER_PGNUM[1:])


def resize_images(doc, s, report):
    pct = max(10, min(100, int(s["images"].get("max_width") or 100))) / 100
    sec = doc.sections[-1]
    max_w = int(page_text_width(sec) * pct)
    body = doc.element.body
    for container_tag in ("inline", "anchor"):
        for cont in body.iter(f"{{{WP_NS}}}{container_tag}"):
            ext = cont.find(f"{{{WP_NS}}}extent")
            if ext is None:
                continue
            try:
                cx, cy = int(ext.get("cx")), int(ext.get("cy"))
            except (TypeError, ValueError):
                continue
            if cx <= max_w or cx <= 0:
                continue
            ratio = max_w / cx
            ncx, ncy = max_w, int(cy * ratio)
            ext.set("cx", str(ncx))
            ext.set("cy", str(ncy))
            for a_ext in cont.iter(f"{{{A_NS}}}ext"):
                if a_ext.getparent().tag == f"{{{A_NS}}}xfrm" and a_ext.get("cx") == str(cx):
                    a_ext.set("cx", str(ncx))
                    a_ext.set("cy", str(ncy))
            report["imagens_redimensionadas"] += 1


def format_tables(doc, s, report):
    tc = s["tables"]
    body = doc.element.body
    for tbl_el in iter_tables(body):
        tblPr = tbl_el.find(qn("w:tblPr"))
        if tblPr is None:
            tblPr = OxmlElement("w:tblPr")
            tbl_el.insert(0, tblPr)
        if tc.get("center"):
            for tag in ("w:jc", "w:tblInd"):
                for el in tblPr.findall(qn(tag)):
                    tblPr.remove(el)
            jc = OxmlElement("w:jc")
            jc.set(qn("w:val"), "center")
            _insert_ordered(tblPr, jc, TBLPR_ORDER)
        if tc.get("full_width"):
            for el in tblPr.findall(qn("w:tblW")):
                tblPr.remove(el)
            tw = OxmlElement("w:tblW")
            tw.set(qn("w:w"), "5000")
            tw.set(qn("w:type"), "pct")
            _insert_ordered(tblPr, tw, TBLPR_ORDER)
        if tc.get("borders") == "all":
            for el in tblPr.findall(qn("w:tblBorders")):
                tblPr.remove(el)
            borders = OxmlElement("w:tblBorders")
            for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
                b = OxmlElement(f"w:{side}")
                b.set(qn("w:val"), "single")
                b.set(qn("w:sz"), "4")
                b.set(qn("w:space"), "0")
                b.set(qn("w:color"), "000000")
                borders.append(b)
            _insert_ordered(tblPr, borders, TBLPR_ORDER)
            for tcb in tbl_el.iter(qn("w:tcBorders")):
                tcb.getparent().remove(tcb)
        rows = tbl_el.findall(qn("w:tr"))
        if rows and len(rows) > 1:
            first = rows[0]
            if tc.get("repeat_header"):
                trPr = first.find(qn("w:trPr"))
                if trPr is None:
                    trPr = OxmlElement("w:trPr")
                    tblPrEx = first.find(qn("w:tblPrEx"))
                    if tblPrEx is not None:
                        tblPrEx.addnext(trPr)
                    else:
                        first.insert(0, trPr)
                if trPr.find(qn("w:tblHeader")) is None:
                    th = OxmlElement("w:tblHeader")
                    after = [qn(t) for t in ("w:tblCellSpacing", "w:jc", "w:hidden", "w:ins",
                                             "w:del", "w:trPrChange")]
                    pos = next((i for i, e in enumerate(trPr) if e.tag in after), None)
                    if pos is None:
                        trPr.append(th)
                    else:
                        trPr.insert(pos, th)
            if tc.get("header_bold"):
                for p_el in first.iter(qn("w:p")):
                    for r in iter_runs(p_el):
                        _set_run_bold(r)
        report["tabelas_formatadas"] += 1


# ----------------------------------------------------------------------------- cabeçalho/rodapé

def _clear_story(story_el):
    for ch in list(story_el):
        if ch.tag in (qn("w:p"), qn("w:tbl"), qn("w:sdt")):
            story_el.remove(ch)


def _new_par(container, text="", size=10, bold=False, align="center", font=None,
             space_after=0):
    p = container.add_paragraph()
    pf = p.paragraph_format
    pf.alignment = ALIGN.get(align, WD_ALIGN_PARAGRAPH.CENTER)
    pf.space_before = Pt(0)
    pf.space_after = Pt(space_after)
    pf.first_line_indent = Cm(0)
    pf.left_indent = Cm(0)
    pf.line_spacing = 1.0
    if text:
        r = p.add_run(text)
        r.font.size = Pt(size)
        r.font.bold = bold
        if font:
            r.font.name = font
    return p


def _add_field(paragraph, instr, size, font=None):
    def mk_run():
        r = paragraph.add_run()
        r.font.size = Pt(size)
        if font:
            r.font.name = font
        return r
    r1 = mk_run()
    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), "begin")
    r1._r.append(fc)
    r2 = mk_run()
    it = OxmlElement("w:instrText")
    it.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    it.text = f" {instr} "
    r2._r.append(it)
    r3 = mk_run()
    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), "separate")
    r3._r.append(fc)
    r4 = mk_run()
    r4.text = "1"
    r5 = mk_run()
    fc = OxmlElement("w:fldChar")
    fc.set(qn("w:fldCharType"), "end")
    r5._r.append(fc)


def _page_number_paragraph(container, fmt, size, align, font):
    p = _new_par(container, align=align)
    for part in re.split(r"(\{n\}|\{t\})", fmt or "{n}"):
        if part == "{n}":
            _add_field(p, "PAGE", size, font)
        elif part == "{t}":
            _add_field(p, "NUMPAGES", size, font)
        elif part:
            r = p.add_run(part)
            r.font.size = Pt(size)
            if font:
                r.font.name = font
    return p


def _set_cell_borders(cell, show=True):
    tcPr = cell._tc.get_or_add_tcPr()
    for el in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(el)
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "single" if show else "nil")
        if show:
            b.set(qn("w:sz"), "4")
            b.set(qn("w:space"), "0")
            b.set(qn("w:color"), "808080")
        borders.append(b)
    # tcBorders vem depois de tcW/gridSpan/vMerge
    after = [qn(t) for t in ("w:shd", "w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText",
                             "w:vAlign", "w:hideMark")]
    pos = next((i for i, e in enumerate(tcPr) if e.tag in after), None)
    if pos is None:
        tcPr.append(borders)
    else:
        tcPr.insert(pos, borders)


def _set_grid(table, widths):
    """Define a largura das colunas na grade da tabela (o LibreOffice usa a grade)."""
    for col, w in zip(table._tbl.tblGrid.findall(qn("w:gridCol")), widths):
        col.set(qn("w:w"), str(int(w) // 635))  # EMU -> twips


def _table_no_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "nil")
        borders.append(b)
    _insert_ordered(tblPr, borders, TBLPR_ORDER)


def _cell_text(cell, text, size, bold_label=True, font=None):
    p = cell.paragraphs[0]
    pf = p.paragraph_format
    pf.space_before = Pt(2)
    pf.space_after = Pt(2)
    pf.first_line_indent = Cm(0)
    pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
    pf.line_spacing = 1.0
    label, _, rest = text.partition(":")
    r = p.add_run(label + (":" if _ else ""))
    r.font.size = Pt(size)
    r.font.bold = bold_label
    if font:
        r.font.name = font
    if rest:
        r2 = p.add_run(rest)
        r2.font.size = Pt(size)
        if font:
            r2.font.name = font


def _student_box(container, hc, width, font):
    f = hc.get("student_fields") or {}
    size = float(hc.get("font_size") or 10)
    row1 = []
    if f.get("name", True):
        row1.append(("Nome:", 0.78 if f.get("number") else 1.0))
    if f.get("number"):
        row1.append(("Nº:", 0.22 if f.get("name", True) else 1.0))
    row2 = []
    if f.get("class"):
        row2.append("Turma:")
    if f.get("date"):
        row2.append("Data:       /       /")
    if f.get("grade"):
        row2.append("Nota:")
    rows = [r for r in (row1, row2) if r]
    if not rows:
        return
    _new_par(container, size=4, space_after=0)  # pequeno respiro entre o cabeçalho e o quadro
    for row in rows:
        cols = len(row)
        t = container.add_table(rows=1, cols=cols, width=width)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        widths = []
        for i, cell in enumerate(t.rows[0].cells):
            entry = row[i]
            if isinstance(entry, tuple):
                text, frac = entry
                cell.width = int(width * frac)
            else:
                text = entry
                cell.width = int(width / cols)
            widths.append(cell.width)
            _set_cell_borders(cell, True)
            _cell_text(cell, text, size, True, font)
        _set_grid(t, widths)


def _header_lines(hc):
    lines = []
    second = []
    if hc.get("discipline"):
        second.append(f"Disciplina: {hc['discipline']}")
    if hc.get("teacher"):
        second.append(f"Professor(a): {hc['teacher']}")
    third = []
    if hc.get("class_name"):
        third.append(f"Turma: {hc['class_name']}")
    if hc.get("date"):
        third.append(f"Data: {hc['date']}")
    if second:
        lines.append("   •   ".join(second))
    if third:
        lines.append("   •   ".join(third))
    if hc.get("extra"):
        lines.append(hc["extra"])
    return lines


def _bottom_border(paragraph):
    ppr = paragraph._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    b = OxmlElement("w:bottom")
    b.set(qn("w:val"), "single")
    b.set(qn("w:sz"), "6")
    b.set(qn("w:space"), "4")
    b.set(qn("w:color"), "808080")
    bdr.append(b)
    _insert_ordered(ppr, bdr, PPR_ORDER)


def _fill_header(story, hc, s, width, logo_path, include_student, compact):
    font = s["body"]["font"]
    size = float(hc.get("font_size") or 10)
    align = hc.get("align") or "center"
    inst = (hc.get("institution") or "").strip()
    lines = [] if compact else _header_lines(hc)
    last = None
    has_logo = bool(logo_path and Path(logo_path).exists()) and not compact
    if compact:
        bits = [b for b in (inst, hc.get("discipline")) if b]
        if bits:
            last = _new_par(story, "   •   ".join(bits), size=max(7, size - 1), align=align,
                            font=font)
    elif has_logo:
        logo_h = Cm(float(hc.get("logo_height") or 1.6))
        t = story.add_table(rows=1, cols=2, width=width)
        t.autofit = False
        _table_no_borders(t)
        # a coluna do logotipo acompanha a proporção da imagem (logos horizontais são largos);
        # se ficar larga demais, a altura é reduzida para caber em 40% da linha
        try:
            with Image.open(logo_path) as im:
                ratio = im.width / max(1, im.height)
        except Exception:
            ratio = 1.0
        if logo_h * ratio > width * 0.4:
            logo_h = int(width * 0.4 / ratio)
        logo_w = int(logo_h * ratio) + int(Cm(0.4))
        c0, c1 = t.rows[0].cells
        c0.width = logo_w
        c1.width = int(width - logo_w)
        c0.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        c1.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        _set_grid(t, [logo_w, int(width - logo_w)])
        p0 = c0.paragraphs[0]
        p0.paragraph_format.first_line_indent = Cm(0)
        p0.paragraph_format.space_after = Pt(0)
        p0.add_run().add_picture(str(logo_path), height=logo_h)
        first = True
        if inst:
            p = c1.paragraphs[0]
            p.paragraph_format.alignment = ALIGN.get(align)
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.line_spacing = 1.0
            r = p.add_run(inst)
            r.font.size = Pt(size + 2)
            r.font.bold = bool(hc.get("bold_institution", True))
            r.font.name = font
            first = False
        for line in lines:
            if first:
                p = c1.paragraphs[0]
                p.paragraph_format.alignment = ALIGN.get(align)
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.line_spacing = 1.0
                r = p.add_run(line)
                r.font.size = Pt(size)
                r.font.name = font
                first = False
            else:
                _new_par(c1, line, size=size, align=align, font=font)
        last = _new_par(story, size=4)
    else:
        if inst:
            last = _new_par(story, inst, size=size + 2, bold=bool(hc.get("bold_institution", True)),
                            align=align, font=font, space_after=1)
        for line in lines:
            last = _new_par(story, line, size=size, align=align, font=font)
    if last is not None and hc.get("border_bottom") and not include_student and not compact:
        _bottom_border(last)
    if include_student:
        _student_box(story, hc, width, font)
        _new_par(story, size=4)


# ----------------------------------------------------------------------------- cabeçalho Fleming

ASSETS = Path(__file__).resolve().parent / "assets"
VERDE_ESCURO = "0F3A2C"
VERDE = "1C6048"
VERDE_CLARO = "CFE4D9"
VERDE_50 = "F3F8F5"
VERDE_MEDIO = "237657"
CINZA_VERDE = "4A5A52"
MENTA = "1CE692"


def _shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    for el in tcPr.findall(qn("w:shd")):
        tcPr.remove(el)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    after = [qn(t) for t in ("w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText", "w:vAlign",
                             "w:hideMark")]
    pos = next((i for i, e in enumerate(tcPr) if e.tag in after), None)
    if pos is None:
        tcPr.append(shd)
    else:
        tcPr.insert(pos, shd)


def _cell_margins(cell, top, bottom, left, right):
    """Margens internas da célula, em twips (1 cm = 567)."""
    tcPr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for side, v in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(v))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    after = [qn(t) for t in ("w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark")]
    pos = next((i for i, e in enumerate(tcPr) if e.tag in after), None)
    if pos is None:
        tcPr.append(mar)
    else:
        tcPr.insert(pos, mar)


def _table_borders(table, spec):
    """spec: {lado: None (sem borda) ou (espessura em 1/8 pt, cor)}"""
    tblPr = table._tbl.tblPr
    for el in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(el)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{side}")
        val = spec.get(side)
        if val:
            b.set(qn("w:val"), "single")
            b.set(qn("w:sz"), str(val[0]))
            b.set(qn("w:space"), "0")
            b.set(qn("w:color"), val[1])
        else:
            b.set(qn("w:val"), "nil")
        borders.append(b)
    _insert_ordered(tblPr, borders, TBLPR_ORDER)


def _fpar(container, align="left", first=False, after=0):
    p = container.paragraphs[0] if first else container.add_paragraph()
    pf = p.paragraph_format
    pf.alignment = ALIGN.get(align)
    pf.space_before = Pt(0)
    pf.space_after = Pt(after)
    pf.first_line_indent = Cm(0)
    pf.left_indent = Cm(0)
    pf.line_spacing = 1.0
    return p


def _frun(p, text, size, color, bold=False, font="Arial"):
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.name = font
    r.font.color.rgb = RGBColor.from_string(color)
    return r


def _fleming_header(story, fl, width, font, include_student, compact):
    """Cabeçalho institucional: faixa verde-escura com o logo do Fleming, título do
    material, dados da turma e um filete verde-menta; abaixo, o quadro do estudante."""
    font = font or "Arial"
    if compact:
        # demais páginas: linha discreta com o logo pequeno e o resumo do material
        t = story.add_table(rows=1, cols=2, width=width)
        t.autofit = False
        _table_borders(t, {"bottom": (12, MENTA)})
        lw = int(Cm(3.2))
        c0, c1 = t.rows[0].cells
        c0.width, c1.width = lw, width - lw
        _set_grid(t, [lw, width - lw])
        for c in (c0, c1):
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            _cell_margins(c, 0, 60, 0, 0)
        logo = ASSETS / "logo-fleming.png"
        if logo.exists():
            _fpar(c0, first=True).add_run().add_picture(str(logo), height=Cm(0.6))
        _frun(_fpar(c1, "right", first=True), fl.get("resumo", ""), 8.5, VERDE, True, font)
        _fpar(story, after=4)
        return

    # Versão econômica para impressão: fundo branco (sem área preenchida), logo verde,
    # textos em verde e cinza-esverdeado e só um filete verde-menta como destaque.
    t = story.add_table(rows=1, cols=2, width=width)
    t.autofit = False
    _table_borders(t, {"bottom": (18, MENTA)})
    lw = int(Cm(5.0))
    c0, c1 = t.rows[0].cells
    c0.width, c1.width = lw, width - lw
    _set_grid(t, [lw, width - lw])
    for c in (c0, c1):
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    _cell_margins(c0, 60, 200, 0, 60)
    _cell_margins(c1, 60, 200, 60, 0)
    logo = ASSETS / "logo-fleming.png"
    if logo.exists():
        _fpar(c0, first=True).add_run().add_picture(str(logo), height=Cm(1.15))
    _frun(_fpar(c1, "right", first=True, after=3), fl.get("rotulo", ""), 7, VERDE_MEDIO, True, font)
    _frun(_fpar(c1, "right", after=5), fl.get("titulo", ""), 15, VERDE_ESCURO, True, font)
    for line in fl.get("linhas", []):
        _frun(_fpar(c1, "right", after=3), line, 9, CINZA_VERDE, False, font)

    if include_student:
        rows = fl.get("campos", [])
        if rows:
            _fpar(story, after=0).add_run().font.size = Pt(10)
            # uma única tabela: a grade reúne as divisões de todas as linhas e cada campo
            # ocupa (mescla) as colunas correspondentes
            cuts = sorted({round(sum(f for _, f in row[:i + 1]), 4)
                           for row in rows for i in range(len(row))} | {0.0, 1.0})
            cols = [b - a for a, b in zip(cuts, cuts[1:]) if b - a > 0.001]
            cuts = [0.0]
            for c in cols:
                cuts.append(round(cuts[-1] + c, 4))
            rt = story.add_table(rows=len(rows), cols=len(cols), width=width)
            rt.autofit = False
            _table_borders(rt, {s: (6, VERDE_CLARO) for s in
                                ("top", "left", "bottom", "right", "insideH", "insideV")})
            col_w = [int(width * c) for c in cols]
            _set_grid(rt, col_w)
            for ri, row in enumerate(rows):
                pos = 0.0
                for label, frac in row:
                    start = min(range(len(cuts)), key=lambda i: abs(cuts[i] - pos))
                    pos = round(pos + frac, 4)
                    end = min(range(len(cuts)), key=lambda i: abs(cuts[i] - pos)) - 1
                    cell = rt.cell(ri, start)
                    if end > start:
                        cell = cell.merge(rt.cell(ri, end))
                    cell.width = sum(col_w[start:end + 1])
                    _cell_margins(cell, 110, 110, 120, 120)
                    _frun(_fpar(cell, first=True), f"{label}:", 9, VERDE, True, font)
    _fpar(story, after=10).add_run().font.size = Pt(6)


def setup_header_footer(doc, s, logo_path, report):
    hc = s["header"]
    fc = s["footer"]
    num = s["numbering"]
    font = s["body"]["font"]
    sections = doc.sections
    first = sections[0]
    # cabeçalho e rodapé ocupam a largura toda, mesmo com o texto em colunas
    width = int(first.page_width - first.left_margin - first.right_margin)

    # Guarda o texto original para informar o que foi substituído
    def story_text(story):
        return " ".join("".join(t.text or "" for t in p.iter(qn("w:t")))
                        for p in story._element.iter(qn("w:p"))).strip()

    replace_header = hc.get("mode") in ("replace", "remove")
    replace_footer = fc.get("mode") in ("replace", "remove")
    for i, sec in enumerate(sections):
        stories = []
        if replace_header:
            stories += [sec.header, sec.first_page_header, sec.even_page_header]
        if replace_footer:
            stories += [sec.footer, sec.first_page_footer, sec.even_page_footer]
        for st in stories:
            if st.is_linked_to_previous and i > 0:
                continue
            if not st.is_linked_to_previous:
                txt = story_text(st)
                if txt and txt not in report["cabecalhos_substituidos"]:
                    report["cabecalhos_substituidos"].append(txt[:200])
        if i > 0:
            # as demais seções herdam o cabeçalho/rodapé da primeira
            if replace_header:
                sec.header.is_linked_to_previous = True
                sec.first_page_header.is_linked_to_previous = True
                sec.even_page_header.is_linked_to_previous = True
            if replace_footer:
                sec.footer.is_linked_to_previous = True
                sec.first_page_footer.is_linked_to_previous = True
                sec.even_page_footer.is_linked_to_previous = True

    # páginas pares/ímpares diferentes não são usadas no padrão
    settings_el = doc.settings.element
    eo = settings_el.find(qn("w:evenAndOddHeaders"))
    if eo is not None and (replace_header and replace_footer):
        settings_el.remove(eo)

    student = hc.get("mode") == "replace" and bool(hc.get("student_field"))
    first_only = student and bool(hc.get("first_page_only", True))
    if replace_header or replace_footer:
        first.different_first_page_header_footer = first_only

    page_in_header = num.get("page_numbers") and num.get("page_position") == "header"
    page_in_footer = num.get("page_numbers") and num.get("page_position") != "header"
    nsize = float(fc.get("font_size") or 9)

    if replace_header:
        targets = [(first.header, False)]
        if first_only:
            targets.append((first.first_page_header, True))
        for story, is_first in targets:
            story.is_linked_to_previous = False
            _clear_story(story._element)
            if hc.get("mode") == "replace":
                include_student = student and (is_first or not first_only)
                compact = first_only and not is_first
                if page_in_header:
                    _page_number_paragraph(story, num.get("page_format"), nsize,
                                           num.get("page_align", "right"), font)
                if hc.get("style") == "fleming" and hc.get("fleming"):
                    _fleming_header(story, hc["fleming"], width, font, include_student, compact)
                else:
                    _fill_header(story, hc, s, width, logo_path, include_student, compact)
            if not len(story._element):
                _new_par(story, size=2)
    elif page_in_header:
        story = first.header
        story.is_linked_to_previous = False
        _page_number_paragraph(story, num.get("page_format"), nsize,
                               num.get("page_align", "right"), font)

    if replace_footer:
        targets = [first.footer] + ([first.first_page_footer] if first_only else [])
        for story in targets:
            story.is_linked_to_previous = False
            _clear_story(story._element)
            if fc.get("mode") == "replace":
                if fc.get("text"):
                    _new_par(story, fc["text"], size=nsize, align=fc.get("align", "center"),
                             font=font)
                if page_in_footer:
                    _page_number_paragraph(story, num.get("page_format"), nsize,
                                           num.get("page_align", "center"), font)
            if not len(story._element):
                _new_par(story, size=2)
    elif page_in_footer:
        story = first.footer
        story.is_linked_to_previous = False
        _page_number_paragraph(story, num.get("page_format"), nsize,
                               num.get("page_align", "center"), font)

    start = int(num.get("page_start") or 1)
    if start != 1:
        sp = first._sectPr
        for el in sp.findall(qn("w:pgNumType")):
            sp.remove(el)
        pn = OxmlElement("w:pgNumType")
        pn.set(qn("w:start"), str(start))
        sp.insert_element_before(pn, *SECTPR_AFTER_PGNUM)


# ----------------------------------------------------------------------------- principal

def new_report():
    return {"rotulos_alterados": [], "cabecalhos_substituidos": [], "imagens_redimensionadas": 0,
            "tabelas_formatadas": 0, "linhas_em_branco_removidas": 0}


def apply(doc, items, s, logo_path=None):
    """Aplica o modelo `s` ao documento já analisado. Retorna um relatório das ações."""
    report = new_report()
    setup_pages(doc, s)
    setup_styles(doc, s)
    format_paragraphs(doc, items, s, report)
    format_tables(doc, s, report)
    resize_images(doc, s, report)
    setup_header_footer(doc, s, logo_path, report)
    if s.get("answer_sheet"):
        report["palavras_grade"] = add_answer_sheet(doc, s["answer_sheet"], s["body"]["font"])
    return report


def _cell_border(cell, color, sz=6):
    tcPr = cell._tc.get_or_add_tcPr()
    for el in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(el)
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        b = OxmlElement(f"w:{side}")
        if color:
            b.set(qn("w:val"), "single")
            b.set(qn("w:sz"), str(sz))
            b.set(qn("w:space"), "0")
            b.set(qn("w:color"), color)
        else:
            b.set(qn("w:val"), "nil")
        borders.append(b)
    after = [qn(t) for t in ("w:shd", "w:noWrap", "w:tcMar", "w:textDirection", "w:tcFitText",
                             "w:vAlign", "w:hideMark")]
    pos = next((i for i, e in enumerate(tcPr) if e.tag in after), None)
    if pos is None:
        tcPr.append(borders)
    else:
        tcPr.insert(pos, borders)


def add_answer_sheet(doc, cfg, font):
    """Acrescenta, numa última página de coluna única, a grade de respostas da prova.

    Retorna quantas palavras foram acrescentadas (a conferência de integridade as desconta,
    pois não fazem parte do conteúdo original)."""
    from .docxutil import body_text_words

    font = font or "Arial"
    n = int(cfg.get("questoes") or 20)
    letras = list(cfg.get("alternativas") or "ABCDE")
    body = doc.element.body
    final = body.find(qn("w:sectPr"))
    n_before = len(body)  # o sectPr final é sempre o último filho; o novo conteúdo entra antes dele

    # quebra de seção: o conteúdo da prova termina na seção atual (com suas colunas) e a
    # grade começa em página nova, de coluna única, com o mesmo cabeçalho
    brk = OxmlElement("w:p")
    ppr = OxmlElement("w:pPr")
    ppr.append(copy.deepcopy(final))
    brk.append(ppr)
    final.addprevious(brk)
    for el in final.findall(qn("w:type")):
        final.remove(el)
    t_el = OxmlElement("w:type")
    t_el.set(qn("w:val"), "nextPage")
    final.insert_element_before(t_el, "w:pgSz", "w:pgMar", "w:paperSrc", "w:pgBorders",
                                "w:lnNumType", "w:pgNumType", *SECTPR_AFTER_PGNUM)
    sec = doc.sections[-1]
    _set_columns(sec, 1)
    width = int(sec.page_width - sec.left_margin - sec.right_margin)

    _frun(_fpar(doc, "center", after=4), "GRADE DE RESPOSTAS", 16, VERDE_ESCURO, True, font)
    _frun(_fpar(doc, "justify", after=12),
          "Marque apenas uma alternativa por questão, preenchendo completamente o quadro com caneta "
          "azul ou preta. Questões rasuradas ou com mais de uma marcação serão anuladas.",
          10, "4A5A52", False, font)

    blocos = 2
    por_bloco = -(-n // blocos)
    ncols_bloco = 1 + len(letras)
    q_w, l_w, gap_w = int(Cm(1.8)), int(Cm(1.3)), int(Cm(1.2))
    bloco_w = q_w + l_w * len(letras)
    if bloco_w * 2 + gap_w > width:  # muitas alternativas: estreita as colunas
        l_w = int((width - gap_w) / 2 - q_w) // len(letras)
    widths = ([q_w] + [l_w] * len(letras)) + [gap_w] + ([q_w] + [l_w] * len(letras))
    t = doc.add_table(rows=por_bloco + 1, cols=len(widths))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    _table_borders(t, {})
    _set_grid(t, widths)
    for ri, row in enumerate(t.rows):
        row.height = Cm(0.95 if ri else 0.85)
        for ci, cell in enumerate(row.cells):
            cell.width = widths[ci]
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            gap = ci == ncols_bloco
            if gap:
                _cell_border(cell, None)
                continue
            bloco = 0 if ci < ncols_bloco else 1
            pos = ci - bloco * (ncols_bloco + 1)
            p = _fpar(cell, "center", first=True)
            if ri == 0:
                # sem preenchimento, para economizar tinta: só texto e contorno
                _cell_border(cell, MENTA, 12)
                _frun(p, "Questão" if pos == 0 else letras[pos - 1], 10, VERDE_ESCURO, True, font)
                continue
            q = bloco * por_bloco + ri
            if q > n:
                _cell_border(cell, None)
                continue
            _cell_border(cell, VERDE_CLARO, 8)
            if pos == 0:
                _frun(p, f"{q:02d}", 11, VERDE_ESCURO, True, font)
            else:
                _frun(p, letras[pos - 1], 10, "9AB5A6", False, font)
    _frun(_fpar(doc, "center", after=0), "", 4, VERDE_ESCURO)
    _frun(_fpar(doc, "center", after=0),
          "Somente as respostas marcadas nesta grade serão consideradas na correção.",
          9, "4A5A52", False, font)

    added = list(body)[n_before - 1:len(body) - 1]
    return sum(len(body_text_words(e)) for e in added)
