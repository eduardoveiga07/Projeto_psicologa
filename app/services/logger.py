import os
import logging
from logging.handlers import RotatingFileHandler

# Garante o diretório de logs
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

LOG_FILE = os.path.join(LOG_DIR, "tecnico.log")

# Configura o formato do log
formatter = logging.Formatter(
    "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Configura o Logger raiz para a aplicação
logger = logging.getLogger("consultorio_tecnico")
logger.setLevel(logging.INFO)

# Evita duplicação de handlers se reimportado
if not logger.handlers:
    # 1. Handler para gravar em arquivo rotativo (máx 5MB, mantém até 3 arquivos)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)

    # 2. Handler para imprimir no console/stdout (útil para Docker compose logs)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)


def get_logger(name: str):
    """Retorna um logger filho com o namespace correto."""
    return logger.getChild(name)
