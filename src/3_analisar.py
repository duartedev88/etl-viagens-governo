"""Analise academica da Pergunta 1 usando a camada Silver."""

import sys
import unicodedata
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import psycopg2
from matplotlib.ticker import FuncFormatter


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


RAIZ_PROJETO = Path(__file__).resolve().parent.parent

if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from src.banco import conectar


CAMINHO_GRAFICO = RAIZ_PROJETO / "output" / "pergunta_1_viagens_urgentes.png"
CAMINHO_GRAFICO_PERGUNTA_2 = (
    RAIZ_PROJETO / "output" / "pergunta_2_duracao_viagem.png"
)
CAMINHO_GRAFICO_PERGUNTA_3 = (
    RAIZ_PROJETO / "output" / "pergunta_3_evolucao_pagamentos.png"
)
CAMINHO_GRAFICO_PERGUNTA_4 = (
    RAIZ_PROJETO / "output" / "pergunta_4_perfil_orgaos_pagadores.png"
)

SQL_PERGUNTA_1 = """
SELECT
    viagem_urgente,
    COUNT(*)::INTEGER AS qtd_viagens,
    AVG(duracao_dias)::DECIMAL(12,2) AS duracao_media_dias,
    AVG(valor_total)::DECIMAL(14,2) AS valor_total_medio,
    AVG(valor_total / NULLIF(duracao_dias, 0))::DECIMAL(14,2) AS custo_medio_diario
FROM silver_viagem
WHERE duracao_dias IS NOT NULL
  AND duracao_dias > 0
  AND valor_total IS NOT NULL
  AND viagem_urgente IS NOT NULL
GROUP BY viagem_urgente
ORDER BY viagem_urgente;
""".strip()

SQL_PERGUNTA_2 = """
SELECT
    faixa_duracao,
    COUNT(*)::INTEGER AS qtd_viagens,
    AVG(valor_total / NULLIF(duracao_dias, 0))::DECIMAL(14,2) AS custo_medio_diario,
    AVG(valor_total)::DECIMAL(14,2) AS valor_total_medio
FROM (
    SELECT
        CASE
            WHEN duracao_dias = 1 THEN '1 dia'
            WHEN duracao_dias BETWEEN 2 AND 3 THEN '2 a 3 dias'
            WHEN duracao_dias BETWEEN 4 AND 7 THEN '4 a 7 dias'
            WHEN duracao_dias BETWEEN 8 AND 15 THEN '8 a 15 dias'
            WHEN duracao_dias > 15 THEN 'Acima de 15 dias'
        END AS faixa_duracao,
        duracao_dias,
        valor_total
    FROM silver_viagem
    WHERE duracao_dias IS NOT NULL
      AND duracao_dias > 0
      AND valor_total IS NOT NULL
) AS viagens_classificadas
WHERE faixa_duracao IS NOT NULL
GROUP BY faixa_duracao
ORDER BY
    CASE faixa_duracao
        WHEN '1 dia' THEN 1
        WHEN '2 a 3 dias' THEN 2
        WHEN '4 a 7 dias' THEN 3
        WHEN '8 a 15 dias' THEN 4
        WHEN 'Acima de 15 dias' THEN 5
    END;
""".strip()

SQL_PERGUNTA_3 = """
WITH pagamentos_mensais AS (
    SELECT
        ano_referencia,
        mes_referencia,
        tipo_pagamento,
        SUM(valor_total_pago) AS valor_total_pago
    FROM gold_resumo_pagamentos_mensais
    WHERE ano_referencia IS NOT NULL
      AND mes_referencia IS NOT NULL
      AND tipo_pagamento IS NOT NULL
    GROUP BY
        ano_referencia,
        mes_referencia,
        tipo_pagamento
)
SELECT
    ano_referencia,
    mes_referencia,
    tipo_pagamento,
    valor_total_pago::DECIMAL(14,2) AS valor_total_pago,
    (
        (
            valor_total_pago
            / NULLIF(
                SUM(valor_total_pago) OVER (
                    PARTITION BY ano_referencia, mes_referencia
                ),
                0
            )
        ) * 100
    )::DECIMAL(7,2) AS participacao_percentual
FROM pagamentos_mensais
ORDER BY
    ano_referencia,
    mes_referencia,
    tipo_pagamento;
""".strip()

SQL_PERGUNTA_4 = """
SELECT
    nome_orgao_pagador,
    SUM(valor_total_pago)::DECIMAL(16,2) AS valor_total_pago,
    SUM(qtd_pagamentos)::INTEGER AS qtd_pagamentos,
    (
        SUM(valor_total_pago)
        / NULLIF(SUM(qtd_pagamentos), 0)
    )::DECIMAL(14,2) AS valor_medio_pagamento,
    SUM(qtd_viagens)::INTEGER AS qtd_viagens_atendidas
FROM gold_resumo_pagamentos_mensais
WHERE nome_orgao_pagador IS NOT NULL
GROUP BY nome_orgao_pagador
ORDER BY valor_total_pago DESC
LIMIT 10;
""".strip()


def formatar_reais(valor: float | int | None) -> str:
    """Formata um numero no padrao monetario brasileiro."""

    if valor is None or pd.isna(valor):
        return "R$ 0,00"

    texto = f"{float(valor):,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def formatar_inteiro_brasileiro(valor: int | float | None) -> str:
    """Formata inteiros com separador de milhar brasileiro."""

    if valor is None or pd.isna(valor):
        return "0"

    return f"{int(valor):,}".replace(",", ".")


def normalizar_texto(texto: str) -> str:
    """Normaliza texto para comparacoes deterministicas."""

    texto_sem_acentos = unicodedata.normalize("NFKD", texto)
    texto_sem_acentos = "".join(
        caractere
        for caractere in texto_sem_acentos
        if not unicodedata.combining(caractere)
    )
    return texto_sem_acentos.strip().upper()


def rotulo_urgencia(valor: str) -> str:
    """Gera um rotulo amigavel sem alterar o valor original do banco."""

    valor_normalizado = normalizar_texto(valor)

    if valor_normalizado in {"SIM", "S"}:
        return f"Urgente ({valor})"
    if valor_normalizado in {"NAO", "N", "NAO URGENTE"}:
        return f"Nao urgente ({valor})"
    return valor


