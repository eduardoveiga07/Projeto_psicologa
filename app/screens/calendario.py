import streamlit as st
from datetime import datetime
from app.screens.shared import (
    db, registrar, mostrar_flash, flash, Indisponibilidade, MotivoIndisp,
    DiaSemana, HORARIOS_INICIO, HORARIOS_FIM
)
from app.services.feriados import feriados_brasil
from app.services.pdf_export import gerar_pdf
from app.services.indisponibilidade import agrupar_em_ranges, formatar_grupo


def tela_calendario():
    mostrar_flash()
    st.header("📅 Calendário do Consultório")
    ABAS = ["Visão geral", "Feriados oficiais",
            "Indisponibilidades (férias/imprevistos)"]
    aba_sel = st.radio("Seção", ABAS, horizontal=True,
                       key="cal_aba", label_visibility="collapsed")
    st.divider()

    if aba_sel == "Visão geral":
        st.caption("Tudo o que afeta o atendimento no ano: feriados oficiais "
                   "+ bloqueios cadastrados (férias, imprevistos).")
        ano_v = st.number_input("Ano", 2025, 2040, datetime.now().year,
                                key="ano_visao")
        # Feriados
        fer = feriados_brasil(int(ano_v))
        eventos = [{"Data": d, "Tipo": t, "Descrição": n}
                   for d, (n, t) in fer.items()]
        # Indisponibilidades do ano
        indisps = db().query(Indisponibilidade).all()
        for r in indisps:
            if r.data.year == int(ano_v):
                # Se motivo "Outro" e ha observacao, usa a obs como motivo
                if r.motivo.value == "Outro" and r.observacao:
                    motivo_label = r.observacao
                    obs_extra = ""
                else:
                    motivo_label = r.motivo.value
                    obs_extra = r.observacao or ""
                desc = (motivo_label +
                        ("" if r.dia_todo else f" ({r.horario})") +
                        (f" — {obs_extra}" if obs_extra else ""))
                eventos.append({"Data": r.data,
                                "Tipo": "Bloqueio (consultório)",
                                "Descrição": desc})
        eventos.sort(key=lambda x: x["Data"])
        linhas_v = [{"Data": e["Data"].strftime("%d/%m/%Y"),
                     "Dia": ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"][e["Data"].weekday()],
                     "Tipo": e["Tipo"], "Descrição": e["Descrição"]}
                    for e in eventos]
        st.dataframe(linhas_v, use_container_width=True, height=600)
        st.download_button("Baixar PDF (visão geral)",
            gerar_pdf(f"Calendário {ano_v} — Visão geral", linhas_v),
            file_name=f"calendario_{ano_v}.pdf", mime="application/pdf")

    elif aba_sel == "Feriados oficiais":
        c1, c2 = st.columns([1, 3])
        ano_f = c1.number_input("Ano", 2025, 2040, datetime.now().year, key="ano_fer")
        tipos = c2.multiselect("Filtrar tipo",
            ["Nacional", "Estadual SP", "Municipal SP"],
            default=["Nacional", "Estadual SP", "Municipal SP"])
        fer = feriados_brasil(int(ano_f))
        linhas = sorted(
            [{"Data": d.strftime("%d/%m/%Y"),
              "Dia da semana": ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"][d.weekday()],
              "Feriado": nome, "Tipo": tipo}
             for d, (nome, tipo) in fer.items() if tipo in tipos],
            key=lambda x: datetime.strptime(x["Data"], "%d/%m/%Y"))
        st.dataframe(linhas, use_container_width=True, height=600)
        st.download_button("Baixar PDF (feriados do ano)",
            gerar_pdf(f"Feriados {ano_f}", linhas),
            file_name=f"feriados_{ano_f}.pdf", mime="application/pdf")
        st.caption("Fontes: Portaria MGI 11.460/2025 (federal), "
                   "Lei 9.497/1997 (estadual SP - 9/jul), "
                   "Lei 14.485/2007 (municipal SP - 25/jan). "
                   "Datas móveis (Carnaval, Páscoa, Corpus Christi) "
                   "calculadas automaticamente até 2040.")

    elif aba_sel == "Indisponibilidades (férias/imprevistos)":
        st.caption("Marque dias/horários em que não vai atender (férias, "
                   "feriado prolongado, imprevisto, compromisso fixo). "
                   "Já entram no cálculo financeiro e na grade de horários.")
        dia_todo = st.checkbox("Dia inteiro", value=True, key="ind_dia")
        recor = st.checkbox("Repetir toda semana (compromisso fixo)",
            value=False, key="ind_rec",
            help="Ex: fisioterapia toda terça 10-14h e quinta 16-18h")
        ci1, ci2 = st.columns(2)
        d_ini = ci1.date_input("De", format="DD/MM/YYYY",
            value=datetime.now().date(), key="ind_de")
        d_fim = ci2.date_input("Até (inclusive)", format="DD/MM/YYYY",
            value=d_ini, min_value=d_ini, key="ind_ate")
        motivo = st.selectbox("Motivo", [m.value for m in MotivoIndisp],
                              key="ind_motivo")
        motivo_outro = ""
        if motivo == "Outro":
            motivo_outro = st.text_input("Especifique o motivo (opcional)",
                key="ind_motivo_outro",
                placeholder="Ex: Fisioterapia, reunião, curso...")

        # Dias da semana selecionados (so se recor)
        DIAS_LISTA = [e.value for e in DiaSemana]
        dias_selecionados = []
        if recor:
            dias_selecionados = st.multiselect(
                "Repetir em qual(is) dia(s) da semana?",
                DIAS_LISTA, default=[DIAS_LISTA[0]], key="ind_dias_sem")

        # Horarios: por-dia se recor+multiplos dias; senao 1 par geral
        horarios_por_dia = {}  # nome_dia -> "HH:MM - HH:MM"
        horario_geral = None
        if not dia_todo:
            if recor and len(dias_selecionados) > 1:
                st.markdown("**Horário de cada dia:**")
                for d_nome in dias_selecionados:
                    ch1, ch2 = st.columns(2)
                    h_das = ch1.selectbox(f"{d_nome} — Das", HORARIOS_INICIO,
                        index=HORARIOS_INICIO.index("13:00")
                            if "13:00" in HORARIOS_INICIO else 0,
                        key=f"ind_das_{d_nome}")
                    h_ate = ch2.selectbox(f"{d_nome} — Até", HORARIOS_FIM,
                        index=HORARIOS_FIM.index("14:00")
                            if "14:00" in HORARIOS_FIM else 0,
                        key=f"ind_ate_{d_nome}")
                    if h_ate <= h_das:
                        st.error(f"{d_nome}: 'Até' deve ser depois de 'Das'.")
                    horarios_por_dia[d_nome] = f"{h_das} - {h_ate}"
            else:
                ch1, ch2 = st.columns(2)
                h_das = ch1.selectbox("Das", HORARIOS_INICIO,
                    index=HORARIOS_INICIO.index("13:00")
                        if "13:00" in HORARIOS_INICIO else 0,
                    key="ind_das")
                h_ate = ch2.selectbox("Até", HORARIOS_FIM,
                    index=HORARIOS_FIM.index("14:00")
                        if "14:00" in HORARIOS_FIM else 0,
                    key="ind_ate_h")
                if h_ate <= h_das:
                    st.error("'Até' deve ser depois de 'Das'.")
                horario_geral = f"{h_das} - {h_ate}"

        with st.form("nova_indisp"):
            obs = st.text_input("Observação (opcional)")
            if st.form_submit_button("Adicionar"):
                if d_fim < d_ini:
                    st.error("Data final anterior à inicial.")
                elif recor and not dias_selecionados:
                    st.error("Selecione ao menos um dia da semana.")
                else:
                    # Valida horarios
                    erro_hr = False
                    if not dia_todo:
                        if horarios_por_dia:
                            for d_nome, hr in horarios_por_dia.items():
                                das, ate = hr.split(" - ")
                                if ate <= das:
                                    erro_hr = True; break
                        elif horario_geral:
                            das, ate = horario_geral.split(" - ")
                            if ate <= das:
                                erro_hr = True
                    if erro_hr:
                        st.error("Corrija os horários (Até deve ser > Das).")
                    else:
                        obs_final = obs
                        if motivo == "Outro" and motivo_outro.strip():
                            obs_final = motivo_outro.strip()
                            if obs:
                                obs_final += f" — {obs}"
                        from datetime import timedelta
                        dias_idx = {"Segunda-feira":0,"Terça-feira":1,
                            "Quarta-feira":2,"Quinta-feira":3,
                            "Sexta-feira":4,"Sábado":5}
                        alvos_idx = ({dias_idx[n] for n in dias_selecionados}
                                     if recor else None)
                        # idx->nome para olhar horario_por_dia
                        idx_para_nome = {dias_idx[n]: n
                                         for n in dias_selecionados}
                        d = d_ini
                        qtd = 0
                        while d <= d_fim:
                            if recor and d.weekday() not in alvos_idx:
                                d += timedelta(days=1); continue
                            if dia_todo:
                                hr = None
                            elif horarios_por_dia:
                                hr = horarios_por_dia[idx_para_nome[
                                    d.weekday()]]
                            else:
                                hr = horario_geral
                            db().add(Indisponibilidade(
                                data=d, dia_todo=dia_todo,
                                horario=hr,
                                motivo=MotivoIndisp(motivo),
                                observacao=obs_final))
                            qtd += 1
                            d += timedelta(days=1)
                        db().commit()
                        registrar(db(), st.session_state.username,
                                  "INDISP_CRIADA",
                                  f"{d_ini}..{d_fim} {motivo}")
                        flash(f"{qtd} bloqueio(s) registrado(s).",
                              "success")
                        st.rerun()

        st.subheader("Bloqueios cadastrados")
        regs = db().query(Indisponibilidade).order_by(
            Indisponibilidade.data.desc()).limit(500).all()
        grupos = agrupar_em_ranges(regs)
        if not grupos:
            st.info("Nenhum bloqueio cadastrado.")
        for g in grupos:
            gkey = f"g_{g['ids'][0]}"
            txt = formatar_grupo(g)
            c1, c2, c3 = st.columns([6, 1, 1])
            c1.write(txt)
            if c2.button("Editar", key=f"edi_{gkey}"):
                st.session_state[f"edi_open_{gkey}"] = True
            if c3.button("Remover", key=f"rmi_{gkey}"):
                for rid in g["ids"]:
                    obj = db().query(Indisponibilidade).get(rid)
                    if obj: db().delete(obj)
                db().commit()
                registrar(db(), st.session_state.username,
                          "INDISP_REMOVIDA",
                          f"{txt} ({len(g['ids'])} dias)")
                flash(f"{len(g['ids'])} bloqueio(s) removido(s).", "success")
                st.rerun()
            if st.session_state.get(f"edi_open_{gkey}"):
                with st.form(f"edi_f_{gkey}"):
                    st.caption("Editar bloqueio (aplica a todos os dias do grupo)")
                    ce1, ce2 = st.columns(2)
                    nv_ini = ce1.date_input("De", value=g["ini"],
                        format="DD/MM/YYYY", key=f"edi_de_{gkey}")
                    nv_fim = ce2.date_input("Até", value=g["fim"],
                        format="DD/MM/YYYY", min_value=nv_ini,
                        key=f"edi_ate_{gkey}")
                    nv_mot = st.selectbox("Motivo",
                        [m.value for m in MotivoIndisp],
                        index=[m.value for m in MotivoIndisp].index(g["motivo"]),
                        key=f"edi_mot_{gkey}")
                    nv_diatd = st.checkbox("Dia inteiro",
                        value=g["dia_todo"], key=f"edi_dt_{gkey}")
                    eh_multi = g.get("padrao") == "semanal_multi"
                    eh_semanal = g.get("padrao") == "semanal"
                    nv_hr = None
                    nv_slots = []  # so para multi: lista de {weekday, horario}
                    DIAS_PT = ["Segunda-feira","Terça-feira","Quarta-feira",
                               "Quinta-feira","Sexta-feira","Sábado","Domingo"]
                    if not nv_diatd and eh_multi:
                        st.markdown("**Horário de cada dia:**")
                        for s in g.get("slots", []):
                            d_nome = s["dia_semana"]
                            cur_das, cur_ate = "13:00", "14:00"
                            if s.get("horario") and " - " in s["horario"]:
                                try:
                                    cur_das, cur_ate = s["horario"].split(" - ")
                                Except Exception:
                                    pass
                            cm1, cm2 = st.columns(2)
                            nd = cm1.selectbox(f"{d_nome} — Das",
                                HORARIOS_INICIO,
                                index=(HORARIOS_INICIO.index(cur_das)
                                       if cur_das in HORARIOS_INICIO else 0),
                                key=f"edi_das_{gkey}_{s['weekday']}")
                            na = cm2.selectbox(f"{d_nome} — Até",
                                HORARIOS_FIM,
                                index=(HORARIOS_FIM.index(cur_ate)
                                       if cur_ate in HORARIOS_FIM else 0),
                                key=f"edi_ate_{gkey}_{s['weekday']}")
                            nv_slots.append({"weekday": s["weekday"],
                                "horario": f"{nd} - {na}"})
                    elif not nv_diatd:
                        cur_das, cur_ate = "13:00", "14:00"
                        if g["horario"] and " - " in g["horario"]:
                            try:
                                cur_das, cur_ate = g["horario"].split(" - ")
                            except Exception:
                                pass
                        ceh1, ceh2 = st.columns(2)
                        nv_das = ceh1.selectbox("Das", HORARIOS_INICIO,
                            index=(HORARIOS_INICIO.index(cur_das)
                                   if cur_das in HORARIOS_INICIO else 0),
                            key=f"edi_das_{gkey}")
                        nv_ate = ceh2.selectbox("Até", HORARIOS_FIM,
                            index=(HORARIOS_FIM.index(cur_ate)
                                   if cur_ate in HORARIOS_FIM else 0),
                            key=f"edi_ate_h_{gkey}")
                        nv_hr = f"{nv_das} - {nv_ate}"
                    nv_obs = st.text_input(
                        "Especifique" if g["motivo"] == "Outro"
                        else "Observação",
                        value=g["obs"] or "",
                        key=f"edi_obs_{gkey}",
                        placeholder=("Ex: Médico, reunião, curso..."
                            if g["motivo"] == "Outro" else ""),
                        help=("Aparece no lugar de 'Outro' nas listagens."
                              if g["motivo"] == "Outro" else None))
                    cb1, cb2 = st.columns(2)
                    if cb1.form_submit_button("Salvar"):
                        erro = False
                        if not nv_diatd and eh_multi:
                            for s in nv_slots:
                                das, ate = s["horario"].split(" - ")
                                if ate <= das:
                                    erro = True; break
                        elif not nv_diatd and nv_ate <= nv_das:
                            erro = True
                        if erro:
                            st.error("Corrija os horários (Até > Das).")
                        else:
                            for rid in g["ids"]:
                                obj = db().query(Indisponibilidade).get(rid)
                                if obj: db().delete(obj)
                            from datetime import timedelta
                            wd_map = ({s["weekday"]: s["horario"]
                                       for s in nv_slots} if eh_multi
                                      else None)
                            wds_alvo = (set(wd_map.keys()) if eh_multi
                                        else ({g["ini"].weekday()}
                                              if eh_semanal else None))
                            d = nv_ini
                            while d <= nv_fim:
                                if wds_alvo is not None \
                                        and d.weekday() not in wds_alvo:
                                    d += timedelta(days=1); continue
                                if nv_diatd:
                                    hr_d = None
                                elif eh_multi:
                                    hr_d = wd_map[d.weekday()]
                                else:
                                    hr_d = nv_hr
                                db().add(Indisponibilidade(
                                    data=d, dia_todo=nv_diatd,
                                    horario=hr_d,
                                    motivo=MotivoIndisp(nv_mot),
                                    observacao=nv_obs))
                                d += timedelta(days=1)
                            db().commit()
                            registrar(db(), st.session_state.username,
                                      "INDISP_EDITADA", formatar_grupo(g))
                            del st.session_state[f"edi_open_{gkey}"]
                            flash("Bloqueio atualizado.", "success")
                            st.rerun()
                    if cb2.form_submit_button("Cancelar"):
                        del st.session_state[f"edi_open_{gkey}"]
                        st.rerun()
