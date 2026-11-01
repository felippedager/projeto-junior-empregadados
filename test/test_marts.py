"""Testes de pipeline/marts.py e dos onze SQLs de sql/marts.

Spec (specs/06_testes.md, seção 3, marts), com o motivo de cada regra provada:

Orquestrador:
- Um mart por arquivo, com o nome sem o prefixo NN_; apagar o arquivo faz o mart sumir (o schema é
  recriado), senão ficaria um mart fantasma.
- Nome sem prefixo e nome repetido param antes de tocar o banco; SQL com erro e mart vazio param
  e fazem rollback (os marts antigos ficam); pasta sem .sql e refined faltando param com mensagem.

SQLs (os .sql reais, rodados sobre o refined inventado de apoio.py):
- Receita é só de pedido Delivered; ticket divide só por pedido entregue com item; taxa sem venda
  é NULL, não 0; cidade igual em estados diferentes não se mistura; produtos de mesmo nome não
  se confundem; as somas por categoria, estado e método fecham com a receita total.
Valores esperados: contas à mão em apoio.py (receita 120,00, devolvido 80,00, ...).
"""

from datetime import date
from decimal import Decimal as D

import pytest

import apoio
from pipeline import db, marts


# --------------------------------------------------------------------- orquestrador


def preparar_orquestrador(monkeypatch, tmp_path, arquivos: dict[str, str], com_refined=True):
    ambiente = apoio.isolar(monkeypatch, tmp_path)
    pasta = tmp_path / "sql" / "marts"
    pasta.mkdir(parents=True)
    for nome, sql in arquivos.items():
        (pasta / nome).write_text(sql, encoding="utf-8")
    monkeypatch.setattr(marts, "PASTA_SQL", pasta)
    if com_refined:
        apoio.criar_refined(ambiente.banco)
    return ambiente, pasta


def tabelas_de_marts(banco) -> set:
    linhas = apoio.consultar(
        banco, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'marts'"
    )
    return {l["table_name"] for l in linhas}


def esperar_falha(capsys):
    with pytest.raises(SystemExit) as saida:
        marts.main()
    assert saida.value.code == 1
    return capsys.readouterr().out


def test_um_mart_por_arquivo_com_o_nome_sem_o_prefixo(monkeypatch, tmp_path):
    ambiente, _ = preparar_orquestrador(
        monkeypatch, tmp_path,
        {"01_alfa.sql": "SELECT 1 AS x", "02_beta.sql": "SELECT 2 AS y;"},  # o segundo termina com ';'
    )

    marts.main()

    assert tabelas_de_marts(ambiente.banco) == {"alfa", "beta"}
    assert apoio.consultar(ambiente.banco, "SELECT y FROM marts.beta") == [{"y": 2}]


def test_apagar_o_arquivo_faz_o_mart_sumir(monkeypatch, tmp_path):
    ambiente, pasta = preparar_orquestrador(
        monkeypatch, tmp_path, {"01_alfa.sql": "SELECT 1 AS x", "02_beta.sql": "SELECT 2 AS y"}
    )
    marts.main()
    assert tabelas_de_marts(ambiente.banco) == {"alfa", "beta"}

    (pasta / "02_beta.sql").unlink()  # apaga o arquivo: o mart não pode sobrar como fantasma
    marts.main()

    assert tabelas_de_marts(ambiente.banco) == {"alfa"}


def test_nome_sem_prefixo_para_sem_tocar_o_banco(monkeypatch, tmp_path, capsys):
    ambiente, _ = preparar_orquestrador(
        monkeypatch, tmp_path, {"01_alfa.sql": "SELECT 1 AS x", "kpis.sql": "SELECT 1 AS x"}
    )
    antes = apoio.hash_do(ambiente.banco)

    texto = esperar_falha(capsys)

    assert "kpis.sql" in texto
    assert apoio.hash_do(ambiente.banco) == antes


def test_nomes_repetidos_depois_do_prefixo_param(monkeypatch, tmp_path, capsys):
    ambiente, _ = preparar_orquestrador(
        monkeypatch, tmp_path, {"01_alfa.sql": "SELECT 1 AS x", "02_alfa.sql": "SELECT 2 AS x"}
    )
    antes = apoio.hash_do(ambiente.banco)

    texto = esperar_falha(capsys)

    assert "marts.alfa" in texto
    assert "01_alfa.sql" in texto and "02_alfa.sql" in texto
    assert apoio.hash_do(ambiente.banco) == antes


