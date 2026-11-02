"""Desenha o documento já padronizado como páginas A4 em HTML.

Usado na versão do portal que roda no navegador (GitHub Pages): o mesmo HTML serve de
prévia na tela e é impresso pelo navegador como PDF ("Salvar como PDF"). Cabeçalho do
Fleming, colunas, numeração de páginas e grade de respostas seguem as configurações do
perfil; o conteúdo vem do DOCX gerado pelo motor (texto, listas, tabelas, imagens e
equações).
"""
import base64
import html
import json
import re
from pathlib import Path

from docx.oxml.ns import qn

from .docxutil import A_NS, M_NS, WP_NS
from .formatter import STYLE_NAMES, ASSETS

R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
V_NS = "urn:schemas-microsoft-com:vml"
WPS_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
M = f"{{{M_NS}}}"

LINHA_SIMPLES = 1.15  # altura de linha "simples" do Word para Arial
ALIGN = {"left": "left", "center": "center", "right": "right", "justify": "justify",
         "both": "justify", "start": "left", "end": "right", "distribute": "justify"}


def esc(t):
    return html.escape(t or "", quote=False)


def _local(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _twips_cm(v):
    try:
        return int(v) / 567.0
    except (TypeError, ValueError):
        return 0.0


# ----------------------------------------------------------------------------- equações

_TOKEN = re.compile(r"(\d+(?:[.,]\d+)*)|([A-Za-zÀ-ÿΑ-Ωα-ω]+)|(\s+)|(.)")


def _mtext(text, normal=False):
    out = []
    for num, word, space, other in _TOKEN.findall(text):
        if num:
            out.append(f"<mn>{esc(num)}</mn>")
        elif word:
            attr = ' mathvariant="normal"' if normal and len(word) == 1 else ""
            out.append(f"<mi{attr}>{esc(word)}</mi>")
        elif space:
            out.append('<mspace width="0.25em"/>')
        elif other:
            out.append(f"<mo>{esc(other)}</mo>")
    return "".join(out)


def _mval(el, tag, attr="val", default=None):
    pr = el.find(f"{M}{tag}")
    if pr is None:
        return default
    return pr.get(f"{M}{attr}", default)


def _mrow(el):
    if el is None:
        return "<mrow></mrow>"
    return "<mrow>" + "".join(_omml(ch) for ch in el) + "</mrow>"


def _omml(el):
    """Converte um elemento OMML (equação do Word) em MathML."""
    t = _local(el.tag)
    if el.tag.startswith(W) or t.endswith("Pr"):
        return ""
    if t == "r":
        text = "".join(x.text or "" for x in el.iter(f"{M}t"))
        rpr = el.find(f"{M}rPr")
        normal = rpr is not None and (rpr.find(f"{M}nor") is not None or _mval(rpr, "sty") == "p")
        return _mtext(text, normal)
    if t == "f":
        return f"<mfrac>{_mrow(el.find(M + 'num'))}{_mrow(el.find(M + 'den'))}</mfrac>"
    if t == "rad":
        pr = el.find(f"{M}radPr")
        hide = pr is not None and _mval(pr, "degHide") in ("1", "on", "true")
        deg = el.find(f"{M}deg")
        if hide or deg is None or not len(deg):
            return f"<msqrt>{_mrow(el.find(M + 'e'))}</msqrt>"
        return f"<mroot>{_mrow(el.find(M + 'e'))}{_mrow(deg)}</mroot>"
    if t == "sSup":
        return f"<msup>{_mrow(el.find(M + 'e'))}{_mrow(el.find(M + 'sup'))}</msup>"
    if t == "sSub":
        return f"<msub>{_mrow(el.find(M + 'e'))}{_mrow(el.find(M + 'sub'))}</msub>"
    if t == "sSubSup":
        return (f"<msubsup>{_mrow(el.find(M + 'e'))}{_mrow(el.find(M + 'sub'))}"
                f"{_mrow(el.find(M + 'sup'))}</msubsup>")
    if t == "sPre":
        return (f"<mmultiscripts>{_mrow(el.find(M + 'e'))}<mprescripts/>"
                f"{_mrow(el.find(M + 'sub'))}{_mrow(el.find(M + 'sup'))}</mmultiscripts>")
    if t == "d":
        pr = el.find(f"{M}dPr")
        beg = _mval(pr, "begChr", default="(") if pr is not None else "("
        end = _mval(pr, "endChr", default=")") if pr is not None else ")"
        sep = _mval(pr, "sepChr", default="|") if pr is not None else "|"
        parts = [_mrow(e) for e in el.findall(f"{M}e")]
        mid = f"<mo>{esc(sep)}</mo>".join(parts)
        return f"<mrow><mo>{esc(beg)}</mo>{mid}<mo>{esc(end)}</mo></mrow>"
    if t == "nary":
        pr = el.find(f"{M}naryPr")
        chr_ = (_mval(pr, "chr") if pr is not None else None) or "∫"
        und = pr is not None and _mval(pr, "limLoc") == "undOvr"
        sub, sup = el.find(f"{M}sub"), el.find(f"{M}sup")
        op = f"<mo>{esc(chr_)}</mo>"
        tag = "munderover" if und else "msubsup"
        return f"<mrow><{tag}>{op}{_mrow(sub)}{_mrow(sup)}</{tag}>{_mrow(el.find(M + 'e'))}</mrow>"
    if t == "func":
        return f"<mrow>{_mrow(el.find(M + 'fName'))}<mo>&#x2061;</mo>{_mrow(el.find(M + 'e'))}</mrow>"
    if t == "acc":
        pr = el.find(f"{M}accPr")
        chr_ = (_mval(pr, "chr") if pr is not None else None) or "̂"
        return f'<mover accent="true">{_mrow(el.find(M + "e"))}<mo>{esc(chr_)}</mo></mover>'
    if t == "bar":
        pr = el.find(f"{M}barPr")
        bottom = pr is not None and _mval(pr, "pos") == "bot"
        tag = "munder" if bottom else "mover"
        return f'<{tag} accent="true">{_mrow(el.find(M + "e"))}<mo>¯</mo></{tag}>'
    if t == "limLow":
        return f"<munder>{_mrow(el.find(M + 'e'))}{_mrow(el.find(M + 'lim'))}</munder>"
    if t == "limUpp":
        return f"<mover>{_mrow(el.find(M + 'e'))}{_mrow(el.find(M + 'lim'))}</mover>"
    if t == "groupChr":
        pr = el.find(f"{M}groupChrPr")
        chr_ = (_mval(pr, "chr") if pr is not None else None) or "⏟"
        return f"<munder>{_mrow(el.find(M + 'e'))}<mo>{esc(chr_)}</mo></munder>"
    if t == "m":
        rows = "".join("<mtr>" + "".join(f"<mtd>{_mrow(e)}</mtd>" for e in mr.findall(f"{M}e")) + "</mtr>"
                       for mr in el.findall(f"{M}mr"))
        return f"<mtable>{rows}</mtable>"
    if t == "eqArr":
        rows = "".join(f"<mtr><mtd>{_mrow(e)}</mtd></mtr>" for e in el.findall(f"{M}e"))
        return f'<mtable columnalign="left">{rows}</mtable>'
    # e, num, den, sub, sup, deg, fName, lim, box, borderBox, phant e outros contêineres
    return "".join(_omml(ch) for ch in el)


def math_html(el):
    if _local(el.tag) == "oMathPara":
        return "".join(f'<math display="block">{_omml(m)}</math>' for m in el.findall(f"{M}oMath"))
    return f"<math>{_omml(el)}</math>"


# ----------------------------------------------------------------------------- documento

class Renderer:
    def __init__(self, doc, s):
        self.doc = doc
        self.s = s
        self.part = doc.part
        styles_el = doc.styles.element
        self.style_by_id = {st.get(qn("w:styleId")): st for st in styles_el.findall(qn("w:style"))}
        name_to_key = {}
        for key, name in STYLE_NAMES.items():
            try:
                name_to_key[doc.styles[name].style_id] = key
            except KeyError:
                pass
        self.style_key = name_to_key
        self.counters = {}
        self.numbering = self._load_numbering()
        self.avisos = set()

    # -- numeração automática do Word (listas numeradas)
    def _load_numbering(self):
        try:
            root = self.part.numbering_part.element
        except Exception:
            return {}
        abstract = {}
        for an in root.findall(qn("w:abstractNum")):
            lv = {}
            for lvl in an.findall(qn("w:lvl")):
                fmt = lvl.find(qn("w:numFmt"))
                txt = lvl.find(qn("w:lvlText"))
                start = lvl.find(qn("w:start"))
                ind = lvl.find(f"{qn('w:pPr')}/{qn('w:ind')}")
                lv[lvl.get(qn("w:ilvl"))] = {
                    "fmt": fmt.get(qn("w:val")) if fmt is not None else "decimal",
                    "text": txt.get(qn("w:val")) if txt is not None else "%1.",
                    "start": int(start.get(qn("w:val"))) if start is not None else 1,
                    "left": _twips_cm(ind.get(qn("w:left")) or ind.get(qn("w:start"))) if ind is not None else 0,
                    "hanging": _twips_cm(ind.get(qn("w:hanging"))) if ind is not None else 0,
                }
            abstract[an.get(qn("w:abstractNumId"))] = lv
        out = {}
        for num in root.findall(qn("w:num")):
            aid = num.find(qn("w:abstractNumId"))
            if aid is not None:
                out[num.get(qn("w:numId"))] = abstract.get(aid.get(qn("w:val")), {})
        return out

    def _num_of(self, p):
        ppr = p.find(qn("w:pPr"))
        np_ = ppr.find(qn("w:numPr")) if ppr is not None else None
        if np_ is None and ppr is not None:
            ps = ppr.find(qn("w:pStyle"))
            sid, guard = (ps.get(qn("w:val")) if ps is not None else None), 0
            while sid and guard < 15 and np_ is None:
                st = self.style_by_id.get(sid)
                if st is None:
                    break
                spr = st.find(qn("w:pPr"))
                np_ = spr.find(qn("w:numPr")) if spr is not None else None
                base = st.find(qn("w:basedOn"))
                sid = base.get(qn("w:val")) if base is not None else None
                guard += 1
        if np_ is None:
            return None
        nid = np_.find(qn("w:numId"))
        il = np_.find(qn("w:ilvl"))
        num_id = nid.get(qn("w:val")) if nid is not None else None
        if not num_id or num_id == "0" or num_id not in self.numbering:
            return None
        return num_id, (il.get(qn("w:val")) if il is not None else "0")

    @staticmethod
    def _fmt_num(n, fmt):
        if fmt in ("lowerLetter", "upperLetter"):
            s = ""
            while n > 0:
                n, r = divmod(n - 1, 26)
                s = chr(97 + r) + s
            return s.upper() if fmt == "upperLetter" else s
        if fmt in ("lowerRoman", "upperRoman"):
            vals = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
                    (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
            s = ""
            for v, r in vals:
                while n >= v:
                    s += r
                    n -= v
            return s.upper() if fmt == "upperRoman" else s
        if fmt == "decimalZero":
            return f"{n:02d}"
        return str(n)

    def _label(self, num_id, ilvl):
        levels = self.numbering[num_id]
        lvl = levels.get(ilvl) or {"fmt": "decimal", "text": "%1.", "start": 1}
        key = (num_id, ilvl)
        self.counters[key] = self.counters.get(key, lvl["start"] - 1) + 1
        for (nid, il) in list(self.counters):  # níveis mais internos recomeçam
            if nid == num_id and int(il) > int(ilvl):
                del self.counters[(nid, il)]
        if lvl["fmt"] == "bullet":
            return "•", lvl
        def repl(m):
            k = str(int(m.group(1)) - 1)
            lv = levels.get(k) or {"fmt": "decimal", "start": 1}
            return self._fmt_num(self.counters.get((num_id, k), lv.get("start", 1)), lv["fmt"])
        return re.sub(r"%(\d)", repl, lvl["text"]), lvl

    # -- imagens
    def _image(self, rid, cx=None, cy=None):
        try:
            part = self.part.related_parts[rid]
        except KeyError:
            return ""
        ctype = getattr(part, "content_type", "image/png")
        if not ctype.startswith("image/") or "wmf" in ctype or "emf" in ctype:
            self.avisos.add("Há imagens em formato antigo (WMF/EMF) que aparecem no Word, mas não na prévia/PDF.")
            return '<span class="sem-previa">[imagem]</span>'
        data = base64.b64encode(part.blob).decode()
        size = ""
        if cx and cy:
            size = f' style="width:{int(cx) / 360000:.2f}cm;height:{int(cy) / 360000:.2f}cm"'
        return f'<img src="data:{ctype};base64,{data}"{size} alt="">'

    def _drawing(self, el):
        ext = el.find(f".//{{{WP_NS}}}extent")
        cx, cy = (ext.get("cx"), ext.get("cy")) if ext is not None else (None, None)
        blip = el.find(f".//{{{A_NS}}}blip")
        if blip is not None:
            rid = blip.get(f"{{{R_NS}}}embed")
            if rid:
                return self._image(rid, cx, cy)
        txbx = el.find(f".//{{{WPS_NS}}}txbx")
        if txbx is not None:
            inner = txbx.find(qn("w:txbxContent"))
            if inner is not None:
                return f'<span class="caixa-texto">{self.blocks(inner)}</span>'
        if el.find(".//{http://schemas.openxmlformats.org/drawingml/2006/chart}chart") is not None:
            self.avisos.add("Gráficos do Word aparecem no arquivo Word, mas não na prévia/PDF.")
            return '<span class="sem-previa">[gráfico — veja no arquivo Word]</span>'
        return ""

    def _vml(self, el):
        imgd = el.find(f".//{{{V_NS}}}imagedata")
        if imgd is not None and imgd.get(f"{{{R_NS}}}id"):
            shape = imgd.getparent()
            style = shape.get("style", "") if shape is not None else ""
            w = re.search(r"width:([\d.]+)pt", style)
            h = re.search(r"height:([\d.]+)pt", style)
            img = self._image(imgd.get(f"{{{R_NS}}}id"))
            if w and h and img.startswith("<img"):
                img = img.replace("<img ", f'<img style="width:{w.group(1)}pt;height:{h.group(1)}pt" ', 1)
            return img
        inner = el.find(f".//{qn('w:txbxContent')}")
        if inner is not None:
            return f'<span class="caixa-texto">{self.blocks(inner)}</span>'
        return ""

    # -- trechos de texto
    def _run(self, r, state):
        rpr = r.find(qn("w:rPr"))
        css, wrap = [], []
        if rpr is not None:
            def on(tag):
                el = rpr.find(qn(tag))
                return el is not None and el.get(qn("w:val")) not in ("0", "false", "off")
            if on("w:b"):
                css.append("font-weight:700")
            if rpr.find(qn("w:b")) is not None and not on("w:b"):
                css.append("font-weight:400")
            if on("w:i"):
                css.append("font-style:italic")
            u = rpr.find(qn("w:u"))
            if u is not None and u.get(qn("w:val")) not in ("none", "0", "false"):
                css.append("text-decoration:underline")
            if on("w:strike"):
                css.append("text-decoration:line-through")
            if on("w:caps"):
                css.append("text-transform:uppercase")
            if on("w:smallCaps"):
                css.append("font-variant:small-caps")
            va = rpr.find(qn("w:vertAlign"))
            if va is not None and va.get(qn("w:val")) in ("superscript", "subscript"):
                wrap.append("sup" if va.get(qn("w:val")) == "superscript" else "sub")
            col = rpr.find(qn("w:color"))
            if col is not None and re.fullmatch(r"[0-9A-Fa-f]{6}", col.get(qn("w:val"), "")):
                css.append(f"color:#{col.get(qn('w:val'))}")
            hl = rpr.find(qn("w:highlight"))
            cores = {"yellow": "#ffff00", "green": "#00ff00", "cyan": "#00ffff", "magenta": "#ff00ff",
                     "lightGray": "#d3d3d3", "red": "#ff0000", "blue": "#0000ff"}
            if hl is not None and hl.get(qn("w:val")) in cores:
                css.append(f"background:{cores[hl.get(qn('w:val'))]}")
            shd = rpr.find(qn("w:shd"))
            if shd is not None and re.fullmatch(r"[0-9A-Fa-f]{6}", shd.get(qn("w:fill"), "")):
                css.append(f"background:#{shd.get(qn('w:fill'))}")
            sz = rpr.find(qn("w:sz"))
            if sz is not None and sz.get(qn("w:val"), "").isdigit():
                css.append(f"font-size:{int(sz.get(qn('w:val'))) / 2}pt")
            rf = rpr.find(qn("w:rFonts"))
            if rf is not None and rf.get(qn("w:ascii")):
                css.append(f"font-family:'{esc(rf.get(qn('w:ascii')))}',Arial,sans-serif")
        parts = []
        for ch in r:
            t = _local(ch.tag)
            if t == "t":
                if state["campo"] != "codigo":
                    parts.append(esc(ch.text))
            elif t == "tab":
                parts.append('<span class="tab"></span>')
            elif t in ("br", "cr"):
                if ch.get(qn("w:type")) == "page":
                    state["quebra"] = True
                else:
                    parts.append("<br>")
            elif t == "noBreakHyphen":
                parts.append("&#8209;")
            elif t == "softHyphen":
                parts.append("&shy;")
            elif t == "sym":
                code = ch.get(qn("w:char"), "")
                try:
                    c = int(code, 16)
                    if c >= 0xF000:
                        c -= 0xF000
                    parts.append(esc(chr(c)))
                except ValueError:
                    pass
            elif t == "drawing":
                parts.append(self._drawing(ch))
            elif t in ("pict", "object"):
                parts.append(self._vml(ch))
            elif t == "fldChar":
                kind = ch.get(qn("w:fldCharType"))
                state["campo"] = "codigo" if kind == "begin" else ("resultado" if kind == "separate" else None)
            elif t == "AlternateContent":
                fb = ch.find(f"{{{MC_NS}}}Choice")
                if fb is None:
                    fb = ch.find(f"{{{MC_NS}}}Fallback")
                if fb is not None:
                    for sub in fb:
                        if _local(sub.tag) == "drawing":
                            parts.append(self._drawing(sub))
                        elif _local(sub.tag) == "pict":
                            parts.append(self._vml(sub))
        text = "".join(parts)
        for w in wrap:
            text = f"<{w}>{text}</{w}>"
        if css and text:
            text = f'<span style="{";".join(css)}">{text}</span>'
        return text

    def inline(self, el, state):
        out = []
        for ch in el:
            t = _local(ch.tag)
            if t == "r" and ch.tag == qn("w:r"):
                out.append(self._run(ch, state))
            elif ch.tag in (f"{M}oMath", f"{M}oMathPara"):
                out.append(math_html(ch))
            elif t in ("hyperlink", "ins", "smartTag", "customXml", "fldSimple", "moveTo", "bdo", "dir"):
                out.append(self.inline(ch, state))
            elif t == "sdt":
                c = ch.find(qn("w:sdtContent"))
                if c is not None:
                    out.append(self.inline(c, state))
            # w:del, w:moveFrom, pPr, bookmarks etc. não aparecem
        return "".join(out)

    def paragraph(self, p):
        ppr = p.find(qn("w:pPr"))
        cls = "corpo"
        css = []
        attrs = []
        if ppr is not None:
            ps = ppr.find(qn("w:pStyle"))
            if ps is not None:
                cls = self.style_key.get(ps.get(qn("w:val")), "corpo")
            jc = ppr.find(qn("w:jc"))
            if jc is not None and jc.get(qn("w:val")) in ALIGN:
                css.append(f"text-align:{ALIGN[jc.get(qn('w:val'))]}")
            ind = ppr.find(qn("w:ind"))
            if ind is not None:
                left = ind.get(qn("w:left")) or ind.get(qn("w:start"))
                if left:
                    css.append(f"margin-left:{_twips_cm(left):.2f}cm")
                if ind.get(qn("w:firstLine")):
                    css.append(f"text-indent:{_twips_cm(ind.get(qn('w:firstLine'))):.2f}cm")
                if ind.get(qn("w:hanging")):
                    css.append(f"text-indent:-{_twips_cm(ind.get(qn('w:hanging'))):.2f}cm")
            if ppr.find(qn("w:keepNext")) is not None:
                attrs.append('data-kn="1"')
            if ppr.find(qn("w:pageBreakBefore")) is not None:
                attrs.append('data-antes="pagina"')
        state = {"campo": None, "quebra": False}
        label = ""
        num = self._num_of(p)
        if num:
            text_label, lvl = self._label(*num)
            label = f'<span class="rotulo-lista">{esc(text_label)}</span>'
            if lvl.get("left"):
                css.append(f"margin-left:{lvl['left']:.2f}cm")
                css.append(f"text-indent:-{lvl.get('hanging', 0.63) or 0.63:.2f}cm")
        content = self.inline(p, state)
        if not content.strip():
            content = "&nbsp;"
        if state["quebra"]:
            attrs.append('data-depois="pagina"')
        style = f' style="{";".join(css)}"' if css else ""
        extra = (" " + " ".join(attrs)) if attrs else ""
        return f'<p class="{cls}"{style}{extra}>{label}{content}</p>'

    def table(self, tbl):
        rows = tbl.findall(qn("w:tr"))
        tblpr = tbl.find(qn("w:tblPr"))
        bordered = False
        if tblpr is not None:
            b = tblpr.find(qn("w:tblBorders"))
            if b is not None:
                bordered = any(x.get(qn("w:val")) not in (None, "nil", "none") for x in b)
            ts = tblpr.find(qn("w:tblStyle"))
            if ts is not None and not bordered:
                st = self.style_by_id.get(ts.get(qn("w:val")))
                if st is not None:
                    sb = st.find(f".//{qn('w:tblBorders')}")
                    bordered = sb is not None and any(
                        x.get(qn("w:val")) not in (None, "nil", "none") for x in sb)
        width = ""
        if tblpr is not None:
            tw = tblpr.find(qn("w:tblW"))
            if tw is not None and tw.get(qn("w:type")) == "pct":
                width = "width:100%;"
        # células mescladas verticalmente: conta quantas linhas cada início ocupa
        grid = []
        for r in rows:
            line, col = [], 0
            for tc in r.findall(qn("w:tc")):
                pr = tc.find(qn("w:tcPr"))
                span = 1
                vm = None
                if pr is not None:
                    gs = pr.find(qn("w:gridSpan"))
                    if gs is not None:
                        span = int(gs.get(qn("w:val"), "1"))
                    v = pr.find(qn("w:vMerge"))
                    if v is not None:
                        vm = v.get(qn("w:val"), "continue")
                line.append({"tc": tc, "col": col, "span": span, "vm": vm, "rows": 1})
                col += span
            grid.append(line)
        for ri, line in enumerate(grid):
            for cell in line:
                if cell["vm"] == "restart":
                    k = ri + 1
                    while k < len(grid):
                        nxt = next((c for c in grid[k] if c["col"] == cell["col"]), None)
                        if nxt and nxt["vm"] == "continue":
                            cell["rows"] += 1
                            k += 1
                        else:
                            break
        out = [f'<table class="{"com-bordas" if bordered else "sem-bordas"}" style="{width}">']
        for line in grid:
            out.append("<tr>")
            for cell in line:
                if cell["vm"] == "continue":
                    continue
                attrs = ""
                if cell["span"] > 1:
                    attrs += f' colspan="{cell["span"]}"'
                if cell["rows"] > 1:
                    attrs += f' rowspan="{cell["rows"]}"'
                pr = cell["tc"].find(qn("w:tcPr"))
                if pr is not None:
                    shd = pr.find(qn("w:shd"))
                    if shd is not None and re.fullmatch(r"[0-9A-Fa-f]{6}", shd.get(qn("w:fill"), "")):
                        attrs += f' style="background:#{shd.get(qn("w:fill"))}"'
                out.append(f"<td{attrs}>{self.blocks(cell['tc'])}</td>")
            out.append("</tr>")
        out.append("</table>")
        return "".join(out)

    def blocks(self, container, stop_at_section=False):
        out = []
        for ch in container:
            t = _local(ch.tag)
            if t == "p" and ch.tag == qn("w:p"):
                ppr = ch.find(qn("w:pPr"))
                if stop_at_section and ppr is not None and ppr.find(qn("w:sectPr")) is not None:
                    par = self.paragraph(ch)
                    if "&nbsp;</p>" not in par:  # o parágrafo vazio da quebra de seção não é desenhado
                        out.append(par)
                    return "".join(out), True
                out.append(self.paragraph(ch))
            elif t == "tbl":
                out.append(self.table(ch))
            elif t == "sdt":
                c = ch.find(qn("w:sdtContent"))
                if c is not None:
                    out.append(self.blocks(c))
            elif t == "customXml":
                out.append(self.blocks(ch))
        return ("".join(out), False) if stop_at_section else "".join(out)


# ----------------------------------------------------------------------------- estilos

def _style_css(cls, cfg, body):
    font = cfg.get("font") or body["font"]
    size = float(cfg.get("size") or body["size"])
    color = cfg.get("color") or body["color"]
    ls = float(cfg.get("line_spacing") or body["line_spacing"]) * LINHA_SIMPLES
    props = [
        f"font-family:'{font}',Arial,'Liberation Sans',Helvetica,sans-serif",
        f"font-size:{size}pt", f"color:{color}", f"line-height:{ls:.3f}",
        f"text-align:{ALIGN.get(cfg.get('align') or 'left', 'left')}",
        f"margin:{float(cfg.get('space_before') or 0)}pt {float(cfg.get('right_indent') or 0)}cm "
        f"{float(cfg.get('space_after') or 0)}pt {float(cfg.get('left_indent') or 0)}cm",
        f"text-indent:{float(cfg.get('first_line_indent') or 0)}cm",
        f"font-weight:{700 if cfg.get('bold') else 400}",
        f"font-style:{'italic' if cfg.get('italic') else 'normal'}",
    ]
    if cfg.get("underline"):
        props.append("text-decoration:underline")
    if cfg.get("caps"):
        props.append("text-transform:uppercase")
    return f"p.{cls}{{{';'.join(props)}}}"


def _css(s):
    body = s["body"]
    st = s["styles"]
    pg = s["page"]
    q = s["questions"]
    base = {k: body[k] for k in ("font", "size", "color", "bold", "italic", "underline", "align",
                                 "space_before", "space_after", "line_spacing", "left_indent",
                                 "right_indent", "first_line_indent")}
    rules = [_style_css("corpo", base, body), _style_css("empty", base, body),
             _style_css("student_info", base, body),
             _style_css("list", dict(base, first_line_indent=0, space_after=min(float(body["space_after"]), 3)), body)]
    for key in ("title", "heading1", "heading2", "activity", "instruction", "question", "quote",
                "caption", "reference"):
        rules.append(_style_css(key, st[key], body))
    alt = dict(st["alternative"])
    hanging = float(q.get("alternative_hanging") or 0)
    alt["left_indent"] = float(q.get("alternative_indent") or 0) + hanging
    alt["first_line_indent"] = -hanging
    rules.append(_style_css("alternative", alt, body))
    rules.append(_style_css("image", dict(base, align="center" if s["images"]["center"] else "left",
                                          first_line_indent=0, left_indent=0, line_spacing=1.0,
                                          space_before=6, space_after=6), body))
    rules.append(_style_css("equation", dict(base, align="center", first_line_indent=0, left_indent=0,
                                             space_before=6, space_after=6), body))
    rules.append(_style_css("table", dict(base, size=s["tables"]["font_size"], align="left",
                                          first_line_indent=0, left_indent=0, right_indent=0,
                                          line_spacing=1.0, space_before=0, space_after=0), body))
    cols = int(pg.get("columns") or 1)
    return "\n".join(rules), cols


# ----------------------------------------------------------------------------- página

VERDE_ESCURO = "#0F3A2C"
VERDE = "#1C6048"
VERDE_MEDIO = "#237657"
VERDE_CLARO = "#CFE4D9"
CINZA_VERDE = "#4A5A52"
MENTA = "#1CE692"


def _logo_data():
    p = Path(ASSETS) / "logo-fleming.png"
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode() if p.exists() else ""


def _campos_html(rows):
    """Quadro do estudante: uma tabela com colunas mescladas como no Word."""
    if not rows:
        return ""
    cuts = sorted({round(sum(f for _, f in row[:i + 1]), 4) for row in rows for i in range(len(row))} | {0.0, 1.0})
    cols = [round(b - a, 4) for a, b in zip(cuts, cuts[1:]) if b - a > 0.001]
    cuts = [0.0]
    for c in cols:
        cuts.append(round(cuts[-1] + c, 4))
    out = ['<table class="campos"><colgroup>']
    out += [f'<col style="width:{c * 100:.2f}%">' for c in cols]
    out.append("</colgroup>")
    for row in rows:
        out.append("<tr>")
        pos = 0.0
        for label, frac in row:
            start = min(range(len(cuts)), key=lambda i: abs(cuts[i] - pos))
            pos = round(pos + frac, 4)
            end = min(range(len(cuts)), key=lambda i: abs(cuts[i] - pos))
            out.append(f'<td colspan="{max(1, end - start)}">{esc(label)}:</td>')
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def _cabecalho_html(fl, logo, com_campos=True):
    linhas = "".join(f'<div class="cab-linha">{esc(l)}</div>' for l in fl.get("linhas", []))
    campos = _campos_html(fl.get("campos")) if com_campos else ""
    return f"""
<header class="cabecalho">
  <div class="cab-faixa">
    <div class="cab-logo">{f'<img src="{logo}" alt="Fleming Ensino Médio">' if logo else ''}</div>
    <div class="cab-texto">
      <div class="cab-rotulo">{esc(fl.get('rotulo', ''))}</div>
      <div class="cab-titulo">{esc(fl.get('titulo', ''))}</div>
      {linhas}
    </div>
  </div>
  {campos}
</header>"""


def _grade_html(cfg, fl, logo):
    n = int(cfg.get("questoes") or 20)
    letras = list(cfg.get("alternativas") or "ABCDE")
    por_bloco = -(-n // 2)

    def bloco(ini):
        cab = "<tr><th>Questão</th>" + "".join(f"<th>{l}</th>" for l in letras) + "</tr>"
        linhas = []
        for q in range(ini, ini + por_bloco):
            if q > n:
                linhas.append("<tr class='vazia'>" + "<td></td>" * (len(letras) + 1) + "</tr>")
                continue
            linhas.append(f"<tr><td class='q'>{q:02d}</td>" + "".join(f"<td>{l}</td>" for l in letras) + "</tr>")
        return f'<table class="grade-tab">{cab}{"".join(linhas)}</table>'

    return f"""
<section class="pagina-grade">
  {_cabecalho_html(fl, logo)}
  <h2 class="grade-titulo">GRADE DE RESPOSTAS</h2>
  <p class="grade-instr">Marque apenas uma alternativa por questão, preenchendo completamente o quadro com caneta
  azul ou preta. Questões rasuradas ou com mais de uma marcação serão anuladas.</p>
  <div class="grade-blocos">{bloco(1)}{bloco(por_bloco + 1)}</div>
  <p class="grade-nota">Somente as respostas marcadas nesta grade serão consideradas na correção.</p>
</section>"""


def render(doc, s, titulo="Documento"):
    """Retorna (html, avisos)."""
    r = Renderer(doc, s)
    style_rules, cols = _css(s)
    pg = s["page"]
    fl = (s.get("header") or {}).get("fleming") or {}
    logo = _logo_data()
    body = doc.element.body
    if s.get("answer_sheet"):
        # a grade acrescentada pelo motor fica depois da quebra de seção; aqui ela é desenhada à parte
        conteudo, _ = r.blocks(body, stop_at_section=True)
    else:
        conteudo = r.blocks(body)
    grade = _grade_html(s["answer_sheet"], fl, logo) if s.get("answer_sheet") else ""
    mb = float(pg["margin_bottom"])
    ml, mr = float(pg["margin_left"]), float(pg["margin_right"])
    page_fmt = s["numbering"].get("page_format") or "Página {n} de {t}"
    config = json.dumps({"colunas": cols, "resumo": fl.get("resumo", ""), "formato_pagina": page_fmt},
                        ensure_ascii=False)

    # As páginas são montadas por um pequeno script (abaixo): o conteúdo é distribuído em
    # folhas A4 com colunas, cabeçalho e numeração. A mesma montagem aparece na tela e é
    # impressa no PDF — a prévia é exatamente o que sai na impressão.
    doc_html = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>{esc(titulo)}</title>
<style>
@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; }}
html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{ margin: 0; font-family: Arial, 'Liberation Sans', Helvetica, sans-serif; color: #000; }}
p {{ orphans: 2; widows: 2; }}
{style_rules}
.rotulo-lista {{ display: inline-block; min-width: 0.63cm; text-indent: 0; }}
.tab {{ display: inline-block; width: 1.25cm; }}
img {{ max-width: 100%; height: auto; vertical-align: middle; }}
p.image img {{ display: inline-block; }}
math[display="block"] {{ margin: 4pt 0; }}
math {{ font-size: 1.05em; }}
table {{ border-collapse: collapse; margin: 0 auto 6pt; break-inside: avoid; }}
table.com-bordas td {{ border: 0.75pt solid #000; }}
td {{ padding: 1pt 4pt; vertical-align: top; }}
td p {{ margin: 0 !important; text-indent: 0 !important; }}
.caixa-texto {{ display: inline-block; border: 0.75pt solid #999; padding: 3pt 6pt; vertical-align: top; }}
.sem-previa {{ display: inline-block; border: 1px dashed #999; color: #666; font-size: 9pt; padding: 6pt 10pt; }}

/* folhas A4 */
.pagina {{ position: relative; width: 21cm; height: 29.7cm; overflow: hidden; background: #fff;
          padding: 0.7cm {mr}cm {mb}cm {ml}cm; display: flex; flex-direction: column; break-after: page; }}
.pagina:last-child {{ break-after: auto; }}
.corpo-pagina {{ flex: 1; min-height: 0; display: flex; }}
.coluna {{ flex: 1 1 0; min-width: 0; height: 100%; overflow: hidden; }}
.coluna > :first-child {{ margin-top: 0 !important; }}
.sep {{ flex: none; width: 0.4cm; margin-right: 0.4cm; border-right: 0.5pt solid #000; }}
.cab-resumo {{ font: 700 8.5pt Arial, sans-serif; color: {VERDE}; border-bottom: 1.5pt solid {MENTA};
              padding: 0.15cm 0 4pt; margin-bottom: 0.4cm; }}
.num-pag {{ position: absolute; left: 0; right: 0; bottom: 0.75cm; text-align: center;
           font: 8.5pt Arial, sans-serif; color: #333; }}
#fonte, template {{ display: none; }}

/* cabeçalho do Fleming (fundo branco, econômico para impressão) */
.cabecalho {{ margin-bottom: 0.45cm; break-inside: avoid; }}
.cab-faixa {{ display: flex; align-items: center; justify-content: space-between; gap: 0.4cm;
             padding: 0.05cm 0 0.33cm; border-bottom: 2.25pt solid {MENTA}; }}
.cab-logo img {{ height: 1.15cm; width: auto; display: block; }}
.cab-texto {{ text-align: right; line-height: 1.2; }}
.cab-rotulo {{ font: 700 7pt Arial, sans-serif; color: {VERDE_MEDIO}; margin-bottom: 3pt; }}
.cab-titulo {{ font: 700 15pt Arial, sans-serif; color: {VERDE_ESCURO}; margin-bottom: 5pt; }}
.cab-linha {{ font: 9pt Arial, sans-serif; color: {CINZA_VERDE}; margin-bottom: 3pt; }}
.campos {{ width: 100%; margin: 0.35cm 0 0; table-layout: fixed; }}
.campos td {{ border: 0.75pt solid {VERDE_CLARO}; font: 700 9pt Arial, sans-serif; color: {VERDE};
             padding: 0.19cm 0.21cm; height: 0.75cm; vertical-align: top; }}

/* página da grade de respostas */
.grade-titulo {{ text-align: center; font: 700 16pt Arial, sans-serif; color: {VERDE_ESCURO}; margin: 0.2cm 0 4pt; }}
.grade-instr {{ font: 10pt Arial, sans-serif; color: {CINZA_VERDE}; text-align: justify; margin: 0 0 12pt; line-height: 1.15; }}
.grade-blocos {{ display: flex; justify-content: center; gap: 1.2cm; }}
.grade-tab {{ margin: 0; }}
.grade-tab th {{ font: 700 10pt Arial, sans-serif; color: {VERDE_ESCURO}; border: 1.5pt solid {MENTA};
                height: 0.85cm; width: 1.3cm; text-align: center; vertical-align: middle; }}
.grade-tab th:first-child {{ width: 1.8cm; }}
.grade-tab td {{ border: 1pt solid {VERDE_CLARO}; height: 0.95cm; text-align: center; vertical-align: middle;
                font: 10pt Arial, sans-serif; color: #9AB5A6; }}
.grade-tab td.q {{ font: 700 11pt Arial, sans-serif; color: {VERDE_ESCURO}; }}
.grade-tab tr.vazia td {{ border: 0; }}
.grade-nota {{ text-align: center; font: 9pt Arial, sans-serif; color: {CINZA_VERDE}; margin-top: 10pt; }}

/* na tela: folhas com sombra sobre fundo cinza */
@media screen {{
  html {{ background: #e7eaee; }}
  body {{ padding: 16px 0; }}
  .pagina {{ margin: 0 auto 16px; box-shadow: 0 2px 10px rgba(0,0,0,.18); }}
}}
@media print {{ body {{ margin: 0; }} .pagina {{ margin: 0; box-shadow: none; }} }}
</style></head>
<body>
<div id="paginas"></div>
<div id="fonte">{conteudo}</div>
<template id="cab-completo">{_cabecalho_html(fl, logo) if fl else ''}</template>
<template id="grade">{grade}</template>
<script>
(function () {{
  var CFG = {config};
  var paginas = document.getElementById('paginas');
  var fonte = document.getElementById('fonte');
  var cabCompleto = document.getElementById('cab-completo').innerHTML;
  var grade = document.getElementById('grade').innerHTML.trim();

  function novaPagina(primeira) {{
    var pg = document.createElement('section');
    pg.className = 'pagina';
    var resumo = document.createElement('div');
    resumo.className = 'cab-resumo';
    resumo.textContent = CFG.resumo;
    var html = primeira ? cabCompleto : resumo.outerHTML;
    html += '<div class="corpo-pagina">';
    for (var i = 0; i < CFG.colunas; i++) html += (i ? '<div class="sep"></div>' : '') + '<div class="coluna"></div>';
    html += '</div><div class="num-pag"></div>';
    pg.innerHTML = html;
    paginas.appendChild(pg);
    return Array.prototype.slice.call(pg.querySelectorAll('.coluna'));
  }}

  function cabe(col) {{ return col.scrollHeight <= col.clientHeight + 1; }}

  function montar() {{
    var blocos = Array.prototype.slice.call(fonte.children);
    var cols = novaPagina(true), ci = 0;
    function proxima() {{
      ci += 1;
      if (ci >= cols.length) {{ cols = novaPagina(false); ci = 0; }}
      return cols[ci];
    }}
    var col = cols[0];
    blocos.forEach(function (b) {{
      if (b.dataset.antes === 'pagina' && col.children.length) {{ cols = novaPagina(false); ci = 0; col = cols[0]; }}
      col.appendChild(b);
      if (!cabe(col) && col.children.length > 1) {{
        col.removeChild(b);
        // "manter com o próximo": a questão acompanha suas alternativas para a próxima coluna
        var mover = [b];
        var ant = col.lastElementChild;
        while (ant && ant.dataset.kn === '1' && col.children.length > 1) {{
          mover.unshift(ant); col.removeChild(ant); ant = col.lastElementChild;
        }}
        col = proxima();
        mover.forEach(function (m) {{ col.appendChild(m); }});
      }}
      if (b.dataset.depois === 'pagina') {{ cols = novaPagina(false); ci = 0; col = cols[0]; }}
    }});
    if (grade) {{
      var g = document.createElement('section');
      g.className = 'pagina';
      g.innerHTML = grade + '<div class="num-pag"></div>';
      paginas.appendChild(g);
    }}
    var todas = paginas.querySelectorAll('.pagina');
    for (var k = 0; k < todas.length; k++) {{
      todas[k].querySelector('.num-pag').textContent =
        CFG.formato_pagina.replace('{{n}}', k + 1).replace('{{t}}', todas.length);
    }}
    document.documentElement.setAttribute('data-paginas', todas.length);
  }}

  var imgs = Array.prototype.slice.call(fonte.querySelectorAll('img'));
  Promise.all(imgs.map(function (i) {{ return i.decode ? i.decode().catch(function () {{}}) : null; }}))
    .then(function () {{ return document.fonts ? document.fonts.ready : null; }})
    .then(montar, montar);
}})();
</script>
</body></html>"""
    return doc_html, sorted(r.avisos)
