-- Pergunta: quanto do dado tem anomalia que muda a leitura dos números?
-- Grão: uma verificação (ordem fixa). refined guarda as anomalias sem corrigir; aqui elas ficam à vista.
-- devolucoes_de_pedido_nao_entregue vigia a premissa da receita: toda devolução é de pedido Delivered.
SELECT
    verificacao,
    descricao,
    ocorrencias,
    base,
    ROUND(CAST(ocorrencias AS DOUBLE) / NULLIF(base, 0), 4) AS proporcao
FROM (
    SELECT 1 AS ordem, 'pedidos_sem_item' AS verificacao,
        'pedidos sem nenhuma linha em itens_pedido (base: todos os pedidos)' AS descricao,
        (SELECT count(*) FROM refined.pedidos p
          WHERE NOT EXISTS (SELECT 1 FROM refined.itens_pedido i WHERE i.pedido_id = p.pedido_id)) AS ocorrencias,
        (SELECT count(*) FROM refined.pedidos) AS base
    UNION ALL
    SELECT 2, 'clientes_sem_pedido',
        'clientes sem nenhum pedido (base: todos os clientes)',
        (SELECT count(*) FROM refined.clientes c
          WHERE NOT EXISTS (SELECT 1 FROM refined.pedidos p WHERE p.cliente_id = c.cliente_id)),
        (SELECT count(*) FROM refined.clientes)
    UNION ALL
    SELECT 3, 'pares_pedido_produto_repetidos',
        'pares (pedido, produto) em mais de uma linha de itens (base: todos os itens)',
        (SELECT count(*) FROM (SELECT 1 FROM refined.itens_pedido GROUP BY pedido_id, produto_id HAVING count(*) > 1)),
        (SELECT count(*) FROM refined.itens_pedido)
    UNION ALL
    SELECT 4, 'pedidos_entregues_sem_item',
        'pedidos Delivered sem item (base: todos os pedidos Delivered)',
        (SELECT count(*) FROM refined.pedidos p
          WHERE p.status = 'Delivered'
            AND NOT EXISTS (SELECT 1 FROM refined.itens_pedido i WHERE i.pedido_id = p.pedido_id)),
        (SELECT count(*) FROM refined.pedidos WHERE status = 'Delivered')
    UNION ALL
    SELECT 5, 'produtos_com_nome_repetido',
        'produtos cujo nome é igual ao de outro produto (base: todos os produtos)',
        (SELECT count(*) FROM (SELECT count(*) OVER (PARTITION BY nome) AS n FROM refined.produtos) WHERE n > 1),
        (SELECT count(*) FROM refined.produtos)
    UNION ALL
    SELECT 6, 'devolucoes_de_pedido_nao_entregue',
        'devoluções de itens de pedido que não é Delivered (base: todas as devoluções)',
        (SELECT count(*) FROM refined.devolucoes d
          JOIN refined.itens_pedido i ON i.item_id = d.item_id
          JOIN refined.pedidos p ON p.pedido_id = i.pedido_id
          WHERE p.status <> 'Delivered'),
        (SELECT count(*) FROM refined.devolucoes)
)
ORDER BY ordem
