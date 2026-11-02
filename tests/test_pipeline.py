"""Teste completo pela API: envio, análise, padronização, prévia, confirmação e download.

Executar:  .venv\\Scripts\\python.exe tests\\test_pipeline.py
"""
import io
import os
import sys
import tempfile
import time
import urllib.parse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["PRUMO_DADOS"] = tempfile.mkdtemp(prefix="prumo_teste_")

import pymupdf as fitz  # noqa: E402
from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

DOCS = ROOT / "tests" / "documentos"
OUT = ROOT / "tests" / "saida"
OUT.mkdir(exist_ok=True)
c = TestClient(app)
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("OK   " if cond else "FALHA") + f" {name} {detail}")


def upload(fname):
    with open(DOCS / fname, "rb") as fh:
        return c.post("/api/documentos", files={"arquivo": (fname, fh)})


def full_flow(fname, template, saida="ambos", header=None, expect_types=None, ocr=None):
    t0 = time.time()
    r = upload(fname)
    check(f"{fname}: envio aceito", r.status_code == 200, r.text[:200] if r.status_code != 200 else "")
    job = r.json()
    if ocr is not None:
        check(f"{fname}: PDF digitalizado detectado", job["status"] == "aguardando_ocr", job["status"])
        r = c.post(f"/api/documentos/{job['id']}/pdf", json={"ocr": ocr})
        check(f"{fname}: conversão do PDF (ocr={ocr})", r.status_code == 200, r.text[:200])
        job = r.json()
        if ocr:
            rep = job["ocr_relatorio"]
            check(f"{fname}: qualidade do OCR informada", rep["ocr_qualidade"] is not None,
                  f"confiança={rep['ocr_qualidade']} duvidosas={rep['palavras_duvidosas']}")
    check(f"{fname}: analisado", job["status"] == "analisado", job.get("erro") or "")
    cont = job["analise"]["contagem"]
    print("      estrutura:", cont, "| tabelas", job["analise"]["tabelas"], "| imagens",
          job["analise"]["imagens"], "| equações", job["analise"]["equacoes"])
    for t, n in (expect_types or {}).items():
        check(f"{fname}: reconhece {t} >= {n}", cont.get(t, 0) >= n, f"encontrado {cont.get(t, 0)}")
    r = c.post(f"/api/documentos/{job['id']}/processar",
               json={"modelo": template, "saida": saida, "cabecalho": header or {}})
    check(f"{fname}: padronizado com '{template}'", r.status_code == 200, r.text[:300])
    job = r.json()
    ig = job["integridade"]
    check(f"{fname}: conteúdo preservado", ig["status"] == "preservado",
          f"palavras {ig['palavras_antes']}->{ig['palavras_depois']} pdf={ig.get('cobertura_pdf')}% "
          f"dif={ig['diferencas'][:3]} perdas={ig['midia_perdida']}")
    check(f"{fname}: mídia preservada", not ig["midia_perdida"], str(ig["midia_depois"]))
    r = c.get(f"/api/documentos/{job['id']}/previa/resultado/1")
    check(f"{fname}: prévia gerada", r.status_code == 200 and r.content[:4] == b"\x89PNG")
    r = c.get(f"/api/documentos/{job['id']}/previa/original/1")
    check(f"{fname}: prévia do original", r.status_code == 200)
    r = c.get(f"/api/documentos/{job['id']}/baixar/docx")
    check(f"{fname}: download bloqueado antes de confirmar", r.status_code == 400)
    r = c.post(f"/api/documentos/{job['id']}/confirmar")
    check(f"{fname}: confirmado", r.status_code == 200 and r.json()["status"] == "confirmado")
    stem = Path(fname).stem
    for fmt in (["docx", "pdf"] if saida == "ambos" else [saida]):
        r = c.get(f"/api/documentos/{job['id']}/baixar/{fmt}")
        ok = r.status_code == 200
        path = OUT / f"{stem}__{template}.{fmt}"
        if ok:
            path.write_bytes(r.content)
            if fmt == "docx":
                try:
                    d = Document(io.BytesIO(r.content))
                    ok = len(d.paragraphs) > 0
                except Exception as e:  # noqa: BLE001
                    ok = False
            else:
                with fitz.open(stream=r.content, filetype="pdf") as p:
                    ok = p.page_count > 0
        check(f"{fname}: arquivo {fmt.upper()} válido", ok, path.name)
    print(f"      tempo total {time.time() - t0:.1f}s")
    return job


