"""Conexao com PostgreSQL. URL via variavel de ambiente DATABASE_URL ou st.secrets."""
import os
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker
from app.db.models import Base
from app.services.logger import get_logger

logger = get_logger("db")

def _get_database_url() -> str:
    """Resolve a DATABASE_URL priorizando st.secrets (Streamlit Cloud)
    e caindo em variável de ambiente como fallback (Docker/local)."""
    try:
        import streamlit as st
        # st.secrets pode lançar FileNotFoundError ou KeyError fora do Streamlit
        url = st.secrets.get("DATABASE_URL", None)
        if url:
            return url
    except (ImportError, FileNotFoundError, KeyError, AttributeError):
        pass
    return os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://psico:psico@localhost:5432/consultorio")

DATABASE_URL = _get_database_url()
engine = create_engine(DATABASE_URL, pool_pre_ping=True, poolclass=NullPool)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def criar_tabelas():
    """Executa a conexão e roda migrações do Alembic programaticamente no boot."""
    import time
    from sqlalchemy import text
    
    # 1. Loop de verificação de conexão com retry (para desenvolvimento/docker local)
    conexao_ok = False
    for i in range(15):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            conexao_ok = True
            break
        except Exception as e:
            logger.warning(f"Tentativa {i+1}/15 de conexao com o banco falhou. Erro: {e}. Aguardando 2s...")
            time.sleep(2)
            
    if not conexao_ok:
        logger.critical("Erro crítico: Não foi possível conectar ao banco de dados após 15 tentativas.")
        raise ConnectionError("Banco de dados indisponível.")

    # 2. Execução das migrações do Alembic no boot
    ambiente = os.getenv("AMBIENTE", "desenvolvimento").lower()
    try:
        logger.info("Executando migrações do Alembic (alembic upgrade head)...")
        from alembic.config import Config
        from alembic import command
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Migrações do Alembic aplicadas com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao rodar migrações do Alembic: {e}", exc_info=True)
        if ambiente == "producao":
            logger.critical("Erro crítico em PRODUCAO: Alembic falhou. Interrompendo boot do app.")
            raise e
        else:
            logger.warning("Ambiente de desenvolvimento. Continuando boot apesar da falha de migração...")


def get_session():
    return SessionLocal()


if __name__ == "__main__":
    criar_tabelas()
    print("Tabelas criadas:", list(Base.metadata.tables))
