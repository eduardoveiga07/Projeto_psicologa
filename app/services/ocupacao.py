"""Calcula as datas reais em que cada paciente atende em um mes."""
import calendar
from datetime import date
from app.db.models import (Paciente, StatusPaciente, Frequencia, DiaSemana)

_DIA_IDX = {DiaSemana.SEG: 0, DiaSemana.TER: 1, DiaSemana.QUA: 2,
            DiaSemana.QUI: 3, DiaSemana.SEX: 4, DiaSemana.SAB: 5}


def _para_min(faixa: str) -> tuple:
    """'07:00 - 08:00' -> (420, 480)."""
    try:
        ini, fim = faixa.split(" - ")
        hi, mi = map(int, ini.split(":"))
        hf, mf = map(int, fim.split(":"))
        return (hi * 60 + mi, hf * 60 + mf)
    except (ValueError, AttributeError):
        return (0, 0)


def faixas_sobrepoem(f1: str, f2: str) -> bool:
    """True se duas faixas '07:00 - 08:00' se sobrepoem."""
    i1, e1 = _para_min(f1)
    i2, e2 = _para_min(f2)
    return i1 < e2 and i2 < e1


def _ocorrencias(ano: int, mes: int, dia_nome: str) -> list:
    """Lista de datas no mes onde cai 'dia_nome'."""
    try:
        idx = _DIA_IDX[DiaSemana(dia_nome)]
    except (ValueError, KeyError):
        return []
    _, td = calendar.monthrange(ano, mes)
    return [date(ano, mes, d) for d in range(1, td + 1)
            if calendar.weekday(ano, mes, d) == idx]


def _faixa_do_paciente_no_dia(p: Paciente, dia_nome: str) -> str:
    """Faixa de horario que p usa nesse dia, ou ''."""
    for par in (p.horario_atendimento or "").split(","):
        if "=" in par:
            d, faixa = par.split("=", 1)
            if d == dia_nome:
                return faixa.strip()
    return ""


# _aplicar_excecoes removida pois excecoes agora sao gravadas diretamente no banco de dados.


def sessoes_perdidas_no_mes(p, ano: int, mes: int,
                             db, indisp_set: set = None,
                             feriados_set: set = None,
                             historico=None,
                             ja_remarcadas=None) -> list:
    """Retorna [(data, horario, motivo)] de sessoes que CAIRIAM pela regra
    do contrato mas estao bloqueadas por feriado ou indisponibilidade.
    Usa indisp_set: {(data, 'dia_todo'|horario)}. feriados_set: {data}."""
    from app.db.models import StatusPaciente, Frequencia, DiaSemana
    import calendar
    from datetime import date
    if p.em_avaliacao or p.status != StatusPaciente.ATIVO:
        return []
    if p.ativo_desde and p.ativo_desde > date(ano, mes, 28):
        return []
    from app.services.contrato import snapshot_vigente_em_memoria
    from app.services.feriados import feriados_brasil
    from app.db.models import AgendaSessao, ContratoHistorico
    fer = feriados_set if feriados_set is not None else feriados_brasil(ano)
    indisp = indisp_set or set()
    # Datas que ja foram remarcadas (ignora-las)
    if ja_remarcadas is None:
        ja_remarcadas = {
            s.remarcada_de for s in db.query(AgendaSessao).filter(
                AgendaSessao.id_paciente == p.id_paciente,
                AgendaSessao.remarcada_de.isnot(None)).all()
        }
    # Carrega todo o historico de contratos do paciente de uma vez
    if historico is None:
        historico = db.query(ContratoHistorico).filter(
            ContratoHistorico.id_paciente == p.id_paciente
        ).order_by(ContratoHistorico.vigente_de.desc()).all()

    _, total_dias = calendar.monthrange(ano, mes)
    perdidas = []
    for d in range(1, total_dias + 1):
        dt = date(ano, mes, d)
        if p.ativo_desde and dt < p.ativo_desde:
            continue
        snap = snapshot_vigente_em_memoria(historico, dt)
        if not snap:
            continue
        dias_csv = snap.dias_semana or ""
        if not dias_csv:
            continue
        idx_hoje = calendar.weekday(ano, mes, d)
        nome_dia_bate = None
        for nome in [x.strip() for x in dias_csv.split(",") if x.strip()]:
            try:
                if _DIA_IDX[DiaSemana(nome)] == idx_hoje:
                    nome_dia_bate = nome; break
            except (ValueError, KeyError):
                pass
        if not nome_dia_bate:
            continue
        # Filtros de frequencia (mesma logica)
        if snap.frequencia == Frequencia.QUINZENAL:
            paridade = (snap.paridade_quinzenal or "impar").lower()
            alvo = 0 if paridade == "par" else 1
            if dt.isocalendar()[1] % 2 != alvo:
                continue
        elif snap.frequencia == Frequencia.MENSAL:
            ocorr = sum(1 for dd in range(1, d + 1)
                        if calendar.weekday(ano, mes, dd) == idx_hoje)
            alvo = snap.semana_do_mes or 1
            if alvo == 5:  # Ultima
                total_ocorr = sum(1 for dd in range(1, total_dias + 1)
                                  if calendar.weekday(ano, mes, dd) == idx_hoje)
                if ocorr != total_ocorr:
                    continue
            else:
                if ocorr != alvo:
                    continue
        # Cairia esse dia. Ja foi remarcada?
        if dt in ja_remarcadas:
            continue
        # Esta bloqueado?
        hr = _faixa_do_paciente_no_dia(p, nome_dia_bate)
        if dt in fer:
            nome_fer = fer[dt] if isinstance(fer, dict) else "feriado"
            perdidas.append((dt, hr, f"Feriado: {nome_fer}"))
        elif (dt, "dia_todo") in indisp:
            perdidas.append((dt, hr, "Bloqueio (dia todo)"))
        elif hr and (dt, hr) in indisp:
            perdidas.append((dt, hr, "Bloqueio de horário"))
    return perdidas


