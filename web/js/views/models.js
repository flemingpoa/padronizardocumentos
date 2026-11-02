// Lista de modelos de padronização.
import { $, $$, api, confirmDialog, esc, icons, toast } from '../util.js';
import { selectTemplate } from './home.js';

let filter = 'Todos';

export async function renderModels(main) {
  const { modelos } = await api('/modelos');
  const cats = ['Todos', ...new Set(modelos.map((m) => m.category))];
  if (!cats.includes(filter)) filter = 'Todos';
  const shown = modelos.filter((m) => filter === 'Todos' || m.category === filter);
  main.innerHTML = `
    <div class="page-head">
      <div><h1>Modelos de padronização</h1>
      <p>Cada modelo guarda um conjunto de regras (página, fontes, títulos, questões, cabeçalho…). Edite os exemplos ou crie os seus.</p></div>
      <span class="spacer"></span>
      <button class="btn btn-primary" id="new">${icons.plus}Novo modelo</button>
    </div>
    <div class="style-tabs" role="tablist" aria-label="Categorias">
      ${cats.map((c) => `<button role="tab" aria-selected="${c === filter}" data-cat="${esc(c)}">${esc(c)}</button>`).join('')}
    </div>
    <div class="tpl-grid">
      ${shown.map((m) => `
        <article class="tpl-card">
          <div class="tpl-card-top"><span class="tpl-icon">${icons[m.icon] || icons.personalizado}</span>
            <div><h3>${esc(m.name)}</h3><span class="badge gray">${esc(m.category)}</span>
            ${m.builtin ? `<span class="badge">${m.modified ? 'Exemplo (alterado)' : 'Exemplo editável'}</span>` : '<span class="badge ok">Seu modelo</span>'}</div></div>
          <p class="muted small">${esc(m.description || '')}</p>
          <div class="btn-row">
            <button class="btn btn-sm btn-primary" data-use="${esc(m.id)}">Usar</button>
            <a class="btn btn-sm" href="#/modelos/${esc(m.id)}">${icons.edit}Editar</a>
            <button class="btn btn-sm btn-ghost icon-btn" data-dup="${esc(m.id)}" aria-label="Duplicar ${esc(m.name)}" title="Duplicar">${icons.copy}</button>
            ${m.builtin ? '' : `<button class="btn btn-sm btn-ghost btn-danger icon-btn" data-del="${esc(m.id)}" data-name="${esc(m.name)}" aria-label="Excluir ${esc(m.name)}" title="Excluir">${icons.trash}</button>`}
          </div>
        </article>`).join('')}
    </div>`;
  $$('[data-cat]', main).forEach((b) => b.addEventListener('click', () => { filter = b.dataset.cat; renderModels(main); }));
  $('#new', main).addEventListener('click', async () => {
    try {
      const m = await api('/modelos', { method: 'POST', body: { name: 'Meu modelo', base: 'personalizado', category: 'Personalizados' } });
      location.hash = `#/modelos/${m.id}`;
    } catch (e) { toast(e.message, 'err'); }
  });
  $$('[data-use]', main).forEach((b) => b.addEventListener('click', () => {
    selectTemplate(b.dataset.use);
    location.hash = '#/';
  }));
  $$('[data-dup]', main).forEach((b) => b.addEventListener('click', async () => {
    try {
      const m = await api(`/modelos/${b.dataset.dup}/duplicar`, { method: 'POST' });
      toast(`Cópia criada: ${m.name}`, 'ok');
      location.hash = `#/modelos/${m.id}`;
    } catch (e) { toast(e.message, 'err'); }
  }));
  $$('[data-del]', main).forEach((b) => b.addEventListener('click', async () => {
    if (!await confirmDialog('Excluir modelo', `Excluir o modelo “${b.dataset.name}”? Esta ação não pode ser desfeita.`, 'Excluir', true)) return;
    try {
      await api(`/modelos/${b.dataset.del}`, { method: 'DELETE' });
      toast('Modelo excluído.', 'ok');
      renderModels(main);
    } catch (e) { toast(e.message, 'err'); }
  }));
}
