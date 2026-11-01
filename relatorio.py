"""Etapa 5: relatório. Gera relatorio.html, um arquivo só, a partir dos marts.

Comando: uv run python relatorio.py

Spec (specs/05_relatorio.md), com o motivo de cada regra:

1. ESCOPO. Lê os onze marts pelo painel.ler e monta as mesmas seis faixas do app: números do
   negócio, status e pagamento, categorias, estado e cidade, tamanho do pedido, qualidade.
   Não calcula nem desenha gráfico: cartões, gráficos e tabela vêm de painel.py.
   Motivo: relatório e painel têm que mostrar os mesmos números e os mesmos gráficos; duas
   implementações divergiriam. Sem filtro por categoria: o arquivo é estático e a faixa 3
   mostra todas as categorias.

2. UM ARQUIVO SÓ. Texto, CSS inline e gráficos no mesmo HTML; plotly.js por CDN, carregado
   uma vez (no primeiro gráfico). Motivo: embutir o plotly.js pesa cerca de 4 MB, e com CDN os
   dez gráficos pesam cerca de 90 KB. Consequência: ver os gráficos exige internet. Sem
   JavaScript próprio, fundo branco em qualquer tema: é um documento para ler e imprimir.

3. IDS FIXOS. div_id grafico_1 a grafico_10, na ordem da página. Motivo: sem div_id o plotly
   sorteia um identificador por execução e dois relatórios do mesmo dado deixam de ser
   comparáveis por diff.

4. RODAPÉ. "Gerado em DD/MM/AAAA HH:MM", numa linha própria: a única parte que depende do
   relógio. Motivo: o leitor precisa saber de quando é o número, e o diff entre duas versões
   fica com uma linha.

5. ESCAPE. Todo texto que entra no HTML passa por escape ("Home & Kitchen Furniture" não
   pode quebrar a marcação).

6. SAÍDA. "relatorio.html gerado: N bytes, 10 gráficos"; N é o tamanho lido de volta do disco.

REEXECUÇÃO. Sobrescreve o arquivo; só o rodapé muda. O arquivo só é escrito depois de todo o
HTML estar pronto na memória, então uma falha no meio não estraga o relatório anterior.
Gravado com quebra de linha LF (write_bytes), para o arquivo não depender do sistema.

ERRO. PainelErro (banco ou mart ausente): imprime a mensagem dele, sai com 1, não cria nem
altera relatorio.html. O banco nunca é criado por este script.
"""

import html
import sys
from datetime import datetime
from pathlib import Path

import plotly.io as pio

import painel

SAIDA = Path(__file__).resolve().parent / "relatorio.html"

CSS = """
:root { color-scheme: light; }
body { margin: 0; background: #fff; color: #1f2328;
       font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1280px; margin: 0 auto; padding: 32px 24px; }
h1 { font-size: 30px; margin: 0 0 4px; }
h2 { font-size: 20px; margin: 40px 0 12px; border-bottom: 1px solid #d8d8d4; padding-bottom: 6px; }
.legenda { color: #57606a; margin: 0 0 8px; }
.cartoes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.cartao { border: 1px solid #d8d8d4; border-radius: 8px; padding: 14px 16px; }
.cartao .rotulo { color: #57606a; font-size: 14px; }
.cartao .valor { font-size: 28px; font-weight: 600; margin: 4px 0; }
.cartao .ajuda { color: #57606a; font-size: 12px; }
.duas { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.grafico { break-inside: avoid; min-width: 0; }
.nota { color: #57606a; font-size: 13px; margin: 0; }
table.tabela { border-collapse: collapse; width: 100%; font-size: 14px; }
table.tabela th, table.tabela td { border-bottom: 1px solid #d8d8d4; padding: 6px 10px; text-align: left; }
table.tabela th { background: #f6f6f3; }
.rodape { color: #57606a; font-size: 13px; margin: 40px 0 0; }
@media (max-width: 800px) { .cartoes, .duas { grid-template-columns: 1fr; } }
"""


