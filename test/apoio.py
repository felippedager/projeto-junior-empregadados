"""Apoio dos testes: isolamento e entrada inventada. Funções, não fixtures (CLAUDE.md: só
tmp_path e monkeypatch são fixtures).

Isolamento: os módulos fazem "from pipeline.db import BANCO", que copia o nome. Trocar só
db.BANCO deixaria os outros apontando para o banco real; por isso isolar() troca o nome em
cada módulo que o importou. Todo teste que toca banco ou arquivo chama isolar() primeiro.
"""

import copy
import hashlib
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

import duckdb

import painel
import relatorio
from pipeline import db, ingestao, marts, transformacao

# Os .sql reais dos marts: é o código sob teste, lido do projeto; só rodam sobre tabelas inventadas.
SQL_REAL = Path(__file__).resolve().parent.parent / "sql" / "marts"


def isolar(monkeypatch, tmp_path):
    """Aponta todos os módulos para arquivos dentro de tmp_path."""
    banco = tmp_path / "ecommerce.duckdb"
    raw = tmp_path / "raw"
    raw.mkdir()
    saida = tmp_path / "relatorio.html"
    monkeypatch.setattr(db, "BANCO", banco)
    monkeypatch.setattr(db, "PASTA_RAW", raw)
    monkeypatch.setattr(ingestao, "PASTA_RAW", raw)
    monkeypatch.setattr(transformacao, "BANCO", banco)
    monkeypatch.setattr(marts, "BANCO", banco)
    monkeypatch.setattr(marts, "RAIZ", tmp_path)
    monkeypatch.setattr(marts, "PASTA_SQL", SQL_REAL)
    monkeypatch.setattr(painel, "BANCO", banco)
    monkeypatch.setattr(relatorio, "SAIDA", saida)
    return SimpleNamespace(banco=banco, raw=raw, saida=saida, raiz=tmp_path)


def hash_do(arquivo: Path) -> str:
    return hashlib.md5(arquivo.read_bytes()).hexdigest()


def consultar(banco: Path, sql: str) -> list[dict]:
    """Abre o banco de teste só para ler e devolve linhas como dicionários."""
    con = duckdb.connect(str(banco), read_only=True)
    try:
        cur = con.execute(sql)
        colunas = [c[0] for c in cur.description]
        return [dict(zip(colunas, linha)) for linha in cur.fetchall()]
    finally:
        con.close()


def executar(banco: Path, *comandos: str) -> None:
    con = duckdb.connect(str(banco))
    try:
        for comando in comandos:
            con.execute(comando)
    finally:
        con.close()


# ------------------------------------------------------------------ CSVs (ingestão)

CABECALHOS = {
    "categories.csv": "category_id,category_name",
    "customers.csv": "customer_id,name,email,signup_date,city,state",
    "products.csv": "product_id,product_name,category_id,price,cost_price",
    "orders.csv": "order_id,customer_id,order_status,payment_method",
    "order_items.csv": "order_item_id,order_id,product_id,quantity,unit_price",
    "returns.csv": "return_id,order_item_id,return_date,refund_amount",
}

# Linhas de dados inventadas. O comentário de cada linha diz por que ela existe.
LINHAS_CSV = {
    "categories.csv": [
        "1,Cat A",  # linha comum
        "2,NA",  # o texto "NA" é valor do arquivo, não nulo: tem que continuar texto
    ],
    "customers.csv": [
        "1,Ana,a@x,2026-01-22,P,X",  # linha comum
        "2,Bia,,2026-02-19,Q,Y",  # e-mail vazio: tem que virar NULL
    ],
    "products.csv": [
        "007,N,1,10.50,6.00",  # id com zero à esquerda: tem que ficar '007'
    ],
    "orders.csv": [
        "1,1,Delivered,UPI",  # linha comum
    ],
    "order_items.csv": [
        "1,1,007,2,10.50",  # liga ao produto '007'
    ],
    "returns.csv": [
        "1,1,2026-02-20,21.00",  # linha comum
    ],
}
CONTAGEM_CSV = {  # tabela em raw -> linhas de dados acima
    "categorias": 2,
    "clientes": 2,
    "produtos": 1,
    "pedidos": 1,
    "itens_pedido": 1,
    "devolucoes": 1,
}


