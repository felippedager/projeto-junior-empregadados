CONTEXTO
Pipeline de dados em Python sobre um dataset sintético de e-commerce (Faker `en_IN`, 6 CSVs).
Trabalho com spec-driven development: a spec abaixo é a fonte da verdade e o código é
consequência dela. Não acrescente requisito que não esteja escrito aqui. Se algo estiver
ambíguo, pergunte antes de escrever código.

STACK
- Python 3.13, dependências gerenciadas com uv
- DuckDB, arquivo ecommerce.duckdb na raiz do projeto
- Nenhum orquestrador. Script executável pela linha de comando.

O QUE JÁ EXISTE (use, não reimplemente)
pipeline/db.py expõe:
  conectar(somente_leitura=False)  abre o ecommerce.duckdb, criando se faltar
  criar_schema(con, nome)          CREATE SCHEMA IF NOT EXISTS
  gravar(con, df, schema, tabela)  (não é usada nesta etapa: a transformação é toda em SQL)
O schema raw, criado pela etapa 1: seis tabelas (categorias, clientes, produtos, pedidos,
itens_pedido, devolucoes), 30.806 linhas, todas as colunas VARCHAR, nomes de coluna em inglês
como no CSV, campo vazio como NULL (hoje há 0 nulos).

ARTEFATO A PRODUZIR
pipeline/transformacao.py, executável com:
  uv run python -m pipeline.transformacao

SPEC

1. ESCOPO
   Lê de raw, escreve no schema refined. Nunca escreve em raw.
   Entram as seis tabelas: categorias, clientes, produtos, pedidos, itens_pedido, devolucoes.
   Todas servem a pelo menos uma pergunta de mart (receita, margem, estado, devolução).
   Ficam de fora duas colunas de clientes:
     name    nenhuma pergunta de mart usa, e é dado pessoal.
     email   idem. 22 e-mails se repetem entre clientes diferentes, o que mostra que não
             identifica ninguém.
   Motivo: não se limpa o que ninguém vai ler. As colunas continuam em raw.

2. NOMES
   Colunas renomeadas para português, snake_case, com o mapa abaixo, completo e literal.
   Nenhuma coluna fora do mapa; nenhuma descartada, exceto as duas do item 1.
   Motivo: é o vocabulário que será digitado de memória nos JOINs dos marts.

   categorias
     category_id -> categoria_id           category_name -> nome
   clientes
     customer_id -> cliente_id             signup_date -> data_cadastro
     city -> cidade                        state -> estado
   produtos
     product_id -> produto_id              product_name -> nome
     category_id -> categoria_id           price -> preco
     cost_price -> custo
   pedidos
     order_id -> pedido_id                 customer_id -> cliente_id
     order_status -> status                payment_method -> metodo_pagamento
   itens_pedido
     order_item_id -> item_id              order_id -> pedido_id
     product_id -> produto_id              quantity -> quantidade
     unit_price -> preco_unitario
   devolucoes
     return_id -> devolucao_id             order_item_id -> item_id
     return_date -> data_devolucao         refund_amount -> valor_reembolso

