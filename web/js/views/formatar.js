// Aba 2 — Formatar documento (Prova ou Lista de exercícios).
import { $, $$, api, esc, fmtBytes, icons, STATUS, store, toast, uploadFile } from '../util.js';

const ACCEPT = ['docx', 'doc', 'odt', 'pdf'];
const MATERIAIS = {
  prova: { nome: 'Prova', icone: 'prova', desc: 'Arial 12 · espaçamento simples · duas colunas' },
  lista: { nome: 'Lista de exercícios', icone: 'lista', desc: 'Arial 12 · espaçamento simples · uma coluna' },
};

const st = {
  file: null, // { name, size, ext, status, progress, job, error }
  tipo: store.get('tipo', 'prova'),
  dados: {
    tipo_prova: 'local', serie: '', conteudo: '', tipo_questoes: '',
    disciplina: store.get('disciplina', ''), professor: store.get('professor', ''),
  },
  busy: false,
  result: null,
  stale: false,
};
let root = null;

const opts = () => STATUS.perfis || { tipos_prova: {}, series: [], disciplinas: [], tipos_questao: [] };

// ------------------------------------------------------------------ regras (iguais às do servidor)
function campos() {
  return st.tipo === 'prova'
    ? ['tipo_prova', 'disciplina', 'professor', 'serie']
    : ['disciplina', 'professor', 'serie', 'conteudo', 'tipo_questoes'];
}

function faltando() {
  const nomes = { tipo_prova: 'tipo de prova', disciplina: 'disciplina', professor: 'nome do professor(a)', serie: 'série', conteudo: 'conteúdo', tipo_questoes: 'tipo de questões' };
  return campos().filter((k) => !String(st.dados[k] || '').trim()).map((k) => nomes[k]);
}

