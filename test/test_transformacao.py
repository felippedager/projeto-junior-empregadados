"""Testes de pipeline/transformacao.py.

Spec (specs/06_testes.md, seção 3, transformacao), com o motivo de cada regra provada:
- Nomes em português e tipos estritos (id INTEGER, data DATE, dinheiro DECIMAL): soma de dinheiro
  tem que fechar centavo por centavo.
- clientes perde name e email: nenhuma pergunta de mart usa, e são dado pessoal.
- Conversão que falha (texto, mais de 2 casas, inteiro com casa, data inválida) para tudo e diz
  tabela, coluna e valor: um nulo ou um arredondamento fabricado seria indistinguível do dado.
- Linha inteira repetida sai uma vez e é contada; chave repetida com conteúdo diferente para.
- Nulo é mantido, anomalia (pedido sem item) é mantida: refined não corrige fato.
- Atomicidade: falha no meio não muda nenhuma tabela. Raw faltando lista o que falta.
"""

import re
from decimal import Decimal

import apoio
import duckdb
import pytest

from pipeline import transformacao

TABELAS = ["categorias", "clientes", "produtos", "pedidos", "itens_pedido", "devolucoes"]


def preparar(monkeypatch, tmp_path, raw=None):
    ambiente = apoio.isolar(monkeypatch, tmp_path)
    apoio.criar_raw(ambiente.banco, raw)
    return ambiente


def rodar_ok(monkeypatch, tmp_path, raw=None):
    ambiente = preparar(monkeypatch, tmp_path, raw)
    transformacao.main()
    return ambiente


def esperar_falha(capsys):
    with pytest.raises(SystemExit) as saida:
        transformacao.main()
    assert saida.value.code == 1
    return capsys.readouterr().out


def refined_existe(banco) -> bool:
    return apoio.consultar(
        banco, "SELECT count(*) AS n FROM information_schema.schemata WHERE schema_name = 'refined'"
    )[0]["n"] == 1


def colunas(banco, tabela):
    linhas = apoio.consultar(
        banco,
        "SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_schema = 'refined' AND table_name = '{tabela}' ORDER BY ordinal_position",
    )
    return [(l["column_name"], l["data_type"]) for l in linhas]


def test_tipos_e_nomes_do_refined(monkeypatch, tmp_path):
    ambiente = rodar_ok(monkeypatch, tmp_path)

    esperado = {  # mapa da spec 02, escrito por extenso: nome e tipo de cada coluna
        "categorias": [("categoria_id", "INTEGER"), ("nome", "VARCHAR")],
        "clientes": [("cliente_id", "INTEGER"), ("data_cadastro", "DATE"), ("cidade", "VARCHAR"), ("estado", "VARCHAR")],
        "produtos": [("produto_id", "INTEGER"), ("nome", "VARCHAR"), ("categoria_id", "INTEGER"),
                     ("preco", "DECIMAL(10,2)"), ("custo", "DECIMAL(10,2)")],
        "pedidos": [("pedido_id", "INTEGER"), ("cliente_id", "INTEGER"), ("status", "VARCHAR"),
                    ("metodo_pagamento", "VARCHAR")],
        "itens_pedido": [("item_id", "INTEGER"), ("pedido_id", "INTEGER"), ("produto_id", "INTEGER"),
                         ("quantidade", "INTEGER"), ("preco_unitario", "DECIMAL(10,2)")],
        "devolucoes": [("devolucao_id", "INTEGER"), ("item_id", "INTEGER"), ("data_devolucao", "DATE"),
                       ("valor_reembolso", "DECIMAL(10,2)")],
    }
    for tabela, cols in esperado.items():
        assert colunas(ambiente.banco, tabela) == cols, tabela


def test_clientes_perdem_name_e_email(monkeypatch, tmp_path, capsys):
    ambiente = rodar_ok(monkeypatch, tmp_path)

    nomes = [c for c, _ in colunas(ambiente.banco, "clientes")]

    assert "name" not in nomes
    assert "email" not in nomes
    assert "colunas fora: name, email" in capsys.readouterr().out