3. TIPOS
   Identificadores (categoria_id, cliente_id, produto_id, pedido_id, item_id, devolucao_id):
     INTEGER. Motivo: são números sequenciais de 1 a N, sem zero à esquerda (0 ocorrências em
     12 colunas de id auditadas, regex ^(0|[1-9][0-9]*)$), então nada se perde na conversão; e
     como INTEGER ordenam e ligam sem surpresa. Se um id um dia vier com zero à esquerda, a
     conversão não falha, mas a regra deve voltar para VARCHAR: está registrado aqui para
     quem mexer.
   Datas: DATE, formato declarado '%Y-%m-%d' (data_cadastro, data_devolucao).
     Motivo: o dado só tem dia; guardar hora seria inventar precisão. Auditado: 5.000 e 1.500
     valores batem com ^[0-9]{4}-[0-9]{2}-[0-9]{2}$.
   Dinheiro (preco, custo, preco_unitario, valor_reembolso): DECIMAL(10,2).
     Motivo: DOUBLE não representa centavos com exatidão e soma de dinheiro tem que fechar.
     Maior valor auditado: 307.518,60 (valor_reembolso); cabe com folga (limite 99.999.999,99).
   Contagem (quantidade): INTEGER. Valores de 1 a 5.
   Todo o resto continua VARCHAR: nome, cidade, estado, status, metodo_pagamento.
     Motivo: são rótulos. Os valores continuam em inglês, como no dado (status: Canceled,
     Delivered, In Transit); traduzir rótulo é decisão de mart.
   A conversão é feita em SQL pelo DuckDB (CAST, strptime), disparada pelo Python.
   Motivo: o dado já está no banco; não há por que trazê-lo para a memória só para converter.

4. CONVERSÃO QUE FALHA
   Para tudo. Use strptime e CAST, que estouram, e nunca try_strptime, TRY_CAST ou
   errors="coerce", que transformam falha em nulo.
   Ao falhar: diga tabela, coluna e um exemplo do valor que não converteu, e encerre com
   sys.exit(1). Para saber a coluna, cada coluna a converter é testada isoladamente antes de
   gravar (um SELECT por coluna); o valor de exemplo é o que o DuckDB cita na própria
   mensagem de erro.
   Motivo: um nulo fabricado pela conversão fica indistinguível de um nulo verdadeiro do dado,
   para sempre.
   Dinheiro tem uma verificação a mais: antes do CAST, todo valor tem que casar com
   ^[0-9]+(\.[0-9]{1,2})?$; se um valor tiver mais de duas casas, para com a mesma mensagem.
   Motivo: CAST para DECIMAL(10,2) arredonda "1.239" para 1.24 sem avisar, e isso é corrigir
   em silêncio. Auditado: 0 violações nas quatro colunas de dinheiro.
   Inteiro tem a mesma verificação, com ^[0-9]+$ (acrescentada na implementação, ao testar
   que CAST('2.5' AS INTEGER) devolve 3 sem erro). Auditado: 0 violações nas 12 colunas de
   id e em quantidade.
   Se qualquer conversão falhar, nada é gravado em refined (ver item 8).

5. DUPLICATAS
   Chave de cada tabela:
     categorias (categoria_id)   clientes (cliente_id)    produtos (produto_id)
     pedidos (pedido_id)         itens_pedido (item_id)   devolucoes (devolucao_id)
   Linha inteira repetida (comparada sobre a linha completa de raw, inclusive as colunas que
   não vão para refined): mantém uma, e conta quantas saíram.
   Chave repetida com conteúdo diferente: para, mostra a chave e as linhas conflitantes,
   sys.exit(1). Não escolhe uma por conta própria.
   Motivo: escolher em silêncio é decidir sem dizer que decidiu.
   Auditado: 0 linhas inteiras repetidas e 0 chaves repetidas nas seis tabelas.
   Observação (não é regra): item_id é único em devolucoes, ou seja, há no máximo uma
   devolução por item. A transformação não impõe isso.

6. NULOS
   Nenhuma linha é apagada por ter nulo. Nenhum nulo é preenchido.
   Motivo: nulo é informação; rótulo para "sem valor" é decisão de mart. Hoje há 0 nulos em
   todas as colunas, então a regra não age, mas fica escrita para o dia em que o dado mudar.
   Anomalias de negócio também ficam. refined não corrige fato; quem decide o que fazer com
   ele é a pergunta que o mart responde. Auditadas hoje:
     1.658 pedidos sem nenhum item
       838 clientes sem nenhum pedido
        48 pares (pedido, produto) em mais de uma linha de itens_pedido
     1.500 devoluções, todas de itens de pedido Delivered
     4.930 pedidos Canceled ou In Transit com itens (2.429 e 2.501 pedidos; 5.008 e 5.010
           itens): têm valor, mas não são receita (decisão do mart)
   Integridade referencial: 0 órfãos nas cinco ligações (pedidos->clientes, itens->pedidos,
   itens->produtos, devolucoes->itens, produtos->categorias). A transformação não verifica nem
   impõe isso; é critério de aceite desta spec.

