# MODELO DE SPEC DE UMA ETAPA

Copie este arquivo para `specs/NN_<etapa>.md`, preencha e entregue à IA. Apague os comentários.
Regra de ouro: **toda regra vem com o motivo**. Regra sem motivo vira regra esquecida.
Veja um exemplo completo e já aprovado em `02_transformacao.md`.

---

CONTEXTO
<1 parágrafo: o projeto, o método (spec-driven) e as duas regras: "não acrescente requisito que
não esteja escrito aqui" e "se algo estiver ambíguo, pergunte antes de escrever código".>

STACK
- <Python 3.13, uv, DuckDB, arquivo <nome>.duckdb na raiz>
- <outras dependências desta etapa>

O QUE JÁ EXISTE (use, não reimplemente)
<Funções, schemas e tabelas que a etapa anterior entrega, com nome e assinatura.
Ex.: pipeline/db.py expõe conectar(), criar_schema(con, nome), gravar(con, df, schema, tabela).
O schema raw tem N tabelas, todas VARCHAR, campo vazio como NULL.>

ARTEFATO A PRODUZIR
<caminho do arquivo>, executável com:
  <comando exato>

SPEC

1. ESCOPO
   <Lê de onde, escreve onde. O que entra e o que fica de fora, com o motivo de cada exclusão.>

2. <REGRA>
   <O que fazer.>
   Motivo: <por que a regra existe, de preferência com um número auditado no dado.>

3. <REGRA>
   ...

N. SAÍDA NA TELA
   <Formato exato de cada linha impressa, com um exemplo. De onde vêm as números (do banco).>

REEXECUÇÃO
   <Idempotência: CREATE OR REPLACE, nunca acrescenta. Rodar dez vezes = rodar uma.>

ERRO
   <Pré-requisitos verificados antes de agir. Para cada falha: o que imprimir, qual comando
   sugerir e o código de saída.>

CRITÉRIOS DE ACEITE
- <Cada item verificável por um comando ou uma consulta. Sem adjetivos.>
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.

ENTREGA, nesta ordem
1. A spec como docstring no topo do arquivo, dizendo por que cada regra existe, não só o que ela manda.
2. O código, com comentários apenas onde a decisão não é óbvia pelo código.
3. Uma lista final do que você assumiu e que não estava na spec. Se a lista não estiver vazia,
   é a minha spec que precisa melhorar.
