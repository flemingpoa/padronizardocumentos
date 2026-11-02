"""Funções auxiliares para ler a estrutura XML de documentos DOCX."""
from docx.oxml.ns import qn

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
V_NS = "urn:schemas-microsoft-com:vml"
O_NS = "urn:schemas-microsoft-com:office:office"

T_P = qn("w:p")
T_R = qn("w:r")
T_T = qn("w:t")
T_TAB = qn("w:tab")
T_BR = qn("w:br")
T_CR = qn("w:cr")
T_TBL = qn("w:tbl")
T_SDT = qn("w:sdt")
T_SDTCONTENT = qn("w:sdtContent")
T_TXBX = qn("w:txbxContent")
T_DEL = qn("w:del")
T_MOVEFROM = qn("w:moveFrom")
T_PPR = qn("w:pPr")
T_RPR = qn("w:rPr")
T_OMATH = f"{{{M_NS}}}oMath"
T_DRAWING = qn("w:drawing")
T_PICT = qn("w:pict")
T_OBJECT = qn("w:object")
T_NOBREAK_HYPHEN = qn("w:noBreakHyphen")
T_SOFT_HYPHEN = qn("w:softHyphen")

_SKIP_SUBTREES = {T_TXBX, T_DEL, T_MOVEFROM, T_PPR, T_RPR}


def iter_runs(p_el):
    """Runs (w:r) do parágrafo, na ordem, ignorando caixas de texto e texto excluído."""
    stack = list(reversed(list(p_el)))
    while stack:
        el = stack.pop()
        if el.tag in _SKIP_SUBTREES:
            continue
        if el.tag == T_R:
            yield el
            continue
        if el.tag == T_OMATH or el.tag == f"{{{M_NS}}}oMathPara":
            continue
        stack.extend(reversed(list(el)))


def run_text(r_el):
    parts = []
    for ch in r_el:
        if ch.tag == T_T:
            parts.append(ch.text or "")
        elif ch.tag == T_TAB:
            parts.append("\t")
        elif ch.tag in (T_BR, T_CR):
            parts.append("\n")
        elif ch.tag == T_NOBREAK_HYPHEN:
            parts.append("-")
    return "".join(parts)


def para_text(p_el):
    return "".join(run_text(r) for r in iter_runs(p_el))


def iter_block_paragraphs(container):
    """Parágrafos de nível superior do corpo (inclui controles de conteúdo), sem os de tabelas."""
    for child in container.iterchildren():
        tag = child.tag
        if tag == T_P:
            yield child
        elif tag in (T_SDT, qn("w:customXml")):
            content = child.find(T_SDTCONTENT) if tag == T_SDT else child
            if content is not None:
                yield from iter_block_paragraphs(content)


def iter_tables(container):
    """Tabelas de nível superior do corpo."""
    for child in container.iterchildren():
        if child.tag == T_TBL:
            yield child
        elif child.tag == T_SDT:
            content = child.find(T_SDTCONTENT)
            if content is not None:
                yield from iter_tables(content)


def table_paragraphs(tbl_el):
    """Todos os parágrafos de uma tabela (inclusive tabelas aninhadas), sem caixas de texto."""
    return [p for p in tbl_el.iter(T_P) if not is_inside(p, T_TXBX)]


def is_inside(el, tag):
    p = el.getparent()
    while p is not None:
        if p.tag == tag:
            return True
        p = p.getparent()
    return False


def body_text_words(body_el):
    """Palavras do corpo do documento (sem cabeçalhos/rodapés), para conferência de integridade."""
    words = []
    for p in body_el.iter(T_P):
        txt = "".join(run_text(r) for r in iter_runs(p))
        # inclui texto de caixas de texto separadamente (não são alteradas, mas são conferidas)
        words.extend(txt.split())
    return words


def media_counts(root_el):
    """Contagem de elementos que não podem se perder: imagens, tabelas, equações, gráficos etc."""
    blips = len(root_el.findall(f".//{{{A_NS}}}blip"))
    vml_imgs = len(root_el.findall(f".//{{{V_NS}}}imagedata"))
    return {
        "imagens": blips + vml_imgs,
        "tabelas": len(root_el.findall(".//" + T_TBL)),
        "equacoes": len(root_el.findall(f".//{T_OMATH}")),
        "graficos": len(root_el.findall(f".//{{{C_NS}}}chart")),
        "objetos": len(root_el.findall(f".//{{{O_NS}}}OLEObject")),
        "caixas_texto": len(root_el.findall(".//" + T_TXBX)),
    }
