"""Motor financeiro: previsto vs realizado, DRE simplificado."""
from decimal import Decimal
from datetime import datetime, date
from sqlalchemy import func, extract
from app.db.models import (Paciente, AgendaSessao, Despesa,
                           StatusPaciente, StatusPresenca, Frequencia)
from app.services.calendario import sessoes_previstas, sessoes_previstas_lista
from app.services.contrato import snapshot_vigente


def previsto_paciente(p: Paciente, ano: int, mes: int,
                      bloqueadas: set = None, db=None) -> dict:
    """Previsao de sessoes e faturamento de UM paciente no mes.
    Pro-rateado: cada data candidata do mes eh avaliada com o snapshot
    vigente NAQUELA data (corrige mudanca de contrato no meio do mes)."""
    import calendar as _cal
    from app.services.calendario import _DIA_IDX
    from app.services.feriados import feriados_brasil
    from app.db.models import DiaSemana as _DS

    fim_mes = date(ano, mes, 28)
    if p.em_avaliacao or (p.ativo_desde and p.ativo_desde > fim_mes):
        return {"paciente": p.nome, "sessoes_previstas": 0,
                "faturamento_previsto": Decimal(0)}

    # Sem db: comportamento legado (campos atuais do paciente)
    if db is None:
        return _previsto_legado(p, ano, mes, bloqueadas)

    _, total_dias = _cal.monthrange(ano, mes)
    fer = feriados_brasil(ano)
    bloq = bloqueadas or set()
    n = 0
    fat = Decimal(0)
    datas_recorrentes = set()  # para evitar dupla contagem com pontuais

    # Para cada dia do mes, ve qual snapshot vigente e se conta sessao
    for d in range(1, total_dias + 1):
        dt = date(ano, mes, d)
        if dt in fer or dt in bloq:
            continue
        # Antes do ativo_desde, nao conta
        if p.ativo_desde and dt < p.ativo_desde:
            continue
        snap = snapshot_vigente(db, p.id_paciente, dt)
        if not snap:
            continue
        # PERSONALIZADO: usa o snapshot vigente no fim do mes (count fixo)
        if snap.frequencia == Frequencia.PERSONALIZADO:
            continue  # tratado fora do loop
        dias_csv = snap.dias_semana or ""
        if not dias_csv:
            continue
        idx_dia = _cal.weekday(ano, mes, d)
        dias_lista = [x.strip() for x in dias_csv.split(",") if x.strip()]
        # Esse dia da semana eh um dos dias do contrato vigente?
        bate = False
        for nome in dias_lista:
            try:
                if _DIA_IDX[_DS(nome)] == idx_dia:
                    bate = True; break
            except (ValueError, KeyError):
                pass
        if not bate:
            continue
        # Regras de frequencia (quinzenal/mensal precisam de filtro extra)
        if snap.frequencia == Frequencia.QUINZENAL:
            iso_sem = dt.isocalendar()[1]
            paridade = "par" if iso_sem % 2 == 0 else "impar"
            if (snap.paridade_quinzenal or "impar") != paridade:
                continue
        elif snap.frequencia == Frequencia.MENSAL:
            # Conta posicao da ocorrencia desse dia da semana no mes
            ocorr = sum(1 for dd in range(1, d + 1)
                        if _cal.weekday(ano, mes, dd) == idx_dia)
            alvo = snap.semana_do_mes or 1
            if alvo == 5:  # Ultima
                total_ocorr = sum(1 for dd in range(1, total_dias + 1)
                                  if _cal.weekday(ano, mes, dd) == idx_dia)
                if ocorr != total_ocorr:
                    continue
            else:
                if ocorr != alvo:
                    continue
        # SEMANAL / DUAS_SEMANA / TRES_SEMANA: bate dia da semana ja basta
        n += 1
        fat += snap.valor_sessao
        datas_recorrentes.add(dt)

    # PERSONALIZADO: usa snapshot do fim do mes (count fixo nao pro-rateavel)
    snap_fim = snapshot_vigente(db, p.id_paciente, fim_mes)
    if snap_fim and snap_fim.frequencia == Frequencia.PERSONALIZADO \
            and snap_fim.sessoes_mes_custom:
        n = snap_fim.sessoes_mes_custom
        fat = Decimal(n) * snap_fim.valor_sessao

    # Sessoes pontuais AGENDADAS no mes (avulsas/remarcadas) -> entram no previsto
    from app.db.models import AgendaSessao, StatusPresenca
    pontuais = db.query(AgendaSessao).filter(
        AgendaSessao.id_paciente == p.id_paciente,
        AgendaSessao.status_presenca == StatusPresenca.AGENDADA,
        extract("year", AgendaSessao.data_hora_inicio) == ano,
        extract("month", AgendaSessao.data_hora_inicio) == mes,
    ).all()
    for s in pontuais:
        d_pont = s.data_hora_inicio.date()
        # Se a data ja foi contada pela recorrencia, pula
        if d_pont in datas_recorrentes:
            continue
        sn = snapshot_vigente(db, p.id_paciente, d_pont)
        n += 1
        fat += (sn.valor_sessao if sn else p.valor_sessao)

    return {"paciente": p.nome, "sessoes_previstas": n,
            "faturamento_previsto": fat}


