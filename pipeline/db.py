"""Infraestrutura do banco (etapa 0 do roteiro, entregue junto da etapa 1).

Spec (specs/01_ingestao.md, item 2):

Constantes de caminho, calculadas a partir da localização deste arquivo:
  RAIZ, BANCO (RAIZ/ecommerce.duckdb), PASTA_RAW (RAIZ/raw).
  Motivo: os caminhos moram num só lugar e não dependem do diretório de onde o comando roda.

Funções:
  conectar(somente_leitura=False)  Abre BANCO, criando o arquivo se faltar. Com
      somente_leitura=True não cria: se o arquivo não existe, o erro do DuckDB sobe.
      Motivo: o painel (etapa 4) abre só para ler e não pode criar um banco vazio nem
      segurar o arquivo contra o pipeline.
  criar_schema(con, nome)  CREATE SCHEMA IF NOT EXISTS. Motivo: idempotência.
  gravar(con, df, schema, tabela)  CREATE OR REPLACE TABLE a partir do DataFrame e devolve a
      contagem lida do BANCO (SELECT count(*)), não len(df). Motivo: o número que vai para a
      tela tem que ser o que o banco guardou (CLAUDE.md, regra 7).
"""

from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
BANCO = RAIZ / "ecommerce.duckdb"
PASTA_RAW = RAIZ / "raw"


def conectar(somente_leitura: bool = False) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(BANCO), read_only=somente_leitura)


def criar_schema(con: duckdb.DuckDBPyConnection, nome: str) -> None:
    con.execute(f'CREATE SCHEMA IF NOT EXISTS "{nome}"')


def gravar(
    con: duckdb.DuckDBPyConnection, df: pd.DataFrame, schema: str, tabela: str
) -> int:
    con.register("_df_entrada", df)
    try:
        con.execute(
            f'CREATE OR REPLACE TABLE "{schema}"."{tabela}" AS SELECT * FROM _df_entrada'
        )
    finally:
        con.unregister("_df_entrada")
    # fetchall (e não fetchone): no DuckDB 2.0 fetchone deixa o resultado aberto e a próxima
    # chamada na conexão estoura "unfinished result".
    return con.execute(f'SELECT count(*) FROM "{schema}"."{tabela}"').fetchall()[0][0]