def consultar_pergunta_1() -> pd.DataFrame:
    """Consulta os agregados da Pergunta 1 na silver_viagem."""

    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            cursor.execute(SQL_PERGUNTA_1)
            registros = cursor.fetchall()
            colunas = [descricao[0] for descricao in cursor.description]
        return pd.DataFrame(registros, columns=colunas)
    finally:
        conexao.close()


def consultar_pergunta_2() -> pd.DataFrame:
    """Consulta os agregados da Pergunta 2 na silver_viagem."""

    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            cursor.execute(SQL_PERGUNTA_2)
            registros = cursor.fetchall()
            colunas = [descricao[0] for descricao in cursor.description]
        return pd.DataFrame(registros, columns=colunas)
    finally:
        conexao.close()


def consultar_pergunta_3() -> pd.DataFrame:
    """Consulta os agregados mensais da Pergunta 3 na gold."""

    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            cursor.execute(SQL_PERGUNTA_3)
            registros = cursor.fetchall()
            colunas = [descricao[0] for descricao in cursor.description]
        return pd.DataFrame(registros, columns=colunas)
    finally:
        conexao.close()


def consultar_pergunta_4() -> pd.DataFrame:
    """Consulta os agregados da Pergunta 4 na gold."""

    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            cursor.execute(SQL_PERGUNTA_4)
            registros = cursor.fetchall()
            colunas = [descricao[0] for descricao in cursor.description]
        return pd.DataFrame(registros, columns=colunas)
    finally:
        conexao.close()


def validar_resultado_pergunta_1(df: pd.DataFrame) -> None:
    """Valida a estrutura minima necessaria para a analise."""

    if df.empty:
        raise RuntimeError(
            "A consulta da Pergunta 1 nao retornou registros para analise."
        )

    colunas_esperadas = {
        "viagem_urgente",
        "qtd_viagens",
        "duracao_media_dias",
        "valor_total_medio",
        "custo_medio_diario",
    }
    colunas_ausentes = colunas_esperadas - set(df.columns)
    if colunas_ausentes:
        raise RuntimeError(
            "A consulta da Pergunta 1 nao retornou todas as colunas esperadas: "
            + ", ".join(sorted(colunas_ausentes))
        )

    if df["viagem_urgente"].dropna().empty:
        raise RuntimeError(
            "A consulta da Pergunta 1 nao retornou categorias validas de urgencia."
        )

    if df["custo_medio_diario"].dropna().empty:
        raise RuntimeError(
            "A consulta da Pergunta 1 nao retornou custo medio diario valido."
        )


def validar_resultado_pergunta_2(df: pd.DataFrame) -> None:
    """Valida a estrutura minima necessaria para a Pergunta 2."""

    if df.empty:
        raise RuntimeError(
            "A consulta da Pergunta 2 nao retornou registros para analise."
        )

    colunas_esperadas = {
        "faixa_duracao",
        "qtd_viagens",
        "custo_medio_diario",
        "valor_total_medio",
    }
    colunas_ausentes = colunas_esperadas - set(df.columns)
    if colunas_ausentes:
        raise RuntimeError(
            "A consulta da Pergunta 2 nao retornou todas as colunas esperadas: "
            + ", ".join(sorted(colunas_ausentes))
        )

    if len(df) > 5:
        raise RuntimeError(
            "A consulta da Pergunta 2 retornou mais de cinco faixas de duracao."
        )

    if df["custo_medio_diario"].dropna().empty:
        raise RuntimeError(
            "A consulta da Pergunta 2 nao retornou custo medio diario valido."
        )

    if df["qtd_viagens"].dropna().empty:
        raise RuntimeError(
            "A consulta da Pergunta 2 nao retornou quantidade de viagens valida."
        )


def validar_resultado_pergunta_3(df: pd.DataFrame) -> None:
    """Valida a estrutura minima necessaria para a Pergunta 3."""

    if df.empty:
        raise RuntimeError(
            "A consulta da Pergunta 3 nao retornou registros para analise."
        )

    colunas_esperadas = {
        "ano_referencia",
        "mes_referencia",
        "tipo_pagamento",
        "valor_total_pago",
        "participacao_percentual",
    }
    colunas_ausentes = colunas_esperadas - set(df.columns)
    if colunas_ausentes:
        raise RuntimeError(
            "A consulta da Pergunta 3 nao retornou todas as colunas esperadas: "
            + ", ".join(sorted(colunas_ausentes))
        )

    if df["valor_total_pago"].dropna().empty:
        raise RuntimeError(
            "A consulta da Pergunta 3 nao retornou valor total pago valido."
        )

    if not pd.to_numeric(df["valor_total_pago"], errors="coerce").notna().any():
        raise RuntimeError(
            "A coluna valor_total_pago da Pergunta 3 nao possui valores numericos validos."
        )

    if df["participacao_percentual"].dropna().empty:
        raise RuntimeError(
            "A consulta da Pergunta 3 nao retornou participacao percentual valida."
        )

    if not pd.to_numeric(
        df["participacao_percentual"], errors="coerce"
    ).notna().any():
        raise RuntimeError(
            "A coluna participacao_percentual da Pergunta 3 nao possui valores numericos validos."
        )

    anos = pd.to_numeric(df["ano_referencia"], errors="coerce")
    if anos.isna().any():
        raise RuntimeError(
            "A consulta da Pergunta 3 retornou ano_referencia invalido."
        )

    meses = pd.to_numeric(df["mes_referencia"], errors="coerce")
    if meses.isna().any() or not meses.between(1, 12).all():
        raise RuntimeError(
            "A consulta da Pergunta 3 retornou mes_referencia fora do intervalo de 1 a 12."
        )

    tipos_validos = df["tipo_pagamento"].astype(str).str.strip()
    if tipos_validos.replace("nan", "").eq("").all():
        raise RuntimeError(
            "A consulta da Pergunta 3 nao retornou tipos de pagamento validos."
        )


