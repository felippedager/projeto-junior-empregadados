# Pipeline E-commerce Índia

Pipeline de dados em Python sobre um dataset **sintético** de e-commerce (gerado com Faker `en_IN`):
seis CSVs entram, passam por três camadas num banco DuckDB e saem como onze tabelas prontas para
responder perguntas de negócio, mais um relatório HTML.

O projeto foi feito em *spec-driven development*: cada etapa tem uma spec em `specs/` (regra +
motivo + critérios de aceite), e o código é consequência dela. Os testes cobrem tudo.

## Como rodar

Pré-requisito: [uv](https://docs.astral.sh/uv/). O `uv` instala o Python 3.13 e as dependências.

```
uv sync                                  # instala o ambiente

uv run python -m pipeline.ingestao       # 1. raw/*.csv        -> schema raw
uv run python -m pipeline.transformacao  # 2. raw              -> schema refined
uv run python -m pipeline.marts          # 3. refined          -> schema marts (11 tabelas)

uv run python relatorio.py               # 4. marts            -> relatorio.html

uv run pytest --cov                      # 5. testes e cobertura
```

As etapas são independentes e idempotentes: rodar dez vezes dá o mesmo resultado que rodar uma.
Cada uma confere o que precisa antes de agir e, se faltar algo, diz qual comando rodar.

O resultado fica em `ecommerce.duckdb`, na raiz.

## Os dados

Os seis CSVs ficam em `raw/` e **são versionados** (cerca de 1 MB no total). As contagens abaixo são
as desses arquivos:

| Arquivo | Linhas | O que é |
|---|---:|---|
| `categories.csv` | 6 | categorias de produto |
| `customers.csv` | 5.000 | clientes (cidade e estado) |
| `products.csv` | 300 | produtos, com preço e custo |
| `orders.csv` | 9.000 | pedidos, com status e método de pagamento |
| `order_items.csv` | 15.000 | itens de cada pedido |
| `returns.csv` | 1.500 | devoluções |

`dataset/Data_Extraction.py` é o script que gera esse dado. Ele não usa semente e a exportação dos
CSVs está comentada, então **gerar de novo produz números diferentes**: é por isso que os CSVs de
`raw/` ficam no repositório, como fonte única dos números. Como o dado é sintético e sorteado, não
há tendência nem correlação: as barras dos gráficos saem quase do mesmo tamanho.

O dado não tem data de pedido, frete, desconto nem moeda declarada. Por isso não há série temporal,
e os valores são exibidos em dólar (US$) por convenção de exibição, sem conversão.

## Arquitetura

```
raw/*.csv ──[1 ingestão]──▶ schema raw ──[2 transformação]──▶ schema refined ──[3 marts]──▶ schema marts
                                                                                                  │
                                                                                                  ▼
                                                                                         [4 relatório HTML]
```

| Camada | O que faz |
|---|---|
| **raw** | Cópia fiel dos CSVs, tudo como texto (`VARCHAR`). Só o campo vazio vira `NULL`; `"NA"` continua texto. |
| **refined** | Nomes em português, tipos estritos (id `INTEGER`, data `DATE`, dinheiro `DECIMAL(10,2)`), linha repetida removida e contada. Não corrige fato: anomalia fica. |
| **marts** | Onze tabelas, uma por pergunta de negócio. Toda a regra de negócio mora no SQL (`sql/marts/NN_nome.sql`). |

Regras que valem em todas as etapas:

- **Camadas isoladas:** cada etapa lê só da anterior e escreve só na sua.
- **Falhar alto:** conversão que falha, chave repetida com conteúdo diferente e mart vazio param tudo.
  Nada de `TRY_CAST`: um nulo ou arredondamento fabricado seria indistinguível do dado.
- **Nulo é informação:** nenhuma linha é apagada por ter nulo, nenhum nulo é preenchido.
- **O relatório não calcula:** só lê os marts. Número novo = mart novo.
- **Contagens vêm do banco**, com milhar separado por ponto e decimal por vírgula, sem `locale`.

## Os onze marts

| Mart | Pergunta que responde |
|---|---|
| `kpis` | Quanto vendemos, quanto devolvemos, qual o ticket médio? |
| `receita_por_status` | Quanto do valor dos itens está em cada status? |
| `receita_por_categoria` | Qual categoria vende mais? |
| `margem_por_categoria` | Qual categoria dá mais margem? |
| `top_produtos` | Quais os 10 produtos que mais vendem? |
| `receita_por_estado` | De quais estados vem a receita? |
| `receita_por_cidade` | Quais as 10 cidades que mais compram? |
| `pagamento_por_metodo` | Como se divide receita e cancelamento por método de pagamento? |
| `devolucao_por_categoria` | Qual categoria tem mais devolução? |
| `tamanho_pedido` | Quantas linhas de item e que valor tem um pedido típico? |
| `qualidade_dados` | Quanto do dado tem anomalia que muda a leitura dos números? |

Definições de negócio (valem em todos):

- **Receita** é só de itens de pedidos `Delivered`. Pedido `Canceled` não aconteceu e `In Transit`
  ainda não se realizou: têm valor, mas não são receita (aparecem em `receita_por_status`).
- **Receita líquida** = receita bruta − valor devolvido.
- **Margem** = (preço − custo) × quantidade, com o custo atual do produto (o dado não guarda o
  custo na hora da venda), antes das devoluções.
- **Ticket médio** = receita bruta / pedidos entregues **com item**. Pedido entregue sem item tem
  valor zero por defeito do dado e não entra na divisão.
- Taxas são fração entre 0 e 1; divisão por zero dá `NULL`, não 0.

Anomalias do dado que o pipeline **mantém** e o mart `qualidade_dados` expõe: pedidos sem item,
clientes sem pedido, pares (pedido, produto) em mais de uma linha, pedidos entregues sem item e
nomes de produto repetidos (poucos nomes para 300 produtos).

## Estrutura do projeto

```
pipeline/
  db.py              conectar, criar_schema, gravar; caminhos do banco e de raw/
  ingestao.py        etapa 1
  transformacao.py   etapa 2
  marts.py           etapa 3: roda sql/marts/*.sql numa transação única
sql/marts/           um arquivo NN_nome.sql = uma tabela marts.nome
painel.py            leitura dos marts, formatos (US$, %, milhar) e uma função por gráfico;
                     o relatório reaproveita tudo isso
relatorio.py         gera relatorio.html (plotly por CDN, ids de gráfico fixos)
test/                um arquivo por módulo, mais apoio.py com a entrada inventada
specs/               uma spec por etapa (01 a 06), o roteiro e o modelo de spec
raw/                 os 6 CSVs
dataset/             o gerador do dado (Data_Extraction.py)
```

## Relatório

`relatorio.html` é um arquivo só, com seis faixas: números do negócio, status e pagamento,
categorias, estado e cidade, tamanho do pedido e qualidade dos dados. O plotly.js vem de CDN, então
ver os gráficos exige internet; texto, cartões e tabela aparecem sem ela. Rodar duas vezes muda só
a linha do rodapé ("Gerado em ..."). O banco é aberto só para leitura e fechado em seguida.

## Testes

```
uv run pytest            # roda a suíte
uv run pytest --cov      # com cobertura; falha se ficar abaixo de 90%
uv run pytest -k marts   # só os testes cujo nome contém "marts"
```

- Nunca abrem `ecommerce.duckdb` nem leem `raw/`: tudo roda em pasta temporária, com CSVs
  minúsculos escritos pelo próprio teste e DuckDB de verdade (sem mock do banco).
- A entrada é inventada, e o valor esperado de cada teste sai de uma conta feita à mão sobre ela,
  nunca de um número medido no dado real. Os SQLs reais dos marts rodam sobre essa entrada.
- O nome de cada teste é a frase que ele prova, por exemplo
  `test_cancelado_e_em_transito_ficam_fora_da_receita`.
- Além da cobertura, as regras foram validadas por **mutação**: 16 regras foram quebradas, uma por
  vez, numa cópia do projeto, e a suíte falhou em todas.
- Não é testado o visual do relatório no navegador, só a estrutura do HTML.

## Método

Cada etapa segue o mesmo ciclo: escrever a spec (`specs/NN_nome.md`: regra + motivo + critérios de
aceite verificáveis), aprovar, implementar com a spec como docstring no topo do arquivo, verificar
cada critério contra o dado e listar o que foi assumido e não estava na spec. As regras do método e
as armadilhas conhecidas estão em `CLAUDE.md`; a ordem das etapas está em `specs/roteiro.md`.
