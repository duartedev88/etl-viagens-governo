"""Configurações de ambiente do projeto."""

import os
from urllib.parse import parse_qs, urlparse
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
CAMINHO_ENV = RAIZ_PROJETO / ".env"

load_dotenv(CAMINHO_ENV)


@dataclass(frozen=True)
class ConfiguracaoBanco:
    """Configurações de conexão com o PostgreSQL."""

    host: str
    porta: int
    nome_banco: str
    usuario: str
    senha: str


@dataclass(frozen=True)
class ConfiguracaoDrive:
    """Configuração do arquivo ZIP no Google Drive."""

    file_id: str


def _obter_variavel_obrigatoria(nome_variavel: str) -> str:
    """Retorna uma variável obrigatória do ambiente."""

    valor = os.getenv(nome_variavel)

    if valor is None or not valor.strip():
        raise ValueError(
            f"A variável de ambiente obrigatória "
            f"'{nome_variavel}' não foi definida."
        )

    return valor.strip()


def carregar_configuracao_banco() -> ConfiguracaoBanco:
    """Carrega e valida as configurações do banco de dados."""

    porta_texto = _obter_variavel_obrigatoria("DB_PORT")

    try:
        porta = int(porta_texto)
    except ValueError as exc:
        raise ValueError(
            "A variável de ambiente 'DB_PORT' deve ser um inteiro."
        ) from exc

    if not 1 <= porta <= 65535:
        raise ValueError(
            "A variável de ambiente 'DB_PORT' deve estar "
            "entre 1 e 65535."
        )

    return ConfiguracaoBanco(
        host=_obter_variavel_obrigatoria("DB_HOST"),
        porta=porta,
        nome_banco=_obter_variavel_obrigatoria("DB_NAME"),
        usuario=_obter_variavel_obrigatoria("DB_USER"),
        senha=_obter_variavel_obrigatoria("DB_PASSWORD"),
    )


def carregar_configuracao_drive() -> ConfiguracaoDrive:
    """Carrega e valida a configuração do Google Drive."""

    valor_bruto = os.getenv("DRIVE_FILE_ID")

    if valor_bruto is None or not valor_bruto.strip():
        raise ValueError(
            "Defina 'DRIVE_FILE_ID' no arquivo .env com o ID ou a URL "
            "de compartilhamento do arquivo no Google Drive."
        )

    valor_normalizado = valor_bruto.strip()

    if "drive.google.com" in valor_normalizado:
        url = urlparse(valor_normalizado)
        parametros = parse_qs(url.query)
        file_id = parametros.get("id", [None])[0]

        if file_id is None:
            partes = [parte for parte in url.path.split("/") if parte]

            if "d" in partes:
                indice = partes.index("d")
                if indice + 1 < len(partes):
                    file_id = partes[indice + 1]

        if file_id is None or not file_id.strip():
            raise ValueError(
                "Não foi possível extrair o ID do arquivo a partir de "
                "'DRIVE_FILE_ID'. Use o ID puro ou uma URL válida do Google Drive."
            )

        valor_normalizado = file_id.strip()

    return ConfiguracaoDrive(
        file_id=valor_normalizado,
    )


CONFIGURACAO_BANCO = carregar_configuracao_banco()
