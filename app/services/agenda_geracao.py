import calendar
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from sqlalchemy import extract
from app.db.models import (
    Paciente, AgendaSessao, ContratoHistorico, Indisponibilidade,
    StatusPaciente, StatusPresenca, StatusPagamento, Frequencia, DiaSemana
)
from app.services.feriados import feriados_brasil
from app.services.contrato import snapshot_vigente_em_memoria

DIAS_PT = ["Segunda-feira", "Terça-feira", "Quarta-feira",
           "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]

def obter_horario_inicio_fim(paciente, dia_nome):
    for par in (paciente.horario_atendimento or "").split(","):
        if "=" in par:
            d, faixa = par.split("=", 1)
            if d.strip() == dia_nome:
                try:
                    ini, fim = faixa.split(" - ")
                    hi, mi = map(int, ini.split(":"))
                    hf, mf = map(int, fim.split(":"))
                    return time(hi, mi), time(hf, mf)
                except (ValueError, AttributeError):
                    pass
    return None, None

class AgendaGeracaoService:
    @staticmethod
    def gerar_sessoes_futuras(db, paciente, data_inicio, limite_meses=12):
        """
        Gera instâncias físicas de sessões futuras para o paciente a partir de data_inicio.
        """
        if paciente.status != StatusPaciente.ATIVO or paciente.em_avaliacao:
            return

        # Carrega histórico de contratos
        historico = db.query(ContratoHistorico).filter(
            ContratoHistorico.id_paciente == paciente.id_paciente
        ).order_by(ContratoHistorico.vigente_de.desc()).all()

        # Pre-fetch Indisponibilidades
        fim_periodo = data_inicio + timedelta(days=30 * limite_meses)
        indisps = db.query(Indisponibilidade).filter(
            Indisponibilidade.data >= data_inicio,
            Indisponibilidade.data <= fim_periodo
        ).all()
        
        indisp_set = set()
        for r in indisps:
            indisp_set.add((r.data, "dia_todo" if r.dia_todo else r.horario))

        # Feriados por ano no range
        feriados = {}
        for ano in range(data_inicio.year, fim_periodo.year + 1):
            feriados.update(feriados_brasil(ano))

        # Check existing sessions to avoid duplicates
        existentes_db = db.query(AgendaSessao.data_hora_inicio).filter(
            AgendaSessao.id_paciente == paciente.id_paciente,
            AgendaSessao.data_hora_inicio >= datetime.combine(data_inicio, time.min),
            AgendaSessao.data_hora_inicio <= datetime.combine(fim_periodo, time.max)
        ).all()
        existentes_set = {s[0] for s in existentes_db}

        novas_sessoes = []
        d = data_inicio
        while d <= fim_periodo:
            if paciente.ativo_desde and d < paciente.ativo_desde:
                d += timedelta(days=1)
                continue

            snap = snapshot_vigente_em_memoria(historico, d)
            if not snap:
                d += timedelta(days=1)
                continue

            dias_csv = snap.dias_semana or ""
            if not dias_csv:
                d += timedelta(days=1)
                continue

            weekday_idx = d.weekday()
            dia_nome = DIAS_PT[weekday_idx]
            dias_lista = [x.strip() for x in dias_csv.split(",") if x.strip()]

            if dia_nome not in dias_lista:
                d += timedelta(days=1)
                continue

            # Regras de frequencia
            if snap.frequencia == Frequencia.QUINZENAL:
                iso_sem = d.isocalendar()[1]
                paridade = "par" if iso_sem % 2 == 0 else "impar"
                if (snap.paridade_quinzenal or "impar").lower() != paridade:
                    d += timedelta(days=1)
                    continue
            elif snap.frequencia == Frequencia.MENSAL:
                ocorr = sum(1 for dd in range(1, d.day + 1)
                            if date(d.year, d.month, dd).weekday() == weekday_idx)
                alvo = snap.semana_do_mes or 1
                if alvo == 5:
                    total_ocorr = sum(1 for dd in range(1, calendar.monthrange(d.year, d.month)[1] + 1)
                                      if date(d.year, d.month, dd).weekday() == weekday_idx)
                    if ocorr != total_ocorr:
                        d += timedelta(days=1)
                        continue
                else:
                    if ocorr != alvo:
                        d += timedelta(days=1)
                        continue

            # Determina horário de atendimento
            t_ini, t_fim = obter_horario_inicio_fim(paciente, dia_nome)
            if not t_ini or not t_fim:
                d += timedelta(days=1)
                continue

            ini_dt = datetime.combine(d, t_ini)
            fim_dt = datetime.combine(d, t_fim)

            if ini_dt in existentes_set:
                d += timedelta(days=1)
                continue

            # Verifica feriado ou bloqueio
            bloqueada = False
            motivo_bloqueio = ""
            if d in feriados:
                bloqueada = True
                motivo_bloqueio = f"Feriado: {feriados[d][0]}"
            elif (d, "dia_todo") in indisp_set:
                bloqueada = True
                motivo_bloqueio = "Bloqueio (dia todo)"
            else:
                faixa_str = f"{t_ini.strftime('%H:%M')} - {t_fim.strftime('%H:%M')}"
                if (d, faixa_str) in indisp_set:
                    bloqueada = True
                    motivo_bloqueio = "Bloqueio de horário"

            status_pres = StatusPresenca.CANCELADA if bloqueada else StatusPresenca.AGENDADA
            status_pag = StatusPagamento.ISENTO if bloqueada else StatusPagamento.PENDENTE

            novas_sessoes.append(AgendaSessao(
                id_paciente=paciente.id_paciente,
                data_hora_inicio=ini_dt,
                data_hora_fim=fim_dt,
                status_presenca=status_pres,
                status_pagamento=status_pag,
                valor_sessao=snap.valor_sessao,
                recorrente=True,
                remarcada_motivo=motivo_bloqueio if bloqueada else None
            ))
            d += timedelta(days=1)

        if novas_sessoes:
            db.add_all(novas_sessoes)

    @staticmethod
    def remover_sessoes_futuras(db, paciente_id, data_inicio):
        """
        Apaga sessões futuras que ainda não foram realizadas ou faturadas (status AGENDADA).
        """
        db.query(AgendaSessao).filter(
            AgendaSessao.id_paciente == paciente_id,
            AgendaSessao.data_hora_inicio >= datetime.combine(data_inicio, time.min),
            AgendaSessao.status_presenca == StatusPresenca.AGENDADA
        ).delete()

    @staticmethod
    def processar_mudanca_contrato(db, paciente, data_efetivacao):
        """
        Gerencia o impacto de uma alteração de contrato no agendamento.
        """
        # 1. Remove sessões futuras pendentes na regra antiga
        AgendaGeracaoService.remover_sessoes_futuras(db, paciente.id_paciente, data_efetivacao)
        # 2. Gera novas sessões a partir da data de efetivação
        AgendaGeracaoService.gerar_sessoes_futuras(db, paciente, data_efetivacao, limite_meses=12)

    @staticmethod
    def processar_bloqueio_agenda(db, data_inicio, data_fim, horario=None):
        """
        Aplica um bloqueio na agenda cancelando sessões conflitantes que estejam com status AGENDADA.
        """
        dt_ini = datetime.combine(data_inicio, time.min)
        dt_fim = datetime.combine(data_fim, time.max)
        
        query = db.query(AgendaSessao).filter(
            AgendaSessao.data_hora_inicio >= dt_ini,
            AgendaSessao.data_hora_inicio <= dt_fim,
            AgendaSessao.status_presenca == StatusPresenca.AGENDADA
        )
        
        sessoes = query.all()
        for s in sessoes:
            dia = s.data_hora_inicio.date()
            if horario:
                # Verifica se há sobreposição com a faixa de horário bloqueada
                faixa_sessao = f"{s.data_hora_inicio.strftime('%H:%M')} - {s.data_hora_fim.strftime('%H:%M')}"
                from app.services.ocupacao import faixas_sobrepoem
                if not faixas_sobrepoem(faixa_sessao, horario):
                    continue
            
            s.status_presenca = StatusPresenca.CANCELADA
            s.status_pagamento = StatusPagamento.ISENTO
            s.remarcada_motivo = "Bloqueio do Consultório"
