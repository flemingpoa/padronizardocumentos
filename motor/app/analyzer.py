"""Reconhecimento da estrutura do documento.

Usa regras determinísticas (estilos do Word, tamanho/negrito do texto, numeração e
expressões regulares típicas de provas e atividades). Nada aqui altera o texto: o
resultado é apenas uma classificação de cada parágrafo.
"""
import re
import unicodedata
from collections import Counter

from docx.oxml.ns import qn

from .docxutil import (T_DRAWING, T_OBJECT, T_OMATH, T_PICT, T_TXBX, iter_block_paragraphs,
                       iter_runs, iter_tables, media_counts, para_text, run_text, table_paragraphs)

TYPE_LABELS = {
    "title": "Título principal",
    "heading1": "Título de seção",
    "heading2": "Subtítulo",
    "activity": "Identificação de atividade",
    "instruction": "Instruções",
    "question": "Questão",
    "alternative": "Alternativa",
    "body": "Parágrafo",
    "list": "Item de lista",
    "quote": "Citação",
    "caption": "Legenda",
    "reference": "Referência",
    "student_info": "Identificação do estudante",
    "image": "Imagem",
    "equation": "Equação",
    "empty": "Linha em branco",
    "keep": "Mantido como está",
}
USER_SELECTABLE = [t for t in TYPE_LABELS if t not in ("empty",)]

QUESTION_RE = re.compile(
    r"^(?P<label>\s*(?:"
    r"(?P<word>quest[ãa]o|exerc[íi]cio|problema|q)\s*(?:n[º°o]\.?\s*)?(?P<n1>\d{1,3})\s*[ºª°]?\s*(?:[.):\-–—]+)?"
    r"|(?P<n2>\d{1,3})\s*(?:[ºª°]\s*)?(?:\.(?!\d)|\)|\s[\-–—]|[\-–—])"
    r")\s*)",
    re.I,
)
ALT_RE = re.compile(
    r"^(?P<label>\s*(?:"
    r"\(\s*(?P<l1>[a-jA-J])\s*\)"
    r"|(?P<l2>[a-jA-J])\s*(?:\)|\.(?=\s)|\s?[\-–—](?=\s))"
    r"|\[\s*(?P<l3>[a-jA-J])\s*\]"
    r")\s*)"
)
VF_RE = re.compile(r"^\s*\(\s{0,4}[VFvfCEce]?\s{0,4}\)\s*")
ROMAN_RE = re.compile(r"^\s*(?=[IVX])(?:X{0,1}(?:IX|IV|V?I{0,3}))\s*[.)\-–—]\s+")
BULLET_RE = re.compile(r"^\s*[•●▪■◦○➢➤✓\*]\s+")
INSTR_RE = re.compile(
    r"^\s*(instru[çc][õo]es|orienta[çc][õo]es|aten[çc][ãa]o|observa[çc][ãa]o|observa[çc][õo]es"
    r"|obs\.?|importante|leia\s+(com\s+)?aten[çc][ãa]o|leia\s+atentamente)\b",
    re.I,
)
ACTIVITY_RE = re.compile(
    r"^\s*(atividade|parte|se[çc][ãa]o|bloco|unidade|m[óo]dulo|etapa|tarefa)\s+(\d{1,3}|[ivxlc]+|[a-z])\b",
    re.I,
)
CAPTION_RE = re.compile(
    r"^\s*(figura|fig\.|tabela|quadro|gr[áa]fico|imagem|ilustra[çc][ãa]o|fonte)\s*\d*\s*[:\-–—.]", re.I)
REF_HEAD_RE = re.compile(
    r"^\s*(refer[êe]ncias(\s+bibliogr[áa]ficas)?|bibliografia|obras\s+citadas)\s*:?\s*$", re.I)
STUDENT_RE = re.compile(
    r"(nome\s*(do\s+aluno|do\s+estudante|da\s+aluna|completo)?\s*:?\s*(_{3,}|\.{5,}|\t))|"
    r"(aluno\(?a?\)?\s*:\s*_{3,})|(turma\s*:\s*_{2,}.*n[º°o]\.?\s*:?)", re.I)
NUMBERED_HEADING_RE = re.compile(r"^\s*\d{1,2}(\.\d{1,2})+\.?\s+\S")


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _val_on(el):
    """Interpreta propriedades booleanas do Word (<w:b/>, <w:b w:val="0"/>)."""
    if el is None:
        return None
    v = el.get(qn("w:val"))
    return v not in ("0", "false", "off")


