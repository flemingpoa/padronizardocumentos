// Histórico de documentos processados.
import { $, $$, api, confirmDialog, esc, fmtDate, icons, toast } from '../util.js';

const STATUS_LABEL = {
  confirmado: ['ok', 'Concluído'], processado: ['warn', 'Aguardando confirmação'],
  expirado: ['gray', 'Arquivos apagados'], erro: ['err', 'Erro'],
};
const OUT = { docx: 'DOCX', pdf: 'PDF', ambos: 'DOCX + PDF' };

export async function renderHistory(main) {
  const { itens, retencao_horas: hrs } = await api('/historico');
  main.innerHTML = `
    <div class="page-head">
      <div><h1>Histórico</h1><p>Documentos padronizados recentemente.</p></div>
      <span class="spacer"></span>
      ${itens.length ? `<button class="btn btn-ghost btn-danger" id="clear">${icons.trash}Apagar todo o histórico</button>` : ''}
    </div>
    <div class="notice info"><strong>${icons.shield.replace('<svg', '<svg width="16" height="16"')} Privacidade dos documentos</strong>
      Os arquivos enviados e gerados ficam guardados apenas neste servidor, sem acesso público, por <b>${hrs} horas</b>.
      Depois disso são apagados automaticamente — fica só este registro (nome, data e modelo), que você pode excluir quando quiser.
      Nenhum documento é enviado a serviços externos.</div>
    <section class="card mt">
      ${itens.length ? `
        <div class="table-wrap"><table class="list">
          <thead><tr><th>Arquivo</th><th>Data</th><th>Modelo</th><th>Entrada</th><th>Saída</th><th>Status</th><th><span class="sr-only">Ações</span></th></tr></thead>
          <tbody>
          ${itens.map((h) => {
    const [cls, lbl] = STATUS_LABEL[h.status] || ['gray', h.status];
    const outs = h.saida === 'ambos' ? ['docx', 'pdf'] : (h.saida ? [h.saida] : []);
    const canDl = h.disponivel && h.status === 'confirmado';
    return `<tr>
              <td class="name" title="${esc(h.nome)}">${esc(h.nome)}</td>
              <td data-l="Data">${fmtDate(h.data)}</td>
              <td data-l="Modelo">${esc(h.modelo || '—')}</td>
              <td data-l="Entrada">${esc(h.entrada || '—')}</td>
              <td data-l="Saída">${esc(OUT[h.saida] || '—')}</td>
              <td><span class="badge ${cls}">${esc(lbl)}</span>${h.integridade === 'alerta' ? ' <span class="badge warn">Revisar</span>' : ''}
                ${h.disponivel ? `<div class="small muted">disponível até ${fmtDate(h.expira)}</div>` : ''}</td>
              <td><div class="btn-row">
                ${canDl ? outs.map((o) => `<a class="btn btn-sm" href="/api/documentos/${h.id}/baixar/${o}">${icons.download}${o.toUpperCase()}</a>`).join('') : ''}
                <button class="btn btn-sm btn-ghost btn-danger icon-btn" data-del="${h.id}" data-name="${esc(h.nome)}" aria-label="Excluir registro de ${esc(h.nome)}" title="Excluir">${icons.trash}</button>
              </div></td></tr>`;
  }).join('')}
          </tbody></table></div>`
    : `<div class="empty-state">${icons.clock}<p>Nenhum documento padronizado ainda.</p><a class="btn btn-primary" href="#/">Padronizar um documento</a></div>`}
    </section>`;
  $$('[data-del]', main).forEach((b) => b.addEventListener('click', async () => {
    if (!await confirmDialog('Excluir registro', `Excluir “${b.dataset.name}” e os arquivos ligados a ele?`, 'Excluir', true)) return;
    try {
      await api(`/documentos/${b.dataset.del}`, { method: 'DELETE' });
      toast('Registro excluído.', 'ok');
      renderHistory(main);
    } catch (e) { toast(e.message, 'err'); }
  }));
  $('#clear', main)?.addEventListener('click', async () => {
    if (!await confirmDialog('Apagar histórico', 'Apagar todos os registros e arquivos do histórico? Esta ação não pode ser desfeita.', 'Apagar tudo', true)) return;
    await api('/historico', { method: 'DELETE' });
    toast('Histórico apagado.', 'ok');
    renderHistory(main);
  });
}
