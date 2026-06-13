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
    Pro-rateado: cada data candidata del mes eh avaliada com o snapshot
    vigente NAQUELA data (corrige mudanca de contrato no meio do mes)."""
    import calendar as _cal
    from app.services.calendario import _DIA_IDX
    from app.services.feriados import feriados_brasil
    from app.db.models import DiaSemana as _DS, ContratoHistorico
    from app.services.contrato import snapshot_vigente_em_memoria

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

    # Carrega todo o historico de contratos do paciente de uma vez
    if historico is None:
        historico = db.query(ContratoHistorico).filter(
            ContratoHistorico.id_paciente == p.id_paciente
        ).order_by(ContratoHistorico.vigente_de.desc()).all()

    # Para cada dia do mes, ve qual snapshot vigente e se conta sessao
    for d in range(1, total_dias + 1):
        dt = date(ano, mes, d)
        if dt in fer or dt in bloq:
            continue
        # Antes do ativo_desde, nao conta
        if p.ativo_desde and dt < p.ativo_desde:
            continue
        snap = snapshot_vigente_em_memoria(historico, dt)
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
    snap_fim = snapshot_vigente_em_memoria(historico, fim_mes)
    if snap_fim and snap_fim.frequencia == Frequencia.PERSONALIZADO \
            and snap_fim.sessoes_mes_custom:
        n = snap_fim.sessoes_mes_custom
        fat = Decimal(n) * snap_fim.valor_sessao

    # Sessoes pontuais AGENDADAS no mes (avulsas/remarcadas) -> entram no previsto
    if pontuais is None:
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
        sn = snapshot_vigente_em_memoria(historico, d_pont)
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


def realizado_paciente(db, p: Paciente, ano: int, mes: int,
                       historico=None, sessoes=None) -> dict:
    """Sessoes que geram receita: Realizada ou Cancelou -24h (cobra).
    Cada sessao eh valorada pelo snapshot vigente na sua data (corrige
    mudancas de valor retroativas).
    Tambem calcula a inadimplencia (sessoes faturadas com status PENDENTE ou ATRASADO)."""
    from app.db.models import AgendaSessao, StatusPresenca, StatusPagamento, ContratoHistorico
    from app.services.contrato import snapshot_vigente_em_memoria

    if sessoes is None:
        sessoes = db.query(AgendaSessao).filter(
            AgendaSessao.id_paciente == p.id_paciente,
            AgendaSessao.status_presenca.in_([
                StatusPresenca.REALIZADA,
                StatusPresenca.CANCELOU_EM_CIMA]),
            extract("year", AgendaSessao.data_hora_inicio) == ano,
            extract("month", AgendaSessao.data_hora_inicio) == mes,
        ).all()

    # Carrega todo o historico de contratos do paciente de uma vez
    if historico is None:
        historico = db.query(ContratoHistorico).filter(
            ContratoHistorico.id_paciente == p.id_paciente
        ).order_by(ContratoHistorico.vigente_de.desc()).all()

    fat = Decimal(0)
    inad = Decimal(0)
    for s in sessoes:
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
