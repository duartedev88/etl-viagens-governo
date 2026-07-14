"""Configuracoes de ambiente do projeto."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
CAMINHO_ENV = RAIZ_PROJETO / ".env"

load_dotenv(CAMINHO_ENV)


@dataclass(frozen=True)
class ConfiguracaoBanco:
    """Configuracoes de conexao com o PostgreSQL."""

    host: str
    porta: int
    nome_banco: str
    usuario: str
    senha: str


def _obter_variavel_obrigatoria(nome_variavel: str) -> str:
    """Retorna uma variavel obrigatoria do ambiente."""

    valor = os.getenv(nome_variavel)

    if not valor:
        raise ValueError(
            f"A variavel de ambiente obrigatoria '{nome_variavel}' nao foi definida."
        )

    return valor


def carregar_configuracao_banco() -> ConfiguracaoBanco:
    """Carrega e valida as configuracoes do banco de dados."""

    porta_texto = _obter_variavel_obrigatoria("DB_PORT")

    try:
        porta = int(porta_texto)
    except ValueError as exc:
        raise ValueError("A variavel de ambiente 'DB_PORT' deve ser um inteiro.") from exc

    return ConfiguracaoBanco(
        host=_obter_variavel_obrigatoria("DB_HOST"),
        porta=porta,
        nome_banco=_obter_variavel_obrigatoria("DB_NAME"),
        usuario=_obter_variavel_obrigatoria("DB_USER"),
        senha=_obter_variavel_obrigatoria("DB_PASSWORD"),
    )


CONFIGURACAO_BANCO = carregar_configuracao_banco()