def test_sql_com_erro_para_e_mantem_os_marts_antigos(monkeypatch, tmp_path, capsys):
    ambiente, pasta = preparar_orquestrador(monkeypatch, tmp_path, {"01_alfa.sql": "SELECT 1 AS x"})
    marts.main()
    capsys.readouterr()
    (pasta / "02_ruim.sql").write_text("SELEC 1", encoding="utf-8")  # erro de sintaxe

    texto = esperar_falha(capsys)

    assert "02_ruim.sql" in texto
    assert tabelas_de_marts(ambiente.banco) == {"alfa"}  # rollback: o mart antigo continua, o novo não nasceu


def test_mart_vazio_para_e_mantem_os_marts_antigos(monkeypatch, tmp_path, capsys):
    ambiente, pasta = preparar_orquestrador(monkeypatch, tmp_path, {"01_alfa.sql": "SELECT 1 AS x"})
    marts.main()
    capsys.readouterr()
    (pasta / "02_vazio.sql").write_text("SELECT 1 AS x WHERE 1 = 0", encoding="utf-8")  # 0 linhas

    texto = esperar_falha(capsys)

    assert "Mart vazio: 02_vazio.sql" in texto
    assert tabelas_de_marts(ambiente.banco) == {"alfa"}


def test_falha_na_construcao_desfaz_a_transacao_mesmo_com_a_conexao_aberta(monkeypatch, tmp_path, capsys):
    ambiente, pasta = preparar_orquestrador(monkeypatch, tmp_path, {"01_alfa.sql": "SELECT 1 AS x"})
    marts.main()
    capsys.readouterr()
    (pasta / "02_ruim.sql").write_text("SELEC 1", encoding="utf-8")  # erro de sintaxe no segundo arquivo
    # Conexão que continua aberta depois da falha: fechar a conexão já descartaria a transação sozinho,
    # então só olhando daqui se vê se o próprio construir() fez o ROLLBACK.
    con = db.conectar()
    try:
        with pytest.raises(SystemExit) as saida:
            marts.construir(con, marts.listar_arquivos())
        tabelas = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'marts'"
        ).fetchall()
    finally:
        con.close()

    assert saida.value.code == 1
    assert tabelas == [("alfa",)]  # o mart antigo continua e o DROP SCHEMA foi desfeito


def test_pasta_sem_sql_para(monkeypatch, tmp_path, capsys):
    preparar_orquestrador(monkeypatch, tmp_path, {})  # pasta existe e está vazia

    texto = esperar_falha(capsys)

    assert "Nenhum arquivo .sql" in texto


def test_refined_faltando_lista_o_que_falta_e_nao_cria_o_banco(monkeypatch, tmp_path, capsys):
    ambiente, _ = preparar_orquestrador(
        monkeypatch, tmp_path, {"01_alfa.sql": "SELECT 1 AS x"}, com_refined=False
    )

    texto = esperar_falha(capsys)

    for tabela in ["categorias", "clientes", "produtos", "pedidos", "itens_pedido", "devolucoes"]:
        assert tabela in texto
    assert "pipeline.transformacao" in texto
    assert not ambiente.banco.exists()


def test_saida_usa_singular_para_uma_linha_e_total(monkeypatch, tmp_path, capsys):
    preparar_orquestrador(
        monkeypatch, tmp_path,
        {"01_um.sql": "SELECT 1 AS x", "02_dois.sql": "SELECT * FROM (VALUES (1), (2)) AS t(x)"},
    )

    marts.main()

    linhas = capsys.readouterr().out.splitlines()
    assert linhas[0].startswith("marts.um") and linhas[0].endswith("1 linha")
    assert linhas[1].startswith("marts.dois") and linhas[1].endswith("2 linhas")
    assert linhas[2] == "Total  2 marts"


def test_rodar_duas_vezes_imprime_igual(monkeypatch, tmp_path, capsys):
    preparar_orquestrador(monkeypatch, tmp_path, {"01_alfa.sql": "SELECT 1 AS x"})
    marts.main()
    primeira = capsys.readouterr().out

    marts.main()
    segunda = capsys.readouterr().out

    assert primeira == segunda


# ------------------------------------------------------------------------ os SQLs


def mart(banco, nome):
    return apoio.consultar(banco, f"SELECT * FROM marts.{nome}")


