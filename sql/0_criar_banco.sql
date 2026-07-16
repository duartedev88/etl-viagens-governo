-- =========================================================
-- ETAPA 1: CRIACAO DO BANCO
-- Execute somente o comando CREATE DATABASE conectado
-- a outro banco, como "postgres".
-- Execute esta etapa apenas se o banco ainda nao existir.
-- =========================================================
CREATE DATABASE etl_viagens_governo;


-- =========================================================
-- ETAPA 2: CRIACAO DAS TABELAS
-- Depois de criar o banco, conecte-se manualmente ao banco
-- antes de executar os comandos abaixo.
-- =========================================================


-- =========================================================
-- REMOCAO DAS TABELAS EXISTENTES
-- Ordem inversa das dependencias da camada Silver.
-- =========================================================
DROP TABLE IF EXISTS silver_trecho;
DROP TABLE IF EXISTS silver_passagem;
DROP TABLE IF EXISTS silver_pagamento;
DROP TABLE IF EXISTS silver_viagem;

DROP TABLE IF EXISTS raw_trecho;
DROP TABLE IF EXISTS raw_passagem;
DROP TABLE IF EXISTS raw_pagamento;
DROP TABLE IF EXISTS raw_viagem;


-- =========================================================
-- CAMADA RAW
-- Estrutura derivada dos cabecalhos reais dos CSVs encontrados
-- em viagens_2025_6meses.zip.
-- Todas as colunas sao VARCHAR, sem tamanho maximo.
-- Nenhuma tabela Raw possui constraints.
-- =========================================================

CREATE TABLE raw_viagem (
    "Identificador do processo de viagem" VARCHAR,
    "Número da Proposta (PCDP)" VARCHAR,
    "Situação" VARCHAR,
    "Viagem Urgente" VARCHAR,
    "Justificativa Urgência Viagem" VARCHAR,
    "Código do órgão superior" VARCHAR,
    "Nome do órgão superior" VARCHAR,
    "Código órgão solicitante" VARCHAR,
    "Nome órgão solicitante" VARCHAR,
    "CPF viajante" VARCHAR,
    "Nome" VARCHAR,
    "Cargo" VARCHAR,
    "Função" VARCHAR,
    "Descrição Função" VARCHAR,
    "Período - Data de início" VARCHAR,
    "Período - Data de fim" VARCHAR,
    "Destinos" VARCHAR,
    "Motivo" VARCHAR,
    "Valor diárias" VARCHAR,
    "Valor passagens" VARCHAR,
    "Valor devolução" VARCHAR,
    "Valor outros gastos" VARCHAR
);

CREATE TABLE raw_pagamento (
    "Identificador do processo de viagem" VARCHAR,
    "Número da Proposta (PCDP)" VARCHAR,
    "Código do órgão superior" VARCHAR,
    "Nome do órgão superior" VARCHAR,
    "Codigo do órgão pagador" VARCHAR,
    "Nome do órgao pagador" VARCHAR,
    "Código da unidade gestora pagadora" VARCHAR,
    "Nome da unidade gestora pagadora" VARCHAR,
    "Tipo de pagamento" VARCHAR,
    "Valor" VARCHAR
);

CREATE TABLE raw_passagem (
    "Identificador do processo de viagem" VARCHAR,
    "Número da Proposta (PCDP)" VARCHAR,
    "Meio de transporte" VARCHAR,
    "País - Origem ida" VARCHAR,
    "UF - Origem ida" VARCHAR,
    "Cidade - Origem ida" VARCHAR,
    "País - Destino ida" VARCHAR,
    "UF - Destino ida" VARCHAR,
    "Cidade - Destino ida" VARCHAR,
    "País - Origem volta" VARCHAR,
    "UF - Origem volta" VARCHAR,
    "Cidade - Origem volta" VARCHAR,
    "Pais - Destino volta" VARCHAR,
    "UF - Destino volta" VARCHAR,
    "Cidade - Destino volta" VARCHAR,
    "Valor da passagem" VARCHAR,
    "Taxa de serviço" VARCHAR,
    "Data da emissão/compra" VARCHAR,
    "Hora da emissão/compra" VARCHAR
);

