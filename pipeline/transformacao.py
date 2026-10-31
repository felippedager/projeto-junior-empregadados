"""Etapa 2: transformação. Lê o schema raw e grava o schema refined de ecommerce.duckdb.

Comando: uv run python -m pipeline.transformacao

Spec (specs/02_transformacao.md), com o motivo de cada regra:

1. ESCOPO. Lê de raw, escreve em refined, nunca em raw. Entram as seis tabelas (categorias,
   clientes, produtos, pedidos, itens_pedido, devolucoes): todas servem a algum mart.
   Fora: clientes.name e clientes.email. Motivo: nenhuma pergunta de mart usa, são dado
   pessoal e 22 e-mails se repetem entre clientes diferentes (não identificam ninguém).
   Continuam em raw.

2. NOMES. Português, snake_case, mapa literal em TABELAS abaixo. Nenhuma coluna fora do mapa
   além das duas do item 1. Motivo: é o vocabulário digitado de memória nos JOINs dos marts.

3. TIPOS.
   - Ids (*_id) e quantidade: INTEGER. Motivo: sequenciais de 1 a N, 0 ocorrências de zero à
     esquerda em 12 colunas de id; nada se perde. Se um id vier com zero à esquerda, esta
     regra deve voltar para VARCHAR.
   - Datas (data_cadastro, data_devolucao): DATE, formato '%Y-%m-%d'. Motivo: o dado só tem
     dia; guardar hora seria inventar precisão.
   - Dinheiro (preco, custo, preco_unitario, valor_reembolso): DECIMAL(10,2). Motivo: DOUBLE
     não guarda centavos com exatidão e soma de dinheiro tem que fechar.
   - Resto: VARCHAR, valores em inglês como no dado. Traduzir rótulo é decisão de mart.
   - Conversão em SQL (CAST, strptime): o dado já está no banco.

4. CONVERSÃO QUE FALHA. Para tudo, com CAST e strptime, nunca TRY_CAST, try_strptime ou
   errors="coerce". Mostra tabela, coluna e um exemplo do valor, sai com 1. Cada coluna é
   testada isoladamente antes de gravar, para saber qual falhou; o valor de exemplo é o que o
   DuckDB cita na própria mensagem. Dinheiro: antes do CAST, todo valor tem que casar com
   ^[0-9]+(\\.[0-9]{1,2})?$; inteiro, com ^[0-9]+$. Motivo: um nulo fabricado pela conversão
   fica indistinguível de um nulo verdadeiro para sempre; e CAST arredonda em silêncio
   ("1.239" para DECIMAL(10,2) vira 1.24; "2.5" para INTEGER vira 3), o que é corrigir sem avisar.

5. DUPLICATAS. Chave: categorias (categoria_id), clientes (cliente_id), produtos
   (produto_id), pedidos (pedido_id), itens_pedido (item_id), devolucoes (devolucao_id).
   Linha inteira repetida (comparada sobre a linha completa de raw, inclusive colunas que não
   vão para refined): mantém uma e conta quantas saíram. Chave repetida com conteúdo
   diferente: para, mostra a chave e as linhas, sai com 1. Motivo: escolher em silêncio é
   decidir sem dizer que decidiu.

6. NULOS. Nenhuma linha é apagada por ter nulo, nenhum nulo é preenchido; anomalias de
   negócio ficam (pedido sem item, cliente sem pedido, pedido cancelado com itens...).
   Motivo: nulo é informação e refined não corrige fato; quem decide é o mart.

7. SAÍDA. Uma linha por tabela (entrada -> saída, duplicatas), com "colunas fora" e
   "nulos mantidos" indentados quando existirem, e uma linha de total. Contagens vêm do
   banco, milhar com ponto. stdout em utf-8 dentro de main().

8. REEXECUÇÃO E ATOMICIDADE. CREATE OR REPLACE TABLE numa única transação: as seis tabelas
   mudam ou nenhuma muda. Motivo: falha na quarta tabela não pode deixar refined meio novo,
   meio velho. Rodar dez vezes = rodar uma.

ERRO. Banco ou tabela de raw faltando: lista o que falta, manda rodar
"uv run python -m pipeline.ingestao", sai com 1 (sem criar o banco). Conversão que falha e
chave conflitante: imprimem o descrito e saem com 1.
"""

import re
import sys

import duckdb

from pipeline.db import BANCO, conectar, criar_schema

