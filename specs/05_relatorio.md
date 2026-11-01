CONTEXTO
Pipeline de dados em Python sobre um dataset sintético de e-commerce (Faker `en_IN`, 6 CSVs).
Trabalho com spec-driven development: a spec abaixo é a fonte da verdade e o código é
consequência dela. Não acrescente requisito que não esteja escrito aqui. Se algo estiver
ambíguo, pergunte antes de escrever código.

STACK
- Python 3.13, dependências gerenciadas com uv
- DuckDB, arquivo ecommerce.duckdb na raiz do projeto
- plotly (já instalado), que gera o HTML dos gráficos
- Nenhum orquestrador. Script executável pela linha de comando.

O QUE JÁ EXISTE (use, não reimplemente)
painel.py (etapa 4, só a parte de funções; a página app.py ficou fora desta entrega) expõe,
sem importar streamlit:
  MARTS, PainelErro
  ler(nome)                  DataFrame de marts.<nome>, conexão somente leitura aberta e
                             fechada dentro da função; levanta PainelErro se faltar banco ou mart
  cartoes(df_kpis)           seis tuplas (rótulo, valor formatado, ajuda)
  dinheiro, pct, numero      formatos sem locale ("US$ 1.234,56", "30,07%", "15.000")
  tabela_qualidade(df)       DataFrame da faixa de qualidade, já formatado
  dez funções de gráfico, cada uma recebe o DataFrame do seu mart e devolve go.Figure:
    grafico_status, grafico_pagamento_receita, grafico_pagamento_cancelamento,
    grafico_categoria_receita, grafico_categoria_margem, grafico_categoria_devolucao,
    grafico_top_produtos, grafico_estado, grafico_cidade, grafico_tamanho_pedido
O schema marts, da etapa 3, com onze tabelas. Rascunho das faixas: design/painel.md.

ARTEFATO A PRODUZIR
relatorio.py, na raiz do projeto, executável com:
  uv run python relatorio.py
que escreve relatorio.html na raiz.

SPEC

1. ESCOPO
   Lê os mesmos onze marts do painel e produz um único arquivo HTML estático com as mesmas seis
   faixas do app: 1 números do negócio, 2 status e pagamento, 3 categorias, 4 estado e cidade,
   5 tamanho do pedido, 6 qualidade dos dados. Nunca escreve no banco.
   Não calcula, não desenha gráfico novo: tudo vem de painel.py (ler, cartoes, funções de
   gráfico, tabela_qualidade). Nada de agrupar, somar, tirar média ou juntar tabelas.
   Motivo: relatório e painel têm que mostrar exatamente os mesmos números e os mesmos
   gráficos; duas implementações divergiriam. Número novo = mart novo.
   Fica de fora o filtro por categoria: o arquivo é estático e a faixa 3 mostra todas as
   categorias. Motivo: filtro exige execução; o relatório é para ler e enviar.

2. UM ARQUIVO SÓ
   relatorio.html contém tudo: texto, estilos (CSS dentro de <style>) e gráficos. Nenhum
   arquivo auxiliar.
   plotly.js vem de CDN, carregado uma única vez (no primeiro gráfico; os outros nove não
   repetem o script). Motivo: embutir o plotly.js pesa cerca de 4 MB; os dez gráficos
   com CDN pesam cerca de 90 KB (medido). Consequência declarada: ver os gráficos exige
   internet; texto, cartões e tabela aparecem sem ela.
   Sem JavaScript próprio. O arquivo é claro (fundo branco, texto escuro) em qualquer tema do
   sistema. Motivo: é um documento para ler e imprimir, não uma tela com tema.

3. IDS FIXOS (reprodutibilidade)
   Cada gráfico recebe div_id fixo: grafico_1 a grafico_10, na ordem em que aparecem na página
   (status, pagamento_receita, pagamento_cancelamento, categoria_receita, categoria_margem,
   categoria_devolucao, top_produtos, estado, cidade, tamanho_pedido).
   Motivo: sem div_id o plotly sorteia um identificador novo a cada execução, e dois
   relatórios do mesmo dado deixam de ser comparáveis por diff. Medido: com div_id fixo duas
   gerações saem byte a byte iguais; sem ele, não.

4. RODAPÉ
   Última linha visível: "Gerado em DD/MM/AAAA HH:MM" (hora local, sem segundos), numa linha
   própria do arquivo. É a única parte do arquivo que depende do relógio: duas execuções com o
   mesmo banco diferem só nessa linha (e nem nela, se caírem no mesmo minuto).
   Motivo: o leitor precisa saber de quando é o número; deixar a data numa linha só faz o diff
   entre duas versões do relatório ter uma linha de diferença.

