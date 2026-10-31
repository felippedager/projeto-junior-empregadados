-- Pergunta: qual categoria tem mais devolução?
-- Grão: uma categoria.
-- A categoria de uma devolução é a do produto do item devolvido.
-- taxa_devolucao = valor devolvido / receita bruta da categoria (itens de pedidos Delivered).
-- Contagem sem ocorrência é 0 (é uma contagem); soma de dinheiro sem ocorrência fica NULL.
WITH vendas AS (
    SELECT
        pr.categoria_id,
        count(*) AS itens_entregues,
        sum(i.preco_unitario * i.quantidade) AS receita_bruta
    FROM refined.itens_pedido i
    JOIN refined.pedidos  p  ON p.pedido_id   = i.pedido_id
    JOIN refined.produtos pr ON pr.produto_id = i.produto_id
    WHERE p.status = 'Delivered'
    GROUP BY pr.categoria_id
),
devolvido AS (
    SELECT
        pr.categoria_id,
        count(*) AS itens_devolvidos,
        sum(d.valor_reembolso) AS valor_devolvido
    FROM refined.devolucoes d
    JOIN refined.itens_pedido i  ON i.item_id     = d.item_id
    JOIN refined.produtos     pr ON pr.produto_id = i.produto_id
    GROUP BY pr.categoria_id
)
SELECT
    c.categoria_id,
    c.nome AS categoria,
    COALESCE(v.itens_entregues, 0)  AS itens_entregues,
    COALESCE(d.itens_devolvidos, 0) AS itens_devolvidos,
    CAST(v.receita_bruta AS DECIMAL(18,2))   AS receita_bruta,
    CAST(d.valor_devolvido AS DECIMAL(18,2)) AS valor_devolvido,
    ROUND(CAST(d.valor_devolvido AS DOUBLE) / NULLIF(CAST(v.receita_bruta AS DOUBLE), 0), 4) AS taxa_devolucao
FROM refined.categorias c
LEFT JOIN vendas    v ON v.categoria_id = c.categoria_id
LEFT JOIN devolvido d ON d.categoria_id = c.categoria_id
ORDER BY c.categoria_id
