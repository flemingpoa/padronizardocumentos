// Formatar documento (Prova ou Lista de exercícios) — tudo acontece no navegador do professor.
import { $, $$, esc, fmtBytes, icons, store, toast } from './util.js';
import { analisar, carregarMotor, formatar as formatarNoMotor } from './motor.js';

const LIMITE_MB = 25;
const OPCOES = {
  tipos_prova: { local: 'Prova Local', recuperacao: 'Prova de Recuperação Semestral' },
  series: ['1ª série', '2ª série', '3ª série'],
  disciplinas: ['Arte', 'Biologia', 'Educação Física', 'Espanhol', 'Filosofia', 'Física', 'Geografia',
    'História', 'Inglês', 'Língua Portuguesa', 'Literatura', 'Matemática', 'Química', 'Redação', 'Sociologia'],
  tipos_questao: ['ENEM', 'Vestibulares', 'ENEM e Vestibulares', 'Autorais', 'Olimpíadas'],
};
const MATERIAIS = {
  prova: { nome: 'Prova', icone: 'prova', desc: 'Arial 12 · espaçamento simples · duas colunas · grade de respostas' },
  lista: { nome: 'Lista de exercícios', icone: 'lista', desc: 'Arial 12 · espaçamento simples · uma coluna' },
};

