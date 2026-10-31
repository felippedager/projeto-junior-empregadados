-- Pergunta: quantas linhas de item e que valor tem um pedido típico?
-- Grão: um tamanho de pedido = número de linhas de item que o pedido tem; só pedidos Delivered
-- com item. "Linhas" e não "unidades": a quantidade é outra coluna; aqui importa quantos itens
-- distintos o cliente pôs no pedido.
WITH por_pedido AS (
    SELECT
        i.pedido_id,
        count(*) AS linhas,
        sum(i.preco_unitario * i.quantidade) AS valor
    FROM refined.itens_pedido i
    JOIN refined.pedidos p ON p.pedido_id = i.pedido_id
    WHERE p.status = 'Delivered'
    GROUP BY i.pedido_id
)
SELECT
    linhas AS linhas_no_pedido,
    count(*) AS pedidos,
    CAST(sum(valor) AS DECIMAL(18,2)) AS receita_bruta,
    CAST(ROUND(CAST(sum(valor) AS DOUBLE) / NULLIF(count(*), 0), 2) AS DECIMAL(18,2)) AS ticket_medio
FROM por_pedido
GROUP BY linhas
ORDER BY linhas