def escrever_csvs(raw: Path, linhas: dict | None = None, cabecalhos: dict | None = None) -> None:
    linhas = linhas or LINHAS_CSV
    cabecalhos = cabecalhos or CABECALHOS
    for nome, cab in cabecalhos.items():
        texto = "\n".join([cab, *linhas[nome]]) + "\n"
        (raw / nome).write_bytes(texto.encode("utf-8"))


# ------------------------------------------------------------------ raw (transformação)

RAW_BASE = {
    "categorias": (["category_id", "category_name"], [
        ["1", "Cat A"],  # categoria única
    ]),
    "clientes": (["customer_id", "name", "email", "signup_date", "city", "state"], [
        ["1", "Ana", "a@x", "2026-01-22", "P", "X"],  # menor data de cadastro
        ["2", "Bia", "b@x", "2026-02-19", "Q", "Y"],  # maior data de cadastro
    ]),
    "produtos": (["product_id", "product_name", "category_id", "price", "cost_price"], [
        ["1", "N", "1", "10.5", "6"],  # preço com 1 casa e custo inteiro: ambos válidos
        ["2", "M", "1", "20.00", "15.25"],  # preço e custo com 2 casas
    ]),
    "pedidos": (["order_id", "customer_id", "order_status", "payment_method"], [
        ["1", "1", "Delivered", "UPI"],  # pedido com 2 itens
        ["2", "2", "Canceled", "UPI"],  # pedido cancelado com 1 item
        ["3", "1", "Delivered", "Card"],  # pedido sem item: anomalia que refined tem que manter
    ]),
    "itens_pedido": (["order_item_id", "order_id", "product_id", "quantity", "unit_price"], [
        ["1", "1", "1", "2", "10.5"],  # 2 unidades do produto 1
        ["2", "1", "2", "1", "20.00"],  # 1 unidade do produto 2
        ["3", "2", "1", "1", "10.5"],  # item do pedido cancelado
    ]),
    "devolucoes": (["return_id", "order_item_id", "return_date", "refund_amount"], [
        ["1", "1", "2026-02-20", "21"],  # devolução do item 1 (2 x 10,5)
    ]),
}
# Somas do RAW_BASE feitas à mão: unit_price 10,5 + 20 + 10,5 = 41,00; price 10,5 + 20 = 30,50;
# cost_price 6 + 15,25 = 21,25; refund 21,00; quantity 2 + 1 + 1 = 4.


def raw_base() -> dict:
    return copy.deepcopy(RAW_BASE)


def criar_raw(banco: Path, raw: dict | None = None) -> None:
    """Cria raw.<tabela> com todas as colunas VARCHAR, como a ingestão faz."""
    raw = raw or raw_base()
    con = duckdb.connect(str(banco))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        for tabela, (colunas, linhas) in raw.items():
            definicao = ", ".join(f'"{c}" VARCHAR' for c in colunas)
            con.execute(f"CREATE OR REPLACE TABLE raw.{tabela} ({definicao})")
            marcas = ", ".join("?" for _ in colunas)
            for linha in linhas:
                con.execute(f"INSERT INTO raw.{tabela} VALUES ({marcas})", linha)
    finally:
        con.close()


# ------------------------------------------------------------------ refined (marts)

DDL_REFINED = {
    "categorias": "categoria_id INTEGER, nome VARCHAR",
    "clientes": "cliente_id INTEGER, data_cadastro DATE, cidade VARCHAR, estado VARCHAR",
    "produtos": "produto_id INTEGER, nome VARCHAR, categoria_id INTEGER, preco DECIMAL(10,2), custo DECIMAL(10,2)",
    "pedidos": "pedido_id INTEGER, cliente_id INTEGER, status VARCHAR, metodo_pagamento VARCHAR",
    "itens_pedido": "item_id INTEGER, pedido_id INTEGER, produto_id INTEGER, quantidade INTEGER, preco_unitario DECIMAL(10,2)",
    "devolucoes": "devolucao_id INTEGER, item_id INTEGER, data_devolucao DATE, valor_reembolso DECIMAL(10,2)",
}
DIA = date(2026, 2, 1)