def test_cancelado_e_em_transito_ficam_fora_da_receita(monkeypatch, tmp_path):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)

    kpis = mart(ambiente.banco, "kpis")[0]

    # Delivered: 20 + 20 + 60 + 10 + 10 = 120. Se Canceled (50) e In Transit (10) entrassem: 180.
    assert kpis["receita_bruta"] == D("120.00")
    assert kpis["itens_entregues"] == 5


def test_kpis_batem_com_a_conta_feita_a_mao(monkeypatch, tmp_path):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)

    kpis = mart(ambiente.banco, "kpis")[0]

    # devolvido 60 + 20 = 80; líquida 120 - 80 = 40; taxa 80/120 = 0,6667; pedidos entregues 1, 2, 5, 6
    assert kpis["valor_devolvido"] == D("80.00")
    assert kpis["receita_liquida"] == D("40.00")
    assert kpis["taxa_devolucao"] == 0.6667
    assert kpis["itens_devolvidos"] == 2
    assert kpis["pedidos_entregues"] == 4
    assert kpis["pedidos_entregues_com_item"] == 3


def test_ticket_divide_so_pelos_pedidos_entregues_com_item(monkeypatch, tmp_path):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)

    ticket = mart(ambiente.banco, "kpis")[0]["ticket_medio"]

    # 120 / 3 pedidos com item (1, 2, 6) = 40. Dividir pelos 4 entregues (o 5 não tem item) daria 30.
    assert ticket == D("40.00")


def test_taxa_sem_vendas_fica_nula_e_nao_zero(monkeypatch, tmp_path):
    ambiente = apoio.isolar(monkeypatch, tmp_path)
    dados = apoio.refined_base()
    dados["pedidos"] = [(1, 1, "Canceled", "Card")]  # único pedido cancelado: nada entregue
    dados["itens_pedido"] = [(1, 1, 1, 1, D("10.00"))]  # o item existe, mas não é receita
    dados["devolucoes"] = []  # nenhuma devolução
    apoio.criar_refined(ambiente.banco, dados)

    kpis = apoio.rodar_sql_do_mart(ambiente.banco, "01_kpis.sql")[0]

    assert kpis["receita_bruta"] is None  # soma de nada é NULL
    assert kpis["taxa_devolucao"] is None  # divisão por zero dá NULL, não 0
    assert kpis["ticket_medio"] is None
    assert kpis["itens_entregues"] == 0


def test_status_mostra_valor_de_todos_e_marca_so_o_entregue_como_receita(monkeypatch, tmp_path):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)

    status = {l["status"]: l for l in mart(ambiente.banco, "receita_por_status")}

    # Delivered 120 (5 itens, pedidos 1, 2, 5, 6, três com item); Canceled 5 x 10 = 50; In Transit 10
    assert status["Delivered"]["valor_itens"] == D("120.00")
    assert (status["Delivered"]["pedidos"], status["Delivered"]["pedidos_com_item"], status["Delivered"]["itens"]) == (4, 3, 5)
    assert status["Canceled"]["valor_itens"] == D("50.00")
    assert status["In Transit"]["valor_itens"] == D("10.00")
    assert {s: l["conta_como_receita"] for s, l in status.items()} == {
        "Delivered": "sim", "Canceled": "não", "In Transit": "não",
    }
    assert status["In Transit"]["rotulo"] == "Em trânsito"


def test_categoria_soma_fecha_com_a_receita_total(monkeypatch, tmp_path):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)

    linhas = {l["categoria"]: l for l in mart(ambiente.banco, "receita_por_categoria")}

    # Cat A (produto 1): itens 1 (q2), 6 e 7 = 3 itens, 4 unidades, 20 + 10 + 10 = 40
    # Cat B (produto 2): itens 2 e 3 = 2 itens, 4 unidades, 20 + 60 = 80
    assert (linhas["Cat A"]["itens"], linhas["Cat A"]["quantidade"], linhas["Cat A"]["receita_bruta"]) == (3, 4, D("40.00"))
    assert (linhas["Cat B"]["itens"], linhas["Cat B"]["quantidade"], linhas["Cat B"]["receita_bruta"]) == (2, 4, D("80.00"))
    assert sum(l["receita_bruta"] for l in linhas.values()) == D("120.00")
    assert linhas["Cat A"]["participacao"] == 0.3333  # 40 / 120
    assert linhas["Cat B"]["participacao"] == 0.6667  # 80 / 120


