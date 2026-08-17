-- CRIACAO DA CAMADA GOLD

-- REMOCAO DE OBJETOS ANTERIORES
BEGIN;

DROP VIEW IF EXISTS vw_resumo_pagamentos_mensais;
DROP TABLE IF EXISTS gold_resumo_pagamentos_mensais;

-- CRIACAO DA TABELA GOLD
CREATE TABLE gold_resumo_pagamentos_mensais (
    ano_referencia INTEGER,
    mes_referencia INTEGER,
    nome_orgao_pagador VARCHAR(255),
    tipo_pagamento VARCHAR(50),
    qtd_viagens INTEGER,
    qtd_pagamentos INTEGER,
    valor_total_pago DECIMAL(14,2),
    valor_medio_pagamento DECIMAL(12,2)
);

-- CARGA DA GOLD
INSERT INTO gold_resumo_pagamentos_mensais (
    ano_referencia,
    mes_referencia,
    nome_orgao_pagador,
    tipo_pagamento,
    qtd_viagens,
    qtd_pagamentos,
    valor_total_pago,
    valor_medio_pagamento
)
SELECT
    EXTRACT(YEAR FROM v.data_inicio)::INTEGER AS ano_referencia,
    EXTRACT(MONTH FROM v.data_inicio)::INTEGER AS mes_referencia,
    p.nome_orgao_pagador,
    p.tipo_pagamento,
    COUNT(DISTINCT v.id_viagem)::INTEGER AS qtd_viagens,
    COUNT(p.id_pagamento)::INTEGER AS qtd_pagamentos,
    SUM(p.valor)::DECIMAL(14,2) AS valor_total_pago,
    AVG(p.valor)::DECIMAL(12,2) AS valor_medio_pagamento
FROM silver_viagem v
INNER JOIN silver_pagamento p
    ON p.id_viagem = v.id_viagem
WHERE v.data_inicio IS NOT NULL
  AND p.nome_orgao_pagador IS NOT NULL
  AND p.tipo_pagamento IS NOT NULL
GROUP BY
    EXTRACT(YEAR FROM v.data_inicio)::INTEGER,
    EXTRACT(MONTH FROM v.data_inicio)::INTEGER,
    p.nome_orgao_pagador,
    p.tipo_pagamento;

-- CRIACAO DA VIEW
CREATE OR REPLACE VIEW vw_resumo_pagamentos_mensais AS
SELECT
    EXTRACT(YEAR FROM v.data_inicio)::INTEGER AS ano_referencia,
    EXTRACT(MONTH FROM v.data_inicio)::INTEGER AS mes_referencia,
    p.nome_orgao_pagador,
    p.tipo_pagamento,
    COUNT(DISTINCT v.id_viagem)::INTEGER AS qtd_viagens,
    COUNT(p.id_pagamento)::INTEGER AS qtd_pagamentos,
    SUM(p.valor)::DECIMAL(14,2) AS valor_total_pago,
    AVG(p.valor)::DECIMAL(12,2) AS valor_medio_pagamento
FROM silver_viagem v
INNER JOIN silver_pagamento p
    ON p.id_viagem = v.id_viagem
WHERE v.data_inicio IS NOT NULL
  AND p.nome_orgao_pagador IS NOT NULL
  AND p.tipo_pagamento IS NOT NULL
GROUP BY
    EXTRACT(YEAR FROM v.data_inicio)::INTEGER,
    EXTRACT(MONTH FROM v.data_inicio)::INTEGER,
    p.nome_orgao_pagador,
    p.tipo_pagamento;

COMMIT;

-- VALIDACOES
SELECT
    COUNT(*) AS qtd_registros_tabela_gold
FROM gold_resumo_pagamentos_mensais;

SELECT
    COUNT(*) AS qtd_registros_view_gold
FROM vw_resumo_pagamentos_mensais;

SELECT
    SUM(valor_total_pago) AS total_pago_gold
FROM gold_resumo_pagamentos_mensais;

SELECT
    SUM(p.valor) AS total_pago_silver
FROM silver_pagamento p
INNER JOIN silver_viagem v
    ON v.id_viagem = p.id_viagem
WHERE v.data_inicio IS NOT NULL
  AND p.nome_orgao_pagador IS NOT NULL
  AND p.tipo_pagamento IS NOT NULL;

(
    SELECT * FROM gold_resumo_pagamentos_mensais
    EXCEPT
    SELECT * FROM vw_resumo_pagamentos_mensais
)
UNION ALL
(
    SELECT * FROM vw_resumo_pagamentos_mensais
    EXCEPT
    SELECT * FROM gold_resumo_pagamentos_mensais
);

SELECT *
FROM gold_resumo_pagamentos_mensais
ORDER BY
    ano_referencia,
    mes_referencia,
    valor_total_pago DESC
LIMIT 20;
