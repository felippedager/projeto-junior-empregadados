-- Pergunta: quais os 10 produtos que mais vendem?
-- Grão: um produto, só os 10 de maior receita bruta (desempate: menor produto_id).
-- Receita = itens de pedidos Delivered. produto_id vai junto do nome: 300 produtos dividem
-- 15 nomes, então o nome não identifica ninguém.
WITH por_produto AS (
    SELECT
        pr.produto_id,
        pr.nome,
        c.nome AS categoria,
        sum(i.quantidade) AS quantidade,
        CAST(sum(i.preco_unitario * i.quantidade) AS DECIMAL(18,2)) AS receita_bruta
    FROM refined.itens_pedido i
    JOIN refined.pedidos    p  ON p.pedido_id    = i.pedido_id
    JOIN refined.produtos   pr ON pr.produto_id  = i.produto_id
    JOIN refined.categorias c  ON c.categoria_id = pr.categoria_id
    WHERE p.status = 'Delivered'
    GROUP BY pr.produto_id, pr.nome, c.nome
),
ranqueado AS (
    SELECT
        row_number() OVER (ORDER BY receita_bruta DESC, produto_id) AS posicao,
        *
    FROM por_produto
)
SELECT posicao, produto_id, nome, categoria, quantidade, receita_bruta
FROM ranqueado
WHERE posicao <= 10
ORDER BY posicao
