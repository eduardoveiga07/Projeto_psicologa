"""Motor financeiro: previsto vs realizado, DRE simplificado."""
from decimal import Decimal
from datetime import datetime
from sqlalchemy import func, extract
from app.db.models import (Paciente, AgendaSessao, Despesa,
                           StatusPaciente, StatusPresenca, Frequencia)
from app.services.calendario import sessoes_previstas


def previsto_paciente(p: Paciente, ano: int, mes: int) -> dict:
    """Previsao de sessoes e faturamento de UM paciente no mes."""
    if p.frequencia == Frequencia.PERSONALIZADO and p.sessoes_mes_custom:
        n = p.sessoes_mes_custom
    else:
        n = sessoes_previstas(ano, mes, p.dia_atendimento, p.frequencia)
    return {"paciente": p.nome, "sessoes_previstas": n,
            "faturamento_previsto": Decimal(n) * p.valor_sessao}


def realizado_paciente(db, p: Paciente, ano: int, mes: int) -> dict:
    """Sessoes realizadas (status Realizada) de UM paciente no mes."""
    n = db.query(func.count(AgendaSessao.id_sessao)).filter(
        AgendaSessao.id_paciente == p.id_paciente,
        AgendaSessao.status_presenca == StatusPresenca.REALIZADA,
        extract("year", AgendaSessao.data_hora_inicio) == ano,
        extract("month", AgendaSessao.data_hora_inicio) == mes,
    ).scalar() or 0
    return {"paciente": p.nome, "sessoes_realizadas": n,
            "faturamento_realizado": Decimal(n) * p.valor_sessao}


def consolidado_mes(db, ano: int, mes: int) -> dict:
    """Visao da planilha: previsto e realizado de todos os pacientes ativos + DRE."""
    ativos = db.query(Paciente).filter(
        Paciente.status == StatusPaciente.ATIVO).all()

    linhas, fat_prev, fat_real = [], Decimal(0), Decimal(0)
    for p in ativos:
        pv = previsto_paciente(p, ano, mes)
        rl = realizado_paciente(db, p, ano, mes)
        fat_prev += pv["faturamento_previsto"]
        fat_real += rl["faturamento_realizado"]
        linhas.append({
            "paciente": p.nome,
            "sessoes_previstas": pv["sessoes_previstas"],
            "faturamento_previsto": pv["faturamento_previsto"],
            "sessoes_realizadas": rl["sessoes_realizadas"],
            "faturamento_realizado": rl["faturamento_realizado"],
        })

    mes_ref = f"{ano:04d}-{mes:02d}"
    despesas = db.query(func.coalesce(func.sum(Despesa.valor), 0)).filter(
        Despesa.mes_referencia == mes_ref).scalar() or Decimal(0)
    despesas = Decimal(despesas)

    return {
        "mes_ano": mes_ref,
        "linhas": linhas,
        "faturamento_previsto": fat_prev,
        "faturamento_realizado": fat_real,
        "total_despesas": despesas,
        "lucro_liquido": fat_real - despesas,  # DRE simplificado
    }
