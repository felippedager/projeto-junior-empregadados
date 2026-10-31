-- Pergunta: quanto do valor dos itens está em cada status de pedido?
-- Grão: um status de pedido.
-- Só a linha Delivered é receita; Canceled e In Transit têm valor, mas não se realizaram.
-- O rótulo em português é decisão de mart: refined guarda os valores em inglês.
SELECT
    p.status,
    CASE p.status
        WHEN 'Delivered'  THEN 'Entregue'
        WHEN 'Canceled'   THEN 'Cancelado'
        WHEN 'In Transit' THEN 'Em trânsito'
    END AS rotulo,
    count(DISTINCT p.pedido_id) AS pedidos,
    count(DISTINCT i.pedido_id) AS pedidos_com_item,
    count(i.item_id)            AS itens,
    CAST(sum(i.preco_unitario * i.quantidade) AS DECIMAL(18,2)) AS valor_itens,
    CASE WHEN p.status = 'Delivered' THEN 'sim' ELSE 'não' END AS conta_como_receita
FROM refined.pedidos p
LEFT JOIN refined.itens_pedido i ON i.pedido_id = p.pedido_id
GROUP BY p.status
ORDER BY p.status
