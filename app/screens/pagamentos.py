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
                from app.services.financeiro import is_mes_fechado
                if nm_r in mapa:
                    if is_mes_fechado(db(), dt_r):
                        st.error(f"Erro: O período {dt_r.strftime('%m/%Y')} está fechado para novos lançamentos.")
                    else:
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
                            st.success(f"Sessão de {dt_r.strftime('%d/%m/%Y')} lançada.")
                        except Exception:
                            db().rollback()
                            st.error("Horário já ocupado nesta data.")

    # ===== FILTROS RÁPIDOS =====
    st.write("---")
    filtro_r = st.selectbox(
        "⚡ Filtros Rápidos",
        ["Todos", "Mês Atual", "Pagamentos Pendentes", "Sessões Realizadas"],
        key="filtro_rapido_sessao"
    )

    query = db().query(AgendaSessao).filter(
        AgendaSessao.status_presenca != StatusPresenca.CANCELADA
    )

    hoje_dt = datetime.now()
    if filtro_r == "Mês Atual":
        from sqlalchemy import extract
        query = query.filter(
            extract("year", AgendaSessao.data_hora_inicio) == hoje_dt.year,
            extract("month", AgendaSessao.data_hora_inicio) == hoje_dt.month
        )
    elif filtro_r == "Pagamentos Pendentes":
        query = query.filter(
            AgendaSessao.status_pagamento.in_([
                StatusPagamento.PENDENTE, StatusPagamento.ATRASADO
            ])
        )
    elif filtro_r == "Sessões Realizadas":
        query = query.filter(
            AgendaSessao.status_presenca == StatusPresenca.REALIZADA
        )

    sessoes = query.order_by(AgendaSessao.data_hora_inicio.desc()).limit(100).all()

    if not sessoes:
        st.info("Nenhuma sessão encontrada para o filtro selecionado.")

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
        pago_str = f" | 📅 Pago em {s.data_pagamento.strftime('%d/%m/%Y')}" if s.status_pagamento == StatusPagamento.PAGO and s.data_pagamento else ""
        with st.expander(f"{nome} — {quando} — {s.status_presenca.value} / {s.status_pagamento.value}{pago_str}"):
            from app.services.financeiro import is_mes_fechado
            fechado = is_mes_fechado(db(), s.data_hora_inicio.date())
            if fechado:
                st.warning("🔒 Este período está fechado. Reabra o mês no financeiro para fazer edições.")
            c1, c2 = st.columns(2)
            pres = c1.selectbox("Situação", [e.value for e in StatusPresenca],
                index=[e.value for e in StatusPresenca].index(
                    s.status_presenca.value),
                key=f"pres_{s.id_sessao}",
                disabled=fechado)
            pag = c2.selectbox("Pagamento",
                [e.value for e in StatusPagamento],
                index=[e.value for e in StatusPagamento].index(
                    s.status_pagamento.value),
                key=f"pag_{s.id_sessao}",
                disabled=fechado)
            
            if s.data_pagamento:
                st.info(f"📅 **Pagamento registrado em:** {s.data_pagamento.strftime('%d/%m/%Y')}")
                
            comp_file = None
            del_comp = False
            if pag == StatusPagamento.PAGO.value:
                if s.comprovante_nome:
                    import os
                    from app.services.comprovantes import obter_comprovante_caminho
                    caminho = obter_comprovante_caminho(s.comprovante_nome)
                    if caminho and os.path.exists(caminho):
                        with open(caminho, "rb") as f:
                            btn_data = f.read()
                        nome_dl = s.comprovante_nome_original or s.comprovante_nome
                        mime_dl = s.comprovante_mime or "application/octet-stream"
                        tamanho_kb = f" ({s.comprovante_tamanho // 1024} KB)" if s.comprovante_tamanho else ""
                        enviado_em = f" — {s.comprovante_enviado_em.strftime('%d/%m/%Y %H:%M')}" if s.comprovante_enviado_em else ""
                        st.download_button(
                            label=f"📎 Baixar: {nome_dl}{tamanho_kb}{enviado_em}",
                            data=btn_data,
                            file_name=nome_dl,
                            mime=mime_dl,
                            key=f"dl_comp_{s.id_sessao}"
                        )
                    else:
                        st.caption("⚠️ Arquivo físico do comprovante ausente")
                    del_comp = st.checkbox("Excluir comprovante?", key=f"del_comp_{s.id_sessao}", disabled=fechado)
                
                comp_file = st.file_uploader("Enviar comprovante (PDF, Imagem)", type=["pdf", "png", "jpg", "jpeg"], key=f"comp_u_{s.id_sessao}", disabled=fechado)
                
            if not fechado and st.button("Salvar", key=f"save_{s.id_sessao}"):
                novo_pres = StatusPresenca(pres)
                s.status_presenca = novo_pres
                novo_pag = StatusPagamento(pag)
                
                # Regra automatica de cobranca:
                if novo_pres in (StatusPresenca.CANCELOU_COM_ANTECEDENCIA,
                                 StatusPresenca.IMPREVISTO):
                    s.status_pagamento = StatusPagamento.ISENTO
                    s.data_pagamento = None
                elif novo_pres == StatusPresenca.CANCELOU_EM_CIMA:
                    if novo_pag != StatusPagamento.PAGO:
                        s.status_pagamento = StatusPagamento.PENDENTE
                        s.data_pagamento = None
                    else:
                        s.status_pagamento = StatusPagamento.PAGO
                        if not s.data_pagamento:
                            s.data_pagamento = datetime.now().date()
                else:
                    s.status_pagamento = novo_pag
                    if novo_pag == StatusPagamento.PAGO:
                        if not s.data_pagamento:
                            s.data_pagamento = datetime.now().date()
                    else:
                        s.data_pagamento = None
                
                # Processar comprovante com validação e auditoria
                from app.services.comprovantes import (
                    salvar_comprovante, deletar_comprovante,
                    aplicar_metadados_comprovante, limpar_metadados_comprovante,
                    ComprovantesError
                )
                erro_comp = None
                if s.status_pagamento != StatusPagamento.PAGO:
                    if s.comprovante_nome:
                        deletar_comprovante(s.comprovante_nome)
                        registrar(db(), st.session_state.username, "COMPROVANTE_REMOVIDO",
                                  f"sessao_id={s.id_sessao} arquivo={s.comprovante_nome} motivo=status_nao_pago")
                        limpar_metadados_comprovante(s)
                else:
                    try:
                        if del_comp:
                            arq_anterior = s.comprovante_nome
                            deletar_comprovante(arq_anterior)
                            limpar_metadados_comprovante(s)
                            registrar(db(), st.session_state.username, "COMPROVANTE_REMOVIDO",
                                      f"sessao_id={s.id_sessao} arquivo={arq_anterior}")
                        if comp_file:
                            if s.comprovante_nome:
                                deletar_comprovante(s.comprovante_nome)
                            meta = salvar_comprovante(comp_file, "sessao", s.id_sessao)
                            aplicar_metadados_comprovante(s, meta)
                            registrar(db(), st.session_state.username, "COMPROVANTE_ANEXADO",
                                      f"sessao_id={s.id_sessao} arquivo={meta['nome']} mime={meta['mime']} bytes={meta['tamanho']}")
                    except ComprovantesError as ce:
                        erro_comp = str(ce)
                        
                if erro_comp:
                    st.error(erro_comp)
                else:
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
        confirmado = c1.checkbox("Confirmo que os valores de todas as sessões selecionadas foram recebidos.", key="conf_lote_checkbox")
        
        if c1.button("Confirmar Pagamento das Selecionadas", type="primary", disabled=not confirmado):
            selecionadas = df_editado[df_editado["Pagar em Lote"] == True]
            if not selecionadas.empty:
                from app.services.financeiro import is_mes_fechado
                has_closed = False
                for idx, row in selecionadas.iterrows():
                    sessao_id = int(row["id_sessao"])
                    sessao = db().query(AgendaSessao).get(sessao_id)
                    if sessao and is_mes_fechado(db(), sessao.data_hora_inicio.date()):
                        st.error(f"Erro: A sessão de {row['Paciente']} em {row['Data']} pertence a um período fechado.")
                        has_closed = True
                        break
                
                if not has_closed:
                    count_pagos = 0
                    hoje = datetime.now().date()
                    for idx, row in selecionadas.iterrows():
                        sessao_id = int(row["id_sessao"])
                        sessao = db().query(AgendaSessao).get(sessao_id)
                        if sessao:
                            sessao.status_pagamento = StatusPagamento.PAGO
                            sessao.data_pagamento = hoje
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
