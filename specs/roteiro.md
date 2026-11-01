# ROTEIRO DAS ETAPAS

Ordem em que as specs são escritas e entregues. Uma etapa só começa quando os critérios de
aceite da anterior passam. Para cada etapa: copie `modelo_etapa.md`, preencha as decisões
listadas aqui e entregue à IA.

```
raw/*.csv.gz -> 1 ingestão -> raw -> 2 transformação -> refined -> 3 marts -> marts
             -> 4 painel/app e 5 relatório HTML          6 testes (cobrem 0 a 5)
```

## 0. Infraestrutura — `pipeline/db.py`
- Entrega: `conectar()` (cria o arquivo se faltar), `criar_schema(con, nome)` (idempotente),
  `gravar(con, df, schema, tabela)` (`CREATE OR REPLACE`, devolve a contagem **lida do banco**).
- Define as constantes de caminho: banco e pasta `raw/`.
- Decida: nome do banco e onde ficam os arquivos brutos.

## 1. Ingestão — `pipeline/ingestao.py` -> schema `raw`
- Lê cada CSV como texto puro (`dtype=str`, sem inferência), campo vazio vira NULL, encoding declarado.
- Nomes de tabela em português; mapa arquivo -> tabela literal.
- Verifica **todos** os arquivos antes de abrir o banco (tudo-ou-nada).
- Decida: lista de arquivos e nomes das tabelas.
- Aceite: mesma contagem de linhas do CSV; rodar duas vezes não duplica.

## 2. Transformação — `pipeline/transformacao.py` -> schema `refined`
- Decisões a tomar, cada uma **com motivo e número auditado no dado**:
  quais tabelas entram e quais ficam de fora; mapa de nomes (completo e literal);
  tipos (data com hora vs só data, dinheiro como DECIMAL, inteiros, identificadores como texto);
  chave de cada tabela; tratamento de duplicata; o que fazer com nulos e anomalias.
- Conversão estrita: falha para tudo, mostra tabela, coluna e um valor de exemplo.
- Aceite: linhas que saem = entram (menos duplicatas), nulos antes = depois, soma de dinheiro
  bate centavo por centavo, identificador com zero à esquerda preservado.
- Exemplo completo: `02_transformacao.md`.

## 3. Marts — `pipeline/marts.py` + `sql/marts/NN_nome.sql` -> schema `marts`
- O orquestrador roda `sql/marts/*.sql` em ordem, cria `marts.<nome>` (sem prefixo `NN_`), numa
  transação única. Valida prefixo, nomes duplicados, mart vazio e SQL com erro.
- Cada `.sql` abre com comentários: a pergunta que responde e o **grão** (uma linha = o quê).
- Decida: a lista de perguntas de negócio. **Cada número que a tela vai mostrar precisa de um mart**,
  inclusive os cartões (um mart `kpis` de uma linha).
- Aceite: um mart por arquivo; apagar o arquivo faz o mart sumir na execução seguinte.

## 4. Painel — `painel.py` + `app.py` (Streamlit + plotly)
- `painel.py`: leitura (`SELECT * FROM marts.<nome>`, conexão `read_only=True` aberta e fechada
  dentro da função), formatação (`reais`, `pct`, `numero` sem `locale`) e **uma função por gráfico**
  que recebe o DataFrame e devolve a figura. Não importa streamlit.
- `app.py`: só monta a página. Proibido calcular (agrupar, somar, média, juntar, pivotar).
- Decida: o layout (faixas, cartões, gráficos), o filtro e o que ele recorta.
- Aceite: cartões com os valores esperados; erro claro se faltar banco ou mart (`st.error` + `st.stop()`);
  rodar o pipeline com o painel de pé não dá erro de lock.
- Rascunho da tela em `design/`.

## 5. Relatório — `relatorio.py` -> `relatorio.html`
- Reaproveita `painel.ler`, as funções de formato e as funções de gráfico. Não desenha gráfico novo.
- Um arquivo só, mesmas faixas do app, plotly via CDN uma vez, `div_id` fixo, rodapé com data e hora.
- Aceite: abre com dois cliques; tamanho abaixo de um limite; rodar duas vezes muda só o rodapé.

## 6. Testes — `test/test_<modulo>.py`
- Um arquivo por módulo. Regras no `CLAUDE.md` (seção Testes). Meta: coverage de linhas no total.
- Cada critério de aceite que descreve uma regra vira pelo menos um teste.
- Os SQLs dos marts são testados rodando o `.sql` real sobre tabelas inventadas.
- Feche com mutação (ver `CLAUDE.md`).

## Opcional
- **Spec adiada:** se uma tabela ficou de fora, deixe a spec dela escrita em `specs/`.
- **Visualizar o banco:** um `ui.py` que abre a interface web do DuckDB. Verifique que o arquivo existe
  antes de conectar, para não criar um banco vazio.
