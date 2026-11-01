"""Testes de painel.py (leitura, formatos, cartões, filtro, gráficos). O app.py não é testado aqui.

Spec (specs/06_testes.md, seção 3, painel), com o motivo de cada regra provada:
- Formatos sem locale: ponto de milhar, vírgula decimal, "US$" no dinheiro; nulo vira "—" (não 0).
- ler: nome fora da lista é erro de programação; sem banco ou sem mart vira PainelErro com o comando
  a rodar, e nunca cria banco; a conexão é fechada, para o pipeline poder gravar com o painel de pé.
- cartões e filtro seguem os marts; cada gráfico é uma figura de barras de uma série, em formato
  brasileiro; rótulos de produto e cidade trazem o identificador (nome e cidade não identificam).
Valores esperados: contas à mão em apoio.py (receita 120,00, devolvido 80,00, líquida 40,00, ...).
"""

import duckdb
import pandas as pd
import plotly.graph_objects as go
import pytest

import apoio
import painel
from pipeline import db


# ------------------------------------------------------------------------ formatos


def test_formatos_usam_ponto_de_milhar_e_virgula_decimal():
    from decimal import Decimal

    assert painel.dinheiro(Decimal("1234567.8")) == "US$ 1.234.567,80"
    assert painel.dinheiro(0) == "US$ 0,00"
    assert painel.dinheiro(1234.5) == "US$ 1.234,50"
    assert painel.pct(0.3007) == "30,07%"
    assert painel.pct(1) == "100,00%"
    assert painel.numero(15000) == "15.000"
    assert painel.numero(999) == "999"
    assert painel.numero(1234567) == "1.234.567"


def test_formatos_devolvem_traco_para_nulo():
    for nulo in (None, float("nan")):
        assert painel.dinheiro(nulo) == "—"
        assert painel.pct(nulo) == "—"
        assert painel.numero(nulo) == "—"


# --------------------------------------------------------------------------- leitura


def test_ler_devolve_o_mart(monkeypatch, tmp_path):
    apoio.montar_marts(monkeypatch, tmp_path)

    kpis = painel.ler("kpis")

    assert len(kpis) == 1
    assert kpis.iloc[0]["receita_bruta"] == 120  # receita à mão: 120,00
    assert kpis.iloc[0]["itens_entregues"] == 5


def test_ler_nome_desconhecido_e_erro_de_programacao(monkeypatch, tmp_path):
    apoio.montar_marts(monkeypatch, tmp_path)

    with pytest.raises(ValueError) as erro:
        painel.ler("tabela_que_nao_existe")

    assert "tabela_que_nao_existe" in str(erro.value)


def test_ler_sem_banco_diz_o_comando_e_nao_cria_o_banco(monkeypatch, tmp_path):
    ambiente = apoio.isolar(monkeypatch, tmp_path)

    with pytest.raises(painel.PainelErro) as erro:
        painel.ler("kpis")

    assert "pipeline.ingestao" in str(erro.value)
    assert not ambiente.banco.exists()


def test_ler_sem_mart_diz_o_comando(monkeypatch, tmp_path):
    ambiente = apoio.isolar(monkeypatch, tmp_path)
    apoio.criar_refined(ambiente.banco)  # o banco existe, mas o schema marts não

    with pytest.raises(painel.PainelErro) as erro:
        painel.ler("kpis")

    assert "marts.kpis" in str(erro.value)
    assert "pipeline.marts" in str(erro.value)


def test_ler_fecha_a_conexao(monkeypatch, tmp_path):
    apoio.montar_marts(monkeypatch, tmp_path)
    abertas = []

    def espiao(**opcoes):  # conexão de verdade, só guardada para o teste olhar depois
        con = db.conectar(**opcoes)
        abertas.append(con)
        return con

    monkeypatch.setattr(painel, "conectar", espiao)

    painel.ler("kpis")

    assert len(abertas) == 1
    with pytest.raises(duckdb.ConnectionException):
        abertas[0].execute("SELECT 1")  # conexão fechada não executa nada


# ---------------------------------------------------------------- cartões e filtro


def test_cartoes_seguem_o_kpis(monkeypatch, tmp_path):
    apoio.montar_marts(monkeypatch, tmp_path)

    cartoes = painel.cartoes(painel.ler("kpis"))

    # receita 120, devolvido 80, líquida 40, taxa 80/120 = 66,67%, ticket 120/3 = 40, pedidos entregues 4
    assert [(r, v) for r, v, _ in cartoes] == [
        ("Receita bruta", "US$ 120,00"),
        ("Valor devolvido", "US$ 80,00"),
        ("Receita líquida", "US$ 40,00"),
        ("Taxa de devolução", "66,67%"),
        ("Ticket médio", "US$ 40,00"),
        ("Pedidos entregues", "4"),
    ]
    ajuda = {r: a for r, _, a in cartoes}
    assert "(3)" in ajuda["Ticket médio"]  # 3 pedidos entregues com item
    assert "com item: 3" in ajuda["Pedidos entregues"]


