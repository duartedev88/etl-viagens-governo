"""Download e extração inicial dos arquivos brutos."""

import sys
import zipfile
from pathlib import Path

import gdown
import pandas as pd
import psycopg2
from gdown.exceptions import FileURLRetrievalError
from psycopg2 import sql
from psycopg2.extensions import cursor as Cursor
from psycopg2.extras import execute_values
from requests import RequestException

# Inclui a raiz do projeto no caminho de importação quando o script
# é executado diretamente pelo PyCharm ou pelo terminal.
RAIZ_PROJETO = Path(__file__).resolve().parent.parent

if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from src.config import carregar_configuracao_drive
from src.banco import conectar


DIRETORIO_RAW = RAIZ_PROJETO / "data" / "raw"
DIRETORIO_EXTRAIDO = RAIZ_PROJETO / "data" / "extracted"
CAMINHO_SCRIPT_SQL = RAIZ_PROJETO / "sql" / "0_criar_banco.sql"
NOME_ARQUIVO_ZIP = "viagens_2025_6meses.zip"
CAMINHO_ARQUIVO_ZIP = DIRETORIO_RAW / NOME_ARQUIVO_ZIP
TAMANHO_CHUNK = 10_000
ENCODING_CSV = "cp1252"
MARCADOR_INICIO_SQL = "-- INICIO_CRIACAO_AUTOMATICA"
MARCADOR_FIM_SQL = "-- FIM_CRIACAO_AUTOMATICA"
ARQUIVOS_ESPERADOS = {
    "2025_Viagem.csv",
    "2025_Pagamento.csv",
    "2025_Passagem.csv",
    "2025_Trecho.csv",
}
ARQUIVOS_TABELAS = {
    "2025_Viagem.csv": "raw_viagem",
    "2025_Pagamento.csv": "raw_pagamento",
    "2025_Passagem.csv": "raw_passagem",
    "2025_Trecho.csv": "raw_trecho",
}
ORDEM_CARGA = [
    "2025_Viagem.csv",
    "2025_Pagamento.csv",
    "2025_Passagem.csv",
    "2025_Trecho.csv",
]


def preparar_diretorios() -> None:
    """Cria os diretórios necessários para a extração."""

    DIRETORIO_RAW.mkdir(parents=True, exist_ok=True)
    DIRETORIO_EXTRAIDO.mkdir(parents=True, exist_ok=True)


def baixar_arquivo_zip(
    drive_file_id: str,
    caminho_destino: Path,
) -> Path:
    """Baixa o arquivo ZIP do Google Drive."""

    drive_file_id = drive_file_id.strip()

    if not drive_file_id:
        raise ValueError(
            "A configuração DRIVE_FILE_ID está ausente ou vazia."
        )

    url = f"https://drive.google.com/uc?id={drive_file_id}"

    try:
        if caminho_destino.exists():
            caminho_destino.unlink()

        resultado = gdown.download(
            url=url,
            output=str(caminho_destino),
            quiet=True,
        )
    except FileURLRetrievalError as exc:
        raise PermissionError(
            "Não foi possível obter o arquivo no Google Drive. "
            "Confirme se o ID está correto e se o arquivo está compartilhado "
            "como 'Qualquer pessoa com o link' ou equivalente."
        ) from exc
    except RequestException as exc:
        raise ConnectionError(
            "Falha ao baixar o arquivo do Google Drive. "
            "Verifique o ID informado, a permissão de compartilhamento "
            "e a conexão com a internet."
        ) from exc
    except PermissionError as exc:
        raise PermissionError(
            f"Sem permissão para gravar o arquivo ZIP em '{caminho_destino}'."
        ) from exc
    except OSError as exc:
        raise OSError("Falha ao salvar o arquivo ZIP baixado do Google Drive.") from exc

    if resultado is None or not caminho_destino.exists():
        raise FileNotFoundError("O arquivo ZIP não foi criado após o download.")

    if caminho_destino.stat().st_size == 0:
        raise ValueError("O arquivo ZIP foi baixado, mas está vazio.")

    return caminho_destino


