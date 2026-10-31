"""Etapa 1: ingestão. Lê os CSVs de raw/ e grava o schema raw de ecommerce.duckdb.

Comando: uv run python -m pipeline.ingestao

Spec (specs/01_ingestao.md), com o motivo de cada regra:

1. ESCOPO. Lê os seis CSVs de raw/, escreve só no schema raw. Nada fica de fora e nada é
   renomeado, convertido, deduplicado ou preenchido.
   Motivo: a ingestão é cópia fiel; decidir o que serve é trabalho da etapa 2.

3. MAPA ARQUIVO -> TABELA (literal, em português; colunas continuam em inglês):
     categories.csv -> raw.categorias    customers.csv   -> raw.clientes
     products.csv   -> raw.produtos      orders.csv      -> raw.pedidos
     order_items.csv -> raw.itens_pedido returns.csv     -> raw.devolucoes
   Motivo: raw espelha o arquivo; se um número do refined parecer estranho, a comparação com
   o CSV é direta. Quem renomeia é a etapa 2.

4. LEITURA COMO TEXTO. pandas com dtype=str, encoding="utf-8", keep_default_na=False e
   na_values=[""]: toda coluna é VARCHAR e só o campo vazio vira NULL.
   Motivo: sem inferência, "007" não vira 7. "NA", "null" e "None" são valores reais do
   arquivo; o default do pandas os apagaria em silêncio.

5. VERIFICAÇÃO ANTES DE ABRIR O BANCO (tudo-ou-nada). Os seis arquivos existem e o cabeçalho
   de cada um é exatamente o esperado, na ordem. Qualquer falha: nada é gravado e o banco nem
   é aberto (nem criado).
   Motivo: ingestão pela metade deixaria tabelas novas e velhas misturadas, indistinguíveis de
   uma ingestão completa. CSV que mudou de colunas é a falha mais provável e mais silenciosa.

6. GRAVAÇÃO. criar_schema("raw") e uma gravação por tabela. A contagem devolvida pelo banco
   tem que ser igual às linhas de dados lidas; se diferir, mostra tabela, esperado e obtido e
   sai com código 1. Motivo: é o critério de aceite da etapa e não pode falhar calado.

7. SAÍDA. Uma linha por tabela e uma de total, milhar com ponto, contagens vindas do banco.
   stdout reconfigurado para utf-8 dentro de main().

REEXECUÇÃO. CREATE OR REPLACE TABLE: rodar dez vezes = rodar uma.

ERRO (sempre antes de abrir o banco, sys.exit(1)): lista todos os arquivos que faltam;
cabeçalho diferente mostra arquivo, colunas esperadas e encontradas; contagem divergente
mostra tabela, esperado e obtido.
"""

import csv
import sys

import pandas as pd

from pipeline.db import PASTA_RAW, conectar, criar_schema, gravar

# arquivo -> (tabela em raw, cabeçalho esperado). A ordem é a ordem de gravação e de impressão.
ARQUIVOS = {
    "categories.csv": ("categorias", ["category_id", "category_name"]),
    "customers.csv": (
        "clientes",
        ["customer_id", "name", "email", "signup_date", "city", "state"],
    ),
    "products.csv": (
        "produtos",
        ["product_id", "product_name", "category_id", "price", "cost_price"],
    ),
    "orders.csv": (
        "pedidos",
        ["order_id", "customer_id", "order_status", "payment_method"],
    ),
    "order_items.csv": (
        "itens_pedido",
        ["order_item_id", "order_id", "product_id", "quantity", "unit_price"],
    ),
    "returns.csv": (
        "devolucoes",
        ["return_id", "order_item_id", "return_date", "refund_amount"],
    ),
}

SCHEMA = "raw"


def milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def verificar() -> None:
    """Confere existência e cabeçalho dos seis arquivos; encerra com 1 se algo falhar."""
    faltando = [nome for nome in ARQUIVOS if not (PASTA_RAW / nome).is_file()]
    if faltando:
        print("Faltam arquivos em raw/:")
        for nome in faltando:
            print(f"  - {nome}")
        print("Coloque os CSVs em raw/ e rode: uv run python -m pipeline.ingestao")
        sys.exit(1)

    erros = []
    for nome, (_, esperado) in ARQUIVOS.items():
        with open(PASTA_RAW / nome, encoding="utf-8", newline="") as f:
            encontrado = next(csv.reader(f), [])
        if encontrado != esperado:
            erros.append((nome, esperado, encontrado))
    if erros:
        for nome, esperado, encontrado in erros:
            print(f"Cabeçalho diferente em raw/{nome}:")
            print(f"  esperado:   {esperado}")
            print(f"  encontrado: {encontrado}")
        sys.exit(1)


def ler(nome: str) -> pd.DataFrame:
    return pd.read_csv(
        PASTA_RAW / nome,
        dtype=str,
        encoding="utf-8",
        keep_default_na=False,
        na_values=[""],
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    verificar()
    # Lê tudo antes de abrir o banco: erro de leitura também não deixa banco pela metade.
    dados = {nome: ler(nome) for nome in ARQUIVOS}

    con = conectar()
    try:
        criar_schema(con, SCHEMA)
        resultado = []
        for nome, (tabela, _) in ARQUIVOS.items():
            esperado = len(dados[nome])
            obtido = gravar(con, dados[nome], SCHEMA, tabela)
            if obtido != esperado:
                print(f"Contagem divergente em {SCHEMA}.{tabela}: esperado {milhar(esperado)}, obtido {milhar(obtido)}")
                sys.exit(1)
            resultado.append((f"{SCHEMA}.{tabela}", obtido))
    finally:
        con.close()

    for nome, n in resultado:
        print(f"{nome:<18}{milhar(n):>8} linhas")
    print(f"{'Total':<18}{milhar(sum(n for _, n in resultado)):>8} linhas")


if __name__ == "__main__":
    main()
