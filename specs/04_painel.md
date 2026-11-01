STATUS (atualizado depois da entrega)
Só a parte de funções desta spec foi mantida: o painel.py (leitura, formatos, cartões, filtro de
linhas e as dez funções de gráfico), que o relatório da etapa 5 reaproveita. A página app.py
(item 7), o comando `streamlit run` e o uso do Streamlit foram descartados, e o app.py e a
dependência foram removidos do projeto. O restante do texto abaixo é o da spec original, mantido
como histórico; os itens 1 a 6 continuam valendo para o painel.py.

CONTEXTO
Pipeline de dados em Python sobre um dataset sintético de e-commerce (Faker `en_IN`, 6 CSVs).
Trabalho com spec-driven development: a spec abaixo é a fonte da verdade e o código é
consequência dela. Não acrescente requisito que não esteja escrito aqui. Se algo estiver
ambíguo, pergunte antes de escrever código.

STACK
- Python 3.13, dependências gerenciadas com uv
- DuckDB, arquivo ecommerce.duckdb na raiz do projeto
- Streamlit (página) e plotly (gráficos), já instalados na etapa 0
- Nenhum orquestrador.

O QUE JÁ EXISTE (use, não reimplemente)
pipeline/db.py expõe BANCO, conectar(somente_leitura=False), criar_schema, gravar.
O schema marts, criado pela etapa 3, com onze tabelas:
  kpis (1 linha), receita_por_status (3), receita_por_categoria (6), margem_por_categoria (6),
  top_produtos (10), receita_por_estado (28), receita_por_cidade (10),
  pagamento_por_metodo (4), devolucao_por_categoria (6), tamanho_pedido (9),
  qualidade_dados (6).
Colunas de cada uma: ver specs/03_marts.md, item 3. Dinheiro é DECIMAL(18,2); taxas e
participações são fração de 0 a 1. Rascunho da tela: design/painel.md.

ARTEFATOS A PRODUZIR
painel.py (leitura, formatação, gráficos; não importa streamlit) e app.py (só monta a página),
na raiz do projeto, executáveis com:
  uv run streamlit run app.py

SPEC

1. ESCOPO
   Só lê de marts e só mostra. Nunca escreve no banco. Cada número da tela sai de um mart;
   painel.py e app.py não calculam: nada de groupby, sum, mean, merge, pivot, nem somar,
   dividir ou agrupar valores de dois marts. Número novo = mart novo.
   Motivo: regra de negócio mora no SQL. Dois lugares com a conta é onde os números começam
   a divergir.
   Escolher linhas de um DataFrame (filtro do item 6) e ordenar para exibir não são cálculo.

2. painel.py: LEITURA
   ler(nome) devolve um DataFrame com SELECT * FROM marts.<nome>. O nome tem que ser um dos
   onze acima; outro nome é erro de programação (ValueError).
   A conexão é aberta com conectar(somente_leitura=True) e fechada no finally da própria
   função. Sem cache (sem st.cache_data): são 11 leituras minúsculas, e cache serviria número
   velho depois de o pipeline rodar.
   Motivo: conexão aberta segura o arquivo; fechando na função, o pipeline grava com o painel
   de pé.
   Erros viram uma exceção PainelErro, com a mensagem pronta para a tela:
     - banco não existe (checado antes de conectar, para nunca criar banco vazio):
       "Banco ecommerce.duckdb não encontrado. Rode: uv run python -m pipeline.ingestao"
     - mart não existe: "Mart marts.<nome> não encontrado. Rode: uv run python -m pipeline.marts"
   Motivo: erro de DuckDB cru não diz ao leitor o que fazer.

