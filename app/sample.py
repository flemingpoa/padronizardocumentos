"""Documento de exemplo usado na prévia dos modelos (e nos testes)."""
import io
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.shared import Cm, Pt, RGBColor
from PIL import Image, ImageDraw

from .config import DATA_DIR

SAMPLE_PATH = DATA_DIR / "exemplo_modelo.docx"

OMML = ('<m:oMathPara xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
        '<m:oMath><m:r><m:t>x=</m:t></m:r><m:f><m:num><m:r><m:t>-b±</m:t></m:r><m:rad>'
        '<m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e><m:sSup><m:e><m:r><m:t>b</m:t>'
        '</m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup><m:r><m:t>-4ac</m:t></m:r>'
        '</m:e></m:rad></m:num><m:den><m:r><m:t>2a</m:t></m:r></m:den></m:f></m:oMath>'
        '</m:oMathPara>')


def chart_png():
    img = Image.new("RGB", (600, 300), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 599, 299], outline=(150, 150, 150))
    vals = [120, 200, 90, 240, 160]
    for i, v in enumerate(vals):
        x = 60 + i * 105
        d.rectangle([x, 270 - v, x + 60, 270], fill=(31, 58, 95))
    d.line([40, 270, 580, 270], fill=(0, 0, 0), width=2)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


def build_sample(path: Path):
    doc = Document()
    def p(text, size=11, bold=False, align=None, font="Calibri", color=None):
        par = doc.add_paragraph()
        r = par.add_run(text)
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.name = font
        if color:
            r.font.color.rgb = RGBColor.from_string(color)
        if align:
            par.alignment = align
        return par

    p("Avaliação de Ciências – 2º Bimestre", 16, True, WD_ALIGN_PARAGRAPH.CENTER, "Times New Roman")
    p("Instruções: leia cada questão com atenção. Utilize caneta azul ou preta. "
      "Não é permitido o uso de corretivo.", 10, False, None, "Verdana")
    p("PARTE I – QUESTÕES OBJETIVAS", 12, True)
    p("1) Observe o gráfico abaixo, que mostra a quantidade de chuva em cinco meses. "
      "Em qual mês choveu mais?", 11)
    doc.add_paragraph().add_run().add_picture(chart_png(), width=Cm(12))
    p("Figura 1 – Chuva mensal (mm).", 9)
    for alt in ("a) Janeiro.", "b) Fevereiro.", "c) Março.", "d) Abril.", "e) Maio."):
        p(alt, 11, font="Comic Sans MS")
    p("2. A fórmula de Bhaskara é usada para encontrar as raízes de uma equação do 2º grau:", 12,
      font="Arial")
    eq = doc.add_paragraph()
    eq._p.append(parse_xml(OMML))
    for alt in ("(A) Apenas quando a > 0.", "(B) Para qualquer equação do 2º grau.",
                "(C) Somente para equações do 1º grau.", "(D) Apenas quando b = 0."):
        p(alt, 12, font="Arial")
    p("Questão 3 – Complete a tabela com o estado físico da água em cada temperatura.", 11,
      color="C00000")
    t = doc.add_table(rows=3, cols=2)
    t.style = "Table Grid"
    for i, (a, b) in enumerate((("Temperatura", "Estado físico"), ("-5 °C", ""), ("25 °C", ""))):
        t.cell(i, 0).text = a
        t.cell(i, 1).text = b
    p("")
    p("PARTE II – QUESTÕES DISCURSIVAS", 12, True)
    p("4) Explique, com suas palavras, o que é o ciclo da água e por que ele é importante "
      "para os seres vivos.", 11)
    doc.save(path)
    return path


def ensure_sample():
    if not SAMPLE_PATH.exists():
        build_sample(SAMPLE_PATH)
    return SAMPLE_PATH
