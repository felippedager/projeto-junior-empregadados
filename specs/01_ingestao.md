CONTEXTO
Pipeline de dados em Python sobre um dataset sintético de e-commerce (Faker `en_IN`, 6 CSVs).
Trabalho com spec-driven development: a spec abaixo é a fonte da verdade e o código é
consequência dela. Não acrescente requisito que não esteja escrito aqui. Se algo estiver
ambíguo, pergunte antes de escrever código.

STACK
- Python 3.13, dependências gerenciadas com uv
- DuckDB, arquivo ecommerce.duckdb na raiz do projeto
- pandas (só para ler o CSV como texto e entregar ao DuckDB)
- Nenhum orquestrador. Script executável pela linha de comando.

O QUE JÁ EXISTE (use, não reimplemente)
Etapa 0 (ambiente): pyproject.toml com duckdb, pandas, plotly, streamlit, pytest, pytest-cov, ruff;
pasta raw/ com seis arquivos .csv (categories, customers, products, orders, order_items, returns).
Não existe ainda nenhum arquivo em pipeline/ nem o banco.

ARTEFATOS A PRODUZIR
pipeline/db.py (infraestrutura, sem comando próprio) e pipeline/ingestao.py, executável com:
  uv run python -m pipeline.ingestao

SPEC

1. ESCOPO
   Lê os seis CSVs de raw/, escreve no schema raw do ecommerce.duckdb. Nunca escreve fora de raw.
   Entram todos os seis arquivos; nada fica de fora.
   Motivo: a ingestão é cópia fiel. Decidir o que serve é trabalho da etapa 2.
   Nesta etapa não há renomeação de colunas, conversão de tipo, remoção de duplicata nem
   tratamento de nulo (além do item 4).

2. pipeline/db.py
   Constantes de caminho, calculadas a partir da localização do arquivo db.py:
     RAIZ      pasta raiz do projeto
     BANCO     RAIZ / "ecommerce.duckdb"
     PASTA_RAW RAIZ / "raw"
   Funções:
     conectar(somente_leitura=False)  abre BANCO, criando o arquivo se faltar (somente_leitura=False).
                                      Com somente_leitura=True não cria: se o arquivo não existe,
                                      deixa o erro do DuckDB subir.
     criar_schema(con, nome)          CREATE SCHEMA IF NOT EXISTS
     gravar(con, df, schema, tabela)  CREATE OR REPLACE TABLE a partir do DataFrame; devolve a
                                      contagem lida do banco (SELECT count(*)), não len(df).
   Motivo: os caminhos fixos num só lugar; a contagem vem do banco porque é o que a tela
   promete ao leitor (CLAUDE.md, regra 7). O parâmetro somente_leitura existe para o painel
   (etapa 4) abrir sem travar o pipeline; é a única antecipação, e está aqui porque conectar
   é escrita uma vez só.

3. MAPA ARQUIVO -> TABELA (literal, nomes em português)
     categories.csv   -> raw.categorias
     customers.csv    -> raw.clientes
     products.csv     -> raw.produtos
     orders.csv       -> raw.pedidos
     order_items.csv  -> raw.itens_pedido
     returns.csv      -> raw.devolucoes
   Os nomes das colunas ficam exatamente como no CSV (inglês).
   Motivo: raw é o espelho do arquivo; quem renomeia é a etapa 2, com mapa próprio. Assim, se
   um número de refined parecer estranho, a comparação com o CSV é direta.

4. LEITURA COMO TEXTO
   Cada CSV é lido com pandas: dtype=str, encoding="utf-8" declarado, keep_default_na=False e
   na_values=[""]. Resultado: toda coluna é VARCHAR, e só o campo vazio vira NULL.
   Motivo: sem inferência, "007" não vira 7 e nenhuma conversão acontece sem ser vista. Os
   textos "NA", "null" e "None" são valores reais do arquivo, não nulos; o default do pandas
   os apagaria em silêncio. Auditado: os 6 arquivos são UTF-8 sem BOM e têm 0 campos vazios.

5. VERIFICAÇÃO ANTES DE ABRIR O BANCO (tudo-ou-nada)
   Antes de qualquer conexão, confere para os seis arquivos:
     a) o arquivo existe em raw/;
     b) o cabeçalho tem exatamente as colunas esperadas, na ordem (constante no código, uma
        lista por arquivo, igual ao cabeçalho auditado).
   Se qualquer verificação falhar em qualquer arquivo, nada é gravado e o banco não é aberto
   (nem criado).
   Motivo: ingestão pela metade deixaria um schema raw com algumas tabelas novas e outras
   velhas, indistinguível de uma ingestão completa. O cabeçalho é conferido porque um CSV que
   mudou de colunas é a falha mais provável e a mais silenciosa.

6. GRAVAÇÃO
   criar_schema(con, "raw"), depois uma gravar(...) por tabela. Cada tabela é conferida: a
   contagem devolvida pelo banco tem que ser igual ao número de linhas de dados do DataFrame
   lido. Se diferir, imprime tabela, esperado e obtido, e encerra com sys.exit(1).
   Motivo: é o critério de aceite da etapa, e a falha não pode passar calada.

7. SAÍDA NA TELA
   Uma linha por tabela, nome alinhado, contagem com milhar separado por ponto, sem locale:
     raw.categorias           6 linhas
     raw.clientes         5.000 linhas
     raw.produtos           300 linhas
     raw.pedidos          9.000 linhas
     raw.itens_pedido    15.000 linhas
     raw.devolucoes       1.500 linhas
     Total               30.806 linhas
   Contagens vêm do banco. stdout reconfigurado para utf-8 com sys.stdout.reconfigure
   dentro de main(), nunca no topo do módulo (CLAUDE.md, armadilhas).

REEXECUÇÃO
   CREATE OR REPLACE TABLE, nunca acrescenta. Rodar dez vezes = rodar uma.

ERRO
   Tudo antes de abrir o banco. Para cada falha, imprime e encerra com sys.exit(1):
   - Arquivo faltando: lista todos os que faltam (não só o primeiro) e diz "coloque os CSVs
     em raw/ e rode: uv run python -m pipeline.ingestao".
   - Cabeçalho diferente: arquivo, colunas esperadas e colunas encontradas.
   - Contagem divergente (item 6): tabela, esperado e obtido.

CRITÉRIOS DE ACEITE
- Seis tabelas em raw, com as contagens do item 7 e total 30.806, iguais ao número de linhas de
  dados de cada CSV (contagem de linhas do arquivo menos o cabeçalho).
- DESCRIBE em cada tabela de raw mostra todas as colunas como VARCHAR.
- Nulos em raw: 0 em todas as colunas (igual aos CSVs).
- Rodar duas vezes seguidas imprime exatamente a mesma coisa e as contagens não mudam.
- Com um CSV removido de raw/ (por exemplo orders.csv), o comando imprime a lista de faltantes,
  sai com código 1 e, se o banco ainda não existia, não o cria.
- Com o cabeçalho de um CSV alterado, o comando aponta o arquivo, sai com código 1 e não altera
  o banco.

ENTREGA, nesta ordem
1. A spec como docstring no topo do arquivo, dizendo por que cada regra existe, não só o que ela manda.
2. O código, com comentários apenas onde a decisão não é óbvia pelo código.
3. Uma lista final do que você assumiu e que não estava na spec. Se a lista não estiver vazia,
   é a minha spec que precisa melhorar.
