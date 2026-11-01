"""Etapa 4: painel. Leitura dos marts, formatação e gráficos.

Uso: o relatorio.py reaproveita estas funções (leitura, formatos, cartões e gráficos). A página
interativa (app.py) foi descartada, então nenhum código aqui depende de uma interface.

Spec (specs/04_painel.md), com o motivo de cada regra:

1. ESCOPO. Só lê de marts e só mostra; nunca escreve no banco. Nada de agrupar, somar, tirar
   média, juntar ou transpor tabelas, nem dividir valores de dois marts: número novo = mart novo.
   Motivo: regra de negócio mora no SQL; dois lugares com a conta é onde os números divergem.
   Escolher linhas (filtro) e ordenar para exibir não são cálculo.

2. LEITURA. ler(nome) devolve SELECT * FROM marts.<nome>. Conexão somente leitura, aberta e
   fechada dentro da função (finally). Sem cache.
   Motivo: conexão aberta segura o arquivo; fechando na função, o pipeline grava com o painel
   de pé. Cache mostraria número velho depois de o pipeline rodar.
   Erros viram PainelErro com a mensagem pronta para a tela (banco ausente: checado ANTES de
   conectar, para nunca criar banco vazio; mart ausente). Motivo: erro cru do DuckDB não diz
   ao leitor o que fazer.

3. FORMATAÇÃO sem locale: dinheiro "US$ 1.234.567,80", pct "30,07%", numero "15.000";
   None/NaN dá "—". Motivo do US$: decisão do dono do projeto; o dataset não declara moeda,
   então é convenção de exibição e nenhum valor é convertido. Motivo do "—": nulo é
   informação; o rótulo "sem valor" é decisão de mart, o painel não preenche com 0.
   Nos gráficos, separators=",." faz eixos e dicas usarem o formato brasileiro.

4. CARTÕES. cartoes(df_kpis) -> seis tuplas (rótulo, valor, ajuda) lidas da linha de kpis.

5. GRÁFICOS. Uma função por gráfico: recebe o DataFrame e devolve go.Figure. Barras, uma cor
   só (categorias nominais não ganham rampa de cor: o comprimento da barra já diz a
   magnitude); só o status "Entregue" fica em destaque, o resto em cinza. Rótulo de produto
   "nome #id" (15 nomes para 300 produtos) e de cidade "cidade (estado)" (Udaipur existe em
   dois estados). Valor escrito na barra quando são poucas barras; no gráfico de 28 estados
   só nas cinco maiores, e a dica mostra todas (um número em toda barra vira ruído).

6. FILTRO. filtrar_categorias(df, categorias) recorta linhas por categoria nos marts que têm
   essa coluna. Motivo: um filtro que muda números sem mart por trás seria cálculo na tela.
"""

import duckdb
import pandas as pd
import plotly.graph_objects as go

from pipeline.db import BANCO, conectar

MARTS = (
    "kpis",
    "receita_por_status",
    "receita_por_categoria",
    "margem_por_categoria",
    "top_produtos",
    "receita_por_estado",
    "receita_por_cidade",
    "pagamento_por_metodo",
    "devolucao_por_categoria",
    "tamanho_pedido",
    "qualidade_dados",
)


class PainelErro(Exception):
    """Erro com mensagem pronta para mostrar ao leitor."""


def ler(nome: str) -> pd.DataFrame:
    if nome not in MARTS:
        raise ValueError(f"Mart desconhecido: {nome!r}")
    if not BANCO.is_file():
        raise PainelErro(
            f"Banco {BANCO.name} não encontrado. Rode: uv run python -m pipeline.ingestao"
        )
    con = conectar(somente_leitura=True)
    try:
        return con.execute(f"SELECT * FROM marts.{nome}").df()
    except duckdb.CatalogException as erro:
        raise PainelErro(
            f"Mart marts.{nome} não encontrado. Rode: uv run python -m pipeline.marts"
        ) from erro
    finally:
        con.close()


