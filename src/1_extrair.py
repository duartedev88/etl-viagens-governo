"""Download e extração inicial dos arquivos brutos."""

import sys
import zipfile
from pathlib import Path

import gdown
from gdown.exceptions import FileURLRetrievalError
from requests import RequestException

# Inclui a raiz do projeto no caminho de importação quando o script
# é executado diretamente pelo PyCharm ou pelo terminal.
RAIZ_PROJETO = Path(__file__).resolve().parent.parent

if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from src.config import carregar_configuracao_drive


DIRETORIO_RAW = RAIZ_PROJETO / "data" / "raw"
DIRETORIO_EXTRAIDO = RAIZ_PROJETO / "data" / "extracted"
NOME_ARQUIVO_ZIP = "viagens_2025_6meses.zip"
CAMINHO_ARQUIVO_ZIP = DIRETORIO_RAW / NOME_ARQUIVO_ZIP
ARQUIVOS_ESPERADOS = {
    "2025_Viagem.csv",
    "2025_Pagamento.csv",
    "2025_Passagem.csv",
    "2025_Trecho.csv",
}


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


def executar_download_e_extracao() -> None:
    """Orquestra o download, a extração e a validação inicial."""

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
    except (
        ConnectionError,
        FileNotFoundError,
        PermissionError,
        OSError,
        ValueError,
        zipfile.BadZipFile,
    ) as exc:
        print(f"Erro na extração inicial: {exc}")
        raise SystemExit(1) from None

    nomes_arquivos = ", ".join(sorted(arquivos_validados))
    print(f"Download e extração concluídos com sucesso: {nomes_arquivos}")


if __name__ == "__main__":
    executar_download_e_extracao()