def validar_resultado_pergunta_4(df: pd.DataFrame) -> None:
    """Valida a estrutura minima necessaria para a Pergunta 4."""

    if df.empty:
        raise RuntimeError(
            "A consulta da Pergunta 4 nao retornou registros para analise."
        )

    if len(df) > 10:
        raise RuntimeError("A consulta da Pergunta 4 retornou mais de 10 orgaos.")

    colunas_esperadas = {
        "nome_orgao_pagador",
        "valor_total_pago",
        "qtd_pagamentos",
        "valor_medio_pagamento",
        "qtd_viagens_atendidas",
    }
    colunas_ausentes = colunas_esperadas - set(df.columns)
    if colunas_ausentes:
        raise RuntimeError(
            "A consulta da Pergunta 4 nao retornou todas as colunas esperadas: "
            + ", ".join(sorted(colunas_ausentes))
        )

    nomes_validos = df["nome_orgao_pagador"].astype(str).str.strip()
    if nomes_validos.replace("nan", "").eq("").any():
        raise RuntimeError(
            "A consulta da Pergunta 4 retornou nome_orgao_pagador invalido."
        )

    if df["valor_total_pago"].isna().any():
        raise RuntimeError(
            "A consulta da Pergunta 4 retornou valor_total_pago nulo."
        )

    if pd.to_numeric(df["qtd_pagamentos"], errors="coerce").le(0).any():
        raise RuntimeError(
            "A consulta da Pergunta 4 retornou qtd_pagamentos menor ou igual a zero."
        )

    if pd.to_numeric(df["valor_medio_pagamento"], errors="coerce").isna().any():
        raise RuntimeError(
            "A consulta da Pergunta 4 retornou valor_medio_pagamento invalido."
        )

    if pd.to_numeric(df["qtd_viagens_atendidas"], errors="coerce").isna().any():
        raise RuntimeError(
            "A consulta da Pergunta 4 retornou qtd_viagens_atendidas invalida."
        )


def exibir_resultado_pergunta_1(df: pd.DataFrame) -> str:
    """Monta a tabela formatada para exibicao no terminal."""

    df_exibicao = df.copy()
    df_exibicao["duracao_media_dias"] = df_exibicao["duracao_media_dias"].map(
        lambda valor: f"{float(valor):.2f}" if pd.notna(valor) else ""
    )
    df_exibicao["valor_total_medio"] = df_exibicao["valor_total_medio"].map(
        formatar_reais
    )
    df_exibicao["custo_medio_diario"] = df_exibicao["custo_medio_diario"].map(
        formatar_reais
    )
    return df_exibicao.to_string(index=False)


def exibir_resultado_pergunta_2(df: pd.DataFrame) -> str:
    """Monta a tabela formatada da Pergunta 2 para o terminal."""

    df_exibicao = df.copy()
    df_exibicao["custo_medio_diario"] = df_exibicao["custo_medio_diario"].map(
        formatar_reais
    )
    df_exibicao["valor_total_medio"] = df_exibicao["valor_total_medio"].map(
        formatar_reais
    )
    return df_exibicao.to_string(index=False)


def exibir_resultado_pergunta_3(df: pd.DataFrame) -> str:
    """Monta a tabela formatada da Pergunta 3 para o terminal."""

    df_exibicao = df.copy()
    df_exibicao["valor_total_pago"] = df_exibicao["valor_total_pago"].map(
        formatar_reais
    )
    df_exibicao["participacao_percentual"] = df_exibicao[
        "participacao_percentual"
    ].map(lambda valor: f"{float(valor):.2f}%" if pd.notna(valor) else "")
    return df_exibicao.to_string(index=False)


def exibir_resultado_pergunta_4(df: pd.DataFrame) -> str:
    """Monta a tabela formatada da Pergunta 4 para o terminal."""

    df_exibicao = df.copy()
    df_exibicao["valor_total_pago"] = df_exibicao["valor_total_pago"].map(
        formatar_reais
    )
    df_exibicao["valor_medio_pagamento"] = df_exibicao["valor_medio_pagamento"].map(
        formatar_reais
    )
    df_exibicao["qtd_pagamentos"] = df_exibicao["qtd_pagamentos"].map(
        lambda valor: f"{int(valor):,}".replace(",", ".") if pd.notna(valor) else ""
    )
    df_exibicao["qtd_viagens_atendidas"] = df_exibicao["qtd_viagens_atendidas"].map(
        lambda valor: f"{int(valor):,}".replace(",", ".") if pd.notna(valor) else ""
    )
    return df_exibicao.to_string(index=False)


