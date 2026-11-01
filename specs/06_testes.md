CONTEXTO
Pipeline de dados em Python sobre um dataset sintético de e-commerce (Faker `en_IN`, 6 CSVs).
Trabalho com spec-driven development: a spec abaixo é a fonte da verdade e o código é
consequência dela. Não acrescente requisito que não esteja escrito aqui. Se algo estiver
ambíguo, pergunte antes de escrever código. As regras de teste do CLAUDE.md (seção Testes) valem
inteiras e não são repetidas aqui, só aplicadas.

STACK
- Python 3.13, uv, DuckDB de verdade (nada de mock do banco)
- pytest e pytest-cov (já instalados, config no pyproject.toml)

O QUE JÁ EXISTE (use, não reimplemente)
Módulos a testar, todos já entregues e aprovados:
  pipeline/db.py             constantes BANCO e PASTA_RAW; conectar, criar_schema, gravar
  pipeline/ingestao.py       raw: 6 CSVs lidos como texto
  pipeline/transformacao.py  refined: tipos estritos, nomes, duplicata, atomicidade
  pipeline/marts.py          orquestrador de sql/marts/*.sql
  sql/marts/01..11_*.sql     os onze marts
  painel.py                  leitura, formatos, cartões, filtro, 10 gráficos, tabela de qualidade
  relatorio.py               relatorio.html
Fora do escopo: app.py (só monta a página; já está no omit da cobertura) e o visual no
navegador. Nada disso se testa aqui; a spec da etapa 5 já diz que o visual é verificação humana.

ARTEFATOS A PRODUZIR
Um arquivo por módulo, mais um módulo de apoio (funções, não fixtures):
  test/test_db.py   test/test_ingestao.py   test/test_transformacao.py
  test/test_marts.py (orquestrador e os onze SQLs)   test/test_painel.py   test/test_relatorio.py
  test/apoio.py      entrada inventada compartilhada e isolamento (item 2)
executáveis com:
  uv run pytest --cov

SPEC

1. ISOLAMENTO (nada toca o projeto real)
   Nenhum teste abre ecommerce.duckdb, nem lê raw/. Tudo em tmp_path, com CSV .csv escritos pelo
   próprio teste e DuckDB de verdade. As constantes de caminho são trocadas com monkeypatch,
   em todos os módulos que as importaram por nome (db.BANCO; ingestao.PASTA_RAW;
   transformacao.BANCO; marts.BANCO e marts.PASTA_SQL; painel.BANCO; relatorio.SAIDA): a função
   apoio.isolar(monkeypatch, tmp_path) faz isso e devolve os caminhos temporários.
   Todo teste que toca banco ou arquivo chama isolar primeiro.
   Motivo: os módulos fazem "from pipeline.db import BANCO", que copia o nome; trocar só db.BANCO
   deixaria o resto apontando para o banco real. Um teste que escreve no banco do projeto
   estragaria os dados e passaria "por sorte".
   Os testes dos SQLs de marts leem os arquivos .sql reais de sql/marts (é o código sob teste),
   mas só rodam sobre tabelas refined inventadas.
   Motivo de apoio.py ser funções e não fixtures: o CLAUDE.md permite só tmp_path e monkeypatch.

2. ENTRADA INVENTADA (apoio.py)
   Cada linha inventada traz um comentário dizendo por que existe. O valor esperado de cada
   teste sai da conta feita à mão sobre essa entrada, escrita no comentário do teste, nunca de um
   número medido no dado real. Entrada refined usada pelos marts e pelo painel:
     categorias  1 Cat A, 2 Cat B
     clientes    c1 (X, P), c2 (X, Q), c3 (Y, P: mesma cidade de c1 em outro estado), c4 sem pedido
     produtos    p1 "N" cat 1 preco 10,00 custo 6,00; p2 "N" cat 2 preco 20,00 custo 15,00
                 (mesmo nome, categorias diferentes); p3 "M" cat 1, nunca vendido
     pedidos     o1 c1 Delivered Card; o2 c2 Delivered UPI; o3 c3 Canceled UPI; o4 c1 In Transit
                 Card; o5 c2 Delivered Card sem itens; o6 c3 Delivered UPI
     itens       i1 o1 p1 q2; i2 o1 p2 q1; i3 o2 p2 q3; i4 o3 p1 q5; i5 o4 p1 q1; i6 o6 p1 q1;
                 i7 o6 p1 q1 (par pedido-produto repetido); preço unitário igual ao do produto
     devolucoes  d1 sobre i3 valor 60,00; d2 sobre i1 valor 20,00
   Contas à mão sobre essa entrada (receita só de itens de pedido Delivered):
     receita bruta 20+20+60+10+10 = 120,00; devolvido 80,00; líquida 40,00; taxa 80/120 = 0,6667;
     itens entregues 5; pedidos entregues 4, com item 3; ticket 120/3 = 40,00.
     Cat A: itens 3, unidades 4, receita 40,00, custo 24,00, margem 16,00 (0,4), devolvido 20,00
     (taxa 0,5). Cat B: itens 2, unidades 4, receita 80,00, custo 60,00, margem 20,00 (0,25),
     devolvido 60,00 (taxa 0,75). Estado X 100,00 (2 pedidos), Y 20,00 (1). Cidades (X,P) 40,
     (X,Q) 60, (Y,P) 20. Método Card: 3 pedidos, 2 entregues, receita 40,00; UPI: 3 pedidos,
     2 entregues, 1 cancelado (0,3333), receita 80,00. Tamanho: 1 linha -> 1 pedido, 60,00;
     2 linhas -> 2 pedidos, 60,00 (ticket 30,00).
   Entradas menores são montadas no próprio teste quando uma regra pede (chave conflitante,
   valor 'abc', etc.), a partir de apoio.

3. O QUE CADA MÓDULO PROVA (cada item é uma frase = o nome de um teste; o nome real segue
   test_<frase com underscores>)
   db
     banco_e_raw_ficam_na_raiz_do_projeto; conectar_cria_o_arquivo_se_faltar;
     conectar_somente_leitura_nao_cria_o_arquivo; criar_schema_e_idempotente;
     gravar_devolve_a_contagem_lida_do_banco; gravar_substitui_e_nao_acrescenta
   ingestao
     tabelas_em_portugues_com_a_contagem_de_cada_csv; toda_coluna_fica_varchar;
     campo_vazio_vira_nulo_e_o_texto_na_continua_texto; zero_a_esquerda_e_preservado;
     rodar_duas_vezes_nao_duplica_e_imprime_igual; arquivo_faltando_lista_todos_e_nao_cria_o_banco;
     cabecalho_diferente_para_tudo_e_nao_cria_o_banco; cabecalho_diferente_nao_altera_banco_existente;
     contagem_divergente_para_com_codigo_1; saida_tem_total_e_milhar_com_ponto
   transformacao
     tipos_e_nomes_do_refined; clientes_perdem_name_e_email; ids_viram_inteiro_e_dinheiro_fica_decimal;
     soma_de_dinheiro_fecha_centavo_por_centavo; linha_inteira_repetida_sai_uma_vez_e_e_contada;
     chave_repetida_com_conteudo_diferente_para_tudo; valor_nao_numerico_para_e_diz_tabela_coluna_e_valor;
     mais_de_duas_casas_decimais_para_em_vez_de_arredondar; inteiro_com_casa_decimal_para_em_vez_de_arredondar;
     data_invalida_para_e_diz_o_valor; nulo_e_mantido_e_nao_preenchido; pedido_sem_item_continua_no_refined;
     falha_no_meio_nao_muda_nenhuma_tabela; raw_faltando_lista_o_que_falta_e_nao_cria_o_banco;
     rodar_duas_vezes_imprime_igual; saida_mostra_colunas_fora_e_nulos_mantidos
   marts (orquestrador)
     um_mart_por_arquivo_com_o_nome_sem_o_prefixo; apagar_o_arquivo_faz_o_mart_sumir;
     nome_sem_prefixo_para_sem_tocar_o_banco; nomes_repetidos_depois_do_prefixo_param;
     sql_com_erro_para_e_mantem_os_marts_antigos; mart_vazio_para_e_mantem_os_marts_antigos;
     pasta_sem_sql_para; refined_faltando_lista_o_que_falta_e_nao_cria_o_banco;
     saida_usa_singular_para_uma_linha_e_total; rodar_duas_vezes_imprime_igual
   Dois testes entraram além da lista acima, acrescentados na implementação:
     marts: falha_na_construcao_desfaz_a_transacao_mesmo_com_a_conexao_aberta (a M6, sem o
       ROLLBACK, sobrevivia a todos os outros testes: fechar a conexão já descarta a transação,
       então só olhando pela mesma conexão aberta se prova que o construir() faz o ROLLBACK)
     transformacao: tabela_de_raw_faltando_lista_so_a_que_falta (a lista pedia só o caso do banco
       ausente; este cobre uma tabela faltando num banco existente)
   marts (SQLs, rodando o .sql real sobre a entrada de apoio)
     cancelado_e_em_transito_ficam_fora_da_receita; kpis_batem_com_a_conta_feita_a_mao;
     ticket_divide_so_pelos_pedidos_entregues_com_item; taxa_sem_vendas_fica_nula_e_nao_zero;
     status_mostra_valor_de_todos_e_marca_so_o_entregue_como_receita;
     categoria_soma_fecha_com_a_receita_total; margem_usa_custo_do_produto;
     top_produtos_nao_confunde_produtos_de_mesmo_nome; cidade_igual_em_estados_diferentes_nao_se_mistura;
     estado_soma_fecha_com_a_receita_total; pagamento_conta_todos_os_pedidos_e_receita_so_dos_entregues;
     devolucao_usa_a_categoria_do_produto_devolvido; tamanho_conta_linhas_de_item_por_pedido;
     qualidade_conta_as_anomalias_da_entrada; qualidade_pega_devolucao_de_pedido_nao_entregue;
     top_produtos_e_cidades_limitam_a_dez
   painel
     formatos_usam_ponto_de_milhar_e_virgula_decimal; formatos_devolvem_traco_para_nulo;
     ler_devolve_o_mart; ler_nome_desconhecido_e_erro_de_programacao; ler_sem_banco_diz_o_comando_e_nao_cria_o_banco;
     ler_sem_mart_diz_o_comando; ler_fecha_a_conexao; cartoes_seguem_o_kpis; filtro_recorta_so_as_categorias_marcadas;
     cada_grafico_e_uma_figura_com_uma_serie_de_barras; rotulos_de_produto_e_cidade_trazem_identificador;
     grafico_de_estados_escreve_valor_so_nas_cinco_maiores; status_destaca_so_o_entregue; tabela_de_qualidade_vem_formatada
   relatorio
     gera_um_html_completo_com_um_script_de_cdn; graficos_tem_ids_fixos_de_1_a_10;
     cartoes_do_relatorio_batem_com_os_marts; duas_geracoes_no_mesmo_minuto_sao_identicas;
     so_o_rodape_muda_entre_minutos; texto_do_relatorio_e_escapado; sem_banco_para_e_nao_cria_o_arquivo;
     falha_nao_altera_o_relatorio_anterior; saida_traz_tamanho_e_numero_de_graficos

4. REGRAS DOS TESTES (aplicação do CLAUDE.md)
   Nome do teste é a frase que ele prova. Sem teste sem assert, sem skip, sem xfail, sem
   try/except em volta de assert, sem pytest.approx em dinheiro (dinheiro compara DECIMAL
   exato). Taxas e participações (fração arredondada a 4 casas pelo mart) comparam com igualdade;
   approx só se a igualdade exata falhar por representação, nunca em dinheiro.
   Erros esperados com pytest.raises(SystemExit) e verificação do código de saída (== 1);
   mensagens conferidas com capsys.
   Sem sleep e sem relógio real: o relógio do relatório é trocado com monkeypatch.

5. META DE COBERTURA
   Cobertura de linhas no total >= 90% (fail_under = 90 no pyproject.toml; o snippet vinha com
   60). Motivo: 60 deixaria passar um módulo inteiro sem teste; com app.py fora, o resto é
   código de comando com poucas linhas que só rodam pelo "if __name__ == '__main__'"
   (uma linha por módulo, que não se cobre por import). 90 deixa essas linhas e mais nada.
   Cobertura sozinha não prova nada: a prova é a mutação (item 6).
   Também entra no omit do coverage a pasta dataset/, que guarda o gerador do dado
   (Data_Extraction.py) e não é parte do pipeline; com source = ["."] ela contaria 0%.
   Isto altera o pyproject.toml da etapa 0: avisado aqui, nada mais nele muda.

6. MUTAÇÃO (feita em uma cópia do projeto, nunca no original)
   Para cada mutação abaixo, quebra-se a regra na cópia, roda-se a suíte e confirma-se que algum
   teste falha. Se alguma mutação sobreviver, ou o teste é reforçado ou o motivo de ela ser
   equivalente é escrito na entrega.
     M1  01_kpis.sql: tirar o filtro status = 'Delivered' da receita
     M2  01_kpis.sql: ticket dividido por pedidos_entregues em vez de pedidos_entregues_com_item
     M3  09_devolucao_por_categoria.sql: trocar a categoria do produto devolvido por outra junção
     M4  07_receita_por_cidade.sql: agrupar só por cidade (sem estado)
     M5  marts.py: tirar o DROP SCHEMA (mart fantasma)
     M6  marts.py: não fazer ROLLBACK na falha
     M7  transformacao.py: trocar regexp do dinheiro por aceitar qualquer número
     M8  transformacao.py: tirar a verificação de chave conflitante
     M9  transformacao.py: preencher nulo com valor (COALESCE) em refined
     M10 ingestao.py: ler sem keep_default_na=False (texto "NA" some)
     M11 ingestao.py: gravar antes de verificar os cabeçalhos
     M12 db.py: criar_schema sem IF NOT EXISTS (deixa de ser idempotente)
     M13 painel.py: dinheiro sem trocar ponto e vírgula
     M14 painel.py: ler sem fechar a conexão
     M15 relatorio.py: sem div_id fixo
     M16 relatorio.py: sem escape no cartão
   Não se muta "gravar devolve len(df) em vez da contagem do banco": com o DuckDB de verdade as
   duas são sempre iguais, então a mutação é indistinguível e só um mock do banco (proibido)
   a mataria. O teste gravar_devolve_a_contagem_lida_do_banco confere que o valor devolvido
   é a contagem da tabela gravada.
   O teste top_produtos_e_cidades_limitam_a_dez monta o próprio refined maior (12 produtos e 12
   cidades vendidos), porque a entrada de apoio só tem 2 produtos e 3 cidades.

ERRO
   A suíte nunca deve falhar por falta de banco real ou de raw/: ela tem que passar numa cópia do
   projeto sem ecommerce.duckdb e sem os CSVs de raw/.

CRITÉRIOS DE ACEITE
- `uv run pytest --cov` passa e imprime cobertura total >= 90%, com a coluna Missing.
- Todo teste da seção 3 existe com esse nome (conferido por pytest --collect-only).
- Nenhum teste usa skip, xfail, pytest.approx em dinheiro, fixtures além de tmp_path/monkeypatch,
  nem try/except em volta de assert (conferido por busca).
- O hash de ecommerce.duckdb e dos seis CSVs de raw/ é o mesmo antes e depois da suíte.
- A suíte passa numa cópia do projeto sem ecommerce.duckdb e sem os CSVs de raw/.
- A suíte roda em menos de 60 segundos.
- As 16 mutações da seção 6 são todas mortas (cada uma faz a suíte falhar); sobreviventes, se
  houver, aparecem listados com o motivo.
- Nenhum arquivo gerado fica no repositório (.coverage, .pytest_cache e *.duckdb estão no
  .gitignore).

ENTREGA, nesta ordem
1. A spec como docstring no topo de cada arquivo de teste (a parte do módulo, com o motivo de
   cada regra provada).
2. O código, com comentários apenas onde a decisão não é óbvia; entrada inventada com comentário
   por linha.
3. Uma lista final do que você assumiu e que não estava na spec. Se a lista não estiver vazia,
   é a minha spec que precisa melhorar.