def datas_paciente_no_mes(p, ano: int, mes: int,
                          db=None, indisp_set=None, historico=None, excs=None) -> list:
    """Retorna [(data, horario)] em que p atende neste mes.
    Lê diretamente da tabela agenda_sessoes se db for passado e o paciente for cadastrado.
    Caso contrário, calcula em memória usando o contrato (fallback e simulação)."""
    from app.db.models import StatusPaciente
    from datetime import date
    if p.em_avaliacao or p.status != StatusPaciente.ATIVO:
        return []
    if p.ativo_desde and p.ativo_desde > date(ano, mes, 28):
        return []

    # Se db estiver disponível e o paciente tiver ID (já persistido no banco)
    if db is not None and p.id_paciente is not None:
        from app.db.models import AgendaSessao, StatusPresenca
        from datetime import datetime, time
        import calendar
        
        inicio_mes = datetime.combine(date(ano, mes, 1), time.min)
        fim_mes = datetime.combine(date(ano, mes, calendar.monthrange(ano, mes)[1]), time.max)
        
        sessoes = db.query(AgendaSessao).filter(
            AgendaSessao.id_paciente == p.id_paciente,
            AgendaSessao.data_hora_inicio >= inicio_mes,
            AgendaSessao.data_hora_inicio <= fim_mes,
            AgendaSessao.status_presenca != StatusPresenca.CANCELADA,
            AgendaSessao.status_presenca != StatusPresenca.CANCELOU_COM_ANTECEDENCIA,
            AgendaSessao.status_presenca != StatusPresenca.IMPREVISTO
        ).order_by(AgendaSessao.data_hora_inicio).all()
        
        out = []
        for s in sessoes:
            dt = s.data_hora_inicio.date()
            hr = f"{s.data_hora_inicio.strftime('%H:%M')} - {s.data_hora_fim.strftime('%H:%M')}"
            out.append((dt, hr))
        return out

    # Fallback/Simulação em memória (sem db ou paciente novo)
    if db is None:
        return _datas_legado(p, ano, mes)

    # Caso tenhamos db mas o paciente seja novo (p.id_paciente é None), simula a geração:
    from app.services.contrato import snapshot_vigente_em_memoria
    from app.services.feriados import feriados_brasil
    from app.db.models import Indisponibilidade, ContratoHistorico, Frequencia, DiaSemana
    import calendar
    
    fer = feriados_brasil(ano)
    
    if indisp_set is None:
        indisp_set = set()
        indisps = db.query(Indisponibilidade).filter(
            Indisponibilidade.data >= date(ano, mes, 1),
            Indisponibilidade.data <= date(ano, mes,
                calendar.monthrange(ano, mes)[1])).all()
        for r in indisps:
            indisp_set.add((r.data, "dia_todo" if r.dia_todo else r.horario))

    if historico is None:
        historico = db.query(ContratoHistorico).filter(
            ContratoHistorico.id_paciente == p.id_paciente
        ).order_by(ContratoHistorico.vigente_de.desc()).all()

    _, total_dias = calendar.monthrange(ano, mes)
    out = []
    for d in range(1, total_dias + 1):
        dt = date(ano, mes, d)
        if p.ativo_desde and dt < p.ativo_desde:
            continue
        snap = snapshot_vigente_em_memoria(historico, dt)
        if not snap:
            snap = p
        dias_csv = snap.dias_semana or ""
        if not dias_csv:
            continue
        idx_hoje = calendar.weekday(ano, mes, d)
        nome_dia_bate = None
        for nome in [x.strip() for x in dias_csv.split(",") if x.strip()]:
            try:
                if _DIA_IDX[DiaSemana(nome)] == idx_hoje:
                    nome_dia_bate = nome; break
            except (ValueError, KeyError):
                pass
        if not nome_dia_bate:
            continue
        if snap.frequencia == Frequencia.QUINZENAL:
            paridade = (snap.paridade_quinzenal or "impar").lower()
            alvo = 0 if paridade == "par" else 1
            if dt.isocalendar()[1] % 2 != alvo:
                continue
        elif snap.frequencia == Frequencia.MENSAL:
            ocorr = sum(1 for dd in range(1, d + 1)
                        if calendar.weekday(ano, mes, dd) == idx_hoje)
            alvo = snap.semana_do_mes or 1
            if alvo >= 5:
                total_ocorr = sum(1 for dd in range(1, total_dias + 1)
                                  if calendar.weekday(ano, mes, dd) == idx_hoje)
                if ocorr != total_ocorr:
                    continue
            else:
                if ocorr != alvo:
                    continue
        hr = _faixa_do_paciente_no_dia(p, nome_dia_bate)
        if dt in fer:
            continue
        if (dt, "dia_todo") in indisp_set:
            continue
        if hr and (dt, hr) in indisp_set:
            continue
        out.append((dt, hr))

    return out


