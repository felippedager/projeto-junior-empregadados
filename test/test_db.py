"""Testes de pipeline/db.py.

Spec (specs/06_testes.md, seção 3, db), com o motivo de cada regra provada:
- Os caminhos ficam num lugar só, na raiz do projeto: o resto do pipeline confia neles.
- conectar cria o arquivo se faltar, mas em somente leitura nunca cria: o painel não pode gerar
  um banco vazio sem querer.
- criar_schema é idempotente (rodar o pipeline dez vezes = rodar uma).
- gravar substitui a tabela (nunca acrescenta) e devolve a contagem lida da tabela gravada.
"""

import duckdb
import pandas as pd
import pytest

import apoio
from pipeline import db


def test_banco_e_raw_ficam_na_raiz_do_projeto():
    assert db.BANCO == db.RAIZ / "ecommerce.duckdb"
    assert db.PASTA_RAW == db.RAIZ / "raw"
    assert (db.RAIZ / "pyproject.toml").is_file()  # a raiz é onde mora o pyproject


def test_conectar_cria_o_arquivo_se_faltar(monkeypatch, tmp_path):
    ambiente = apoio.isolar(monkeypatch, tmp_path)
    assert not ambiente.banco.exists()

    con = db.conectar()
    con.close()

    assert ambiente.banco.is_file()


def test_conectar_somente_leitura_nao_cria_o_arquivo(monkeypatch, tmp_path):
    ambiente = apoio.isolar(monkeypatch, tmp_path)

    with pytest.raises(duckdb.Error):
        db.conectar(somente_leitura=True)

    assert not ambiente.banco.exists()


def test_criar_schema_e_idempotente(monkeypatch, tmp_path):
    ambiente = apoio.isolar(monkeypatch, tmp_path)
    con = db.conectar()
    try:
        db.criar_schema(con, "meu_schema")
        db.criar_schema(con, "meu_schema")  # segunda chamada não pode estourar nem duplicar
        schemas = con.execute(
            "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'meu_schema'"
        ).fetchall()[0][0]
    finally:
        con.close()

    assert schemas == 1
    assert ambiente.banco.is_file()


def test_gravar_devolve_a_contagem_lida_do_banco(monkeypatch, tmp_path):
    apoio.isolar(monkeypatch, tmp_path)
    df = pd.DataFrame({"a": ["x", "y", "z"]})  # 3 linhas: a contagem esperada é 3
    con = db.conectar()
    try:
        db.criar_schema(con, "s")
        devolvido = db.gravar(con, df, "s", "t")
        no_banco = con.execute("SELECT count(*) FROM s.t").fetchall()[0][0]
    finally:
        con.close()

    assert devolvido == 3
    assert devolvido == no_banco


def test_gravar_substitui_e_nao_acrescenta(monkeypatch, tmp_path):
    apoio.isolar(monkeypatch, tmp_path)
    tres = pd.DataFrame({"a": ["x", "y", "z"]})  # primeira gravação: 3 linhas
    duas = pd.DataFrame({"a": ["x", "y"]})  # segunda gravação: 2 linhas, tem que substituir
    con = db.conectar()
    try:
        db.criar_schema(con, "s")
        db.gravar(con, tres, "s", "t")
        devolvido = db.gravar(con, duas, "s", "t")
        no_banco = con.execute("SELECT count(*) FROM s.t").fetchall()[0][0]
    finally:
        con.close()

    assert devolvido == 2
    assert no_banco == 2