3. painel.py: FORMATAÇÃO (sem locale)
   dinheiro(v)  1234567.8 -> "US$ 1.234.567,80"   dólar, sempre duas casas; aceita Decimal,
                                                  int e float
   pct(f)       0.3007    -> "30,07%"         fração vira percentual, duas casas
   numero(n)    15000     -> "15.000"         inteiro, milhar com ponto
   Valor None ou NaN devolve "—" nas três.
   Motivo do "US$": decisão do dono do projeto. O dataset não declara moeda; o dólar é uma
   convenção de exibição escolhida, não um fato do dado, e nenhum valor é convertido (o
   número do mart aparece como está). A escrita segue o formato brasileiro (ponto de milhar,
   vírgula decimal), com o prefixo "US$ " e espaço.
   Motivo do "—": nulo é informação e o rótulo "sem valor" é decisão de mart; o painel só
   mostra que ali não há valor, sem preencher com 0.
   Nos gráficos, o plotly recebe layout separators=",." para eixos e dicas usarem vírgula
   decimal e ponto de milhar sem locale.

4. painel.py: CARTÕES
   cartoes(df_kpis) devolve seis tuplas (rótulo, valor formatado, ajuda), nesta ordem, lendo
   a única linha de marts.kpis:
     "Receita bruta"        dinheiro(receita_bruta)   "Itens de pedidos entregues"
     "Valor devolvido"      dinheiro(valor_devolvido) "Soma dos reembolsos"
     "Receita líquida"      dinheiro(receita_liquida) "Receita bruta menos valor devolvido"
     "Taxa de devolução"    pct(taxa_devolucao)       "Valor devolvido / receita bruta"
     "Ticket médio"         dinheiro(ticket_medio)    "Receita bruta / pedidos entregues com item (2.412)"
     "Pedidos entregues"    numero(pedidos_entregues) "Inclui os sem item; com item: 2.412"
   A ajuda traz o número de pedidos com item lido de pedidos_entregues_com_item, formatado
   com numero(); o texto acima mostra o valor de hoje só como exemplo.

5. painel.py: GRÁFICOS (uma função por gráfico; recebe o DataFrame e devolve go.Figure)
   Barras em todos; horizontais quando o rótulo é longo (status, estado, cidade, produto).
   Título, rótulos de eixo e dicas em português. Valor escrito em cada barra, formatado
   pelas funções do item 3. A ordem das barras é a de exibição: valor decrescente nos
   rankings (estado, cidade, produto) e a ordem do mart nos demais.
     grafico_status(df)               valor_itens por rotulo; só "Entregue" (conta_como_receita
                                      = 'sim') em destaque, o resto em cor neutra
     grafico_pagamento_receita(df)    receita_bruta por metodo_pagamento
     grafico_pagamento_cancelamento(df) taxa_cancelamento por metodo_pagamento
     grafico_categoria_receita(df)    receita_bruta por categoria
     grafico_categoria_margem(df)     margem_pct por categoria
     grafico_categoria_devolucao(df)  taxa_devolucao por categoria
     grafico_top_produtos(df)         receita_bruta por produto, rótulo "<nome> #<produto_id>"
     grafico_estado(df)               receita_bruta por estado
     grafico_cidade(df)               receita_bruta por "<cidade> (<estado>)"
     grafico_tamanho_pedido(df)       pedidos por linhas_no_pedido
   Motivo do rótulo "nome #id" e "cidade (estado)": nome de produto não identifica (15 nomes
   para 300 produtos) e Udaipur existe em dois estados.
   tabela_qualidade(df) devolve o DataFrame de qualidade_dados com ocorrencias e base por
   numero() e proporcao por pct(), colunas renomeadas para "Verificação", "Descrição",
   "Ocorrências", "Base", "Proporção". É formatação, não cálculo.
   As cores vêm de uma paleta única definida em painel.py, usada por todos os gráficos.

