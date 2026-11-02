// Utilitários de interface: escape de texto, ícones, avisos, janelas e chamadas à API.

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[c]));

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const P = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
export const icons = {
  upload: P('<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>'),
  file: P('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>'),
  plus: P('<path d="M12 5v14M5 12h14"/>'),
  x: P('<path d="M6 6l12 12M18 6L6 18"/>'),
  swap: P('<path d="M7 7h11l-3-3M17 17H6l3 3"/>'),
  sliders: P('<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>'),
  layers: P('<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>'),
  clock: P('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
  help: P('<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7M12 17h.01"/>'),
  download: P('<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 20h16"/>'),
  check: P('<path d="M5 12l5 5 9-10"/>'),
  eye: P('<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
  edit: P('<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13 7l4 4"/>'),
  copy: P('<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>'),
  trash: P('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>'),
  reset: P('<path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.5"/><path d="M4 4v4.5h4.5"/>'),
  save: P('<path d="M5 4h11l3 3v13H5z"/><path d="M8 4v5h7V4M8 20v-6h8v6"/>'),
  back: P('<path d="M15 6l-6 6 6 6"/>'),
  next: P('<path d="M9 6l6 6-6 6"/>'),
  zoomIn: P('<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4M11 8v6M8 11h6"/>'),
  zoomOut: P('<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4M8 11h6"/>'),
  columns: P('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/>'),
  shield: P('<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>'),
  alert: P('<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>'),
  // ícones dos modelos
  prova: P('<path d="M9 4h6v3H9z"/><path d="M15 5h2a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2"/><path d="M8.5 13l2 2 4-4"/>'),
  lista: P('<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6h1M4 12h1M4 18h1"/>'),
  atividade: P('<path d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8L3.5 9.2l5.9-.9z"/>'),
  simulado: P('<rect x="4" y="3" width="16" height="18" rx="2"/><circle cx="9" cy="8" r="1.3"/><circle cx="9" cy="12" r="1.3"/><circle cx="9" cy="16" r="1.3"/><path d="M13 8h4M13 12h4M13 16h4"/>'),
  academico: P('<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c0 1.5 2.7 3 6 3s6-1.5 6-3v-5"/>'),
  institucional: P('<path d="M3 21h18M5 21V10M19 21V10M9 21V10M15 21V10M2 10l10-6 10 6z"/>'),
  comunicado: P('<path d="M4 5h16v11H8l-4 4z"/><path d="M8 9h8M8 12h5"/>'),
  personalizado: P('<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>'),
};

export function fmtBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} MB`;
}

export function fmtDate(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

export function toast(msg, kind = '') {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), kind === 'err' ? 7000 : 4000);
}

// Janela modal acessível. `content` é HTML já escapado.
export function modal({ title, body, actions = [], narrow = false, onClose }) {
  const root = $('#modal-root');
  const prev = document.activeElement;
  const wrap = document.createElement('div');
  wrap.className = 'modal-backdrop';
  wrap.innerHTML = `
    <div class="modal ${narrow ? 'narrow' : ''}" role="dialog" aria-modal="true" aria-labelledby="mtitle">
      <div class="modal-head"><h2 id="mtitle">${esc(title)}</h2>
        <button class="btn btn-ghost icon-btn" data-close aria-label="Fechar">${icons.x}</button></div>
      <div class="modal-body">${body}</div>
      ${actions.length ? '<div class="modal-foot"></div>' : ''}
    </div>`;
  const close = (val) => {
    wrap.remove();
    document.removeEventListener('keydown', onKey);
    prev?.focus?.();
    onClose?.(val);
  };
  const onKey = (e) => { if (e.key === 'Escape') close(null); };
  document.addEventListener('keydown', onKey);
  wrap.addEventListener('click', (e) => { if (e.target === wrap || e.target.closest('[data-close]')) close(null); });
  const foot = $('.modal-foot', wrap);
  actions.forEach((a) => {
    const b = document.createElement('button');
    b.className = `btn ${a.cls || ''}`;
    b.textContent = a.label;
    b.addEventListener('click', () => (a.onClick ? a.onClick(close) : close(a.value)));
    foot.appendChild(b);
  });
  root.appendChild(wrap);
  ($('[autofocus]', wrap) || $('.modal-foot .btn:last-child', wrap) || $('[data-close]', wrap)).focus();
  return { el: wrap, close };
}

export function confirmDialog(title, text, okLabel = 'Confirmar', danger = false) {
  return new Promise((resolve) => {
    modal({
      title, narrow: true, body: `<p>${esc(text)}</p>`,
      actions: [
        { label: 'Cancelar', value: false, cls: 'btn-ghost' },
        { label: okLabel, value: true, cls: danger ? 'btn-danger' : 'btn-primary' },
      ],
      onClose: (v) => resolve(!!v),
    });
  });
}

// ------------------------------------------------------------------ API

export class ApiError extends Error {}

export async function api(path, { method = 'GET', body, form } = {}) {
  const opts = { method, headers: {}, credentials: 'same-origin' };
  if (form) opts.body = form;
  else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(`/api${path}`, opts);
  } catch {
    throw new ApiError('Sem conexão com o servidor. Verifique se a plataforma está em execução.');
  }
  let data = null;
  try { data = await res.json(); } catch { /* resposta sem JSON */ }
  if (!res.ok) {
    if (data?.login) window.dispatchEvent(new CustomEvent('prumo:login'));
    throw new ApiError(data?.erro || `Erro ${res.status}`);
  }
  return data;
}

// Envio com barra de progresso (fetch não informa o progresso do upload)
export function uploadFile(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/documentos');
    xhr.responseType = 'json';
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
    xhr.upload.onload = () => onProgress(1, true);
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response);
      else {
        if (xhr.response?.login) window.dispatchEvent(new CustomEvent('prumo:login'));
        reject(new ApiError(xhr.response?.erro || `Erro ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new ApiError('Falha de conexão durante o envio.'));
    const fd = new FormData();
    fd.append('arquivo', file);
    xhr.send(fd);
  });
}

export const store = {
  get(k, d = null) { try { const v = localStorage.getItem(`prumo.${k}`); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(`prumo.${k}`, JSON.stringify(v)); } catch { /* sem armazenamento */ } },
};

export const TYPE_LABELS = {};
export function setTypeLabels(t) { Object.assign(TYPE_LABELS, t); }

export const STATUS = {};
export function setStatus(s) { Object.assign(STATUS, s); }
