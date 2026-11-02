// Editor de configurações de um modelo (salvamento automático).
import { $, $$, api, confirmDialog, esc, icons, modal, STATUS, toast } from '../util.js';
import { templateChanged } from './home.js';

const ALIGN = [['left', 'À esquerda'], ['center', 'Centralizado'], ['right', 'À direita'], ['justify', 'Justificado']];
const LINES = [[1, 'Simples (1,0)'], [1.15, '1,15'], [1.3, '1,3'], [1.5, '1,5'], [2, 'Duplo (2,0)']];

const STYLE_LABELS = {
  title: 'Título principal', heading1: 'Títulos de seção', heading2: 'Subtítulos',
  activity: 'Identificação de atividades', instruction: 'Instruções gerais', question: 'Questões',
  alternative: 'Alternativas', quote: 'Citações longas', caption: 'Legendas (Figura, Tabela)',
  reference: 'Referências',
};

const num = (k, l, unit, min, max, step = 0.1, help) => ({ t: 'num', k, l, unit, min, max, step, help });
const sel = (k, l, opts, help) => ({ t: 'sel', k, l, opts, help });
const chk = (k, l) => ({ t: 'chk', k, l });
const txt = (k, l, ph = '') => ({ t: 'txt', k, l, ph });
const title = (l) => ({ t: 'title', l });
const note = (l) => ({ t: 'note', l });

