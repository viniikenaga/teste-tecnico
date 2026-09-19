-- Tarefa 1.3 — View de Normalização
-- Convenção do dataset: vendedores com nome prefixado por "X -" são
-- ex-funcionários (não há coluna de status de vendedor); mesma convenção
-- usada para excluí-los em query_1.sql.
DROP VIEW IF EXISTS vw_cotacoes_normalizadas;

CREATE VIEW vw_cotacoes_normalizadas AS
SELECT
    codigo,
    cliente,
    criacao,
    paisorigem,
    paisdestino,
    lane,
    modal,
    status,
    CASE
        WHEN vendedor LIKE 'X -%' THEN 'Ex-Funcionário'
        ELSE SUBSTR(vendedor, 1, INSTR(vendedor || ' ', ' ') - 1)
    END AS vendedor_normalizado,
    CAST(strftime('%m', criacao) AS INTEGER) AS mes
FROM cotacoes
WHERE status <> 'CANCELADO';