CREATE TABLE raw_trecho (
    "Identificador do processo de viagem " VARCHAR,
    "Número da Proposta (PCDP)" VARCHAR,
    "Sequência Trecho" VARCHAR,
    "Origem - Data" VARCHAR,
    "Origem - País" VARCHAR,
    "Origem - UF" VARCHAR,
    "Origem - Cidade" VARCHAR,
    "Destino - Data" VARCHAR,
    "Destino - País" VARCHAR,
    "Destino - UF" VARCHAR,
    "Destino - Cidade" VARCHAR,
    "Meio de transporte" VARCHAR,
    "Número Diárias" VARCHAR,
    "Missao?" VARCHAR
);


-- =========================================================
-- CAMADA SILVER
-- Observacao: o PostgreSQL nao permite nomear restricoes NOT NULL.
-- Por isso, os NOT NULL exigidos foram declarados diretamente nas colunas.
-- =========================================================

CREATE TABLE silver_viagem (
    id_viagem VARCHAR(20) NOT NULL,
    num_proposta VARCHAR(20),
    situacao VARCHAR(50),
    viagem_urgente VARCHAR(5),
    cod_orgao_superior VARCHAR(20),
    nome_orgao_superior VARCHAR(255) NOT NULL,
    nome_viajante VARCHAR(255),
    cargo VARCHAR(255),
    data_inicio DATE,
    data_fim DATE,
    destinos VARCHAR(4000),
    motivo VARCHAR(4000),
    valor_diarias DECIMAL(10,2),
    valor_passagens DECIMAL(10,2),
    valor_devolucao DECIMAL(10,2),
    valor_outros_gastos DECIMAL(10,2),
    valor_total DECIMAL(12,2),
    duracao_dias INTEGER,
    CONSTRAINT pk_silver_viagem PRIMARY KEY (id_viagem),
    CONSTRAINT ck_silver_viagem_valor_diarias CHECK (valor_diarias >= 0)
);

CREATE TABLE silver_pagamento (
    id_pagamento INTEGER GENERATED ALWAYS AS IDENTITY,
    id_viagem VARCHAR(20) NOT NULL,
    num_proposta VARCHAR(20),
    nome_orgao_pagador VARCHAR(255),
    nome_ug_pagadora VARCHAR(255),
    tipo_pagamento VARCHAR(50) NOT NULL,
    valor DECIMAL(10,2),
    CONSTRAINT pk_silver_pagamento PRIMARY KEY (id_pagamento),
    CONSTRAINT fk_silver_pagamento_viagem
        FOREIGN KEY (id_viagem) REFERENCES silver_viagem (id_viagem),
    CONSTRAINT ck_silver_pagamento_valor CHECK (valor >= 0)
);

CREATE TABLE silver_passagem (
    id_passagem INTEGER GENERATED ALWAYS AS IDENTITY,
    id_viagem VARCHAR(20) NOT NULL,
    meio_transporte VARCHAR(50),
    pais_origem_ida VARCHAR(60),
    uf_origem_ida VARCHAR(40),
    cidade_origem_ida VARCHAR(80),
    pais_destino_ida VARCHAR(60),
    uf_destino_ida VARCHAR(40),
    cidade_destino_ida VARCHAR(80),
    valor_passagem DECIMAL(10,2),
    taxa_servico DECIMAL(10,2),
    data_emissao DATE,
    CONSTRAINT pk_silver_passagem PRIMARY KEY (id_passagem),
    CONSTRAINT fk_silver_passagem_viagem
        FOREIGN KEY (id_viagem) REFERENCES silver_viagem (id_viagem),
    CONSTRAINT ck_silver_passagem_valor_passagem CHECK (valor_passagem >= 0),
    CONSTRAINT ck_silver_passagem_taxa_servico CHECK (taxa_servico >= 0)
);

CREATE TABLE silver_trecho (
    id_trecho INTEGER GENERATED ALWAYS AS IDENTITY,
    id_viagem VARCHAR(20) NOT NULL,
    sequencia_trecho INTEGER,
    origem_data DATE,
    origem_uf VARCHAR(40),
    origem_cidade VARCHAR(80),
    destino_data DATE,
    destino_uf VARCHAR(40),
    destino_cidade VARCHAR(80),
    meio_transporte VARCHAR(50),
    numero_diarias DECIMAL(10,2),
    CONSTRAINT pk_silver_trecho PRIMARY KEY (id_trecho),
    CONSTRAINT fk_silver_trecho_viagem
        FOREIGN KEY (id_viagem) REFERENCES silver_viagem (id_viagem),
    CONSTRAINT ck_silver_trecho_numero_diarias CHECK (numero_diarias >= 0),
    CONSTRAINT uq_silver_trecho_viagem_sequencia UNIQUE (id_viagem, sequencia_trecho)
);