const SECTIONS = [
  { id: 'pagina', l: 'Página', d: 'Tamanho do papel, orientação e distância do cabeçalho e rodapé.', f: [
    sel('page.size', 'Tamanho do papel', null), sel('page.orientation', 'Orientação', [['portrait', 'Retrato (em pé)'], ['landscape', 'Paisagem (deitado)']]),
    num('page.header_distance', 'Distância do cabeçalho', 'cm', 0, 5), num('page.footer_distance', 'Distância do rodapé', 'cm', 0, 5)] },
  { id: 'margens', l: 'Margens', d: 'Espaço em branco nas bordas da folha.', margins: true, f: [
    num('page.margin_top', 'Superior', 'cm', 0.3, 6), num('page.margin_bottom', 'Inferior', 'cm', 0.3, 6),
    num('page.margin_left', 'Esquerda', 'cm', 0.3, 6), num('page.margin_right', 'Direita', 'cm', 0.3, 6)] },
  { id: 'fonte', l: 'Fonte', d: 'Letra usada no texto comum do documento.', f: [
    { t: 'font', k: 'body.font', l: 'Família tipográfica' }, num('body.size', 'Tamanho', 'pt', 6, 36, 0.5),
    { t: 'color', k: 'body.color', l: 'Cor do texto' },
    chk('body.bold', 'Negrito em todo o texto'), chk('body.italic', 'Itálico em todo o texto'), chk('body.underline', 'Sublinhado em todo o texto'),
    title('Destaques do original'),
    chk('body.keep_emphasis', 'Manter negrito, itálico e sublinhado usados em palavras do texto'),
    chk('body.standardize_color', 'Padronizar a cor de todo o texto (remove cores diferentes)')] },
  { id: 'paragrafos', l: 'Parágrafos', d: 'Alinhamento, recuos e espaçamentos do texto comum.', styles: ['instruction', 'quote', 'caption', 'reference'], f: [
    sel('body.align', 'Alinhamento', ALIGN), { t: 'line', k: 'body.line_spacing', l: 'Espaçamento entre linhas' },
    num('body.space_before', 'Espaço antes', 'pt', 0, 72, 1), num('body.space_after', 'Espaço depois', 'pt', 0, 72, 1),
    num('body.first_line_indent', 'Recuo da primeira linha', 'cm', -3, 8), num('body.left_indent', 'Recuo à esquerda', 'cm', -3, 8),
    num('body.right_indent', 'Recuo à direita', 'cm', -3, 8),
    chk('body.preserve_centered', 'Manter centralizadas as linhas curtas que já estavam centralizadas'),
    chk('body.collapse_empty', 'Remover linhas em branco repetidas (mantém uma; não use se houver espaço para respostas)')] },
  { id: 'titulos', l: 'Títulos', d: 'Cada nível de título pode ter fonte, tamanho, cor, alinhamento e espaçamento próprios.', styles: ['title', 'heading1', 'heading2', 'activity'], f: [] },
  { id: 'questoes', l: 'Questões e alternativas', d: 'Como as questões e as alternativas de múltipla escolha aparecem.', styles: ['question', 'alternative'], f: [
    chk('questions.label_bold', 'Número/identificação da questão em negrito'),
    chk('questions.keep_together', 'Manter a questão junto das alternativas na mesma página'),
    num('questions.alternative_indent', 'Recuo das alternativas', 'cm', 0, 5),
    num('questions.alternative_hanging', 'Recuo deslocado das alternativas', 'cm', 0, 3, 0.1, 'Alinha a 2ª linha da alternativa depois da letra. Use 0 para desativar.')] },
  { id: 'cabecalho', l: 'Cabeçalho', d: 'Identificação institucional no topo das páginas. Todos os itens são opcionais.', header: true, f: [
    sel('header.mode', 'Cabeçalho', [['replace', 'Usar o cabeçalho padronizado deste modelo'], ['keep', 'Manter o cabeçalho que já está no documento'], ['remove', 'Remover o cabeçalho']]),
    txt('header.institution', 'Nome da instituição', 'Ex.: Escola Estadual Monteiro Lobato'),
    txt('header.discipline', 'Disciplina', 'Ex.: Matemática'), txt('header.teacher', 'Professor(a)'),
    txt('header.class_name', 'Turma', 'Ex.: 7º ano A'), txt('header.date', 'Data', 'Ex.: 15/03/2026'),
    txt('header.extra', 'Texto adicional', 'Ex.: Avaliação Bimestral — Valor: 10 pontos'),
    { t: 'logo', k: 'header.logo', l: 'Logotipo institucional' }, num('header.logo_height', 'Altura do logotipo', 'cm', 0.5, 4),
    sel('header.align', 'Alinhamento do texto', ALIGN.slice(0, 3)), num('header.font_size', 'Tamanho da letra', 'pt', 6, 20, 0.5),
    chk('header.border_bottom', 'Linha separadora abaixo do cabeçalho'),
    title('Identificação do estudante'),
    chk('header.student_field', 'Incluir quadro de identificação do estudante'),
    chk('header.student_fields.name', 'Nome'), chk('header.student_fields.number', 'Número'), chk('header.student_fields.class', 'Turma'),
    chk('header.student_fields.date', 'Data'), chk('header.student_fields.grade', 'Nota'),
    chk('header.first_page_only', 'Quadro só na primeira página (nas demais, cabeçalho resumido)')] },
  { id: 'rodape', l: 'Rodapé', d: 'Texto na parte de baixo das páginas.', f: [
    sel('footer.mode', 'Rodapé', [['replace', 'Usar o rodapé padronizado deste modelo'], ['keep', 'Manter o rodapé que já está no documento'], ['remove', 'Remover o rodapé']]),
    txt('footer.text', 'Texto personalizado do rodapé', 'Ex.: Boa prova!'), sel('footer.align', 'Alinhamento', ALIGN.slice(0, 3)),
    num('footer.font_size', 'Tamanho da letra', 'pt', 6, 16, 0.5), note('A numeração de páginas é configurada em “Numeração”.')] },
  { id: 'imagens', l: 'Imagens', d: 'As imagens nunca são removidas. A proporção é sempre mantida.', f: [
    num('images.max_width', 'Largura máxima', '% da linha', 10, 100, 5, 'Imagens maiores são reduzidas proporcionalmente; menores não são ampliadas.'),
    chk('images.center', 'Centralizar imagens que estão sozinhas na linha')] },
  { id: 'tabelas', l: 'Tabelas', d: 'A estrutura das tabelas (linhas, colunas, células mescladas) é sempre preservada.', f: [
    num('tables.font_size', 'Tamanho da letra nas tabelas', 'pt', 6, 20, 0.5), chk('tables.center', 'Centralizar tabelas na página'),
    chk('tables.full_width', 'Ajustar tabelas à largura da página'),
    sel('tables.borders', 'Bordas', [['keep', 'Manter as bordas e cores originais'], ['all', 'Aplicar borda simples em todas as células']]),
    chk('tables.header_bold', 'Primeira linha em negrito'), chk('tables.repeat_header', 'Repetir a primeira linha quando a tabela continuar na outra página')] },
  { id: 'numeracao', l: 'Numeração', d: 'Numeração das páginas e das questões.', f: [
    chk('numbering.page_numbers', 'Numerar as páginas'),
    sel('numbering.page_position', 'Posição do número', [['footer', 'No rodapé'], ['header', 'No cabeçalho']]),
    sel('numbering.page_align', 'Alinhamento do número', ALIGN.slice(0, 3)),
    sel('numbering.page_format', 'Formato', [['Página {n} de {t}', 'Página 1 de 3'], ['Página {n}', 'Página 1'], ['{n}', '1'], ['{n}/{t}', '1/3'], ['– {n} –', '– 1 –']]),
    num('numbering.page_start', 'Começar a contagem em', '', 1, 999, 1),
    title('Questões e alternativas'),
    note('Atenção: as opções abaixo alteram apenas os RÓTULOS (números e letras), nunca o enunciado. Todas as mudanças aparecem no relatório da prévia.'),
    chk('numbering.renumber_questions', 'Renumerar questões em sequência (1, 2, 3…)'),
    sel('numbering.question_format', 'Formato do número da questão', [['keep', 'Manter como está no documento'], ['1.', '1.'], ['1)', '1)'], ['1 –', '1 –'], ['Questão 1.', 'Questão 1.'], ['Questão 1 –', 'Questão 1 –'], ['QUESTÃO 1', 'QUESTÃO 1 –'], ['Questão 01', 'Questão 01 –']]),
    sel('numbering.alternative_format', 'Formato das alternativas', [['keep', 'Manter como está no documento'], ['a)', 'a)'], ['A)', 'A)'], ['(a)', '(a)'], ['(A)', '(A)'], ['a.', 'a.'], ['A.', 'A.'], ['a –', 'a –']])] },
];