def _datas_legado(p, ano: int, mes: int) -> list:
    """Fallback sem db: usa campos atuais do paciente."""
    from app.db.models import Frequencia
    dias = (p.dias_semana.split(",") if p.dias_semana
            else [p.dia_atendimento.value] if p.dia_atendimento else [])
    out = []
    for d_nome in dias:
        hr = _faixa_do_paciente_no_dia(p, d_nome)
        ocs = _ocorrencias(ano, mes, d_nome)
        if not ocs:
            continue
        if p.frequencia == Frequencia.MENSAL:
            n = (p.semana_do_mes or 1)
            if n >= 5:
                escolhidas = [ocs[-1]]
            elif n <= len(ocs):
                escolhidas = [ocs[n - 1]]
            else:
                escolhidas = []
        elif p.frequencia == Frequencia.QUINZENAL:
            paridade = (p.paridade_quinzenal or "impar").lower()
            alvo = 0 if paridade == "par" else 1
            escolhidas = [dt for dt in ocs
                          if dt.isocalendar()[1] % 2 == alvo]
        else:
            escolhidas = ocs
        for dt in escolhidas:
            if p.ativo_desde and dt < p.ativo_desde:
                continue
            out.append((dt, hr))
    return out


def sessoes_perdidas_no_mes_query(db, p, ano: int, mes: int) -> list:
    """Retorna [(data, horario, motivo)] de sessoes canceladas fisicamente no banco no mes,
    que possuem remarcada_motivo preenchido e nao foram remarcadas ainda."""
    from app.db.models import AgendaSessao, StatusPresenca
    from datetime import date, time, datetime
    import calendar
    
    inicio_mes = datetime.combine(date(ano, mes, 1), time.min)
    fim_mes = datetime.combine(date(ano, mes, calendar.monthrange(ano, mes)[1]), time.max)
    
    # Busca todas as sessoes do paciente no mes que estao canceladas e tem motivo
    sessoes_canc = db.query(AgendaSessao).filter(
        AgendaSessao.id_paciente == p.id_paciente,
        AgendaSessao.data_hora_inicio >= inicio_mes,
        AgendaSessao.data_hora_inicio <= fim_mes,
        AgendaSessao.status_presenca == StatusPresenca.CANCELADA,
        AgendaSessao.remarcada_motivo.isnot(None)
    ).all()
    
    # Busca datas que ja foram remarcadas
    ja_remarcadas = {
        s.remarcada_de for s in db.query(AgendaSessao.remarcada_de).filter(
            AgendaSessao.id_paciente == p.id_paciente,
            AgendaSessao.remarcada_de.isnot(None)
        ).all() if s.remarcada_de is not None
    }
    
    perdidas = []
    for s in sessoes_canc:
        dt = s.data_hora_inicio.date()
        if dt in ja_remarcadas:
            continue
        hr = f"{s.data_hora_inicio.strftime('%H:%M')} - {s.data_hora_fim.strftime('%H:%M')}"
        perdidas.append((dt, hr, s.remarcada_motivo))
        
    return perdidas


