-- Pergunta: quais as 10 cidades que mais compram?
-- Grão: uma cidade dentro de um estado, só as 10 de maior receita bruta (desempate: estado, cidade).
-- O grão é (estado, cidade) porque Udaipur existe em Rajasthan e em Tripura: são cidades diferentes.
-- Receita = itens de pedidos Delivered. pedidos = pedidos entregues com item.
WITH por_cidade AS (
    SELECT
        c.estado,
        c.cidade,
        count(DISTINCT i.pedido_id) AS pedidos,
        CAST(sum(i.preco_unitario * i.quantidade) AS DECIMAL(18,2)) AS receita_bruta
    FROM refined.itens_pedido i
    JOIN refined.pedidos  p ON p.pedido_id  = i.pedido_id
    JOIN refined.clientes c ON c.cliente_id = p.cliente_id
    WHERE p.status = 'Delivered'
    GROUP BY c.estado, c.cidade
),
ranqueado AS (
    SELECT
        row_number() OVER (ORDER BY receita_bruta DESC, estado, cidade) AS posicao,
        *
    FROM por_cidade
)
SELECT posicao, estado, cidade, pedidos, receita_bruta
FROM ranqueado
WHERE posicao <= 10
ORDER BY posicao