function nomeArquivo() {
  const d = st.dados;
  const v = (x) => String(x || '').trim();
  const partes = st.tipo === 'prova'
    ? [v(d.serie) || 'SÉRIE', opts().tipos_prova[d.tipo_prova] || 'TIPO DE PROVA', v(d.disciplina) || 'DISCIPLINA']
    : [v(d.serie) || 'SÉRIE', 'Lista de Exercícios', v(d.disciplina) || 'DISCIPLINA', v(d.conteudo) || 'CONTEÚDO', v(d.tipo_questoes) || 'TIPO DE QUESTÃO'];
  return partes.map((p) => p.toLocaleUpperCase('pt-BR')).join(' - ').replace(/[\\/:*?"<>|]/g, '-');
}

// ------------------------------------------------------------------ tela
export function renderFormatar(main) {
  root = main;
  render();
  return () => { root = null; };
}

function render() {
  if (!root) return;
  root.innerHTML = `
    <section class="page-head"><div>
      <h1>Formatar documento</h1>
      <p>Envie o arquivo, escolha o tipo de material e preencha os dados. O cabeçalho do Fleming e a formatação são aplicados automaticamente.</p>
    </div></section>
    <div class="formatar">
      <section class="card card-pad" aria-labelledby="p1">
        <div class="passo-titulo"><span class="passo-num">1</span><h2 id="p1">Envie o documento</h2></div>
        <div id="area-arquivo">${areaArquivo()}</div>
      </section>

      <section class="card card-pad" aria-labelledby="p2">
        <div class="passo-titulo"><span class="passo-num">2</span><h2 id="p2">Qual material você vai formatar?</h2></div>
        <div class="materiais" role="radiogroup" aria-labelledby="p2">
          ${Object.entries(MATERIAIS).map(([k, m]) => `
            <button type="button" class="material" role="radio" aria-checked="${st.tipo === k}" data-tipo="${k}">
              <span class="tpl-icon">${icons[m.icone]}</span>
              <span><b>${m.nome}</b><small>${m.desc}</small></span>
              <span class="check" aria-hidden="true"></span>
            </button>`).join('')}
        </div>
      </section>

      <section class="card card-pad" aria-labelledby="p3">
        <div class="passo-titulo"><span class="passo-num">3</span><h2 id="p3">Dados do cabeçalho</h2></div>
        <div class="form-grid" id="campos">${formulario()}</div>
      </section>

      <section class="card card-pad resumo" aria-live="polite">
        <div class="resumo-nome"><span class="field-label">Nome do arquivo final</span>
          <code id="nome-final">${esc(nomeArquivo())}</code></div>
        <div class="btn-row">
          <span class="muted small" id="falta"></span>
          <button class="btn btn-primary btn-lg" id="formatar">${icons.check}Formatar documento</button>
        </div>
      </section>

      <section id="resultado">${st.result ? resultado() : ''}</section>
    </div>
    <datalist id="lista-disciplinas">${opts().disciplinas.map((d) => `<option value="${esc(d)}">`).join('')}</datalist>
    <datalist id="lista-questoes">${opts().tipos_questao.map((d) => `<option value="${esc(d)}">`).join('')}</datalist>`;
  bind();
  atualizarResumo();
}

function pills(name, items, value) {
  return `<div class="pills" role="radiogroup">${items.map(([v, l]) => `
    <label><input type="radio" name="${name}" value="${esc(v)}" ${value === v ? 'checked' : ''} data-campo="${name}"><span>${esc(l)}</span></label>`).join('')}</div>`;
}

function formulario() {
  const d = st.dados;
  const o = opts();
  const serie = `<div class="field span-all"><span class="field-label" id="l-serie">Série destinada</span>${pills('serie', o.series.map((s) => [s, s]), d.serie)}</div>`;
  const disc = `<label class="field"><span>Disciplina</span><input class="input" data-campo="disciplina" list="lista-disciplinas" value="${esc(d.disciplina)}" maxlength="80" placeholder="Ex.: Matemática" autocomplete="off"></label>`;
  const prof = `<label class="field"><span>Nome do professor(a)</span><input class="input" data-campo="professor" value="${esc(d.professor)}" maxlength="80" placeholder="Ex.: Ana Souza"></label>`;
  if (st.tipo === 'prova') {
    return `<div class="field span-all"><span class="field-label">Tipo de prova</span>${pills('tipo_prova', Object.entries(o.tipos_prova), d.tipo_prova)}</div>
      ${disc}${prof}${serie}`;
  }
  return `${disc}${prof}${serie}
    <label class="field"><span>Conteúdo da lista</span><input class="input" data-campo="conteudo" value="${esc(d.conteudo)}" maxlength="100" placeholder="Ex.: Estequiometria"></label>
    <label class="field"><span>Tipo de questões</span><input class="input" data-campo="tipo_questoes" list="lista-questoes" value="${esc(d.tipo_questoes)}" maxlength="60" placeholder="Ex.: ENEM, Vestibulares…" autocomplete="off"></label>`;
}

function areaArquivo() {
  const f = st.file;
  if (!f) {
    return `
      <div class="dropzone" id="dz" role="button" tabindex="0" aria-describedby="dz-help">
        <div class="dz-icon">${icons.upload}</div>
        <strong>Arraste o arquivo para cá</strong>
        <span class="muted">ou <u>clique para escolher no computador</u></span>
        <div class="formats" id="dz-help"><span class="badge gray">DOCX</span><span class="badge gray">DOC</span><span class="badge gray">ODT</span><span class="badge gray">PDF</span><span class="muted small">até ${STATUS.tamanho_max_mb || 25} MB</span></div>
      </div>
      <input type="file" id="file-input" class="sr-only" accept=".docx,.doc,.odt,.pdf" tabindex="-1" aria-hidden="true">`;
  }
  const busy = ['enviando', 'analisando', 'convertendo'].includes(f.status);
  const status = {
    enviando: `<span class="badge gray">Enviando ${Math.round((f.progress || 0) * 100)}%</span>`,
    analisando: '<span class="badge gray">Lendo o documento…</span>',
    convertendo: '<span class="badge gray">Reconhecendo o texto…</span>',
    ocr: '<span class="badge warn">PDF digitalizado</span>',
    erro: '<span class="badge err">Não foi possível ler</span>',
    pronto: '<span class="badge ok">Pronto</span>',
  }[f.status];
  let extra = '';
  if (busy) extra = `<div class="progress ${f.status === 'enviando' ? '' : 'indeterminate'}"><span data-bar></span></div>`;
  else if (f.status === 'erro') extra = `<div class="notice err mt-s">${esc(f.error)}</div>`;
  else if (f.status === 'ocr') {
    extra = `<div class="notice warn mt-s"><strong>Este PDF é digitalizado (uma imagem do papel).</strong>
      Para ter texto editável, o portal pode <b>reconhecer o texto (OCR)</b>. O reconhecimento pode ter erros:
      as palavras duvidosas ficam marcadas em amarelo e o resultado precisa ser conferido.
      <div class="btn-row">${STATUS.ocr ? '<button class="btn btn-sm btn-primary" id="ocr-sim">Reconhecer o texto</button>' : ''}
      <button class="btn btn-sm" id="ocr-nao">Manter as páginas como imagem</button></div></div>`;
  } else if (f.job?.avisos?.length) {
    extra = `<details class="more"><summary>Observações sobre o arquivo</summary><ul>${f.job.avisos.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></details>`;
  }
  return `
    <div class="file">
      <div class="file-top">
        <div class="file-type ${esc(f.ext)}" aria-hidden="true">${esc(f.ext.toUpperCase())}</div>
        <div class="file-info"><div class="file-name" title="${esc(f.name)}">${esc(f.name)}</div>
          <div class="file-meta"><span>${fmtBytes(f.size)}</span><span data-status>${status}</span></div></div>
        <div class="file-actions"><button class="btn btn-sm" id="trocar" ${busy || st.busy ? 'disabled' : ''}>${icons.swap}Trocar arquivo</button></div>
      </div>
      ${extra}
    </div>
    <input type="file" id="file-input" class="sr-only" accept=".docx,.doc,.odt,.pdf" tabindex="-1" aria-hidden="true">`;
}

function resultado() {
  const job = st.result;
  const ig = job.integridade || {};
  const v = Math.round(job.processado || 0);
  const pages = Array.from({ length: job.paginas_resultado || 0 }, (_, i) => `
    <img class="page-img" loading="lazy" width="560" src="/api/documentos/${job.id}/previa/resultado/${i + 1}?v=${v}" alt="Página ${i + 1} do documento formatado">`).join('');
  const ok = ig.status === 'preservado';
  return `
    <div class="card card-pad">
      <div class="passo-titulo"><span class="passo-num ok">${icons.check}</span><h2>Documento formatado</h2></div>
      ${st.stale ? '<div class="notice warn">Você alterou os dados depois de formatar. Clique em “Formatar documento” de novo para atualizar.</div>' : ''}
      ${ok ? `<div class="notice ok mt-s"><strong>Conteúdo preservado</strong>As ${ig.palavras_antes} palavras, imagens, tabelas e equações do original estão no documento final.</div>`
    : `<div class="notice warn mt-s"><strong>Confira com atenção</strong>A conferência automática encontrou diferenças entre o original e o resultado.
        ${(ig.diferencas || []).slice(0, 5).map((d) => `<br>• “${esc(d.antes || '—')}” → “${esc(d.depois || '—')}”`).join('')}</div>`}
      ${(job.avisos || []).length ? `<details class="more"><summary>Observações</summary><ul>${job.avisos.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></details>` : ''}
      <div class="baixar mt">
        <div><span class="field-label">Arquivo</span><code>${esc(job.nome_saida)}</code></div>
        <div class="btn-row">
          <a class="btn btn-primary btn-lg" data-baixar="docx" href="/api/documentos/${job.id}/baixar/docx">${icons.download}Baixar Word</a>
          <a class="btn btn-lg" data-baixar="pdf" href="/api/documentos/${job.id}/baixar/pdf">${icons.download}Baixar PDF</a>
        </div>
      </div>
      <h3 class="mt">Prévia <span class="muted small">(${job.paginas_resultado} página${job.paginas_resultado > 1 ? 's' : ''})</span></h3>
      <div class="pages">${pages}</div>
      <div class="btn-row mt"><button class="btn" id="outro">${icons.plus}Formatar outro documento</button></div>
    </div>`;
}

// ------------------------------------------------------------------ eventos
function bind() {
  const input = $('#file-input', root);
  const dz = $('#dz', root);
  if (dz) {
    dz.addEventListener('click', () => input.click());
    dz.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
    ['dragenter', 'dragover'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
    ['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('drag'); }));
    dz.addEventListener('drop', (e) => { if (e.dataTransfer.files[0]) enviar(e.dataTransfer.files[0]); });
  }
  input?.addEventListener('change', () => { if (input.files[0]) enviar(input.files[0]); input.value = ''; });
  $('#trocar', root)?.addEventListener('click', () => input.click());
  $('#ocr-sim', root)?.addEventListener('click', () => converterPdf(true));
  $('#ocr-nao', root)?.addEventListener('click', () => converterPdf(false));

  $$('[data-tipo]', root).forEach((b) => b.addEventListener('click', () => {
    if (st.tipo === b.dataset.tipo) return;
    st.tipo = b.dataset.tipo;
    store.set('tipo', st.tipo);
    marcarAlterado();
    render();
  }));
  $$('[data-campo]', root).forEach((el) => {
    el.addEventListener(el.type === 'radio' ? 'change' : 'input', () => {
      st.dados[el.dataset.campo] = el.value;
      if (['professor', 'disciplina'].includes(el.dataset.campo)) store.set(el.dataset.campo, el.value);
      marcarAlterado();
      atualizarResumo();
    });
  });
  $('#formatar', root).addEventListener('click', formatar);
  $('#outro', root)?.addEventListener('click', () => {
    st.file = null; st.result = null; st.stale = false;
    Object.assign(st.dados, { conteudo: '', tipo_questoes: '' });
    render();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  $$('[data-baixar]', root).forEach((a) => a.addEventListener('click', baixar));
}

function marcarAlterado() {
  if (st.result && !st.stale) {
    st.stale = true;
    const r = $('#resultado', root);
    if (r) r.innerHTML = resultado();
    $$('[data-baixar]', root).forEach((a) => a.addEventListener('click', baixar));
    $('#outro', root)?.addEventListener('click', () => { st.file = null; st.result = null; st.stale = false; render(); });
  }
}

function atualizarResumo() {
  const nome = $('#nome-final', root);
  if (nome) nome.textContent = nomeArquivo();
  const falta = faltando();
  const pronto = st.file?.status === 'pronto';
  const btn = $('#formatar', root);
  const msg = $('#falta', root);
  if (!btn) return;
  btn.disabled = st.busy || !pronto || falta.length > 0;
  msg.textContent = !st.file ? 'Envie o documento para continuar.'
    : (!pronto ? 'Aguarde a leitura do arquivo.' : (falta.length ? `Falta preencher: ${falta.join(', ')}.` : ''));
}

// ------------------------------------------------------------------ ações
async function enviar(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  if (!ACCEPT.includes(ext)) { toast('Formato não aceito. Envie DOCX, DOC, ODT ou PDF.', 'err'); return; }
  if (file.size > (STATUS.tamanho_max_mb || 25) * 1024 * 1024) { toast(`O arquivo passa do limite de ${STATUS.tamanho_max_mb || 25} MB.`, 'err'); return; }
  const antigo = st.file?.job?.id;
  if (antigo) api(`/documentos/${antigo}`, { method: 'DELETE' }).catch(() => {});
  st.file = { name: file.name, size: file.size, ext, status: 'enviando', progress: 0 };
  st.result = null;
  st.stale = false;
  render();
  const f = st.file;
  try {
    const job = await uploadFile(file, (p, done) => {
      f.progress = p;
      if (done) f.status = 'analisando';
      const s = root && $('[data-status]', root);
      if (s && f.status === 'enviando') {
        s.innerHTML = `<span class="badge gray">Enviando ${Math.round(p * 100)}%</span>`;
        const bar = $('[data-bar]', root);
        if (bar) bar.style.width = `${Math.round(p * 100)}%`;
      }
    });
    f.job = job;
    f.status = job.status === 'erro' ? 'erro' : (job.status === 'aguardando_ocr' ? 'ocr' : 'pronto');
    f.error = job.erro;
  } catch (e) {
    f.status = 'erro';
    f.error = e.message;
  }
  if (st.file === f) atualizarArquivo();
}

function atualizarArquivo() {
  const area = root && $('#area-arquivo', root);
  if (!area) return;
  area.innerHTML = areaArquivo();
  bind2();
  atualizarResumo();
}

// eventos só da área do arquivo (sem redesenhar o formulário, para não perder o que está sendo digitado)
function bind2() {
  const input = $('#file-input', root);
  input?.addEventListener('change', () => { if (input.files[0]) enviar(input.files[0]); input.value = ''; });
  $('#trocar', root)?.addEventListener('click', () => input.click());
  $('#ocr-sim', root)?.addEventListener('click', () => converterPdf(true));
  $('#ocr-nao', root)?.addEventListener('click', () => converterPdf(false));
}

async function converterPdf(ocr) {
  const f = st.file;
  f.status = 'convertendo';
  atualizarArquivo();
  try {
    f.job = await api(`/documentos/${f.job.id}/pdf`, { method: 'POST', body: { ocr, destacar: true } });
    f.status = 'pronto';
  } catch (e) {
    f.status = 'ocr';
    toast(e.message, 'err');
  }
  if (st.file === f) atualizarArquivo();
}

async function formatar() {
  if (st.busy) return;
  const btn = $('#formatar', root);
  st.busy = true;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Formatando…';
  const perfil = { tipo: st.tipo, ...Object.fromEntries(campos().map((k) => [k, st.dados[k]])) };
  try {
    st.result = await api(`/documentos/${st.file.job.id}/processar`, { method: 'POST', body: { perfil, saida: 'ambos' } });
    st.file.job = st.result;
    st.stale = false;
    toast('Documento formatado! Confira a prévia e baixe.', 'ok');
  } catch (e) {
    toast(e.message, 'err');
  }
  st.busy = false;
  render();
  $('#resultado', root)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function baixar(e) {
  e.preventDefault();
  const url = e.currentTarget.getAttribute('href');
  try {
    if (st.result.status !== 'confirmado') {
      st.result = await api(`/documentos/${st.result.id}/confirmar`, { method: 'POST' });
    }
    window.location.href = url;
  } catch (err) { toast(err.message, 'err'); }
}