def _previsto_legado(p, ano, mes, bloqueadas):
    """Fallback sem historico (compatibilidade quando db=None)."""
    if p.frequencia == Frequencia.PERSONALIZADO and p.sessoes_mes_custom:
        n = p.sessoes_mes_custom
    else:
        dias = (p.dias_semana.split(",") if p.dias_semana
                else [p.dia_atendimento.value] if p.dia_atendimento else [])
        n = sessoes_previstas_lista(ano, mes, dias, p.frequencia, bloqueadas)
    return {"paciente": p.nome, "sessoes_previstas": n,
            "faturamento_previsto": Decimal(n) * p.valor_sessao}


def realizado_paciente(db, p: Paciente, ano: int, mes: int) -> dict:
    """Sessoes que geram receita: Realizada ou Cancelou -24h (cobra).
    Cada sessao eh valorada pelo snapshot vigente na sua data (corrige
    mudancas de valor retroativas)."""
    sessoes = db.query(AgendaSessao).filter(
        AgendaSessao.id_paciente == p.id_paciente,
        AgendaSessao.status_presenca.in_([
            StatusPresenca.REALIZADA,
            StatusPresenca.CANCELOU_EM_CIMA]),
        extract("year", AgendaSessao.data_hora_inicio) == ano,
        extract("month", AgendaSessao.data_hora_inicio) == mes,
    ).all()
    fat = Decimal(0)
    for s in sessoes:
        snap = snapshot_vigente(db, p.id_paciente,
                                s.data_hora_inicio.date())
        fat += (snap.valor_sessao if snap else p.valor_sessao)
    return {"paciente": p.nome, "sessoes_realizadas": len(sessoes),
            "faturamento_realizado": fat}


def consolidado_mes(db, ano: int, mes: int) -> dict:
    """Visao da planilha: previsto e realizado de todos os pacientes ativos + DRE."""
    from app.services.indisponibilidade import datas_dia_todo
    bloq = datas_dia_todo(db, ano, mes)
    ativos = db.query(Paciente).filter(
        Paciente.status == StatusPaciente.ATIVO).all()

    linhas, fat_prev, fat_real = [], Decimal(0), Decimal(0)
    for p in ativos:
        pv = previsto_paciente(p, ano, mes, bloq, db=db)
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


def consolidado_periodo(db, ano: int, meses: list) -> dict:
    """Agrega varios meses (trimestre/semestre/ano) somando os totais."""
    prev = real = desp = Decimal(0)
    agg = {}
    for m in meses:
        r = consolidado_mes(db, ano, m)
        prev += r["faturamento_previsto"]
        real += r["faturamento_realizado"]
        desp += r["total_despesas"]
        for l in r["linhas"]:
            a = agg.setdefault(l["paciente"], {
                "paciente": l["paciente"], "sessoes_previstas": 0,
                "faturamento_previsto": Decimal(0),
                "sessoes_realizadas": 0, "faturamento_realizado": Decimal(0)})
            a["sessoes_previstas"] += l["sessoes_previstas"]
            a["faturamento_previsto"] += l["faturamento_previsto"]
            a["sessoes_realizadas"] += l["sessoes_realizadas"]
            a["faturamento_realizado"] += l["faturamento_realizado"]
    return {
        "linhas": list(agg.values()),
        "faturamento_previsto": prev,
        "faturamento_realizado": real,
        "total_despesas": desp,
        "lucro_liquido": real - desp,
    }


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
    for d in base:
        if ref < d.mes_referencia:
            continue
        if d.mes_fim and ref > d.mes_fim:
            continue
        if ref == d.mes_referencia:
            continue
        ja = db.query(Despesa).filter(
            Despesa.descricao == d.descricao,
            Despesa.mes_referencia == ref).first()
        if ja:
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
