import streamlit as st
from datetime import datetime, date, time
from decimal import Decimal
import json

from app.screens.shared import (
    db, registrar, mostrar_flash, flash, invalidar_cache, FAIXAS_HORARIO, mapa_cached
)
from app.db.models import (
    Paciente, AgendaSessao, ContratoHistorico, ExcecaoHorario,
    TipoContrato, Frequencia, DiaSemana, StatusPaciente, StatusPresenca,
    Indisponibilidade
)
from app.services.feriados import feriados_brasil
from app.services.pdf_export import gerar_pdf

# Importa os validadores de negócio
from app.services.validacao_negocio import (
    validar_telefone, validar_email_paciente, validar_data_nascimento,
    validar_valor_sessao
)


@st.dialog("Confirmar Exclusão de Paciente")
def confirmar_exclusao_paciente(p_id, p_nome):
    st.warning(f"⚠️ Atenção: Você está prestes a excluir permanentemente o(a) paciente **{p_nome}**.")
    st.write("Esta ação é **irreversível**. Ao confirmar, todos os dados do paciente (sessões, histórico de contratos e exceções de horários) serão excluídos definitivamente (exclusão física - LGPD).")
    
    confirmacao_texto = st.text_input("Para prosseguir, digite 'EXCLUIR' no campo abaixo:")
    
    c1, c2 = st.columns(2)
    if c1.button("Confirmar Exclusão", type="primary", disabled=(confirmacao_texto != "EXCLUIR")):
        s = db()
        try:
            s.query(AgendaSessao).filter(AgendaSessao.id_paciente == p_id).delete()
            s.query(ContratoHistorico).filter(ContratoHistorico.id_paciente == p_id).delete()
            s.query(ExcecaoHorario).filter(ExcecaoHorario.id_paciente == p_id).delete()
            p = s.query(Paciente).get(p_id)
            if p:
                s.delete(p)
            s.commit()
            invalidar_cache()
            registrar(s, st.session_state.username, "PACIENTE_EXCLUIDO", "manual")
            flash(f"Paciente '{p_nome}' foi excluído permanentemente.", "success")
        except Exception as e:
            s.rollback()
            flash(f"Erro ao excluir paciente: {str(e)}", "error")
        st.rerun()
        
    if c2.button("Cancelar"):
        st.rerun()