REFINED_BASE = {
    "categorias": [
        (1, "Cat A"),  # categoria com os produtos 1 e 3
        (2, "Cat B"),  # categoria com o produto 2
    ],
    "clientes": [
        (1, DIA, "P", "X"),  # cidade P do estado X
        (2, DIA, "Q", "X"),  # outra cidade do mesmo estado
        (3, DIA, "P", "Y"),  # mesmo nome de cidade (P) em OUTRO estado: não pode se misturar
        (4, DIA, "R", "Z"),  # cliente sem nenhum pedido
    ],
    "produtos": [
        (1, "N", 1, D("10.00"), D("6.00")),  # custo 6
        (2, "N", 2, D("20.00"), D("15.00")),  # MESMO nome do 1, outra categoria
        (3, "M", 1, D("5.00"), D("4.00")),  # nunca vendido
    ],
    "pedidos": [
        (1, 1, "Delivered", "Card"),  # entregue, 2 itens, cliente de (X,P)
        (2, 2, "Delivered", "UPI"),  # entregue, 1 item, cliente de (X,Q)
        (3, 3, "Canceled", "UPI"),  # cancelado: item não é receita
        (4, 1, "In Transit", "Card"),  # em trânsito: item não é receita
        (5, 2, "Delivered", "Card"),  # entregue SEM item: anomalia
        (6, 3, "Delivered", "UPI"),  # entregue, 2 linhas do mesmo produto, cliente de (Y,P)
    ],
    "itens_pedido": [
        (1, 1, 1, 2, D("10.00")),  # entregue: 2 x 10 = 20
        (2, 1, 2, 1, D("20.00")),  # entregue: 1 x 20 = 20
        (3, 2, 2, 3, D("20.00")),  # entregue: 3 x 20 = 60
        (4, 3, 1, 5, D("10.00")),  # pedido cancelado: 50, fora da receita
        (5, 4, 1, 1, D("10.00")),  # pedido em trânsito: 10, fora da receita
        (6, 6, 1, 1, D("10.00")),  # entregue: 10
        (7, 6, 1, 1, D("10.00")),  # par (pedido 6, produto 1) repetido: entregue, 10
    ],
    "devolucoes": [
        (1, 3, DIA, D("60.00")),  # devolve o item 3 (produto 2, Cat B)
        (2, 1, DIA, D("20.00")),  # devolve o item 1 (produto 1, Cat A)
    ],
}
# Contas à mão sobre REFINED_BASE (receita só de itens de pedido Delivered):
#   receita bruta 20 + 20 + 60 + 10 + 10 = 120,00 ; devolvido 60 + 20 = 80,00 ; líquida 40,00
#   itens entregues 5 ; pedidos entregues 4 (1, 2, 5, 6), com item 3 (1, 2, 6) ; ticket 120/3 = 40,00


def refined_base() -> dict:
    return copy.deepcopy(REFINED_BASE)


def criar_refined(banco: Path, dados: dict | None = None) -> None:
    dados = dados or refined_base()
    con = duckdb.connect(str(banco))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS refined")
        for tabela, ddl in DDL_REFINED.items():
            con.execute(f"CREATE OR REPLACE TABLE refined.{tabela} ({ddl})")
            for linha in dados.get(tabela, []):
                marcas = ", ".join("?" for _ in linha)
                con.execute(f"INSERT INTO refined.{tabela} VALUES ({marcas})", list(linha))
    finally:
        con.close()


def montar_marts(monkeypatch, tmp_path, dados: dict | None = None):
    """Isola, cria o refined inventado e roda o orquestrador com os .sql reais."""
    ambiente = isolar(monkeypatch, tmp_path)
    criar_refined(ambiente.banco, dados)
    marts.main()
    return ambiente


def rodar_sql_do_mart(banco: Path, nome_arquivo: str) -> list[dict]:
    """Roda um .sql real direto (sem o orquestrador), para casos em que outros marts ficariam vazios."""
    sql = (SQL_REAL / nome_arquivo).read_text(encoding="utf-8")
    return consultar(banco, sql)
