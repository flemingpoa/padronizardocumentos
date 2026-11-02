// Versão do portal para o GitHub Pages: uma única página, com o motor rodando no navegador.
import { $ } from './util.js';
import { renderFormatar } from './formatar.js';

const ano = document.getElementById('ano');
if (ano) ano.textContent = new Date().getFullYear();
$('.mainnav a')?.classList.add('active');
renderFormatar($('#conteudo'));