6. FILTRO
   Barra lateral com um multiselect "Categorias", todas marcadas no início, com as seis
   categorias lidas de receita_por_categoria (coluna categoria).
   Recorta, por seleção de linhas (categoria in escolhidas), os quatro blocos que têm a
   coluna categoria: receita_por_categoria, margem_por_categoria, devolucao_por_categoria e
   top_produtos. Função em painel.py: filtrar_categorias(df, categorias).
   Não recorta: os cartões, status, pagamento, estado, cidade, tamanho de pedido e
   qualidade, porque esses marts não têm categoria; recortá-los exigiria mart novo.
   O top_produtos continua sendo o top 10 do negócio inteiro, só restrito às categorias
   marcadas; pode mostrar menos de 10 barras, e uma legenda diz isso.
   Nenhuma categoria marcada: os quatro gráficos viram o aviso "Nenhuma categoria selecionada".
   Motivo: um filtro que não muda nada engana; um que muda números sem mart por trás seria
   cálculo na tela. Recorte de linhas é o que cabe sem calcular, e a barra lateral diz o que
   ele atinge.

7. app.py: PÁGINA
   Só monta: st.set_page_config(layout="wide"), título, legenda de definição (receita =
   pedidos entregues; valores em dólar, US$), as seis faixas do rascunho, na ordem:
   1 números do negócio (seis st.metric em duas linhas de três), 2 status e pagamento,
   3 categorias, 4 estado e cidade, 5 tamanho do pedido, 6 qualidade dos dados.
   Chama ler(...) e as funções de painel.py; não importa duckdb nem pandas.
   Toda leitura fica dentro de um try/except PainelErro: na falha, st.error(mensagem) e
   st.stop(); nenhuma faixa é desenhada.

REEXECUÇÃO
   A página lê o banco a cada execução do script; apertar R no navegador mostra o que o
   pipeline gravou por último. Nada é persistido.

ERRO
   Banco ausente e mart ausente: item 2 (PainelErro, st.error + st.stop). Arquivo de banco
   nunca é criado pelo painel.

CRITÉRIOS DE ACEITE
- `uv run streamlit run app.py` sobe sem erro (endpoint de saúde do Streamlit responde ok) e
  a página roda inteira sem exceção (verificado com streamlit.testing.v1.AppTest).
- Cartões com os valores esperados, texto exato:
    Receita bruta US$ 426.938.559,64    Valor devolvido US$ 128.389.562,98
    Receita líquida US$ 298.548.996,66  Taxa de devolução 30,07%
    Ticket médio US$ 177.006,04         Pedidos entregues 2.940
  e a ajuda do ticket médio cita 2.412.
- Formatos: dinheiro(Decimal("1234567.8")) = "US$ 1.234.567,80"; pct(0.3007) = "30,07%";
  numero(15000) = "15.000"; as três devolvem "—" para None.
- painel.py não contém "import streamlit"; app.py não contém "import duckdb" nem
  "import pandas" nem as palavras groupby, .sum(, .mean(, merge, pivot (verificado por grep).
- Cada uma das dez funções de gráfico devolve uma figura com pelo menos um traço e usa
  separators=",.".
- Filtro: com só "Toys" marcada, os quatro gráficos da faixa 3 mostram só Toys, os cartões
  não mudam e o top de produtos mostra só produtos de Toys; com nenhuma marcada, aparece o
  aviso nos quatro lugares. Verificado com AppTest.
- Erro claro: sem o banco, a página mostra a mensagem do item 2 e nenhum gráfico, e o banco
  não é criado; sem a tabela marts.kpis (cópia do banco), idem com a mensagem do mart.
- Sem lock: depois de ler com ler(), outra conexão de escrita abre o banco; e com a página
  executada, `uv run python -m pipeline.marts` roda com código 0.
- Todo mart é usado: os onze nomes aparecem em chamadas ler(...) de app.py.

ENTREGA, nesta ordem
1. A spec como docstring no topo de painel.py (e uma linha de remissão em app.py), dizendo por
   que cada regra existe, não só o que ela manda.
2. O código, com comentários apenas onde a decisão não é óbvia pelo código.
3. Uma lista final do que você assumiu e que não estava na spec. Se a lista não estiver vazia,
   é a minha spec que precisa melhorar.