def test_ids_viram_inteiro_e_dinheiro_fica_decimal(monkeypatch, tmp_path):
    ambiente = rodar_ok(monkeypatch, tmp_path)

    linha = apoio.consultar(
        ambiente.banco,
        "SELECT typeof(item_id) AS id, typeof(quantidade) AS q, typeof(preco_unitario) AS p, "
        "typeof(preco_unitario * quantidade) AS conta FROM refined.itens_pedido LIMIT 1",
    )[0]

    assert (linha["id"], linha["q"], linha["p"]) == ("INTEGER", "INTEGER", "DECIMAL(10,2)")
    assert linha["conta"].startswith("DECIMAL")  # dinheiro vezes inteiro não vira DOUBLE


def test_soma_de_dinheiro_fecha_centavo_por_centavo(monkeypatch, tmp_path):
    ambiente = rodar_ok(monkeypatch, tmp_path)

    # contas à mão em apoio.RAW_BASE: unit_price 41,00; price 30,50; cost 21,25; refund 21,00; qtd 4
    soma = apoio.consultar(
        ambiente.banco,
        "SELECT (SELECT sum(preco_unitario) FROM refined.itens_pedido) AS unit, "
        "(SELECT sum(preco) FROM refined.produtos) AS preco, "
        "(SELECT sum(custo) FROM refined.produtos) AS custo, "
        "(SELECT sum(valor_reembolso) FROM refined.devolucoes) AS reembolso, "
        "(SELECT sum(quantidade) FROM refined.itens_pedido) AS qtd",
    )[0]

    assert soma["unit"] == Decimal("41.00")
    assert soma["preco"] == Decimal("30.50")
    assert soma["custo"] == Decimal("21.25")
    assert soma["reembolso"] == Decimal("21.00")
    assert soma["qtd"] == 4


def test_linha_inteira_repetida_sai_uma_vez_e_e_contada(monkeypatch, tmp_path, capsys):
    raw = apoio.raw_base()
    raw["pedidos"][1].append(list(raw["pedidos"][1][0]))  # repete o pedido 1 inteiro: 4 linhas entram
    ambiente = rodar_ok(monkeypatch, tmp_path, raw)

    n = apoio.consultar(ambiente.banco, "SELECT count(*) AS n FROM refined.pedidos")[0]["n"]

    assert n == 3  # 4 entram, a cópia exata sai
    linha = next(l for l in capsys.readouterr().out.splitlines() if l.startswith("refined.pedidos"))
    assert re.search(r"4 ->\s+3 linhas\s+\(1 duplicatas\)", linha)


def test_chave_repetida_com_conteudo_diferente_para_tudo(monkeypatch, tmp_path, capsys):
    raw = apoio.raw_base()
    raw["pedidos"][1].append(["1", "1", "Canceled", "UPI"])  # mesmo pedido 1, status diferente
    ambiente = preparar(monkeypatch, tmp_path, raw)

    texto = esperar_falha(capsys)

    assert "Chave repetida com conteúdo diferente em raw.pedidos" in texto
    assert "order_id = 1" in texto
    assert "Delivered" in texto and "Canceled" in texto  # as duas linhas conflitantes aparecem
    assert not refined_existe(ambiente.banco)


def test_valor_nao_numerico_para_e_diz_tabela_coluna_e_valor(monkeypatch, tmp_path, capsys):
    raw = apoio.raw_base()
    raw["produtos"][1][0][3] = "abc"  # preço do produto 1 vira texto
    ambiente = preparar(monkeypatch, tmp_path, raw)

    texto = esperar_falha(capsys)

    assert "raw.produtos.price" in texto
    assert "'abc'" in texto
    assert not refined_existe(ambiente.banco)


def test_mais_de_duas_casas_decimais_para_em_vez_de_arredondar(monkeypatch, tmp_path, capsys):
    raw = apoio.raw_base()
    raw["produtos"][1][0][3] = "1.239"  # CAST puro arredondaria para 1.24 sem avisar
    ambiente = preparar(monkeypatch, tmp_path, raw)

    texto = esperar_falha(capsys)

    assert "raw.produtos.price" in texto
    assert "'1.239'" in texto
    assert not refined_existe(ambiente.banco)


def test_inteiro_com_casa_decimal_para_em_vez_de_arredondar(monkeypatch, tmp_path, capsys):
    raw = apoio.raw_base()
    raw["itens_pedido"][1][0][3] = "2.5"  # CAST puro para INTEGER devolveria 3 sem avisar
    ambiente = preparar(monkeypatch, tmp_path, raw)

    texto = esperar_falha(capsys)

    assert "raw.itens_pedido.quantity" in texto
    assert "'2.5'" in texto
    assert not refined_existe(ambiente.banco)