# ---------------------------------------------------------------- formatação

# Troca "," e "." para o formato brasileiro sem usar locale.
_BR = str.maketrans({",": ".", ".": ","})


def _vazio(v) -> bool:
    return v is None or bool(pd.isna(v))


def dinheiro(v) -> str:
    if _vazio(v):
        return "—"
    return "US$ " + f"{v:,.2f}".translate(_BR)


def pct(f) -> str:
    if _vazio(f):
        return "—"
    return f"{float(f):.2%}".translate(_BR)


def numero(n) -> str:
    if _vazio(n):
        return "—"
    return f"{int(n):,}".translate(_BR)


# ------------------------------------------------------------------- cartões


def cartoes(df_kpis: pd.DataFrame) -> list[tuple[str, str, str]]:
    k = df_kpis.iloc[0]
    com_item = numero(k["pedidos_entregues_com_item"])
    return [
        ("Receita bruta", dinheiro(k["receita_bruta"]), "Itens de pedidos entregues"),
        ("Valor devolvido", dinheiro(k["valor_devolvido"]), "Soma dos reembolsos"),
        ("Receita líquida", dinheiro(k["receita_liquida"]), "Receita bruta menos valor devolvido"),
        ("Taxa de devolução", pct(k["taxa_devolucao"]), "Valor devolvido / receita bruta"),
        (
            "Ticket médio",
            dinheiro(k["ticket_medio"]),
            f"Receita bruta / pedidos entregues com item ({com_item})",
        ),
        (
            "Pedidos entregues",
            numero(k["pedidos_entregues"]),
            f"Inclui os sem item; com item: {com_item}",
        ),
    ]


def filtrar_categorias(df: pd.DataFrame, categorias) -> pd.DataFrame:
    return df[df["categoria"].isin(list(categorias))]


# ------------------------------------------------------------------- gráficos

# Paleta única: um azul (série 1 da paleta de referência) e um cinza que serve nos dois temas.
# Texto, título e fundo NÃO têm cor fixa: herdam do template (no relatório HTML, o plotly_white).
# Cor fixa de texto sumiria se a figura fosse mostrada sobre fundo escuro.
AZUL = "#2a78d6"
CINZA_BARRA = "#9b9a93"
LINHA = "rgba(128,128,128,0.35)"  # cinza translúcido: discreto no tema claro e no escuro