# ----------------------------------------------------------------------------- testes
st = c.get("/api/status").json()
check("status: conversor LibreOffice disponível", st["conversor"])
check("status: OCR disponível", st["ocr"])
check("página inicial servida", c.get("/").status_code == 200
      and "Padronização de documentos".encode() in c.get("/").content)
st_tpl = c.get("/api/modelos/prova").json()["settings"]["header"]
check("modelo já vem com o Colégio Fleming e o logotipo",
      st_tpl["institution"] == "Colégio Fleming Porto Alegre" and st_tpl["logo"]
      and c.get(f"/api/logos/{st_tpl['logo']}").status_code == 200)

hdr = {"institution": "Escola Municipal Teste", "discipline": "Matemática", "teacher": "Prof. Ana",
       "class_name": "7º A", "date": "10/03/2026"}
j1 = full_flow("prova_baguncada.docx", "prova", header=hdr,
               expect_types={"question": 4, "alternative": 8, "title": 1, "instruction": 1, "equation": 1,
                             "image": 1, "student_info": 1})
full_flow("prova_baguncada.docx", "simulado")
full_flow("trabalho_academico.docx", "academico",
          expect_types={"title": 1, "heading1": 3, "heading2": 1, "reference": 2, "quote": 1, "caption": 2})
full_flow("lista_numerada.docx", "lista", saida="docx", expect_types={"question": 3})
full_flow("comunicado.odt", "comunicado", saida="pdf")
full_flow("comunicado.doc", "institucional")
full_flow("prova_texto.pdf", "prova", expect_types={"question": 3})
full_flow("prova_digitalizada.pdf", "prova", ocr=True)
full_flow("prova_digitalizada.pdf", "atividade", ocr=False)
full_flow("trabalho_academico.docx", "personalizado")

# arquivos inválidos
for fname, expect in (("falso.docx", 400), ("vazio.pdf", 400), ("planilha.xlsx", 400), ("grande.pdf", 400)):
    r = upload(fname)
    check(f"recusa arquivo inválido {fname}", r.status_code == expect, r.json().get("erro", ""))

# modelos: criar, editar, persistir, duplicar, restaurar, excluir
r = c.post("/api/modelos", json={"name": "Prova do 9º ano", "base": "prova"})
m = r.json()
check("modelo personalizado criado", r.status_code == 200 and m["id"].startswith("m_"))
s = m["settings"]
s["body"]["font"] = "Georgia"
s["body"]["size"] = 13
s["numbering"]["alternative_format"] = "a)"
s["numbering"]["question_format"] = "Questão 1 –"
s["numbering"]["renumber_questions"] = True
s["page"]["orientation"] = "landscape"
r = c.put(f"/api/modelos/{m['id']}", json={"name": "Prova do 9º ano", "settings": s})
check("modelo salvo", r.status_code == 200)
again = c.get(f"/api/modelos/{m['id']}").json()
check("configuração persistida", again["settings"]["body"]["font"] == "Georgia"
      and again["settings"]["page"]["orientation"] == "landscape")
job = full_flow("prova_baguncada.docx", m["id"])
labels = job["relatorio"]["rotulos_alterados"]
check("rótulos uniformizados e registrados", len(labels) >= 8, str(labels[:4]))
d = Document(OUT / f"prova_baguncada__{m['id']}.docx")
sec = d.sections[0]
check("orientação paisagem aplicada", sec.page_width > sec.page_height)
texts = [p.text for p in d.paragraphs]
check("alternativa 'A) 28' virou 'a) 28'", "a) 28" in texts, str([t for t in texts if "28" in t]))
check("questão renumerada 'Questão 1 – Resolva...'", any(t.startswith("Questão 1 – Resolva") for t in texts))
r = c.post(f"/api/modelos/{m['id']}/duplicar")
check("modelo duplicado", r.status_code == 200 and "cópia" in r.json()["name"])
r = c.post("/api/modelos/prova/restaurar")
check("restaurar modelo de exemplo", r.status_code == 200)
r = c.delete("/api/modelos/prova")
check("exemplo não pode ser excluído", r.status_code == 400)
r = c.delete(f"/api/modelos/{m['id']}")
check("modelo personalizado excluído", r.status_code == 200)
r = c.post("/api/modelos/prova/previa", json={"settings": c.get("/api/modelos/prova").json()["settings"]})
check("prévia de modelo", r.status_code == 200 and r.json()["paginas"] >= 1)