def test_data_invalida_para_e_diz_o_valor(monkeypatch, tmp_path, capsys):
    raw = apoio.raw_base()
    raw["clientes"][1][0][3] = "2026-13-45"  # mês 13 não existe
    ambiente = preparar(monkeypatch, tmp_path, raw)

    texto = esperar_falha(capsys)

    assert "raw.clientes.signup_date" in texto
    assert "2026-13-45" in texto
    assert not refined_existe(ambiente.banco)


def test_nulo_e_mantido_e_nao_preenchido(monkeypatch, tmp_path, capsys):
    raw = apoio.raw_base()
    raw["produtos"][1][1][4] = None  # produto 2 sem custo: o nulo tem que sobreviver
    ambiente = rodar_ok(monkeypatch, tmp_path, raw)

    produtos = apoio.consultar(ambiente.banco, "SELECT produto_id, custo FROM refined.produtos ORDER BY 1")

    assert produtos == [{"produto_id": 1, "custo": Decimal("6.00")}, {"produto_id": 2, "custo": None}]
    assert "nulos mantidos: custo 1" in capsys.readouterr().out


def test_pedido_sem_item_continua_no_refined(monkeypatch, tmp_path):
    ambiente = rodar_ok(monkeypatch, tmp_path)

    sem_item = apoio.consultar(
        ambiente.banco,
        "SELECT pedido_id FROM refined.pedidos WHERE pedido_id NOT IN (SELECT pedido_id FROM refined.itens_pedido)",
    )

    assert sem_item == [{"pedido_id": 3}]  # o pedido 3 do RAW_BASE não tem item


def test_falha_no_meio_nao_muda_nenhuma_tabela(monkeypatch, tmp_path):
    ambiente = rodar_ok(monkeypatch, tmp_path)
    apoio.executar(
        ambiente.banco,
        "INSERT INTO refined.categorias VALUES (99, 'MARCA')",  # marca: some se o refined for refeito
        # troca a tabela refined.pedidos (4ª a ser gravada) por uma view: o CREATE OR REPLACE TABLE estoura
        "DROP TABLE refined.pedidos",
        "CREATE VIEW refined.pedidos AS SELECT 1 AS x",
    )

    with pytest.raises(duckdb.CatalogException):
        transformacao.main()

    marcas = apoio.consultar(ambiente.banco, "SELECT count(*) AS n FROM refined.categorias WHERE categoria_id = 99")
    assert marcas == [{"n": 1}]  # as tabelas anteriores não foram refeitas (rollback)


def test_raw_faltando_lista_o_que_falta_e_nao_cria_o_banco(monkeypatch, tmp_path, capsys):
    ambiente = apoio.isolar(monkeypatch, tmp_path)  # nenhum banco criado

    texto = esperar_falha(capsys)

    for tabela in TABELAS:
        assert tabela in texto
    assert "pipeline.ingestao" in texto
    assert not ambiente.banco.exists()


def test_tabela_de_raw_faltando_lista_so_a_que_falta(monkeypatch, tmp_path, capsys):
    ambiente = preparar(monkeypatch, tmp_path)
    apoio.executar(ambiente.banco, "DROP TABLE raw.devolucoes")

    texto = esperar_falha(capsys)

    assert "Faltam tabelas em raw: devolucoes" in texto
    assert not refined_existe(ambiente.banco)


def test_rodar_duas_vezes_imprime_igual(monkeypatch, tmp_path, capsys):
    rodar_ok(monkeypatch, tmp_path)
    primeira = capsys.readouterr().out

    transformacao.main()
    segunda = capsys.readouterr().out

    assert primeira == segunda
    assert "Total" in primeira


def test_saida_mostra_colunas_fora_e_nulos_mantidos(monkeypatch, tmp_path, capsys):
    raw = apoio.raw_base()
    raw["produtos"][1][0][4] = None  # produto 1 sem custo
    raw["produtos"][1][1][4] = None  # produto 2 sem custo
    rodar_ok(monkeypatch, tmp_path, raw)

    linhas = capsys.readouterr().out.splitlines()

    assert "    colunas fora: name, email" in linhas
    assert "    nulos mantidos: custo 2" in linhas
    # linhas do raw base: 1 categoria + 2 clientes + 2 produtos + 3 pedidos + 3 itens + 1 devolução = 12
    assert linhas[-1].startswith("Total")
    assert re.search(r"12 ->\s+12 linhas\s+\(0 duplicatas\)", linhas[-1])
