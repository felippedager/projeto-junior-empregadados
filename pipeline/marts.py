"""Etapa 3: marts. Roda sql/marts/NN_nome.sql e grava marts.<nome> em ecommerce.duckdb.

Comando: uv run python -m pipeline.marts

Spec (specs/03_marts.md), com o motivo de cada regra:

1. ESCOPO. Lê só de refined, escreve só no schema marts. Cada .sql lê refined, nunca outro
   mart. Motivo: mart que depende de mart esconde a conta em dois lugares, e a ordem dos
   arquivos deixa de importar para o resultado.

2. DEFINIÇÕES (vivem nos .sql, não aqui: regra de negócio mora no SQL).
   Receita = itens de pedidos Delivered (Canceled não aconteceu, In Transit não se realizou).
   Taxas são fração de 0 a 1; divisão por zero dá NULL, não 0 (0 diria "nenhuma devolução",
   NULL diz "nada vendido"). Dinheiro é DECIMAL(18,2), nunca DOUBLE.

3. ORQUESTRADOR. Executa sql/marts/*.sql em ordem alfabética. Cada arquivo é uma única
   consulta SELECT (pode abrir com WITH; ponto e vírgula final opcional) que vira
   CREATE TABLE marts.<nome> AS <consulta>; o nome é o do arquivo sem NN_ e sem .sql.
   Tudo numa transação: DROP SCHEMA IF EXISTS marts CASCADE, CREATE SCHEMA, uma tabela por
   arquivo, COMMIT; qualquer falha faz ROLLBACK e marts fica como estava.
   Motivo do DROP: apagar o arquivo faz o mart sumir na execução seguinte; sem ele a tabela
   velha ficaria no banco como mart fantasma.

   Validações antes de executar qualquer SQL (não tocam o banco):
     a) a pasta existe e tem pelo menos um .sql;
     b) todo nome casa com ^[0-9]{2}_[a-z][a-z0-9_]*\\.sql$;
     c) nenhum nome de tabela se repete depois de tirar o prefixo.
   Durante a execução:
     d) SQL com erro: mostra arquivo e mensagem do DuckDB, ROLLBACK, sai com 1;
     e) mart vazio: mostra o arquivo, ROLLBACK, sai com 1. Motivo: mart vazio quase sempre é
        filtro errado ou refined vazio, e um painel em branco esconde o erro.

5. SAÍDA. Uma linha por mart com a contagem lida do banco (milhar com ponto; singular para 1)
   e "Total  N marts". stdout em utf-8 dentro de main().

REEXECUÇÃO. DROP + CREATE na mesma transação: rodar dez vezes = rodar uma.

ERRO. Banco inexistente ou tabela de refined faltando: lista o que falta, manda rodar
"uv run python -m pipeline.transformacao", sai com 1, sem criar o banco.
"""

import re
import sys
from pathlib import Path

import duckdb

from pipeline.db import BANCO, RAIZ, conectar

PASTA_SQL = RAIZ / "sql" / "marts"
ORIGEM = "refined"
DESTINO = "marts"
TABELAS_ORIGEM = [
    "categorias",
    "clientes",
    "produtos",
    "pedidos",
    "itens_pedido",
    "devolucoes",
]
PADRAO_ARQUIVO = re.compile(r"^[0-9]{2}_([a-z][a-z0-9_]*)\.sql$")


def milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def falhar(*linhas: str) -> None:
    for linha in linhas:
        print(linha)
    sys.exit(1)


def verificar_entrada() -> None:
    if BANCO.is_file():
        con = conectar(somente_leitura=True)
        try:
            existentes = {
                t
                for (t,) in con.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
                    [ORIGEM],
                ).fetchall()
            }
        finally:
            con.close()
    else:
        existentes = set()
    faltando = [t for t in TABELAS_ORIGEM if t not in existentes]
    if faltando:
        falhar(
            f"Faltam tabelas em {ORIGEM}: " + ", ".join(faltando),
            "Rode: uv run python -m pipeline.transformacao",
        )


def listar_arquivos() -> list[tuple[str, Path]]:
    """Validações a), b) e c). Devolve (nome do mart, caminho) em ordem alfabética."""
    arquivos = sorted(PASTA_SQL.glob("*.sql")) if PASTA_SQL.is_dir() else []
    if not arquivos:
        falhar(f"Nenhum arquivo .sql em {PASTA_SQL.relative_to(RAIZ)}/.")

    invalidos = [a.name for a in arquivos if not PADRAO_ARQUIVO.match(a.name)]
    if invalidos:
        falhar(
            "Nome de arquivo fora do padrão NN_nome.sql (dois dígitos, _, minúsculas): "
            + ", ".join(invalidos)
        )

    por_nome: dict[str, list[str]] = {}
    for a in arquivos:
        por_nome.setdefault(PADRAO_ARQUIVO.match(a.name).group(1), []).append(a.name)
    repetidos = {n: fs for n, fs in por_nome.items() if len(fs) > 1}
    if repetidos:
        falhar(
            *[
                f"Mais de um arquivo gera marts.{n}: " + ", ".join(fs)
                for n, fs in repetidos.items()
            ]
        )
    return [(PADRAO_ARQUIVO.match(a.name).group(1), a) for a in arquivos]


def consulta(arquivo: Path) -> str:
    texto = arquivo.read_text(encoding="utf-8").strip()
    return texto.removesuffix(";").rstrip()


def construir(con: duckdb.DuckDBPyConnection, arquivos: list[tuple[str, Path]]) -> list[tuple[str, int]]:
    resultado = []
    con.execute("BEGIN")
    try:
        con.execute(f"DROP SCHEMA IF EXISTS {DESTINO} CASCADE")
        con.execute(f"CREATE SCHEMA {DESTINO}")
        for nome, arquivo in arquivos:
            try:
                con.execute(f"CREATE TABLE {DESTINO}.{nome} AS {consulta(arquivo)}")
            except duckdb.Error as erro:
                falhar(f"Erro no SQL de {arquivo.name}:", f"  {erro}")
            linhas = con.execute(f"SELECT count(*) FROM {DESTINO}.{nome}").fetchall()[0][0]
            if linhas == 0:
                falhar(f"Mart vazio: {arquivo.name} não devolveu nenhuma linha.")
            resultado.append((nome, linhas))
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return resultado


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    verificar_entrada()
    arquivos = listar_arquivos()
    con = conectar()
    try:
        resultado = construir(con, arquivos)
    finally:
        con.close()

    for nome, linhas in resultado:
        unidade = "linha" if linhas == 1 else "linhas"
        print(f"{DESTINO + '.' + nome:<34}{milhar(linhas):>6} {unidade}")
    print(f"Total  {len(resultado)} marts")


if __name__ == "__main__":
    main()
