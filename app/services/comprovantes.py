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
from datetime import datetime

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

    # Valida extensão
    _, ext = os.path.splitext(uploaded_file.name.lower())
    if ext not in EXTENSOES_PERMITIDAS:
        raise ComprovantesError(
            f"Tipo de arquivo não permitido: '{ext}'. "
            f"Aceitos: PDF, PNG, JPG/JPEG."
        )

    # Valida tamanho
    dados = uploaded_file.getbuffer()
    tamanho = len(dados)
    if tamanho > TAMANHO_MAXIMO_BYTES:
        mb = tamanho / (1024 * 1024)
        raise ComprovantesError(
            f"Arquivo muito grande: {mb:.1f} MB. Limite máximo: 10 MB."
        )

    if tamanho == 0:
        raise ComprovantesError("Arquivo enviado está vazio.")


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

    # Constrói nome interno seguro: tipo_id_timestamp_nome-original-sanitizado.ext
    _, ext = os.path.splitext(uploaded_file.name.lower())
    timestamp = int(datetime.now().timestamp())
    nome_sanitizado = _sanitizar_nome(uploaded_file.name)
    nome_arquivo = f"{tipo}_{registro_id}_{timestamp}_{nome_sanitizado}"
    caminho_completo = os.path.join(UPLOAD_DIR, nome_arquivo)

    dados = uploaded_file.getbuffer()
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
        except Exception:
            pass
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
