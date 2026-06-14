import os
import json
import time
from datetime import datetime
from cryptography.fernet import Fernet
from app.services.logger import get_logger
from app.db.models import Perfil

logger = get_logger("auth_sessao")


def _obter_session_secret_key() -> str:
    """
    Resolve a SESSION_SECRET_KEY de acordo com a política de ambientes:
    - Em produção: exige a definição da variável de ambiente, abortando se ausente.
    - Em desenvolvimento: gera e persiste localmente em '.session_key.local'.
    """
    ambiente = os.getenv("AMBIENTE", "desenvolvimento").lower()

    if ambiente == "producao":
        # Em produção, prioriza st.secrets (Streamlit Cloud) e depois variáveis de ambiente
        url_secret = None
        try:
            import streamlit as st
            url_secret = st.secrets.get("SESSION_SECRET_KEY")
        except Exception:
            pass

        key = url_secret or os.getenv("SESSION_SECRET_KEY")
        if not key:
            raise RuntimeError(
                "SESSION_SECRET_KEY não definida em produção. "
                "Defina nos Secrets do Streamlit Cloud antes de subir."
            )
        return key
    else:
        # Em desenvolvimento, tenta ler do arquivo local .session_key.local
        file_path = ".session_key.local"
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    key = f.read().strip()
                    if key:
                        return key
            except Exception as e:
                logger.error(f"Erro ao ler .session_key.local: {e}")

        # Se não existe ou deu erro, gera uma nova chave e salva
        new_key = Fernet.generate_key().decode()
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_key)
            logger.warning(
                "SESSION_SECRET_KEY ausente. Gerada chave de desenvolvimento "
                "em .session_key.local — NÃO USE EM PRODUÇÃO."
            )
        except Exception as e:
            logger.error(f"Erro ao salvar nova chave em .session_key.local: {e}")

        return new_key


# Carrega a chave e inicializa o Fernet no boot
SESSION_SECRET_KEY = _obter_session_secret_key()
fernet_inst = Fernet(SESSION_SECRET_KEY.encode())


def _obter_timeout_seconds() -> int:
    """Retorna o tempo limite da sessão em segundos (padrão 30 minutos)."""
    try:
        minutes = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))
    except ValueError:
        minutes = 30
    return minutes * 60


def criar_token_sessao(usuario_id: str, username: str, perfil: Perfil) -> str:
    """
    Gera um token de sessão criptografado contendo o payload do usuário.
    """
    timeout = _obter_timeout_seconds()
    now = time.time()

    payload = {
        "usuario_id": str(usuario_id),
        "username": username,
        "perfil": perfil.value if isinstance(perfil, Perfil) else str(perfil),
        "criado_em": now,
        "expira_em": now + timeout
    }

    payload_json = json.dumps(payload)
    token = fernet_inst.encrypt(payload_json.encode()).decode()
    return token


def validar_token(token: str) -> dict | None:
    """
    Descriptografa, valida o formato e a expiração do token de sessão.
    Tratamento defensivo de erros: retorna None em qualquer falha de validação ou parsing.
    """
    if not token:
        return None

    try:
        # Descriptografa sem passar o parâmetro ttl (validação manual de expira_em)
        payload_bytes = fernet_inst.decrypt(token.encode())
        payload = json.loads(payload_bytes.decode("utf-8"))

        # Verifica campos esperados
        required_keys = ["usuario_id", "username", "perfil", "criado_em", "expira_em"]
        for key in required_keys:
            if key not in payload:
                logger.warning(f"Token inválido: campo ausente '{key}'")
                return None

        # Verifica expiração no payload
        if time.time() > payload["expira_em"]:
            logger.info(f"Token expirado para o usuário '{payload['username']}'")
            return None

        # Converte o perfil (string) para o Enum Perfil correspondente
        perfil_str = payload["perfil"]
        try:
            payload["perfil"] = Perfil(perfil_str)
        except ValueError:
            logger.warning(f"Perfil inválido '{perfil_str}' no token")
            return None

        return payload
    except Exception as e:
        # Captura qualquer falha de criptografia (InvalidToken), json malformado, etc.
        logger.debug(f"Falha na validação do token: {e}")
        return None


def renovar_token(payload: dict) -> str:
    """
    Emite um novo token baseado no payload descriptografado anterior.
    """
    timeout = _obter_timeout_seconds()
    now = time.time()

    perfil = payload["perfil"]
    perfil_val = perfil.value if isinstance(perfil, Perfil) else str(perfil)

    novo_payload = {
        "usuario_id": payload["usuario_id"],
        "username": payload["username"],
        "perfil": perfil_val,
        "criado_em": now,
        "expira_em": now + timeout
    }

    payload_json = json.dumps(novo_payload)
    token = fernet_inst.encrypt(payload_json.encode()).decode()
    return token
