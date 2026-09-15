-- Tarefa 1.1 — Rank de Vendedores
-- Ranking de vendedores ativos por quantidade de cotações aprovadas,
-- no período de 01/01/2022 a 31/07/2022, excluindo destino = BRASIL.
SELECT
    v.nome                                          AS vendedor,
    COUNT(c.codigo)                                 AS qtd_cotacoes_aprovadas,
    RANK() OVER (ORDER BY COUNT(c.codigo) DESC)     AS posicao_ranking
FROM cotacoes c
JOIN vendedores v ON v.nome = c.vendedor
WHERE c.status = 'APROVADO'
  AND c.criacao BETWEEN '2022-01-01' AND '2022-07-31'
  AND c.paisdestino <> 'BRASIL'
  AND v.nome NOT LIKE 'X -%'
GROUP BY v.nome
ORDER BY qtd_cotacoes_aprovadas DESC;
