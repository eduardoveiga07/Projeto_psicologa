"""Motor financeiro: previsto vs realizado, DRE simplificado."""
from decimal import Decimal
from datetime import datetime, date
from sqlalchemy import func, extract
from app.db.models import (Paciente, AgendaSessao, Despesa,
                           StatusPaciente, StatusPresenca, Frequencia, StatusPagamento)
from app.services.calendario import sessoes_previstas, sessoes_previstas_lista
from app.services.contrato import snapshot_vigente


def previsto_paciente(p: Paciente, ano: int, mes: int,
                      bloqueadas: set = None, db=None,
                      historico=None, pontuais=None) -> dict:
    """Previsao de sessoes e faturamento de UM paciente no mes.
    Sob a arquitetura de sessões físicas, consulta diretamente o banco de dados
    para somar as sessões agendadas/realizadas do mês."""
    from decimal import Decimal
    from datetime import date, time, datetime
    import calendar
    from app.db.models import Frequencia, AgendaSessao, StatusPresenca, StatusPagamento, ContratoHistorico
    from app.services.contrato import snapshot_vigente_em_memoria

    if db is None:
        return _previsto_legado(p, ano, mes, bloqueadas)

    # Carrega todo o histórico de contratos do paciente de uma vez se não vier na chamada
    if historico is None:
        historico = db.query(ContratoHistorico).filter(
            ContratoHistorico.id_paciente == p.id_paciente
        ).order_by(ContratoHistorico.vigente_de.desc()).all()

    fim_mes = date(ano, mes, calendar.monthrange(ano, mes)[1])
    snap_fim = snapshot_vigente_em_memoria(historico, fim_mes)

    # 1. Se for PERSONALIZADO, usa a regra de quantidade fixa do contrato
    if snap_fim and snap_fim.frequencia == Frequencia.PERSONALIZADO:
        n = snap_fim.sessoes_mes_custom or 0
        fat = Decimal(n) * snap_fim.valor_sessao
        return {"paciente": p.nome, "sessoes_previstas": n,
                "faturamento_previsto": fat}

    # 2. Caso contrário, busca as sessões físicas do paciente no mês
    inicio_mes = datetime.combine(date(ano, mes, 1), time.min)
    fim_mes_dt = datetime.combine(fim_mes, time.max)

    # Sessões válidas para o previsto: tudo exceto CANCELADA (por feriado/bloqueio) e ISENTO (ex: cancelamento >24h)
    sessoes_mes = db.query(AgendaSessao).filter(
        AgendaSessao.id_paciente == p.id_paciente,
        AgendaSessao.data_hora_inicio >= inicio_mes,
        AgendaSessao.data_hora_inicio <= fim_mes_dt,
        AgendaSessao.status_presenca != StatusPresenca.CANCELADA,
        AgendaSessao.status_presenca != StatusPresenca.CANCELOU_COM_ANTECEDENCIA,
        AgendaSessao.status_presenca != StatusPresenca.IMPREVISTO,
        AgendaSessao.status_pagamento != StatusPagamento.ISENTO
    ).all()

    n = len(sessoes_mes)
    fat = Decimal(0)
    for s in sessoes_mes:
        if s.valor_sessao is not None:
            fat += s.valor_sessao
        else:
            snap = snapshot_vigente_em_memoria(historico, s.data_hora_inicio.date())
            fat += (snap.valor_sessao if snap else p.valor_sessao)

    return {"paciente": p.nome, "sessoes_previstas": n,
            "faturamento_previsto": fat}


def _previsto_legado(p, ano, mes, bloqueadas):
    """Fallback sem historico (compatibilidade quando db=None)."""
    import calendar
    from app.services.calendario import sessoes_previstas_lista
    if p.frequencia == Frequencia.PERSONALIZADO and p.sessoes_mes_custom:
        n = p.sessoes_mes_custom
    else:
        dias = (p.dias_semana.split(",") if p.dias_semana
                else [p.dia_atendimento.value] if p.dia_atendimento else [])
        n = sessoes_previstas_lista(ano, mes, dias, p.frequencia, bloqueadas)
    return {"paciente": p.nome, "sessoes_previstas": n,
            "faturamento_previsto": Decimal(n) * p.valor_sessao}


