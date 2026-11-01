"""Testes de relatorio.py (gera relatorio.html).

Spec (specs/06_testes.md, seção 3, relatorio), com o motivo de cada regra provada:
- Um HTML completo, com plotly.js de CDN carregado uma vez e dez gráficos de id fixo
  (grafico_1 a grafico_10): sem id fixo o plotly sorteia um por execução e dois relatórios do
  mesmo dado deixam de ser comparáveis por diff.
- Cartões batem com os marts; duas gerações no mesmo minuto saem idênticas e entre minutos só o
  rodapé muda (o relógio é trocado com monkeypatch).
- Todo texto é escapado; sem banco ou sem mart o script para com código 1 e o relatório
  anterior continua intacto.
Valores esperados: contas à mão em apoio.py (receita 120,00, devolvido 80,00, ...).
"""

import difflib
import re
from datetime import datetime as DateTime

import apoio
import pytest

import painel
import relatorio


def relogio(monkeypatch, momento):
    class Falso(DateTime):
        @classmethod
        def now(cls, tz=None):
            return momento

    monkeypatch.setattr(relatorio, "datetime", Falso)


def gerar(monkeypatch, tmp_path, momento=DateTime(2026, 10, 31, 21, 8)):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)
    relogio(monkeypatch, momento)
    relatorio.main()
    return ambiente


def test_gera_um_html_completo_com_um_script_de_cdn(monkeypatch, tmp_path):
    ambiente = gerar(monkeypatch, tmp_path)

    texto = ambiente.saida.read_text(encoding="utf-8")

    assert texto.startswith("<!DOCTYPE html>")
    assert '<meta charset="utf-8">' in texto
    assert "<body>" in texto and "</html>" in texto
    assert len(re.findall(r'<script[^>]+src="https://cdn\.plot\.ly/', texto)) == 1  # plotly.js uma vez só


def test_graficos_tem_ids_fixos_de_1_a_10(monkeypatch, tmp_path):
    ambiente = gerar(monkeypatch, tmp_path)

    ids = re.findall(r'<div id="(grafico_\d+)"', ambiente.saida.read_text(encoding="utf-8"))

    assert ids == [f"grafico_{i}" for i in range(1, 11)]  # dez, sem repetição, na ordem da página


def test_cartoes_do_relatorio_batem_com_os_marts(monkeypatch, tmp_path):
    ambiente = gerar(monkeypatch, tmp_path)

    texto = ambiente.saida.read_text(encoding="utf-8")

    # receita 120, devolvido 80, líquida 40, taxa 80/120, ticket 120/3, pedidos entregues 4
    for esperado in ["US$ 120,00", "US$ 80,00", "US$ 40,00", "66,67%", ">4<"]:
        assert esperado in texto
    assert texto.count("US$ 40,00") >= 2  # líquida e ticket médio valem 40 cada


def test_duas_geracoes_no_mesmo_minuto_sao_identicas(monkeypatch, tmp_path):
    ambiente = gerar(monkeypatch, tmp_path)
    primeira = ambiente.saida.read_bytes()

    relatorio.main()

    assert ambiente.saida.read_bytes() == primeira


def test_so_o_rodape_muda_entre_minutos(monkeypatch, tmp_path):
    ambiente = gerar(monkeypatch, tmp_path, DateTime(2026, 10, 31, 21, 8))
    antes = ambiente.saida.read_text(encoding="utf-8").splitlines()

    relogio(monkeypatch, DateTime(2026, 11, 2, 9, 45))
    relatorio.main()
    depois = ambiente.saida.read_text(encoding="utf-8").splitlines()

    mudou = [l for l in difflib.unified_diff(antes, depois, lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    assert mudou == [
        '-<p class="rodape">Gerado em 31/10/2026 21:08</p>',
        '+<p class="rodape">Gerado em 02/11/2026 09:45</p>',
    ]


def test_texto_do_relatorio_e_escapado(monkeypatch, tmp_path):
    apoio.montar_marts(monkeypatch, tmp_path)
    dados = {nome: painel.ler(nome) for nome in painel.MARTS}
    dados["qualidade_dados"].loc[0, "descricao"] = "x & <y>"  # linha inventada com & e <

    documento, _ = relatorio.montar_html(dados)

    assert "x &amp; &lt;y&gt;" in documento
    assert "x & <y>" not in documento
    cartao = relatorio.cartao("A & B", "<1>", '"x"')
    assert "A &amp; B" in cartao and "&lt;1&gt;" in cartao and "&quot;x&quot;" in cartao


def test_sem_banco_para_e_nao_cria_o_arquivo(monkeypatch, tmp_path, capsys):
    ambiente = apoio.isolar(monkeypatch, tmp_path)

    with pytest.raises(SystemExit) as saida:
        relatorio.main()

    assert saida.value.code == 1
    assert "pipeline.ingestao" in capsys.readouterr().out
    assert not ambiente.saida.exists()
    assert not ambiente.banco.exists()


def test_falha_nao_altera_o_relatorio_anterior(monkeypatch, tmp_path, capsys):
    ambiente = apoio.isolar(monkeypatch, tmp_path)
    apoio.criar_refined(ambiente.banco)  # o banco existe, mas os marts não
    ambiente.saida.write_text("<html>anterior</html>", encoding="utf-8")
    antes = apoio.hash_do(ambiente.saida)

    with pytest.raises(SystemExit) as saida:
        relatorio.main()

    assert saida.value.code == 1
    assert "pipeline.marts" in capsys.readouterr().out
    assert apoio.hash_do(ambiente.saida) == antes


def test_saida_traz_tamanho_e_numero_de_graficos(monkeypatch, tmp_path, capsys):
    ambiente = apoio.montar_marts(monkeypatch, tmp_path)
    capsys.readouterr()
    relogio(monkeypatch, DateTime(2026, 10, 31, 21, 8))

    relatorio.main()

    tamanho = len(ambiente.saida.read_bytes())
    esperado = f"{tamanho:,}".replace(",", ".")
    assert capsys.readouterr().out == f"relatorio.html gerado: {esperado} bytes, 10 gráficos\n"
