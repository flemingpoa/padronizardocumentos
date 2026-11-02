"""Gera documentos de teste com diferentes níveis de complexidade."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf as fitz  # noqa: E402
from docx import Document  # noqa: E402
from docx.enum.section import WD_ORIENT, WD_SECTION  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK  # noqa: E402
from docx.oxml import OxmlElement, parse_xml  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt, RGBColor  # noqa: E402

from app import converters  # noqa: E402
from app.sample import OMML, chart_png  # noqa: E402

OUT = Path(__file__).resolve().parent / "documentos"
OUT.mkdir(exist_ok=True)


def run(par, text, size=None, bold=None, italic=None, font=None, color=None, sup=False):
    r = par.add_run(text)
    if size:
        r.font.size = Pt(size)
    if bold is not None:
        r.font.bold = bold
    if italic is not None:
        r.font.italic = italic
    if font:
        r.font.name = font
    if color:
        r.font.color.rgb = RGBColor.from_string(color)
    if sup:
        r.font.superscript = True
    return r


def prova_baguncada():
    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = Cm(1)
    sec.right_margin = Cm(4)
    sec.header.paragraphs[0].text = "Cabeçalho antigo da escola — 2025"
    p = doc.add_paragraph()
    run(p, "Nome: ______________________________ Nº ____ Turma: ______", 10)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run(p, "PROVA DE MATEMÁTICA – 1º TRIMESTRE", 18, True, font="Impact", color="1F4E79")
    p = doc.add_paragraph()
    run(p, "Instruções: ", 9, True, font="Courier New")
    run(p, "responda a lápis; não use calculadora; questões sem cálculo não serão consideradas.", 9,
        font="Courier New")
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Cm(3)
    p.paragraph_format.space_after = Pt(30)
    run(p, "QUESTÃO 01 - ", 14, True, font="Georgia")
    run(p, "Resolva a expressão e marque a alternativa correta: 2", 14, font="Georgia")
    run(p, "3", 14, font="Georgia", sup=True)
    run(p, " + 4 × 5.", 14, font="Georgia")
    for alt in ("A) 28", "B) 40", "C) 30", "D) 52"):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(5)
        run(p, alt, 8, font="Tahoma", color="FF0000")
    p = doc.add_paragraph()
    run(p, "Questão 2) Observe a figura e responda: quantas barras ultrapassam 150 unidades?", 11,
        font="Calibri")
    doc.add_paragraph().add_run().add_picture(chart_png(), width=Cm(22))  # maior que a página
    for alt in ("(a) uma", "(b) duas", "(c) três", "(d) quatro"):
        p = doc.add_paragraph()
        run(p, alt, 11, font="Calibri")
    p = doc.add_paragraph()
    run(p, "3. Calcule as raízes usando a fórmula abaixo e ", 12)
    run(p, "justifique", 12, italic=True)
    run(p, " cada passo.", 12)
    eq = doc.add_paragraph()
    eq._p.append(parse_xml(OMML))
    for _ in range(4):
        doc.add_paragraph()  # espaço para a resposta
    p = doc.add_paragraph()
    run(p, "4) Complete a tabela:", 12, True)
    t = doc.add_table(rows=3, cols=3)
    t.style = "Table Grid"
    data = [("x", "2x", "x²"), ("1", "", ""), ("3", "", "")]
    for i, row in enumerate(data):
        for j, val in enumerate(row):
            t.cell(i, j).text = val
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "D9E2F3")
    t.cell(0, 0)._tc.get_or_add_tcPr().append(shd)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run(p, "Boa prova!", 12, True)
    doc.save(OUT / "prova_baguncada.docx")


def trabalho_academico():
    doc = Document()
    doc.add_heading("O Ciclo da Água e a Educação Ambiental", 0)
    doc.add_heading("1 Introdução", 1)
    for _ in range(3):
        doc.add_paragraph(
            "A água é um recurso natural essencial à vida no planeta. Seu ciclo envolve processos "
            "de evaporação, condensação, precipitação e infiltração, que se repetem continuamente "
            "e garantem a renovação desse recurso em diferentes ambientes.")
    doc.add_heading("1.1 Objetivos", 2)
    doc.add_paragraph("Compreender o ciclo hidrológico.", style="List Bullet")
    doc.add_paragraph("Relacionar o ciclo à preservação ambiental.", style="List Bullet")
    q = doc.add_paragraph(
        "A educação ambiental deve ser entendida como um processo permanente, no qual os indivíduos "
        "e a comunidade tomam consciência do seu meio ambiente e adquirem conhecimentos, valores e "
        "habilidades que os tornem aptos a agir na solução de problemas ambientais (DIAS, 2004, p. 523).")
    q.paragraph_format.left_indent = Cm(4)
    doc.add_heading("2 Desenvolvimento", 1)
    p = doc.add_paragraph("Os dados coletados estão na Tabela 1.")
    doc.add_paragraph("Tabela 1 – Precipitação média anual")
    t = doc.add_table(rows=3, cols=3)
    t.style = "Light Grid Accent 1"
    t.cell(0, 0).merge(t.cell(0, 1)).text = "Região (mesclada)"
    t.cell(0, 2).text = "mm/ano"
    t.cell(1, 0).text = "Norte"
    t.cell(1, 1).text = "Amazonas"
    t.cell(1, 2).text = "2300"
    t.cell(2, 0).text = "Nordeste"
    t.cell(2, 1).text = "Ceará"
    t.cell(2, 2).text = "800"
    doc.add_paragraph("Fonte: dados fictícios para teste.")
    # seção em paisagem
    new = doc.add_section(WD_SECTION.NEW_PAGE)
    new.orientation = WD_ORIENT.LANDSCAPE
    new.page_width, new.page_height = new.page_height, new.page_width
    doc.add_heading("3 Considerações finais", 1)
    doc.add_paragraph("O estudo do ciclo da água contribui para a formação de cidadãos conscientes.")
    doc.add_heading("Referências", 1)
    doc.add_paragraph("DIAS, G. F. Educação ambiental: princípios e práticas. 9. ed. São Paulo: Gaia, 2004.")
    doc.add_paragraph("TUNDISI, J. G. Água no século XXI. São Carlos: RiMa, 2003.")
    doc.save(OUT / "trabalho_academico.docx")


def lista_numerada():
    doc = Document()
    p = doc.add_paragraph()
    run(p, "Lista de Exercícios – Frações", 16, True)
    for txt in ("Simplifique a fração 12/18 e explique o procedimento utilizado.",
                "Qual é o resultado de 3/4 + 1/2? Mostre os cálculos.",
                "Uma pizza foi dividida em 8 pedaços e João comeu 3. Que fração sobrou?"):
        doc.add_paragraph(txt, style="List Number")
        doc.add_paragraph()
    doc.save(OUT / "lista_numerada.docx")


def comunicado():
    doc = Document()
    p = doc.add_paragraph()
    run(p, "COMUNICADO AOS PAIS E RESPONSÁVEIS", 14, True)
    doc.add_paragraph("Prezadas famílias,")
    doc.add_paragraph("Informamos que no dia 20 de março não haverá aula devido à reunião pedagógica. "
                      "As atividades serão retomadas normalmente no dia seguinte.")
    doc.add_paragraph("Atenciosamente,")
    p = doc.add_paragraph("A Direção")
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    src = OUT / "_comunicado_tmp.docx"
    doc.save(src)
    converters.convert(src, "pdf", OUT / "_ignore.pdf")  # aquece o conversor
    # ODT e DOC são gerados pelo LibreOffice
    import shutil, subprocess, tempfile
    for ext, flt in (("odt", "odt"), ("doc", 'doc:MS Word 97')):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(src, Path(tmp) / "c.docx")
            subprocess.run([converters.SOFFICE, "--headless", f"-env:UserInstallation={converters._PROFILE_DIR.as_uri()}",
                            "--convert-to", flt, "--outdir", tmp, str(Path(tmp) / "c.docx")],
                           capture_output=True, timeout=120)
            shutil.copy(Path(tmp) / f"c.{ext}", OUT / f"comunicado.{ext}")
    src.unlink()
    (OUT / "_ignore.pdf").unlink()


def pdfs():
    converters.convert(OUT / "prova_baguncada.docx", "pdf", OUT / "prova_texto.pdf")
    # PDF "digitalizado": cada página vira apenas uma imagem
    src = fitz.open(OUT / "prova_texto.pdf")
    out = fitz.open()
    for page in src:
        pix = page.get_pixmap(dpi=200)
        np = out.new_page(width=page.rect.width, height=page.rect.height)
        np.insert_image(np.rect, pixmap=pix)
    out.save(OUT / "prova_digitalizada.pdf")


def invalidos():
    (OUT / "falso.docx").write_text("isto não é um documento do word", encoding="utf-8")
    (OUT / "vazio.pdf").write_bytes(b"")
    (OUT / "planilha.xlsx").write_bytes(b"PK\x03\x04qualquer")
    (OUT / "grande.pdf").write_bytes(b"%PDF-1.4\n" + b"0" * (26 * 1024 * 1024))


if __name__ == "__main__":
    prova_baguncada()
    trabalho_academico()
    lista_numerada()
    comunicado()
    pdfs()
    invalidos()
    for f in sorted(OUT.iterdir()):
        print(f.name, f.stat().st_size)