def test_margem_usa_custo_do_produto(monkeypatch, tmp_path):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)

    linhas = {l["categoria"]: l for l in mart(ambiente.banco, "margem_por_categoria")}

    # Cat A: custo 6 x 4 unidades = 24; margem 40 - 24 = 16; 16/40 = 0,4
    # Cat B: custo 15 x 4 unidades = 60; margem 80 - 60 = 20; 20/80 = 0,25
    assert (linhas["Cat A"]["custo_total"], linhas["Cat A"]["margem"], linhas["Cat A"]["margem_pct"]) == (D("24.00"), D("16.00"), 0.4)
    assert (linhas["Cat B"]["custo_total"], linhas["Cat B"]["margem"], linhas["Cat B"]["margem_pct"]) == (D("60.00"), D("20.00"), 0.25)


def test_top_produtos_nao_confunde_produtos_de_mesmo_nome(monkeypatch, tmp_path):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)

    linhas = mart(ambiente.banco, "top_produtos")

    # Os produtos 1 e 2 se chamam "N". Produto 2: 20 + 60 = 80; produto 1: 20 + 10 + 10 = 40.
    # O produto 3 nunca foi vendido e não aparece.
    assert [(l["posicao"], l["produto_id"], l["nome"], l["receita_bruta"]) for l in linhas] == [
        (1, 2, "N", D("80.00")),
        (2, 1, "N", D("40.00")),
    ]
    assert linhas[0]["categoria"] == "Cat B"


def test_estado_soma_fecha_com_a_receita_total(monkeypatch, tmp_path):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)

    linhas = {l["estado"]: l for l in mart(ambiente.banco, "receita_por_estado")}

    # X: pedido 1 (40) + pedido 2 (60) = 100 em 2 pedidos; Y: pedido 6 (20) em 1. Z não comprou.
    assert set(linhas) == {"X", "Y"}
    assert (linhas["X"]["pedidos"], linhas["X"]["receita_bruta"]) == (2, D("100.00"))
    assert (linhas["Y"]["pedidos"], linhas["Y"]["receita_bruta"]) == (1, D("20.00"))
    assert sum(l["receita_bruta"] for l in linhas.values()) == D("120.00")
    assert linhas["X"]["participacao"] == 0.8333  # 100 / 120


def test_cidade_igual_em_estados_diferentes_nao_se_mistura(monkeypatch, tmp_path):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)

    linhas = mart(ambiente.banco, "receita_por_cidade")

    # (X,P) 40, (X,Q) 60, (Y,P) 20. Se agrupasse só por cidade, P valeria 60.
    assert [(l["posicao"], l["estado"], l["cidade"], l["receita_bruta"]) for l in linhas] == [
        (1, "X", "Q", D("60.00")),
        (2, "X", "P", D("40.00")),
        (3, "Y", "P", D("20.00")),
    ]


def test_pagamento_conta_todos_os_pedidos_e_receita_so_dos_entregues(monkeypatch, tmp_path):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)

    linhas = {l["metodo_pagamento"]: l for l in mart(ambiente.banco, "pagamento_por_metodo")}

    # Card: pedidos 1, 4, 5 (3), entregues 1 e 5 (2), cancelados 0, receita só do pedido 1 = 40
    # UPI: pedidos 2, 3, 6 (3), entregues 2 e 6 (2), cancelado 3 (1; 1/3 = 0,3333), receita 60 + 20 = 80
    card, upi = linhas["Card"], linhas["UPI"]
    assert (card["pedidos"], card["pedidos_entregues"], card["pedidos_cancelados"]) == (3, 2, 0)
    assert (card["taxa_cancelamento"], card["receita_bruta"]) == (0.0, D("40.00"))
    assert (upi["pedidos"], upi["pedidos_entregues"], upi["pedidos_cancelados"]) == (3, 2, 1)
    assert (upi["taxa_cancelamento"], upi["receita_bruta"]) == (0.3333, D("80.00"))
    assert card["receita_bruta"] + upi["receita_bruta"] == D("120.00")


def test_devolucao_usa_a_categoria_do_produto_devolvido(monkeypatch, tmp_path):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)

    linhas = {l["categoria"]: l for l in mart(ambiente.banco, "devolucao_por_categoria")}

    # Devolução 1 é do item 3 (produto 2, Cat B): 60. Devolução 2 é do item 1 (produto 1, Cat A): 20.
    # Cat A: 3 itens entregues, receita 40, taxa 20/40 = 0,5. Cat B: 2 itens, receita 80, taxa 60/80 = 0,75.
    a, b = linhas["Cat A"], linhas["Cat B"]
    assert (a["itens_entregues"], a["itens_devolvidos"], a["valor_devolvido"], a["taxa_devolucao"]) == (3, 1, D("20.00"), 0.5)
    assert (b["itens_entregues"], b["itens_devolvidos"], b["valor_devolvido"], b["taxa_devolucao"]) == (2, 1, D("60.00"), 0.75)