def _barras(
    rotulos,
    valores,
    textos,
    dicas,
    titulo: str,
    horizontal: bool,
    cores=None,
    rotulo_valor: str = "",
    eixo_valor: dict | None = None,
    altura: int = 380,
) -> go.Figure:
    """Gráfico de barras de uma série. Textos e dicas já vêm formatados pelo chamador."""
    rotulos, valores = list(rotulos), list(valores)
    barra = dict(
        marker=dict(color=cores or AZUL, cornerradius=4),
        text=list(textos),
        textposition="outside",
        cliponaxis=False,
        customdata=list(dicas),
        textfont=dict(size=13),
    )
    if horizontal:
        fig = go.Figure(go.Bar(
            x=valores, y=rotulos, orientation="h",
            hovertemplate="%{y}<br>%{customdata}<extra></extra>", **barra,
        ))
        eixo_rotulo, eixo_num = "yaxis", "xaxis"
        fig.update_yaxes(autorange="reversed")
    else:
        fig = go.Figure(go.Bar(
            x=rotulos, y=valores,
            hovertemplate="%{x}<br>%{customdata}<extra></extra>", **barra,
        ))
        eixo_rotulo, eixo_num = "xaxis", "yaxis"

    maior = max((v for v in valores if not _vazio(v)), default=0)
    # Folga à direita do maior valor para o texto não ser cortado: proporcional ao tamanho
    # do maior texto (valor em dinheiro tem 17 caracteres, percentual 6). Barra vertical só
    # precisa de folga em cima.
    maior_texto = max((len(t) for t in textos), default=0)
    folga = 1 + 0.03 * maior_texto if horizontal else 1.18
    # Com o valor escrito na barra, a grade só atrapalha (cortava os números): fica desligada
    # e só o gráfico de estados, que mostra eixo, liga a grade.
    num = dict(
        range=[0, maior * folga if maior else 1],
        showgrid=False, zeroline=False, showticklabels=False, title=rotulo_valor,
    )
    num.update(eixo_valor or {})
    fig.update_layout(**{eixo_num: num})
    fig.update_layout(**{eixo_rotulo: dict(showgrid=False, linecolor=LINHA, title="")})
    fig.update_layout(
        template="plotly_white",
        title=dict(text=titulo, x=0, font=dict(size=16)),
        separators=",.",
        bargap=0.45,
        showlegend=False,
        height=altura,
        margin=dict(l=10, r=10, t=50, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def grafico_status(df: pd.DataFrame) -> go.Figure:
    cores = [AZUL if c == "sim" else CINZA_BARRA for c in df["conta_como_receita"]]
    textos = [dinheiro(v) for v in df["valor_itens"]]
    dicas = [
        f"Valor dos itens: {dinheiro(v)}<br>Pedidos: {numero(p)}"
        f"<br>{'Conta como receita' if c == 'sim' else 'Não conta como receita'}"
        for v, p, c in zip(df["valor_itens"], df["pedidos"], df["conta_como_receita"])
    ]
    return _barras(
        df["rotulo"], df["valor_itens"], textos, dicas,
        "Valor dos itens por status (só Entregue é receita)",
        horizontal=True, cores=cores, altura=300,
    )


def grafico_pagamento_receita(df: pd.DataFrame) -> go.Figure:
    textos = [dinheiro(v) for v in df["receita_bruta"]]
    dicas = [
        f"Receita bruta: {dinheiro(v)}<br>Pedidos entregues: {numero(p)}"
        for v, p in zip(df["receita_bruta"], df["pedidos_entregues"])
    ]
    return _barras(
        df["metodo_pagamento"], df["receita_bruta"], textos, dicas,
        "Receita por método de pagamento", horizontal=False, altura=340,
    )


def grafico_pagamento_cancelamento(df: pd.DataFrame) -> go.Figure:
    textos = [pct(v) for v in df["taxa_cancelamento"]]
    dicas = [
        f"Taxa de cancelamento: {pct(t)}<br>Cancelados: {numero(c)} de {numero(p)} pedidos"
        for t, c, p in zip(df["taxa_cancelamento"], df["pedidos_cancelados"], df["pedidos"])
    ]
    return _barras(
        df["metodo_pagamento"], df["taxa_cancelamento"], textos, dicas,
        "Taxa de cancelamento por método de pagamento", horizontal=False, altura=340,
    )


def grafico_categoria_receita(df: pd.DataFrame) -> go.Figure:
    textos = [dinheiro(v) for v in df["receita_bruta"]]
    dicas = [
        f"Receita bruta: {dinheiro(v)}<br>Participação: {pct(p)}<br>Itens: {numero(i)}"
        for v, p, i in zip(df["receita_bruta"], df["participacao"], df["itens"])
    ]
    return _barras(
        df["categoria"], df["receita_bruta"], textos, dicas,
        "Receita por categoria", horizontal=True,
    )


def grafico_categoria_margem(df: pd.DataFrame) -> go.Figure:
    textos = [pct(v) for v in df["margem_pct"]]
    dicas = [
        f"Margem: {pct(p)}<br>Margem em valor: {dinheiro(m)}<br>Custo total: {dinheiro(c)}"
        for p, m, c in zip(df["margem_pct"], df["margem"], df["custo_total"])
    ]
    return _barras(
        df["categoria"], df["margem_pct"], textos, dicas,
        "Margem bruta por categoria (% da receita)", horizontal=True,
    )


def grafico_categoria_devolucao(df: pd.DataFrame) -> go.Figure:
    textos = [pct(v) for v in df["taxa_devolucao"]]
    dicas = [
        f"Taxa de devolução: {pct(t)}<br>Valor devolvido: {dinheiro(v)}"
        f"<br>Itens devolvidos: {numero(d)} de {numero(e)}"
        for t, v, d, e in zip(
            df["taxa_devolucao"], df["valor_devolvido"], df["itens_devolvidos"], df["itens_entregues"]
        )
    ]
    return _barras(
        df["categoria"], df["taxa_devolucao"], textos, dicas,
        "Taxa de devolução por categoria (% da receita)", horizontal=True,
    )


def grafico_top_produtos(df: pd.DataFrame) -> go.Figure:
    df = df.sort_values("receita_bruta", ascending=False)
    rotulos = [f"{n} #{int(i)}" for n, i in zip(df["nome"], df["produto_id"])]
    textos = [dinheiro(v) for v in df["receita_bruta"]]
    dicas = [
        f"Receita bruta: {dinheiro(v)}<br>Categoria: {c}<br>Unidades: {numero(q)}"
        for v, c, q in zip(df["receita_bruta"], df["categoria"], df["quantidade"])
    ]
    return _barras(
        rotulos, df["receita_bruta"], textos, dicas,
        "Top 10 produtos por receita", horizontal=True, altura=420,
    )


def grafico_estado(df: pd.DataFrame) -> go.Figure:
    df = df.sort_values("receita_bruta", ascending=False)
    # Valor escrito só nas cinco maiores; o eixo e a dica carregam o resto.
    textos = [dinheiro(v) if i < 5 else "" for i, v in enumerate(df["receita_bruta"])]
    dicas = [
        f"Receita bruta: {dinheiro(v)}<br>Participação: {pct(p)}<br>Pedidos: {numero(n)}"
        for v, p, n in zip(df["receita_bruta"], df["participacao"], df["pedidos"])
    ]
    return _barras(
        df["estado"], df["receita_bruta"], textos, dicas,
        "Receita por estado", horizontal=True, altura=760,
        eixo_valor=dict(
            showticklabels=True, tickformat=",.0f", tickprefix="US$ ",
            showgrid=True, gridcolor=LINHA,
        ),
    )


def grafico_cidade(df: pd.DataFrame) -> go.Figure:
    df = df.sort_values("receita_bruta", ascending=False)
    rotulos = [f"{c} ({e})" for c, e in zip(df["cidade"], df["estado"])]
    textos = [dinheiro(v) for v in df["receita_bruta"]]
    dicas = [
        f"Receita bruta: {dinheiro(v)}<br>Pedidos: {numero(n)}"
        for v, n in zip(df["receita_bruta"], df["pedidos"])
    ]
    return _barras(
        rotulos, df["receita_bruta"], textos, dicas,
        "Top 10 cidades por receita", horizontal=True, altura=420,
    )


def grafico_tamanho_pedido(df: pd.DataFrame) -> go.Figure:
    textos = [numero(v) for v in df["pedidos"]]
    dicas = [
        f"Pedidos: {numero(p)}<br>Receita bruta: {dinheiro(r)}<br>Ticket médio: {dinheiro(t)}"
        for p, r, t in zip(df["pedidos"], df["receita_bruta"], df["ticket_medio"])
    ]
    fig = _barras(
        [str(int(n)) for n in df["linhas_no_pedido"]], df["pedidos"], textos, dicas,
        "Pedidos entregues por número de linhas de item", horizontal=False, altura=340,
    )
    fig.update_xaxes(title="Linhas de item no pedido")
    return fig


def tabela_qualidade(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Verificação": df["verificacao"],
            "Descrição": df["descricao"],
            "Ocorrências": [numero(v) for v in df["ocorrencias"]],
            "Base": [numero(v) for v in df["base"]],
            "Proporção": [pct(v) for v in df["proporcao"]],
        }
    )