const STYLE_FIELDS = (p) => [
  { t: 'font', k: `${p}.font`, l: 'Fonte', inherit: true }, num(`${p}.size`, 'Tamanho', 'pt', 6, 48, 0.5),
  { t: 'color', k: `${p}.color`, l: 'Cor', inherit: true }, sel(`${p}.align`, 'Alinhamento', ALIGN),
  num(`${p}.space_before`, 'Espaço antes', 'pt', 0, 96, 1), num(`${p}.space_after`, 'Espaço depois', 'pt', 0, 96, 1),
  { t: 'line', k: `${p}.line_spacing`, l: 'Entre linhas', inherit: true },
  num(`${p}.left_indent`, 'Recuo à esquerda', 'cm', -3, 10), num(`${p}.first_line_indent`, 'Recuo da 1ª linha', 'cm', -3, 8),
  chk(`${p}.bold`, 'Negrito'), chk(`${p}.italic`, 'Itálico'), chk(`${p}.underline`, 'Sublinhado'), chk(`${p}.caps`, 'Letras maiúsculas (apenas na exibição)'),
];

const getPath = (o, path) => path.split('.').reduce((a, k) => (a == null ? undefined : a[k]), o);
function setPath(o, path, v) {
  const keys = path.split('.');
  const last = keys.pop();
  const tgt = keys.reduce((a, k) => (a[k] ??= {}), o);
  tgt[last] = v;
}

let tpl = null;
let section = 'pagina';
let styleTab = {};
let saveTimer = null;
let dirty = false;