ORIGEM = "raw"
DESTINO = "refined"

INT = "INTEGER"
DATA = "DATE"
DIN = "DECIMAL(10,2)"
TXT = "VARCHAR"

# tabela -> (coluna que é a chave em refined, [(coluna em raw, coluna em refined, tipo)])
TABELAS = {
    "categorias": (
        "categoria_id",
        [("category_id", "categoria_id", INT), ("category_name", "nome", TXT)],
    ),
    "clientes": (
        "cliente_id",
        [
            ("customer_id", "cliente_id", INT),
            ("signup_date", "data_cadastro", DATA),
            ("city", "cidade", TXT),
            ("state", "estado", TXT),
        ],
    ),
    "produtos": (
        "produto_id",
        [
            ("product_id", "produto_id", INT),
            ("product_name", "nome", TXT),
            ("category_id", "categoria_id", INT),
            ("price", "preco", DIN),
            ("cost_price", "custo", DIN),
        ],
    ),
    "pedidos": (
        "pedido_id",
        [
            ("order_id", "pedido_id", INT),
            ("customer_id", "cliente_id", INT),
            ("order_status", "status", TXT),
            ("payment_method", "metodo_pagamento", TXT),
        ],
    ),
    "itens_pedido": (
        "item_id",
        [
            ("order_item_id", "item_id", INT),
            ("order_id", "pedido_id", INT),
            ("product_id", "produto_id", INT),
            ("quantity", "quantidade", INT),
            ("unit_price", "preco_unitario", DIN),
        ],
    ),
    "devolucoes": (
        "devolucao_id",
        [
            ("return_id", "devolucao_id", INT),
            ("order_item_id", "item_id", INT),
            ("return_date", "data_devolucao", DATA),
            ("refund_amount", "valor_reembolso", DIN),
        ],
    ),
}

# CAST arredonda em silêncio ("1.239" -> 1.24, "2.5" -> 3), então inteiro e dinheiro passam
# primeiro por um formato estrito.
FORMATO_ESTRITO = {
    DIN: (r"^[0-9]+(\.[0-9]{1,2})?$", "dinheiro com até 2 casas decimais"),
    INT: (r"^[0-9]+$", "número inteiro"),
}


def milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def expressao(coluna: str, tipo: str) -> str:
    """SQL que converte a coluna de raw (VARCHAR) para o tipo de refined, de forma estrita."""
    if tipo == TXT:
        return f'"{coluna}"'
    if tipo == DATA:
        return f"CAST(strptime(\"{coluna}\", '%Y-%m-%d') AS DATE)"
    return f'CAST("{coluna}" AS {tipo})'


def um(con: duckdb.DuckDBPyConnection, sql: str, params=None):
    return con.execute(sql, params or []).fetchall()[0][0]


def falhar(*linhas: str) -> None:
    for linha in linhas:
        print(linha)
    sys.exit(1)


def verificar_entrada() -> None:
    """Banco e seis tabelas de raw têm que existir; sem criar o banco se ele faltar."""
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
    faltando = [t for t in TABELAS if t not in existentes]
    if faltando:
        falhar(
            f"Faltam tabelas em {ORIGEM}: " + ", ".join(faltando),
            "Rode: uv run python -m pipeline.ingestao",
        )


def testar_conversoes(con: duckdb.DuckDBPyConnection) -> None:
    for tabela, (_, colunas) in TABELAS.items():
        for raw_col, nova, tipo in colunas:
            formato = FORMATO_ESTRITO.get(tipo)
            if formato:
                regex, descricao = formato
                ruim = con.execute(
                    f'SELECT "{raw_col}" FROM {ORIGEM}.{tabela} '
                    f'WHERE "{raw_col}" IS NOT NULL AND NOT regexp_matches("{raw_col}", ?) LIMIT 1',
                    [regex],
                ).fetchall()
                if ruim:
                    falhar(
                        f"Conversão falhou em {ORIGEM}.{tabela}.{raw_col} ({tipo}): "
                        f"valor '{ruim[0][0]}' não é {descricao}."
                    )
            if tipo == TXT:
                continue
            try:
                # count() força o DuckDB a avaliar a conversão em todas as linhas.
                um(con, f"SELECT count({expressao(raw_col, tipo)}) FROM {ORIGEM}.{tabela}")
            except duckdb.Error as erro:
                achado = re.search(r"""['"]([^'"]*)['"]""", str(erro))
                exemplo = achado.group(1) if achado else str(erro)
                falhar(
                    f"Conversão falhou em {ORIGEM}.{tabela}.{raw_col} (para {tipo}): "
                    f"valor '{exemplo}'."
                )