def _remover_csvs_antigos(diretorio_destino: Path) -> None:
    """Remove apenas versões antigas dos CSVs esperados."""

    for nome_arquivo in ARQUIVOS_ESPERADOS:
        caminho_arquivo = diretorio_destino / nome_arquivo

        if caminho_arquivo.exists():
            try:
                caminho_arquivo.unlink()
            except PermissionError as exc:
                raise PermissionError(
                    f"Sem permissão para remover '{caminho_arquivo.name}'."
                ) from exc


def _validar_conteudo_zip(
    arquivo_zip: zipfile.ZipFile,
    diretorio_destino: Path,
) -> None:
    """Valida se o conteúdo do ZIP será extraído no diretório esperado."""

    destino_resolvido = diretorio_destino.resolve()

    for membro in arquivo_zip.infolist():
        caminho_final = (diretorio_destino / membro.filename).resolve()

        if (
            destino_resolvido not in caminho_final.parents
            and caminho_final != destino_resolvido
        ):
            raise ValueError(
                f"Caminho inválido encontrado no ZIP: '{membro.filename}'."
            )


def extrair_arquivo_zip(
    caminho_zip: Path,
    diretorio_destino: Path,
) -> list[Path]:
    """Extrai os arquivos CSV do ZIP para o diretório informado."""

    if not caminho_zip.exists():
        raise FileNotFoundError(f"O arquivo ZIP '{caminho_zip}' não foi encontrado.")

    if not zipfile.is_zipfile(caminho_zip):
        raise ValueError("O arquivo informado não é um ZIP válido.")

    _remover_csvs_antigos(diretorio_destino)

    try:
        with zipfile.ZipFile(caminho_zip, "r") as arquivo_zip:
            _validar_conteudo_zip(arquivo_zip, diretorio_destino)
            arquivo_zip.extractall(diretorio_destino)
    except PermissionError as exc:
        raise PermissionError(
            f"Sem permissão para extrair arquivos em '{diretorio_destino}'."
        ) from exc
    except zipfile.BadZipFile as exc:
        raise zipfile.BadZipFile("O arquivo ZIP está inválido ou corrompido.") from exc
    except OSError as exc:
        raise OSError("Falha ao extrair o conteúdo do arquivo ZIP.") from exc

    return sorted(
        [
            diretorio_destino / nome_arquivo
            for nome_arquivo in ARQUIVOS_ESPERADOS
            if (diretorio_destino / nome_arquivo).exists()
        ]
    )


def validar_arquivos_csv(
    diretorio: Path,
) -> dict[str, Path]:
    """Valida a existência e o tamanho dos CSVs esperados."""

    arquivos_validados: dict[str, Path] = {}

    for nome_arquivo in sorted(ARQUIVOS_ESPERADOS):
        caminho_arquivo = diretorio / nome_arquivo

        if not caminho_arquivo.exists():
            raise FileNotFoundError(
                f"O arquivo CSV obrigatório '{nome_arquivo}' não foi encontrado."
            )

        if caminho_arquivo.stat().st_size == 0:
            raise ValueError(f"O arquivo CSV '{nome_arquivo}' está vazio.")

        arquivos_validados[nome_arquivo] = caminho_arquivo

    return arquivos_validados


def obter_colunas_tabela(cursor: Cursor, nome_tabela: str) -> list[str]:
    """Obtém as colunas da tabela na ordem em que foram criadas."""

    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
        ORDER BY ordinal_position;
        """,
        (nome_tabela,),
    )
    resultado = cursor.fetchall()

    if not resultado:
        raise FileNotFoundError(
            f"A tabela Raw '{nome_tabela}' não foi encontrada no PostgreSQL."
        )

    return [str(linha[0]) for linha in resultado]


def validar_cabecalhos(
    colunas_csv: list[str],
    colunas_tabela: list[str],
    nome_arquivo: str,
    nome_tabela: str,
) -> None:
    """Valida se os cabeçalhos do CSV correspondem à tabela Raw."""

    if colunas_csv != colunas_tabela:
        raise ValueError(
            f"Incompatibilidade de cabeçalhos no arquivo '{nome_arquivo}' "
            f"para a tabela '{nome_tabela}'. "
            f"Colunas esperadas: {colunas_tabela}. "
            f"Colunas encontradas: {colunas_csv}."
        )


def obter_tabelas_raw_ausentes(cursor: Cursor) -> list[str]:
    """Retorna os nomes das tabelas Raw ainda não criadas."""

    tabelas_esperadas = list(ARQUIVOS_TABELAS.values())

    cursor.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name = ANY(%s)
        ORDER BY table_name;
        """,
        (tabelas_esperadas,),
    )
    tabelas_encontradas = [str(linha[0]) for linha in cursor.fetchall()]

    return sorted(
        set(tabelas_esperadas) - set(tabelas_encontradas)
    )


