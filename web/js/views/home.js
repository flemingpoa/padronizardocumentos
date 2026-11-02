// Fluxo principal: enviar → escolher modelo → conferir prévia → baixar.
import {
  $, $$, api, confirmDialog, esc, fmtBytes, icons, STATUS, store, toast, TYPE_LABELS, uploadFile,
} from '../util.js';

const ACCEPT = ['docx', 'doc', 'odt', 'pdf'];
const HEADER_FIELDS = [
  ['institution', 'Instituição'], ['discipline', 'Disciplina'], ['teacher', 'Professor(a)'],
  ['class_name', 'Turma'], ['date', 'Data'], ['extra', 'Texto adicional'],
];

const state = {
  files: [],
  step: 1,
  templateId: store.get('ultimoModelo', 'prova'),
  output: store.get('ultimaSaida', 'ambos'),
  header: null,
  headerTouched: false,
  active: 0,
  compare: false,
  zoom: 1,
  corrections: {},
  restored: false,
  processing: null,
};
let templates = [];
let root = null;
let keySeq = 0;

// ------------------------------------------------------------------ sessão (sobrevive a recarregar a página)
function saveSession() {
  try {
    sessionStorage.setItem('prumo.sessao', JSON.stringify({
      jobs: state.files.filter((f) => f.job?.id).map((f) => f.job.id),
      step: state.step === 'processing' ? 2 : state.step,
      templateId: state.templateId, output: state.output, header: state.header,
      headerTouched: state.headerTouched, corrections: state.corrections, active: state.active,
    }));
  } catch { /* sem armazenamento */ }
}

async function restoreSession() {
  state.restored = true;
  let s = null;
  try { s = JSON.parse(sessionStorage.getItem('prumo.sessao') || 'null'); } catch { s = null; }
  if (!s?.jobs?.length) return;
  Object.assign(state, {
    templateId: s.templateId || state.templateId, output: s.output || state.output, header: s.header,
    headerTouched: !!s.headerTouched, corrections: s.corrections || {}, active: s.active || 0,
  });
  const loaded = await Promise.all(s.jobs.map((id) => api(`/documentos/${id}`).catch(() => null)));
  state.files = loaded.filter(Boolean).map((job) => fileFromJob(job));
  state.step = state.files.length ? (s.step || 1) : 1;
  if (state.step >= 3 && !processedFiles().length) state.step = 2;
  if (state.step === 4 && !processedFiles().every((f) => f.job.status === 'confirmado')) state.step = 3;
}

function fileFromJob(job) {
  return {
    key: ++keySeq, name: job.nome, size: job.tamanho, ext: job.formato, job,
    status: job.status === 'erro' ? 'erro' : (job.status === 'aguardando_ocr' ? 'ocr' : 'pronto'),
    error: job.erro,
  };
}

const readyFiles = () => state.files.filter((f) => f.status === 'pronto');
const processedFiles = () => state.files.filter((f) => ['processado', 'confirmado'].includes(f.job?.status));
const busy = () => state.files.some((f) => ['enviando', 'analisando', 'convertendo'].includes(f.status));

// ------------------------------------------------------------------ textos auxiliares
const plural = (n, s, p) => `${n} ${n === 1 ? s : p}`;

function summaryChips(job) {
  const a = job?.analise;
  if (!a) return '';
  const c = a.contagem || {};
  const chips = [];
  if (c.title) chips.push(plural(c.title, 'título', 'títulos'));
  const sec = (c.heading1 || 0) + (c.heading2 || 0) + (c.activity || 0);
  if (sec) chips.push(plural(sec, 'seção/subtítulo', 'seções/subtítulos'));
  if (c.question) chips.push(plural(c.question, 'questão', 'questões'));
  if (c.alternative) chips.push(plural(c.alternative, 'alternativa', 'alternativas'));
  if (c.body) chips.push(plural(c.body, 'parágrafo', 'parágrafos'));
  if (c.list) chips.push(plural(c.list, 'item de lista', 'itens de lista'));
  if (a.tabelas) chips.push(plural(a.tabelas, 'tabela', 'tabelas'));
  if (a.imagens) chips.push(plural(a.imagens, 'imagem', 'imagens'));
  if (a.equacoes) chips.push(plural(a.equacoes, 'equação', 'equações'));
  if (a.graficos) chips.push(plural(a.graficos, 'gráfico', 'gráficos'));
  return `<div class="chips" aria-label="Estrutura reconhecida">${chips.map((t) => `<span class="chip">${esc(t)}</span>`).join('')}</div>`;
}

function notesFor(job) {
  const notes = [...(job?.avisos || []), ...((job?.analise?.avisos) || [])];
  const hdr = job?.analise?.cabecalhos_rodapes_originais || [];
  if (hdr.length) {
    notes.push(`O documento tem cabeçalho/rodapé próprio (“${hdr[0].slice(0, 80)}”). `
      + 'Se o modelo usar cabeçalho/rodapé padronizado, ele será substituído.');
  }
  return notes;
}

