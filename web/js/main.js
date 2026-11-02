// Ponto de entrada: rotas da interface e carregamento inicial.
import { $, $$, api, esc, setStatus, setTypeLabels, toast } from './util.js';
import { renderFormatar } from './views/formatar.js';

const main = $('#conteudo');
let cleanup = null;

// O portal tem uma única página: Formatar documento. (As telas antigas de modelos,
// histórico e ajuda continuam em js/views/ e podem voltar a ser ligadas aqui.)
const routes = [
  [/^#?\/?$/, 'formatar', () => renderFormatar(main)],
  [/^#\/formatar$/, 'formatar', () => renderFormatar(main)],
];

async function route() {
  if (typeof cleanup === 'function') cleanup();
  cleanup = null;
  const hash = location.hash || '#/';
  const [path] = hash.split('?');
  for (const [re, nav, fn] of routes) {
    const m = path.match(re);
    if (m) {
      $$('.mainnav a').forEach((a) => a.classList.toggle('active', a.dataset.nav === nav));
      $$('.mainnav a').forEach((a) => a.toggleAttribute('aria-current', a.dataset.nav === nav));
      try {
        cleanup = await fn(m);
      } catch (e) {
        main.innerHTML = `<div class="notice err"><strong>Não foi possível abrir esta página.</strong>${esc(e.message)}</div>`;
      }
      return;
    }
  }
  location.hash = '#/';
}

function showLogin() {
  main.innerHTML = `
    <div class="card card-pad login">
      <h1>Acesso à plataforma</h1>
      <p class="muted">Informe a senha definida pela sua instituição.</p>
      <form id="login-form" class="stack">
        <label class="field"><span>Senha</span>
          <input class="input" type="password" name="senha" autocomplete="current-password" required autofocus></label>
        <button class="btn btn-primary btn-lg" type="submit">Entrar</button>
      </form>
    </div>`;
  $('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api('/login', { method: 'POST', body: { senha: e.target.senha.value } });
      await boot();
    } catch (err) { toast(err.message, 'err'); }
  });
}

async function boot() {
  try {
    const st = await api('/status');
    setStatus(st);
    setTypeLabels(st.tipos);
    if (st.senha) {
      try { await api('/modelos'); } catch { showLogin(); return; }
    }
    if (!st.conversor) {
      toast('Atenção: o conversor LibreOffice não foi encontrado. A geração de PDF e a prévia não funcionarão.', 'err');
    }
  } catch (e) {
    main.innerHTML = `<div class="notice err"><strong>Servidor indisponível.</strong>${esc(e.message)}</div>`;
    return;
  }
  route();
}

const ano = document.getElementById('ano');
if (ano) ano.textContent = new Date().getFullYear();

window.addEventListener('hashchange', route);
window.addEventListener('prumo:login', showLogin);
boot();
