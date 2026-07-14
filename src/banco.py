"""Conexao e teste simples com PostgreSQL."""

from typing import Any

import psycopg2
from psycopg2.extensions import connection as Connection
from psycopg2.extensions import cursor as Cursor

from src.config import CONFIGURACAO_BANCO


def conectar() -> Connection:
    """Cria e retorna uma conexao com o PostgreSQL."""

    try:
        return psycopg2.connect(
            host=CONFIGURACAO_BANCO.host,
            port=CONFIGURACAO_BANCO.porta,
            dbname=CONFIGURACAO_BANCO.nome_banco,
            user=CONFIGURACAO_BANCO.usuario,
            password=CONFIGURACAO_BANCO.senha,
        )
    except psycopg2.Error as exc:
        raise ConnectionError(
            "Nao foi possivel conectar ao PostgreSQL. "
            f"Host: {CONFIGURACAO_BANCO.host}, "
            f"Porta: {CONFIGURACAO_BANCO.porta}, "
            f"Banco: {CONFIGURACAO_BANCO.nome_banco}, "
            f"Usuario: {CONFIGURACAO_BANCO.usuario}."
        ) from exc


def testar_conexao() -> str:
    """Executa um teste simples de conexao com o banco."""

    conexao: Connection | None = None
    cursor: Cursor | None = None

    try:
        conexao = conectar()
        cursor = conexao.cursor()
        cursor.execute("SELECT version();")
        resultado = cursor.fetchone()

        if not resultado:
            raise ConnectionError(
                "A conexao foi estabelecida, mas nao houve retorno do banco."
            )

        return str(resultado[0])
    except (psycopg2.Error, ConnectionError) as exc:
        raise ConnectionError("Falha ao executar o teste de conexao no PostgreSQL.") from exc
    finally:
        if cursor is not None:
            cursor.close()

        if conexao is not None:
            conexao.close()


if __name__ == "__main__":
    versao = testar_conexao()
    print("Conexao com PostgreSQL realizada com sucesso.")
    print(versao)
