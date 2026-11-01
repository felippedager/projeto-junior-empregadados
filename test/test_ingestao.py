"""Testes de pipeline/ingestao.py.

Spec (specs/06_testes.md, seção 3, ingestao), com o motivo de cada regra provada:
- Seis tabelas em português com a contagem de cada CSV: a ingestão é cópia fiel.
- Tudo VARCHAR, só o campo vazio vira NULL, "NA" continua texto e "007" continua "007":
  sem inferência, nenhuma conversão acontece sem ser vista.
- Verificação tudo-ou-nada antes de abrir o banco: arquivo faltando ou cabeçalho diferente
  para tudo, não cria banco e não altera o banco existente.
- Contagem gravada diferente da lida para tudo com código 1.
- Reexecução idêntica e sem duplicar; saída com total e milhar com ponto.
"""

import pytest

import apoio
from pipeline import ingestao

TABELAS = ["categorias", "clientes", "produtos", "pedidos", "itens_pedido", "devolucoes"]


def rodar_ok(monkeypatch, tmp_path):
    ambiente = apoio.isolar(monkeypatch, tmp_path)
    apoio.escrever_csvs(ambiente.raw)
    ingestao.main()
    return ambiente


def test_tabelas_em_portugues_com_a_contagem_de_cada_csv(monkeypatch, tmp_path):
    ambiente = rodar_ok(monkeypatch, tmp_path)

    for tabela in TABELAS:
        n = apoio.consultar(ambiente.banco, f"SELECT count(*) AS n FROM raw.{tabela}")[0]["n"]
        # contagem escrita em apoio.CONTAGEM_CSV a partir das linhas de cada CSV inventado
        assert n == apoio.CONTAGEM_CSV[tabela], tabela


def test_toda_coluna_fica_varchar(monkeypatch, tmp_path):
    ambiente = rodar_ok(monkeypatch, tmp_path)

    tipos = apoio.consultar(
        ambiente.banco,
        "SELECT DISTINCT data_type FROM information_schema.columns WHERE table_schema = 'raw'",
    )

    assert tipos == [{"data_type": "VARCHAR"}]


def test_campo_vazio_vira_nulo_e_o_texto_na_continua_texto(monkeypatch, tmp_path):
    ambiente = rodar_ok(monkeypatch, tmp_path)

    email = apoio.consultar(ambiente.banco, "SELECT email FROM raw.clientes WHERE customer_id = '2'")
    nome = apoio.consultar(ambiente.banco, "SELECT category_name FROM raw.categorias WHERE category_id = '2'")

    assert email == [{"email": None}]  # campo vazio do CSV
    assert nome == [{"category_name": "NA"}]  # texto "NA" não é nulo


def test_zero_a_esquerda_e_preservado(monkeypatch, tmp_path):
    ambiente = rodar_ok(monkeypatch, tmp_path)

    ids = apoio.consultar(ambiente.banco, "SELECT product_id FROM raw.produtos")

    assert ids == [{"product_id": "007"}]


def test_rodar_duas_vezes_nao_duplica_e_imprime_igual(monkeypatch, tmp_path, capsys):
    ambiente = rodar_ok(monkeypatch, tmp_path)
    primeira = capsys.readouterr().out

    ingestao.main()
    segunda = capsys.readouterr().out

    assert primeira == segunda
    total = sum(
        apoio.consultar(ambiente.banco, f"SELECT count(*) AS n FROM raw.{t}")[0]["n"] for t in TABELAS
    )
    assert total == sum(apoio.CONTAGEM_CSV.values())


def test_arquivo_faltando_lista_todos_e_nao_cria_o_banco(monkeypatch, tmp_path, capsys):
    ambiente = apoio.isolar(monkeypatch, tmp_path)
    apoio.escrever_csvs(ambiente.raw)
    (ambiente.raw / "orders.csv").unlink()  # faltam dois arquivos: a lista tem que trazer os dois
    (ambiente.raw / "returns.csv").unlink()

    with pytest.raises(SystemExit) as saida:
        ingestao.main()

    texto = capsys.readouterr().out
    assert saida.value.code == 1
    assert "orders.csv" in texto
    assert "returns.csv" in texto
    assert "pipeline.ingestao" in texto
    assert not ambiente.banco.exists()


def test_cabecalho_diferente_para_tudo_e_nao_cria_o_banco(monkeypatch, tmp_path, capsys):
    ambiente = apoio.isolar(monkeypatch, tmp_path)
    cabecalhos = dict(apoio.CABECALHOS)
    cabecalhos["products.csv"] = "product_id,product_name,category_id,preco,cost_price"  # price virou preco
    apoio.escrever_csvs(ambiente.raw, cabecalhos=cabecalhos)

    with pytest.raises(SystemExit) as saida:
        ingestao.main()

    texto = capsys.readouterr().out
    assert saida.value.code == 1
    assert "products.csv" in texto
    assert "preco" in texto
    assert not ambiente.banco.exists()


def test_cabecalho_diferente_nao_altera_banco_existente(monkeypatch, tmp_path):
    ambiente = rodar_ok(monkeypatch, tmp_path)
    antes = apoio.hash_do(ambiente.banco)
    cabecalhos = dict(apoio.CABECALHOS)
    cabecalhos["orders.csv"] = "order_id,customer_id,status,payment_method"  # order_status virou status
    apoio.escrever_csvs(ambiente.raw, cabecalhos=cabecalhos)

    with pytest.raises(SystemExit) as saida:
        ingestao.main()

    assert saida.value.code == 1
    assert apoio.hash_do(ambiente.banco) == antes


def test_contagem_divergente_para_com_codigo_1(monkeypatch, tmp_path, capsys):
    ambiente = apoio.isolar(monkeypatch, tmp_path)
    apoio.escrever_csvs(ambiente.raw)
    # Só assim a divergência acontece com DuckDB de verdade: troca a função de gravar por uma que
    # relata uma linha a menos do que o CSV tinha.
    monkeypatch.setattr(ingestao, "gravar", lambda con, df, schema, tabela: len(df) - 1)

    with pytest.raises(SystemExit) as saida:
        ingestao.main()

    texto = capsys.readouterr().out
    assert saida.value.code == 1
    assert "Contagem divergente em raw.categorias" in texto
    assert "esperado 2, obtido 1" in texto


def test_saida_tem_total_e_milhar_com_ponto(monkeypatch, tmp_path, capsys):
    ambiente = apoio.isolar(monkeypatch, tmp_path)
    linhas = dict(apoio.LINHAS_CSV)
    # 1.000 clientes: o mínimo para a contagem ter separador de milhar
    linhas["customers.csv"] = [f"{i},C{i},c{i}@x,2026-01-22,P,X" for i in range(1, 1001)]
    apoio.escrever_csvs(ambiente.raw, linhas=linhas)

    ingestao.main()

    texto = capsys.readouterr().out.splitlines()
    clientes = next(l for l in texto if l.startswith("raw.clientes"))
    total = next(l for l in texto if l.startswith("Total"))
    assert clientes.endswith("1.000 linhas")
    # total = 2 + 1000 + 1 + 1 + 1 + 1 = 1.006
    assert total.endswith("1.006 linhas")