def carregar_script_criacao_tabelas(caminho_sql: Path) -> str:
    """Lê a seção de criação automática do arquivo SQL."""

    if not caminho_sql.exists():
        raise FileNotFoundError(
            f"O arquivo SQL '{caminho_sql}' não foi encontrado."
        )

    conteudo_sql = caminho_sql.read_text(encoding="utf-8")
    indice_inicio = conteudo_sql.find(MARCADOR_INICIO_SQL)
    indice_fim = conteudo_sql.find(MARCADOR_FIM_SQL)

    if indice_inicio == -1:
        raise ValueError(
            f"Marcador inicial '{MARCADOR_INICIO_SQL}' não encontrado em "
            f"'{caminho_sql.name}'."
        )

    if indice_fim == -1:
        raise ValueError(
            f"Marcador final '{MARCADOR_FIM_SQL}' não encontrado em "
            f"'{caminho_sql.name}'."
        )

    if indice_inicio >= indice_fim:
        raise ValueError(
            f"Os marcadores de criação automática em '{caminho_sql.name}' "
            "estão em ordem inválida."
        )

    inicio_conteudo = indice_inicio + len(MARCADOR_INICIO_SQL)
    trecho_sql = conteudo_sql[inicio_conteudo:indice_fim].strip()

    if not trecho_sql:
        raise ValueError(
            f"A seção de criação automática em '{caminho_sql.name}' está vazia."
        )

    return trecho_sql


def garantir_tabelas_raw(cursor: Cursor) -> bool:
    """Cria a estrutura do banco quando as tabelas Raw estiverem ausentes."""

    tabelas_ausentes = obter_tabelas_raw_ausentes(cursor)

    if not tabelas_ausentes:
        print("Estrutura das tabelas Raw já está disponível.")
        return False

    tabelas_texto = ", ".join(tabelas_ausentes)
    print(f"Tabelas Raw ausentes: {tabelas_texto}.")
    print(f"Executando o script '{CAMINHO_SCRIPT_SQL.name}'...")

    script_sql = carregar_script_criacao_tabelas(CAMINHO_SCRIPT_SQL)
    cursor.execute(script_sql)

    tabelas_restantes = obter_tabelas_raw_ausentes(cursor)

    if tabelas_restantes:
        raise RuntimeError(
            "A criação automática não concluiu todas as tabelas Raw. "
            f"Tabelas ainda ausentes: {tabelas_restantes}."
        )

    print("Tabelas criadas com sucesso.")
    return True


def limpar_tabelas_raw(cursor: Cursor) -> None:
    """Remove os registros atuais das tabelas Raw."""

    cursor.execute(
        """
        TRUNCATE TABLE
            raw_trecho,
            raw_passagem,
            raw_pagamento,
            raw_viagem;
        """
    )


def inserir_chunk(
    cursor: Cursor,
    nome_tabela: str,
    colunas: list[str],
    dados: list[tuple[str, ...]],
) -> int:
    """Insere um bloco de registros e retorna a quantidade inserida."""

    if not dados:
        return 0

    comando_insert = sql.SQL("INSERT INTO {tabela} ({colunas}) VALUES %s").format(
        tabela=sql.Identifier(nome_tabela),
        colunas=sql.SQL(", ").join(
            sql.Identifier(coluna) for coluna in colunas
        ),
    )

    execute_values(
        cursor,
        comando_insert.as_string(cursor.connection),
        dados,
    )

    return len(dados)