def realizado_paciente(db, p: Paciente, ano: int, mes: int,
                       historico=None, sessoes=None) -> dict:
    """Sessoes que geram receita: Realizada ou Cancelou -24h (cobra).
    Cada sessao eh valorada pelo valor_sessao físico registrado nela,
    caindo de volta para o snapshot de contrato caso seja nulo."""
    from decimal import Decimal
    from datetime import date, time, datetime
    import calendar
    from app.db.models import AgendaSessao, StatusPresenca, StatusPagamento, ContratoHistorico
    from app.services.contrato import snapshot_vigente_em_memoria

    if sessoes is None:
        inicio_mes = datetime.combine(date(ano, mes, 1), time.min)
        fim_mes = datetime.combine(date(ano, mes, calendar.monthrange(ano, mes)[1]), time.max)
        sessoes = db.query(AgendaSessao).filter(
            AgendaSessao.id_paciente == p.id_paciente,
            AgendaSessao.status_presenca.in_([
                StatusPresenca.REALIZADA,
                StatusPresenca.CANCELOU_EM_CIMA]),
            AgendaSessao.data_hora_inicio >= inicio_mes,
            AgendaSessao.data_hora_inicio <= fim_mes
        ).all()

    if historico is None:
        historico = db.query(ContratoHistorico).filter(
            ContratoHistorico.id_paciente == p.id_paciente
        ).order_by(ContratoHistorico.vigente_de.desc()).all()

    fat = Decimal(0)
    inad = Decimal(0)
    for s in sessoes:
        if s.valor_sessao is not None:
            valor = s.valor_sessao
        else:
            snap = snapshot_vigente_em_memoria(historico, s.data_hora_inicio.date())
            valor = (snap.valor_sessao if snap else p.valor_sessao)
        fat += valor
        if s.status_pagamento in [StatusPagamento.PENDENTE, StatusPagamento.ATRASADO]:
            inad += valor

    return {"paciente": p.nome, "sessoes_realizadas": len(sessoes),
            "faturamento_realizado": fat, "inadimplencia": inad}


