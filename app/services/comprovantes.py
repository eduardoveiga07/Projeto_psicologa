"""Serviço de gerenciamento de arquivos de comprovante.

Responsabilidades:
- Validação de tipo MIME e extensão
- Validação de tamanho máximo (10 MB por padrão)
- Sanitização do nome de arquivo
- Persistência local em uploads/comprovantes/
- Retorno de metadados completos para banco de dados

# Contratos estáveis (não mudam ao trocar o storage):

    salvar_comprovante(uploaded_file, tipo, registro_id) -> dict | None
        Retorna sempre um dict com as chaves:
            "nome"          — nome interno único (usado no banco)
            "nome_original" — nome original enviado pelo usuário
            "mime"          — tipo MIME (ex: "application/pdf")
            "tamanho"       — tamanho em bytes (int)
            "enviado_em"    — datetime do upload

    obter_comprovante_caminho(nome_arquivo) -> str | None
        Retorna o caminho absoluto para leitura interna.
        NUNCA exponha este valor na interface do usuário.

    deletar_comprovante(nome_arquivo) -> bool
        Remove o arquivo do storage. Retorna True se removido.

    aplicar_metadados_comprovante(registro, metadados) -> None
    limpar_metadados_comprovante(registro) -> None
        Helpers para aplicar/apagar os 5 campos de metadados em um objeto ORM.

# Limitação atual — filesystem efêmero no Streamlit Cloud:

    O Streamlit Cloud pode reiniciar o servidor a qualquer momento, apagando
    tudo em uploads/comprovantes/. Os METADADOS permanecem seguros no banco
    PostgreSQL, mas o arquivo físico pode desaparecer.

    A UI trata esse caso com fallback gracioso ("⚠️ Arquivo ausente") sem
    quebrar o sistema.

# ─────────────────────────────────────────────────────────────────
# TODO TÉCNICO — Migração para storage externo em produção
# ─────────────────────────────────────────────────────────────────
#
# Quando o sistema for para produção definitiva (ou enquanto rodar no
# Streamlit Cloud), substituir SOMENTE a função `salvar_comprovante`
# por uma implementação de storage externo. O restante do código
# (telas, ORM, auditoria) não precisa ser alterado.
#
# Opções recomendadas:
#
#   1. Supabase Storage (mais simples, já oferece PostgreSQL)
#      - pip install supabase
#      - bucket: "comprovantes"
#      - URL pública controlada por policies (RLS)
#      - Implementar: salvar → supabase.storage.from_("comprovantes").upload(...)
#
#   2. Amazon S3 / Cloudflare R2
#      - pip install boto3
#      - bucket privado + URL assinada com expiração (ex: 15 min)
#      - Implementar: salvar → s3.put_object(...); download → s3.generate_presigned_url(...)
#
#   3. Google Drive API
#      - pip install google-api-python-client google-auth
#      - Pasta compartilhada somente com a conta da profissional
#      - Implementar: salvar → drive.files().create(...)
#
# Regras que devem ser mantidas independente do storage escolhido:
#   ✔ Metadados (nome, mime, tamanho, enviado_em) permanecem no banco PostgreSQL
#   ✔ Caminho/URL absoluta nunca é exposta diretamente na interface
#   ✔ Download sempre controlado por usuário autenticado
#   ✔ Fallback gracioso quando arquivo não existe ("⚠️ Arquivo ausente")
#   ✔ Auditoria registrada ao anexar e ao remover (COMPROVANTE_ANEXADO/REMOVIDO)
#   ✔ Arquivos dos pacientes são dados pessoais/financeiros — conformidade LGPD obrigatória
#   ✔ uploads/ permanece no .gitignore (nunca versionar arquivos de pacientes)
# ─────────────────────────────────────────────────────────────────
"""
import os
import re
import unicodedata
import uuid
from datetime import datetime
from app.services.logger import get_logger

logger = get_logger("comprovantes")

# Diretório base para armazenamento local
UPLOAD_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "comprovantes")
)

# Limite máximo de tamanho de arquivo (10 MB)
TAMANHO_MAXIMO_BYTES = 10 * 1024 * 1024