class StyleResolver:
    """Resolve tamanho, negrito e nível de tópico herdados de estilos."""

    def __init__(self, doc):
        self.styles_el = doc.styles.element
        self.by_id = {s.get(qn("w:styleId")): s for s in self.styles_el.findall(qn("w:style"))}
        self.cache = {}
        self.default_size = 10.0
        dd = self.styles_el.find(qn("w:docDefaults"))
        if dd is not None:
            sz = dd.find(f"{qn('w:rPrDefault')}/{qn('w:rPr')}/{qn('w:sz')}")
            if sz is not None and sz.get(qn("w:val")):
                self.default_size = int(sz.get(qn("w:val"))) / 2
        self.default_para_id = None
        for sid, s in self.by_id.items():
            if s.get(qn("w:type")) == "paragraph" and s.get(qn("w:default")) in ("1", "true"):
                self.default_para_id = sid

    def info(self, style_id):
        if style_id is None:
            style_id = self.default_para_id
        if style_id in self.cache:
            return self.cache[style_id]
        res = {"name": "", "size": None, "bold": None, "outline": None, "jc": None,
               "ind_left": None, "numbered": False}
        chain, sid, guard = [], style_id, 0
        while sid and sid in self.by_id and guard < 20:
            chain.append(self.by_id[sid])
            base = self.by_id[sid].find(qn("w:basedOn"))
            sid = base.get(qn("w:val")) if base is not None else None
            guard += 1
        if chain:
            name_el = chain[0].find(qn("w:name"))
            res["name"] = name_el.get(qn("w:val")) if name_el is not None else ""
        for s in chain:  # do mais específico para o mais genérico
            rpr = s.find(qn("w:rPr"))
            ppr = s.find(qn("w:pPr"))
            if rpr is not None:
                sz = rpr.find(qn("w:sz"))
                if res["size"] is None and sz is not None and sz.get(qn("w:val")):
                    res["size"] = int(sz.get(qn("w:val"))) / 2
                b = rpr.find(qn("w:b"))
                if res["bold"] is None and b is not None:
                    res["bold"] = _val_on(b)
            if ppr is not None:
                ol = ppr.find(qn("w:outlineLvl"))
                if res["outline"] is None and ol is not None:
                    res["outline"] = int(ol.get(qn("w:val"), "9"))
                jc = ppr.find(qn("w:jc"))
                if res["jc"] is None and jc is not None:
                    res["jc"] = jc.get(qn("w:val"))
                np_ = ppr.find(qn("w:numPr"))
                if np_ is not None and not res["numbered"]:
                    res["numbered"] = True
                    nid = np_.find(qn("w:numId"))
                    il = np_.find(qn("w:ilvl"))
                    res["num_id"] = nid.get(qn("w:val")) if nid is not None else None
                    res["num_ilvl"] = il.get(qn("w:val")) if il is not None else "0"
        if res["size"] is None:
            res["size"] = self.default_size
        res["bold"] = bool(res["bold"])
        self.cache[style_id] = res
        return res

    def char_style(self, style_id):
        s = self.by_id.get(style_id)
        if s is None:
            return None, None
        rpr = s.find(qn("w:rPr"))
        if rpr is None:
            return None, None
        sz = rpr.find(qn("w:sz"))
        size = int(sz.get(qn("w:val"))) / 2 if sz is not None and sz.get(qn("w:val")) else None
        return size, _val_on(rpr.find(qn("w:b")))


class NumberingResolver:
    def __init__(self, doc):
        self.fmt = {}
        try:
            numbering = doc.part.numbering_part.element
        except Exception:  # documento sem numeração
            return
        abstract = {}
        for an in numbering.findall(qn("w:abstractNum")):
            lv = {}
            for lvl in an.findall(qn("w:lvl")):
                nf = lvl.find(qn("w:numFmt"))
                lv[lvl.get(qn("w:ilvl"))] = nf.get(qn("w:val")) if nf is not None else "decimal"
            abstract[an.get(qn("w:abstractNumId"))] = lv
        for num in numbering.findall(qn("w:num")):
            aid = num.find(qn("w:abstractNumId"))
            if aid is not None:
                self.fmt[num.get(qn("w:numId"))] = abstract.get(aid.get(qn("w:val")), {})

    def get(self, num_id, ilvl):
        return self.fmt.get(num_id, {}).get(ilvl or "0")


