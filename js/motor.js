// Carrega o motor de padronização (Python) dentro do navegador, usando o Pyodide.
// Na primeira visita o navegador baixa o motor (~15 MB) e depois o guarda em cache.
const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';

let pronto = null;
let py = null;

function carregarScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error('Não foi possível baixar o motor do portal. Verifique a conexão com a internet.'));
    document.head.appendChild(s);
  });
}

export function carregarMotor(aoMudar = () => {}) {
  if (pronto) return pronto;
  pronto = (async () => {
    aoMudar('Baixando o motor de formatação…');
    await carregarScript(`${PYODIDE_URL}pyodide.js`);
    py = await window.loadPyodide({ indexURL: PYODIDE_URL });
    aoMudar('Preparando as ferramentas de documentos…');
    await py.loadPackage(['lxml', 'pillow', 'micropip', 'typing-extensions']);
    const base = new URL('motor/', document.baseURI).href;
    const lista = await (await fetch(`${base}arquivos.json`, { cache: 'no-cache' })).json();
    const micropip = py.pyimport('micropip');
    await micropip.install.callKwargs(`${base}${lista.wheel}`, { deps: false });
    aoMudar('Carregando as regras do Fleming…');
    for (const arq of lista.arquivos) {
      const resp = await fetch(`${base}${arq}`, { cache: 'no-cache' });
      if (!resp.ok) throw new Error(`Arquivo do motor não encontrado: ${arq}`);
      const dados = new Uint8Array(await resp.arrayBuffer());
      const destino = `/home/pyodide/${arq}`;
      py.FS.mkdirTree(destino.substring(0, destino.lastIndexOf('/')));
      py.FS.writeFile(destino, dados);
    }
    py.runPython('import importlib, sys; importlib.invalidate_caches(); import navegador');
    aoMudar('');
    return true;
  })().catch((e) => { pronto = null; throw e; });
  return pronto;
}

function chamar(funcao, ...args) {
  const mod = py.pyimport('navegador');
  const bruto = mod[funcao](...args);
  const resp = JSON.parse(bruto);
  if (resp.erro) {
    if (resp.detalhe) console.warn(resp.detalhe);
    throw new Error(resp.erro);
  }
  return resp.ok;
}

export async function analisar(bytes) {
  await carregarMotor();
  return chamar('analisar', bytes);
}

export async function formatar(bytes, perfil) {
  await carregarMotor();
  return chamar('formatar', bytes, JSON.stringify(perfil));
}