5. CONTEÚDO DAS FAIXAS
   Título "Relatório de vendas — e-commerce" e a legenda "Dados sintéticos. Receita = pedidos
   entregues. Valores em dólar (US$)." (mesmo texto do app).
   Faixa 1: seis cartões (rótulo, valor, ajuda) de cartoes(ler("kpis")), em grade de três
     colunas, a ajuda como texto pequeno sob o valor (relatório impresso não tem dica de mouse).
   Faixa 2: grafico_status em largura total; abaixo, grafico_pagamento_receita e
     grafico_pagamento_cancelamento lado a lado.
   Faixa 3: os quatro gráficos de categoria em duas linhas de duas colunas, com todas as
     categorias (receita, margem; devolução, top produtos), mais a legenda do top produtos
     ("Top 10 do negócio inteiro.").
   Faixa 4: grafico_estado e grafico_cidade lado a lado.
   Faixa 5: grafico_tamanho_pedido em largura total.
   Faixa 6: tabela HTML de tabela_qualidade(ler("qualidade_dados")), seis linhas.
   Texto vindo dos dados passa por html.escape antes de entrar no HTML.
   Motivo do escape: nome de categoria ou de cidade com "&" (existe "Home & Kitchen
   Furniture") não pode quebrar a marcação.

6. SAÍDA NA TELA
   Uma linha:
     relatorio.html gerado: 90.188 bytes, 10 gráficos
   O tamanho vem do arquivo escrito (os bytes lidos de volta do disco), com milhar separado por
   ponto, sem locale. Nenhum outro número é impresso. stdout reconfigurado para utf-8 dentro
   de main().

REEXECUÇÃO
   Sobrescreve relatorio.html. Rodar dez vezes = rodar uma; só o rodapé muda.
   O arquivo só é escrito depois de todo o HTML estar pronto na memória: se algo falhar no meio,
   o relatorio.html anterior continua intacto.

ERRO
   Qualquer PainelErro (banco ausente ou mart ausente): imprime a mensagem do próprio
   PainelErro (já traz o comando a rodar) e encerra com sys.exit(1), sem criar nem alterar
   relatorio.html.
   O banco nunca é criado por este script.

CRITÉRIOS DE ACEITE
- `uv run python relatorio.py` termina com código 0 e imprime a linha do item 6.
- relatorio.html existe, tem menos de 500.000 bytes (medido hoje: cerca de 90 KB) e é um
  documento HTML completo (começa com <!DOCTYPE html>, tem <html>, <head> com <meta
  charset="utf-8"> e <body>).
- Exatamente um <script src="https://cdn.plot.ly/..."> no arquivo.
- Exatamente dez elementos com id grafico_1 a grafico_10, sem repetição.
- Os seis valores dos cartões aparecem no arquivo, texto exato: "US$ 426.938.559,64",
  "US$ 128.389.562,98", "US$ 298.548.996,66", "30,07%", "US$ 177.006,04", "2.940".
- A tabela de qualidade tem as seis verificações (pedidos_sem_item ... devolucoes_de_pedido_nao_entregue).
- Escape: o texto que o relatório monta passa por html.escape. Verificado com entrada inventada,
  porque hoje nenhum texto vindo do dado fora dos gráficos contém "&" (os nomes como "Home &
  Kitchen Furniture" só aparecem dentro dos dados dos gráficos, onde o plotly cuida deles):
  um cartão com rótulo "A & B" e valor "<1>" sai como "A &amp; B" e "&lt;1&gt;", e a tabela de
  qualidade escapa "&" e "<" de uma linha inventada.
- Rodar duas vezes seguidas (no mesmo minuto) gera arquivos idênticos; rodar com o relógio em
  minutos diferentes muda só a linha do rodapé (diff com uma linha).
- Sem banco: mensagem do PainelErro, código 1, e nenhum relatorio.html é criado. Com um
  relatorio.html já existente, ele não é alterado (mesmo hash). Sem marts.kpis (cópia do
  banco): idem. Testado numa cópia do projeto.
- relatorio.py não define figura nenhuma: não importa plotly.graph_objects nem chama go.Figure;
  não contém as palavras groupby, .sum(, .mean(, merge, pivot; não importa duckdb, pandas nem
  streamlit (verificado por busca).
- Com `uv run python -m pipeline.marts` rodando logo depois, nenhum erro de lock (a conexão de
  ler() já está fechada).
- Verificação visual: o arquivo é aberto no navegador e os dez gráficos aparecem (esta
  verificação é do dono do projeto, com internet; a IA só garante a estrutura do HTML).

ENTREGA, nesta ordem
1. A spec como docstring no topo de relatorio.py, dizendo por que cada regra existe, não só o
   que ela manda.
2. O código, com comentários apenas onde a decisão não é óbvia pelo código.
3. Uma lista final do que você assumiu e que não estava na spec. Se a lista não estiver vazia,
   é a minha spec que precisa melhorar.
