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
O schema refined, criado pela etapa 2: seis tabelas, 30.806 linhas.
  categorias    (categoria_id INT, nome)
  clientes      (cliente_id INT, data_cadastro DATE, cidade, estado)
  produtos      (produto_id INT, nome, categoria_id INT, preco DEC(10,2), custo DEC(10,2))
  pedidos       (pedido_id INT, cliente_id INT, status, metodo_pagamento)
  itens_pedido  (item_id INT, pedido_id INT, produto_id INT, quantidade INT, preco_unitario DEC(10,2))
  devolucoes    (devolucao_id INT, item_id INT, data_devolucao DATE, valor_reembolso DEC(10,2))
  status tem 3 valores (Canceled, Delivered, In Transit); metodo_pagamento tem 4 (Cash on
  Delivery, Loyalty Points, Net Banking, UPI). Todos em inglês, como no dado.

ARTEFATOS A PRODUZIR
pipeline/marts.py (o orquestrador) e onze arquivos sql/marts/NN_nome.sql, executáveis com:
  uv run python -m pipeline.marts

SPEC

1. ESCOPO
   Lê só de refined, escreve só no schema marts. Nunca escreve em refined nem em raw.
   Cada .sql lê tabelas de refined, nunca de outro mart: assim a ordem dos arquivos não
   importa para o resultado. Motivo: mart que depende de mart esconde a conta em dois lugares.

2. DEFINIÇÕES DE NEGÓCIO (valem para todos os marts; cada SQL repete a conta, não há view)
   - Receita bruta: soma de preco_unitario * quantidade dos itens de pedidos com
     status = 'Delivered'. Pedido Canceled não aconteceu e pedido In Transit ainda não se
     realizou; os dois têm valor, mas não são receita. Hoje: 426.938.559,64 (4.982 itens).
     Para os outros dois status o valor aparece só no mart receita_por_status.
   - Valor devolvido: soma de valor_reembolso das devoluções. Hoje: 128.389.562,98
     (1.500 devoluções). Todas são de itens de pedidos Delivered (0 exceções), então não
     precisa filtrar status; o mart qualidade_dados vigia essa premissa.
   - Receita líquida: receita bruta menos valor devolvido.
   - Margem: (preco_unitario - custo) * quantidade dos mesmos itens da receita bruta, com o
     custo atual de produtos (o dado não guarda o custo no momento da venda). É margem bruta,
     antes das devoluções.
   - "Pedido com item" = tem pelo menos uma linha em itens_pedido. Pedido sem item não tem
     valor e não entra em ticket nem em tamanho de pedido, mas conta nas contagens de
     pedidos por status e por método (status é atributo do pedido, não do item).
   - Taxas e percentuais: fração entre 0 e 1 (0,3007 e não 30,07), arredondada a 4 casas.
     Quem multiplica por 100 e põe o "%" é o painel. Divisão por zero dá NULL (NULLIF), não
     0 nem erro. Motivo: 0 diria "nenhuma devolução", que é uma informação diferente de
     "nada vendido".
   - Dinheiro sai como DECIMAL(18,2), nunca DOUBLE. Divisão de dinheiro (ticket médio) é
     convertida de volta para DECIMAL(18,2) depois de ROUND(.., 2).
   - Pedidos, itens e devoluções são contagens inteiras (BIGINT, o que o count devolve).
   - Rótulo "sem valor": não existe hoje (0 nulos), então nenhum COALESCE.

