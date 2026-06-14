from app.services.logger import get_logger

logger = get_logger("auditoria")


def registrar(db, usuario: str, acao: str, detalhe: str = "", ip: str = ""):
    """Grava um evento. 'detalhe' NUNCA deve conter nome/telefone de paciente."""
    try:
        db.add(Auditoria(usuario=usuario or "?", acao=acao,
                         detalhe=detalhe[:300], ip=ip or "?"))
        db.commit()
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.error(f"Falha ao salvar log de auditoria (usuario={usuario}, acao={acao}): {e}", exc_info=True)