export async function renderEditor(main, id) {
  tpl = await api(`/modelos/${id}`);
  const back = location.hash.includes('voltar=1');
  dirty = false;
  main.innerHTML = `
    <div class="editor-head">
      <a class="btn btn-ghost btn-sm" href="${back ? '#/' : '#/modelos'}">${icons.back}${back ? 'Voltar para a padronização' : 'Modelos'}</a>
      <span class="spacer"></span>
      <span class="save-state ok" id="save-state" aria-live="polite">Alterações salvas automaticamente</span>
    </div>
    <section class="card card-pad">
      <div class="form-grid">
        <label class="field"><span>Nome do modelo</span><input class="input" id="m-name" maxlength="80" value="${esc(tpl.name)}"></label>
        <label class="field"><span>Categoria</span><input class="input" id="m-cat" maxlength="50" list="cats" value="${esc(tpl.category)}">
          <datalist id="cats"><option>Avaliações</option><option>Exercícios</option><option>Atividades</option><option>Acadêmico</option><option>Institucional</option><option>Comunicação</option><option>Personalizados</option></datalist></label>
        <label class="field span-all"><span>Descrição</span><input class="input" id="m-desc" maxlength="240" value="${esc(tpl.description || '')}"></label>
      </div>
      <div class="btn-row mt">
        <button class="btn btn-primary" id="b-save">${icons.save}Salvar</button>
        <button class="btn" id="b-prev">${icons.eye}Visualizar prévia</button>
        <button class="btn" id="b-new">${icons.plus}Salvar como novo modelo</button>
        <button class="btn btn-ghost" id="b-dup">${icons.copy}Duplicar</button>
        <button class="btn btn-ghost" id="b-reset">${icons.reset}Restaurar padrão</button>
        ${tpl.builtin ? '' : `<button class="btn btn-ghost btn-danger" id="b-del">${icons.trash}Excluir</button>`}
      </div>
      ${tpl.builtin ? '<p class="small muted mt-s">Este é um modelo de exemplo: você pode alterá-lo à vontade e, se quiser, voltar às configurações originais com “Restaurar padrão”.</p>' : ''}
    </section>
    <div class="editor mt">
      <nav class="editor-nav" aria-label="Categorias de configuração">
        ${SECTIONS.map((s, i) => `<button data-sec="${s.id}" aria-current="${s.id === section}"><span class="n">${i + 1}</span>${s.l}</button>`).join('')}
      </nav>
      <section class="card card-pad" id="sec-body" aria-live="polite"></section>
    </div>`;

  ['m-name', 'm-cat', 'm-desc'].forEach((i) => $(`#${i}`, main).addEventListener('input', scheduleSave));
  $$('[data-sec]', main).forEach((b) => b.addEventListener('click', () => {
    section = b.dataset.sec;
    $$('[data-sec]', main).forEach((x) => x.setAttribute('aria-current', x.dataset.sec === section));
    renderSection(main);
  }));
  $('#b-save', main).addEventListener('click', () => save(true));
  $('#b-prev', main).addEventListener('click', preview);
  $('#b-new', main).addEventListener('click', saveAsNew);
  $('#b-dup', main).addEventListener('click', async () => {
    await save();
    const m = await api(`/modelos/${tpl.id}/duplicar`, { method: 'POST' });
    toast(`Cópia criada: ${m.name}`, 'ok');
    location.hash = `#/modelos/${m.id}`;
  });
  $('#b-reset', main).addEventListener('click', async () => {
    const msg = tpl.builtin ? 'Voltar este modelo às configurações originais de exemplo?'
      : 'Voltar às configurações do modelo que deu origem a este?';
    if (!await confirmDialog('Restaurar padrão', msg, 'Restaurar')) return;
    clearTimeout(saveTimer);
    tpl = await api(`/modelos/${tpl.id}/restaurar`, { method: 'POST' });
    templateChanged(tpl.id);
    toast('Configurações restauradas.', 'ok');
    renderSection(main);
  });
  $('#b-del', main)?.addEventListener('click', async () => {
    if (!await confirmDialog('Excluir modelo', `Excluir o modelo “${tpl.name}”?`, 'Excluir', true)) return;
    clearTimeout(saveTimer);
    await api(`/modelos/${tpl.id}`, { method: 'DELETE' });
    toast('Modelo excluído.', 'ok');
    location.hash = '#/modelos';
  });
  renderSection(main);
  const onLeave = (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } };
  window.addEventListener('beforeunload', onLeave);
  return () => {
    window.removeEventListener('beforeunload', onLeave);
    if (dirty) save();
  };
}