# lote: zip
hist = c.get("/api/historico").json()["itens"]
check("histórico registra documentos", len(hist) >= 10, f"{len(hist)} registros")
ids = ",".join(h["id"] for h in hist[:3])
r = c.get(f"/api/baixar-varios?ids={ids}&fmt=ambos")
ok = r.status_code == 200
if ok:
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        names = z.namelist()
    ok = len(names) >= 3
check("download de vários em .zip", ok, str(names[:4]) if ok else r.text[:200])
r = c.delete(f"/api/documentos/{hist[0]['id']}")
check("excluir registro do histórico", r.status_code == 200
      and all(h["id"] != hist[0]["id"] for h in c.get("/api/historico").json()["itens"]))

# correção manual de classificação
r = upload("prova_baguncada.docx")
jid = r.json()["id"]
first = next(it for it in r.json()["estrutura"] if it["tipo"] == "instruction")
r = c.post(f"/api/documentos/{jid}/processar", json={"modelo": "prova", "correcoes": {str(first["i"]): "heading1"}})
check("correção manual de tipo aplicada", r.status_code == 200 and r.json()["integridade"]["status"] == "preservado")

# perfis do Fleming: Prova e Lista de exercícios
PERFIS = {
    "prova": ({"tipo": "prova", "tipo_prova": "local", "disciplina": "Matemática", "professor": "Ana Souza",
               "serie": "1ª série"}, "1ª SÉRIE - PROVA LOCAL - MATEMÁTICA", 2),
    "lista": ({"tipo": "lista", "disciplina": "Química", "professor": "Carlos Lima", "serie": "2ª série",
               "conteudo": "Estequiometria", "tipo_questoes": "ENEM"},
              "2ª SÉRIE - LISTA DE EXERCÍCIOS - QUÍMICA - ESTEQUIOMETRIA - ENEM", 1),
}
for nome, (perfil, esperado, colunas) in PERFIS.items():
    jid = upload("prova_baguncada.docx").json()["id"]
    r = c.post(f"/api/documentos/{jid}/processar", json={"perfil": perfil, "saida": "ambos"})
    job = r.json()
    check(f"perfil {nome}: formatado e conteúdo preservado",
          r.status_code == 200 and job["integridade"]["status"] == "preservado", r.text[:200])
    c.post(f"/api/documentos/{jid}/confirmar")
    r = c.get(f"/api/documentos/{jid}/baixar/docx")
    nome_baixado = urllib.parse.unquote(r.headers.get("content-disposition", "").split("''")[-1])
    check(f"perfil {nome}: nome automático do arquivo", nome_baixado == f"{esperado}.docx", nome_baixado)
    d = Document(io.BytesIO(r.content))
    sec = d.sections[0]
    cols = sec._sectPr.find(qn("w:cols"))
    fonte = d.styles["Normal"].font
    check(f"perfil {nome}: Arial 12, espaçamento simples, {colunas} coluna(s)",
          fonte.name == "Arial" and fonte.size.pt == 12
          and d.styles["Prumo Corpo"].paragraph_format.line_spacing == 1.0
          and int(cols.get(qn("w:num"))) == colunas)
    hdr = " ".join(p.text for t in sec.first_page_header.tables for row in t.rows for cell in row.cells
                   for p in cell.paragraphs)
    check(f"perfil {nome}: cabeçalho com os dados e o logo", perfil["disciplina"] in hdr
          and perfil["professor"] in hdr and len(sec.first_page_header.part.package.image_parts) > 0)
    textos = [p.text for p in d.paragraphs]
    tem_grade = "GRADE DE RESPOSTAS" in textos
    check(f"perfil {nome}: grade de respostas {'presente' if nome == 'prova' else 'ausente'}",
          tem_grade == (nome == "prova") and (nome != "prova" or (
              len(d.sections) == 2 and d.sections[-1]._sectPr.find(qn("w:cols")).get(qn("w:num")) == "1"
              and any(c.text == "20" for c in d.tables[-1]._cells))))
    corpo = d.styles["Prumo Corpo"].paragraph_format.alignment
    check(f"perfil {nome}: texto justificado", corpo == 3 and all(
        d.styles[n].paragraph_format.alignment == 3 for n in ("Prumo Questão", "Prumo Alternativa", "Heading 1")))
    (OUT / f"{esperado}.docx").write_bytes(r.content)
r = c.post(f"/api/documentos/{jid}/processar", json={"perfil": {"tipo": "prova", "serie": "1ª série"}})
check("perfil incompleto é recusado com mensagem clara", r.status_code == 400, r.json().get("erro", ""))

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} verificações aprovadas")
for f in failed:
    print("  FALHA:", f[0], f[2])
sys.exit(1 if failed else 0)
