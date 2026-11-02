# Portal de Padronização — Fleming Ensino Médio (Porto Alegre)

Formata provas e listas de exercícios no padrão do Colégio Fleming: cabeçalho institucional,
Arial 12, espaçamento simples, texto justificado, duas colunas e grade de respostas nas provas,
e nome de arquivo automático. Gera o arquivo em Word (.docx) e em PDF.

Tudo roda no navegador de quem usa o site: os documentos **não são enviados a nenhum servidor**.

* Publicação: GitHub Pages (Settings → Pages → Deploy from a branch → `main` / `(root)`).
* O motor de formatação (pasta `motor/`) é Python executado no navegador com o Pyodide.
* Esta pasta é gerada pelo script `construir_site.py` do projeto completo.
