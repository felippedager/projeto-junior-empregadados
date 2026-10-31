-- Pergunta: quanto vendemos, quanto devolvemos e qual o ticket médio?
-- Grão: uma linha, o negócio inteiro.
-- Receita = itens de pedidos Delivered (Canceled não aconteceu, In Transit não se realizou).
-- Ticket médio = receita bruta / pedidos entregues COM item (528 entregues sem item têm valor
-- zero por defeito do dado e diluiriam o ticket).
WITH vendas AS (
    SELECT
        CAST(sum(i.preco_unitario * i.quantidade) AS DECIMAL(18,2)) AS receita_bruta,
        count(*)                                                     AS itens_entregues,
        count(DISTINCT i.pedido_id)                                  AS pedidos_entregues_com_item
    FROM refined.itens_pedido i
    JOIN refined.pedidos p ON p.pedido_id = i.pedido_id
    WHERE p.status = 'Delivered'
),
devolvido AS (
    SELECT
        CAST(sum(valor_reembolso) AS DECIMAL(18,2)) AS valor_devolvido,
        count(*)                                    AS itens_devolvidos
    FROM refined.devolucoes
),
entregues AS (
    SELECT count(*) AS pedidos_entregues FROM refined.pedidos WHERE status = 'Delivered'
)
SELECT
    v.receita_bruta,
    d.valor_devolvido,
    CAST(v.receita_bruta - d.valor_devolvido AS DECIMAL(18,2)) AS receita_liquida,
    ROUND(CAST(d.valor_devolvido AS DOUBLE) / NULLIF(CAST(v.receita_bruta AS DOUBLE), 0), 4) AS taxa_devolucao,
    v.itens_entregues,
    d.itens_devolvidos,
    e.pedidos_entregues,
    v.pedidos_entregues_com_item,
    CAST(ROUND(CAST(v.receita_bruta AS DOUBLE) / NULLIF(v.pedidos_entregues_com_item, 0), 2) AS DECIMAL(18,2)) AS ticket_medio
FROM vendas v, devolvido d, entregues e
