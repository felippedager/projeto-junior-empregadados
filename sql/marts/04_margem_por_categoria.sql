-- Pergunta: qual categoria dá mais margem?
-- Grão: uma categoria.
-- Margem bruta = (preco_unitario - custo) * quantidade dos itens de pedidos Delivered, antes das
-- devoluções. O custo é o atual de produtos: o dado não guarda o custo no momento da venda.
WITH vendas AS (
    SELECT pr.categoria_id, i.quantidade, i.preco_unitario, pr.custo
    FROM refined.itens_pedido i
    JOIN refined.pedidos  p  ON p.pedido_id   = i.pedido_id
    JOIN refined.produtos pr ON pr.produto_id = i.produto_id
    WHERE p.status = 'Delivered'
),
por_categoria AS (
    SELECT
        c.categoria_id,
        c.nome AS categoria,
        sum(v.preco_unitario * v.quantidade) AS receita_bruta,
        sum(v.custo * v.quantidade)          AS custo_total
    FROM refined.categorias c
    LEFT JOIN vendas v ON v.categoria_id = c.categoria_id
    GROUP BY c.categoria_id, c.nome
)
SELECT
    categoria_id,
    categoria,
    CAST(receita_bruta AS DECIMAL(18,2))               AS receita_bruta,
    CAST(custo_total AS DECIMAL(18,2))                 AS custo_total,
    CAST(receita_bruta - custo_total AS DECIMAL(18,2)) AS margem,
    ROUND(CAST(receita_bruta - custo_total AS DOUBLE) / NULLIF(CAST(receita_bruta AS DOUBLE), 0), 4) AS margem_pct
FROM por_categoria
ORDER BY categoria_id
