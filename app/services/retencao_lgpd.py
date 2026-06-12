"""
Serviço de Retenção LGPD.
Gerencia a expiração e limpeza de dados inativos antigos (pacientes e logs de auditoria)
de acordo com limites de tempo configuráveis via variáveis de ambiente.
"""
import os
from datetime import datetime, timedelta
from app.db.models import Paciente, Auditoria, StatusPaciente
from app.services.logger import get_logger

logger = get_logger("lgpd")

# Padrão: 2 anos para inatividade de pacientes, 5 anos para logs de auditoria
RETENCAO_PACIENTES_DIAS = int(os.getenv("RETENCAO_PACIENTES_DIAS", "730"))
RETENCAO_AUDITORIA_DIAS = int(os.getenv("RETENCAO_AUDITORIA_DIAS", "1825"))

def executar_limpeza_lgpd(db) -> dict:
    """
    Executa a exclusão permanente de pacientes inativos há mais de N dias
    e de logs de auditoria gerados há mais de M dias.
    Retorna estatísticas da limpeza executada.
    """
    stats = {"pacientes_removidos": 0, "logs_removidos": 0}
    
    # 1. Limpeza de Pacientes Inativos
    limite_paciente = datetime.now().date() - timedelta(days=RETENCAO_PACIENTES_DIAS)
    try:
        pacientes_expirados = db.query(Paciente).filter(
            Paciente.status == StatusPaciente.INATIVO,
            Paciente.data_desativacao != None,  # noqa: E711
            Paciente.data_desativacao < limite_paciente
        ).all()
        
        for p in pacientes_expirados:
            logger.info(
                f"Remoção LGPD: Paciente '{p.id_paciente}' inativo desde {p.data_desativacao} "
                f"(limite de retenção: {RETENCAO_PACIENTES_DIAS} dias) será excluído permanentemente."
            )
            db.delete(p)
            stats["pacientes_removidos"] += 1
            
        if stats["pacientes_removidos"] > 0:
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao executar limpeza de pacientes inativos antigos (LGPD): {e}", exc_info=True)
        
    # 2. Limpeza de Logs de Auditoria
    limite_auditoria = datetime.now() - timedelta(days=RETENCAO_AUDITORIA_DIAS)
    try:
        logs_expirados_query = db.query(Auditoria).filter(
            Auditoria.quando < limite_auditoria
        )
        stats["logs_removidos"] = logs_expirados_query.count()
        
        if stats["logs_removidos"] > 0:
            logger.info(
                f"Remoção LGPD: {stats['logs_removidos']} logs de auditoria mais antigos que "
                f"{limite_auditoria.strftime('%Y-%m-%d %H:%M:%S')} serão excluídos."
            )
            logs_expirados_query.delete(synchronize_session=False)
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao executar limpeza de logs de auditoria antigos (LGPD): {e}", exc_info=True)
        
    if stats["pacientes_removidos"] > 0 or stats["logs_removidos"] > 0:
        logger.info(
            f"Rotina de Retenção LGPD concluída: {stats['pacientes_removidos']} pacientes "
            f"e {stats['logs_removidos']} logs de auditoria removidos."
        )
        
    return stats
