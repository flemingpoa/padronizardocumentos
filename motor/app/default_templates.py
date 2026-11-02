"""Modelos de padronização de exemplo (editáveis pelo professor)."""
import copy

FONTS = ["Arial", "Calibri", "Times New Roman", "Verdana", "Tahoma", "Georgia", "Cambria",
         "Segoe UI", "Century Gothic", "Trebuchet MS", "Garamond", "Book Antiqua",
         "Courier New", "Comic Sans MS"]

# Identidade do Colégio Fleming usada por padrão no cabeçalho dos documentos
INSTITUTION_NAME = "Colégio Fleming Porto Alegre"
FLEMING_LOGO_ID = "f1e3a1c0f1e3a1c0f1e3a1c0f1e3a1c0"

PAPER_SIZES = {
    "A4": (21.0, 29.7),
    "Carta": (21.59, 27.94),
    "Ofício": (21.59, 35.56),
    "A5": (14.8, 21.0),
    "A3": (29.7, 42.0),
}


def _style(**kw):
    base = {"font": "", "size": 12, "color": "", "bold": False, "italic": False,
            "underline": False, "caps": False, "align": "left", "space_before": 0,
            "space_after": 6, "line_spacing": None, "left_indent": 0.0, "first_line_indent": 0.0}
    base.update(kw)
    return base


def base_settings():
    """Todas as opções existentes, com valores neutros."""
    return {
        "page": {"size": "A4", "orientation": "portrait", "columns": 1, "margin_top": 2.0, "margin_bottom": 2.0,
                 "margin_left": 2.0, "margin_right": 2.0, "header_distance": 1.0,
                 "footer_distance": 1.0},
        "body": {"font": "Arial", "size": 12, "color": "#000000", "bold": False, "italic": False,
                 "underline": False, "align": "justify", "first_line_indent": 0.0,
                 "left_indent": 0.0, "right_indent": 0.0, "line_spacing": 1.15,
                 "space_before": 0, "space_after": 6, "keep_emphasis": True,
                 "standardize_color": True, "preserve_centered": True, "collapse_empty": False},
        "styles": {
            "title": _style(size=14, bold=True, align="center", space_before=0, space_after=12),
            "heading1": _style(size=13, bold=True, space_before=12, space_after=6),
            "heading2": _style(size=12, bold=True, space_before=10, space_after=4),
            "activity": _style(size=12, bold=True, space_before=12, space_after=6),
            "instruction": _style(size=11, italic=False, align="justify", space_after=4),
            "question": _style(size=12, align="justify", space_before=12, space_after=6),
            "alternative": _style(size=12, space_before=0, space_after=3),
            "quote": _style(size=10, align="justify", left_indent=4.0, line_spacing=1.0,
                            space_before=6, space_after=12),
            "caption": _style(size=10, align="center", space_before=3, space_after=9),
            "reference": _style(size=12, align="left", line_spacing=1.0, space_after=12),
        },
        "questions": {"label_bold": True, "alternative_indent": 0.6, "alternative_hanging": 0.0,
                      "keep_together": True},
        "header": {"mode": "replace", "institution": INSTITUTION_NAME, "discipline": "", "teacher": "",
                   "class_name": "", "date": "", "extra": "", "logo": FLEMING_LOGO_ID, "logo_height": 1.1,
                   "align": "center", "font_size": 10, "border_bottom": True,
                   "student_field": False,
                   "student_fields": {"name": True, "number": True, "class": True, "date": True,
                                      "grade": False},
                   "first_page_only": True},
        "footer": {"mode": "replace", "text": "", "align": "center", "font_size": 9},
        "images": {"max_width": 100, "center": True},
        "tables": {"font_size": 10, "full_width": False, "center": True, "borders": "keep",
                   "header_bold": False, "repeat_header": True},
        "numbering": {"page_numbers": True, "page_position": "footer", "page_align": "center",
                      "page_format": "Página {n} de {t}", "page_start": 1,
                      "renumber_questions": False, "question_format": "keep",
                      "alternative_format": "keep"},
    }


def deep_merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _tpl(tid, name, category, description, icon, changes):
    return {"id": tid, "name": name, "category": category, "description": description,
            "icon": icon, "builtin": True,
            "settings": deep_merge(base_settings(), changes)}