def _features(p, styles, numbering):
    ppr = p.find(qn("w:pPr"))
    style_id = None
    num_fmt = None
    num_id = None
    ilvl = "0"
    jc = None
    ind_left = 0
    outline = None
    if ppr is not None:
        ps = ppr.find(qn("w:pStyle"))
        style_id = ps.get(qn("w:val")) if ps is not None else None
        np_ = ppr.find(qn("w:numPr"))
        if np_ is not None:
            nid = np_.find(qn("w:numId"))
            il = np_.find(qn("w:ilvl"))
            ilvl = il.get(qn("w:val")) if il is not None else "0"
            if nid is not None and nid.get(qn("w:val")) not in (None, "0"):
                num_id = nid.get(qn("w:val"))
                num_fmt = numbering.get(num_id, ilvl) or "decimal"
        j = ppr.find(qn("w:jc"))
        jc = j.get(qn("w:val")) if j is not None else None
        ind = ppr.find(qn("w:ind"))
        if ind is not None:
            for a in ("w:left", "w:start"):
                v = ind.get(qn(a))
                if v and v.lstrip("-").isdigit():
                    ind_left = int(v)
        ol = ppr.find(qn("w:outlineLvl"))
        if ol is not None:
            outline = int(ol.get(qn("w:val"), "9"))
    sinfo = styles.info(style_id)
    if num_fmt is None and sinfo.get("num_id") not in (None, "0"):
        # numeração automática definida no estilo (ex.: "Lista Numerada" do Word)
        ilvl = sinfo.get("num_ilvl") or "0"
        num_id = sinfo["num_id"]
        num_fmt = numbering.get(num_id, ilvl) or "decimal"
    if outline is None:
        outline = sinfo["outline"]
    jc = jc or sinfo["jc"]

    total = 0
    bold_chars = 0
    size_weight = Counter()
    for r in iter_runs(p):
        t = run_text(r)
        n = len(t.strip())
        if not n:
            continue
        rpr = r.find(qn("w:rPr"))
        size = None
        bold = None
        if rpr is not None:
            sz = rpr.find(qn("w:sz"))
            if sz is not None and sz.get(qn("w:val")):
                try:
                    size = int(sz.get(qn("w:val"))) / 2
                except ValueError:
                    size = None
            bold = _val_on(rpr.find(qn("w:b")))
            rs = rpr.find(qn("w:rStyle"))
            if rs is not None:
                csize, cbold = styles.char_style(rs.get(qn("w:val")))
                size = size if size is not None else csize
                bold = bold if bold is not None else cbold
        if size is None:
            size = sinfo["size"]
        if bold is None:
            bold = sinfo["bold"]
        total += n
        bold_chars += n if bold else 0
        size_weight[round(size * 2) / 2] += n

    text = para_text(p)
    size = size_weight.most_common(1)[0][0] if size_weight else sinfo["size"]
    return {
        "text": text,
        "stripped": text.strip(),
        "style_name": _norm(sinfo["name"]),
        "num_fmt": num_fmt,
        "num_id": num_id,
        "ilvl": ilvl,
        "jc": jc,
        "ind_left": ind_left,
        "outline": outline,
        "size": size,
        "bold_ratio": (bold_chars / total) if total else 0.0,
        "chars": total,
        "has_drawing": p.find(".//" + T_DRAWING) is not None or p.find(".//" + T_PICT) is not None
        or p.find(".//" + T_OBJECT) is not None,
        "has_math": p.find(".//" + T_OMATH) is not None,
    }


def _style_class(name):
    if name in ("title", "titulo"):
        return "title"
    if re.fullmatch(r"(heading|titulo)\s*1", name):
        return "heading1"
    if re.fullmatch(r"(heading|titulo)\s*[2-9]", name) or name in ("subtitle", "subtitulo"):
        return "heading2"
    if name in ("caption", "legenda"):
        return "caption"
    if name.startswith("toc") or name.startswith("sumario") or name.startswith("index")\
            or name.startswith("indice") or name.startswith("table of"):
        return "keep"
    if name in ("quote", "intense quote", "citacao", "citacao intensa", "block text"):
        return "quote"
    return None


def _is_alt_like(f):
    s = f["text"]
    return bool(ALT_RE.match(s) or VF_RE.match(s) or ROMAN_RE.match(s)) or f["num_fmt"] in (
        "lowerLetter", "upperLetter", "lowerRoman", "upperRoman")


def _is_caps(s):
    letters = [c for c in s if c.isalpha() and c.lower() != c.upper()]
    return len(letters) >= 4 and all(c.isupper() for c in letters)


def _ends_sentence(s):
    return s.rstrip().endswith((".", ";", ",", "?", "!", ":"))


