import os
import logging
from logging.handlers import RotatingFileHandler

import re

class SegredosMaskFilter(logging.Filter):
    def filter(self, record):
        if record.msg:
            if isinstance(record.msg, str):
                record.msg = self.mascarar(record.msg)
            else:
                try:
                    record.msg = self.mascarar(str(record.msg))
                except Exception:
                    record.msg = "<mensagem_nao_conversivel>"
        if record.args:
            novos_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    novos_args.append(self.mascarar(arg))
                else:
                    novos_args.append(arg)
            record.args = tuple(novos_args)
        return True

    def mascarar(self, texto: str) -> str:
        # 1. Mascara senhas em URIs do banco de dados (ex: postgresql+psycopg2://user:pass@host...)
        texto = re.sub(
            r"(postgresql(?:\+[a-zA-Z0-9_-]+)?://[^:]+:)([^@\s]+)(@[^\s]+)",
            r"\1***\3",
            texto
        )
        # 2. Mascara termos sensíveis como senha=, password=, key=, token=, etc.
        texto = re.sub(
            r"([pP]assword|[sS]enha|[tT]oken|[kK]ey|[sS]ecret)\s*[:=]\s*['\"]?[^\s'\",;]+['\"]?",
            r"\1=***",
            texto
        )
        return texto

# Configura o formato do log
formatter = logging.Formatter(
    "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Configura o Logger raiz para a aplicação
logger = logging.getLogger("consultorio_tecnico")
logger.setLevel(logging.INFO)
logger.addFilter(SegredosMaskFilter())

# Evita duplicação de handlers se reimportado
if not logger.handlers:
    # 1. Handler para gravar em arquivo rotativo (máx 5MB, mantém até 3 arquivos)
    # Em ambientes com sistema de arquivos read-only (ex: Streamlit Cloud),
    # o log em arquivo é desativado automaticamente e apenas o console é usado.
    try:
        LOG_DIR = "logs"
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
        LOG_FILE = os.path.join(LOG_DIR, "tecnico.log")
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)
        logger.addHandler(file_handler)
    except (OSError, PermissionError):
        pass  # Sistema de arquivos somente leitura (ex: Streamlit Cloud) — usa só console

    # 2. Handler para imprimir no console/stdout (útil para Docker compose logs e Streamlit Cloud)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)


def get_logger(name: str):
    """Retorna um logger filho com o namespace correto."""
    return logger.getChild(name)