def builtin_templates():
    return [
        _tpl("prova", "Avaliações e provas", "Avaliações",
             "Cabeçalho institucional, campo do estudante, questões destacadas e alternativas alinhadas.",
             "prova",
             {"header": {"student_field": True},
              "body": {"line_spacing": 1.15, "space_after": 4},
              "styles": {"question": {"space_before": 14}}}),
        _tpl("lista", "Listas de exercícios", "Exercícios",
             "Disciplina em destaque, questões numeradas e mais espaço para resolução.",
             "lista",
             {"header": {"student_field": True,
                         "student_fields": {"name": True, "number": False, "class": True,
                                            "date": True, "grade": False}},
              "body": {"line_spacing": 1.3},
              "styles": {"question": {"space_before": 24}, "title": {"size": 15}}}),
        _tpl("atividade", "Atividades pedagógicas", "Atividades",
             "Visual leve e espaçado, ideal para atividades de sala e tarefas de casa.",
             "atividade",
             {"header": {"student_field": True,
                         "student_fields": {"name": True, "number": False, "class": True,
                                            "date": True, "grade": False}},
              "body": {"font": "Verdana", "size": 12, "line_spacing": 1.5, "align": "left"},
              "styles": {"question": {"space_before": 18, "align": "left"},
                         "title": {"size": 16}}}),
        _tpl("simulado", "Simulados", "Avaliações",
             "Margens compactas, numeração sequencial, paginação e rodapé institucional.",
             "simulado",
             {"page": {"margin_top": 1.5, "margin_bottom": 1.5, "margin_left": 1.5,
                       "margin_right": 1.5},
              "body": {"size": 11, "line_spacing": 1.0, "space_after": 3},
              "styles": {"question": {"size": 11, "space_before": 10},
                         "alternative": {"size": 11, "space_after": 2}},
              "header": {"student_field": True,
                         "student_fields": {"name": True, "number": True, "class": True,
                                            "date": False, "grade": False}},
              "footer": {"text": "Simulado — leia com atenção e marque apenas uma alternativa."},
              "numbering": {"renumber_questions": True}}),
        _tpl("academico", "Trabalhos acadêmicos", "Acadêmico",
             "Inspirado na ABNT: margens 3/2 cm, espaçamento 1,5, recuo de 1,25 cm e títulos hierarquizados.",
             "academico",
             {"page": {"margin_top": 3.0, "margin_left": 3.0, "margin_bottom": 2.0,
                       "margin_right": 2.0},
              "body": {"font": "Times New Roman", "line_spacing": 1.5, "first_line_indent": 1.25,
                       "space_after": 0},
              "styles": {"title": {"size": 14, "caps": True, "space_after": 18},
                         "heading1": {"size": 12, "caps": True, "space_before": 18,
                                      "space_after": 12},
                         "heading2": {"size": 12, "space_before": 12, "space_after": 12},
                         "question": {"space_before": 6}},
              # ABNT: sem cabeçalho institucional nas páginas (a instituição vai na capa)
              "header": {"mode": "replace", "border_bottom": False, "institution": "",
                         "logo": None},
              "numbering": {"page_position": "header", "page_align": "right", "page_format": "{n}"},
              "questions": {"label_bold": False}}),
        _tpl("institucional", "Documentos institucionais", "Institucional",
             "Projetos, planos e regimentos com títulos claros e texto justificado.",
             "institucional",
             {"body": {"line_spacing": 1.5, "first_line_indent": 1.25, "space_after": 6},
              "styles": {"heading1": {"caps": True}},
              "footer": {"text": ""}}),
        _tpl("comunicado", "Comunicados escolares", "Comunicação",
             "Bilhetes e comunicados às famílias com cabeçalho da escola e leitura confortável.",
             "comunicado",
             {"body": {"size": 12, "line_spacing": 1.5, "first_line_indent": 1.25,
                       "space_after": 8},
              "styles": {"title": {"size": 16}},
              "header": {"font_size": 11},
              "numbering": {"page_numbers": False}}),
        _tpl("personalizado", "Personalizado", "Personalizados",
             "Ponto de partida neutro para você definir todas as regras do seu jeito.",
             "personalizado", {}),
    ]


BUILTIN_IDS = {t["id"] for t in builtin_templates()}