def mapa_ocupacao_mes(db, ano: int, mes: int) -> dict:
    """Retorna {data: {horario: [nomes]}} mostrando quem atende em cada dia/hora."""
    from app.db.models import AgendaSessao, StatusPresenca
    from sqlalchemy.orm import joinedload
    from datetime import date, time, datetime
    import calendar
    
    inicio_mes = datetime.combine(date(ano, mes, 1), time.min)
    fim_mes = datetime.combine(date(ano, mes, calendar.monthrange(ano, mes)[1]), time.max)
    
    # Query all physical sessions for the month that are NOT cancelled
    sessoes = db.query(AgendaSessao).options(joinedload(AgendaSessao.paciente)).filter(
        AgendaSessao.data_hora_inicio >= inicio_mes,
        AgendaSessao.data_hora_inicio <= fim_mes,
        AgendaSessao.status_presenca != StatusPresenca.CANCELADA,
        AgendaSessao.status_presenca != StatusPresenca.CANCELOU_COM_ANTECEDENCIA,
        AgendaSessao.status_presenca != StatusPresenca.IMPREVISTO
    ).all()
    
    mapa = {}
    for s in sessoes:
        p_obj = s.paciente
        if not p_obj or p_obj.em_avaliacao:
            continue
        d = s.data_hora_inicio.date()
        hr = f"{s.data_hora_inicio.strftime('%H:%M')} - {s.data_hora_fim.strftime('%H:%M')}"
        
        mapa.setdefault(d, {}).setdefault(hr, []).append(p_obj.nome)
        
    return mapa


def detectar_conflitos(db, p_novo, ano: int, mes: int,
                       id_excluir=None) -> dict:
    """Verifica conflitos olhando 3 meses (atual + 2 próximos)."""
    from app.db.models import StatusPaciente, Paciente
    outros = db.query(Paciente).filter(
        Paciente.status == StatusPaciente.ATIVO,
        Paciente.em_avaliacao == False).all()  # noqa: E712
    livres, conflitos = [], []
    a, m = ano, mes
    for _ in range(3):
        # Pre-calcula as datas de todos os outros pacientes para este mes
        datas_outros = {}
        for outro in outros:
            if id_excluir and outro.id_paciente == id_excluir:
                continue
            datas_outros[outro.id_paciente] = datas_paciente_no_mes(outro, a, m, db=db)

        for dt, hr_novo in datas_paciente_no_mes(p_novo, a, m, db=db):
            choque = []
            for outro in outros:
                if id_excluir and outro.id_paciente == id_excluir:
                    continue
                for dt2, hr2 in datas_outros[outro.id_paciente]:
                    if dt == dt2 and faixas_sobrepoem(hr_novo, hr2):
                        choque.append(outro.nome)
            if choque:
                conflitos.append((dt, hr_novo, choque))
            else:
                livres.append((dt, hr_novo))
        a, m = (a, m + 1) if m < 12 else (a + 1, 1)
    return {"datas_livres": livres, "conflitos": conflitos}


def sugerir_horarios(db, p_novo, ano: int, mes: int, faixas_lista: list,
                     id_excluir=None) -> dict:
    """Retorna sugestões priorizadas: mesmo dia, mesmo horário em outros dias,
    qualquer livre na semana."""
    dia_novo = (p_novo.dias_semana or "").split(",")[0]
    hr_novo = None
    for par in (p_novo.horario_atendimento or "").split(","):
        if "=" in par:
            hr_novo = par.split("=", 1)[1].strip(); break
    mapa = mapa_ocupacao_mes(db, ano, mes)
    # ocupacao por (dia_semana, horario)
    ocup = {}  # {(dia_nome, hr): True}
    dias_nomes = ["Segunda-feira","Terça-feira","Quarta-feira",
        "Quinta-feira","Sexta-feira","Sábado"]
    for dt, slots in mapa.items():
        if dt.weekday() > 5: continue
        dn = dias_nomes[dt.weekday()]
        for hr in slots:
            ocup[(dn, hr)] = True
    # 1) Mesmo dia, outros horarios
    mesmo_dia = [h for h in faixas_lista
                 if not any(faixas_sobrepoem(h, oh)
                            for (od, oh) in ocup if od == dia_novo)]
    # 2) Mesmo horário, outros dias
    outros_dias = [d for d in dias_nomes if d != dia_novo
                   and (hr_novo is None or not any(
                       faixas_sobrepoem(hr_novo, oh)
                       for (od, oh) in ocup if od == d))]
    return {"mesmo_dia": mesmo_dia[:6], "outros_dias": outros_dias}