def test_filtro_recorta_so_as_categorias_marcadas(monkeypatch, tmp_path):
    apoio.montar_marts(monkeypatch, tmp_path)
    df = painel.ler("receita_por_categoria")

    so_a = painel.filtrar_categorias(df, ["Cat A"])
    nenhuma = painel.filtrar_categorias(df, [])
    todas = painel.filtrar_categorias(df, ["Cat A", "Cat B"])

    assert so_a["categoria"].tolist() == ["Cat A"]
    assert len(nenhuma) == 0
    assert len(todas) == 2


# ---------------------------------------------------------------------- gráficos


def figuras(monkeypatch, tmp_path):
    apoio.montar_marts(monkeypatch, tmp_path)
    return {
        "status": painel.grafico_status(painel.ler("receita_por_status")),
        "pagamento_receita": painel.grafico_pagamento_receita(painel.ler("pagamento_por_metodo")),
        "pagamento_cancelamento": painel.grafico_pagamento_cancelamento(painel.ler("pagamento_por_metodo")),
        "categoria_receita": painel.grafico_categoria_receita(painel.ler("receita_por_categoria")),
        "categoria_margem": painel.grafico_categoria_margem(painel.ler("margem_por_categoria")),
        "categoria_devolucao": painel.grafico_categoria_devolucao(painel.ler("devolucao_por_categoria")),
        "top_produtos": painel.grafico_top_produtos(painel.ler("top_produtos")),
        "estado": painel.grafico_estado(painel.ler("receita_por_estado")),
        "cidade": painel.grafico_cidade(painel.ler("receita_por_cidade")),
        "tamanho": painel.grafico_tamanho_pedido(painel.ler("tamanho_pedido")),
    }


def test_cada_grafico_e_uma_figura_com_uma_serie_de_barras(monkeypatch, tmp_path):
    todas = figuras(monkeypatch, tmp_path)

    assert len(todas) == 10
    for nome, fig in todas.items():
        assert isinstance(fig, go.Figure), nome
        assert len(fig.data) == 1, nome
        assert fig.data[0].type == "bar", nome
        assert fig.layout.separators == ",.", nome  # vírgula decimal e ponto de milhar nos eixos e dicas


def test_rotulos_de_produto_e_cidade_trazem_identificador(monkeypatch, tmp_path):
    todas = figuras(monkeypatch, tmp_path)

    # produtos 1 e 2 se chamam "N": só o #id os distingue. Cidade P existe em X e em Y.
    assert list(todas["top_produtos"].data[0].y) == ["N #2", "N #1"]
    assert list(todas["cidade"].data[0].y) == ["Q (X)", "P (X)", "P (Y)"]


def test_grafico_de_estados_escreve_valor_so_nas_cinco_maiores():
    df = pd.DataFrame({
        "estado": list("ABCDEFG"),  # 7 estados inventados
        "pedidos": [7, 6, 5, 4, 3, 2, 1],  # decrescente, só para o texto da dica
        "receita_bruta": [700.0, 600.0, 500.0, 400.0, 300.0, 200.0, 100.0],  # decrescente: A é a maior
        "participacao": [0.25, 0.2, 0.2, 0.15, 0.1, 0.05, 0.05],
    })

    fig = painel.grafico_estado(df)

    textos = list(fig.data[0].text)
    assert [bool(t) for t in textos] == [True] * 5 + [False] * 2  # só as cinco maiores têm valor escrito
    assert textos[0] == "US$ 700,00"


def test_status_destaca_so_o_entregue(monkeypatch, tmp_path):
    todas = figuras(monkeypatch, tmp_path)

    cores = list(todas["status"].data[0].marker.color)

    # ordem do mart: Canceled, Delivered, In Transit
    assert cores == [painel.CINZA_BARRA, painel.AZUL, painel.CINZA_BARRA]


def test_tabela_de_qualidade_vem_formatada(monkeypatch, tmp_path):
    apoio.montar_marts(monkeypatch, tmp_path)

    tabela = painel.tabela_qualidade(painel.ler("qualidade_dados"))

    assert list(tabela.columns) == ["Verificação", "Descrição", "Ocorrências", "Base", "Proporção"]
    primeira = tabela.iloc[0]
    # pedidos_sem_item: 1 de 6 pedidos = 16,67%
    assert (primeira["Verificação"], primeira["Ocorrências"], primeira["Base"], primeira["Proporção"]) == (
        "pedidos_sem_item", "1", "6", "16,67%",
    )