def consolidado_mes(db, ano: int, mes: int) -> dict:
    """Visao da planilha: previsto e realizado de todos os pacientes ativos + DRE.
    Incorpora faturamento inadimplente."""
    from app.services.indisponibilidade import datas_dia_todo
    from app.db.models import ContratoHistorico, AgendaSessao, StatusPresenca
    
    bloq = datas_dia_todo(db, ano, mes)
    ativos = db.query(Paciente).filter(
        Paciente.status == StatusPaciente.ATIVO).all()

    p_ids = [p.id_paciente for p in ativos]
    if p_ids:
        # Pre-fetch ContratoHistorico for all active patients
        contratos_db = db.query(ContratoHistorico).filter(
            ContratoHistorico.id_paciente.in_(p_ids)
        ).order_by(ContratoHistorico.vigente_de.desc()).all()
        contratos_dict = {}
        for c in contratos_db:
            contratos_dict.setdefault(c.id_paciente, []).append(c)
            
        # Pre-fetch AgendaSessao (AGENDADA) for all active patients in that month
        pontuais_db = db.query(AgendaSessao).filter(
            AgendaSessao.id_paciente.in_(p_ids),
            AgendaSessao.status_presenca == StatusPresenca.AGENDADA,
            extract("year", AgendaSessao.data_hora_inicio) == ano,
            extract("month", AgendaSessao.data_hora_inicio) == mes,
        ).all()
        pontuais_dict = {}
        for s in pontuais_db:
            pontuais_dict.setdefault(s.id_paciente, []).append(s)
            
        # Pre-fetch AgendaSessao (REALIZADA, CANCELOU_EM_CIMA) for all active patients in that month
        sessoes_db = db.query(AgendaSessao).filter(
            AgendaSessao.id_paciente.in_(p_ids),
            AgendaSessao.status_presenca.in_([
                StatusPresenca.REALIZADA,
                StatusPresenca.CANCELOU_EM_CIMA]),
            extract("year", AgendaSessao.data_hora_inicio) == ano,
            extract("month", AgendaSessao.data_hora_inicio) == mes,
        ).all()
        sessoes_dict = {}
        for s in sessoes_db:
            sessoes_dict.setdefault(s.id_paciente, []).append(s)
    else:
        contratos_dict = {}
        pontuais_dict = {}
        sessoes_dict = {}

    linhas, fat_prev, fat_real, total_inad = [], Decimal(0), Decimal(0), Decimal(0)
    for p in ativos:
        hist_p = contratos_dict.get(p.id_paciente, [])
        pont_p = pontuais_dict.get(p.id_paciente, [])
        sess_p = sessoes_dict.get(p.id_paciente, [])
        
        pv = previsto_paciente(p, ano, mes, bloq, db=db, historico=hist_p, pontuais=pont_p)
        rl = realizado_paciente(db, p, ano, mes, historico=hist_p, sessoes=sess_p)
        fat_prev += pv["faturamento_previsto"]
        fat_real += rl["faturamento_realizado"]
        total_inad += rl.get("inadimplencia", Decimal(0))
        linhas.append({
            "paciente": p.nome,
            "sessoes_previstas": pv["sessoes_previstas"],
            "faturamento_previsto": pv["faturamento_previsto"],
            "sessoes_realizadas": rl["sessoes_realizadas"],
            "faturamento_realizado": rl["faturamento_realizado"],
            "inadimplencia": rl.get("inadimplencia", Decimal(0)),
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
        "inadimplencia": total_inad,
        "total_despesas": despesas,
        "lucro_liquido": fat_real - despesas,  # DRE simplificado
    }


def consolidado_periodo(db, ano: int, meses: list) -> dict:
    """Agrega varios meses (trimestre/semestre/ano) somando os totais."""
    prev = real = desp = inad = Decimal(0)
    agg = {}
    for m in meses:
        r = consolidado_mes(db, ano, m)
        prev += r["faturamento_previsto"]
        real += r["faturamento_realizado"]
        desp += r["total_despesas"]
        inad += r.get("inadimplencia", Decimal(0))
        for l in r["linhas"]:
            a = agg.setdefault(l["paciente"], {
                "paciente": l["paciente"], "sessoes_previstas": 0,
                "faturamento_previsto": Decimal(0),
                "sessoes_realizadas": 0, "faturamento_realizado": Decimal(0),
                "inadimplencia": Decimal(0)})
            a["sessoes_previstas"] += l["sessoes_previstas"]
            a["faturamento_previsto"] += l["faturamento_previsto"]
            a["sessoes_realizadas"] += l["sessoes_realizadas"]
            a["faturamento_realizado"] += l["faturamento_realizado"]
            a["inadimplencia"] += l.get("inadimplencia", Decimal(0))
    return {
        "linhas": list(agg.values()),
        "faturamento_previsto": prev,
        "faturamento_realizado": real,
        "total_despesas": desp,
        "inadimplencia": inad,
        "lucro_liquido": real - desp,
    }


def historico_ultimos_meses(db, ano_alvo: int, mes_alvo: int, qtd: int = 6) -> list:
    """Retorna o historico dos ultimos QTD meses terminando no mes/ano informados (inclusive).
    Usado para o grafico de linha de evolucao temporal."""
    meses_lista = []
    mes = mes_alvo
    ano = ano_alvo
    for _ in range(qtd):
        meses_lista.append((ano, mes))
        mes -= 1
        if mes == 0:
            mes = 12
            ano -= 1
    
    meses_lista.reverse()
    
    dados = []
    for a, m in meses_lista:
        r = consolidado_mes(db, a, m)
        dados.append({
            "ano": a,
            "mes": m,
            "mes_rotulo": f"{m:02d}/{a}",
            "faturamento_realizado": float(r["faturamento_realizado"]),
            "total_despesas": float(r["total_despesas"]),
            "lucro_liquido": float(r["lucro_liquido"]),
        })
    return dados



def fmt_br(v) -> str:
    """26280.00 -> 'R$ 26.280,00'"""
    s = f"{float(v):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def expandir_recorrentes(db, ano: int, mes: int):
    """Gera instancia da despesa fixa neste mes/ano se nao existir,
    desde que esteja dentro de [mes_referencia, mes_fim].
    Meses anteriores ao atual sao marcados como paga=True por padrao
    (presume historico ja quitado)."""
    import calendar as cal
    from datetime import datetime as dt_now
    from app.db.models import Despesa
    ref = f"{ano:04d}-{mes:02d}"
    hoje = dt_now.now().date()
    ref_hoje = f"{hoje.year:04d}-{hoje.month:02d}"
    base = db.query(Despesa).filter(
        Despesa.recorrente == True).all()  # noqa: E712
    if not base:
        return
        
    existentes = db.query(Despesa.descricao).filter(
        Despesa.mes_referencia == ref).all()
    existentes_set = {e[0] for e in existentes}
    
    for d in base:
        if ref < d.mes_referencia:
            continue
        if d.mes_fim and ref > d.mes_fim:
            continue
        if ref == d.mes_referencia:
            continue
        if d.descricao in existentes_set:
            continue
        dia = d.dia_vencimento_mes or d.data_vencimento.day
        _, td = cal.monthrange(ano, mes)
        dia = min(dia, td)
        # Meses passados: marca como paga
        eh_passado = ref < ref_hoje
        db.add(Despesa(descricao=d.descricao, valor=d.valor,
            data_vencimento=date(ano, mes, dia), mes_referencia=ref,
            paga=eh_passado,
            data_pagamento=date(ano, mes, dia) if eh_passado else None,
            recorrente=False))
    db.commit()