def analyze(doc):
    """Classifica cada parágrafo do corpo. Retorna (itens, resumo)."""
    styles = StyleResolver(doc)
    numbering = NumberingResolver(doc)
    body = doc.element.body
    paras = list(iter_block_paragraphs(body))
    feats = [_features(p, styles, numbering) for p in paras]

    # tamanho típico do corpo do texto
    sizes = Counter()
    for f in feats:
        if f["chars"] >= 40:
            sizes[f["size"]] += f["chars"]
    if not sizes:
        for f in feats:
            if f["chars"]:
                sizes[f["size"]] += f["chars"]
    body_size = sizes.most_common(1)[0][0] if sizes else 12.0

    nonempty_idx = [i for i, f in enumerate(feats) if f["stripped"] or f["has_drawing"] or f["has_math"]]

    def next_nonempty(i):
        for j in nonempty_idx:
            if j > i:
                return j
        return None

    def heading_strength(f):
        s = f["stripped"]
        if not s or len(s) > 120 or len(s.split()) > 16:
            return False
        if s.endswith((".", ";", ",")):
            return False
        caps = _is_caps(s)
        if s.endswith(":") and not caps:
            return False
        return f["bold_ratio"] >= 0.9 or f["size"] >= body_size + 1.5 or caps

    types = [None] * len(paras)
    meta = [{} for _ in paras]
    in_question = False
    in_refs = False
    in_instr = False
    title_done = False
    question_count = sum(1 for f in feats if QUESTION_RE.match(f["text"]))

    for i, f in enumerate(feats):
        s = f["stripped"]
        t = None
        if not s and not f["has_drawing"] and not f["has_math"]:
            types[i] = "empty"
            continue
        if not s and f["has_drawing"]:
            types[i] = "image"
            continue
        if f["has_math"] and len(s) <= 3:
            types[i] = "equation"
            continue

        sc = _style_class(f["style_name"])
        if sc == "title" and title_done:
            sc = "heading1"
        if sc is None and f["outline"] is not None and f["outline"] < 9:
            sc = "heading1" if f["outline"] == 0 else "heading2"

        q = QUESTION_RE.match(f["text"])
        a = ALT_RE.match(f["text"])
        nxt = next_nonempty(i)
        next_is_alt = nxt is not None and _is_alt_like(feats[nxt])

        if sc in ("keep",):
            t = "keep"
        elif sc in ("title", "heading1", "heading2"):
            t = sc
        elif STUDENT_RE.search(f["text"]) and i <= 15:
            t = "student_info"
        elif REF_HEAD_RE.match(s):
            t = "heading1"
            in_refs = True
        elif sc == "caption" or (CAPTION_RE.match(s) and len(s) <= 220 and not q):
            t = "caption"
        elif sc == "quote":
            t = "quote"
        elif in_refs and not heading_strength(f):
            t = "reference"
        elif ACTIVITY_RE.match(s) and len(s) <= 90 and not q:
            t = "activity"
        elif INSTR_RE.match(s):
            t = "instruction"
            in_instr = True
        elif q:
            short_heading = heading_strength(f) and "?" not in s and not next_is_alt and not _ends_sentence(s)
            if short_heading and question_count < 3:
                t = "heading1"
            else:
                t = "question"
                meta[i] = {"label": q.group("label"), "number": q.group("n1") or q.group("n2"),
                           "worded": bool(q.group("word"))}
        elif a and (in_question or next_is_alt or (i > 0 and types[i - 1] == "alternative")):
            t = "alternative"
            meta[i] = {"label": a.group("label"),
                       "letter": (a.group("l1") or a.group("l2") or a.group("l3"))}
        elif (VF_RE.match(s) or ROMAN_RE.match(f["text"])) and (in_question or next_is_alt):
            t = "alternative"
        elif f["num_fmt"]:
            fmt = f["num_fmt"]
            if fmt in ("lowerLetter", "upperLetter") and in_question:
                t = "alternative"
            elif fmt == "decimal" and f["ilvl"] == "0" and question_count == 0 and \
                    (len(s) > 60 or s.endswith(("?", ":")) or next_is_alt):
                t = "question"
            elif fmt == "decimal" and f["ilvl"] == "0" and heading_strength(f) and not next_is_alt:
                t = "heading1"
            elif in_instr:
                t = "instruction"
            else:
                t = "list"
        elif BULLET_RE.match(f["text"]):
            t = "instruction" if in_instr else "list"
        elif f["ind_left"] >= 850 and len(s) >= 60:
            t = "quote"
        elif heading_strength(f):
            if NUMBERED_HEADING_RE.match(s):
                t = "heading2"
            else:
                t = "heading_candidate"
        else:
            t = "body"

        # título principal: primeiro destaque logo no início do documento
        if not title_done and t in ("heading_candidate", "heading1", "title"):
            pos = nonempty_idx.index(i) if i in nonempty_idx else 99
            if t == "title" or (pos <= 3 and (f["jc"] == "center" or f["size"] >= body_size + 2
                                               or t == "heading_candidate")):
                t = "title"
                title_done = True
        if t == "title":
            title_done = True

        if t == "question":
            in_question = True
            in_instr = False
        elif t in ("title", "heading1", "heading2", "heading_candidate", "activity"):
            in_question = False
            in_instr = False
            in_refs = bool(REF_HEAD_RE.match(s))
        elif t == "body" and in_instr:
            in_instr = False
        types[i] = t

    # itens de uma mesma lista numerada automática são tratados de forma consistente:
    # se a maioria parece questão, todos viram questão
    groups = {}
    for i, f in enumerate(feats):
        if f["num_id"] and f["num_fmt"] == "decimal" and f["ilvl"] == "0" and types[i] in ("question", "list"):
            groups.setdefault(f["num_id"], []).append(i)
    for idxs in groups.values():
        q = sum(1 for i in idxs if types[i] == "question")
        if q and q * 2 >= len(idxs):
            for i in idxs:
                types[i] = "question"

    # níveis dos títulos detectados por aparência
    cand = [i for i, t in enumerate(types) if t == "heading_candidate"]
    if cand:
        cand_sizes = sorted({feats[i]["size"] for i in cand}, reverse=True)
        top = cand_sizes[0]
        for i in cand:
            f = feats[i]
            caps = _is_caps(f["stripped"])
            if len(cand_sizes) > 1:
                types[i] = "heading1" if f["size"] >= top - 0.25 else "heading2"
            else:
                types[i] = "heading1" if (caps or f["size"] > body_size + 0.5) else "heading2"

    items = []
    for i, p in enumerate(paras):
        items.append({"el": p, "type": types[i], "meta": meta[i], "index": i,
                      "text": feats[i]["stripped"], "jc": feats[i]["jc"]})

    summary = summarize(doc, items)
    summary["tamanho_corpo_original"] = body_size
    return items, summary


