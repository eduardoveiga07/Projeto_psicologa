"""Conexao com PostgreSQL. URL via variavel de ambiente DATABASE_URL."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base
from app.services.logger import get_logger

logger = get_logger("db")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://psico:psico@localhost:5432/consultorio")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _migrar_colunas():
    """Adiciona colunas novas que faltam em tabelas ja existentes.
    Evita erro quando o modelo muda sem recriar o banco."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    existentes = {t: {c["name"]: c for c in insp.get_columns(t)}
                  for t in insp.get_table_names()}
    with engine.begin() as conn:
        for tabela in Base.metadata.tables.values():
            if tabela.name not in existentes:
                continue
            for col in tabela.columns:
                if col.name not in existentes[tabela.name]:
                    tipo = col.type.compile(engine.dialect)
                    logger.info(f"Detectada coluna nova: {col.name} na tabela {tabela.name}. Executando migracao...")
                    conn.execute(text(
                        f'ALTER TABLE {tabela.name} '
                        f'ADD COLUMN IF NOT EXISTS {col.name} {tipo}'))
                else:
                    # Amplia VARCHAR se o modelo agora exige mais espaco.
                    novo = getattr(col.type, "length", None)
                    atual = existentes[tabela.name][col.name].get("type")
                    velho = getattr(atual, "length", None)
                    if novo and velho and novo > velho:
                        logger.info(f"Ampliando VARCHAR da coluna {col.name} na tabela {tabela.name} de {velho} para {novo}...")
                        conn.execute(text(
                            f'ALTER TABLE {tabela.name} '
                            f'ALTER COLUMN {col.name} TYPE VARCHAR({novo})'))


def criar_tabelas():
    """Cria tabelas e adiciona colunas faltantes. Espera o Postgres subir."""
    import time
    logger.info("Iniciando a verificacao/criacao das tabelas do banco de dados...")
    for i in range(15):
        try:
            Base.metadata.create_all(engine)
            _migrar_colunas()
            # Drop da constraint antiga de duração fixa (1h)
            try:
                with engine.begin() as conn:
                    conn.exec_driver_sql(
                        "ALTER TABLE agenda_sessoes "
                        "DROP CONSTRAINT IF EXISTS ck_duracao_1h")
            except Exception:
                pass
            logger.info("Banco de dados inicializado e migrado com sucesso.")
            return
        except Exception as e:
            logger.warning(f"Tentativa {i+1}/15 de conexao com o banco falhou. Erro: {e}. Aguardando 2s...")
            time.sleep(2)
    try:
        Base.metadata.create_all(engine)
        _migrar_colunas()
        logger.info("Banco de dados inicializado e migrado com sucesso apos tentativas de fallback.")
    except Exception as e:
        logger.critical(f"Erro critico: Nao foi possivel conectar ao banco de dados apos 15 tentativas. Detalhes: {e}", exc_info=True)
        raise e


def get_session():
    return SessionLocal()


if __name__ == "__main__":
    criar_tabelas()
    print("Tabelas criadas:", list(Base.metadata.tables))