def gerar_grafico_pergunta_1(df: pd.DataFrame) -> Path:
    """Gera o grafico de barras verticais da Pergunta 1."""

    df_grafico = df.copy()
    df_grafico["rotulo"] = df_grafico["viagem_urgente"].map(rotulo_urgencia)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    barras = ax.bar(df_grafico["rotulo"], df_grafico["custo_medio_diario"])

    ax.set_title("Custo medio diario por urgencia da viagem")
    ax.set_xlabel("Urgencia da viagem")
    ax.set_ylabel("Custo medio diario (R$)")
    ax.margins(y=0.25)

    for barra, custo, quantidade in zip(
        barras,
        df_grafico["custo_medio_diario"],
        df_grafico["qtd_viagens"],
    ):
        ax.text(
            barra.get_x() + barra.get_width() / 2,
            barra.get_height(),
            f"{formatar_reais(custo)}\nn = {formatar_inteiro_brasileiro(quantidade)}",
            ha="center",
            va="bottom",
        )

    CAMINHO_GRAFICO.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(CAMINHO_GRAFICO, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return CAMINHO_GRAFICO


def gerar_grafico_pergunta_2(df: pd.DataFrame) -> Path:
    """Gera o grafico de barras verticais da Pergunta 2."""

    fig, ax = plt.subplots(figsize=(10, 5.5))
    barras = ax.bar(df["faixa_duracao"], df["custo_medio_diario"])

    ax.set_title("Custo medio diario por duracao da viagem")
    ax.set_xlabel("Faixa de duracao")
    ax.set_ylabel("Custo medio diario (R$)")
    ax.margins(y=0.25)

    for barra, custo, quantidade in zip(
        barras,
        df["custo_medio_diario"],
        df["qtd_viagens"],
    ):
        ax.text(
            barra.get_x() + barra.get_width() / 2,
            barra.get_height(),
            f"{formatar_reais(custo)}\nn = {formatar_inteiro_brasileiro(quantidade)}",
            ha="center",
            va="bottom",
        )

    CAMINHO_GRAFICO_PERGUNTA_2.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(CAMINHO_GRAFICO_PERGUNTA_2, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return CAMINHO_GRAFICO_PERGUNTA_2


def preparar_dataframe_pergunta_3(df: pd.DataFrame) -> pd.DataFrame:
    """Cria referencia temporal cronologica para analises e grafico."""

    df_preparado = df.copy()
    df_preparado["ano_referencia"] = pd.to_numeric(
        df_preparado["ano_referencia"], errors="coerce"
    ).astype(int)
    df_preparado["mes_referencia"] = pd.to_numeric(
        df_preparado["mes_referencia"], errors="coerce"
    ).astype(int)
    df_preparado["valor_total_pago"] = pd.to_numeric(
        df_preparado["valor_total_pago"], errors="coerce"
    )
    df_preparado["participacao_percentual"] = pd.to_numeric(
        df_preparado["participacao_percentual"], errors="coerce"
    )
    df_preparado["referencia_temporal"] = pd.to_datetime(
        {
            "year": df_preparado["ano_referencia"],
            "month": df_preparado["mes_referencia"],
            "day": 1,
        }
    )
    return df_preparado.sort_values(
        ["referencia_temporal", "tipo_pagamento"]
    ).reset_index(drop=True)


def gerar_grafico_pergunta_3(df: pd.DataFrame) -> Path:
    """Gera o grafico de linhas da Pergunta 3."""

    df_grafico = preparar_dataframe_pergunta_3(df)
    fig, ax = plt.subplots(figsize=(11, 6))

    for tipo_pagamento, grupo in df_grafico.groupby("tipo_pagamento", sort=False):
        grupo_ordenado = grupo.sort_values("referencia_temporal")
        ax.plot(
            grupo_ordenado["referencia_temporal"],
            grupo_ordenado["valor_total_pago"],
            marker="o",
            label=tipo_pagamento,
        )

    referencias = (
        df_grafico["referencia_temporal"].drop_duplicates().sort_values().tolist()
    )
    ax.set_xticks(referencias)
    ax.set_xticklabels([referencia.strftime("%m/%Y") for referencia in referencias])
    ax.set_title("Evolucao mensal do valor pago por tipo de pagamento")
    ax.set_xlabel("Mes/ano")
    ax.set_ylabel("Valor total pago (R$)")
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    ax.yaxis.set_major_formatter(FuncFormatter(formatar_reais_milhoes))
    ax.legend(title="Tipo de pagamento")
    ax.tick_params(axis="x", rotation=45)

    CAMINHO_GRAFICO_PERGUNTA_3.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(CAMINHO_GRAFICO_PERGUNTA_3, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return CAMINHO_GRAFICO_PERGUNTA_3


def preparar_dataframe_pergunta_4(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza os tipos numericos da Pergunta 4 para calculos e grafico."""

    df_preparado = df.copy()
    df_preparado["valor_total_pago"] = pd.to_numeric(
        df_preparado["valor_total_pago"], errors="coerce"
    )
    df_preparado["qtd_pagamentos"] = pd.to_numeric(
        df_preparado["qtd_pagamentos"], errors="coerce"
    ).astype(int)
    df_preparado["valor_medio_pagamento"] = pd.to_numeric(
        df_preparado["valor_medio_pagamento"], errors="coerce"
    )
    df_preparado["qtd_viagens_atendidas"] = pd.to_numeric(
        df_preparado["qtd_viagens_atendidas"], errors="coerce"
    ).astype(int)
    return df_preparado.sort_values("valor_total_pago", ascending=False).reset_index(
        drop=True
    )


def abreviar_nome_orgao(nome: str) -> str:
    """Abrevia nomes longos apenas para rotulos do grafico."""

    if len(nome) > 35:
        return nome[:32] + "..."
    return nome


def calcular_tamanhos_bolhas(valores: pd.Series) -> pd.Series:
    """Normaliza tamanhos de bolha para uma faixa visual razoavel."""

    tamanho_minimo = 150.0
    tamanho_maximo = 1800.0

    valor_minimo = float(valores.min())
    valor_maximo = float(valores.max())

    if valor_minimo == valor_maximo:
        tamanho_intermediario = (tamanho_minimo + tamanho_maximo) / 2
        return pd.Series([tamanho_intermediario] * len(valores), index=valores.index)

    return tamanho_minimo + (
        (valores - valor_minimo) / (valor_maximo - valor_minimo)
    ) * (tamanho_maximo - tamanho_minimo)


def formatar_reais_sem_centavos(valor: float, _pos: int | None = None) -> str:
    """Formata valores em reais para os eixos do matplotlib."""

    texto = f"{valor:,.0f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def formatar_reais_milhoes(valor: float, _pos: int | None = None) -> str:
    """Formata valores monetarios dinamicamente em milhoes no eixo."""

    if abs(valor) < 1_000_000:
        return formatar_reais_sem_centavos(valor)

    valor_em_milhoes = valor / 1_000_000
    if float(valor_em_milhoes).is_integer():
        return f"R$ {int(valor_em_milhoes)} mi"
    return f"R$ {valor_em_milhoes:.1f} mi".replace(".", ",")


def classificar_perfil_orgaos(df: pd.DataFrame) -> tuple[pd.DataFrame, float, float]:
    """Classifica os perfis relativos ao Top 10 pelas medianas do grupo."""

    df_classificado = preparar_dataframe_pergunta_4(df)
    mediana_qtd_pagamentos = float(df_classificado["qtd_pagamentos"].median())
    mediana_valor_medio_pagamento = float(
        df_classificado["valor_medio_pagamento"].median()
    )

    def classificar_linha(linha: pd.Series) -> str:
        volume = (
            "alto volume"
            if float(linha["qtd_pagamentos"]) >= mediana_qtd_pagamentos
            else "baixo volume"
        )
        ticket = (
            "ticket alto"
            if float(linha["valor_medio_pagamento"]) >= mediana_valor_medio_pagamento
            else "ticket baixo"
        )
        return f"{volume} / {ticket}"

    df_classificado["perfil"] = df_classificado.apply(classificar_linha, axis=1)
    return df_classificado, mediana_qtd_pagamentos, mediana_valor_medio_pagamento


def gerar_grafico_pergunta_4(df: pd.DataFrame) -> Path:
    """Gera o grafico de dispersao em bolhas da Pergunta 4."""

    df_grafico = preparar_dataframe_pergunta_4(df)
    tamanhos = calcular_tamanhos_bolhas(df_grafico["valor_total_pago"])

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.scatter(
        df_grafico["qtd_pagamentos"],
        df_grafico["valor_medio_pagamento"],
        s=tamanhos,
        alpha=0.7,
    )

    deslocamentos = [
        (10, 10),
        (10, -16),
        (-120, 10),
        (10, 22),
        (-115, -18),
        (10, -26),
        (-135, 20),
        (10, 30),
        (-125, -30),
        (12, 0),
    ]

    for indice, (_, linha) in enumerate(df_grafico.iterrows()):
        deslocamento_x, deslocamento_y = deslocamentos[indice % len(deslocamentos)]
        ax.annotate(
            abreviar_nome_orgao(str(linha["nome_orgao_pagador"])),
            (linha["qtd_pagamentos"], linha["valor_medio_pagamento"]),
            xytext=(deslocamento_x, deslocamento_y),
            textcoords="offset points",
            fontsize=9,
        )

    ax.set_title("Perfil de gasto dos 10 maiores orgaos pagadores")
    ax.set_xlabel("Quantidade de pagamentos")
    ax.set_ylabel("Valor medio por pagamento (R$)")
    ax.yaxis.set_major_formatter(FuncFormatter(formatar_reais_sem_centavos))
    ax.text(
        0.99,
        0.02,
        "Tamanho da bolha = valor total pago",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "alpha": 0.85},
    )

    CAMINHO_GRAFICO_PERGUNTA_4.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(CAMINHO_GRAFICO_PERGUNTA_4, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return CAMINHO_GRAFICO_PERGUNTA_4


def identificar_grupos(df: pd.DataFrame) -> tuple[pd.Series | None, pd.Series | None]:
    """Identifica os grupos urgente e nao urgente a partir dos valores reais."""

    urgente = None
    nao_urgente = None

    for _, linha in df.iterrows():
        valor = str(linha["viagem_urgente"])
        valor_normalizado = normalizar_texto(valor)

        if valor_normalizado in {"SIM", "S"} and urgente is None:
            urgente = linha
        elif valor_normalizado in {"NAO", "N", "NAO URGENTE"} and nao_urgente is None:
            nao_urgente = linha

    return urgente, nao_urgente


def analisar_pergunta_1(df: pd.DataFrame) -> str:
    """Produz uma analise textual deterministica a partir do resultado."""

    urgente, nao_urgente = identificar_grupos(df)

    if urgente is None or nao_urgente is None:
        categorias = ", ".join(str(valor) for valor in df["viagem_urgente"].tolist())
        return (
            "Nao foi possivel concluir a comparacao entre viagens urgentes e nao "
            "urgentes porque a base nao apresentou os dois grupos esperados. "
            f"Categorias retornadas: {categorias}."
        )

    custo_urgente = float(urgente["custo_medio_diario"])
    custo_nao_urgente = float(nao_urgente["custo_medio_diario"])
    duracao_urgente = float(urgente["duracao_media_dias"])
    duracao_nao_urgente = float(nao_urgente["duracao_media_dias"])
    valor_total_urgente = float(urgente["valor_total_medio"])
    valor_total_nao_urgente = float(nao_urgente["valor_total_medio"])
    qtd_urgente = int(urgente["qtd_viagens"])
    qtd_nao_urgente = int(nao_urgente["qtd_viagens"])

    total_viagens = qtd_urgente + qtd_nao_urgente
    participacao_urgente = (
        (qtd_urgente / total_viagens) * 100 if total_viagens > 0 else 0.0
    )

    grupo_mais_caro = (
        f"urgente ({urgente['viagem_urgente']})"
        if custo_urgente >= custo_nao_urgente
        else f"nao urgente ({nao_urgente['viagem_urgente']})"
    )
    diferenca_absoluta = abs(custo_urgente - custo_nao_urgente)

    diferenca_percentual = None
    if custo_nao_urgente != 0:
        diferenca_percentual = (
            (custo_urgente - custo_nao_urgente) / custo_nao_urgente
        ) * 100

    resposta_encarece = (
        "Sim. A urgencia encarece o dia da viagem."
        if custo_urgente > custo_nao_urgente
        else "Nao. A urgencia nao encarece o dia da viagem."
    )

    if participacao_urgente > 50:
        resposta_volume = (
            f"As viagens urgentes representam {participacao_urgente:.2f}% das viagens "
            "analisadas e, portanto, constituem a maioria do conjunto, com volume "
            "relevante."
        )
    elif participacao_urgente == 50:
        resposta_volume = (
            "As viagens urgentes representam 50,00% das viagens analisadas, portanto "
            "os dois grupos possuem a mesma participacao."
        )
    else:
        resposta_volume = (
            f"As viagens urgentes representam {participacao_urgente:.2f}% das viagens "
            "analisadas e, portanto, formam um grupo minoritario no conjunto."
        )

    trecho_percentual = (
        f"{diferenca_percentual:.2f}%"
        if diferenca_percentual is not None
        else "comparacao percentual indisponivel por base de referencia igual a zero"
    )

    return (
        f"O grupo com maior custo medio diario foi o {grupo_mais_caro}. "
        f"As viagens urgentes registraram custo medio diario de "
        f"{formatar_reais(custo_urgente)}, contra {formatar_reais(custo_nao_urgente)} "
        f"nas nao urgentes, uma diferenca absoluta de "
        f"{formatar_reais(diferenca_absoluta)} e diferenca percentual de "
        f"{trecho_percentual}. Em volume, o grupo urgente somou {qtd_urgente} viagens "
        f"e o nao urgente {qtd_nao_urgente}, com participacao de "
        f"{participacao_urgente:.2f}% das urgentes no total analisado. A duracao media "
        f"foi de {duracao_urgente:.2f} dias nas urgentes e {duracao_nao_urgente:.2f} "
        f"dias nas nao urgentes, enquanto o valor total medio foi de "
        f"{formatar_reais(valor_total_urgente)} e "
        f"{formatar_reais(valor_total_nao_urgente)}, respectivamente. "
        f"{resposta_encarece} {resposta_volume}"
    )


def analisar_pergunta_2(df: pd.DataFrame) -> str:
    """Produz uma analise textual deterministica para a Pergunta 2."""

    df_analise = df.copy()
    faixa_maior_custo = df_analise.loc[df_analise["custo_medio_diario"].idxmax()]
    faixa_menor_custo = df_analise.loc[df_analise["custo_medio_diario"].idxmin()]
    faixa_maior_volume = df_analise.loc[df_analise["qtd_viagens"].idxmax()]
    faixa_maior_valor_total = df_analise.loc[df_analise["valor_total_medio"].idxmax()]
    faixa_menor_valor_total = df_analise.loc[df_analise["valor_total_medio"].idxmin()]

    maior_custo = float(faixa_maior_custo["custo_medio_diario"])
    menor_custo = float(faixa_menor_custo["custo_medio_diario"])
    diferenca_absoluta = maior_custo - menor_custo

    diferenca_percentual = None
    if menor_custo != 0:
        diferenca_percentual = ((maior_custo - menor_custo) / menor_custo) * 100

    trecho_percentual = (
        f"{diferenca_percentual:.2f}%"
        if diferenca_percentual is not None
        else "comparacao percentual indisponivel porque a menor faixa tem custo zero"
    )

    custos = [float(valor) for valor in df_analise["custo_medio_diario"].tolist()]
    tendencia = "nao ha tendencia monotonicamente clara"
    if all(atual <= proximo for atual, proximo in zip(custos, custos[1:])):
        tendencia = "o custo medio diario tende a crescer conforme a duracao aumenta"
    elif all(atual >= proximo for atual, proximo in zip(custos, custos[1:])):
        tendencia = "o custo medio diario tende a cair conforme a duracao aumenta"
    else:
        primeira_faixa = df_analise.iloc[0]
        ultima_faixa = df_analise.iloc[-1]
        if float(ultima_faixa["custo_medio_diario"]) < float(
            primeira_faixa["custo_medio_diario"]
        ):
            tendencia = (
                "o custo medio diario termina menor nas faixas longas, mas sem "
                "trajetoria monotonicamente decrescente"
            )
        elif float(ultima_faixa["custo_medio_diario"]) > float(
            primeira_faixa["custo_medio_diario"]
        ):
            tendencia = (
                "o custo medio diario termina maior nas faixas longas, mas sem "
                "trajetoria monotonicamente crescente"
            )

    observacao_faixas = ""
    if len(df_analise) < 5:
        observacao_faixas = (
            f" A base retornou {len(df_analise)} faixas de duracao, portanto a "
            "comparacao foi feita apenas entre as categorias existentes."
        )

    return (
        f"A faixa com maior custo medio diario foi '{faixa_maior_custo['faixa_duracao']}', "
        f"com {formatar_reais(maior_custo)} e {int(faixa_maior_custo['qtd_viagens'])} "
        f"viagens, enquanto a menor foi '{faixa_menor_custo['faixa_duracao']}', com "
        f"{formatar_reais(menor_custo)} e {int(faixa_menor_custo['qtd_viagens'])} "
        f"viagens. A diferenca absoluta entre essas extremidades foi de "
        f"{formatar_reais(diferenca_absoluta)} e a diferenca percentual foi de "
        f"{trecho_percentual}. A faixa com maior volume de viagens foi "
        f"'{faixa_maior_volume['faixa_duracao']}', com "
        f"{int(faixa_maior_volume['qtd_viagens'])} registros. Em valor total medio, "
        f"a faixa mais alta foi '{faixa_maior_valor_total['faixa_duracao']}' com "
        f"{formatar_reais(float(faixa_maior_valor_total['valor_total_medio']))}, "
        f"enquanto a menor foi '{faixa_menor_valor_total['faixa_duracao']}' com "
        f"{formatar_reais(float(faixa_menor_valor_total['valor_total_medio']))}. "
        f"Assim, o custo medio diario varia por faixa de duracao de modo que "
        f"{tendencia}.{observacao_faixas}"
    )


def analisar_pergunta_3(df: pd.DataFrame) -> str:
    """Produz a analise textual deterministica para a Pergunta 3."""

    df_analise = preparar_dataframe_pergunta_3(df)

    totais_mensais = (
        df_analise.groupby(
            ["ano_referencia", "mes_referencia", "referencia_temporal"], as_index=False
        )["valor_total_pago"]
        .sum()
        .sort_values("referencia_temporal")
        .reset_index(drop=True)
    )

    primeiro_mes = totais_mensais.iloc[0]
    ultimo_mes = totais_mensais.iloc[-1]
    mes_maior_valor = totais_mensais.loc[totais_mensais["valor_total_pago"].idxmax()]
    mes_menor_valor = totais_mensais.loc[totais_mensais["valor_total_pago"].idxmin()]

    valor_primeiro_mes = float(primeiro_mes["valor_total_pago"])
    valor_ultimo_mes = float(ultimo_mes["valor_total_pago"])
    variacao_percentual = None
    if valor_primeiro_mes != 0:
        variacao_percentual = (
            (valor_ultimo_mes - valor_primeiro_mes) / valor_primeiro_mes
        ) * 100

    participacoes = (
        df_analise.pivot_table(
            index="tipo_pagamento",
            columns="referencia_temporal",
            values="participacao_percentual",
            aggfunc="sum",
            fill_value=0.0,
        )
        .sort_index()
    )

    referencia_inicial = totais_mensais.iloc[0]["referencia_temporal"]
    referencia_final = totais_mensais.iloc[-1]["referencia_temporal"]
    participacao_inicial = participacoes.get(referencia_inicial, pd.Series(dtype=float))
    participacao_final = participacoes.get(referencia_final, pd.Series(dtype=float))
    variacao_participacao = (participacao_final - participacao_inicial).sort_values(
        ascending=False
    )

    tipo_maior_inicio = participacao_inicial.idxmax()
    tipo_maior_final = participacao_final.idxmax()
    tipo_mais_ganhou = variacao_participacao.idxmax()
    tipo_mais_perdeu = variacao_participacao.idxmin()
    ganho_pp = float(variacao_participacao.loc[tipo_mais_ganhou])
    perda_pp = float(variacao_participacao.loc[tipo_mais_perdeu])

    acumulado_por_tipo = (
        df_analise.groupby("tipo_pagamento", as_index=False)["valor_total_pago"]
        .sum()
        .sort_values(["valor_total_pago", "tipo_pagamento"], ascending=[False, True])
        .reset_index(drop=True)
    )
    tipo_sustenta = acumulado_por_tipo.iloc[0]
    total_periodo = float(acumulado_por_tipo["valor_total_pago"].sum())
    participacao_tipo_sustenta = (
        (float(tipo_sustenta["valor_total_pago"]) / total_periodo) * 100
        if total_periodo != 0
        else 0.0
    )

    meses_texto = ", ".join(
        referencia.strftime("%m/%Y") for referencia in totais_mensais["referencia_temporal"]
    )
    trecho_variacao = (
        f"variacao de {variacao_percentual:.2f}% entre o primeiro e o ultimo mes"
        if variacao_percentual is not None
        else "variacao percentual indisponivel porque o primeiro mes teve total igual a zero"
    )

    observacao_sazonalidade = (
        "Os dados permitem identificar variacoes mensais, mas o periodo analisado "
        "e insuficiente para confirmar um padrao sazonal recorrente."
    )

    return (
        f"O valor total pago evoluiu ao longo de {len(totais_mensais)} meses "
        f"({meses_texto}), saindo de {formatar_reais(valor_primeiro_mes)} em "
        f"{primeiro_mes['referencia_temporal'].strftime('%m/%Y')} para "
        f"{formatar_reais(valor_ultimo_mes)} em "
        f"{ultimo_mes['referencia_temporal'].strftime('%m/%Y')}, com {trecho_variacao}. "
        f"O maior valor mensal ocorreu em "
        f"{mes_maior_valor['referencia_temporal'].strftime('%m/%Y')} "
        f"({formatar_reais(float(mes_maior_valor['valor_total_pago']))}) e o menor em "
        f"{mes_menor_valor['referencia_temporal'].strftime('%m/%Y')} "
        f"({formatar_reais(float(mes_menor_valor['valor_total_pago']))}). "
        f"Quanto a sazonalidade, observa-se variacao mensal no periodo, com picos e "
        f"reducoes descritivas entre meses, mas sem base suficiente para afirmar "
        f"sazonalidade recorrente; {observacao_sazonalidade} "
        f"No inicio do periodo, o tipo com maior participacao foi "
        f"'{tipo_maior_inicio}', com {float(participacao_inicial.loc[tipo_maior_inicio]):.2f}%. "
        f"No final do periodo, o maior foi '{tipo_maior_final}', com "
        f"{float(participacao_final.loc[tipo_maior_final]):.2f}%. "
        f"O tipo que mais ganhou participacao entre "
        f"{referencia_inicial.strftime('%m/%Y')} e {referencia_final.strftime('%m/%Y')} "
        f"foi '{tipo_mais_ganhou}', com {ganho_pp:+.2f} pontos percentuais, enquanto "
        f"o que mais perdeu foi '{tipo_mais_perdeu}', com {perda_pp:+.2f} pontos "
        f"percentuais. No periodo analisado, o tipo "
        f"'{tipo_sustenta['tipo_pagamento']}' concentrou "
        f"{formatar_reais(float(tipo_sustenta['valor_total_pago']))}, equivalente a "
        f"{participacao_tipo_sustenta:.2f}% do valor total pago, sendo o tipo que mais "
        f"sustenta a evolucao do valor pago no periodo."
    )


def analisar_pergunta_4(df: pd.DataFrame) -> str:
    """Produz a analise textual deterministica para a Pergunta 4."""

    df_analise, mediana_qtd_pagamentos, mediana_valor_medio_pagamento = (
        classificar_perfil_orgaos(df)
    )

    orgao_maior_valor = df_analise.iloc[0]
    orgao_maior_pagamentos = df_analise.loc[df_analise["qtd_pagamentos"].idxmax()]
    orgao_maior_ticket = df_analise.loc[
        df_analise["valor_medio_pagamento"].idxmax()
    ]
    orgao_menor_ticket = df_analise.loc[
        df_analise["valor_medio_pagamento"].idxmin()
    ]
    orgao_maior_viagens = df_analise.loc[df_analise["qtd_viagens_atendidas"].idxmax()]

    diferenca_absoluta_ticket = float(
        orgao_maior_ticket["valor_medio_pagamento"]
        - orgao_menor_ticket["valor_medio_pagamento"]
    )
    diferenca_percentual_ticket = None
    menor_ticket = float(orgao_menor_ticket["valor_medio_pagamento"])
    if menor_ticket != 0:
        diferenca_percentual_ticket = (diferenca_absoluta_ticket / menor_ticket) * 100

    contagem_perfis = (
        df_analise["perfil"].value_counts().reindex(
            [
                "alto volume / ticket alto",
                "alto volume / ticket baixo",
                "baixo volume / ticket alto",
                "baixo volume / ticket baixo",
            ],
            fill_value=0,
        )
    )

    orgaos_alto_volume_ticket_baixo = df_analise.loc[
        df_analise["perfil"] == "alto volume / ticket baixo",
        "nome_orgao_pagador",
    ].tolist()
    orgaos_baixo_volume_ticket_alto = df_analise.loc[
        df_analise["perfil"] == "baixo volume / ticket alto",
        "nome_orgao_pagador",
    ].tolist()

    resumo_alto_volume_ticket_baixo = (
        ", ".join(orgaos_alto_volume_ticket_baixo)
        if orgaos_alto_volume_ticket_baixo
        else "nenhum orgao"
    )
    resumo_baixo_volume_ticket_alto = (
        ", ".join(orgaos_baixo_volume_ticket_alto)
        if orgaos_baixo_volume_ticket_alto
        else "nenhum orgao"
    )

    relacao_volume_ticket = (
        "No Top 10, a classificacao relativa pelas medianas indica "
        f"{contagem_perfis['alto volume / ticket alto']} orgaos em alto volume / ticket alto, "
        f"{contagem_perfis['alto volume / ticket baixo']} em alto volume / ticket baixo, "
        f"{contagem_perfis['baixo volume / ticket alto']} em baixo volume / ticket alto e "
        f"{contagem_perfis['baixo volume / ticket baixo']} em baixo volume / ticket baixo."
    )

    trecho_diferenca_percentual = (
        f"{diferenca_percentual_ticket:.2f}%"
        if diferenca_percentual_ticket is not None
        else "indisponivel porque o menor ticket medio foi zero"
    )

    return (
        f"No Top 10 por valor total pago, o orgao com maior desembolso foi "
        f"'{orgao_maior_valor['nome_orgao_pagador']}', com "
        f"{formatar_reais(float(orgao_maior_valor['valor_total_pago']))}, "
        f"{int(orgao_maior_valor['qtd_pagamentos'])} pagamentos, ticket medio de "
        f"{formatar_reais(float(orgao_maior_valor['valor_medio_pagamento']))}, "
        f"{int(orgao_maior_valor['qtd_viagens_atendidas'])} viagens atendidas e perfil "
        f"relativo '{orgao_maior_valor['perfil']}'. O maior volume de pagamentos foi de "
        f"'{orgao_maior_pagamentos['nome_orgao_pagador']}', com "
        f"{int(orgao_maior_pagamentos['qtd_pagamentos'])} pagamentos, enquanto o maior "
        f"ticket medio apareceu em '{orgao_maior_ticket['nome_orgao_pagador']}', com "
        f"{formatar_reais(float(orgao_maior_ticket['valor_medio_pagamento']))}. O maior "
        f"volume de viagens atendidas ficou com "
        f"'{orgao_maior_viagens['nome_orgao_pagador']}', com "
        f"{int(orgao_maior_viagens['qtd_viagens_atendidas'])} viagens. Dentro do Top 10, "
        f"o menor ticket medio foi o de '{orgao_menor_ticket['nome_orgao_pagador']}', com "
        f"{formatar_reais(float(orgao_menor_ticket['valor_medio_pagamento']))}. A "
        f"diferenca entre o maior e o menor ticket medio foi de "
        f"{formatar_reais(diferenca_absoluta_ticket)} e {trecho_diferenca_percentual}. "
        f"As medianas usadas para classificar os perfis relativos dos 10 maiores orgaos "
        f"foram {mediana_qtd_pagamentos:.1f} pagamentos e "
        f"{formatar_reais(mediana_valor_medio_pagamento)} de ticket medio. "
        f"{relacao_volume_ticket} Os orgaos em alto volume / ticket baixo foram "
        f"{resumo_alto_volume_ticket_baixo}; ja os orgaos em baixo volume / ticket alto "
        f"foram {resumo_baixo_volume_ticket_alto}. Em termos de gasto publico, os dados "
        f"sugerem perfis distintos de desembolso entre os maiores orgaos pagadores: um "
        f"orgao pode liderar o gasto total por alta quantidade de pagamentos, por ticket "
        f"medio elevado ou pela combinacao dos dois, enquanto orgaos com muitos pagamentos "
        f"e ticket mais baixo tendem a indicar gasto mais pulverizado e orgaos com menos "
        f"pagamentos e ticket mais alto tendem a indicar desembolso mais concentrado, sem "
        f"que isso permita inferir juizo de eficiencia ou irregularidade apenas por esse "
        f"recorte. Como a camada Gold esta agregada por mes, orgao e tipo de pagamento, a "
        f"soma de qtd_viagens pode contabilizar uma mesma viagem em mais de um grupo quando "
        f"existem multiplos tipos de pagamento."
    )


def executar_pergunta_1() -> None:
    """Executa a Pergunta 1 e falha com excecao se necessario."""

    print("=" * 60)
    print("PERGUNTA 1")
    print("Quais viagens urgentes custam mais por dia do que as nao urgentes?")
    print("=" * 60)
    print()

    df = consultar_pergunta_1()
    validar_resultado_pergunta_1(df)

    print("Consulta SQL:")
    print(SQL_PERGUNTA_1)
    print()

    print("Resultado:")
    print(exibir_resultado_pergunta_1(df))
    print()

    caminho_grafico = gerar_grafico_pergunta_1(df)
    print(f"Grafico salvo em: {caminho_grafico}")
    print()

    analise = analisar_pergunta_1(df)
    print("Analise:")
    print(analise)
    print()


def executar_pergunta_2() -> None:
    """Executa a Pergunta 2 e falha com excecao se necessario."""

    print("=" * 60)
    print("PERGUNTA 2")
    print("Como o custo medio diario varia conforme a duracao da viagem?")
    print("=" * 60)
    print()

    df = consultar_pergunta_2()
    validar_resultado_pergunta_2(df)

    print("Consulta SQL:")
    print(SQL_PERGUNTA_2)
    print()

    print("Resultado:")
    print(exibir_resultado_pergunta_2(df))
    print()

    caminho_grafico = gerar_grafico_pergunta_2(df)
    print(f"Grafico salvo em: {caminho_grafico}")
    print()

    analise = analisar_pergunta_2(df)
    print("Analise:")
    print(analise)


def executar_pergunta_3() -> None:
    """Executa a Pergunta 3 e falha com excecao se necessario."""

    print()
    print("=" * 60)
    print("PERGUNTA 3")
    print("Como o valor pago evoluiu mes a mes e qual tipo de pagamento")
    print("sustenta essa evolucao?")
    print("=" * 60)
    print()

    df = consultar_pergunta_3()
    validar_resultado_pergunta_3(df)

    print("Consulta SQL:")
    print(SQL_PERGUNTA_3)
    print()

    print("Resultado:")
    print(exibir_resultado_pergunta_3(df))
    print()

    caminho_grafico = gerar_grafico_pergunta_3(df)
    print(f"Grafico salvo em: {caminho_grafico}")
    print()

    analise = analisar_pergunta_3(df)
    print("Analise:")
    print(analise)


def executar_pergunta_4() -> None:
    """Executa a Pergunta 4 e falha com excecao se necessario."""

    print()
    print("=" * 60)
    print("PERGUNTA 4")
    print("Qual e o perfil de gasto dos orgaos pagadores?")
    print("=" * 60)
    print()

    df = consultar_pergunta_4()
    validar_resultado_pergunta_4(df)

    print("Consulta SQL:")
    print(SQL_PERGUNTA_4)
    print()

    print("Resultado:")
    print(exibir_resultado_pergunta_4(df))
    print()

    caminho_grafico = gerar_grafico_pergunta_4(df)
    print(f"Grafico salvo em: {caminho_grafico}")
    print()

    analise = analisar_pergunta_4(df)
    print("Analise:")
    print(analise)


def executar_analise() -> int:
    """Executa as perguntas implementadas da secao analitica."""

    try:
        executar_pergunta_1()
        executar_pergunta_2()
        executar_pergunta_3()
        executar_pergunta_4()
        return 0
    except psycopg2.Error as erro:
        print("Erro PostgreSQL durante a execucao das analises.")
        print(f"Detalhes: {erro}")
        return 1
    except Exception as erro:
        print("Erro durante a execucao das analises.")
        print(f"Detalhes: {erro}")
        return 1


if __name__ == "__main__":
    raise SystemExit(executar_analise())
