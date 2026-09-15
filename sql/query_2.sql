-- Tarefa 1.2 — Análise de Conversão de Clientes
-- Clientes com taxa de aprovação < 20%, considerando apenas clientes
-- com no mínimo 10 cotações no período de 01/01/2022 a 31/12/2022.
SELECT
    cl.nome                                                                   AS cliente,
    COUNT(c.codigo)                                                           AS total_cotacoes,
    SUM(CASE WHEN c.status = 'APROVADO' THEN 1 ELSE 0 END)                    AS cotacoes_aprovadas,
    ROUND(
        100.0 * SUM(CASE WHEN c.status = 'APROVADO' THEN 1 ELSE 0 END)
        / COUNT(c.codigo), 2
    )                                                                          AS taxa_aprovacao_pct
FROM cotacoes c
JOIN clientes cl ON cl.nome = c.cliente
WHERE c.criacao BETWEEN '2022-01-01' AND '2022-12-31'
GROUP BY cl.nome
HAVING COUNT(c.codigo) >= 10
   AND (100.0 * SUM(CASE WHEN c.status = 'APROVADO' THEN 1 ELSE 0 END) / COUNT(c.codigo)) < 20
ORDER BY taxa_aprovacao_pct ASC;
