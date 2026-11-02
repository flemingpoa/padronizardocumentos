"""Perfis de formatação do Fleming: Prova e Lista de exercícios.

Cada perfil transforma as escolhas do professor (tipo, disciplina, série…) em um
conjunto completo de configurações para o motor de padronização, em um cabeçalho
institucional e no nome automático do arquivo final.
"""
import re

from .default_templates import INSTITUTION_NAME, base_settings, deep_merge
from .errors import UserError

TIPOS_PROVA = {"local": "Prova Local", "recuperacao": "Prova de Recuperação Semestral"}
SERIES = ["1ª série", "2ª série", "3ª série"]
DISCIPLINAS = ["Arte", "Biologia", "Educação Física", "Espanhol", "Filosofia", "Física",
               "Geografia", "História", "Inglês", "Língua Portuguesa", "Literatura",
               "Matemática", "Química", "Redação", "Sociologia"]
TIPOS_QUESTAO = ["ENEM", "Vestibulares", "ENEM e Vestibulares", "Autorais", "Olimpíadas"]


def opcoes():
    return {"tipos_prova": TIPOS_PROVA, "series": SERIES, "disciplinas": DISCIPLINAS,
            "tipos_questao": TIPOS_QUESTAO}


def _txt(v, campo, obrigatorio=True, limite=80):
    v = re.sub(r"\s+", " ", str(v or "")).strip()[:limite]
    if obrigatorio and not v:
        raise UserError(f"Preencha o campo “{campo}”.")
    return v


def validar(p):
    p = p or {}
    tipo = p.get("tipo")
    if tipo not in ("prova", "lista"):
        raise UserError("Escolha o tipo de material: Prova ou Lista de exercícios.")
    serie = p.get("serie")
    if serie not in SERIES:
        raise UserError("Escolha a série destinada.")
    out = {"tipo": tipo, "serie": serie,
           "disciplina": _txt(p.get("disciplina"), "Disciplina"),
           "professor": _txt(p.get("professor"), "Nome do professor(a)")}
    if tipo == "prova":
        if p.get("tipo_prova") not in TIPOS_PROVA:
            raise UserError("Escolha o tipo de prova.")
        out["tipo_prova"] = p["tipo_prova"]
    else:
        out["conteudo"] = _txt(p.get("conteudo"), "Conteúdo da lista", limite=100)
        out["tipo_questoes"] = _txt(p.get("tipo_questoes"), "Tipo de questões", limite=60)
    return out


def rotulo(p):
    return TIPOS_PROVA[p["tipo_prova"]] if p["tipo"] == "prova" else "Lista de Exercícios"


def nome_arquivo(p):
    """SÉRIE - TIPO DE PROVA - DISCIPLINA  ou
    SÉRIE - LISTA DE EXERCÍCIOS - DISCIPLINA - CONTEÚDO - TIPO DE QUESTÃO"""
    if p["tipo"] == "prova":
        partes = [p["serie"], TIPOS_PROVA[p["tipo_prova"]], p["disciplina"]]
    else:
        partes = [p["serie"], "Lista de Exercícios", p["disciplina"], p["conteudo"], p["tipo_questoes"]]
    nome = " - ".join(x.upper() for x in partes)
    nome = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", nome)  # caracteres proibidos em nomes de arquivo
    return re.sub(r"\s+", " ", nome).strip(" .")[:180]


def _info_cabecalho(p):
    linha1 = [p["disciplina"], p["serie"], f"Professor(a): {p['professor']}"]
    linhas = ["   •   ".join(linha1)]
    if p["tipo"] == "lista":
        linhas.append(f"Conteúdo: {p['conteudo']}   •   Questões: {p['tipo_questoes']}")
    if p["tipo"] == "prova":
        campos = [[("Nome", .64), ("Turma", .18), ("Nº", .18)], [("Data", .5), ("Nota", .5)]]
    else:
        campos = [[("Nome", .64), ("Turma", .18), ("Data", .18)]]
    return {"rotulo": INSTITUTION_NAME.upper(), "titulo": rotulo(p).upper(), "linhas": linhas,
            "resumo": f"{rotulo(p)}  •  {p['disciplina']}  •  {p['serie']}", "campos": campos}


# Todo o texto fica justificado. Só o título do documento e as legendas de figuras
# ficam centralizados (como as próprias imagens).
_ESTILOS = {
    "title": {"size": 12, "bold": True, "align": "center", "space_before": 0, "space_after": 6},
    "heading1": {"size": 12, "bold": True, "align": "justify", "space_before": 8, "space_after": 4},
    "heading2": {"size": 12, "bold": True, "align": "justify", "space_before": 6, "space_after": 3},
    "activity": {"size": 12, "bold": True, "align": "justify", "space_before": 8, "space_after": 4},
    "instruction": {"size": 11, "align": "justify", "space_after": 3},
    "question": {"size": 12, "align": "justify", "space_before": 10, "space_after": 4},
    "alternative": {"size": 12, "align": "justify", "space_before": 0, "space_after": 2},
    "quote": {"size": 11, "align": "justify", "left_indent": 1.0, "line_spacing": 1.0, "space_after": 6},
    "caption": {"size": 10, "align": "center", "space_before": 2, "space_after": 6},
    "reference": {"size": 11, "align": "justify", "line_spacing": 1.0, "space_after": 4},
}

# Provas (local e recuperação semestral) têm sempre 20 questões objetivas
GRADE_QUESTOES = 20
GRADE_ALTERNATIVAS = "ABCDE"


def settings(p):
    """Configurações completas do motor para o perfil escolhido."""
    prova = p["tipo"] == "prova"
    estilos = {k: dict(v) for k, v in _ESTILOS.items()}
    if not prova:
        estilos["question"]["space_before"] = 12
    s = deep_merge(base_settings(), {
        "page": {"size": "A4", "orientation": "portrait", "columns": 2 if prova else 1,
                 "margin_top": 1.5, "margin_bottom": 1.5, "margin_left": 1.5 if prova else 2.0,
                 "margin_right": 1.5 if prova else 2.0, "header_distance": 0.7,
                 "footer_distance": 0.8},
        # Arial 12, espaçamento simples
        "body": {"font": "Arial", "size": 12, "color": "#000000", "line_spacing": 1.0,
                 "align": "justify", "first_line_indent": 0, "space_before": 0, "space_after": 4,
                 "preserve_centered": False},
        "answer_sheet": {"questoes": GRADE_QUESTOES, "alternativas": GRADE_ALTERNATIVAS} if prova else None,
        "styles": estilos,
        "questions": {"label_bold": True, "alternative_indent": 0.4, "alternative_hanging": 0,
                      "keep_together": True},
        "header": {"mode": "replace", "style": "fleming", "fleming": _info_cabecalho(p),
                   "student_field": True, "first_page_only": True, "font_size": 9},
        "footer": {"mode": "replace", "text": "", "align": "center", "font_size": 8.5},
        "images": {"max_width": 100, "center": True},
        "tables": {"font_size": 10, "full_width": True, "center": True, "borders": "keep",
                   "repeat_header": True},
        "numbering": {"page_numbers": True, "page_position": "footer", "page_align": "center",
                      "page_format": "Página {n} de {t}", "page_start": 1,
                      "renumber_questions": False, "question_format": "keep",
                      "alternative_format": "keep"},
    })
    return s
