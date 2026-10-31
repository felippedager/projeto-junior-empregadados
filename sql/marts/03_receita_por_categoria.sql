-- Pergunta: qual categoria vende mais?
-- Grão: uma categoria.
-- Receita bruta = itens de pedidos Delivered. participacao = receita da categoria / receita total.
WITH vendas AS (
    SELECT pr.categoria_id, i.quantidade, i.preco_unitario
    FROM refined.itens_pedido i
    JOIN refined.pedidos  p  ON p.pedido_id   = i.pedido_id
    JOIN refined.produtos pr ON pr.produto_id = i.produto_id
    WHERE p.status = 'Delivered'
),
por_categoria AS (
    SELECT
        c.categoria_id,
        c.nome AS categoria,
        count(v.quantidade) AS itens,
        sum(v.quantidade)   AS quantidade,
        sum(v.preco_unitario * v.quantidade) AS receita_bruta
    FROM refined.categorias c
    LEFT JOIN vendas v ON v.categoria_id = c.categoria_id
    GROUP BY c.categoria_id, c.nome
)
SELECT
    categoria_id,
    categoria,
    itens,
    quantidade,
    CAST(receita_bruta AS DECIMAL(18,2)) AS receita_bruta,
    ROUND(CAST(receita_bruta AS DOUBLE) / NULLIF(CAST(sum(receita_bruta) OVER () AS DOUBLE), 0), 4) AS participacao
FROM por_categoria
ORDER BY categoria_id