def summarize(doc, items):
    counts = Counter(it["type"] for it in items)
    body = doc.element.body
    media = media_counts(body)
    table_count = sum(1 for _ in iter_tables(body))
    warnings = []
    if media["caixas_texto"]:
        warnings.append(f"O documento tem {media['caixas_texto']} caixa(s) de texto. O conteúdo delas "
                        "será mantido, mas a formatação interna não será alterada.")
    if body.find(".//" + qn("w:ins")) is not None or body.find(".//" + qn("w:del")) is not None:
        warnings.append("O documento tem alterações controladas (revisões) pendentes. "
                        "Elas serão mantidas como estão.")
    if counts.get("student_info"):
        warnings.append("O documento já possui um campo de identificação do estudante no corpo do texto. "
                        "Se o modelo também incluir esse campo no cabeçalho, ele aparecerá duas vezes — "
                        "você pode desativá-lo nas configurações do cabeçalho.")
    headers = []
    for s in doc.sections:
        for part in (s.header, s.first_page_header, s.even_page_header,
                     s.footer, s.first_page_footer, s.even_page_footer):
            try:
                if part.is_linked_to_previous:
                    continue
                txt = " ".join(para_text(p) for p in part._element.iter(qn("w:p"))).strip()
            except Exception:
                continue
            if txt and txt not in headers:
                headers.append(txt)
    return {
        "contagem": {k: v for k, v in counts.items() if k != "empty"},
        "tabelas": table_count,
        "imagens": media["imagens"],
        "equacoes": media["equacoes"],
        "graficos": media["graficos"],
        "objetos": media["objetos"],
        "caixas_texto": media["caixas_texto"],
        "secoes": len(doc.sections),
        "cabecalhos_rodapes_originais": headers[:6],
        "avisos": warnings,
    }


def table_paragraph_elements(doc):
    out = []
    for tbl in iter_tables(doc.element.body):
        out.extend(table_paragraphs(tbl))
    return out


def structure_list(items, limit=600):
    """Lista resumida para exibir ao professor (e permitir correções de classificação)."""
    out = []
    for it in items:
        if it["type"] == "empty":
            continue
        text = it["text"]
        if not text:
            text = "[imagem]" if it["type"] == "image" else ("[equação]" if it["type"] == "equation" else "")
        out.append({"i": it["index"], "tipo": it["type"], "texto": text[:140]})
        if len(out) >= limit:
            break
    return out