function statusBadge(f) {
  switch (f.status) {
    case 'enviando': return `<span class="badge gray">Enviando ${Math.round((f.progress || 0) * 100)}%</span>`;
    case 'analisando': return '<span class="badge gray">Analisando estrutura…</span>';
    case 'convertendo': return '<span class="badge gray">Convertendo PDF…</span>';
    case 'ocr': return '<span class="badge warn">Precisa de uma decisão</span>';
    case 'erro': return '<span class="badge err">Não foi possível ler</span>';
    default: return '<span class="badge ok">Pronto</span>';
  }
}

// ------------------------------------------------------------------ renderização
export async function renderHome(main, { reset = false } = {}) {
  root = main;
  if (reset) {
    state.files = []; state.step = 1; state.corrections = {}; state.active = 0;
    saveSession();
    history.replaceState(null, '', '#/');
  }
  if (!state.restored) await restoreSession();
  try {
    templates = (await api('/modelos')).modelos;
  } catch (e) { toast(e.message, 'err'); }
  if (!templates.find((t) => t.id === state.templateId)) state.templateId = templates[0]?.id;
  if (!state.header || !state.headerTouched) loadHeaderFromTemplate();
  render();
  return () => { root = null; };
}

function loadHeaderFromTemplate() {
  const t = templates.find((x) => x.id === state.templateId);
  if (!t) return;
  state.header = Object.fromEntries(HEADER_FIELDS.map(([k]) => [k, t.settings.header[k] || '']));
}

function render() {
  if (!root) return;
  const steps = ['Enviar arquivos', 'Escolher modelo', 'Conferir prévia', 'Baixar'];
  const cur = state.step === 'processing' ? 2 : state.step;
  const maxReach = processedFiles().length ? (processedFiles().every((f) => f.job.status === 'confirmado') ? 4 : 3)
    : (readyFiles().length ? 2 : 1);
  root.innerHTML = `
    <div class="page-head">
      <div><h1>Padronizar documentos</h1>
      <p>Envie o arquivo, escolha o padrão e baixe pronto. O conteúdo do seu documento não é alterado.</p></div>
    </div>
    <nav class="quick" aria-label="Acesso rápido">
      <a href="#/novo">${icons.plus}Novo documento</a>
      <a href="#/modelos">${icons.layers}Meus modelos</a>
      <a href="#/modelos/${esc(state.templateId || 'prova')}">${icons.sliders}Configurações de formatação</a>
      <a href="#/historico">${icons.clock}Histórico</a>
      <a href="#/ajuda">${icons.help}Ajuda e orientações</a>
    </nav>
    <ol class="stepper">
      ${steps.map((s, i) => {
    const n = i + 1;
    const cls = n === cur ? 'current' : (n < cur ? 'done' : '');
    const inner = `<span class="num">${n < cur ? '✓' : n}</span><span class="lbl">${s}</span>`;
    const can = n !== cur && n <= maxReach && state.step !== 'processing';
    return `<li class="${cls}" ${n === cur ? 'aria-current="step"' : ''}>${can ? `<button data-goto="${n}">${inner}</button>` : inner}</li>`;
  }).join('')}
    </ol>
    <div id="panel"></div>`;
  const panel = $('#panel', root);
  if (state.step === 1) renderUpload(panel);
  else if (state.step === 2) renderChoose(panel);
  else if (state.step === 'processing') renderProcessing(panel);
  else if (state.step === 3) renderPreview(panel);
  else renderDone(panel);
  $$('[data-goto]', root).forEach((b) => b.addEventListener('click', () => go(Number(b.dataset.goto))));
}

