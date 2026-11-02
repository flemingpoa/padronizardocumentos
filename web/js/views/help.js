// Ajuda e orientações.
import { STATUS } from '../util.js';

export function renderHelp(main) {
  const hrs = STATUS.retencao_horas || 24;
  main.innerHTML = `
    <div class="page-head"><div><h1>Ajuda e orientações</h1><p>Tudo o que você precisa saber para padronizar seus documentos.</p></div></div>
    <div class="help">
      <section class="card">
        <h2>Como usar, em 4 passos</h2>
        <ol>
          <li><b>Envie</b> um ou mais arquivos (arraste para a área de envio ou clique nela).</li>
          <li><b>Escolha o modelo</b> — por exemplo, “Avaliações e provas”. Se quiser, preencha turma e data.</li>
          <li><b>Confira a prévia</b>: veja as páginas, compare com o original e confira o quadro “Conferência do conteúdo”.</li>
          <li><b>Confirme e baixe</b> o arquivo em Word (editável) e/ou PDF (para imprimir).</li>
        </ol>
      </section>
      <section class="card">
        <h2>Formatos aceitos</h2>
        <ul>
          <li><b>Word (.docx)</b> — melhor resultado; o arquivo final continua editável.</li>
          <li><b>Word antigo (.doc)</b> e <b>OpenDocument (.odt)</b> — convertidos para .docx antes da padronização.</li>
          <li><b>PDF</b> — reconstruído como documento editável (veja abaixo).</li>
        </ul>
        <p class="small muted mt-s">Arquivos finais: <b>DOCX</b> (abre no Word, LibreOffice e Google Docs) e <b>PDF</b> pronto para impressão.</p>
      </section>
      <section class="card">
        <h2>O que a plataforma faz</h2>
        <ul>
          <li>Ajusta papel, margens, fontes, tamanhos, cores, alinhamentos e espaçamentos.</li>
          <li>Reconhece títulos, questões, alternativas, instruções, listas, tabelas, imagens e equações e aplica um estilo para cada um.</li>
          <li>Cria cabeçalho com instituição, logotipo, disciplina, turma e quadro de identificação do estudante.</li>
          <li>Numera as páginas e coloca rodapé personalizado.</li>
        </ul>
      </section>
      <section class="card">
        <h2>O que a plataforma NUNCA faz</h2>
        <ul>
          <li>Não reescreve, resume ou corrige enunciados, alternativas ou respostas.</li>
          <li>Não remove imagens, tabelas, equações ou gráficos.</li>
          <li>Não cria nem exclui questões.</li>
        </ul>
        <p class="small muted mt-s">Depois de cada padronização, o sistema compara palavra por palavra o original com o resultado e avisa se encontrar qualquer diferença.
        A única mudança de texto possível é opcional: uniformizar os <i>rótulos</i> (ex.: “A)” → “a)”), e ela aparece no relatório.</p>
      </section>
      <section class="card wide">
        <h2>PDFs e documentos digitalizados</h2>
        <p>O PDF é um formato “fechado”: ele guarda a aparência da página, mas não os parágrafos e estilos. Por isso:</p>
        <ul>
          <li><b>PDF com texto</b> (gerado no computador): o texto, as imagens e as tabelas são extraídos e montados em um novo documento editável. A disposição pode mudar um pouco — confira a prévia.</li>
          <li><b>PDF digitalizado</b> (foto ou scanner): é preciso <b>reconhecer o texto (OCR)</b>. A plataforma avisa antes e só faz isso com sua autorização. O reconhecimento pode errar letras: as palavras duvidosas ficam <mark>destacadas em amarelo</mark> e a qualidade é informada.</li>
          <li>Se preferir não usar OCR, as páginas digitalizadas são mantidas como imagem.</li>
        </ul>
        <p class="small muted">Dica: sempre que tiver o arquivo original em Word, prefira enviá-lo em vez do PDF.</p>
      </section>
      <section class="card">
        <h2>Modelos</h2>
        <ul>
          <li>Em <a href="#/modelos">Modelos</a>, clique em <b>Editar</b> para mudar qualquer regra. As alterações são salvas automaticamente.</li>
          <li>Use <b>Novo modelo</b>, <b>Duplicar</b> ou <b>Salvar como novo modelo</b> para criar os seus.</li>
          <li><b>Restaurar padrão</b> desfaz as alterações de um modelo de exemplo.</li>
          <li><b>Visualizar prévia</b> mostra o modelo aplicado a uma prova de exemplo.</li>
        </ul>
      </section>
      <section class="card">
        <h2>Privacidade (LGPD)</h2>
        <ul>
          <li>Os documentos são processados apenas neste servidor; nada é enviado para serviços externos ou de inteligência artificial.</li>
          <li>Arquivos são apagados automaticamente após <b>${hrs} horas</b>. Você também pode excluí-los antes no Histórico.</li>
          <li>Não é pedido cadastro nem dado pessoal para usar a plataforma.</li>
          <li>Evite enviar documentos com dados sensíveis de estudantes que não sejam necessários.</li>
        </ul>
      </section>
      <section class="card wide faq">
        <h2>Dúvidas frequentes</h2>
        <details><summary>Um título foi reconhecido como parágrafo comum. Como corrijo?</summary>
          <p>Na prévia, abra “Estrutura reconhecida”, escolha o tipo correto ao lado do trecho e clique em “Reaplicar com correções”.</p></details>
        <details><summary>O cabeçalho do meu documento sumiu.</summary>
          <p>Os modelos usam cabeçalho padronizado. Se quiser manter o cabeçalho original, edite o modelo e, em “Cabeçalho”, escolha “Manter o cabeçalho que já está no documento”.</p></details>
        <details><summary>O documento ficou com o campo do aluno duplicado.</summary>
          <p>Seu arquivo já tinha um campo “Nome: ____”. Desative “Incluir quadro de identificação do estudante” no cabeçalho do modelo.</p></details>
        <details><summary>No Word a quebra de página ficou um pouco diferente da prévia.</summary>
          <p>A prévia mostra exatamente o PDF gerado. No Word, pequenas diferenças podem acontecer se as fontes instaladas no computador forem diferentes.</p></details>
        <details><summary>Posso padronizar vários arquivos de uma vez?</summary>
          <p>Sim. Envie até ${STATUS.max_arquivos || 10} arquivos: o mesmo modelo é aplicado a todos e você pode baixar tudo em um único .zip.</p></details>
        <details><summary>Caixas de texto e formas não mudaram de fonte.</summary>
          <p>O conteúdo de caixas de texto é mantido exatamente como está, por segurança. Isso é informado nas observações do arquivo.</p></details>
      </section>
    </div>`;
}