const st = {
  motor: 'carregando', // carregando | pronto | erro
  motorMsg: 'Preparando o portal…',
  file: null, // { name, size, status: lendo | pronto | erro, bytes, error }
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

// ------------------------------------------------------------------ regras
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
    ? [v(d.serie) || 'SÉRIE', OPCOES.tipos_prova[d.tipo_prova] || 'TIPO DE PROVA', v(d.disciplina) || 'DISCIPLINA']
    : [v(d.serie) || 'SÉRIE', 'Lista de Exercícios', v(d.disciplina) || 'DISCIPLINA', v(d.conteudo) || 'CONTEÚDO', v(d.tipo_questoes) || 'TIPO DE QUESTÃO'];
  return partes.map((p) => p.toLocaleUpperCase('pt-BR')).join(' - ').replace(/[\\/:*?"<>|]/g, '-');
}

// ------------------------------------------------------------------ tela
export function renderFormatar(main) {
  root = main;
  render();
  carregarMotor((msg) => { st.motorMsg = msg; atualizarMotor(); })
    .then(() => { st.motor = 'pronto'; atualizarMotor(); if (st.file?.status === 'lendo') lerArquivo(); })
    .catch((e) => { st.motor = 'erro'; st.motorMsg = e.message; atualizarMotor(); });
}

function avisoMotor() {
  if (st.motor === 'pronto') return '';
  if (st.motor === 'erro') {
    return `<div class="notice err"><strong>Não foi possível preparar o portal.</strong>${esc(st.motorMsg)}
      <div class="btn-row"><button class="btn btn-sm" id="tentar">Tentar de novo</button></div></div>`;
  }
  return `<div class="notice info motor-carregando"><span class="spinner" aria-hidden="true"></span>
    <span><strong>${esc(st.motorMsg || 'Preparando o portal…')}</strong>
    Na primeira visita isso leva alguns segundos; nas próximas é bem mais rápido. Você já pode preencher os dados.</span></div>`;
}

function render() {
  if (!root) return;
  root.innerHTML = `
    <section class="page-head"><div>
      <h1>Formatar documento</h1>
      <p>Envie o arquivo, escolha o tipo de material e preencha os dados. O cabeçalho do Fleming e a formatação são aplicados automaticamente.</p>
    </div></section>
    <div class="formatar">
      <div id="motor-status">${avisoMotor()}</div>
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
    <datalist id="lista-disciplinas">${OPCOES.disciplinas.map((d) => `<option value="${esc(d)}">`).join('')}</datalist>
    <datalist id="lista-questoes">${OPCOES.tipos_questao.map((d) => `<option value="${esc(d)}">`).join('')}</datalist>`;
  bind();
  atualizarResumo();
  if (st.result) prepararPrevia();
}

function atualizarMotor() {
  const box = root && $('#motor-status', root);
  if (box) {
    box.innerHTML = avisoMotor();
    $('#tentar', box)?.addEventListener('click', () => { st.motor = 'carregando'; renderFormatar(root); });
  }
  atualizarResumo();
}

function pills(name, items, value) {
  return `<div class="pills" role="radiogroup">${items.map(([v, l]) => `
    <label><input type="radio" name="${name}" value="${esc(v)}" ${value === v ? 'checked' : ''} data-campo="${name}"><span>${esc(l)}</span></label>`).join('')}</div>`;
}

function formulario() {
  const d = st.dados;
  const serie = `<div class="field span-all"><span class="field-label">Série destinada</span>${pills('serie', OPCOES.series.map((s) => [s, s]), d.serie)}</div>`;
  const disc = `<label class="field"><span>Disciplina</span><input class="input" data-campo="disciplina" list="lista-disciplinas" value="${esc(d.disciplina)}" maxlength="80" placeholder="Ex.: Matemática" autocomplete="off"></label>`;
  const prof = `<label class="field"><span>Nome do professor(a)</span><input class="input" data-campo="professor" value="${esc(d.professor)}" maxlength="80" placeholder="Ex.: Ana Souza"></label>`;
  if (st.tipo === 'prova') {
    return `<div class="field span-all"><span class="field-label">Tipo de prova</span>${pills('tipo_prova', Object.entries(OPCOES.tipos_prova), d.tipo_prova)}</div>
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
        <div class="formats" id="dz-help"><span class="badge gray">Word (.docx)</span><span class="muted small">até ${LIMITE_MB} MB · o arquivo não sai do seu computador</span></div>
      </div>
      <input type="file" id="file-input" class="sr-only" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" tabindex="-1" aria-hidden="true">`;
  }
  const status = {
    lendo: '<span class="badge gray">Lendo o documento…</span>',
    erro: '<span class="badge err">Não foi possível ler</span>',
    pronto: '<span class="badge ok">Pronto</span>',
  }[f.status];
  let extra = '';
  if (f.status === 'lendo') extra = '<div class="progress indeterminate"><span></span></div>';
  else if (f.status === 'erro') extra = `<div class="notice err mt-s">${esc(f.error)}</div>`;
  else if (f.avisos?.length) {
    extra = `<details class="more"><summary>Observações sobre o arquivo</summary><ul>${f.avisos.map((a) => `<li>${esc(a)}</li>`).join('')}</ul></details>`;
  }
  return `
    <div class="file">
      <div class="file-top">
        <div class="file-type docx" aria-hidden="true">DOCX</div>
        <div class="file-info"><div class="file-name" title="${esc(f.name)}">${esc(f.name)}</div>
          <div class="file-meta"><span>${fmtBytes(f.size)}</span><span>${status}</span></div></div>
        <div class="file-actions"><button class="btn btn-sm" id="trocar" ${st.busy ? 'disabled' : ''}>${icons.swap}Trocar arquivo</button></div>
      </div>
      ${extra}
    </div>
    <input type="file" id="file-input" class="sr-only" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" tabindex="-1" aria-hidden="true">`;
}

function resultado() {
  const r = st.result;
  const ig = r.integridade || {};
  const ok = ig.status === 'preservado';
  return `
    <div class="card card-pad">
      <div class="passo-titulo"><span class="passo-num ok">${icons.check}</span><h2>Documento formatado</h2></div>
      ${st.stale ? '<div class="notice warn">Você alterou os dados depois de formatar. Clique em “Formatar documento” de novo para atualizar.</div>' : ''}
      ${ok ? `<div class="notice ok mt-s"><strong>Conteúdo preservado</strong>As ${ig.palavras_antes} palavras, imagens, tabelas e equações do original estão no documento final.</div>`
    : `<div class="notice warn mt-s"><strong>Confira com atenção</strong>A conferência automática encontrou diferenças entre o original e o resultado.
        ${(ig.diferencas || []).slice(0, 5).map((d) => `<br>• “${esc(d.antes || '—')}” → “${esc(d.depois || '—')}”`).join('')}</div>`}
      ${(r.avisos || []).length ? `<div class="notice info mt-s">${r.avisos.map((a) => esc(a)).join('<br>')}</div>` : ''}
      <div class="baixar mt">
        <div><span class="field-label">Arquivo</span><code>${esc(r.nome)}</code></div>
        <div class="btn-row">
          <button class="btn btn-primary btn-lg" id="baixar-word">${icons.download}Baixar Word</button>
          <button class="btn btn-lg" id="baixar-pdf">${icons.download}Baixar PDF</button>
        </div>
      </div>
      <p class="small muted mt-s">Para o PDF: na janela que abrir, escolha <b>Salvar como PDF</b> (em “Destino”) e clique em <b>Salvar</b>.
      Se aparecerem data e endereço do site nas bordas, desmarque “Cabeçalhos e rodapés” em “Mais configurações”.</p>
      <h3 class="mt">Prévia</h3>
      <iframe id="previa" class="previa" title="Prévia do documento formatado"></iframe>
      <div class="btn-row mt"><button class="btn" id="outro">${icons.plus}Formatar outro documento</button></div>
    </div>`;
}

function prepararPrevia() {
  const frame = $('#previa', root);
  if (!frame || !st.result) return;
  frame.addEventListener('load', () => {
    const ajustar = () => {
      try { frame.style.height = `${frame.contentDocument.documentElement.scrollHeight + 4}px`; } catch { /* sem acesso */ }
    };
    ajustar();
    setTimeout(ajustar, 400);
  }, { once: true });
  frame.srcdoc = st.result.html;
}

// ------------------------------------------------------------------ eventos
function bindArquivo() {
  const input = $('#file-input', root);
  const dz = $('#dz', root);
  if (dz) {
    dz.addEventListener('click', () => input.click());
    dz.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
    ['dragenter', 'dragover'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
    ['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('drag'); }));
    dz.addEventListener('drop', (e) => { if (e.dataTransfer.files[0]) receber(e.dataTransfer.files[0]); });
  }
  input?.addEventListener('change', () => { if (input.files[0]) receber(input.files[0]); input.value = ''; });
  $('#trocar', root)?.addEventListener('click', () => input.click());
}

function bindResultado() {
  $('#baixar-word', root)?.addEventListener('click', baixarWord);
  $('#baixar-pdf', root)?.addEventListener('click', baixarPdf);
  $('#outro', root)?.addEventListener('click', () => {
    st.file = null; st.result = null; st.stale = false;
    Object.assign(st.dados, { conteudo: '', tipo_questoes: '' });
    render();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
}

function bind() {
  bindArquivo();
  bindResultado();
  $('#tentar', root)?.addEventListener('click', () => { st.motor = 'carregando'; renderFormatar(root); });
  $$('[data-tipo]', root).forEach((b) => b.addEventListener('click', () => {
    if (st.tipo === b.dataset.tipo) return;
    st.tipo = b.dataset.tipo;
    store.set('tipo', st.tipo);
    if (st.result) st.stale = true;
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
}

function marcarAlterado() {
  if (st.result && !st.stale) {
    st.stale = true;
    const aviso = document.createElement('div');
    aviso.className = 'notice warn';
    aviso.textContent = 'Você alterou os dados depois de formatar. Clique em “Formatar documento” de novo para atualizar.';
    $('#resultado .passo-titulo', root)?.after(aviso);
  }
}

function atualizarResumo() {
  const nome = root && $('#nome-final', root);
  if (nome) nome.textContent = nomeArquivo();
  const btn = root && $('#formatar', root);
  const msg = root && $('#falta', root);
  if (!btn) return;
  const falta = faltando();
  const pronto = st.file?.status === 'pronto';
  btn.disabled = st.busy || st.motor !== 'pronto' || !pronto || falta.length > 0;
  msg.textContent = !st.file ? 'Envie o documento para continuar.'
    : (st.motor !== 'pronto' ? 'Aguarde o portal terminar de carregar.'
      : (!pronto ? 'Aguarde a leitura do arquivo.' : (falta.length ? `Falta preencher: ${falta.join(', ')}.` : '')));
}

// ------------------------------------------------------------------ ações
async function receber(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  if (ext !== 'docx') {
    toast(ext === 'doc' || ext === 'odt' || ext === 'pdf'
      ? 'Este portal aceita arquivos do Word (.docx). Abra o arquivo no Word e use “Salvar como” → Documento do Word (.docx).'
      : 'Formato não aceito. Envie um arquivo do Word (.docx).', 'err');
    return;
  }
  if (file.size > LIMITE_MB * 1024 * 1024) { toast(`O arquivo passa do limite de ${LIMITE_MB} MB.`, 'err'); return; }
  st.file = { name: file.name, size: file.size, status: 'lendo', bytes: new Uint8Array(await file.arrayBuffer()) };
  st.result = null;
  st.stale = false;
  const r = $('#resultado', root);
  if (r) r.innerHTML = '';
  atualizarArquivo();
  if (st.motor === 'pronto') lerArquivo();
}

async function lerArquivo() {
  const f = st.file;
  if (!f) return;
  await new Promise((res) => setTimeout(res, 30)); // deixa a tela mostrar "Lendo…"
  try {
    const info = await analisar(f.bytes);
    f.status = 'pronto';
    f.avisos = info.analise?.avisos || [];
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
  bindArquivo();
  atualizarResumo();
}

async function formatar() {
  if (st.busy) return;
  const btn = $('#formatar', root);
  st.busy = true;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Formatando…';
  await new Promise((res) => setTimeout(res, 30)); // deixa a tela atualizar antes do processamento
  const perfil = { tipo: st.tipo, ...Object.fromEntries(campos().map((k) => [k, st.dados[k]])) };
  try {
    st.result = await formatarNoMotor(st.file.bytes, perfil);
    st.stale = false;
    toast('Documento formatado! Confira a prévia e baixe.', 'ok');
  } catch (e) {
    toast(e.message, 'err');
  }
  st.busy = false;
  render();
  $('#resultado', root)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function baixarWord() {
  const bin = atob(st.result.docx);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  const blob = new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${st.result.nome}.docx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

function baixarPdf() {
  const frame = $('#previa', root);
  if (!frame?.contentWindow) return;
  // o nome sugerido para o PDF é o título da página impressa
  const tituloAntes = document.title;
  document.title = st.result.nome;
  frame.contentWindow.focus();
  frame.contentWindow.print();
  setTimeout(() => { document.title = tituloAntes; }, 1000);
}