function go(step) {
  state.step = step;
  saveSession();
  render();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ------------------------------------------------------------------ etapa 1
function fileRow(f) {
  const ext = (f.ext || '').toLowerCase();
  const notes = f.job ? notesFor(f.job) : [];
  let extra = '';
  if (['enviando', 'analisando', 'convertendo'].includes(f.status)) {
    extra = `<div class="progress ${f.status === 'enviando' ? '' : 'indeterminate'}"><span data-bar></span></div>`;
  } else if (f.status === 'erro') {
    extra = `<div class="notice err mt-s">${esc(f.error || 'Erro ao ler o arquivo.')}</div>`;
  } else if (f.status === 'ocr') {
    const pages = f.job?.pdf_info?.paginas_digitalizadas || [];
    extra = `
      <div class="notice warn">
        <strong>Este PDF é digitalizado (${plural(pages.length, 'página', 'páginas')} em forma de imagem).</strong>
        Um PDF digitalizado é como uma foto do papel: não tem texto editável. A plataforma pode
        <b>reconhecer o texto (OCR)</b> e criar um documento editável novo — mas o reconhecimento pode ter
        erros e o resultado <b>precisa ser conferido</b>. As palavras duvidosas ficam destacadas em amarelo.
        ${STATUS.ocr ? '' : '<br><b>O reconhecimento de texto não está instalado neste servidor.</b>'}
        <div class="btn-row">
          ${STATUS.ocr ? `<button class="btn btn-sm btn-primary" data-ocr="${f.key}">Reconhecer texto (OCR)</button>` : ''}
          <button class="btn btn-sm" data-noocr="${f.key}">Manter páginas como imagem</button>
        </div>
      </div>`;
  } else if (f.job) {
    extra = summaryChips(f.job);
    if (notes.length) {
      extra += `<details class="more"><summary>${plural(notes.length, 'observação', 'observações')} sobre este arquivo</summary>
        <ul>${notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul></details>`;
    }
  }
  return `
    <li class="file" data-key="${f.key}">
      <div class="file-top">
        <div class="file-type ${esc(ext)}" aria-hidden="true">${esc(ext.toUpperCase())}</div>
        <div class="file-info">
          <div class="file-name" title="${esc(f.name)}">${esc(f.name)}</div>
          <div class="file-meta"><span>${esc(ext.toUpperCase())} · ${fmtBytes(f.size || 0)}</span><span data-status>${statusBadge(f)}</span></div>
        </div>
        <div class="file-actions">
          <button class="btn btn-sm btn-ghost" data-replace="${f.key}" ${busy() ? 'disabled' : ''} title="Substituir arquivo">${icons.swap}<span>Substituir</span></button>
          <button class="btn btn-sm btn-ghost icon-btn" data-remove="${f.key}" ${f.status === 'enviando' ? 'disabled' : ''} aria-label="Remover ${esc(f.name)}" title="Remover">${icons.x}</button>
        </div>
      </div>
      ${extra}
    </li>`;
}

function renderUpload(panel) {
  const max = STATUS.max_arquivos || 10;
  panel.innerHTML = `
    <section class="card card-pad" aria-labelledby="t1">
      <div class="card-head"><div><h2 id="t1">Envie seus documentos</h2>
        <p class="muted small" id="dz-help">Formatos aceitos: Word (DOCX e DOC), OpenDocument (ODT) e PDF.
        Até ${STATUS.tamanho_max_mb || 25} MB por arquivo e ${max} arquivos por vez — o mesmo padrão será aplicado a todos.</p></div></div>
      <div class="dropzone" id="dz" role="button" tabindex="0" aria-describedby="dz-help">
        <div class="dz-icon">${icons.upload}</div>
        <strong>Arraste os arquivos para cá</strong>
        <span class="muted">ou <u>clique para escolher no computador</u></span>
        <div class="formats"><span class="badge gray">DOCX</span><span class="badge gray">DOC</span><span class="badge gray">ODT</span><span class="badge gray">PDF</span></div>
      </div>
      <input type="file" id="file-input" class="sr-only" multiple accept=".docx,.doc,.odt,.pdf" tabindex="-1" aria-hidden="true">
      <input type="file" id="replace-input" class="sr-only" accept=".docx,.doc,.odt,.pdf" tabindex="-1" aria-hidden="true">
      <ul class="files" id="files">${state.files.map(fileRow).join('')}</ul>
      <div class="btn-row end mt">
        <span class="muted small" aria-live="polite">${state.files.length ? plural(readyFiles().length, 'arquivo pronto', 'arquivos prontos') : ''}</span>
        <button class="btn btn-primary btn-lg" id="to-step2" ${readyFiles().length && !busy() ? '' : 'disabled'}>
          Escolher modelo ${icons.next}</button>
      </div>
    </section>`;
  const dz = $('#dz', panel);
  const input = $('#file-input', panel);
  dz.addEventListener('click', () => input.click());
  dz.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
  ['dragenter', 'dragover'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('drag'); }));
  dz.addEventListener('drop', (e) => addFiles([...e.dataTransfer.files]));
  input.addEventListener('change', () => { addFiles([...input.files]); input.value = ''; });
  $('#to-step2', panel).addEventListener('click', () => go(2));
  bindFileActions(panel);
}

function bindFileActions(panel) {
  $$('[data-remove]', panel).forEach((b) => b.addEventListener('click', () => removeFile(Number(b.dataset.remove))));
  const rep = $('#replace-input', panel);
  $$('[data-replace]', panel).forEach((b) => b.addEventListener('click', () => {
    rep.dataset.key = b.dataset.replace;
    rep.click();
  }));
  rep?.addEventListener('change', () => {
    const file = rep.files[0];
    rep.value = '';
    if (file) replaceFile(Number(rep.dataset.key), file);
  });
  $$('[data-ocr]', panel).forEach((b) => b.addEventListener('click', () => convertPdf(Number(b.dataset.ocr), true)));
  $$('[data-noocr]', panel).forEach((b) => b.addEventListener('click', () => convertPdf(Number(b.dataset.noocr), false)));
}

function validateLocal(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  if (!ACCEPT.includes(ext)) return `“${file.name}”: formato não aceito. Use DOCX, DOC, ODT ou PDF.`;
  if (file.size > (STATUS.tamanho_max_mb || 25) * 1024 * 1024) return `“${file.name}” passa do limite de ${STATUS.tamanho_max_mb || 25} MB.`;
  if (file.size === 0) return `“${file.name}” está vazio.`;
  return null;
}

