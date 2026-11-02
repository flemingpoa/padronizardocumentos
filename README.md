# Prumo — Padronização automática de documentos escolares

O professor envia um documento, escolhe o padrão, confere a prévia e baixa o arquivo pronto.
**O conteúdo do documento nunca é reescrito**: só a aparência muda.

---

## Como abrir a plataforma no seu computador

1. Dê **dois cliques** no arquivo **`Iniciar Prumo.bat`** (nesta pasta).
2. Uma janela preta vai abrir — **deixe-a aberta** enquanto usa a plataforma.
3. O navegador abre sozinho em **http://127.0.0.1:8000**. Se não abrir, digite esse endereço no navegador.
4. Para encerrar, feche a janela preta.

> Programas que já foram instalados neste computador e que a plataforma usa:
> Python 3.12, LibreOffice (gera PDF e converte DOC/ODT) e Tesseract OCR com português (lê PDFs digitalizados).

## Página do portal

* **Formatar documento** (página única) — envie o arquivo, escolha **Prova** ou **Lista de exercícios** e preencha os dados:
  * Prova: tipo (Prova Local ou Prova de Recuperação Semestral), disciplina, professor(a) e série.
    Resultado: cabeçalho do Fleming, Arial 12, espaçamento simples, texto justificado, **duas colunas** e,
    no fim, uma **página com a grade de respostas** (20 questões, alternativas A a E).
    Arquivo: `SÉRIE - TIPO DE PROVA - DISCIPLINA` (ex.: `1ª SÉRIE - PROVA LOCAL - MATEMÁTICA`).
  * Lista de exercícios: disciplina, professor(a), série, conteúdo e tipo de questões.
    Resultado: cabeçalho do Fleming, Arial 12, espaçamento simples, uma coluna.
    Arquivo: `SÉRIE - LISTA DE EXERCÍCIOS - DISCIPLINA - CONTEÚDO - TIPO DE QUESTÃO`.

As configurações desses dois materiais ficam em `app/perfis.py`. As telas antigas (modelos, histórico e ajuda)
continuam no projeto, desligadas, e podem voltar quando forem necessárias.

## Como usar a versão anterior (4 passos — telas desligadas no momento)

1. **Enviar** — arraste um ou mais arquivos (até 10, de até 25 MB cada) ou clique na área de envio.
2. **Escolher o modelo** — por exemplo “Avaliações e provas”. Opcionalmente preencha turma, data e disciplina.
3. **Conferir a prévia** — veja as páginas, marque “Comparar com o original” e confira o quadro
   “Conferência do conteúdo”. Se algum trecho foi reconhecido errado, corrija em “Estrutura reconhecida”.
4. **Confirmar e baixar** — em Word (DOCX, editável) e/ou PDF (impressão). Vários arquivos: botão “Baixar todos (.zip)”.

## Formatos

| Entrada | O que acontece |
|---|---|
| DOCX (Word) | Padronizado diretamente — o resultado continua editável |
| DOC (Word antigo) e ODT | Convertidos para DOCX e padronizados |
| PDF com texto | Reconstruído como documento editável (texto, imagens, tabelas; fórmulas viram imagem) |
| PDF digitalizado | Com sua autorização, o texto é reconhecido (OCR); palavras duvidosas ficam em amarelo |

Saída: **DOCX editável** e/ou **PDF pronto para impressão** (você escolhe).

## Modelos disponíveis (todos editáveis)

Avaliações e provas · Listas de exercícios · Atividades pedagógicas · Simulados · Trabalhos acadêmicos (ABNT) ·
Documentos institucionais · Comunicados escolares · Personalizado.

**Criar um modelo:** menu *Modelos* → “Novo modelo” (ou “Duplicar” em um existente, ou “Salvar como novo modelo” dentro do editor).
**Alterar configurações:** *Modelos* → “Editar”. São 11 categorias (Página, Margens, Fonte, Parágrafos, Títulos,
Questões e alternativas, Cabeçalho, Rodapé, Imagens, Tabelas, Numeração). Tudo é salvo automaticamente.
“Restaurar padrão” desfaz alterações; “Visualizar prévia” mostra o modelo aplicado a uma prova de exemplo.

## Privacidade (LGPD)

* Os documentos são processados somente neste computador/servidor. Nada é enviado a serviços externos ou de IA.
* Arquivos enviados e gerados são apagados automaticamente após **24 horas** (pasta `dados/trabalhos`).
  No Histórico fica apenas o registro (nome, data, modelo), que pode ser excluído a qualquer momento.
* Arquivos são validados (tipo real, tamanho, macros, estrutura interna) antes de serem abertos.

## Publicar na internet (quando quiser)

A pasta já contém um `Dockerfile` pronto, que instala tudo o que é necessário (LibreOffice, OCR e fontes).
Serviços que aceitam esse arquivo diretamente: **Render**, **Railway**, **Fly.io** ou qualquer servidor (VPS) com Docker.

1. Envie esta pasta para um repositório no GitHub (sem a pasta `.venv` e sem a pasta `dados`).
2. No serviço escolhido, crie um “Web Service” a partir do repositório (ele detecta o Dockerfile).
3. Defina a variável **`PRUMO_SENHA`** com uma senha — assim só quem tiver a senha acessa a plataforma.
4. Se possível, adicione um **disco persistente** montado em `/dados` (para guardar os modelos personalizados).
5. O serviço fornece um endereço `https://...` (conexão segura).

Custos: o plano mais barato com ~1 GB de memória costuma bastar (o LibreOffice precisa de memória). Não há
outros serviços pagos envolvidos. **A plataforma ainda não foi publicada** — isso depende de uma conta sua nesses serviços.

Outras variáveis opcionais: `PRUMO_RETENCAO_HORAS` (padrão 24), `PRUMO_TAMANHO_MAX_MB` (padrão 25).

## Para técnicos

* Backend: Python 3.12 + FastAPI (`app/`). Motor: `analyzer.py` (reconhecimento de estrutura por regras),
  `formatter.py` (aplica estilos do Word), `pdf_import.py` (PDF/OCR), `integrity.py` (conferência palavra a palavra).
* Interface: HTML/CSS/JavaScript sem etapa de build (`web/`).
* Testes: `.venv\Scripts\python.exe tests\make_test_docs.py` e depois `.venv\Scripts\python.exe tests\test_pipeline.py`.
* Executar manualmente: `.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
