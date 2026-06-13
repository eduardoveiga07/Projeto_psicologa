"""Serviço de detecção e agregação de notificações/alertas internos do consultório."""
from datetime import datetime, timedelta
from app.db.models import Paciente, AgendaSessao, StatusPresenca, StatusPagamento, SistemaStatus, StatusPaciente, Perfil
from sqlalchemy import func


def obter_notificacoes(db) -> list:
    """Busca pendências críticas no banco de dados e retorna uma lista de dicionários formatados para o usuário."""
    notifs = []
    agora_dt = datetime.now()

    # 1. Erro técnico recente (últimos 3 dias)
    tres_dias_atras = agora_dt - timedelta(days=3)
    try:
        erros = db.query(SistemaStatus).filter(
            SistemaStatus.status == "falha",
            SistemaStatus.quando >= tres_dias_atras
        ).order_by(SistemaStatus.quando.desc()).all()
        for err in erros:
            notifs.append({
                "tipo": "erro_tecnico",
                "icone": "🔴",
                "titulo": f"Falha técnica recente ({err.tipo})",
                "detalhe": f"Em {err.quando.strftime('%d/%m %H:%M')}: {err.detalhe[:100]}",
                "nivel": "danger"
            })
    except Exception:
        pass

    # 2. Backup atrasado (> 28 horas)
    limite_backup = agora_dt - timedelta(hours=28)
    try:
        ultimo_backup = db.query(SistemaStatus).filter(
            SistemaStatus.tipo == "backup",
            SistemaStatus.status == "sucesso"
        ).order_by(SistemaStatus.quando.desc()).first()
        if not ultimo_backup or ultimo_backup.quando < limite_backup:
            det = f"Último em: {ultimo_backup.quando.strftime('%d/%m %H:%M')}" if ultimo_backup else "Nenhum backup realizado ainda."
            notifs.append({
                "tipo": "backup_atrasado",
                "icone": "⚠️",
                "titulo": "Backup diário atrasado",
                "detalhe": det,
                "nivel": "warning"
            })
    except Exception:
        pass

    # 3. Contrato sem horário ou sem contrato (para pacientes ativos)
    try:
        ativos = db.query(Paciente).filter(Paciente.status == StatusPaciente.ATIVO).all()
        for p in ativos:
            if not p.horario_atendimento or not p.dias_semana:
                notifs.append({
                    "tipo": "paciente_sem_horario",
                    "icone": "👤",
                    "titulo": f"Paciente sem horário fixo: {p.nome}",
                    "detalhe": "Cadastrado como ativo mas sem horário de atendimento configurado.",
                    "nivel": "info"
                })
    except Exception:
        pass

    # 4. Sessões sem pagamento (realizadas/cancelou em cima mas pendentes/atrasadas)
    try:
        sessoes_abertas = db.query(AgendaSessao).filter(
            AgendaSessao.data_hora_inicio < agora_dt,
            AgendaSessao.status_presenca.in_([StatusPresenca.REALIZADA, StatusPresenca.CANCELOU_EM_CIMA]),
            AgendaSessao.status_pagamento.in_([StatusPagamento.PENDENTE, StatusPagamento.ATRASADO])
        ).all()
        if sessoes_abertas:
            notifs.append({
                "tipo": "sessoes_sem_pagamento",
                "icone": "💸",
                "titulo": f"Sessões pendentes de pagamento ({len(sessoes_abertas)})",
                "detalhe": f"Existem {len(sessoes_abertas)} sessões passadas que constam como pendentes/atrasadas.",
                "nivel": "warning"
            })
    except Exception:
        pass

    return notifs