function addFiles(list) {
  const max = STATUS.max_arquivos || 10;
  for (const file of list) {
    if (state.files.length >= max) { toast(`Envie no máximo ${max} arquivos por vez.`, 'err'); break; }
    const err = validateLocal(file);
    if (err) { toast(err, 'err'); continue; }
    const f = { key: ++keySeq, name: file.name, size: file.size, ext: file.name.split('.').pop().toLowerCase(), status: 'enviando', progress: 0 };
    state.files.push(f);
    sendFile(f, file);
  }
  render();
}

async function sendFile(f, file) {
  try {
    const job = await uploadFile(file, (p, done) => {
      f.progress = p;
      if (done) f.status = 'analisando';
      updateRow(f);
    });
    f.job = job;
    f.status = job.status === 'erro' ? 'erro' : (job.status === 'aguardando_ocr' ? 'ocr' : 'pronto');
    f.error = job.erro;
  } catch (e) {
    f.status = 'erro';
    f.error = e.message;
  }
  saveSession();
  if (state.step === 1) render();
}

function updateRow(f) {
  const row = root && $(`[data-key="${f.key}"]`, root);
  if (!row) return;
  const st = $('[data-status]', row);
  if (st) st.innerHTML = statusBadge(f);
  const bar = $('[data-bar]', row);
  if (bar && f.status === 'enviando') bar.style.width = `${Math.round(f.progress * 100)}%`;
  if (f.status === 'analisando') bar?.parentElement.classList.add('indeterminate');
}

async function removeFile(key) {
  const f = state.files.find((x) => x.key === key);
  if (!f) return;
  state.files = state.files.filter((x) => x.key !== key);
  if (f.job?.id) api(`/documentos/${f.job.id}`, { method: 'DELETE' }).catch(() => {});
  saveSession();
  render();
}

async function replaceFile(key, file) {
  const err = validateLocal(file);
  if (err) { toast(err, 'err'); return; }
  const idx = state.files.findIndex((x) => x.key === key);
  if (idx < 0) return;
  const old = state.files[idx];
  if (old.job?.id) api(`/documentos/${old.job.id}`, { method: 'DELETE' }).catch(() => {});
  const f = { key: ++keySeq, name: file.name, size: file.size, ext: file.name.split('.').pop().toLowerCase(), status: 'enviando', progress: 0 };
  state.files[idx] = f;
  render();
  sendFile(f, file);
}

async function convertPdf(key, ocr) {
  const f = state.files.find((x) => x.key === key);
  if (!f) return;
  f.status = 'convertendo';
  render();
  try {
    f.job = await api(`/documentos/${f.job.id}/pdf`, { method: 'POST', body: { ocr, destacar: true } });
    f.status = 'pronto';
    toast(ocr ? 'Texto reconhecido. Confira o resultado na prévia.' : 'PDF preparado.', 'ok');
  } catch (e) {
    f.status = 'ocr';
    toast(e.message, 'err');
  }
  saveSession();
  render();
}

