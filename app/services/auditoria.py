"""Trilha de auditoria. Registra eventos criticos sem dados sensiveis."""
from app.db.models import Auditoria


def registrar(db, usuario: str, acao: str, detalhe: str = "", ip: str = ""):
    """Grava um evento. 'detalhe' NUNCA deve conter nome/telefone de paciente."""
    try:
        db.add(Auditoria(usuario=usuario or "?", acao=acao,
                         detalhe=detalhe[:300], ip=ip or "?"))
        db.commit()
    except Exception:
        db.rollback()  # auditoria nunca pode derrubar a operacao principal
