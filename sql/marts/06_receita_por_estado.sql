-- Pergunta: de quais estados vem a receita?
-- Grão: um estado do cliente.
-- Receita = itens de pedidos Delivered. pedidos = pedidos entregues com item.
WITH por_estado AS (
    SELECT
        c.estado,
        count(DISTINCT i.pedido_id) AS pedidos,
        sum(i.preco_unitario * i.quantidade) AS receita_bruta
    FROM refined.itens_pedido i
    JOIN refined.pedidos  p ON p.pedido_id  = i.pedido_id
    JOIN refined.clientes c ON c.cliente_id = p.cliente_id
    WHERE p.status = 'Delivered'
    GROUP BY c.estado
)
SELECT
    estado,
    pedidos,
    CAST(receita_bruta AS DECIMAL(18,2)) AS receita_bruta,
    ROUND(CAST(receita_bruta AS DOUBLE) / NULLIF(CAST(sum(receita_bruta) OVER () AS DOUBLE), 0), 4) AS participacao
FROM por_estado
ORDER BY estado