# Extensões e MIME types permitidos
EXTENSOES_PERMITIDAS = {".pdf", ".png", ".jpg", ".jpeg"}
MIME_TYPES_PERMITIDOS = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class ComprovantesError(Exception):
    """Erro de validação de comprovante, com mensagem em português para o usuário."""
    pass


def _sanitizar_nome(nome: str) -> str:
    """Remove caracteres especiais e espaços do nome de arquivo, preservando a extensão."""
    nome_sem_ext, ext = os.path.splitext(nome)
    # Normaliza unicode (ã -> a, etc.)
    nfd = unicodedata.normalize("NFD", nome_sem_ext)
    apenas_ascii = nfd.encode("ascii", "ignore").decode("ascii")
    # Remove tudo que não for alfanumérico, hífen ou underscore
    limpo = re.sub(r"[^\w\-]", "_", apenas_ascii).strip("_")
    limpo = re.sub(r"_+", "_", limpo)  # colapsa múltiplos underscores
    return (limpo[:60] or "arquivo") + ext.lower()


def validar_upload(uploaded_file) -> None:
    """Valida tipo e tamanho do arquivo. Lança ComprovantesError se inválido.

    Args:
        uploaded_file: objeto st.file_uploader retornado pelo Streamlit.

    Raises:
        ComprovantesError: se o arquivo não passar nas validações.
    """
    if not uploaded_file:
        return

    # 1. Valida tamanho do arquivo antes de ler os magic bytes (prevenção DoS)
    try:
        dados = uploaded_file.getbuffer()
    except AttributeError:
        # Fallback caso seja um file-like object genérico nos testes
        dados = uploaded_file.read() if hasattr(uploaded_file, "read") else b""
        
    tamanho = len(dados)
    if tamanho > TAMANHO_MAXIMO_BYTES:
        mb = tamanho / (1024 * 1024)
        raise ComprovantesError(
            f"Arquivo muito grande: {mb:.1f} MB. Limite máximo: 10 MB."
        )

    if tamanho == 0:
        raise ComprovantesError("Arquivo enviado está vazio.")

    # 2. Valida extensão
    _, ext = os.path.splitext(uploaded_file.name.lower())
    if ext not in EXTENSOES_PERMITIDAS:
        raise ComprovantesError(
            f"Tipo de arquivo não permitido: '{ext}'. "
            f"Aceitos: PDF, PNG, JPG/JPEG."
        )

    # 3. Valida MIME informado pelo navegador (Streamlit UploadedFile.type)
    if hasattr(uploaded_file, "type") and uploaded_file.type:
        mime_enviado = uploaded_file.type.lower()
        mime_esperado = MIME_TYPES_PERMITIDOS.get(ext)
        if mime_esperado and mime_enviado != mime_esperado:
            # Tolerância para JPG/JPEG com image/jpg vs image/jpeg
            if not (ext in {".jpg", ".jpeg"} and mime_enviado in {"image/jpeg", "image/jpg"}):
                raise ComprovantesError(
                    f"MIME type informado '{mime_enviado}' incompatível com a extensão '{ext}'."
                )

    # 4. Valida assinatura do arquivo (Magic Bytes)
    header = bytes(dados[:8])
    if ext == ".pdf" and not header.startswith(b"%PDF"):
        raise ComprovantesError("Assinatura de arquivo PDF inválida.")
    elif ext == ".png" and not header.startswith(b"\x89PNG"):
        raise ComprovantesError("Assinatura de arquivo PNG inválida.")
    elif ext in {".jpg", ".jpeg"} and not header.startswith(b"\xff\xd8\xff"):
        raise ComprovantesError("Assinatura de arquivo JPEG/JPG inválida.")