// ------------------------------------------------------------------ campos
function fieldHtml(f) {
  const s = tpl.settings;
  const v = f.k ? getPath(s, f.k) : undefined;
  const id = f.k ? `f-${f.k.replace(/\./g, '-')}` : '';
  switch (f.t) {
    case 'title': return `<div class="fieldset-title">${esc(f.l)}</div>`;
    case 'note': return `<div class="notice info span-all">${esc(f.l)}</div>`;
    case 'chk': return `<label class="check-field span-all"><input type="checkbox" data-k="${f.k}" ${v ? 'checked' : ''}> ${esc(f.l)}</label>`;
    case 'num': return `<label class="field" for="${id}"><span>${esc(f.l)}</span>
        <span class="input-unit"><input class="input" id="${id}" type="number" inputmode="decimal" data-k="${f.k}" data-num value="${esc(v ?? '')}" min="${f.min}" max="${f.max}" step="${f.step}">${f.unit ? `<em>${esc(f.unit)}</em>` : ''}</span>
        ${f.help ? `<small>${esc(f.help)}</small>` : ''}</label>`;
    case 'txt': return `<label class="field" for="${id}"><span>${esc(f.l)}</span><input class="input" id="${id}" data-k="${f.k}" value="${esc(v ?? '')}" placeholder="${esc(f.ph || '')}" maxlength="200"></label>`;
    case 'sel': {
      const opts = f.opts || (f.k === 'page.size' ? (STATUS.papeis || ['A4']).map((p) => [p, p]) : []);
      return `<label class="field" for="${id}"><span>${esc(f.l)}</span><select class="input" id="${id}" data-k="${f.k}">
        ${opts.map(([ov, ol]) => `<option value="${esc(ov)}" ${String(v) === String(ov) ? 'selected' : ''}>${esc(ol)}</option>`).join('')}</select>
        ${f.help ? `<small>${esc(f.help)}</small>` : ''}</label>`;
    }
    case 'font': {
      const fonts = STATUS.fontes || ['Arial'];
      const list = v && !fonts.includes(v) ? [v, ...fonts] : fonts;
      return `<label class="field" for="${id}"><span>${esc(f.l)}</span><select class="input" id="${id}" data-k="${f.k}">
        ${f.inherit ? `<option value="" ${!v ? 'selected' : ''}>Igual ao texto (${esc(s.body.font)})</option>` : ''}
        ${list.map((fo) => `<option value="${esc(fo)}" ${fo === v ? 'selected' : ''}>${esc(fo)}</option>`).join('')}</select></label>`;
    }
    case 'line': {
      const opts = [...LINES];
      if (v && !opts.some(([x]) => Number(x) === Number(v))) opts.push([v, String(v).replace('.', ',')]);
      return `<label class="field" for="${id}"><span>${esc(f.l)}</span><select class="input" id="${id}" data-k="${f.k}" data-line>
        ${f.inherit ? `<option value="" ${v == null ? 'selected' : ''}>Igual ao texto</option>` : ''}
        ${opts.map(([ov, ol]) => `<option value="${ov}" ${v != null && Number(v) === Number(ov) ? 'selected' : ''}>${ol}</option>`).join('')}</select></label>`;
    }
    case 'color': return `<div class="field"><span class="field-label">${esc(f.l)}</span><div class="color-field">
        <input type="color" id="${id}" data-k="${f.k}" value="${esc(v || s.body.color || '#000000')}" aria-label="${esc(f.l)}">
        ${f.inherit ? `<label class="check-field small"><input type="checkbox" data-inherit="${f.k}" ${!v ? 'checked' : ''}> Igual ao texto</label>` : ''}</div></div>`;
    case 'logo': return `<div class="field span-all"><span class="field-label">${esc(f.l)}</span><div class="logo-box">
        ${v ? `<img src="/api/logos/${esc(v)}" alt="Logotipo atual">` : '<span class="muted small">Nenhum logotipo enviado.</span>'}
        <label class="btn btn-sm">${icons.upload}${v ? 'Trocar' : 'Enviar'} logotipo<input type="file" accept="image/png,image/jpeg" class="sr-only" id="logo-in"></label>
        ${v ? '<button class="btn btn-sm btn-ghost btn-danger" id="logo-rm">Remover</button>' : ''}
        <small>PNG ou JPG, até 2 MB.</small></div></div>`;
    default: return '';
  }
}

