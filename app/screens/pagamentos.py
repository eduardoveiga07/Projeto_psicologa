import streamlit as st
from datetime import datetime, date, time
import pandas as pd
from app.screens.shared import (
    db, mostrar_flash, flash, registrar, Paciente, AgendaSessao, StatusPaciente,
    StatusPresenca, StatusPagamento, FAIXAS_HORARIO, ui_header, ui_kpi_card
)
from app.services.pdf_export import gerar_pdf
from app.services.financeiro import fmt_br


def tela_pagamentos():
    mostrar_flash()
    ui_header("Controle de Pagamentos", icon="💸")

    # Pre-fetch all patients to avoid N+1 queries
    pacientes = db().query(Paciente).all()
    pacientes_dict = {p.id_paciente: p for p in pacientes}

    # KPIs superiores com visual premium
    pend_kpis = db().query(AgendaSessao).filter(
        AgendaSessao.status_pagamento.in_([
            StatusPagamento.PENDENTE, StatusPagamento.ATRASADO]),
        AgendaSessao.status_presenca != StatusPresenca.CANCELADA).all()
        
    total_valor_pendente = 0.0
    for s in pend_kpis:
        p = pacientes_dict.get(s.id_paciente)
        if p:
            total_valor_pendente += float(p.valor_sessao)
            
    col1, col2 = st.columns(2)
    with col1:
        ui_kpi_card("Sessões em Aberto", f"{len(pend_kpis)} sessões", delta="Aguardando recebimento", delta_color="normal")
    with col2:
        ui_kpi_card("Total Pendente", fmt_br(total_valor_pendente), delta="Acumulado pendente", delta_color="inverse")
        
    st.markdown("<br>", unsafe_allow_html=True)

    # Lancar sessao retroativa (historico antes do sistema existir)
    with st.expander("➕ Lançar sessão antiga (histórico anterior ao sistema)"):
        with st.form("retro_sess"):
            pacs = db().query(Paciente).filter(
                Paciente.status == StatusPaciente.ATIVO).all()
            mapa = {p.nome: p for p in pacs}
            cc1, cc2, cc3 = st.columns(3)
            nm_r = cc1.selectbox("Paciente", list(mapa.keys()) or ["—"])
            dt_r = cc2.date_input("Data", value=datetime.now().date(),
                min_value=date(2020, 1, 1), format="DD/MM/YYYY")
            hr_r = cc3.selectbox("Horário", FAIXAS_HORARIO)
            cc4, cc5 = st.columns(2)
            pres_r = cc4.selectbox("Situação",
                [e.value for e in StatusPresenca],
                index=[e.value for e in StatusPresenca].index("Realizada"))
            pag_r = cc5.selectbox("Pagamento",
                [e.value for e in StatusPagamento])
            if st.form_submit_button("Lançar"):
                if nm_r in mapa:
                    hi, _ = hr_r.split(" - ")
                    h, m = map(int, hi.split(":"))
                    ini = datetime.combine(dt_r, time(h, m))
                    try:
                        db().add(AgendaSessao(
                            id_paciente=mapa[nm_r].id_paciente,
                            data_hora_inicio=ini,
                            data_hora_fim=ini.replace(hour=h + 1),
                            status_presenca=StatusPresenca(pres_r),
                            status_pagamento=StatusPagamento(pag_r)))
                        db().commit()
                        st.success(f"Sessão de {dt_r.strftime('%d/%m/%Y')} lançado.")
                    except Exception:
                        db().rollback()
                        st.error("Horário já ocupado nesta data.")

    sessoes = db().query(AgendaSessao).filter(
        AgendaSessao.status_presenca != StatusPresenca.CANCELADA).order_by(
        AgendaSessao.data_hora_inicio.desc()).limit(100).all()

    if not sessoes:
        st.info("Nenhuma sessão registrada ainda.")

    # PDF com TODAS as sessões e seus pagamentos (sempre disponível).
    todas = []
    for s in sessoes:
        p = pacientes_dict.get(s.id_paciente)
        todas.append({
            "Paciente": p.nome if p else "?",
            "Data": s.data_hora_inicio.strftime("%d/%m/%Y %H:%M"),
            "Situação": s.status_presenca.value,
            "Pagamento": s.status_pagamento.value,
            "Valor": float(p.valor_sessao) if p else 0})
    totais_todos = {
        "Valor": fmt_br(sum(l["Valor"] for l in todas))
    }
    st.download_button("Baixar PDF (todos os pagamentos)",
        gerar_pdf("Controle de Pagamentos", todas, totais=totais_todos),
        file_name="pagamentos_todos.pdf", mime="application/pdf")

    # Lista individual para edições rápidas
    st.write("---")
    st.subheader("Últimas 100 sessões registradas")
    for s in sessoes:
        p = pacientes_dict.get(s.id_paciente)
        nome = p.nome if p else "?"
        quando = s.data_hora_inicio.strftime("%d/%m/%Y %H:%M")
        with st.expander(f"{nome} — {quando} — {s.status_presenca.value} / {s.status_pagamento.value}"):
            c1, c2 = st.columns(2)
            pres = c1.selectbox("Situação", [e.value for e in StatusPresenca],
                index=[e.value for e in StatusPresenca].index(
                    s.status_presenca.value),
                key=f"pres_{s.id_sessao}")
            pag = c2.selectbox("Pagamento",
                [e.value for e in StatusPagamento],
                index=[e.value for e in StatusPagamento].index(
                    s.status_pagamento.value),
                key=f"pag_{s.id_sessao}")
            if st.button("Salvar", key=f"save_{s.id_sessao}"):
                novo_pres = StatusPresenca(pres)
                s.status_presenca = novo_pres
                # Regra automatica de cobranca:
                if novo_pres in (StatusPresenca.CANCELOU_COM_ANTECEDENCIA,
                                 StatusPresenca.IMPREVISTO):
                    s.status_pagamento = StatusPagamento.ISENTO
                elif novo_pres == StatusPresenca.CANCELOU_EM_CIMA:
                    if StatusPagamento(pag) != StatusPagamento.PAGO:
                        s.status_pagamento = StatusPagamento.PENDENTE
                    else:
                        s.status_pagamento = StatusPagamento.PAGO
                else:
                    s.status_pagamento = StatusPagamento(pag)
                db().commit()
                flash("Atualizado.", "success")
                st.rerun()

    # Resumo de inadimplência com Ações em Lote (st.data_editor)
    st.write("---")
    st.subheader(f"Pagamentos em aberto ({len(pend_kpis)})")
    
    linhas_aberto = []
    for s in pend_kpis:
        p = pacientes_dict.get(s.id_paciente)
        linhas_aberto.append({
            "Pagar em Lote": False,
            "Paciente": p.nome if p else "?",
            "Data": s.data_hora_inicio.strftime("%d/%m/%Y %H:%M"),
            "Situação": s.status_presenca.value,
            "Pagamento": s.status_pagamento.value,
            "Valor": float(p.valor_sessao) if p else 0.0,
            "id_sessao": s.id_sessao
        })
        
    if linhas_aberto:
        df_aberto = pd.DataFrame(linhas_aberto)
        df_editado = st.data_editor(
            df_aberto,
            column_config={
                "id_sessao": None,  # Oculta
                "Pagar em Lote": st.column_config.CheckboxColumn("Pagar em Lote", default=False)
            },
            disabled=["Paciente", "Data", "Situação", "Pagamento", "Valor"],
            use_container_width=True,
            key="pagamento_lote_editor"
        )
        
        c1, c2 = st.columns([2, 1])
        if c1.button("Confirmar Pagamento das Selecionadas", type="primary"):
            selecionadas = df_editado[df_editado["Pagar em Lote"] == True]
            if not selecionadas.empty:
                count_pagos = 0
                for idx, row in selecionadas.iterrows():
                    sessao_id = int(row["id_sessao"])
                    sessao = db().query(AgendaSessao).get(sessao_id)
                    if sessao:
                        sessao.status_pagamento = StatusPagamento.PAGO
                        count_pagos += 1
                db().commit()
                registrar(db(), st.session_state.username, "PAGAMENTO_LOTE", f"quantidade={count_pagos}")
                flash(f"Sucesso: {count_pagos} pagamentos registrados em lote!", "success")
                st.rerun()
            else:
                st.warning("Selecione pelo menos uma sessão marcando o checkbox 'Pagar em Lote'.")
                
        totais_aberto = {
            "Valor": fmt_br(sum(l["Valor"] for l in linhas_aberto))
        }
        
        # Remove colunas auxiliares do PDF para manter compatibilidade
        pdf_linhas = [{k: v for k, v in l.items() if k not in ("Pagar em Lote", "id_sessao")} for l in linhas_aberto]
        c2.download_button("Baixar PDF (em aberto)",
            gerar_pdf("Pagamentos em Aberto", pdf_linhas, totais=totais_aberto),
            file_name="pagamentos_aberto.pdf", mime="application/pdf", use_container_width=True)
