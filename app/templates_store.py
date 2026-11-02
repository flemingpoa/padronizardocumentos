"""Armazenamento persistente dos modelos de padronização (arquivo JSON)."""
import copy
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from .config import LOGOS_DIR, TEMPLATES_FILE
from .default_templates import (FLEMING_LOGO_ID, FONTS, PAPER_SIZES, base_settings,
                                builtin_templates, deep_merge)
from .errors import UserError

_lock = threading.Lock()

ALIGNS = {"left", "center", "right", "justify"}


def _ensure_default_logo():
    """Coloca o logotipo do Fleming (que acompanha o projeto) entre os logotipos disponíveis."""
    dest = LOGOS_DIR / f"{FLEMING_LOGO_ID}.png"
    src = Path(__file__).resolve().parent / "assets" / "logo-fleming.png"
    if not dest.exists() and src.exists():
        shutil.copyfile(src, dest)


_ensure_default_logo()


def _read():
    if TEMPLATES_FILE.exists():
        try:
            return json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"templates": {}, "ordem": []}


def _write(data):
    tmp = TEMPLATES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, TEMPLATES_FILE)


def _num(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def sanitize_settings(s):
    """Completa opções ausentes e limita valores a faixas seguras."""
    s = deep_merge(base_settings(), s or {})
    pg = s["page"]
    if pg["size"] not in PAPER_SIZES:
        pg["size"] = "A4"
    pg["orientation"] = "landscape" if pg.get("orientation") == "landscape" else "portrait"
    for k in ("margin_top", "margin_bottom", "margin_left", "margin_right"):
        pg[k] = _num(pg[k], 0.3, 6, 2.0)
    for k in ("header_distance", "footer_distance"):
        pg[k] = _num(pg[k], 0, 5, 1.0)
    pg["columns"] = int(_num(pg.get("columns"), 1, 3, 1))
    b = s["body"]
    b["font"] = str(b.get("font") or "Arial")[:60]
    b["size"] = _num(b["size"], 6, 36, 12)
    b["line_spacing"] = _num(b["line_spacing"], 0.8, 3, 1.15)
    for k in ("space_before", "space_after"):
        b[k] = _num(b[k], 0, 72, 0)
    for k in ("first_line_indent", "left_indent", "right_indent"):
        b[k] = _num(b[k], -3, 8, 0)
    if b["align"] not in ALIGNS:
        b["align"] = "justify"
    for key, st in s["styles"].items():
        st["size"] = _num(st.get("size"), 6, 48, 12)
        st["space_before"] = _num(st.get("space_before"), 0, 96, 0)
        st["space_after"] = _num(st.get("space_after"), 0, 96, 0)
        st["left_indent"] = _num(st.get("left_indent"), -3, 10, 0)
        st["first_line_indent"] = _num(st.get("first_line_indent"), -3, 8, 0)
        if st.get("line_spacing") not in (None, ""):
            st["line_spacing"] = _num(st["line_spacing"], 0.8, 3, 1.15)
        else:
            st["line_spacing"] = None
        if st.get("align") not in ALIGNS:
            st["align"] = "left"
        st["font"] = str(st.get("font") or "")[:60]
    q = s["questions"]
    q["alternative_indent"] = _num(q["alternative_indent"], 0, 5, 0.6)
    q["alternative_hanging"] = _num(q["alternative_hanging"], 0, 3, 0)
    h = s["header"]
    if h["mode"] not in ("replace", "keep", "remove"):
        h["mode"] = "replace"
    for k in ("institution", "discipline", "teacher", "class_name", "date", "extra"):
        h[k] = str(h.get(k) or "")[:200]
    h["font_size"] = _num(h["font_size"], 6, 20, 10)
    h["logo_height"] = _num(h["logo_height"], 0.5, 4, 1.6)
    if h.get("logo") and not (LOGOS_DIR / f"{h['logo']}.png").exists():
        h["logo"] = None
    f = s["footer"]
    if f["mode"] not in ("replace", "keep", "remove"):
        f["mode"] = "replace"
    f["text"] = str(f.get("text") or "")[:300]
    f["font_size"] = _num(f["font_size"], 6, 16, 9)
    s["images"]["max_width"] = _num(s["images"]["max_width"], 10, 100, 100)
    s["tables"]["font_size"] = _num(s["tables"]["font_size"], 6, 20, 10)
    if s["tables"]["borders"] not in ("keep", "all"):
        s["tables"]["borders"] = "keep"
    n = s["numbering"]
    n["page_start"] = int(_num(n["page_start"], 1, 9999, 1))
    n["page_format"] = str(n.get("page_format") or "{n}")[:60]
    return s


def _builtin_map():
    return {t["id"]: t for t in builtin_templates()}


def list_templates():
    with _lock:
        data = _read()
    builtins = _builtin_map()
    out = []
    for tid, t in builtins.items():
        stored = data["templates"].get(tid)
        tpl = copy.deepcopy(stored) if stored else copy.deepcopy(t)
        tpl["builtin"] = True
        tpl["modified"] = bool(stored)
        tpl["settings"] = sanitize_settings(tpl["settings"])
        out.append(tpl)
    customs = [t for tid, t in data["templates"].items() if tid not in builtins]
    customs.sort(key=lambda t: t.get("created", 0))
    for t in customs:
        t = copy.deepcopy(t)
        t["builtin"] = False
        t["settings"] = sanitize_settings(t["settings"])
        out.append(t)
    return out


def get_template(tid):
    for t in list_templates():
        if t["id"] == tid:
            return t
    raise UserError("Modelo não encontrado.", 404)


def _clean_meta(payload, current=None):
    name = str(payload.get("name") or (current or {}).get("name") or "Novo modelo").strip()[:80]
    return {
        "name": name or "Novo modelo",
        "category": str(payload.get("category") or (current or {}).get("category")
                        or "Personalizados").strip()[:50],
        "description": str(payload.get("description") if payload.get("description") is not None
                           else (current or {}).get("description", "")).strip()[:240],
        "icon": str(payload.get("icon") or (current or {}).get("icon") or "personalizado")[:30],
    }


def save_template(tid, payload):
    current = get_template(tid)
    meta = _clean_meta(payload, current)
    settings = sanitize_settings(payload.get("settings", current["settings"]))
    with _lock:
        data = _read()
        stored = data["templates"].get(tid) or {"id": tid, "created": time.time()}
        stored.update(meta)
        stored["settings"] = settings
        stored["updated"] = time.time()
        data["templates"][tid] = stored
        _write(data)
    return get_template(tid)


def create_template(payload, base_id=None):
    base = get_template(base_id) if base_id else None
    settings = payload.get("settings") or (base["settings"] if base else base_settings())
    meta = _clean_meta(payload, base)
    if base and not payload.get("name"):
        meta["name"] = f"{base['name']} (cópia)"[:80]
    if base and not payload.get("category"):
        meta["category"] = "Personalizados" if base.get("builtin") else base.get("category")
    tid = "m_" + uuid.uuid4().hex[:10]
    rec = {"id": tid, **meta, "settings": sanitize_settings(settings), "created": time.time(),
           "updated": time.time(), "origin": base_id or "personalizado"}
    with _lock:
        data = _read()
        data["templates"][tid] = rec
        _write(data)
    return get_template(tid)


def delete_template(tid):
    if tid in _builtin_map():
        raise UserError("Os modelos de exemplo não podem ser excluídos, apenas restaurados.")
    with _lock:
        data = _read()
        if tid not in data["templates"]:
            raise UserError("Modelo não encontrado.", 404)
        data["templates"].pop(tid)
        _write(data)


def reset_template(tid):
    """Restaura as configurações de fábrica (exemplos) ou as do modelo de origem (personalizados)."""
    builtins = _builtin_map()
    with _lock:
        data = _read()
        if tid in builtins:
            data["templates"].pop(tid, None)
        else:
            rec = data["templates"].get(tid)
            if not rec:
                raise UserError("Modelo não encontrado.", 404)
            origin = rec.get("origin")
            src = builtins.get(origin) or builtins["personalizado"]
            rec["settings"] = copy.deepcopy(src["settings"])
            rec["updated"] = time.time()
        _write(data)
    return get_template(tid)


def meta_options():
    return {"fontes": FONTS, "papeis": list(PAPER_SIZES.keys())}