function marginVisual() {
  const p = tpl.settings.page;
  const land = p.orientation === 'landscape';
  const [W, H] = land ? [160, 120] : [120, 160];
  const scale = W / (land ? 29.7 : 21);
  return `<div class="span-all" id="mv-wrap"><div class="margin-visual" id="mv" aria-hidden="true" data-w="${W}" data-h="${H}" data-t="${p.margin_top * scale}" data-b="${p.margin_bottom * scale}" data-l="${p.margin_left * scale}" data-r="${p.margin_right * scale}"><i id="mv-in"></i></div></div>`;
}

function applyMarginVisual(root) {
  const box = $('#mv', root);
  const d = box?.dataset;
  if (!d) return;
  box.style.width = `${d.w}px`;
  box.style.height = `${d.h}px`;
  const inner = $('#mv-in', root);
  Object.assign(inner.style, { top: `${d.t}px`, bottom: `${d.b}px`, left: `${d.l}px`, right: `${d.r}px` });
}

function renderSection(main) {
  const sec = SECTIONS.find((s) => s.id === section);
  const body = $('#sec-body', main);
  let stylesHtml = '';
  if (sec.styles) {
    const cur = styleTab[sec.id] || sec.styles[0];
    stylesHtml = `
      ${sec.f.length ? `<div class="fieldset-title">${sec.id === 'paragrafos' ? 'Tipos especiais de parágrafo' : 'Aparência'}</div>` : ''}
      <div class="span-all"><div class="style-tabs" role="tablist">${sec.styles.map((k) => `<button role="tab" aria-selected="${k === cur}" data-st="${k}">${STYLE_LABELS[k]}</button>`).join('')}</div></div>
      ${STYLE_FIELDS(`styles.${cur}`).map(fieldHtml).join('')}`;
  }
  body.innerHTML = `
    <h2>${esc(sec.l)}</h2><p class="muted small">${esc(sec.d)}</p>
    <div class="form-grid mt">
      ${sec.margins ? marginVisual() : ''}
      ${sec.f.map(fieldHtml).join('')}
      ${stylesHtml}
    </div>`;
  applyMarginVisual(body);
  $$('[data-st]', body).forEach((b) => b.addEventListener('click', () => { styleTab[sec.id] = b.dataset.st; renderSection(main); }));
  $$('[data-k]', body).forEach((el) => {
    const ev = el.type === 'checkbox' || el.tagName === 'SELECT' || el.type === 'color' ? 'change' : 'input';
    el.addEventListener(ev, () => {
      let v;
      if (el.type === 'checkbox') v = el.checked;
      else if (el.dataset.num !== undefined) { if (el.value === '') return; v = Number(el.value); }
      else if (el.dataset.line !== undefined) v = el.value === '' ? null : Number(el.value);
      else v = el.value;
      setPath(tpl.settings, el.dataset.k, v);
      const inh = $(`[data-inherit="${el.dataset.k}"]`, body);
      if (inh) inh.checked = false;
      scheduleSave();
      if (section === 'margens' || el.dataset.k === 'page.orientation') {
        const wrap = $('#mv-wrap', body);
        if (wrap) { wrap.outerHTML = marginVisual(); applyMarginVisual(body); }
      }
    });
  });
  $$('[data-inherit]', body).forEach((el) => el.addEventListener('change', () => {
    const color = $(`[data-k="${el.dataset.inherit}"]`, body);
    setPath(tpl.settings, el.dataset.inherit, el.checked ? '' : color.value);
    scheduleSave();
  }));
  $('#logo-in', body)?.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('arquivo', file);
    try {
      const r = await api('/logos', { method: 'POST', form: fd });
      tpl.settings.header.logo = r.id;
      await save();
      renderSection(main);
    } catch (err) { toast(err.message, 'err'); }
  });
  $('#logo-rm', body)?.addEventListener('click', async () => {
    tpl.settings.header.logo = null;
    await save();
    renderSection(main);
  });
}