// ------------------------------------------------------------------ etapa 2
function renderChoose(panel) {
  const tpl = templates.find((t) => t.id === state.templateId);
  const n = readyFiles().length;
  const headerMode = tpl?.settings.header.mode;
  panel.innerHTML = `
    <section class="card card-pad stack" aria-labelledby="t2">
      <div class="card-head"><div><h2 id="t2">Escolha o modelo de padronização</h2>
        <p class="muted small">O mesmo modelo será aplicado ${n > 1 ? `aos ${n} arquivos` : 'ao arquivo'}. Os modelos de exemplo podem ser editados.</p></div></div>
      <div class="tpl-grid" role="radiogroup" aria-label="Modelos de padronização">
        ${templates.map((t) => `
          <button type="button" class="tpl" role="radio" aria-checked="${t.id === state.templateId}" data-tpl="${esc(t.id)}">
            <span class="check" aria-hidden="true"></span>
            <span class="tpl-icon">${icons[t.icon] || icons.personalizado}</span>
            <h3>${esc(t.name)}</h3>
            <p>${esc(t.description || '')}</p>
            <span class="tpl-tags"><span class="badge gray">${esc(t.category)}</span>${t.builtin ? '<span class="badge">Exemplo editável</span>' : ''}</span>
          </button>`).join('')}
      </div>

      <div>
        <span class="field-label" id="out-l">Formato do arquivo final</span>
        <div class="segmented" role="radiogroup" aria-labelledby="out-l">
          ${[['docx', 'Word editável (DOCX)'], ['pdf', 'PDF para impressão'], ['ambos', 'Os dois']].map(([v, l]) => `
            <label><input type="radio" name="saida" value="${v}" ${state.output === v ? 'checked' : ''}><span>${l}</span></label>`).join('')}
        </div>
      </div>

      <details class="card card-pad" ${state.headerTouched ? 'open' : ''} id="hdr-box">
        <summary><b>Dados do cabeçalho deste documento</b> <span class="muted small">— opcional: turma, data, disciplina…</span></summary>
        ${headerMode !== 'replace' ? '<div class="notice info mt-s">Este modelo mantém ou remove o cabeçalho do documento, então estes dados não serão usados. Você pode mudar isso em “Ajustar configurações”.</div>' : ''}
        <div class="form-grid mt" id="hdr-fields">
          ${HEADER_FIELDS.map(([k, l]) => `<label class="field"><span>${l}</span><input class="input" data-h="${k}" value="${esc(state.header?.[k] || '')}" maxlength="200"></label>`).join('')}
        </div>
        <p class="muted small">Esses dados valem só para esta padronização. Para salvar como padrão, edite o modelo.</p>
      </details>

      <div class="btn-row">
        <button class="btn" id="back1">${icons.back}Voltar</button>
        <a class="btn btn-ghost" href="#/modelos/${esc(state.templateId)}?voltar=1">${icons.sliders}Ajustar configurações do modelo</a>
        <span class="spacer"></span>
        <button class="btn btn-primary btn-lg" id="run" ${n && tpl ? '' : 'disabled'}>Padronizar ${n > 1 ? `${n} documentos` : 'documento'}</button>
      </div>
    </section>`;
  $$('[data-tpl]', panel).forEach((b) => b.addEventListener('click', () => {
    state.templateId = b.dataset.tpl;
    store.set('ultimoModelo', state.templateId);
    if (!state.headerTouched) loadHeaderFromTemplate();
    saveSession();
    renderChoose(panel);
    $(`[data-tpl="${CSS.escape(state.templateId)}"]`, panel)?.focus();
  }));
  // navegação por setas no grupo de modelos
  $('.tpl-grid', panel).addEventListener('keydown', (e) => {
    const items = $$('[data-tpl]', panel);
    const i = items.indexOf(document.activeElement);
    if (i < 0) return;
    if (['ArrowRight', 'ArrowDown'].includes(e.key)) { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    if (['ArrowLeft', 'ArrowUp'].includes(e.key)) { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
  });
  $$('input[name="saida"]', panel).forEach((r) => r.addEventListener('change', () => {
    state.output = r.value;
    store.set('ultimaSaida', r.value);
    saveSession();
  }));
  $$('[data-h]', panel).forEach((inp) => inp.addEventListener('input', () => {
    state.header[inp.dataset.h] = inp.value;
    state.headerTouched = true;
    saveSession();
  }));
  $('#back1', panel).addEventListener('click', () => go(1));
  $('#run', panel).addEventListener('click', runAll);
}

async function runAll() {
  const targets = readyFiles();
  if (!targets.length) return;
  state.step = 'processing';
  state.processing = targets.map((f) => ({ key: f.key, name: f.name, st: 'wait' }));
  render();
  let ok = 0;
  for (const p of state.processing) {
    const f = state.files.find((x) => x.key === p.key);
    p.st = 'run';
    renderProcessingList();
    try {
      f.job = await api(`/documentos/${f.job.id}/processar`, {
        method: 'POST',
        body: { modelo: state.templateId, saida: state.output, cabecalho: state.header, correcoes: state.corrections[f.job.id] || {} },
      });
      p.st = 'ok';
      ok += 1;
    } catch (e) {
      p.st = 'err';
      p.err = e.message;
    }
    renderProcessingList();
  }
  saveSession();
  const failed = state.processing.filter((p) => p.st === 'err');
  if (failed.length) {
    toast(`${plural(failed.length, 'arquivo não pôde', 'arquivos não puderam')} ser padronizado(s).`, 'err');
    if (!ok) {
      state.processing.done = true;
      renderProcessingList();
      return;
    }
  }
  notifyDone(ok);
  state.active = 0;
  state.processing = null;
  go(3);
}

function notifyDone(n) {
  const msg = n > 1 ? `${n} documentos padronizados. Confira a prévia.` : 'Documento padronizado. Confira a prévia.';
  toast(msg, 'ok');
  if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
    try { new Notification('Padronização de documentos', { body: msg, icon: '/img/icone.svg' }); } catch { /* sem notificação */ }
  }
}

function renderProcessing(panel) {
  panel.innerHTML = `
    <section class="card card-pad" aria-labelledby="tp">
      <h2 id="tp">Padronizando…</h2>
      <p class="muted">Aplicando o modelo, conferindo o conteúdo e gerando a prévia. Isso leva alguns segundos por arquivo.</p>
      <div class="progress"><span id="proc-bar"></span></div>
      <ul class="proc-list" id="proc-list" aria-live="polite"></ul>
      <div class="btn-row hidden" id="proc-back"><button class="btn" id="proc-back-btn">${icons.back}Voltar</button></div>
    </section>`;
  $('#proc-back-btn', panel).addEventListener('click', () => go(2));
  renderProcessingList();
}

function renderProcessingList() {
  const list = root && $('#proc-list', root);
  if (!list || !state.processing) return;
  const done = state.processing.filter((p) => ['ok', 'err'].includes(p.st)).length;
  $('#proc-bar', root).style.width = `${Math.round((done / state.processing.length) * 100)}%`;
  list.innerHTML = state.processing.map((p) => {
    const ic = p.st === 'run' ? '<span class="spinner" aria-hidden="true"></span>'
      : p.st === 'ok' ? '<span class="dot-ok" aria-hidden="true">✓</span>'
        : p.st === 'err' ? '<span class="dot-err" aria-hidden="true">!</span>' : '<span class="dot-wait" aria-hidden="true"></span>';
    const label = { run: 'aplicando o padrão…', ok: 'concluído', err: p.err, wait: 'na fila' }[p.st];
    return `<li>${ic}<span><b>${esc(p.name)}</b> — <span class="muted">${esc(label)}</span></span></li>`;
  }).join('');
  if (state.processing.done) $('#proc-back', root)?.classList.remove('hidden');
}

// ------------------------------------------------------------------ etapa 3
function integrityCard(job) {
  const ig = job.integridade;
  if (!ig) return '';
  const m = ig.midia_depois || {};
  const ok = ig.status === 'preservado';
  const rows = [
    ['Palavras no original', ig.palavras_antes], ['Palavras no resultado', ig.palavras_depois],
    ['Imagens', m.imagens], ['Tabelas', m.tabelas], ['Equações', m.equacoes],
  ];
  if (m.graficos) rows.push(['Gráficos', m.graficos]);
  if (ig.cobertura_pdf !== undefined) rows.push(['Texto encontrado no PDF', `${String(ig.cobertura_pdf).replace('.', ',')}%`]);
  const diffs = ig.diferencas || [];
  const lost = Object.entries(ig.midia_perdida || {});
  return `
    <section class="card" aria-labelledby="ig-t">
      <h3 id="ig-t">${icons.shield.replace('<svg', '<svg width="18" height="18"')} Conferência do conteúdo</h3>
      ${ok ? '<div class="notice ok"><strong>Conteúdo preservado</strong>Todo o texto, imagens, tabelas e equações do original estão no resultado.</div>'
    : `<div class="notice warn"><strong>Confira com atenção</strong>Foram encontradas diferenças entre o original e o resultado.
          ${diffs.length ? `<ul>${diffs.slice(0, 8).map((d) => `<li>${esc(d.tipo)}: “${esc(d.antes || '—')}” → “${esc(d.depois || '—')}”</li>`).join('')}</ul>` : ''}
          ${lost.length ? `<ul>${lost.map(([k, [a, b]]) => `<li>${esc(k)}: ${a} no original, ${b} no resultado</li>`).join('')}</ul>` : ''}
          ${ig.cobertura_pdf !== undefined && ig.cobertura_pdf < 97 ? '<p class="small">Parte do texto não foi localizada no PDF gerado — verifique se alguma fonte especial ou símbolo foi exibido corretamente.</p>' : ''}
        </div>`}
      ${ig.rotulos_alterados ? `<p class="small muted mt-s">${plural(ig.rotulos_alterados, 'rótulo de questão/alternativa foi uniformizado', 'rótulos de questões/alternativas foram uniformizados')}, conforme sua configuração de numeração.</p>` : ''}
      <dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v ?? 0)}</dd>`).join('')}</dl>
    </section>`;
}

function actionsCard(job) {
  const r = job.relatorio || {};
  const items = [];
  if (r.tabelas_formatadas) items.push(`${plural(r.tabelas_formatadas, 'tabela padronizada', 'tabelas padronizadas')} (estrutura mantida)`);
  if (r.imagens_redimensionadas) items.push(`${plural(r.imagens_redimensionadas, 'imagem reduzida', 'imagens reduzidas')} para caber na página (proporção mantida)`);
  if (r.linhas_em_branco_removidas) items.push(`${plural(r.linhas_em_branco_removidas, 'linha em branco repetida removida', 'linhas em branco repetidas removidas')}`);
  (r.rotulos_alterados || []).slice(0, 5).forEach((x) => items.push(`Rótulo “${x.de}” → “${x.para}”`));
  (r.cabecalhos_substituidos || []).forEach((t) => items.push(`Cabeçalho/rodapé original substituído: “${t.slice(0, 90)}”`));
  const notes = notesFor(job);
  return `
    <section class="card">
      <h3>O que foi feito</h3>
      <p class="small muted">Modelo: <b>${esc(job.modelo_nome)}</b>. Páginas: ${job.paginas_original ?? '?'} no original → ${job.paginas_resultado} no resultado.</p>
      ${items.length ? `<ul class="small">${items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>` : ''}
      ${notes.length ? `<details class="more" ${job.formato === 'pdf' ? 'open' : ''}><summary>${plural(notes.length, 'observação', 'observações')}</summary><ul>${notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul></details>` : ''}
    </section>`;
}

function structureCard(job) {
  const corr = state.corrections[job.id] || {};
  const list = job.estrutura || [];
  const opts = Object.entries(TYPE_LABELS).filter(([k]) => k !== 'empty');
  return `
    <section class="card">
      <h3>Estrutura reconhecida</h3>
      <p class="small muted">Se algum trecho foi identificado errado (ex.: um título tratado como parágrafo), corrija aqui e clique em “Reaplicar”.</p>
      <ul class="structure">
        ${list.map((it) => {
    const cur = corr[it.i] || it.tipo;
    return `<li class="${corr[it.i] ? 'changed' : ''}">
            <span class="txt" title="${esc(it.texto)}">${esc(it.texto || '—')}</span>
            <select data-idx="${it.i}" data-orig="${esc(it.tipo)}" aria-label="Tipo do trecho: ${esc(it.texto.slice(0, 40))}">
              ${opts.map(([k, l]) => `<option value="${k}" ${k === cur ? 'selected' : ''}>${esc(l)}</option>`).join('')}
            </select></li>`;
  }).join('')}
      </ul>
      <div class="btn-row mt-s"><button class="btn btn-sm" id="reapply" ${Object.keys(corr).length ? '' : 'disabled'}>Reaplicar com correções</button>
      ${Object.keys(corr).length ? '<button class="btn btn-sm btn-ghost" id="clear-corr">Desfazer correções</button>' : ''}</div>
    </section>`;
}

function renderPreview(panel) {
  const files = processedFiles();
  if (!files.length) { go(2); return; }
  if (state.active >= files.length) state.active = 0;
  const f = files[state.active];
  const job = f.job;
  const base = 640 * state.zoom;
  const w = state.compare ? Math.round(base * 0.75) : base;
  const v = Math.round(job.processado || job.criado || 0);
  const pages = [];
  for (let i = 1; i <= job.paginas_resultado; i += 1) {
    const res = `<div class="page-col">${state.compare ? '<span class="lbl">Padronizado</span>' : ''}
      <img class="page-img" loading="lazy" width="${w}" src="/api/documentos/${job.id}/previa/resultado/${i}?v=${v}" alt="Página ${i} do documento padronizado"></div>`;
    const orig = state.compare && i <= (job.paginas_original || 0)
      ? `<div class="page-col"><span class="lbl">Original</span><img class="page-img" loading="lazy" width="${w}" src="/api/documentos/${job.id}/previa/original/${i}?v=${v}" alt="Página ${i} do documento original"></div>`
      : (state.compare ? `<div class="page-col"><span class="lbl">Original</span><span class="muted small">${job.paginas_original ? '— sem página correspondente —' : 'prévia do original indisponível'}</span></div>` : '');
    pages.push(`<div class="page-pair">${orig}${res}</div>`);
  }
  const allConfirmed = files.every((x) => x.job.status === 'confirmado');
  panel.innerHTML = `
    ${files.length > 1 ? `<div class="doc-tabs" role="tablist" aria-label="Documentos">${files.map((x, i) => `
      <button role="tab" aria-selected="${i === state.active}" data-doc="${i}" title="${esc(x.name)}">
      ${x.job.integridade?.status === 'preservado' ? '' : `<span class="badge warn">!</span>`}${esc(x.name)}</button>`).join('')}</div>` : ''}
    <div class="preview-layout">
      <section aria-label="Prévia das páginas">
        <div class="preview-toolbar">
          <label class="check-field"><input type="checkbox" id="cmp" ${state.compare ? 'checked' : ''}> Comparar com o original</label>
          <span class="spacer"></span>
          <span class="muted small">${plural(job.paginas_resultado, 'página', 'páginas')}</span>
          <button class="btn btn-sm icon-btn" id="zout" aria-label="Diminuir zoom">${icons.zoomOut}</button>
          <button class="btn btn-sm icon-btn" id="zin" aria-label="Aumentar zoom">${icons.zoomIn}</button>
          <a class="btn btn-sm btn-ghost" href="/api/documentos/${job.id}/original">${icons.download}Original</a>
        </div>
        <div class="pages" tabindex="0" aria-label="Páginas do documento">${pages.join('')}</div>
        <p class="small muted mt-s">A prévia mostra exatamente o PDF gerado. No Word, a quebra de linhas pode variar levemente conforme as fontes instaladas.</p>
      </section>
      <aside class="side">
        ${integrityCard(job)}
        ${actionsCard(job)}
        ${structureCard(job)}
      </aside>
    </div>
    <div class="action-bar">
      <button class="btn" id="adjust">${icons.sliders}Voltar e ajustar</button>
      <span class="spacer"></span>
      <span class="muted small">${allConfirmed ? 'Já confirmado.' : 'Confira as páginas antes de confirmar.'}</span>
      <button class="btn btn-primary btn-lg" id="confirm">${icons.check}${files.length > 1 ? `Confirmar ${files.length} documentos` : 'Confirmar e gerar arquivo final'}</button>
    </div>`;
  $$('[data-doc]', panel).forEach((b) => b.addEventListener('click', () => { state.active = Number(b.dataset.doc); saveSession(); renderPreview(panel); }));
  $('#cmp', panel).addEventListener('change', (e) => { state.compare = e.target.checked; renderPreview(panel); });
  $('#zin', panel).addEventListener('click', () => { state.zoom = Math.min(1.8, state.zoom + 0.2); renderPreview(panel); });
  $('#zout', panel).addEventListener('click', () => { state.zoom = Math.max(0.5, state.zoom - 0.2); renderPreview(panel); });
  $('#adjust', panel).addEventListener('click', () => go(2));
  $('#confirm', panel).addEventListener('click', confirmAll);
  $$('.structure select', panel).forEach((sel) => sel.addEventListener('change', () => {
    const corr = state.corrections[job.id] || (state.corrections[job.id] = {});
    if (sel.value === sel.dataset.orig) delete corr[sel.dataset.idx];
    else corr[sel.dataset.idx] = sel.value;
    sel.closest('li').classList.toggle('changed', sel.value !== sel.dataset.orig);
    $('#reapply', panel).disabled = !Object.keys(corr).length;
    saveSession();
  }));
  $('#reapply', panel)?.addEventListener('click', () => reprocess(f));
  $('#clear-corr', panel)?.addEventListener('click', () => { state.corrections[job.id] = {}; reprocess(f); });
}

async function reprocess(f) {
  const btn = $('#reapply', root);
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Reaplicando…'; }
  try {
    f.job = await api(`/documentos/${f.job.id}/processar`, {
      method: 'POST',
      body: { modelo: state.templateId, saida: state.output, cabecalho: state.header, correcoes: state.corrections[f.job.id] || {} },
    });
    toast('Padronização reaplicada.', 'ok');
  } catch (e) { toast(e.message, 'err'); }
  saveSession();
  render();
}

async function confirmAll() {
  const files = processedFiles();
  const warn = files.filter((f) => f.job.integridade?.status !== 'preservado');
  if (warn.length) {
    const ok = await confirmDialog('Há pontos para conferir',
      `${plural(warn.length, 'documento tem', 'documentos têm')} diferenças apontadas na conferência do conteúdo. Deseja confirmar mesmo assim?`,
      'Confirmar mesmo assim');
    if (!ok) return;
  }
  try {
    for (const f of files) {
      if (f.job.status !== 'confirmado') f.job = await api(`/documentos/${f.job.id}/confirmar`, { method: 'POST' });
    }
    go(4);
  } catch (e) { toast(e.message, 'err'); }
}

// ------------------------------------------------------------------ etapa 4
function downloadButtons(job) {
  const fmts = job.saida === 'ambos' ? ['docx', 'pdf'] : [job.saida];
  return fmts.map((fm) => `<a class="btn ${fm === 'docx' ? 'btn-primary' : ''}" href="/api/documentos/${job.id}/baixar/${fm}">${icons.download}${fm === 'docx' ? 'Word (DOCX)' : 'PDF'}</a>`).join('');
}

function renderDone(panel) {
  const files = processedFiles().filter((f) => f.job.status === 'confirmado');
  const hrs = STATUS.retencao_horas || 24;
  panel.innerHTML = `
    <section class="card card-pad" aria-labelledby="td">
      <div class="done-head"><span class="done-icon">${icons.check}</span>
        <div><h2 id="td">${files.length > 1 ? 'Documentos prontos!' : 'Documento pronto!'}</h2>
        <p class="muted mt-s">Baixe ${files.length > 1 ? 'os arquivos' : 'o arquivo'} abaixo. ${files.some((f) => f.job.saida !== 'pdf') ? 'O DOCX continua editável no Word, LibreOffice e Google Docs.' : ''}</p></div></div>
      <div class="my">
        ${files.map((f) => `
          <div class="result-row">
            <span class="file-name" title="${esc(f.name)}">${esc(f.name)}</span>
            ${f.job.integridade?.status === 'preservado' ? '<span class="badge ok">Conteúdo preservado</span>' : '<span class="badge warn">Revisar</span>'}
            ${downloadButtons(f.job)}
          </div>`).join('')}
      </div>
      <div class="btn-row">
        ${files.length > 1 ? `<a class="btn btn-primary" href="/api/baixar-varios?ids=${files.map((f) => f.job.id).join(',')}&fmt=ambos">${icons.download}Baixar todos (.zip)</a>` : ''}
        <button class="btn" id="see">${icons.eye}Ver prévia novamente</button>
        <span class="spacer"></span>
        <a class="btn btn-primary btn-lg" href="#/novo">${icons.plus}Padronizar outros documentos</a>
      </div>
      <p class="small muted mt-s">Por privacidade, os arquivos ficam disponíveis no <a href="#/historico">Histórico</a> por ${hrs} horas e depois são apagados automaticamente.</p>
    </section>`;
  $('#see', panel).addEventListener('click', () => go(3));
}

// Usado pela tela de modelos ("Usar este modelo")
export function selectTemplate(id) {
  state.templateId = id;
  store.set('ultimoModelo', id);
  if (!state.headerTouched) state.header = null;
  if (state.step === 1 && readyFiles().length && !busy()) state.step = 2;
  saveSession();
}

// Chamado pelo editor depois de salvar, para recarregar os dados do cabeçalho do modelo
export function templateChanged(id) {
  if (state.templateId === id && !state.headerTouched) state.header = null;
}