def salvar_comprovante(uploaded_file, tipo: str, registro_id: int) -> dict:
    """Salva o arquivo de comprovante e retorna dicionário de metadados.

    Args:
        uploaded_file: objeto st.file_uploader do Streamlit.
        tipo: 'despesa' ou 'sessao'.
        registro_id: ID do registro associado (int).

    Returns:
        dict com chaves: nome, nome_original, mime, tamanho, enviado_em

    Raises:
        ComprovantesError: se validação falhar.
    """
    if not uploaded_file:
        return None

    # Validação antes de qualquer I/O
    validar_upload(uploaded_file)

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Constrói nome interno seguro: tipo_id_timestamp_uuid_nome-original-sanitizado.ext
    _, ext = os.path.splitext(uploaded_file.name.lower())
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    uuid_part = uuid.uuid4().hex[:8]
    nome_sanitizado = _sanitizar_nome(uploaded_file.name)
    nome_arquivo = f"{tipo}_{registro_id}_{timestamp}_{uuid_part}_{nome_sanitizado}"
    caminho_completo = os.path.join(UPLOAD_DIR, nome_arquivo)

    try:
        dados = uploaded_file.getbuffer()
    except AttributeError:
        dados = uploaded_file.read() if hasattr(uploaded_file, "read") else b""

    with open(caminho_completo, "wb") as f:
        f.write(dados)

    return {
        "nome": nome_arquivo,
        "nome_original": uploaded_file.name[:300],
        "mime": MIME_TYPES_PERMITIDOS.get(ext, "application/octet-stream"),
        "tamanho": len(dados),
        "enviado_em": datetime.now(),
    }


def obter_comprovante_caminho(nome_arquivo: str) -> str:
    """Retorna o caminho absoluto de um arquivo de comprovante.

    Nunca expõe o caminho ao usuário final — apenas usado internamente para
    leitura do arquivo para download.
    """
    if not nome_arquivo:
        return None
    return os.path.join(UPLOAD_DIR, nome_arquivo)


def ler_comprovante(nome_arquivo: str) -> bytes | None:
    """Lê e retorna o conteúdo do comprovante como bytes.

    Retorna None se o arquivo não existir ou se houver erro ao ler.
    """
    if not nome_arquivo:
        return None
    caminho = obter_comprovante_caminho(nome_arquivo)
    if caminho and os.path.exists(caminho):
        try:
            with open(caminho, "rb") as f:
                return f.read()
        except OSError as e:
            logger.error(f"Erro ao ler comprovante '{nome_arquivo}' do disco: {e}", exc_info=True)
    return None


def existe_comprovante(nome_arquivo: str) -> bool:
    """Retorna True se o arquivo do comprovante existe fisicamente no storage."""
    if not nome_arquivo:
        return False
    caminho = obter_comprovante_caminho(nome_arquivo)
    return bool(caminho and os.path.exists(caminho))


def obter_comprovante_url(nome_arquivo: str) -> str | None:
    """Retorna a URL pública do comprovante para download.

    No storage local não geramos URL porque o Streamlit não serve arquivos estáticos
    arbitrários por padrão; quando migrar para S3/Supabase, esta função retornará
    a URL pré-assinada (pre-signed URL) temporária com TTL correspondente.
    """
    return None


def deletar_comprovante(nome_arquivo: str) -> bool:
    """Remove o arquivo de comprovante do disco se ele existir.

    Returns:
        True se o arquivo foi removido, False se não existia.
    """
    if not nome_arquivo:
        return False
    caminho = obter_comprovante_caminho(nome_arquivo)
    if caminho and os.path.exists(caminho):
        try:
            os.remove(caminho)
            return True
        except FileNotFoundError:
            return False
        except OSError as e:
            logger.error(f"Erro de permissão ou de E/S ao tentar remover o arquivo '{nome_arquivo}': {e}", exc_info=True)
    return False


def aplicar_metadados_comprovante(registro, metadados: dict) -> None:
    """Aplica o dicionário de metadados de comprovante nos atributos do registro ORM.

    Args:
        registro: instância ORM de Despesa ou AgendaSessao.
        metadados: dict retornado por salvar_comprovante().
    """
    if not metadados:
        return
    registro.comprovante_nome = metadados["nome"]
    registro.comprovante_nome_original = metadados["nome_original"]
    registro.comprovante_mime = metadados["mime"]
    registro.comprovante_tamanho = metadados["tamanho"]
    registro.comprovante_enviado_em = metadados["enviado_em"]


def limpar_metadados_comprovante(registro) -> None:
    """Apaga todos os campos de metadados de comprovante do registro ORM."""
    registro.comprovante_nome = None
    registro.comprovante_nome_original = None
    registro.comprovante_mime = None
    registro.comprovante_tamanho = None
    registro.comprovante_enviado_em = None
