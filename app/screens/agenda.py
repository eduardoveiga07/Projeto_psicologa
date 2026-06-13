import streamlit as st
from datetime import datetime, date, time, timedelta
from sqlalchemy import extract
from app.screens.shared import (
    db, registrar, mostrar_flash, flash, Paciente, AgendaSessao,
    Indisponibilidade, StatusPaciente, StatusPresenca, DiaSemana,
    FAIXAS_HORARIO, mapa_cached, invalidar_cache, ui_header
)
from app.services.feriados import feriados_brasil
from app.services.pdf_export import gerar_pdf
from app.services.ocupacao import sessoes_perdidas_no_mes_query


def tela_agenda():
    mostrar_flash()
    ui_header("Agenda de Sessões", icon="📅")
    st.caption("As sessões aparecem automaticamente conforme o cadastro de "
               "cada paciente (frequência, dia e horário). Para alterar uma "
               "data específica use Editar abaixo; para mudar permanente, "
               "edite o paciente em Cadastro.")
    # ---- Calendário mensal (a tela principal) ----
    st.subheader("Calendário mensal — quem atende em cada data")
    hoje = datetime.now().date()
    proximos = db().query(Indisponibilidade).filter(
        Indisponibilidade.data >= hoje,
        Indisponibilidade.data <= hoje + timedelta(days=60)).order_by(
        Indisponibilidade.data).all()
    if proximos:
        from app.services.indisponibilidade import (agrupar_em_ranges,
                                                     formatar_grupo)
        grupos_px = agrupar_em_ranges(proximos)
        with st.expander(f"⚠️ {len(proximos)} bloqueio(s) próximos (60 dias)"):
            for g in grupos_px:
                st.write(f"- {formatar_grupo(g)}")

    cc1, cc2 = st.columns(2)
    cal_ano = cc1.number_input("Ano", 2024, 2040,
        hoje.year, key="cal_ano")
    cal_mes = cc2.number_input("Mês", 1, 12, hoje.month, key="cal_mes")
    mapa = mapa_cached(int(cal_ano), int(cal_mes))

    # ===== FERIADOS E BLOQUEIOS DO MÊS =====
    fer_mes = feriados_brasil(int(cal_ano))
    fer_lista = [(d, n) for d, (n, t) in fer_mes.items()
                 if d.month == int(cal_mes)]
    bloq_lista = db().query(Indisponibilidade).filter(
        extract("year", Indisponibilidade.data) == int(cal_ano),
        extract("month", Indisponibilidade.data) == int(cal_mes)).order_by(
        Indisponibilidade.data).all()
    if fer_lista or bloq_lista:
        from app.services.indisponibilidade import (agrupar_em_ranges,
                                                     formatar_grupo)
        grupos_bloq = agrupar_em_ranges(bloq_lista)
        n_dias_bloq = sum(len(g["ids"]) for g in grupos_bloq)
        with st.expander(f"🔴 Feriados e bloqueios em "
                f"{int(cal_mes):02d}/{int(cal_ano)} "
                f"({len(fer_lista)} feriados + {n_dias_bloq} dias "
                f"de bloqueio)",
                expanded=True):
            for d, n in sorted(fer_lista):
                st.write(f"🔴 **{d.strftime('%d/%m')}** — {n} (feriado)")
            for g in grupos_bloq:
                st.write(f"🟠 {formatar_grupo(g)}")

    # Sessoes que cairiam mas estao bloqueadas (feriado/indisp) - REMARCAR
    fer_dict = {d: n for d, n in fer_lista}
    indisp_set = set()
    for r in bloq_lista:
        indisp_set.add((r.data, "dia_todo" if r.dia_todo else r.horario))
    perdidas_total = []
    ativos_perdidas = db().query(Paciente).filter(
            Paciente.status == StatusPaciente.ATIVO,
            Paciente.em_avaliacao == False).all()  # noqa: E712
    for p_a in ativos_perdidas:
        for dt, hr, mot in sessoes_perdidas_no_mes_query(
                db(), p_a, int(cal_ano), int(cal_mes)):
            perdidas_total.append((dt, hr, p_a.nome, mot))
    if perdidas_total:
        perdidas_total.sort()
        # Mapa nome->paciente p/ achar id
        pacs_ativos = {p.nome: p for p in db().query(Paciente).filter(
            Paciente.status == StatusPaciente.ATIVO).all()}
        with st.expander(
                f"⚠️ Sessões a remarcar/avisar pacientes "
                f"({len(perdidas_total)})", expanded=True):
            st.caption("Sessões que cairiam pela rotina mas coincidem "
                       "com feriado/bloqueio. Remarque para outra data ou "
                       "apenas avise o paciente.")
            for dt, hr, nome, mot in perdidas_total:
                pk = f"{dt.isoformat()}_{hr}_{nome}"
                ca, cb = st.columns([5, 1])
                ca.warning(f"**{dt.strftime('%d/%m')}** {hr} — "
                           f"**{nome}** — {mot}")
                if cb.button("Remarcar", key=f"rmk_{pk}"):
                    st.session_state[f"rmk_open_{pk}"] = True
                if st.session_state.get(f"rmk_open_{pk}"):
                    with st.form(f"rmk_f_{pk}"):
                        st.caption(f"Remarcar sessão de **{nome}** "
                                   f"que cairia in {dt.strftime('%d/%m/%Y')} "
                                   f"— motivo: _{mot}_")
                        cf1, cf2 = st.columns(2)
                        # Sugere proximo dia util (pula sabado/domingo)
                        from datetime import timedelta as _td
                        sug = dt + _td(days=1)
                        while sug.weekday() >= 5:
                            sug += _td(days=1)
                        nd = cf1.date_input("Nova data", value=sug,
                            min_value=dt + _td(days=1),
                            format="DD/MM/YYYY", key=f"rmk_d_{pk}")
                        idx_h = (FAIXAS_HORARIO.index(hr)
                                 if hr in FAIXAS_HORARIO else 0)
                        nh = cf2.selectbox("Novo horário", FAIXAS_HORARIO,
                            index=idx_h, key=f"rmk_h_{pk}")
                        cs1, cs2 = st.columns(2)
                        if cs1.form_submit_button("Confirmar"):
                            p_obj = pacs_ativos.get(nome)
                            if not p_obj:
                                st.error("Paciente não encontrado.")
                            else:
                                hi, _ = nh.split(" - ")
                                h_, m_ = map(int, hi.split(":"))
                                ini = datetime.combine(nd, time(h_, m_))
                                fim = ini.replace(hour=h_ + 1)
                                db().query(AgendaSessao).filter(
                                    AgendaSessao.data_hora_inicio == ini,
                                    AgendaSessao.status_presenca
                                    == StatusPresenca.CANCELADA).delete()
                                db().add(AgendaSessao(
                                    id_paciente=p_obj.id_paciente,
                                    data_hora_inicio=ini,
                                    data_hora_fim=fim,
                                    status_presenca=StatusPresenca.AGENDADA,
                                    remarcada_de=dt,
                                    remarcada_motivo=mot))
                                try:
                                    db().commit()
                                    invalidar_cache()
                                    registrar(db(), st.session_state.username,
                                              "SESSAO_REMARCADA",
                                              f"paciente_id={p_obj.id_paciente} {dt}->{nd} {nh}")
                                    del st.session_state[f"rmk_open_{pk}"]
                                    flash(f"Sessão de {nome} remarcada "
                                          f"de {dt.strftime('%d/%m')} para "
                                          f"{nd.strftime('%d/%m')} {nh}.",
                                          "success")
                                    st.rerun()
                                except Exception:
                                    db().rollback()
                                    st.error("Esse horário já está ocupado.")
                        if cs2.form_submit_button("Cancelar"):
                            del st.session_state[f"rmk_open_{pk}"]
                            st.rerun()

    # Monta linhas agrupadas por dia da semana.
    DIAS_PT_FULL = ["Segunda-feira", "Terça-feira", "Quarta-feira",
                    "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    pacientes_map = {p.nome: p for p in db().query(Paciente).filter(
        Paciente.status == StatusPaciente.ATIVO).all()}
    if not mapa:
        st.info(f"Sem atendimentos recorrentes em {int(cal_mes):02d}/{int(cal_ano)}.")
    linhas_pdf = []
    # Agrupa: {dia_semana_idx: [(data, hr, nomes)]}
    por_dia = {}
    for data_d in sorted(mapa.keys()):
        for hr, nomes in sorted(mapa[data_d].items()):
            por_dia.setdefault(data_d.weekday(), []).append(
                (data_d, hr, nomes))
    for dia_idx in sorted(por_dia.keys()):
        st.markdown(f"### 📅 {DIAS_PT_FULL[dia_idx]}")
        for data_d, hr, nomes in por_dia[dia_idx]:
            conflito = "⚠️ CONFLITO: " if len(nomes) > 1 else ""
            label = (f"{data_d.strftime('%d/%m')} — {hr} — "
                     f"{conflito}{' + '.join(nomes)}")
            linhas_pdf.append({"Data": data_d.strftime('%d/%m'),
                "Horário": hr, "Paciente(s)": conflito + " + ".join(nomes)})
            uk = f"{data_d.isoformat()}_{hr}_{'_'.join(nomes)}"
            cA, cB, cC = st.columns([6, 1, 1])
            cA.write(label)
            if cB.button("Editar", key=f"calE_{uk}"):
                st.session_state[f"calEd_{uk}"] = True
            if cC.button("Excluir", key=f"calX_{uk}"):
                st.session_state[f"calEx_{uk}"] = True
            if st.session_state.get(f"calEx_{uk}"):
                with st.form(f"calFX_{uk}"):
                    alvo_x = st.selectbox("Qual paciente excluir nesta data?",
                        nomes, key=f"calXP_{uk}")
                    if st.form_submit_button("Confirmar exclusão"):
                        p_obj = pacientes_map.get(alvo_x)
                        if p_obj:
                            hi, _ = hr.split(" - ")
                            h, m = map(int, hi.split(":"))
                            ini = datetime.combine(data_d, time(h, m))
                            sessao_existente = db().query(AgendaSessao).filter(
                                AgendaSessao.id_paciente == p_obj.id_paciente,
                                AgendaSessao.data_hora_inicio == ini
                            ).first()
                            if sessao_existente:
                                sessao_existente.status_presenca = StatusPresenca.CANCELADA
                            else:
                                db().add(AgendaSessao(id_paciente=p_obj.id_paciente,
                                    data_hora_inicio=ini,
                                    data_hora_fim=ini.replace(hour=h + 1),
                                    status_presenca=StatusPresenca.CANCELADA,
                                    recorrente=True))
                            try: db().commit()
                            except Exception: db().rollback()
                        del st.session_state[f"calEx_{uk}"]
                        st.rerun()
            if st.session_state.get(f"calEd_{uk}"):
                with st.form(f"calF_{uk}"):
                    alvo = st.selectbox("Qual paciente alterar?", nomes,
                        key=f"calEP_{uk}")
                    tipo = st.radio("Tipo de alteração",
                        ["Só nesta data (exceção)",
                         "Permanente (mudar cadastro deste paciente)"],
                        key=f"calTipo_{uk}")
                    cf1, cf2 = st.columns(2)
                    nd = cf1.date_input("Nova data",
                        value=data_d, format="DD/MM/YYYY",
                        key=f"calND_{uk}")
                    nh = cf2.selectbox("Novo horário", FAIXAS_HORARIO,
                        index=FAIXAS_HORARIO.index(hr) if hr in FAIXAS_HORARIO else 0,
                        key=f"calNH_{uk}")
                    if st.form_submit_button("Salvar"):
                        p_obj = pacientes_map.get(alvo)
                        if not p_obj:
                            st.error("Paciente não encontrado.")
                        else:
                            hn, _ = nh.split(" - ")
                            hh, mm = map(int, hn.split(":"))
                            hi, _ = hr.split(" - ")
                            h, m = map(int, hi.split(":"))
                            if tipo.startswith("Permanente"):
                                dias_pt = ["Segunda-feira", "Terça-feira",
                                    "Quarta-feira", "Quinta-feira",
                                    "Sexta-feira", "Sábado"]
                                if nd.weekday() <= 5:
                                    novo_dia_nome = dias_pt[nd.weekday()]
                                    p_obj.dia_atendimento = DiaSemana(novo_dia_nome)
                                    p_obj.dias_semana = novo_dia_nome
                                    p_obj.horario_atendimento = f"{novo_dia_nome}={nh}"
                                    db().commit()
                                    from app.services.contrato import abrir_periodo
                                    abrir_periodo(db(), p_obj, datetime.now().date())
                                    from app.services.agenda_geracao import AgendaGeracaoService
                                    AgendaGeracaoService.processar_mudanca_contrato(db(), p_obj, datetime.now().date())
                                    db().commit()
                                    db().expire_all()
                                    st.success(f"Cadastro de {alvo} atualizado "
                                               f"para {novo_dia_nome} {nh}.")
                                    del st.session_state[f"calEd_{uk}"]
                                    st.rerun()
                                else:
                                    st.error("Domingo não é permitido.")
                            else:
                                ini_orig = datetime.combine(data_d, time(h, m))
                                sessao_orig = db().query(AgendaSessao).filter(
                                    AgendaSessao.id_paciente == p_obj.id_paciente,
                                    AgendaSessao.data_hora_inicio == ini_orig
                                ).first()
                                if sessao_orig:
                                    sessao_orig.status_presenca = StatusPresenca.CANCELADA
                                else:
                                    db().add(AgendaSessao(
                                        id_paciente=p_obj.id_paciente,
                                        data_hora_inicio=ini_orig,
                                        data_hora_fim=ini_orig.replace(hour=h + 1),
                                        status_presenca=StatusPresenca.CANCELADA,
                                        recorrente=True))
                                ini_nova = datetime.combine(nd, time(hh, mm))
                                db().add(AgendaSessao(
                                    id_paciente=p_obj.id_paciente,
                                    data_hora_inicio=ini_nova,
                                    data_hora_fim=ini_nova.replace(hour=hh + 1),
                                    status_presenca=StatusPresenca.AGENDADA,
                                    valor_sessao=p_obj.valor_sessao,
                                    recorrente=False,
                                    remarcada_de=data_d))
                                try:
                                    db().commit()
                                    db().expire_all()
                                except Exception as e:
                                    db().rollback()
                                    flash(f"Erro: {e}", "error")
                                del st.session_state[f"calEd_{uk}"]
                                st.rerun()
    if linhas_pdf:
        st.download_button("Baixar PDF (calendário do mês)",
            gerar_pdf(f"Calendário {int(cal_mes):02d}/{int(cal_ano)}", linhas_pdf),
            file_name="calendario_mes.pdf", mime="application/pdf")

    st.subheader("Sessões pontuais agendadas (editar/excluir)")
    st.caption("Aqui aparecem sessões avulsas criadas pelo botão 'Agendar' acima. "
               "Para alterar horário recorrente fixo, edite o cadastro do paciente.")
    futuras = db().query(AgendaSessao).filter(
        AgendaSessao.data_hora_inicio >= datetime.now(),
        extract("year", AgendaSessao.data_hora_inicio) == int(cal_ano),
        extract("month", AgendaSessao.data_hora_inicio) == int(cal_mes)
    ).order_by(AgendaSessao.data_hora_inicio).limit(50).all()
    if not futuras:
        st.info("Nenhuma sessão agendada.")
    for s in futuras:
        p = db().get(Paciente, s.id_paciente)
        c1, c2, c3 = st.columns([5, 1, 1])
        info = (f"**{p.nome if p else '?'}** — "
                f"{s.data_hora_inicio.strftime('%d/%m/%Y %H:%M')} — "
                f"{s.status_presenca.value}")
        if s.remarcada_de:
            info += (f"  \n_↻ Remarcada de "
                     f"{s.remarcada_de.strftime('%d/%m')}"
                     f"{' — ' + s.remarcada_motivo if s.remarcada_motivo else ''}_")
        c1.markdown(info)
        if c2.button("Editar", key=f"eds_{s.id_sessao}"):
            st.session_state[f"edsess_{s.id_sessao}"] = True
        if c3.button("Excluir", key=f"dls_{s.id_sessao}"):
            db().delete(s); db().commit()
            st.rerun()
        if st.session_state.get(f"edsess_{s.id_sessao}"):
            with st.form(f"fsess_{s.id_sessao}"):
                cc1, cc2 = st.columns(2)
                nd = cc1.date_input("Nova data",
                    value=s.data_hora_inicio.date(),
                    format="DD/MM/YYYY", key=f"nd_{s.id_sessao}")
                nh = cc2.selectbox("Novo horário", FAIXAS_HORARIO,
                    key=f"nh_{s.id_sessao}")
                if st.form_submit_button("Salvar"):
                    hi, _ = nh.split(" - ")
                    h, m = map(int, hi.split(":"))
                    ini = datetime.combine(nd, time(h, m))
                    s.data_hora_inicio = ini
                    s.data_hora_fim = ini.replace(hour=h + 1)
                    db().commit()
                    del st.session_state[f"edsess_{s.id_sessao}"]
                    st.rerun()
    rows = [{"Paciente": (db().get(Paciente, s.id_paciente).nome
                          if db().get(Paciente, s.id_paciente) else "?"),
             "Inicio": s.data_hora_inicio.strftime("%d/%m %H:%M"),
             "Presenca": s.status_presenca.value} for s in futuras]
    if futuras:
        st.download_button("Baixar PDF", gerar_pdf("Próximas Sessões", rows),
            file_name="proximas_sessoes.pdf", mime="application/pdf")
