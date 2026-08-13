"""Transformacao da camada Raw para Silver."""

import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import cursor as Cursor


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


RAIZ_PROJETO = Path(__file__).resolve().parent.parent

if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from src.banco import conectar


TABELAS_RAW = [
    "raw_viagem",
    "raw_pagamento",
    "raw_passagem",
    "raw_trecho",
]

TABELAS_SILVER = [
    "silver_viagem",
    "silver_pagamento",
    "silver_passagem",
    "silver_trecho",
]

TABELAS_OBRIGATORIAS = TABELAS_RAW + TABELAS_SILVER


def obter_contagem(cursor: Cursor) -> int:
    """Obtem o resultado de uma consulta COUNT."""

    resultado = cursor.fetchone()
    if resultado is None:
        raise RuntimeError("A consulta de contagem nao retornou resultado.")
    return int(resultado[0])


def verificar_tabelas(cursor: Cursor) -> None:
    """Verifica se todas as tabelas necessarias existem."""

    cursor.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name = ANY(%s);
        """,
        (TABELAS_OBRIGATORIAS,),
    )
    encontradas = {linha[0] for linha in cursor.fetchall()}
    ausentes = sorted(set(TABELAS_OBRIGATORIAS) - encontradas)

    if ausentes:
        raise RuntimeError(
            "As seguintes tabelas obrigatorias nao foram encontradas: "
            + ", ".join(ausentes)
        )


def verificar_bloqueios_silver(cursor: Cursor) -> None:
    """Informa sessoes que estao usando tabelas Silver."""

    cursor.execute(
        """
        SELECT DISTINCT
            a.pid,
            a.state,
            LEFT(REPLACE(REPLACE(COALESCE(a.query, ''), CHR(10), ' '), CHR(13), ' '), 120)
        FROM pg_stat_activity a
        INNER JOIN pg_locks l
            ON l.pid = a.pid
        INNER JOIN pg_class c
            ON c.oid = l.relation
        WHERE a.datname = current_database()
          AND a.pid <> pg_backend_pid()
          AND c.relname = ANY(%s)
          AND l.granted
        ORDER BY a.pid;
        """,
        (TABELAS_SILVER,),
    )
    bloqueios = cursor.fetchall()

    if not bloqueios:
        return

    print("Aviso: existem outras sessoes acessando a camada Silver:")
    for pid, state, consulta in bloqueios:
        estado = state or "sem estado"
        resumo = consulta or "<consulta indisponivel>"
        print(f"- PID {pid} | {estado} | {resumo}")


def contar_registros_raw(cursor: Cursor) -> dict[str, int]:
    """Conta os registros das tabelas Raw."""

    contagens: dict[str, int] = {}

    for tabela in TABELAS_RAW:
        cursor.execute(
            sql.SQL("SELECT COUNT(*) FROM {};").format(sql.Identifier(tabela))
        )
        contagens[tabela] = obter_contagem(cursor)

    return contagens


def contar_registros_silver(cursor: Cursor) -> dict[str, int]:
    """Conta os registros das tabelas Silver."""

    contagens: dict[str, int] = {}

    for tabela in TABELAS_SILVER:
        cursor.execute(
            sql.SQL("SELECT COUNT(*) FROM {};").format(sql.Identifier(tabela))
        )
        contagens[tabela] = obter_contagem(cursor)

    return contagens


def limpar_tabelas_silver(cursor: Cursor) -> None:
    """Limpa somente as tabelas Silver."""

    cursor.execute("SET LOCAL lock_timeout = '5s';")
    cursor.execute(
        """
        TRUNCATE TABLE
            silver_trecho,
            silver_passagem,
            silver_pagamento,
            silver_viagem
        RESTART IDENTITY;
        """
    )


def carregar_silver_viagem(cursor: Cursor) -> int:
    """Carrega a tabela silver_viagem."""

    cursor.execute(
        """
        WITH ids_unicos AS (
            SELECT
                BTRIM("Identificador do processo de viagem") AS id_viagem
            FROM raw_viagem
            WHERE NULLIF(BTRIM("Identificador do processo de viagem"), '') IS NOT NULL
            GROUP BY BTRIM("Identificador do processo de viagem")
            HAVING COUNT(*) = 1
        ),
        dados_convertidos AS (
            SELECT
                NULLIF(BTRIM(rv."Identificador do processo de viagem"), '') AS id_viagem,
                NULLIF(BTRIM(rv."Número da Proposta (PCDP)"), '') AS num_proposta,
                NULLIF(BTRIM(rv."Situação"), '') AS situacao,
                NULLIF(BTRIM(rv."Viagem Urgente"), '') AS viagem_urgente,
                NULLIF(BTRIM(rv."Código do órgão superior"), '') AS cod_orgao_superior,
                NULLIF(BTRIM(rv."Nome do órgão superior"), '') AS nome_orgao_superior,
                NULLIF(BTRIM(rv."Nome"), '') AS nome_viajante,
                NULLIF(BTRIM(rv."Cargo"), '') AS cargo,
                CASE
                    WHEN NULLIF(BTRIM(rv."Período - Data de início"), '') IS NULL THEN NULL
                    ELSE TO_DATE(BTRIM(rv."Período - Data de início"), 'DD/MM/YYYY')
                END AS data_inicio,
                CASE
                    WHEN NULLIF(BTRIM(rv."Período - Data de fim"), '') IS NULL THEN NULL
                    ELSE TO_DATE(BTRIM(rv."Período - Data de fim"), 'DD/MM/YYYY')
                END AS data_fim,
                NULLIF(BTRIM(rv."Destinos"), '') AS destinos,
                NULLIF(BTRIM(rv."Motivo"), '') AS motivo,
                CASE
                    WHEN NULLIF(BTRIM(rv."Valor diárias"), '') IS NULL THEN NULL
                    ELSE REPLACE(REPLACE(BTRIM(rv."Valor diárias"), '.', ''), ',', '.')::DECIMAL(10,2)
                END AS valor_diarias,
                CASE
                    WHEN NULLIF(BTRIM(rv."Valor passagens"), '') IS NULL THEN NULL
                    ELSE REPLACE(REPLACE(BTRIM(rv."Valor passagens"), '.', ''), ',', '.')::DECIMAL(10,2)
                END AS valor_passagens,
                CASE
                    WHEN NULLIF(BTRIM(rv."Valor devolução"), '') IS NULL THEN NULL
                    ELSE REPLACE(REPLACE(BTRIM(rv."Valor devolução"), '.', ''), ',', '.')::DECIMAL(10,2)
                END AS valor_devolucao,
                CASE
                    WHEN NULLIF(BTRIM(rv."Valor outros gastos"), '') IS NULL THEN NULL
                    ELSE REPLACE(REPLACE(BTRIM(rv."Valor outros gastos"), '.', ''), ',', '.')::DECIMAL(10,2)
                END AS valor_outros_gastos
            FROM raw_viagem rv
            INNER JOIN ids_unicos iu
                ON iu.id_viagem = BTRIM(rv."Identificador do processo de viagem")
        )
        INSERT INTO silver_viagem (
            id_viagem,
            num_proposta,
            situacao,
            viagem_urgente,
            cod_orgao_superior,
            nome_orgao_superior,
            nome_viajante,
            cargo,
            data_inicio,
            data_fim,
            destinos,
            motivo,
            valor_diarias,
            valor_passagens,
            valor_devolucao,
            valor_outros_gastos,
            valor_total,
            duracao_dias
        )
        SELECT
            id_viagem,
            num_proposta,
            situacao,
            viagem_urgente,
            cod_orgao_superior,
            nome_orgao_superior,
            nome_viajante,
            cargo,
            data_inicio,
            data_fim,
            destinos,
            motivo,
            valor_diarias,
            valor_passagens,
            valor_devolucao,
            valor_outros_gastos,
            (
                COALESCE(valor_diarias, 0)
                + COALESCE(valor_passagens, 0)
                + COALESCE(valor_outros_gastos, 0)
                - COALESCE(valor_devolucao, 0)
            )::DECIMAL(12,2) AS valor_total,
            CASE
                WHEN data_inicio IS NULL OR data_fim IS NULL THEN NULL
                ELSE data_fim - data_inicio
            END AS duracao_dias
        FROM dados_convertidos
        WHERE id_viagem IS NOT NULL
          AND nome_orgao_superior IS NOT NULL
          AND (valor_diarias IS NULL OR valor_diarias >= 0);
        """
    )
    return int(cursor.rowcount)


def carregar_silver_pagamento(cursor: Cursor) -> int:
    """Carrega a tabela silver_pagamento."""

    cursor.execute(
        """
        WITH dados_convertidos AS (
            SELECT
                NULLIF(BTRIM(rp."Identificador do processo de viagem"), '') AS id_viagem,
                NULLIF(BTRIM(rp."Número da Proposta (PCDP)"), '') AS num_proposta,
                NULLIF(BTRIM(rp."Nome do órgao pagador"), '') AS nome_orgao_pagador,
                NULLIF(BTRIM(rp."Nome da unidade gestora pagadora"), '') AS nome_ug_pagadora,
                NULLIF(BTRIM(rp."Tipo de pagamento"), '') AS tipo_pagamento,
                CASE
                    WHEN NULLIF(BTRIM(rp."Valor"), '') IS NULL THEN NULL
                    ELSE REPLACE(REPLACE(BTRIM(rp."Valor"), '.', ''), ',', '.')::DECIMAL(10,2)
                END AS valor
            FROM raw_pagamento rp
            INNER JOIN silver_viagem sv
                ON sv.id_viagem = BTRIM(rp."Identificador do processo de viagem")
        )
        INSERT INTO silver_pagamento (
            id_viagem,
            num_proposta,
            nome_orgao_pagador,
            nome_ug_pagadora,
            tipo_pagamento,
            valor
        )
        SELECT
            id_viagem,
            num_proposta,
            nome_orgao_pagador,
            nome_ug_pagadora,
            tipo_pagamento,
            valor
        FROM dados_convertidos
        WHERE id_viagem IS NOT NULL
          AND tipo_pagamento IS NOT NULL
          AND (valor IS NULL OR valor >= 0);
        """
    )
    return int(cursor.rowcount)


def carregar_silver_passagem(cursor: Cursor) -> int:
    """Carrega a tabela silver_passagem."""

    cursor.execute(
        """
        WITH dados_convertidos AS (
            SELECT
                NULLIF(BTRIM(rp."Identificador do processo de viagem"), '') AS id_viagem,
                NULLIF(BTRIM(rp."Meio de transporte"), '') AS meio_transporte,
                NULLIF(BTRIM(rp."País - Origem ida"), '') AS pais_origem_ida,
                NULLIF(BTRIM(rp."UF - Origem ida"), '') AS uf_origem_ida,
                NULLIF(BTRIM(rp."Cidade - Origem ida"), '') AS cidade_origem_ida,
                NULLIF(BTRIM(rp."País - Destino ida"), '') AS pais_destino_ida,
                NULLIF(BTRIM(rp."UF - Destino ida"), '') AS uf_destino_ida,
                NULLIF(BTRIM(rp."Cidade - Destino ida"), '') AS cidade_destino_ida,
                CASE
                    WHEN NULLIF(BTRIM(rp."Valor da passagem"), '') IS NULL THEN NULL
                    ELSE REPLACE(REPLACE(BTRIM(rp."Valor da passagem"), '.', ''), ',', '.')::DECIMAL(10,2)
                END AS valor_passagem,
                CASE
                    WHEN NULLIF(BTRIM(rp."Taxa de serviço"), '') IS NULL THEN NULL
                    ELSE REPLACE(REPLACE(BTRIM(rp."Taxa de serviço"), '.', ''), ',', '.')::DECIMAL(10,2)
                END AS taxa_servico,
                CASE
                    WHEN NULLIF(BTRIM(rp."Data da emissão/compra"), '') IS NULL THEN NULL
                    ELSE TO_DATE(BTRIM(rp."Data da emissão/compra"), 'DD/MM/YYYY')
                END AS data_emissao
            FROM raw_passagem rp
            INNER JOIN silver_viagem sv
                ON sv.id_viagem = BTRIM(rp."Identificador do processo de viagem")
        )
        INSERT INTO silver_passagem (
            id_viagem,
            meio_transporte,
            pais_origem_ida,
            uf_origem_ida,
            cidade_origem_ida,
            pais_destino_ida,
            uf_destino_ida,
            cidade_destino_ida,
            valor_passagem,
            taxa_servico,
            data_emissao
        )
        SELECT
            id_viagem,
            meio_transporte,
            pais_origem_ida,
            uf_origem_ida,
            cidade_origem_ida,
            pais_destino_ida,
            uf_destino_ida,
            cidade_destino_ida,
            valor_passagem,
            taxa_servico,
            data_emissao
        FROM dados_convertidos
        WHERE id_viagem IS NOT NULL
          AND (valor_passagem IS NULL OR valor_passagem >= 0)
          AND (taxa_servico IS NULL OR taxa_servico >= 0);
        """
    )
    return int(cursor.rowcount)


def carregar_silver_trecho(cursor: Cursor) -> int:
    """Carrega a tabela silver_trecho."""

    cursor.execute(
        """
        WITH dados_convertidos AS (
            SELECT
                NULLIF(BTRIM(rt."Identificador do processo de viagem "), '') AS id_viagem,
                CASE
                    WHEN NULLIF(BTRIM(rt."Sequência Trecho"), '') IS NULL THEN NULL
                    ELSE BTRIM(rt."Sequência Trecho")::INTEGER
                END AS sequencia_trecho,
                CASE
                    WHEN NULLIF(BTRIM(rt."Origem - Data"), '') IS NULL THEN NULL
                    ELSE TO_DATE(BTRIM(rt."Origem - Data"), 'DD/MM/YYYY')
                END AS origem_data,
                NULLIF(BTRIM(rt."Origem - UF"), '') AS origem_uf,
                NULLIF(BTRIM(rt."Origem - Cidade"), '') AS origem_cidade,
                CASE
                    WHEN NULLIF(BTRIM(rt."Destino - Data"), '') IS NULL THEN NULL
                    ELSE TO_DATE(BTRIM(rt."Destino - Data"), 'DD/MM/YYYY')
                END AS destino_data,
                NULLIF(BTRIM(rt."Destino - UF"), '') AS destino_uf,
                NULLIF(BTRIM(rt."Destino - Cidade"), '') AS destino_cidade,
                NULLIF(BTRIM(rt."Meio de transporte"), '') AS meio_transporte,
                CASE
                    WHEN NULLIF(BTRIM(rt."Número Diárias"), '') IS NULL THEN NULL
                    ELSE REPLACE(REPLACE(BTRIM(rt."Número Diárias"), '.', ''), ',', '.')::DECIMAL(10,2)
                END AS numero_diarias
            FROM raw_trecho rt
            INNER JOIN silver_viagem sv
                ON sv.id_viagem = BTRIM(rt."Identificador do processo de viagem ")
        )
        INSERT INTO silver_trecho (
            id_viagem,
            sequencia_trecho,
            origem_data,
            origem_uf,
            origem_cidade,
            destino_data,
            destino_uf,
            destino_cidade,
            meio_transporte,
            numero_diarias
        )
        SELECT
            id_viagem,
            sequencia_trecho,
            origem_data,
            origem_uf,
            origem_cidade,
            destino_data,
            destino_uf,
            destino_cidade,
            meio_transporte,
            numero_diarias
        FROM dados_convertidos
        WHERE id_viagem IS NOT NULL
          AND (numero_diarias IS NULL OR numero_diarias >= 0);
        """
    )
    return int(cursor.rowcount)


def validar_integridade_silver(cursor: Cursor) -> None:
    """Executa validacoes simples na camada Silver."""

    consultas = {
        "pagamentos orfaos": """
            SELECT COUNT(*)
            FROM silver_pagamento sp
            LEFT JOIN silver_viagem sv ON sv.id_viagem = sp.id_viagem
            WHERE sv.id_viagem IS NULL;
        """,
        "passagens orfas": """
            SELECT COUNT(*)
            FROM silver_passagem sp
            LEFT JOIN silver_viagem sv ON sv.id_viagem = sp.id_viagem
            WHERE sv.id_viagem IS NULL;
        """,
        "trechos orfaos": """
            SELECT COUNT(*)
            FROM silver_trecho st
            LEFT JOIN silver_viagem sv ON sv.id_viagem = st.id_viagem
            WHERE sv.id_viagem IS NULL;
        """,
        "viagens duplicadas": """
            SELECT COUNT(*)
            FROM (
                SELECT id_viagem
                FROM silver_viagem
                GROUP BY id_viagem
                HAVING COUNT(*) > 1
            ) duplicados;
        """,
        "trechos duplicados": """
            SELECT COUNT(*)
            FROM (
                SELECT id_viagem, sequencia_trecho
                FROM silver_trecho
                WHERE sequencia_trecho IS NOT NULL
                GROUP BY id_viagem, sequencia_trecho
                HAVING COUNT(*) > 1
            ) duplicados;
        """,
        "campos obrigatorios nulos": """
            SELECT
                (SELECT COUNT(*) FROM silver_viagem WHERE id_viagem IS NULL OR nome_orgao_superior IS NULL)
                + (SELECT COUNT(*) FROM silver_pagamento WHERE id_viagem IS NULL OR tipo_pagamento IS NULL)
                + (SELECT COUNT(*) FROM silver_passagem WHERE id_viagem IS NULL)
                + (SELECT COUNT(*) FROM silver_trecho WHERE id_viagem IS NULL);
        """,
        "valores negativos proibidos": """
            SELECT
                (SELECT COUNT(*) FROM silver_viagem WHERE valor_diarias < 0)
                + (SELECT COUNT(*) FROM silver_pagamento WHERE valor < 0)
                + (SELECT COUNT(*) FROM silver_passagem WHERE valor_passagem < 0 OR taxa_servico < 0)
                + (SELECT COUNT(*) FROM silver_trecho WHERE numero_diarias < 0);
        """,
    }

    for descricao, consulta in consultas.items():
        cursor.execute(consulta)
        quantidade = obter_contagem(cursor)
        if quantidade > 0:
            raise RuntimeError(
                f"Validacao final falhou: {descricao}: {quantidade}."
            )


def exibir_resumo(
    contagens_raw: dict[str, int],
    contagens_silver: dict[str, int],
) -> None:
    """Exibe um resumo simples da carga."""

    print()
    print("Resumo:")
    print(f"- raw_viagem: {contagens_raw['raw_viagem']}")
    print(f"- silver_viagem: {contagens_silver['silver_viagem']}")
    print(f"- raw_pagamento: {contagens_raw['raw_pagamento']}")
    print(f"- silver_pagamento: {contagens_silver['silver_pagamento']}")
    print(f"- raw_passagem: {contagens_raw['raw_passagem']}")
    print(f"- silver_passagem: {contagens_silver['silver_passagem']}")
    print(f"- raw_trecho: {contagens_raw['raw_trecho']}")
    print(f"- silver_trecho: {contagens_silver['silver_trecho']}")

    nao_carregados = {
        "viagens": contagens_raw["raw_viagem"] - contagens_silver["silver_viagem"],
        "pagamentos": contagens_raw["raw_pagamento"] - contagens_silver["silver_pagamento"],
        "passagens": contagens_raw["raw_passagem"] - contagens_silver["silver_passagem"],
        "trechos": contagens_raw["raw_trecho"] - contagens_silver["silver_trecho"],
    }

    if any(valor > 0 for valor in nao_carregados.values()):
        print()
        print("Registros não carregados na Silver:")
        print(f"- viagens: {nao_carregados['viagens']}")
        print(f"- pagamentos: {nao_carregados['pagamentos']}")
        print(f"- passagens: {nao_carregados['passagens']}")
        print(f"- trechos: {nao_carregados['trechos']}")


def exibir_erro_postgresql(erro: psycopg2.Error) -> None:
    """Exibe detalhes do erro retornado pelo PostgreSQL."""

    print("Erro PostgreSQL durante a transformação.")

    if erro.pgcode:
        print(f"Código PostgreSQL: {erro.pgcode}")
    if erro.diag.message_primary:
        print(f"Mensagem: {erro.diag.message_primary}")
    if erro.diag.message_detail:
        print(f"Detalhe: {erro.diag.message_detail}")
    if erro.diag.message_hint:
        print(f"Dica: {erro.diag.message_hint}")

    mensagem_primaria = (erro.diag.message_primary or "").lower()
    mensagem_completa = (erro.pgerror or str(erro) or "").lower()
    if (
        erro.pgcode == "55P03"
        or "lock timeout" in mensagem_primaria
        or "lock timeout" in mensagem_completa
    ):
        print("Não foi possível obter acesso exclusivo às tabelas Silver.")
        print(
            "Verifique sessões abertas no pgAdmin ou execuções anteriores do ETL."
        )


def executar_transformacao() -> int:
    """Executa a transformacao Raw -> Silver em uma unica transacao."""

    conexao = None

    try:
        print("Iniciando transformação Raw -> Silver...")
        conexao = conectar()

        with conexao.cursor() as cursor:
            verificar_tabelas(cursor)
            contagens_raw = contar_registros_raw(cursor)

            print("Registros encontrados na Raw:")
            for tabela in TABELAS_RAW:
                print(f"- {tabela}: {contagens_raw[tabela]}")

            verificar_bloqueios_silver(cursor)
            limpar_tabelas_silver(cursor)

            inseridos = {
                "silver_viagem": carregar_silver_viagem(cursor),
                "silver_pagamento": carregar_silver_pagamento(cursor),
                "silver_passagem": carregar_silver_passagem(cursor),
                "silver_trecho": carregar_silver_trecho(cursor),
            }

            contagens_silver = contar_registros_silver(cursor)
            validar_integridade_silver(cursor)

        conexao.commit()

        print()
        print("Registros carregados na Silver:")
        for tabela in TABELAS_SILVER:
            print(f"- {tabela}: {inseridos[tabela]}")

        exibir_resumo(contagens_raw, contagens_silver)
        return 0
    except psycopg2.Error as erro:
        if conexao is not None:
            conexao.rollback()
        exibir_erro_postgresql(erro)
        return 1
    except Exception as erro:
        if conexao is not None:
            conexao.rollback()
        print("Erro durante a transformação.")
        print(f"Detalhes: {erro}")
        return 1
    finally:
        if conexao is not None:
            conexao.close()


if __name__ == "__main__":
    raise SystemExit(executar_transformacao())
