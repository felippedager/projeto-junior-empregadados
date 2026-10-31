# Pipeline E-commerce Índia

Pipeline de dados em Python sobre um dataset sintético de e-commerce (gerado com Faker `en_IN`;
6 CSVs em `raw/`: categories, customers, products, orders, order_items, returns).
Trabalho em *spec-driven development*.

## Método (vale para toda tarefa)
- A spec é a fonte da verdade; o código é consequência dela.
- **Não acrescente requisito que não esteja escrito na spec.**
- Se algo estiver ambíguo, **pergunte antes de escrever código**.
- Não reimplemente o que a seção "O QUE JÁ EXISTE" da spec manda usar.
- Ao entregar: (1) a spec como docstring no topo do arquivo, com o **motivo** de cada regra;
  (2) o código, comentado só onde a decisão não é óbvia; (3) lista do que você assumiu
  e que não estava na spec.
- Antes de escrever uma spec nova, leia `specs/modelo_etapa.md` e um exemplo em `specs/exemplos/`.

## Stack
Python 3.13, `uv`, DuckDB (`ecommerce.duckdb` na raiz). Sem orquestrador: cada etapa é um
script de linha de comando.

## Etapas, em ordem (ver `specs/roteiro.md`)
```
raw/*.csv -> [1 ingestão] -> schema raw -> [2 transformação] -> schema refined
 -> [3 marts] -> schema marts -> [4 painel/app] e [5 relatório HTML]      [6 testes cobrem tudo]
```
| # | Arquivo | Comando |
|---|---|---|
| 0 | `pipeline/db.py` | (infraestrutura: `conectar`, `criar_schema`, `gravar`) |
| 1 | `pipeline/ingestao.py` | `uv run python -m pipeline.ingestao` |
| 2 | `pipeline/transformacao.py` | `uv run python -m pipeline.transformacao` |
| 3 | `pipeline/marts.py` + `sql/marts/NN_nome.sql` | `uv run python -m pipeline.marts` |
| 4 | `painel.py` + `app.py` | `uv run streamlit run app.py` |
| 5 | `relatorio.py` | `uv run python relatorio.py` |
| 6 | `test/test_<modulo>.py` | `uv run pytest --cov` |

## Regras que se repetem em todas as etapas
1. **Docstring no topo** de cada arquivo com a spec e o motivo de cada regra.
2. **Camadas isoladas:** cada etapa lê só da anterior e escreve só na sua. Nunca altera o que vem antes.
3. **Idempotente:** `CREATE OR REPLACE`. Rodar dez vezes = rodar uma.
4. **Pré-requisito verificado antes de agir:** se falta algo, liste o que falta, diga qual comando
   rodar e encerre com `sys.exit(1)`.
5. **Falhar alto, nunca corrigir em silêncio:** conversão que falha, chave repetida com conteúdo
   diferente e mart vazio param tudo. Nada de `try_strptime`, `TRY_CAST` ou `errors="coerce"`.
6. **Regra de negócio mora no SQL.** O Python só orquestra, lê e formata. Painel e relatório
   não calculam (nada de agrupar, somar, tirar média, juntar tabelas): número novo = mart novo.
7. **Contagem vem do banco**, não do DataFrame. Milhar com ponto, decimal com vírgula, sem `locale`.
8. **Nulo é informação:** não apague linha por ter nulo, não preencha nulo. Rótulo para "sem valor"
   é decisão de mart.
9. **Marts:** um arquivo `NN_nome.sql` = uma tabela `marts.nome`; schema recriado numa transação única.
10. **Cada spec traz critérios de aceite verificáveis**, e a entrega é conferida contra eles.

## Testes
- Nunca abrir o `.duckdb` do projeto nem ler `raw/`. Tudo em `tmp_path`, com CSV `.csv`
  minúsculos escritos pelo próprio teste e DuckDB de verdade (nada de mock do banco).
- Entrada inventada, com um comentário em cada linha dizendo por que ela existe. O valor
  esperado sai da conta feita sobre essa entrada, **nunca de um número medido no dado real**.
- Nome do teste é a frase que ele prova: `test_cancelado_fica_fora_da_receita`.
- Só fixtures `tmp_path` e `monkeypatch`. Proibido: teste sem assert, `skip`, `xfail`,
  `try/except` em volta de assert, `pytest.approx` em dinheiro.
- Depois de escrever os testes, **faça mutação**: quebre uma regra numa cópia do projeto e confirme
  que algum teste falha. Cobertura sozinha não prova nada.
- Config do pytest e do coverage em `snippets/pyproject_testes.toml`.

## Armadilhas conhecidas
- **`sys.stdout` no import:** não faça `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, ...)` no
  topo do módulo. Dentro do pytest isso fecha o buffer de captura e derruba a sessão
  (`ValueError: I/O operation on closed file`). Use `sys.stdout.reconfigure(encoding="utf-8")`
  dentro de `main()`.
- **Conexão DuckDB aberta segura o arquivo:** o painel abre com `read_only=True` e fecha dentro da
  função de leitura (`finally: con.close()`), para o pipeline poder gravar com o painel de pé.
- **Ambiente quebrado:** se `uv run` reclamar de `pyvenv.cfg`, apague a `.venv` e rode `uv sync`.
- **Arquivos gerados** (`.coverage`, `.pytest_cache`, `*.duckdb`) ficam no `.gitignore`.