def test_tamanho_conta_linhas_de_item_por_pedido(monkeypatch, tmp_path):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)

    linhas = mart(ambiente.banco, "tamanho_pedido")

    # Entregues com item: pedido 1 (2 linhas, 40), pedido 2 (1 linha, 60), pedido 6 (2 linhas, 20).
    # 1 linha: 1 pedido, 60, ticket 60. 2 linhas: 2 pedidos, 60, ticket 30. O pedido 5 (sem item) não conta.
    assert [(l["linhas_no_pedido"], l["pedidos"], l["receita_bruta"], l["ticket_medio"]) for l in linhas] == [
        (1, 1, D("60.00"), D("60.00")),
        (2, 2, D("60.00"), D("30.00")),
    ]


def test_qualidade_conta_as_anomalias_da_entrada(monkeypatch, tmp_path):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)

    linhas = {l["verificacao"]: l for l in mart(ambiente.banco, "qualidade_dados")}

    # (ocorrências, base) à mão: pedido 5 é o único sem item (de 6); cliente 4 é o único sem pedido (de 4);
    # o par (pedido 6, produto 1) se repete (de 7 itens); o pedido 5 é o único entregue sem item (de 4
    # entregues); produtos 1 e 2 dividem o nome "N" (de 3); nenhuma devolução é de pedido não entregue (de 2).
    assert {v: (l["ocorrencias"], l["base"]) for v, l in linhas.items()} == {
        "pedidos_sem_item": (1, 6),
        "clientes_sem_pedido": (1, 4),
        "pares_pedido_produto_repetidos": (1, 7),
        "pedidos_entregues_sem_item": (1, 4),
        "produtos_com_nome_repetido": (2, 3),
        "devolucoes_de_pedido_nao_entregue": (0, 2),
    }
    assert linhas["pedidos_sem_item"]["proporcao"] == 0.1667  # 1 / 6


def test_qualidade_pega_devolucao_de_pedido_nao_entregue(monkeypatch, tmp_path):
    dados = apoio.refined_base()
    dados["devolucoes"].append((3, 4, date(2026, 2, 1), D("50.00")))  # devolve o item 4, do pedido 3 CANCELADO
    ambiente = apoio.montar_marts(monkeypatch, tmp_path, dados)

    linhas = {l["verificacao"]: l for l in mart(ambiente.banco, "qualidade_dados")}

    assert (linhas["devolucoes_de_pedido_nao_entregue"]["ocorrencias"], linhas["devolucoes_de_pedido_nao_entregue"]["base"]) == (1, 3)


def test_top_produtos_e_cidades_limitam_a_dez(monkeypatch, tmp_path):
    ambiente = apoio.isolar(monkeypatch, tmp_path)
    dados = apoio.refined_base()
    # 12 produtos de preço 10, 20, ..., 120; 12 clientes em 12 cidades; cada cliente compra 1 unidade do
    # produto de mesmo número num pedido entregue: receita do produto e da cidade i = 10 x i.
    dados["categorias"] = [(1, "Cat A")]
    dados["produtos"] = [(i, f"P{i}", 1, D(f"{10 * i}.00"), D("1.00")) for i in range(1, 13)]
    dados["clientes"] = [(i, date(2026, 2, 1), f"C{i}", "X") for i in range(1, 13)]
    dados["pedidos"] = [(i, i, "Delivered", "UPI") for i in range(1, 13)]
    dados["itens_pedido"] = [(i, i, i, 1, D(f"{10 * i}.00")) for i in range(1, 13)]
    dados["devolucoes"] = []
    apoio.criar_refined(ambiente.banco, dados)

    produtos = apoio.rodar_sql_do_mart(ambiente.banco, "05_top_produtos.sql")
    cidades = apoio.rodar_sql_do_mart(ambiente.banco, "07_receita_por_cidade.sql")

    # só os 10 maiores: produtos 12 até 3 (os produtos 1 e 2, de 10 e 20, ficam de fora)
    assert [l["produto_id"] for l in produtos] == list(range(12, 2, -1))
    assert [l["cidade"] for l in cidades] == [f"C{i}" for i in range(12, 2, -1)]
    assert [l["posicao"] for l in produtos] == list(range(1, 11))