def testar_chaves(con: duckdb.DuckDBPyConnection) -> None:
    for tabela, (chave, colunas) in TABELAS.items():
        raw_chave = next(r for r, n, _ in colunas if n == chave)
        conflitantes = con.execute(
            f'SELECT "{raw_chave}" FROM (SELECT DISTINCT * FROM {ORIGEM}.{tabela}) '
            f'GROUP BY "{raw_chave}" HAVING count(*) > 1 ORDER BY 1 LIMIT 5'
        ).fetchall()
        if conflitantes:
            linhas = [f"Chave repetida com conteúdo diferente em {ORIGEM}.{tabela} ({raw_chave}):"]
            for (valor,) in conflitantes:
                linhas.append(f"  {raw_chave} = {valor}")
                for linha in con.execute(
                    f'SELECT DISTINCT * FROM {ORIGEM}.{tabela} WHERE "{raw_chave}" = ?', [valor]
                ).fetchall():
                    linhas.append(f"    {linha}")
            falhar(*linhas)


def transformar(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Grava as seis tabelas numa transação e confere nulos; devolve os números da tela."""
    resultado = []
    con.execute("BEGIN")
    try:
        criar_schema(con, DESTINO)
        for tabela, (chave, colunas) in TABELAS.items():
            selecao = ", ".join(f'{expressao(r, t)} AS "{n}"' for r, n, t in colunas)
            # ORDER BY pela chave: SELECT DISTINCT não garante ordem, e a saída tem que ser estável.
            con.execute(
                f"CREATE OR REPLACE TABLE {DESTINO}.{tabela} AS "
                f"SELECT {selecao} FROM (SELECT DISTINCT * FROM {ORIGEM}.{tabela}) "
                f'ORDER BY "{chave}"'
            )
            entrada = um(con, f"SELECT count(*) FROM {ORIGEM}.{tabela}")
            saida = um(con, f"SELECT count(*) FROM {DESTINO}.{tabela}")
            nulos = {}
            for raw_col, nova, _ in colunas:
                antes = um(con, f'SELECT count(*) FROM {ORIGEM}.{tabela} WHERE "{raw_col}" IS NULL')
                depois = um(con, f'SELECT count(*) FROM {DESTINO}.{tabela} WHERE "{nova}" IS NULL')
                # Sem duplicatas (caso real) os nulos têm que ser iguais; com linha repetida
                # removida, só pode diminuir. Aumentar significaria nulo fabricado.
                if depois > antes:
                    falhar(f"Nulos aumentaram em {DESTINO}.{tabela}.{nova}: {antes} -> {depois}.")
                if depois:
                    nulos[nova] = depois
            mapeadas = {r for r, _, _ in colunas}
            fora = [
                c
                for (c,) in con.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
                    [ORIGEM, tabela],
                ).fetchall()
                if c not in mapeadas
            ]
            resultado.append(
                {"tabela": tabela, "entrada": entrada, "saida": saida, "nulos": nulos, "fora": fora}
            )
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return resultado


def imprimir(resultado: list[dict]) -> None:
    for r in resultado:
        dup = r["entrada"] - r["saida"]
        print(
            f"{DESTINO + '.' + r['tabela']:<22}{milhar(r['entrada']):>7} -> "
            f"{milhar(r['saida']):>7} linhas  ({milhar(dup)} duplicatas)"
        )
        if r["fora"]:
            print(f"    colunas fora: {', '.join(r['fora'])}")
        if r["nulos"]:
            print("    nulos mantidos: " + ", ".join(f"{c} {milhar(n)}" for c, n in r["nulos"].items()))
    ent = sum(r["entrada"] for r in resultado)
    sai = sum(r["saida"] for r in resultado)
    print(f"{'Total':<22}{milhar(ent):>7} -> {milhar(sai):>7} linhas  ({milhar(ent - sai)} duplicatas)")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    verificar_entrada()
    con = conectar()
    try:
        testar_conversoes(con)
        testar_chaves(con)
        resultado = transformar(con)
    finally:
        con.close()
    imprimir(resultado)


if __name__ == "__main__":
    main()