@st.dialog("Exportar Dados do Paciente (LGPD)")
def exportar_paciente_dialog(p_id, p_nome):
    st.write(f"Gerando relatório completo de portabilidade para o(a) paciente **{p_nome}**.")
    st.write("Isso inclui dados cadastrais, histórico de vigência de contratos, exceções de horários e sessões agendadas/realizadas.")
    
    s = db()
    p = s.query(Paciente).get(p_id)
    if not p:
        st.error("Paciente não encontrado.")
        return
        
    contratos = s.query(ContratoHistorico).filter(ContratoHistorico.id_paciente == p_id).all()
    sessoes = s.query(AgendaSessao).filter(AgendaSessao.id_paciente == p_id).all()
    excecoes = s.query(ExcecaoHorario).filter(ExcecaoHorario.id_paciente == p_id).all()
    
    def json_serial(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError(f"Type {type(obj)} not serializable")
        
    dados_exportacao = {
        "exportado_em": datetime.now().isoformat(),
        "paciente": {
            "id_paciente": str(p.id_paciente),
            "nome": p.nome,
            "telefone": p.telefone,
            "email": p.email,
            "data_nascimento": p.data_nascimento.isoformat() if p.data_nascimento else None,
            "tipo_contrato": p.tipo_contrato.value if p.tipo_contrato else None,
            "valor_sessao": float(p.valor_sessao),
            "frequencia": p.frequencia.value if p.frequencia else None,
            "dias_semana": p.dias_semana,
            "horario_atendimento": p.horario_atendimento,
            "status": p.status.value if p.status else None,
            "ativo_desde": p.ativo_desde.isoformat() if p.ativo_desde else None,
            "em_avaliacao": p.em_avaliacao,
            "data_desativacao": p.data_desativacao.isoformat() if p.data_desativacao else None,
            "criado_em": p.criado_em.isoformat() if p.criado_em else None
        },
        "historico_contratos": [
            {
                "vigente_de": c.vigente_de.isoformat() if c.vigente_de else None,
                "vigente_ate": c.vigente_ate.isoformat() if c.vigente_ate else None,
                "frequencia": c.frequencia.value if c.frequencia else None,
                "valor_sessao": float(c.valor_sessao),
                "dias_semana": c.dias_semana,
                "semana_do_mes": c.semana_do_mes,
                "paridade_quinzenal": c.paridade_quinzenal,
                "sessoes_mes_custom": c.sessoes_mes_custom,
                "criado_em": c.criado_em.isoformat() if c.criado_em else None
            } for c in contratos
        ],
        "excecoes_horario": [
            {
                "tipo": e.tipo,
                "semana_do_mes": e.semana_do_mes,
                "data_especifica": e.data_especifica.isoformat() if e.data_especifica else None,
                "dia_alvo": e.dia_alvo,
                "horario_alvo": e.horario_alvo
            } for e in excecoes
        ],
        "sessoes": [
            {
                "data_hora_inicio": s_sess.data_hora_inicio.isoformat() if s_sess.data_hora_inicio else None,
                "data_hora_fim": s_sess.data_hora_fim.isoformat() if s_sess.data_hora_fim else None,
                "status_presenca": s_sess.status_presenca.value if s_sess.status_presenca else None,
                "status_pagamento": s_sess.status_pagamento.value if s_sess.status_pagamento else None,
                "confirmacao_enviada": s_sess.confirmacao_enviada,
                "remarcada_de": s_sess.remarcada_de.isoformat() if s_sess.remarcada_de else None,
                "remarcada_motivo": s_sess.remarcada_motivo
            } for s_sess in sessoes
        ]
    }
    
    json_str = json.dumps(dados_exportacao, default=json_serial, indent=2, ensure_ascii=False)
    
    st.success("Relatório de portabilidade compilado com sucesso!")
    st.download_button(
        label="Baixar Arquivo JSON",
        data=json_str,
        file_name=f"portabilidade_lgpd_{p.nome.lower().replace(' ', '_')}.json",
        mime="application/json"
    )
    if st.button("Fechar", key="fechar_export_dialog"):
        st.rerun()


def tela_cadastro():
    mostrar_flash()
    st.header("Cadastro de Pacientes")

    tipo = st.radio("Tipo de paciente", ["Recorrente (ativo)",
        "Avaliação Inicial (sessão única)"], horizontal=True)
    em_aval = tipo.startswith("Avaliação")

    if em_aval:
        # Data e horário da avaliação:
        st.markdown("**Data e horário da avaliação:**")
        cd1, cd2 = st.columns(2)
        data_av = cd1.date_input("Data da avaliação",
            value=datetime.now().date(), format="DD/MM/YYYY", key="av_data")
        dur_av = cd2.selectbox("Duração", ["30 minutos", "1 hora"],
            key="av_dur")
        # Calcula horários LIVRES nesse dia
        from app.services.ocupacao import faixas_sobrepoem
        # Faixas 30min ou 60min
        if dur_av == "30 minutos":
            faixas_pos = []
            for h in range(7, 22):
                for m in (0, 30):
                    if h == 21 and m == 30: break
                    fim_h = h if m == 0 else h + 1
                    fim_m = 30 if m == 0 else 0
                    faixas_pos.append(f"{h:02d}:{m:02d} - {fim_h:02d}:{fim_m:02d}")
        else:
            faixas_pos = FAIXAS_HORARIO  # 1h
        # Bloqueios e feriados
        fer = feriados_brasil(data_av.year).get(data_av)
        ind = db().query(Indisponibilidade).filter(
            Indisponibilidade.data == data_av).all()
        bloq_dia_todo = any(r.dia_todo for r in ind)
        bloq_horarios = [r.horario for r in ind if not r.dia_todo and r.horario]
        if fer:
            st.error(f"🔴 {data_av.strftime('%d/%m/%Y')} é feriado ({fer[1]}): {fer[0]}.")
        if bloq_dia_todo:
            st.error(f"🟠 Psicóloga indisponível o dia todo.")
            faixas_livres = []
        else:
            # ocupação por recorrências
            mapa = mapa_cached(data_av.year, data_av.month)
            ocupados_no_dia = list(mapa.get(data_av, {}).keys()) + bloq_horarios
            faixas_livres = [f for f in faixas_pos
                             if not any(faixas_sobrepoem(f, o)
                                        for o in ocupados_no_dia)]
        if not faixas_livres:
            st.warning("Nenhum horário livre nessa data. Escolha outra.")
            hr_av = None
        else:
            hr_av = cd1.selectbox(f"Horário livre ({len(faixas_livres)} opções)",
                faixas_livres, key="av_hr")

        _kfa = st.session_state.get("form_seed_av", 0)
        # "Sera cobrada" FORA do form para reagir
        paga = st.checkbox("Avaliação será cobrada", value=True, key="av_paga")
        with st.form(f"nova_aval_{_kfa}"):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome")
            tel = c2.text_input("Telefone (DDI+DDD)")
            email_p = c1.text_input("Email (opcional, para NF)")
            nasc = c2.date_input("Data de nascimento",
                min_value=date(1930, 1, 1), format="DD/MM/YYYY")
            valor_av = 0.0
            if paga:
                valor_av = c1.number_input("Valor da avaliação",
                    min_value=0.0, step=10.0)
            if st.form_submit_button("Cadastrar avaliação"):
                faltando = []
                if not nome: faltando.append("nome")
                if not tel: faltando.append("telefone")
                if not email_p: faltando.append("email")
                if not nasc: faltando.append("data de nascimento")
                if not hr_av: faltando.append("horário disponível")
                if faltando and not st.session_state.get("conf_aval"):
                    st.session_state.conf_aval = True
                    st.warning(f"⚠️ Faltam: {', '.join(faltando)}. "
                               "Tem certeza? Clique em **Cadastrar avaliação** "
                               "novamente para confirmar.")
                else:
                    # Validacoes de negocio
                    ok_tel, res_tel = validar_telefone(tel)
                    ok_email, res_email = validar_email_paciente(email_p)
                    ok_nasc, res_nasc = validar_data_nascimento(nasc)
                    ok_val, res_val = validar_valor_sessao(Decimal(str(valor_av)), em_avaliacao=True)
                    
                    if not ok_tel:
                        st.error(f"Erro no Telefone: {res_tel}")
                    elif not ok_email:
                        st.error(f"Erro no E-mail: {res_email}")
                    elif not ok_nasc:
                        st.error(f"Erro na Data de Nascimento: {res_nasc}")
                    elif not ok_val:
                        st.error(f"Erro no Valor: {res_val}")
                    else:
                        try:
                            novo_pac = Paciente(
                                nome=nome, telefone=res_tel, email=res_email or None,
                                data_nascimento=nasc,
                                tipo_contrato=TipoContrato.AVULSO,
                                valor_sessao=Decimal(str(valor_av)),
                                frequencia=Frequencia.PERSONALIZADO,
                                horario_atendimento="",
                                em_avaliacao=True, avaliacao_paga=paga,
                                valor_avaliacao=Decimal(str(valor_av)),
                                status=StatusPaciente.ATIVO)
                            db().add(novo_pac)
                            db().flush()
                            if hr_av:
                                hi, fim = hr_av.split(" - ")
                                h, m = map(int, hi.split(":"))
                                hf, mf = map(int, fim.split(":"))
                                ini = datetime.combine(data_av, time(h, m))
                                fim_dt = datetime.combine(data_av, time(hf, mf))
                                # Limpa qualquer sessão preexistente no slot:
                                # - CANCELADA antiga (exceções/exclusões do calendário)
                                # - Órfã de paciente excluído
                                existentes = db().query(AgendaSessao).filter(
                                    AgendaSessao.data_hora_inicio == ini).all()
                                for ja in existentes:
                                    if ja.status_presenca == StatusPresenca.CANCELADA:
                                        db().delete(ja)
                                    else:
                                        # Verifica se paciente ainda existe
                                        p_ext = db().query(Paciente).filter(
                                            Paciente.id_paciente == ja.id_paciente).first()
                                        if not p_ext:
                                            db().delete(ja)
                                db().flush()
                                db().add(AgendaSessao(
                                    id_paciente=novo_pac.id_paciente,
                                    data_hora_inicio=ini, data_hora_fim=fim_dt,
                                    status_presenca=StatusPresenca.AGENDADA))
                            db().commit()
                            st.session_state.pop("conf_aval", None)
                            st.success(f"{nome} cadastrado(a). Sessão em "
                                       f"{data_av.strftime('%d/%m/%Y')} {hr_av}.")
                            st.session_state["form_seed_av"] = _kfa + 1
                            st.rerun()
                        except Exception as e:
                            db().rollback()
                            msg = str(e)
                            if "data_hora_inicio" in msg or "unique" in msg.lower():
                                st.error(f"⚠️ Já existe uma sessão em "
                                    f"{data_av.strftime('%d/%m/%Y')} {hr_av}. "
                                    "Escolha outro horário.")
                            else:
                                st.error(f"Erro: {type(e).__name__}")
    else:
        freq = st.selectbox("Frequência", [e.value for e in Frequencia])
        dias_opcoes = [e.value for e in DiaSemana]
        sessoes_custom = None
        semana_mes = None
        paridade_q = None
        if freq == Frequencia.DUAS_SEMANA.value:
            st.caption("Selecione 2 dias da semana.")
            dias_sel = st.multiselect("Dias", dias_opcoes, max_selections=2)
        elif freq == Frequencia.TRES_SEMANA.value:
            st.caption("Selecione 3 dias da semana.")
            dias_sel = st.multiselect("Dias", dias_opcoes, max_selections=3)
        elif freq == Frequencia.PERSONALIZADO.value:
            dias_sel = st.multiselect("Dias", dias_opcoes)
            sessoes_custom = st.number_input("Sessões/mês",
                min_value=1, max_value=31, value=4)
        elif freq == Frequencia.MENSAL.value:
            dias_sel = [st.selectbox("Dia de atendimento", dias_opcoes)]
            semana_mes = st.selectbox("Qual semana do mês?",
                [1, 2, 3, 4, 5],
                format_func=lambda n: {1: "1ª", 2: "2ª", 3: "3ª",
                                       4: "4ª", 5: "Última"}[n])
        elif freq == Frequencia.QUINZENAL.value:
            dias_sel = [st.selectbox("Dia de atendimento", dias_opcoes)]
            paridade_q = st.selectbox("Quinzenal — semanas",
                ["impar", "par"],
                format_func=lambda v: "Ímpares (1ª, 3ª, 5ª)" if v == "impar"
                                       else "Pares (2ª, 4ª)")
        else:
            dias_sel = [st.selectbox("Dia de atendimento", dias_opcoes)]

        _kf = st.session_state.get("form_seed", 0)
        with st.form(f"novo_paciente_{_kf}"):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome")
            tel = c2.text_input("Telefone (DDI+DDD)")
            email_p = c1.text_input("Email (opcional, para NF)")
            nasc = c2.date_input("Data de nascimento",
                min_value=date(1930, 1, 1), format="DD/MM/YYYY")
            valor = c1.number_input("Valor por sessão",
                min_value=0.0, step=10.0)
            contrato = c2.selectbox("Contrato",
                [e.value for e in TipoContrato])
            ativo_desde = c1.date_input("Ativo desde (início da recorrência)",
                value=datetime.now().date(), format="DD/MM/YYYY")
            horarios = {}
            if dias_sel:
                st.markdown("**Horário de cada dia:**")
                for d in dias_sel:
                    horarios[d] = st.selectbox(f"Horário — {d}",
                        FAIXAS_HORARIO, key=f"h_{d}")
            if st.form_submit_button("Cadastrar"):
                if not dias_sel:
                    st.error("Selecione ao menos um dia.")
                else:
                    # Checa campos vazios ANTES de salvar.
                    faltando = []
                    if not nome: faltando.append("nome")
                    if not tel: faltando.append("telefone")
                    if not email_p: faltando.append("email")
                    if not valor or valor == 0: faltando.append("valor por sessão")
                    if not nasc: faltando.append("data de nascimento")
                    if faltando and not st.session_state.get("conf_rec"):
                        st.session_state.conf_rec = True
                        st.warning(f"⚠️ Faltam: {', '.join(faltando)}. "
                                   "Tem certeza? Clique em **Cadastrar** "
                                   "novamente para confirmar.")
                    else:
                        # Validacoes de negocio
                        ok_tel, res_tel = validar_telefone(tel)
                        ok_email, res_email = validar_email_paciente(email_p)
                        ok_nasc, res_nasc = validar_data_nascimento(nasc)
                        ok_val, res_val = validar_valor_sessao(Decimal(str(valor)), em_avaliacao=False)
                        
                        if not ok_tel:
                            st.error(f"Erro no Telefone: {res_tel}")
                        elif not ok_email:
                            st.error(f"Erro no E-mail: {res_email}")
                        elif not ok_nasc:
                            st.error(f"Erro na Data de Nascimento: {res_nasc}")
                        elif not ok_val:
                            st.error(f"Erro no Valor: {res_val}")
                        else:
                            # Checa conflitos ANTES de salvar (sem persistir)
                            novo_temp = Paciente(
                                nome=nome, telefone=res_tel, email=res_email or None,
                                data_nascimento=nasc,
                                tipo_contrato=TipoContrato(contrato),
                                valor_sessao=Decimal(str(valor)),
                                frequencia=Frequencia(freq),
                                dia_atendimento=DiaSemana(dias_sel[0]),
                                dias_semana=",".join(dias_sel),
                                horario_atendimento=",".join(f"{d}={h}"
                                    for d, h in horarios.items()),
                                sessoes_mes_custom=int(sessoes_custom) if sessoes_custom else None,
                                semana_do_mes=semana_mes,
                                paridade_quinzenal=paridade_q,
                                ativo_desde=ativo_desde,
                                em_avaliacao=False,
                                status=StatusPaciente.ATIVO)
                            from app.services.ocupacao import detectar_conflitos
                            hj = datetime.now().date()
                            r_test = detectar_conflitos(db(), novo_temp,
                                hj.year, hj.month)
                            if r_test["conflitos"] and not st.session_state.get("conf_conflito"):
                                st.session_state.conf_conflito = True
                                st.error(f"⚠️ {len(r_test['conflitos'])} conflito(s) "
                                         "detectado(s):")
                                for dt, hr, nomes in r_test["conflitos"][:5]:
                                    st.write(f"- {dt.strftime('%d/%m/%Y')} {hr} "
                                             f"— {', '.join(nomes)}")
                                st.warning("Cadastrar mesmo assim? Clique em "
                                           "**Cadastrar** novamente para confirmar.")
                            else:
                                db().add(novo_temp)
                                db().commit()
                                st.session_state.pop("conf_rec", None)
                                st.session_state.pop("conf_conflito", None)
                                novo_p = db().query(Paciente).filter(
                                    Paciente.nome == nome).order_by(
                                    Paciente.criado_em.desc()).first()
                                # Abre 1o periodo do historico de contrato
                                from app.services.contrato import abrir_periodo
                                abrir_periodo(db(), novo_p,
                                    novo_p.ativo_desde or datetime.now().date())
                                hj = datetime.now().date()
                                r = detectar_conflitos(db(), novo_p, hj.year, hj.month,
                                                       id_excluir=novo_p.id_paciente)
                                from app.services.ocupacao import sugerir_horarios
                                sugs = sugerir_horarios(db(), novo_p, hj.year,
                                    hj.month, FAIXAS_HORARIO,
                                    id_excluir=novo_p.id_paciente)
                                st.session_state["ultimo_cad"] = {
                                    "nome": nome, "conflitos": r["conflitos"],
                                    "livres": len(r["datas_livres"]),
                                    "freq": novo_p.frequencia.value,
                                    "paridade": novo_p.paridade_quinzenal,
                                    "dia": (novo_p.dias_semana or "").split(",")[0],
                                    "sug_mesmo_dia": sugs["mesmo_dia"],
                                    "sug_outros_dias": sugs["outros_dias"]}
                                st.session_state["form_seed"] = _kf + 1
                                st.rerun()

    # Mostra resultado do ultimo cadastro (apos rerun)
    if st.session_state.get("ultimo_cad"):
        uc = st.session_state["ultimo_cad"]
        st.success(f"✅ {uc['nome']} cadastrado.")
        if uc["conflitos"]:
            st.warning(f"⚠️ {len(uc['conflitos'])} conflito(s) no mês atual:")
            for dt, hr, nomes in uc["conflitos"]:
                st.write(f"- **{dt.strftime('%d/%m/%Y')}** {hr} — "
                         f"já ocupado por: {', '.join(nomes)}")
            st.info(f"✅ {uc['livres']} data(s) sem conflito.")
            st.markdown("**💡 Sugestões priorizadas:**")
            if uc["freq"] == "Quinzenal":
                outra = "par" if uc["paridade"] == "impar" else "impar"
                st.write(f"- ⚡ Trocar paridade quinzenal para **{outra}** "
                         f"(alterna sem conflito)")
            if uc.get("sug_mesmo_dia"):
                st.write(f"- 🕐 Horários livres em **{uc['dia']}**: "
                         f"{', '.join(uc['sug_mesmo_dia'])}")
            if uc.get("sug_outros_dias"):
                st.write(f"- 📅 Mesmo horário disponível em outros dias: "
                         f"{', '.join(uc['sug_outros_dias'])}")
            st.caption("Use **Editar** abaixo para aplicar uma das sugestões.")
        else:
            flash(f"✅ Todas as {uc['livres']} datas do mês estão livres.", "info")
        if st.button("Fechar aviso", key="fechar_uc"):
            del st.session_state["ultimo_cad"]
            st.rerun()

    # Listagens OCULTAS atras de expanders.
    with st.expander("📋 Ver pacientes em Avaliação Inicial"):
        avals = db().query(Paciente).filter(
            Paciente.em_avaliacao == True,  # noqa: E712
            Paciente.status == StatusPaciente.ATIVO).all()
        if not avals:
            st.info("Nenhum paciente em avaliação.")
        for p in avals:
            # Busca sessão agendada para mostrar data/horário
            sess_av = db().query(AgendaSessao).filter(
                AgendaSessao.id_paciente == p.id_paciente).order_by(
                AgendaSessao.data_hora_inicio.desc()).first()
            quando = ""
            if sess_av:
                dur_min = int((sess_av.data_hora_fim - sess_av.data_hora_inicio).total_seconds() // 60)
                quando = (f" — 📅 {sess_av.data_hora_inicio.strftime('%d/%m/%Y %H:%M')}"
                          f" ({dur_min}min)")
            c1, c2, c3, c4, c5, c6 = st.columns([4, 2, 0.8, 0.8, 0.8, 0.8])
            c1.markdown(f"**{p.nome}** — 📱 {p.telefone}{quando}  \n"
                        f"📧 `{p.email or '—'}` | 🎂 "
                        f"{p.data_nascimento.strftime('%d/%m/%Y') if p.data_nascimento else '—'}")
            c2.write(f"R$ {float(p.valor_avaliacao or 0):.2f} "
                     f"({'cobrada' if p.avaliacao_paga else 'gratuita'})")
            if c3.button("Editar", key=f"edav_{p.id_paciente}"):
                st.session_state[f"edit_av_{p.id_paciente}"] = True
            if c4.button("Recorrente", key=f"rec_{p.id_paciente}"):
                st.session_state[f"converter_{p.id_paciente}"] = True
            if c5.button("Excluir", key=f"delav_{p.id_paciente}"):
                confirmar_exclusao_paciente(p.id_paciente, p.nome)
            if c6.button("📥", key=f"expav_{p.id_paciente}", help="Exportar todos os dados do paciente (Portabilidade/LGPD)"):
                exportar_paciente_dialog(p.id_paciente, p.nome)
            # Form de edição
            if st.session_state.get(f"edit_av_{p.id_paciente}"):
                with st.form(f"feav_{p.id_paciente}"):
                    cc1, cc2 = st.columns(2)
                    n_nome = cc1.text_input("Nome", value=p.nome)
                    n_tel = cc2.text_input("Telefone", value=p.telefone)
                    n_email = cc1.text_input("Email", value=p.email or "")
                    n_nasc = cc2.date_input("Nascimento",
                        value=p.data_nascimento,
                        min_value=date(1930,1,1), format="DD/MM/YYYY")
                    n_paga = cc1.checkbox("Cobrada", value=p.avaliacao_paga)
                    n_val = cc2.number_input("Valor",
                        min_value=0.0, value=float(p.valor_avaliacao or 0))
                    bb1, bb2 = st.columns(2)
                    if bb1.form_submit_button("Salvar"):
                        # Validacoes de negocio
                        ok_tel, res_tel = validar_telefone(n_tel)
                        ok_email, res_email = validar_email_paciente(n_email)
                        ok_nasc, res_nasc = validar_data_nascimento(n_nasc)
                        ok_val, res_val = validar_valor_sessao(Decimal(str(n_val)), em_avaliacao=True)
                        
                        if not ok_tel:
                            st.error(f"Erro no Telefone: {res_tel}")
                        elif not ok_email:
                            st.error(f"Erro no E-mail: {res_email}")
                        elif not ok_nasc:
                            st.error(f"Erro na Data de Nascimento: {res_nasc}")
                        elif not ok_val:
                            st.error(f"Erro no Valor: {res_val}")
                        else:
                            p.nome = n_nome; p.telefone = res_tel; p.email = res_email or None
                            p.data_nascimento = n_nasc
                            p.avaliacao_paga = n_paga
                            p.valor_avaliacao = Decimal(str(n_val))
                            p.valor_sessao = Decimal(str(n_val))
                            db().commit()
                            del st.session_state[f"edit_av_{p.id_paciente}"]
                            st.rerun()
                    if bb2.form_submit_button("Cancelar"):
                        del st.session_state[f"edit_av_{p.id_paciente}"]
                        st.rerun()
            if st.session_state.get(f"converter_{p.id_paciente}"):
                with st.form(f"conv_{p.id_paciente}"):
                    st.write("**Configurar como recorrente:**")
                    fq = st.selectbox("Frequência",
                        [e.value for e in Frequencia], key=f"fq_{p.id_paciente}")
                    dia = st.selectbox("Dia",
                        [e.value for e in DiaSemana], key=f"di_{p.id_paciente}")
                    hr = st.selectbox("Horário", FAIXAS_HORARIO,
                        key=f"hr_{p.id_paciente}")
                    vl = st.number_input("Valor por sessão",
                        min_value=0.0, value=float(p.valor_sessao or 0),
                        step=10.0, key=f"vl_{p.id_paciente}")
                    ad = st.date_input("Ativo desde",
                        value=datetime.now().date(),
                        format="DD/MM/YYYY", key=f"ad_{p.id_paciente}")
                    if st.form_submit_button("Converter"):
                        # Validacoes de negocio
                        ok_val, res_val = validar_valor_sessao(Decimal(str(vl)), em_avaliacao=False)
                        
                        if not ok_val:
                            st.error(f"Erro no Valor: {res_val}")
                        else:
                            p.em_avaliacao = False
                            p.frequencia = Frequencia(fq)
                            p.dia_atendimento = DiaSemana(dia)
                            p.dias_semana = dia
                            p.horario_atendimento = f"{dia}={hr}"
                            p.valor_sessao = Decimal(str(vl))
                            p.ativo_desde = ad
                            db().commit()
                            from app.services.contrato import abrir_periodo
                            abrir_periodo(db(), p, ad)
                            del st.session_state[f"converter_{p.id_paciente}"]
                            flash(f"{p.nome} agora é recorrente.", "success")
                            st.rerun()

    with st.expander("💤 Pacientes inativos (sem retorno)"):
        inativos = db().query(Paciente).filter(
            Paciente.status == StatusPaciente.INATIVO).all()
        if not inativos:
            st.info("Nenhum paciente inativo.")
        st.caption("Pacientes inativos por mais de 2 anos são excluídos "
                   "automaticamente do banco (LGPD - retenção mínima).")
        for p in inativos:
            c1, c2, c3, c4 = st.columns([5, 0.8, 0.8, 0.8])
            dd = p.data_desativacao.strftime("%d/%m/%Y") if p.data_desativacao else "?"
            c1.write(f"**{p.nome}** — {p.telefone} — inativo desde {dd}")
            if c2.button("Reativar", key=f"rea_{p.id_paciente}"):
                p.status = StatusPaciente.ATIVO
                p.data_desativacao = None
                db().commit()
                registrar(db(), st.session_state.username,
                          "PACIENTE_REATIVADO", "")
                st.rerun()
            if c3.button("Excluir", key=f"del_{p.id_paciente}"):
                confirmar_exclusao_paciente(p.id_paciente, p.nome)
            if c4.button("📥", key=f"expin_{p.id_paciente}", help="Exportar todos os dados do paciente (Portabilidade/LGPD)"):
                exportar_paciente_dialog(p.id_paciente, p.nome)

    with st.expander("👥 Ver pacientes ativos recorrentes"):
        ativos = db().query(Paciente).filter(
            Paciente.status == StatusPaciente.ATIVO,
            Paciente.em_avaliacao == False).all()  # noqa: E712
        if not ativos:
            st.info("Nenhum paciente recorrente.")
        for p in ativos:
            c1, c2, c3, c4, c5 = st.columns([5, 0.8, 0.8, 0.8, 0.8])
            ad = p.ativo_desde.strftime("%d/%m/%Y") if p.ativo_desde else "?"
            nasc = p.data_nascimento.strftime("%d/%m/%Y") if p.data_nascimento else "?"
            # Descricao da recorrencia, formato amigavel
            if p.frequencia == Frequencia.MENSAL and p.semana_do_mes:
                pos = ['1ª','2ª','3ª','4ª','Última'][min(p.semana_do_mes-1,4)]
                rec = f"Mensal — {pos} {p.dias_semana or ''} do mês"
            elif p.frequencia == Frequencia.QUINZENAL and p.paridade_quinzenal:
                par = "ímpares" if p.paridade_quinzenal == "impar" else "pares"
                rec = f"Quinzenal ({p.dias_semana or ''}, semanas {par})"
            else:
                rec = f"{p.frequencia.value} — {p.dias_semana or ''}"
            # Extrai horario do formato "Dia=HH:MM - HH:MM"
            hr_str = p.horario_atendimento or ""
            if "=" in hr_str:
                hr_str = hr_str.split("=", 1)[1].strip()
            valor_br = f"R$ {float(p.valor_sessao):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            # Resumo das excecoes para a linha do paciente
            excs_p = db().query(ExcecaoHorario).filter(
                ExcecaoHorario.id_paciente == p.id_paciente).all()
            exc_resumo = ""
            if excs_p:
                partes = []
                for e in excs_p:
                    if e.tipo == "recorrente":
                        rs = {1:"1ª",2:"2ª",3:"3ª",4:"4ª",5:"Última"}.get(
                            e.semana_do_mes, "?")
                        partes.append(f"{rs} sem.→{e.dia_alvo} {e.horario_alvo}")
                    else:
                        partes.append(f"{e.data_especifica.strftime('%d/%m')}→"
                                      f"{e.dia_alvo} {e.horario_alvo}")
                exc_resumo = f"  \n📅 **Exceções:** {' | '.join(partes)}"
            c1.markdown(f"**{p.nome}** &nbsp;|&nbsp; 📱 {p.telefone} &nbsp;|&nbsp; "
                f"Email: `{p.email or '—'}` &nbsp;|&nbsp; 🎂 {nasc}  \n"
                f"{rec} — {hr_str} — {valor_br}/sessão — ativo desde {ad}"
                + exc_resumo)
            if p.email and c2.button("✉️", key=f"cp_{p.id_paciente}",
                                     help="Copiar email"):
                st.session_state[f"showmail_{p.id_paciente}"] = True
            if st.session_state.get(f"showmail_{p.id_paciente}"):
                st.code(p.email, language=None)
                st.caption("Copie acima e cole no seu cliente de email.")
            if c3.button("Editar", key=f"ed_{p.id_paciente}"):
                st.session_state[f"editar_{p.id_paciente}"] = True
            if c4.button("Desativar", key=f"des_{p.id_paciente}"):
                p.status = StatusPaciente.INATIVO
                p.data_desativacao = datetime.now().date()
                db().commit()
                registrar(db(), st.session_state.username,
                          "PACIENTE_DESATIVADO", "")
                st.rerun()
            if c5.button("📥", key=f"exp_{p.id_paciente}", help="Exportar todos os dados do paciente (Portabilidade/LGPD)"):
                exportar_paciente_dialog(p.id_paciente, p.nome)
            if st.session_state.get(f"editar_{p.id_paciente}"):
                # Frequencia FORA do form para reagir imediatamente
                nv_freq = st.selectbox("Frequência",
                    [e.value for e in Frequencia],
                    index=[e.value for e in Frequencia].index(p.frequencia.value),
                    key=f"nfq_{p.id_paciente}")
                nv_semana = None
                nv_paridade = None
                if nv_freq == Frequencia.MENSAL.value:
                    nv_semana = st.selectbox("Semana do mês",
                        [1, 2, 3, 4, 5],
                        index=(p.semana_do_mes or 1) - 1
                            if (p.semana_do_mes or 1) <= 5 else 0,
                        format_func=lambda n: {1: "1ª", 2: "2ª", 3: "3ª",
                                               4: "4ª", 5: "Última"}[n],
                        key=f"nsem_{p.id_paciente}")
                elif nv_freq == Frequencia.QUINZENAL.value:
                    nv_paridade = st.selectbox("Quinzenal",
                        ["impar", "par"],
                        index=0 if (p.paridade_quinzenal or "impar") == "impar" else 1,
                        format_func=lambda v: "Ímpares" if v == "impar" else "Pares",
                        key=f"npar_{p.id_paciente}")
                with st.form(f"edf_{p.id_paciente}"):
                    cc1, cc2 = st.columns(2)
                    nv_nome = cc1.text_input("Nome", value=p.nome,
                        key=f"nn_{p.id_paciente}")
                    nv_tel = cc2.text_input("Telefone", value=p.telefone,
                        key=f"nt_{p.id_paciente}")
                    nv_email = cc1.text_input("Email", value=p.email or "",
                        key=f"ne_{p.id_paciente}")
                    nv_nasc = cc2.date_input("Nascimento",
                        value=p.data_nascimento, min_value=date(1930, 1, 1),
                        format="DD/MM/YYYY", key=f"nb_{p.id_paciente}")
                    nv_dia = cc1.selectbox("Dia",
                        [e.value for e in DiaSemana],
                        index=[e.value for e in DiaSemana].index(
                            (p.dias_semana or "Segunda-feira").split(",")[0]),
                        key=f"ndi_{p.id_paciente}")
                    nv_hr = cc1.selectbox("Horário", FAIXAS_HORARIO,
                        key=f"nhr_{p.id_paciente}")
                    nv_vl = cc2.number_input("Valor por sessão",
                        min_value=0.0, value=float(p.valor_sessao),
                        step=10.0, key=f"nvl_{p.id_paciente}")
                    nv_ad = cc1.date_input("Ativo desde",
                        value=p.ativo_desde or datetime.now().date(),
                        format="DD/MM/YYYY", key=f"nad_{p.id_paciente}")
                    cb1, cb2 = st.columns(2)
                    if cb1.form_submit_button("Salvar alterações"):
                        # Validacoes de negocio
                        ok_tel, res_tel = validar_telefone(nv_tel)
                        ok_email, res_email = validar_email_paciente(nv_email)
                        ok_nasc, res_nasc = validar_data_nascimento(nv_nasc)
                        ok_val, res_val = validar_valor_sessao(Decimal(str(nv_vl)), em_avaliacao=False)
                        
                        if not ok_tel:
                            st.error(f"Erro no Telefone: {res_tel}")
                        elif not ok_email:
                            st.error(f"Erro no E-mail: {res_email}")
                        elif not ok_nasc:
                            st.error(f"Erro na Data de Nascimento: {res_nasc}")
                        elif not ok_val:
                            st.error(f"Erro no Valor: {res_val}")
                        else:
                            # Captura estado antigo para detectar mudanca de contrato
                            antigo = dict(
                                frequencia=p.frequencia,
                                valor_sessao=p.valor_sessao,
                                dias_semana=p.dias_semana,
                                semana_do_mes=p.semana_do_mes,
                                paridade_quinzenal=p.paridade_quinzenal,
                            )
                            p.nome = nv_nome
                            p.telefone = res_tel
                            p.email = res_email or None
                            p.data_nascimento = nv_nasc
                            p.dia_atendimento = DiaSemana(nv_dia)
                            p.frequencia = Frequencia(nv_freq)
                            p.semana_do_mes = nv_semana
                            p.paridade_quinzenal = nv_paridade
                            p.dias_semana = nv_dia
                            p.horario_atendimento = f"{nv_dia}={nv_hr}"
                            p.valor_sessao = Decimal(str(nv_vl))
                            p.ativo_desde = nv_ad
                            db().commit()
                            # Se algum campo de contrato mudou, abre novo periodo
                            mudou = (
                                antigo["frequencia"] != p.frequencia or
                                Decimal(str(antigo["valor_sessao"])) != p.valor_sessao or
                                (antigo["dias_semana"] or "") != (p.dias_semana or "") or
                                antigo["semana_do_mes"] != p.semana_do_mes or
                                antigo["paridade_quinzenal"] != p.paridade_quinzenal
                            )
                            if mudou:
                                from app.services.contrato import abrir_periodo
                                abrir_periodo(db(), p, datetime.now().date())
                            del st.session_state[f"editar_{p.id_paciente}"]
                            registrar(db(), st.session_state.username,
                                      "PACIENTE_EDITADO", "alteracao de cadastro")
                            # Detectar conflitos apos edicao
                            from app.services.ocupacao import detectar_conflitos
                            hj = datetime.now().date()
                            r = detectar_conflitos(db(), p, hj.year, hj.month,
                                                   id_excluir=p.id_paciente)
                            st.session_state["ultimo_cad"] = {
                                "nome": p.nome, "conflitos": r["conflitos"],
                                "livres": len(r["datas_livres"]),
                                "freq": p.frequencia.value,
                                "paridade": p.paridade_quinzenal,
                                "dia": (p.dias_semana or "").split(",")[0]}
                            st.rerun()
                    if cb2.form_submit_button("Cancelar"):
                        del st.session_state[f"editar_{p.id_paciente}"]
                        st.rerun()
            # ===== EXCEÇÕES DE HORÁRIO =====
            excs = db().query(ExcecaoHorario).filter(
                ExcecaoHorario.id_paciente == p.id_paciente).all()
            with st.expander(f"📅 Exceções de horário ({len(excs)})"):
                for ex in excs:
                    cx1, cx2 = st.columns([5, 1])
                    if ex.tipo == "recorrente":
                        rot_sem = {1:"1ª",2:"2ª",3:"3ª",4:"4ª",5:"Última"}.get(
                            ex.semana_do_mes, "?")
                        cx1.write(f"🔁 **Recorrente:** na {rot_sem} semana → "
                                  f"{ex.dia_alvo} {ex.horario_alvo}")
                    else:
                        cx1.write(f"📌 **Pontual:** "
                                  f"{ex.data_especifica.strftime('%d/%m/%Y')} → "
                                  f"{ex.dia_alvo} {ex.horario_alvo}")
                    if cx2.button("Remover", key=f"rmex_{ex.id_excecao}"):
                        db().delete(ex); db().commit(); st.rerun()
                # Form para nova exceção
                tipo_e = st.radio("Tipo", ["Recorrente (toda Nª semana)",
                    "Pontual (data específica)"],
                    key=f"tex_{p.id_paciente}", horizontal=True)
                with st.form(f"fex_{p.id_paciente}"):
                    if tipo_e.startswith("Recorrente"):
                        sm = st.selectbox("Em qual semana do mês?",
                            [1,2,3,4,5],
                            format_func=lambda n: {1:"1ª",2:"2ª",3:"3ª",
                                4:"4ª",5:"Última"}[n],
                            key=f"sm_{p.id_paciente}")
                        de = None
                    else:
                        de = st.date_input("Data específica",
                            format="DD/MM/YYYY", key=f"de_{p.id_paciente}")
                        sm = None
                    dia_a = st.selectbox("Atender em qual dia?",
                        [e.value for e in DiaSemana],
                        key=f"da_{p.id_paciente}")
                    hr_a = st.selectbox("Horário", FAIXAS_HORARIO,
                        key=f"ha_{p.id_paciente}")
                    if st.form_submit_button("Adicionar exceção"):
                        db().add(ExcecaoHorario(
                            id_paciente=p.id_paciente,
                            tipo="recorrente" if tipo_e.startswith("Recorrente") else "pontual",
                            semana_do_mes=sm, data_especifica=de,
                            dia_alvo=dia_a, horario_alvo=hr_a))
                        db().commit()
                        flash("Exceção adicionada.", "success")
                        st.rerun()
        dados_pac = [{"Nome": p.nome, "Tel": p.telefone,
            "Email": p.email or "", "Nasc": p.data_nascimento.strftime("%d/%m/%Y") if p.data_nascimento else "",
            "Freq": p.frequencia.value, "Dias": p.dias_semana or "",
            "Horario": p.horario_atendimento,
            "Valor": float(p.valor_sessao),
            "Ativo desde": p.ativo_desde.strftime("%d/%m/%Y") if p.ativo_desde else ""}
            for p in ativos]
        if ativos:
            st.download_button("Baixar PDF",
                gerar_pdf("Pacientes Ativos", dados_pac),
                file_name="pacientes_ativos.pdf", mime="application/pdf")