3. OS ONZE MARTS
   Cada .sql abre com comentários: a pergunta que responde e o grão (uma linha = o quê).
   Cada número que a tela do painel vai mostrar, inclusive os cartões, sai de um destes.
   Ordenação: toda consulta termina com ORDER BY determinístico (desempate pela chave), para
   duas execuções darem as mesmas linhas na mesma ordem.

   01_kpis  -> marts.kpis
     Pergunta: quanto vendemos, quanto devolvemos e qual o ticket médio?
     Grão: uma linha, o negócio inteiro.
     Colunas: receita_bruta, valor_devolvido, receita_liquida, taxa_devolucao (valor
       devolvido / receita bruta), itens_entregues, itens_devolvidos, pedidos_entregues
       (todos os Delivered, com ou sem item), pedidos_entregues_com_item, ticket_medio
       (receita bruta / pedidos_entregues_com_item).
     Motivo do ticket sobre "com item": 528 dos 2.940 pedidos entregues não têm item e
     entrar no denominador diluiria o ticket com pedido de valor zero que é defeito do dado.

   02_receita_por_status  -> marts.receita_por_status
     Pergunta: quanto do valor dos itens está em cada status?
     Grão: um status de pedido (3 linhas).
     Colunas: status, rotulo (Entregue, Cancelado, Em trânsito), pedidos (todos),
       pedidos_com_item, itens, valor_itens, conta_como_receita ('sim' só para Delivered).
     Motivo do rotulo: o dado fica em inglês em refined; traduzir é decisão de mart.
     Motivo do valor_itens em vez de "receita": só a linha Delivered é receita.

   03_receita_por_categoria  -> marts.receita_por_categoria
     Pergunta: qual categoria vende mais?
     Grão: uma categoria (6 linhas).
     Colunas: categoria_id, categoria, itens, quantidade, receita_bruta, participacao
       (receita da categoria / receita bruta total).

   04_margem_por_categoria  -> marts.margem_por_categoria
     Pergunta: qual categoria dá mais margem?
     Grão: uma categoria (6 linhas).
     Colunas: categoria_id, categoria, receita_bruta, custo_total, margem, margem_pct
       (margem / receita bruta).

   05_top_produtos  -> marts.top_produtos
     Pergunta: quais os 10 produtos que mais vendem?
     Grão: um produto, só os 10 de maior receita bruta (desempate: menor produto_id).
     Colunas: posicao (1 a 10), produto_id, nome, categoria, quantidade, receita_bruta.
     Motivo de produto_id junto do nome: 300 produtos dividem 15 nomes, então o nome não
     identifica ninguém. Nada agrupa por nome.

   06_receita_por_estado  -> marts.receita_por_estado
     Pergunta: de quais estados vem a receita?
     Grão: um estado do cliente (28 linhas hoje).
     Colunas: estado, pedidos (entregues com item), receita_bruta, participacao.

   07_receita_por_cidade  -> marts.receita_por_cidade
     Pergunta: quais as 10 cidades que mais compram?
     Grão: uma cidade dentro de um estado, só as 10 de maior receita bruta (desempate:
       estado, depois cidade).
     Colunas: posicao, estado, cidade, pedidos (entregues com item), receita_bruta.
     Motivo do grão (estado, cidade): Udaipur existe em Rajasthan e em Tripura, são cidades
     diferentes. São 84 pares hoje, para 83 nomes.

   08_pagamento_por_metodo  -> marts.pagamento_por_metodo
     Pergunta: como se divide a receita e o cancelamento por método de pagamento?
     Grão: um método de pagamento (4 linhas).
     Colunas: metodo_pagamento, pedidos (todos), pedidos_entregues, pedidos_cancelados,
       taxa_cancelamento (cancelados / pedidos, em todos os pedidos do método),
       receita_bruta.

   09_devolucao_por_categoria  -> marts.devolucao_por_categoria
     Pergunta: qual categoria tem mais devolução?
     Grão: uma categoria (6 linhas).
     Colunas: categoria_id, categoria, itens_entregues, itens_devolvidos, receita_bruta,
       valor_devolvido, taxa_devolucao (valor devolvido / receita bruta da categoria).
     A categoria de uma devolução é a do produto do item devolvido.

   10_tamanho_pedido  -> marts.tamanho_pedido
     Pergunta: quantas linhas de item e que valor tem um pedido típico?
     Grão: um tamanho de pedido, ou seja, o número de linhas de item que o pedido tem
       (1 a 9 hoje), contando só pedidos Delivered com item.
     Colunas: linhas_no_pedido, pedidos, receita_bruta, ticket_medio.
     Motivo de "linhas" e não "unidades": quantidade fica em outra coluna; aqui o que
     importa é quantos itens distintos o cliente pôs no pedido.

   11_qualidade_dados  -> marts.qualidade_dados
     Pergunta: quanto do dado tem anomalia que muda a leitura dos números?
     Grão: uma verificação (6 linhas, em ordem fixa).
     Colunas: verificacao (código), descricao (frase), ocorrencias, base (o que a
       ocorrência é contada contra: ex. total de pedidos), proporcao (ocorrencias / base).
     Verificações, com os valores de hoje:
       pedidos_sem_item                    1.658 de 9.000 pedidos
       clientes_sem_pedido                   838 de 5.000 clientes
       pares_pedido_produto_repetidos         48 de 15.000 itens
       pedidos_entregues_sem_item            528 de 2.940 pedidos entregues
       produtos_com_nome_repetido            300 de 300 produtos (só 15 nomes distintos)
       devolucoes_de_pedido_nao_entregue       0 de 1.500 devoluções
     Motivo: refined guarda as anomalias sem corrigir; este mart é onde elas ficam à vista,
     inclusive a premissa de que toda devolução é de pedido entregue (ver item 2).