def esc(texto) -> str:
    return html.escape(str(texto))


def cartao(rotulo: str, valor: str, ajuda: str) -> str:
    return (
        '<div class="cartao">'
        f'<div class="rotulo">{esc(rotulo)}</div>'
        f'<div class="valor">{esc(valor)}</div>'
        f'<div class="ajuda">{esc(ajuda)}</div>'
        "</div>"
    )


def montar_html(dados: dict) -> tuple[str, int]:
    """Devolve (documento, número de gráficos). Os gráficos recebem grafico_1, grafico_2..."""
    contador = 0

    def grafico(figura) -> str:
        nonlocal contador
        contador += 1
        corpo = pio.to_html(
            figura,
            full_html=False,
            include_plotlyjs="cdn" if contador == 1 else False,  # plotly.js uma vez só
            div_id=f"grafico_{contador}",
            config={"responsive": True},
        )
        return f'<div class="grafico">{corpo}</div>'

    def duas(esquerda, direita) -> str:
        return f'<div class="duas">{grafico(esquerda)}{grafico(direita)}</div>'

    # A ordem das chamadas abaixo é a ordem da página, que define grafico_1..grafico_10.
    p = painel
    cartoes = "".join(cartao(*c) for c in p.cartoes(dados["kpis"]))
    faixa2 = (
        grafico(p.grafico_status(dados["receita_por_status"]))
        + duas(
            p.grafico_pagamento_receita(dados["pagamento_por_metodo"]),
            p.grafico_pagamento_cancelamento(dados["pagamento_por_metodo"]),
        )
    )
    faixa3 = duas(
        p.grafico_categoria_receita(dados["receita_por_categoria"]),
        p.grafico_categoria_margem(dados["margem_por_categoria"]),
    ) + duas(
        p.grafico_categoria_devolucao(dados["devolucao_por_categoria"]),
        p.grafico_top_produtos(dados["top_produtos"]),
    )
    faixa4 = duas(p.grafico_estado(dados["receita_por_estado"]), p.grafico_cidade(dados["receita_por_cidade"]))
    faixa5 = grafico(p.grafico_tamanho_pedido(dados["tamanho_pedido"]))
    tabela = p.tabela_qualidade(dados["qualidade_dados"]).to_html(
        index=False, border=0, classes="tabela", escape=True
    )
    gerado = datetime.now().strftime("%d/%m/%Y %H:%M")

    documento = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório de vendas — e-commerce</title>
<style>{CSS}</style>
</head>
<body>
<main>
<h1>Relatório de vendas — e-commerce</h1>
<p class="legenda">{esc("Dados sintéticos. Receita = pedidos entregues. Valores em dólar (US$).")}</p>
<h2>1. Números do negócio</h2>
<div class="cartoes">{cartoes}</div>
<h2>2. Status e pagamento</h2>
{faixa2}
<h2>3. Categorias</h2>
{faixa3}
<p class="nota">Top 10 do negócio inteiro.</p>
<h2>4. Onde compram</h2>
{faixa4}
<h2>5. Tamanho do pedido</h2>
{faixa5}
<h2>6. Qualidade dos dados</h2>
{tabela}
<p class="rodape">Gerado em {gerado}</p>
</main>
</body>
</html>
"""
    return documento, contador


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        dados = {nome: painel.ler(nome) for nome in painel.MARTS}
    except painel.PainelErro as erro:
        print(erro)
        sys.exit(1)

    documento, n_graficos = montar_html(dados)
    # Só aqui o arquivo é tocado: o HTML inteiro já está pronto na memória.
    SAIDA.write_bytes(documento.encode("utf-8"))
    tamanho = len(SAIDA.read_bytes())
    print(f"{SAIDA.name} gerado: {painel.numero(tamanho)} bytes, {n_graficos} gráficos")


if __name__ == "__main__":
    main()