7. SAÍDA NA TELA
   Uma linha por tabela, no formato:
     refined.pedidos            9.000 -> 9.000 linhas  (0 duplicatas)
   Onde colunas de raw ficam de fora, uma linha indentada abaixo:
       colunas fora: name, email
   Onde há nulos, uma linha indentada com a coluna e a contagem (hoje nenhuma aparece):
       nulos mantidos: coluna 12, outra_coluna 3
   Linha final com o total. As contagens (entrada, saída, nulos) vêm do banco, milhar separado
   por ponto, sem locale. stdout reconfigurado para utf-8 dentro de main().

8. REEXECUÇÃO E ATOMICIDADE
   refined é criado com CREATE OR REPLACE TABLE, numa única transação: ou as seis tabelas
   mudam, ou nenhuma. Nunca acrescenta. Rodar dez vezes = rodar uma.
   Motivo: falha na quarta tabela não pode deixar refined com metade nova e metade velha.

ERRO
   Antes de transformar, verifica se as seis tabelas de entrada existem em raw. Faltando
   qualquer uma, ou faltando o próprio banco: lista quais, diz para rodar
   "uv run python -m pipeline.ingestao" e encerra com sys.exit(1). Se o arquivo .duckdb não
   existe, não o cria.
   Conversão que falha (item 4) e chave conflitante (item 5): imprimem o descrito e saem com 1.

CRITÉRIOS DE ACEITE
- Seis tabelas em refined; em cada uma, linhas que saem = linhas que entram (com este dado,
  0 duplicatas em todas). Total: 30.806.
- DESCRIBE: ids e quantidade INTEGER; data_cadastro e data_devolucao DATE; preco, custo,
  preco_unitario e valor_reembolso DECIMAL(10,2); o resto VARCHAR. clientes não tem name nem
  email.
- Nulos depois = nulos antes, coluna por coluna (0 em todas).
- Dinheiro bate centavo por centavo com raw:
    sum(preco_unitario) = 429.607.807,71    sum(preco) = 8.553.012,22
    sum(custo) = 6.371.596,23               sum(valor_reembolso) = 128.389.562,98
  e sum(quantidade) = 45.106; cada soma igual à mesma conta com CAST sobre raw.
- Valores de data e id idênticos: min(data_cadastro) = 2026-01-22, max = 2026-02-19;
  data_devolucao = 2026-02-20 nas 1.500 linhas; max(pedido_id) = 9000.
- Integridade referencial: 0 órfãos nas cinco ligações do item 6, medidos em refined.
- Anomalias preservadas em refined: 1.658 pedidos sem item, 838 clientes sem pedido, 48 pares
  (pedido, produto) repetidos.
- Falhas (testadas numa cópia do banco, nunca no original):
    raw.produtos.price com um valor 'abc'  -> imprime tabela, coluna e 'abc', sai com 1,
                                              refined inalterado;
    raw.produtos.price com '1.239'         -> idem (mais de duas casas);
    raw.pedidos com o mesmo pedido_id e status diferente -> mostra a chave e as duas linhas,
                                              sai com 1, refined inalterado;
    raw sem a tabela devolucoes            -> lista a faltante, manda rodar a ingestão, sai com 1.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.

ENTREGA, nesta ordem
1. A spec como docstring no topo do arquivo, dizendo por que cada regra existe, não só o que ela manda.
2. O código, com comentários apenas onde a decisão não é óbvia pelo código.
3. Uma lista final do que você assumiu e que não estava na spec. Se a lista não estiver vazia,
   é a minha spec que precisa melhorar.
