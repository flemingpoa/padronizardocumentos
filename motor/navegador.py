"""Ponte entre a página (JavaScript) e o motor de padronização, rodando no navegador (Pyodide).

Tudo acontece no computador do professor: o documento não é enviado a nenhum servidor.
"""
import base64
import io
import json
import zipfile

from docx import Document

from app import analyzer, formatter, integrity, perfis, render_html
from app.errors import UserError

LIMITE_BYTES = 25 * 1024 * 1024
LIMITE_DESCOMPACTADO = 300 * 1024 * 1024


def _bytes(data):
    """O JavaScript entrega um Uint8Array (JsProxy); no Python vira bytes."""
    return data.to_bytes() if hasattr(data, "to_bytes") else bytes(data)


def _validar(data):
    if len(data) == 0:
        raise UserError("O arquivo está vazio.")
    if len(data) > LIMITE_BYTES:
        raise UserError("O arquivo é maior que o limite de 25 MB.")
    if not data[:2] == b"PK":
        raise UserError("Este arquivo não é um documento do Word (.docx) válido. "
                        "Abra-o no Word e use “Salvar como” → Documento do Word (.docx).")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            nomes = {i.filename for i in infos}
            if "word/document.xml" not in nomes:
                raise UserError("Este arquivo não é um documento do Word (.docx) válido.")
            if sum(i.file_size for i in infos) > LIMITE_DESCOMPACTADO or len(infos) > 5000:
                raise UserError("O documento tem uma estrutura interna suspeita e foi recusado.")
            if any(n.lower().endswith("vbaproject.bin") for n in nomes):
                raise UserError("O documento contém macros. Salve-o como .docx comum e envie novamente.")
    except zipfile.BadZipFile:
        raise UserError("O arquivo está danificado ou não é um documento do Word (.docx).")
    try:
        return Document(io.BytesIO(data))
    except Exception:
        raise UserError("O documento não pôde ser lido. Verifique se ele abre normalmente no Word.")


def _resposta(fn):
    """Devolve sempre JSON: {"ok": ...} ou {"erro": mensagem amigável}."""
    try:
        return json.dumps({"ok": fn()}, ensure_ascii=False)
    except UserError as e:
        return json.dumps({"erro": e.message}, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"erro": "Não foi possível processar este documento. Verifique se ele abre "
                                   "normalmente no Word.", "detalhe": repr(e)[:300]}, ensure_ascii=False)


def analisar(data):
    """Leitura inicial: confere o arquivo e resume a estrutura encontrada."""
    def run():
        doc = _validar(_bytes(data))
        _, resumo = analyzer.analyze(doc)
        return {"analise": resumo}
    return _resposta(run)


def formatar(data, perfil_json):
    """Aplica o perfil (Prova ou Lista) e devolve o DOCX, a página para prévia/PDF e a conferência."""
    def run():
        perfil = perfis.validar(json.loads(perfil_json))
        s = perfis.settings(perfil)
        doc = _validar(_bytes(data))
        antes = integrity.snapshot(doc)
        itens, _ = analyzer.analyze(doc)
        relatorio = formatter.apply(doc, itens, s)
        saida = io.BytesIO()
        doc.save(saida)
        docx_bytes = saida.getvalue()
        final = Document(io.BytesIO(docx_bytes))
        depois = integrity.snapshot(final)
        extra = relatorio.get("palavras_grade") or 0
        if extra:  # a grade de respostas acrescentada não faz parte do conteúdo original
            depois["palavras"] = depois["palavras"][:-extra]
            depois["midia"]["tabelas"] -= 1
        conferencia = integrity.compare(antes, depois)
        nome = perfis.nome_arquivo(perfil)
        html, avisos = render_html.render(final, s, nome)
        return {"docx": base64.b64encode(docx_bytes).decode(), "html": html, "nome": nome,
                "integridade": conferencia, "relatorio": relatorio, "avisos": avisos}
    return _resposta(run)