// ------------------------------------------------------------------ salvar / prévia
function collectMeta() {
  return {
    name: $('#m-name')?.value || tpl.name,
    category: $('#m-cat')?.value || tpl.category,
    description: $('#m-desc')?.value ?? tpl.description,
  };
}

function scheduleSave() {
  dirty = true;
  const st = $('#save-state');
  if (st) { st.textContent = 'Salvando…'; st.classList.remove('ok'); }
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => save(), 900);
}

async function save(manual = false) {
  clearTimeout(saveTimer);
  try {
    const saved = await api(`/modelos/${tpl.id}`, { method: 'PUT', body: { ...collectMeta(), settings: tpl.settings } });
    tpl.name = saved.name;
    tpl.category = saved.category;
    dirty = false;
    templateChanged(tpl.id);
    const st = $('#save-state');
    if (st) { st.textContent = 'Alterações salvas automaticamente'; st.classList.add('ok'); }
    if (manual) toast('Modelo salvo.', 'ok');
  } catch (e) {
    const st = $('#save-state');
    if (st) st.textContent = 'Não foi possível salvar';
    toast(e.message, 'err');
  }
}

async function preview() {
  const m = modal({
    title: 'Prévia do modelo', body: `<div class="proc-list"><span class="spinner"></span> Aplicando o modelo a um documento de exemplo…</div>`,
  });
  try {
    const r = await api(`/modelos/${tpl.id}/previa`, { method: 'POST', body: { settings: tpl.settings } });
    const imgs = Array.from({ length: r.paginas }, (_, i) => `<img class="page-img" width="600" src="/api/previa-modelo/${r.id}/${i + 1}" alt="Página ${i + 1} do exemplo">`).join('');
    $('.modal-body', m.el).innerHTML = `<p class="small muted">Documento de exemplo (avaliação com questões, imagem, equação e tabela) padronizado com as configurações atuais. É gerado pelo mesmo motor usado nos seus arquivos.</p>
      <div class="pages">${imgs}</div>`;
  } catch (e) {
    $('.modal-body', m.el).innerHTML = `<div class="notice err">${esc(e.message)}</div>`;
  }
}

function saveAsNew() {
  const m = modal({
    title: 'Salvar como novo modelo', narrow: true,
    body: `<label class="field"><span>Nome do novo modelo</span><input class="input" id="nm" maxlength="80" value="${esc(`${tpl.name} (meu)`)}" autofocus></label>`,
    actions: [
      { label: 'Cancelar', cls: 'btn-ghost' },
      {
        label: 'Criar modelo', cls: 'btn-primary',
        onClick: async (close) => {
          try {
            const created = await api('/modelos', {
              method: 'POST',
              body: { name: $('#nm', m.el).value, category: tpl.builtin ? 'Personalizados' : tpl.category, description: $('#m-desc').value, settings: tpl.settings, base: tpl.id },
            });
            close();
            toast('Novo modelo criado.', 'ok');
            location.hash = `#/modelos/${created.id}`;
          } catch (e) { toast(e.message, 'err'); }
        },
      },
    ],
  });
}
