# Rascunho da tela do painel (etapa 4)

Rascunho de layout, não de visual final. Cada bloco diz de qual mart sai.
Largura total (`layout="wide"`). Barra lateral só com o filtro.

```
┌ barra lateral ──────┐ ┌ página ─────────────────────────────────────────────────────────┐
│ Filtro              │ │ Painel de vendas — e-commerce                                   │
│                     │ │ (dados sintéticos; receita = pedidos entregues; valores em      │
│ Categorias          │ │  dólar, US$)                                                    │
│ [x] Apparel/Fashion │ │                                                                 │
│ [x] Electronics     │ │ ── FAIXA 1: NÚMEROS DO NEGÓCIO (marts.kpis) ──────────────────  │
│ [x] Beauty/Cosmetics│ │ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                 │
│ [x] Home & Kitchen..│ │ │Receita bruta│ │Valor devolv.│ │Receita líq. │                 │
│ [x] Food & Bever... │ │ │426.938.559,6│ │128.389.562,9│ │298.548.996,6│                 │
│ [x] Toys            │ │ └─────────────┘ └─────────────┘ └─────────────┘                 │
│                     │ │ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                 │
│ O filtro recorta    │ │ │Taxa devoluç.│ │Ticket médio │ │Pedidos entr.│                 │
│ só a faixa 3.       │ │ │   30,07%    │ │ 177.006,04  │ │    2.940    │                 │
│ Os cartões são do   │ │ └─────────────┘ └─────────────┘ └─────────────┘                 │
│ negócio inteiro.    │ │   (cartões nunca mudam com o filtro)                            │
└─────────────────────┘ │                                                                 │
                        │ ── FAIXA 2: STATUS E PAGAMENTO ───────────────────────────────  │
                        │ ┌ Valor dos itens por status ┐ ┌ Receita por método ┐           │
                        │ │ barras horizontais, 3      │ │ barras, 4 métodos  │           │
                        │ │ (receita_por_status)       │ │ (pagamento_por_    │           │
                        │ │ Entregue destacada         │ │  metodo)           │           │
                        │ └────────────────────────────┘ └────────────────────┘           │
                        │ ┌ Taxa de cancelamento por método ┐                              │
                        │ │ barras, 4 (pagamento_por_metodo)│                              │
                        │ └─────────────────────────────────┘                              │
                        │                                                                 │
                        │ ── FAIXA 3: CATEGORIAS (recortada pelo filtro) ───────────────  │
                        │ ┌ Receita por categoria ┐ ┌ Margem % por categ. ┐               │
                        │ │ (receita_por_         │ │ (margem_por_        │               │
                        │ │  categoria)           │ │  categoria)         │               │
                        │ └───────────────────────┘ └─────────────────────┘               │
                        │ ┌ Taxa de devolução por categoria ┐ ┌ Top 10 produtos ┐         │
                        │ │ (devolucao_por_categoria)       │ │ (top_produtos)  │         │
                        │ │                                 │ │ rótulo "nome #id"│        │
                        │ └─────────────────────────────────┘ └─────────────────┘         │
                        │                                                                 │
                        │ ── FAIXA 4: ONDE COMPRAM ─────────────────────────────────────  │
                        │ ┌ Receita por estado (28) ┐ ┌ Top 10 cidades ┐                  │
                        │ │ barras horizontais      │ │ (receita_por_   │                  │
                        │ │ (receita_por_estado)    │ │  cidade)        │                  │
                        │ └─────────────────────────┘ └─────────────────┘                  │
                        │                                                                 │
                        │ ── FAIXA 5: TAMANHO DO PEDIDO ────────────────────────────────  │
                        │ ┌ Pedidos por nº de linhas de item (1 a 9) ┐                     │
                        │ │ barras (tamanho_pedido)                  │                     │
                        │ └──────────────────────────────────────────┘                     │
                        │                                                                 │
                        │ ── FAIXA 6: QUALIDADE DOS DADOS ──────────────────────────────  │
                        │ tabela de 6 linhas: verificação | descrição | ocorrências |     │
                        │ base | proporção            (marts.qualidade_dados)             │
                        └─────────────────────────────────────────────────────────────────┘
```

## Regras de leitura da tela
- Dinheiro: `US$ 1.234.567,89` (dólar, formato brasileiro). Percentual: `30,07%`. Contagem: `15.000`.
- Nenhum número é calculado na tela: tudo sai de um dos 11 marts.
- Estado vazio (nenhuma categoria marcada): os quatro gráficos da faixa 3 mostram aviso
  "Nenhuma categoria selecionada" no lugar do gráfico.
- Banco ou mart ausente: só uma mensagem de erro com o comando a rodar; nenhuma outra faixa.
