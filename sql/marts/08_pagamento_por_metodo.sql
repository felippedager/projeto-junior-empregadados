-- Pergunta: como se divide a receita e o cancelamento por método de pagamento?
-- Grão: um método de pagamento.
-- pedidos e cancelamentos contam todos os pedidos do método (status é atributo do pedido,
-- com ou sem item). Receita = itens de pedidos Delivered.
WITH contagem AS (
    SELECT
        metodo_pagamento,
        count(*)                                     AS pedidos,
        count(*) FILTER (WHERE status = 'Delivered') AS pedidos_entregues,
        count(*) FILTER (WHERE status = 'Canceled')  AS pedidos_cancelados
    FROM refined.pedidos
    GROUP BY metodo_pagamento
),
receita AS (
    SELECT
        p.metodo_pagamento,
        sum(i.preco_unitario * i.quantidade) AS receita_bruta
    FROM refined.itens_pedido i
    JOIN refined.pedidos p ON p.pedido_id = i.pedido_id
    WHERE p.status = 'Delivered'
    GROUP BY p.metodo_pagamento
)
SELECT
    c.metodo_pagamento,
    c.pedidos,
    c.pedidos_entregues,
    c.pedidos_cancelados,
    ROUND(CAST(c.pedidos_cancelados AS DOUBLE) / NULLIF(c.pedidos, 0), 4) AS taxa_cancelamento,
    CAST(r.receita_bruta AS DECIMAL(18,2)) AS receita_bruta
FROM contagem c
LEFT JOIN receita r ON r.metodo_pagamento = c.metodo_pagamento
ORDER BY c.metodo_pagamento