def carregar_csv_na_tabela(
    cursor: Cursor,
    caminho_csv: Path,
    nome_tabela: str,
) -> int:
    """Lê um CSV em blocos e carrega seus registros na tabela Raw."""

    nome_arquivo = caminho_csv.name
    total_inserido = 0
    colunas_tabela = obter_colunas_tabela(cursor, nome_tabela)
    cabecalho_validado = False

    try:
        leitor_chunks = pd.read_csv(
            caminho_csv,
            sep=";",
            encoding=ENCODING_CSV,
            dtype=str,
            chunksize=TAMANHO_CHUNK,
            keep_default_na=False,
        )

        for chunk in leitor_chunks:
            if not cabecalho_validado:
                colunas_csv = chunk.columns.tolist()
                validar_cabecalhos(
                    colunas_csv=colunas_csv,
                    colunas_tabela=colunas_tabela,
                    nome_arquivo=nome_arquivo,
                    nome_tabela=nome_tabela,
                )
                cabecalho_validado = True

            dados = list(chunk.itertuples(index=False, name=None))
            total_inserido += inserir_chunk(
                cursor=cursor,
                nome_tabela=nome_tabela,
                colunas=colunas_tabela,
                dados=dados,
            )
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Falha ao ler o arquivo '{nome_arquivo}' para a tabela "
            f"'{nome_tabela}': encoding inválido ou incompatível."
        ) from exc
    except pd.errors.ParserError as exc:
        raise ValueError(
            f"Falha ao interpretar o arquivo '{nome_arquivo}' para a tabela "
            f"'{nome_tabela}': CSV inválido ou malformado."
        ) from exc
    except psycopg2.Error as exc:
        raise ValueError(
            f"Falha ao inserir dados do arquivo '{nome_arquivo}' na tabela "
            f"'{nome_tabela}': {exc}"
        ) from exc

    if not cabecalho_validado:
        raise ValueError(
            f"O arquivo '{nome_arquivo}' não possui registros para validar "
            f"os cabeçalhos da tabela '{nome_tabela}'."
        )

    return total_inserido


def carregar_tabelas_raw(
    arquivos_validados: dict[str, Path],
) -> dict[str, int]:
    """Carrega os quatro CSVs nas respectivas tabelas Raw."""

    conexao = None
    cursor = None
    registros_carregados: dict[str, int] = {}

    try:
        conexao = conectar()
        cursor = conexao.cursor()
        estrutura_criada = garantir_tabelas_raw(cursor)

        if estrutura_criada:
            conexao.commit()
            print("Estrutura do banco confirmada no PostgreSQL.")

        limpar_tabelas_raw(cursor)

        for nome_arquivo in ORDEM_CARGA:
            nome_tabela = ARQUIVOS_TABELAS[nome_arquivo]
            caminho_csv = arquivos_validados[nome_arquivo]
            print(f"Carregando {nome_arquivo} em {nome_tabela}...")
            registros_carregados[nome_tabela] = carregar_csv_na_tabela(
                cursor=cursor,
                caminho_csv=caminho_csv,
                nome_tabela=nome_tabela,
            )

        conexao.commit()
        return registros_carregados
    except (
        ConnectionError,
        FileNotFoundError,
        PermissionError,
        OSError,
        RuntimeError,
        ValueError,
        psycopg2.Error,
    ):
        if conexao is not None:
            conexao.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()

        if conexao is not None:
            conexao.close()


def executar_download_e_extracao() -> None:
    """Orquestra o download, a extração, a validação e a carga Raw."""

    try:
        configuracao_drive = carregar_configuracao_drive()
        preparar_diretorios()
        caminho_zip = baixar_arquivo_zip(
            drive_file_id=configuracao_drive.file_id,
            caminho_destino=CAMINHO_ARQUIVO_ZIP,
        )
        extrair_arquivo_zip(
            caminho_zip=caminho_zip,
            diretorio_destino=DIRETORIO_EXTRAIDO,
        )
        arquivos_validados = validar_arquivos_csv(DIRETORIO_EXTRAIDO)
        registros_carregados = carregar_tabelas_raw(arquivos_validados)
    except (
        ConnectionError,
        FileNotFoundError,
        PermissionError,
        OSError,
        RuntimeError,
        ValueError,
        UnicodeDecodeError,
        pd.errors.ParserError,
        psycopg2.Error,
        zipfile.BadZipFile,
    ) as exc:
        print(f"Erro durante a execução do pipeline: {exc}")
        raise SystemExit(1) from None

    print("Pipeline de extração concluído com sucesso.\n")
    print("Registros carregados:")
    for nome_tabela in (
        "raw_viagem",
        "raw_pagamento",
        "raw_passagem",
        "raw_trecho",
    ):
        print(f"- {nome_tabela}: {registros_carregados[nome_tabela]}")


if __name__ == "__main__":
    executar_download_e_extracao()