4. ORQUESTRADOR pipeline/marts.py
   Executa sql/marts/*.sql em ordem alfabética. Cada arquivo contém uma única consulta
   SELECT (pode abrir com WITH), com ponto e vírgula final opcional; o orquestrador a
   executa como CREATE TABLE marts.<nome> AS <consulta>. O nome da tabela é o do arquivo sem o
   prefixo NN_ e sem .sql.
   Tudo numa única transação: DROP SCHEMA IF EXISTS marts CASCADE, CREATE SCHEMA marts,
   uma tabela por arquivo, COMMIT. Se qualquer coisa falhar, ROLLBACK e marts fica como estava.
   Motivo do DROP: apagar o arquivo faz o mart sumir na execução seguinte; sem o DROP, a
   tabela velha ficaria no banco como mart fantasma.
   Validações, nesta ordem, antes de executar qualquer SQL:
     a) a pasta existe e tem pelo menos um .sql;
     b) todo nome casa com ^[0-9]{2}_[a-z][a-z0-9_]*\.sql$ (prefixo de dois dígitos);
     c) nenhum nome de tabela se repete depois de tirar o prefixo (ex.: 01_a.sql e 02_a.sql).
   Validações durante a execução:
     d) SQL com erro: mostra o arquivo e a mensagem do DuckDB; sai com 1.
     e) mart vazio (0 linhas): mostra o arquivo; sai com 1. Motivo: mart vazio quase sempre é
        filtro errado ou refined vazio, e um painel em branco esconde o erro.

5. SAÍDA NA TELA
   Uma linha por mart, nome alinhado e contagem de linhas vinda do banco, milhar com ponto:
     marts.kpis                          1 linha
     marts.receita_por_status            3 linhas
   Singular para 1, plural para o resto. Linha final: "Total  11 marts". stdout reconfigurado
   para utf-8 dentro de main().

REEXECUÇÃO
   DROP SCHEMA + CREATE na mesma transação; rodar dez vezes = rodar uma.

ERRO
   Antes de agir: banco inexistente ou alguma das seis tabelas de refined faltando: lista o
   que falta, diz para rodar "uv run python -m pipeline.transformacao" e sai com 1, sem
   criar o banco. Validações a), b), c): imprimem o problema e saem com 1 sem tocar no banco.
   Validações d) e e): imprimem o problema, fazem ROLLBACK e saem com 1.

CRITÉRIOS DE ACEITE
- Onze tabelas em marts, uma por arquivo, com o nome do arquivo sem o prefixo.
- Linhas por mart: kpis 1, receita_por_status 3, receita_por_categoria 6,
  margem_por_categoria 6, top_produtos 10, receita_por_estado 28, receita_por_cidade 10,
  pagamento_por_metodo 4, devolucao_por_categoria 6, tamanho_pedido 9, qualidade_dados 6.
- marts.kpis: receita_bruta 426.938.559,64; valor_devolvido 128.389.562,98; receita_liquida
  298.548.996,66; itens_entregues 4.982; itens_devolvidos 1.500; pedidos_entregues 2.940;
  pedidos_entregues_com_item 2.412.
- marts.receita_por_status: Delivered 426.938.559,64, Canceled 429.288.624,37,
  In Transit 430.078.692,12; pedidos 2.940, 3.009 e 3.051.
- Somas que fecham com kpis.receita_bruta, centavo por centavo: receita_por_categoria,
  receita_por_estado e pagamento_por_metodo (a soma de todas as linhas); tamanho_pedido
  (soma de todas as linhas). top_produtos e receita_por_cidade somam menos que o total
  (são top 10).
- Somas de devolvido: devolucao_por_categoria soma valor_devolvido = 128.389.562,98 e
  itens_devolvidos = 1.500.
- Tipos: todo campo de dinheiro DECIMAL(18,2), nenhum DOUBLE em dinheiro.
- Cada .sql começa com os comentários de pergunta e grão (conferido por leitura).
- top_produtos: posicao 1 é o produto 264 (Bluetooth speaker), receita 4.387.486,56.
  receita_por_cidade: posicao 1 é Rourkela (Odisha), 9.036.184,83.
- qualidade_dados traz as seis ocorrências do item 3.
- Apagar um .sql (numa cópia do projeto) e rodar de novo faz o mart sumir do banco.
- Falhas (numa cópia do projeto, nunca no original), cada uma com código 1:
    sql/marts com nome sem prefixo (ex.: kpis.sql)              -> validação b);
    dois arquivos com o mesmo nome depois do prefixo            -> validação c);
    um .sql com erro de sintaxe                                 -> validação d), marts como estava;
    um .sql com WHERE 1 = 0                                     -> validação e), marts como estava;
    refined sem a tabela devolucoes                             -> lista a faltante, manda rodar
                                                                   a transformação.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.

ENTREGA, nesta ordem
1. A spec como docstring no topo de pipeline/marts.py, dizendo por que cada regra existe, não
   só o que ela manda; e os comentários de pergunta e grão no topo de cada .sql.
2. O código, com comentários apenas onde a decisão não é óbvia pelo código.
3. Uma lista final do que você assumiu e que não estava na spec. Se a lista não estiver vazia,
   é a minha spec que precisa melhorar.
