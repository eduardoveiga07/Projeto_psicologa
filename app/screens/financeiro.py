import streamlit as st
from datetime import datetime, date
from decimal import Decimal
from app.screens.shared import db, mostrar_flash, flash, Despesa, Perfil, ui_header, ui_kpi_card
from app.services.financeiro import fmt_br, expandir_recorrentes, consolidado_periodo, historico_ultimos_meses
from app.services.pdf_export import gerar_pdf

# Importa o validador de despesas
from app.services.validacao_negocio import validar_valor_despesa


def tela_financeiro():
    if st.session_state.get("perfil") not in ["Dona", "Financeiro", "Programador"]:
        st.error("Acesso negado. Você não tem permissão para visualizar o painel financeiro.")
        st.stop()
    mostrar_flash()
    ui_header("Financeiro — Previsto vs Realizado", "Acompanhe o faturamento previsto, realizado, inadimplência e o controle de despesas do consultório.", icon="📊")
    # Filtro Rápido
    st.selectbox("⚡ Filtro Rápido", ["— Nenhum —", "Mês Atual"], key="fin_filtro_rapido")
    if st.session_state.get("fin_filtro_rapido") == "Mês Atual":
        st.session_state.fin_ano = datetime.now().year
        st.session_state.fin_periodo = "Mensal"
        st.session_state.fin_mes = datetime.now().month

    c1, c2, c3 = st.columns(3)
    ano = c1.number_input("Ano", 2024, 2040, datetime.now().year, key="fin_ano")
    periodo = c2.selectbox("Período",
        ["Mensal", "Trimestral", "Semestral", "Anual"], key="fin_periodo")

    if periodo == "Mensal":
        m = c3.number_input("Mês", 1, 12, datetime.now().month, key="fin_mes")
        meses = [int(m)]
        rotulo = f"{int(m):02d}/{int(ano)}"
    elif periodo == "Trimestral":
        t = c3.selectbox("Trimestre", [1, 2, 3, 4])
        meses = list(range((t - 1) * 3 + 1, (t - 1) * 3 + 4))
        rotulo = f"{t}º Trim/{int(ano)}"
    elif periodo == "Semestral":
        sm = c3.selectbox("Semestre", [1, 2])
        meses = list(range(1, 7)) if sm == 1 else list(range(7, 13))
        rotulo = f"{sm}º Sem/{int(ano)}"
    else:
        meses = list(range(1, 13))
        rotulo = f"Ano {int(ano)}"

    # Expande despesas recorrentes para cada mes do periodo
    for mm in meses:
        expandir_recorrentes(db(), int(ano), mm)

    r = consolidado_periodo(db(), int(ano), meses)
    st.subheader(f"Resultado: {rotulo}")
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        ui_kpi_card("Faturamento Previsto", fmt_br(r["faturamento_previsto"]), "Total esperado com base em todas as consultas cadastradas.")
    with k2:
        ui_kpi_card("Faturamento Realizado", fmt_br(r["faturamento_realizado"]), "Total efetivamente faturado por consultas realizadas ou cobradas.")
    with k3:
        ui_kpi_card("Inadimplência / Pendente", fmt_br(r.get("inadimplencia", Decimal(0))), "Total de faturamento realizado que ainda não foi pago (Pendente/Atrasado).")
    with k4:
        ui_kpi_card("Lucro Líquido", fmt_br(r["lucro_liquido"]), "Faturamento Realizado menos as Despesas do período.")
    st.caption(f"💰 Total de despesas: {fmt_br(r['total_despesas'])} — detalhe na seção '💸 Despesas do período' mais abaixo")

    import pandas as pd
    import plotly.graph_objects as go

    def categorizar_despesa(descricao: str) -> str:
        infra = ["aluguel", "condomínio", "iptu", "seguro incêndio", "seguro fiança", "energia", "água", "internet", "telefone"]
        pessoal = ["secretária", "salário", "vale-transporte", "fgts", "inss", "13º", "férias", "alimentação", "refeição", "seguro de vida", "pj"]
        desc_lower = (descricao or "").lower()
        if any(item in desc_lower for item in infra):
            return "Infraestrutura"
        elif any(item in desc_lower for item in pessoal):
            return "Pessoal (RH)"
        else:
            return "Operacional / Outros"

    tab_evolucao, tab_pacientes, tab_despesas, tab_contas_receber, tab_paciente_hist, tab_fechamento = st.tabs([
        "📈 Evolução Temporal",
        "👥 Faturamento por Paciente",
        "💸 Distribuição de Despesas",
        "📥 Contas a Receber",
        "👤 Histórico por Paciente",
        "🔒 Fechamento Mensal"
    ])

    with tab_evolucao:
        if r["linhas"]:
            # Obter histórico de meses conforme o período selecionado
            if periodo == "Mensal":
                historico = historico_ultimos_meses(db(), int(ano), int(m), qtd=6)
            else:
                historico = historico_ultimos_meses(db(), int(ano), meses[-1], qtd=len(meses))
                
            eixo_x = [h["mes_rotulo"] for h in historico]
            y_realizado = [h["faturamento_realizado"] for h in historico]
            y_despesas = [h["total_despesas"] for h in historico]
            y_lucro = [h["lucro_liquido"] for h in historico]
            
            fig_ev = go.Figure()
            fig_ev.add_trace(go.Scatter(
                x=eixo_x, y=y_realizado, name="Faturamento Realizado",
                line=dict(color="#27ae60", width=3), mode="lines+markers+text",
                text=[fmt_br(v) for v in y_realizado], textposition="top center"
            ))
            fig_ev.add_trace(go.Scatter(
                x=eixo_x, y=y_despesas, name="Total de Despesas",
                line=dict(color="#e74c3c", width=2, dash="dash"), mode="lines+markers"
            ))
            fig_ev.add_trace(go.Scatter(
                x=eixo_x, y=y_lucro, name="Lucro Líquido",
                line=dict(color="#4a90e2", width=3), mode="lines+markers+text",
                text=[fmt_br(v) for v in y_lucro], textposition="bottom center"
            ))
            
            fig_ev.update_layout(
                title="Evolução Temporal no Período (R$)",
                xaxis_title="Período",
                yaxis_title="R$",
                template="plotly_dark",
                margin=dict(t=40, b=40, l=10, r=10),
                height=400
            )
            st.plotly_chart(fig_ev, use_container_width=True)
        else:
            st.info("Sem dados de sessões no período selecionado.")

    with tab_pacientes:
        if r["linhas"]:
            ordenado = sorted(r["linhas"],
                key=lambda l: float(l["faturamento_previsto"]), reverse=True)
            top = ordenado[:10]
            outros = ordenado[10:]
            nomes = [l["paciente"] for l in top]
            prev = [float(l["faturamento_previsto"]) for l in top]
            real = [float(l["faturamento_realizado"]) for l in top]
            if outros:
                nomes.append(f"Outros ({len(outros)})")
                prev.append(sum(float(l["faturamento_previsto"]) for l in outros))
                real.append(sum(float(l["faturamento_realizado"]) for l in outros))
            fig = go.Figure(data=[
                go.Bar(name="Previsto", y=nomes, x=prev, orientation="h",
                       marker_color="#4a90e2",
                       text=[fmt_br(v) for v in prev], textposition="auto"),
                go.Bar(name="Realizado", y=nomes, x=real, orientation="h",
                       marker_color="#27ae60",
                       text=[fmt_br(v) for v in real], textposition="auto"),
            ])
            fig.update_layout(barmode="group", height=max(350, 40 * len(nomes)),
                xaxis_title="R$", template="plotly_dark",
                margin=dict(t=20, b=40, l=10, r=10),
                yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("#### Detalhamento por Paciente")
            fin_rows = [{
                "Paciente": l["paciente"],
                "Sessões Previstas": l["sessoes_previstas"],
                "Faturamento Previsto": fmt_br(l["faturamento_previsto"]),
                "Sessões Realizadas": l["sessoes_realizadas"],
                "Faturamento Realizado": fmt_br(l["faturamento_realizado"]),
                "Inadimplência / Pendente": fmt_br(l.get("inadimplencia", Decimal(0)))
            } for l in r["linhas"]]
            
            st.dataframe(fin_rows, use_container_width=True)
            
            # Construir os filtros e totais para a exportação de PDF
            filtros_pdf = {"Ano": str(ano), "Período": periodo}
            if periodo == "Mensal":
                filtros_pdf["Mês"] = f"{int(m):02d}"
            elif periodo == "Trimestral":
                filtros_pdf["Trimestre"] = f"{t}º Trimestre"
            elif periodo == "Semestral":
                filtros_pdf["Semestre"] = f"{sm}º Semestre"
                
            totais_pdf = {
                "Sessões Previstas": str(sum(l["sessoes_previstas"] for l in r["linhas"])),
                "Faturamento Previsto": fmt_br(r["faturamento_previsto"]),
                "Sessões Realizadas": str(sum(l["sessoes_realizadas"] for l in r["linhas"])),
                "Faturamento Realizado": fmt_br(r["faturamento_realizado"]),
                "Inadimplência / Pendente": fmt_br(r.get("inadimplencia", Decimal(0)))
            }
            
            st.download_button("Baixar PDF (Faturamento)",
                gerar_pdf(f"Financeiro — {rotulo}", fin_rows, filtros=filtros_pdf, totais=totais_pdf),
                file_name=f"financeiro_{rotulo.replace('/', '_')}.pdf", mime="application/pdf", key="pdf_fat_cons")
        else:
            st.info("Sem faturamento no período selecionado.")

    with tab_despesas:
        # Buscar despesas do período agrupadas por categoria estrutural
        refs_periodo = [f"{int(ano):04d}-{mm:02d}" for mm in meses]
        despesas_db = db().query(Despesa).filter(
            Despesa.mes_referencia.in_(refs_periodo)).all()
            
        contagem_desp = {}
        for d in despesas_db:
            cat_nome = categorizar_despesa(d.descricao)
            contagem_desp[cat_nome] = contagem_desp.get(cat_nome, Decimal(0)) + d.valor
            
        if contagem_desp:
            labels = list(contagem_desp.keys())
            valores_desp = [float(v) for v in contagem_desp.values()]
            
            fig_desp = go.Figure(data=[go.Pie(
                labels=labels,
                values=valores_desp,
                hole=0.4,
                hoverinfo="label+percent+value",
                textinfo="percent+label"
            )])
            
            fig_desp.update_layout(
                title="Divisão de Despesas por Categoria Estrutural",
                template="plotly_dark",
                margin=dict(t=40, b=20, l=10, r=10),
                height=350
            )
            st.plotly_chart(fig_desp, use_container_width=True)
        else:
            st.info("Sem despesas lançadas no período para exibir o gráfico.")

    with tab_contas_receber:
        st.subheader("📥 Contas a Receber (Inadimplência)")
        st.caption("Consolidado de todas as sessões agendadas/realizadas que ainda não foram pagas.")
        
        from app.db.models import Paciente, AgendaSessao, StatusPresenca, StatusPagamento
        sessoes_pendentes = db().query(AgendaSessao).filter(
            AgendaSessao.status_pagamento.in_([StatusPagamento.PENDENTE, StatusPagamento.ATRASADO]),
            AgendaSessao.status_presenca != StatusPresenca.CANCELADA
        ).order_by(AgendaSessao.data_hora_inicio.asc()).all()
        
        pacs_all = db().query(Paciente).all()
        pacs_dict = {p.id_paciente: p for p in pacs_all}
        
        inad_map = {}
        for s in sessoes_pendentes:
            p = pacs_dict.get(s.id_paciente)
            if not p:
                continue
            val = s.valor_sessao if s.valor_sessao is not None else p.valor_sessao
            dt = s.data_hora_inicio.date()
            if p.id_paciente not in inad_map:
                inad_map[p.id_paciente] = {
                    "Paciente": p.nome,
                    "Telefone": p.telefone or "-",
                    "E-mail": p.email or "-",
                    "Sessões Pendentes": 0,
                    "Mais Antiga": dt,
                    "Dias em Atraso": (datetime.now().date() - dt).days,
                    "Valor Pendente (R$)": Decimal("0.0"),
                    "raw_valor": Decimal("0.0")
                }
            inad_map[p.id_paciente]["Sessões Pendentes"] += 1
            inad_map[p.id_paciente]["raw_valor"] += val
            if dt < inad_map[p.id_paciente]["Mais Antiga"]:
                inad_map[p.id_paciente]["Mais Antiga"] = dt
                inad_map[p.id_paciente]["Dias em Atraso"] = (datetime.now().date() - dt).days
        
        inad_lista = sorted(inad_map.values(), key=lambda x: x["Dias em Atraso"], reverse=True)
        for item in inad_lista:
            item["Valor Pendente"] = fmt_br(item["raw_valor"])
            item["Mais Antiga"] = item["Mais Antiga"].strftime("%d/%m/%Y")
        
        if not inad_lista:
            st.success("🎉 Nenhuma inadimplência pendente no momento!")
        else:
            total_inad_geral = sum(item["raw_valor"] for item in inad_lista)
            ck1, ck2 = st.columns(2)
            with ck1:
                ui_kpi_card("Total em Atraso Geral", fmt_br(total_inad_geral), "Total acumulado de todas as sessões pendentes e atrasadas.")
            with ck2:
                ui_kpi_card("Pacientes Inadimplentes", f"{len(inad_lista)} paciente(s)", "Total de pacientes com pendências financeiras.")
            
            df_inad = pd.DataFrame([{k: v for k, v in item.items() if k not in ("raw_valor", "Valor Pendente (R$)")} for item in inad_lista])
            st.dataframe(df_inad, use_container_width=True)
            
            # PDF Download for Contas a Receber
            pdf_inad_rows = []
            for item in inad_lista:
                pdf_inad_rows.append({
                    "Paciente": item["Paciente"],
                    "Telefone": item["Telefone"],
                    "Sessões Pendentes": str(item["Sessões Pendentes"]),
                    "Mais Antiga": item["Mais Antiga"],
                    "Dias em Atraso": str(item["Dias em Atraso"]),
                    "Valor": item["Valor Pendente"]
                })
            pdf_inad_totais = {"Valor": fmt_br(total_inad_geral)}
            st.download_button("Baixar PDF (Contas a Receber)",
                gerar_pdf("Contas a Receber — Inadimplência", pdf_inad_rows, totais=pdf_inad_totais),
                file_name="contas_a_receber.pdf", mime="application/pdf", key="pdf_contas_receber")

    with tab_paciente_hist:
        st.subheader("👤 Histórico Financeiro do Paciente")
        st.caption("Acompanhe o faturamento consolidado e o detalhamento de todas as sessões de um paciente específico.")
        
        pacs_hist = db().query(Paciente).order_by(Paciente.nome).all()
        if not pacs_hist:
            st.info("Nenhum paciente cadastrado.")
        else:
            p_nomes = {p.nome: p for p in pacs_hist}
            p_selecionado_nome = st.selectbox("Selecione o Paciente", list(p_nomes.keys()), key="hist_pac_sel")
            p_obj = p_nomes[p_selecionado_nome]
            
            # Buscar sessões do paciente
            sessoes_pac = db().query(AgendaSessao).filter(
                AgendaSessao.id_paciente == p_obj.id_paciente,
                AgendaSessao.status_presenca != StatusPresenca.CANCELADA
            ).order_by(AgendaSessao.data_hora_inicio.desc()).all()
            
            total_faturado_pac = Decimal("0.0")
            total_pago_pac = Decimal("0.0")
            total_pendente_pac = Decimal("0.0")
            total_isento_pac = Decimal("0.0")
            
            linhas_hist = []
            for s in sessoes_pac:
                val = s.valor_sessao if s.valor_sessao is not None else p_obj.valor_sessao
                
                # Faturamento realizado: REALIZADA ou CANCELOU_EM_CIMA
                realizado = s.status_presenca in (StatusPresenca.REALIZADA, StatusPresenca.CANCELOU_EM_CIMA)
                if realizado:
                    total_faturado_pac += val
                    if s.status_pagamento == StatusPagamento.PAGO:
                        total_pago_pac += val
                    elif s.status_pagamento in (StatusPagamento.PENDENTE, StatusPagamento.ATRASADO):
                        total_pendente_pac += val
                
                if s.status_pagamento == StatusPagamento.ISENTO:
                    total_isento_pac += val
                    
                linhas_hist.append({
                    "Data/Hora": s.data_hora_inicio.strftime("%d/%m/%Y %H:%M"),
                    "Situação": s.status_presenca.value,
                    "Pagamento": s.status_pagamento.value,
                    "Valor (R$)": fmt_br(val),
                    "Data Pagamento": s.data_pagamento.strftime("%d/%m/%Y") if s.data_pagamento else "-",
                    "raw_val": val
                })
            
            # KPIs
            kh1, kh2, kh3, kh4 = st.columns(4)
            with kh1:
                ui_kpi_card("Total Faturado", fmt_br(total_faturado_pac), "Faturamento realizado do paciente.")
            with kh2:
                ui_kpi_card("Total Recebido", fmt_br(total_pago_pac), "Total efetivamente pago.")
            with kh3:
                ui_kpi_card("Total Pendente", fmt_br(total_pendente_pac), "Total aguardando pagamento.")
            with kh4:
                ui_kpi_card("Total Isento", fmt_br(total_isento_pac), "Sessões isentas de pagamento.")
            
            if not linhas_hist:
                st.info("Nenhuma sessão registrada para este paciente.")
            else:
                df_hist = pd.DataFrame([{k: v for k, v in l.items() if k != "raw_val"} for l in linhas_hist])
                st.dataframe(df_hist, use_container_width=True)
                
                # PDF Download
                pdf_hist_rows = [{
                    "Data/Hora": l["Data/Hora"],
                    "Situação": l["Situação"],
                    "Pagamento": l["Pagamento"],
                    "Valor": l["Valor (R$)"],
                    "Data Pagamento": l["Data Pagamento"]
                } for l in linhas_hist]
                
                filtros_hist = {
                    "Paciente": p_obj.nome,
                    "Telefone": p_obj.telefone or "-",
                    "E-mail": p_obj.email or "-"
                }
                totais_hist = {
                    "Faturado": fmt_br(total_faturado_pac),
                    "Recebido": fmt_br(total_pago_pac),
                    "Pendente": fmt_br(total_pendente_pac)
                }
                st.download_button(f"Baixar PDF de {p_obj.nome}",
                    gerar_pdf(f"Histórico Financeiro — {p_obj.nome}", pdf_hist_rows, filtros=filtros_hist, totais=totais_hist),
                    file_name=f"financeiro_{p_obj.nome.replace(' ', '_').lower()}.pdf", mime="application/pdf", key="pdf_pac_hist")

    with tab_fechamento:
        st.subheader("🔒 Fechamento e Bloqueio de Períodos")
        st.caption("O fechamento de um mês bloqueia qualquer alteração operacional (sessões, pagamentos ou despesas) naquele período. Correções retroativas exigem a reabertura do mês com justificativa obrigatória.")
        
        # --- FORMULÁRIO DE FECHAMENTO ---
        st.markdown("### 📌 Fechar Novo Mês")
        col_f1, col_f2 = st.columns(2)
        ano_fec = col_f1.number_input("Ano para Fechamento", 2024, 2040, datetime.now().year, key="fec_ano")
        mes_fec = col_f2.number_input("Mês para Fechamento", 1, 12, datetime.now().month, key="fec_mes")
        
        ref_fec = f"{ano_fec:04d}-{mes_fec:02d}"
        
        from app.db.models import FechamentoMensal
        from app.services.financeiro import consolidado_mes
        
        existente = db().query(FechamentoMensal).filter(FechamentoMensal.mes_referencia == ref_fec).first()
        
        if existente:
            st.warning(f"O período {mes_fec:02d}/{ano_fec} já está **FECHADO** (encerrado por {existente.fechado_por} em {existente.fechado_em.strftime('%d/%m/%Y %H:%M')}).")
        else:
            dados_prev = consolidado_mes(db(), int(ano_fec), int(mes_fec))
            st.info(f"📊 **Prévia de {mes_fec:02d}/{ano_fec}:**  \n"
                    f"- Faturamento Realizado: {fmt_br(dados_prev['faturamento_realizado'])}  \n"
                    f"- Despesas: {fmt_br(dados_prev['total_despesas'])}  \n"
                    f"- Lucro Líquido: {fmt_br(dados_prev['lucro_liquido'])}")
            
            confirmar_fec = st.checkbox("Confirmo os valores acima e desejo bloquear este período para alterações.", key=f"conf_fec_{ref_fec}")
            if st.button("🔒 Encerrar Mês", type="primary", disabled=not confirmar_fec, key=f"btn_fec_{ref_fec}"):
                try:
                    db().add(FechamentoMensal(
                        mes_referencia=ref_fec,
                        fechado_por=st.session_state.username,
                        total_recebido=dados_prev['faturamento_realizado'],
                        total_despesas=dados_prev['total_despesas']
                    ))
                    db().commit()
                    from app.services.auditoria import registrar
                    registrar(db(), st.session_state.username, "FECHAMENTO_MES", f"mes={ref_fec} realizado={dados_prev['faturamento_realizado']} despesas={dados_prev['total_despesas']}")
                    flash(f"Mês {mes_fec:02d}/{ano_fec} fechado com sucesso!", "success")
                    st.rerun()
                except Exception as e:
                    db().rollback()
                    st.error(f"Erro ao fechar o mês: {e}")
                    
        # --- HISTÓRICO DE FECHAMENTOS ---
        st.markdown("---")
        st.markdown("### 📜 Histórico de Períodos Fechados")
        fechados = db().query(FechamentoMensal).order_by(FechamentoMensal.mes_referencia.desc()).all()
        
        if not fechados:
            st.info("Nenhum período foi fechado ainda.")
        else:
            for f in fechados:
                f_mes_str = f.mes_referencia.split("-")
                f_rotulo = f"{f_mes_str[1]}/{f_mes_str[0]}"
                
                c_info, c_action = st.columns([3, 1])
                with c_info:
                    st.markdown(f"🔒 **{f_rotulo}** — Fechado por **{f.fechado_por}** em {f.fechado_em.strftime('%d/%m/%Y %H:%M')}  \n"
                                f"💰 Realizado: {fmt_br(f.total_recebido)} | Despesas: {fmt_br(f.total_despesas)} | Lucro: {fmt_br(f.total_recebido - f.total_despesas)}")
                with c_action:
                    perfil_atual = st.session_state.get("perfil")
                    if perfil_atual in ["Dona", "Programador"]:
                        if st.button("🔓 Reabrir", key=f"reabrir_{f.mes_referencia}"):
                            st.session_state[f"reabrir_dialog_{f.mes_referencia}"] = True
                    else:
                        st.caption("🔒 Reabertura restrita")
                        
                if st.session_state.get(f"reabrir_dialog_{f.mes_referencia}"):
                    with st.form(f"form_reabrir_{f.mes_referencia}"):
                        st.warning(f"⚠️ Você está prestes a reabrir o período {f_rotulo}.")
                        justificativa = st.text_input("Justificativa (Obrigatória)", key=f"just_{f.mes_referencia}")
                        col_b1, col_b2 = st.columns(2)
                        if col_b1.form_submit_button("Confirmar Reabertura"):
                            if not justificativa.strip():
                                st.error("A justificativa é obrigatória.")
                            else:
                                try:
                                    db().delete(f)
                                    db().commit()
                                    from app.services.auditoria import registrar
                                    registrar(db(), st.session_state.username, "REABERTURA_MES", f"mes={f.mes_referencia} justificativa={justificativa.strip()}")
                                    del st.session_state[f"reabrir_dialog_{f.mes_referencia}"]
                                    flash(f"Mês {f_rotulo} reaberto com sucesso!", "success")
                                    st.rerun()
                                except Exception as e:
                                    db().rollback()
                                    st.error(f"Erro ao reabrir o mês: {e}")
                        if col_b2.form_submit_button("Cancelar"):
                            del st.session_state[f"reabrir_dialog_{f.mes_referencia}"]
                            st.rerun()

    # ===== DESPESAS DETALHADAS =====
    st.subheader("💸 Despesas do período")
    refs_periodo = [f"{int(ano):04d}-{m:02d}" for m in meses]
    desps = db().query(Despesa).filter(
        Despesa.mes_referencia.in_(refs_periodo)).order_by(
        Despesa.data_vencimento).all()
    if not desps:
        st.info("Sem despesas lançadas no período.")
    hoje = datetime.now().date()
    for d in desps:
        dias = (d.data_vencimento - hoje).days
        if d.paga:
            cor = "🟢"
            status = f"Paga em {d.data_pagamento.strftime('%d/%m/%Y') if d.data_pagamento else '?'}"
        elif dias < 0:
            cor = "🔴"
            status = f"ATRASADA há {-dias} dia(s)"
        elif dias <= 7:
            cor = "🟡"
            status = f"Vence em {dias} dia(s)"
        else:
            cor = "⚪"
            status = f"Vence em {dias} dia(s)"
        c1, c_comp, c2, c3, c4 = st.columns([4, 1.5, 1, 1, 1])
        fixa_tag = " 📌FIXA" if d.recorrente else ""
        c1.write(f"{cor} **{d.descricao}**{fixa_tag} — {fmt_br(d.valor)} — "
                 f"venc. {d.data_vencimento.strftime('%d/%m/%Y')} — {status}")
        
        # Download do Comprovante
        if d.comprovante_nome:
            import os
            from app.services.comprovantes import obter_comprovante_caminho
            caminho = obter_comprovante_caminho(d.comprovante_nome)
            if caminho and os.path.exists(caminho):
                with open(caminho, "rb") as f:
                    btn_data = f.read()
                nome_dl = d.comprovante_nome_original or d.comprovante_nome
                mime_dl = d.comprovante_mime or "application/octet-stream"
                c_comp.download_button(
                    label="📎 Comprovante",
                    data=btn_data,
                    file_name=nome_dl,
                    mime=mime_dl,
                    key=f"dl_comp_{d.id_despesa}"
                )
            else:
                c_comp.write("⚠️ Arquivo ausente")
        else:
            c_comp.write("—")

        if not d.paga and c2.button("Pagar", key=f"pg_{d.id_despesa}"):
            from app.services.financeiro import is_mes_fechado
            if is_mes_fechado(db(), d.mes_referencia):
                flash(f"Erro: O período {d.mes_referencia} está fechado para edições.", "error")
                st.rerun()
            d.paga = True
            d.data_pagamento = hoje
            db().commit(); st.rerun()
        if c3.button("Editar", key=f"ed_{d.id_despesa}"):
            st.session_state[f"edd_{d.id_despesa}"] = True
        if c4.button("Excluir", key=f"dd_{d.id_despesa}"):
            from app.services.financeiro import is_mes_fechado
            if is_mes_fechado(db(), d.mes_referencia):
                flash(f"Erro: O período {d.mes_referencia} está fechado para edições.", "error")
                st.rerun()
            try:
                if not d.recorrente:
                    mae = db().query(Despesa).filter(
                        Despesa.descricao == d.descricao,
                        Despesa.recorrente == True).first()  # noqa: E712
                    if mae and mae.id_despesa != d.id_despesa:
                        db().delete(mae)
                from app.services.comprovantes import deletar_comprovante
                if d.comprovante_nome:
                    deletar_comprovante(d.comprovante_nome)
                db().delete(d)
                db().commit()
                db().expire_all()
                st.rerun()
            except Exception as e:
                db().rollback()
                st.error(f"Erro: {e}")
        if st.session_state.get(f"edd_{d.id_despesa}"):
            with st.form(f"fed_{d.id_despesa}"):
                ndesc = st.text_input("Descrição", value=d.descricao,
                    key=f"ndsc_{d.id_despesa}")
                nval = st.number_input("Valor", min_value=0.0,
                    value=float(d.valor), step=10.0,
                    key=f"nval_{d.id_despesa}")
                nvenc = st.date_input("Vencimento", value=d.data_vencimento,
                    format="DD/MM/YYYY", key=f"nvc_{d.id_despesa}")
                
                # Attachment uploader in edit form
                comp_file = st.file_uploader("Comprovante (PDF, Imagem)", type=["pdf", "png", "jpg", "jpeg"], key=f"comp_u_{d.id_despesa}")
                del_comp = False
                if d.comprovante_nome:
                    nome_exib = d.comprovante_nome_original or d.comprovante_nome
                    tamanho_kb = f" ({d.comprovante_tamanho // 1024} KB)" if d.comprovante_tamanho else ""
                    enviado_em = f" — enviado em {d.comprovante_enviado_em.strftime('%d/%m/%Y %H:%M')}" if d.comprovante_enviado_em else ""
                    st.caption(f"📎 Comprovante atual: **{nome_exib}**{tamanho_kb}{enviado_em}")
                    del_comp = st.checkbox("Excluir comprovante atual?", key=f"comp_d_{d.id_despesa}")

                cb1, cb2 = st.columns(2)
                if cb1.form_submit_button("Salvar"):
                    from app.services.financeiro import is_mes_fechado
                    new_ref = f"{nvenc.year:04d}-{nvenc.month:02d}"
                    ok_v, res_v = validar_valor_despesa(Decimal(str(nval)))
                    if is_mes_fechado(db(), d.mes_referencia):
                        st.error(f"Erro: O período original ({d.mes_referencia}) está fechado para edições.")
                    elif is_mes_fechado(db(), new_ref):
                        st.error(f"Erro: O novo período ({new_ref}) está fechado para edições.")
                    elif not ok_v:
                        st.error(res_v)
                    else:
                        from app.services.comprovantes import (
                            salvar_comprovante, deletar_comprovante,
                            aplicar_metadados_comprovante, limpar_metadados_comprovante,
                            ComprovantesError
                        )
                        from app.screens.shared import registrar
                        try:
                            if del_comp:
                                deletar_comprovante(d.comprovante_nome)
                                limpar_metadados_comprovante(d)
                                registrar(db(), st.session_state.username, "COMPROVANTE_REMOVIDO",
                                          f"despesa_id={d.id_despesa} arquivo={d.comprovante_nome}")
                            if comp_file:
                                if d.comprovante_nome:
                                    deletar_comprovante(d.comprovante_nome)
                                meta = salvar_comprovante(comp_file, "despesa", d.id_despesa)
                                aplicar_metadados_comprovante(d, meta)
                                registrar(db(), st.session_state.username, "COMPROVANTE_ANEXADO",
                                          f"despesa_id={d.id_despesa} arquivo={meta['nome']} mime={meta['mime']} bytes={meta['tamanho']}")
                        except ComprovantesError as ce:
                            st.error(str(ce))
                            st.stop()
                            
                        d.descricao = ndesc
                        d.valor = Decimal(str(nval))
                        d.data_vencimento = nvenc
                        d.mes_referencia = new_ref
                        db().commit()
                        del st.session_state[f"edd_{d.id_despesa}"]
                        st.rerun()
                if cb2.form_submit_button("Cancelar"):
                    del st.session_state[f"edd_{d.id_despesa}"]
                    st.rerun()

    # ===== LANCAR DESPESA =====
    with st.expander("➕ Lançar despesa"):
        DESPESAS_PADRAO = [
            "— Selecione —", "Aluguel", "Condomínio", "IPTU",
            "Seguro Incêndio / Seguro Fiança",
            "Energia Elétrica", "Água", "Internet e Telefone",
            "Secretária — Salário Base", "Secretária — Vale-Transporte",
            "Secretária — FGTS", "Secretária — INSS Patronal",
            "Secretária — Provisão 13º Salário",
            "Secretária — Provisão Férias + 1/3",
            "Secretária — Vale-Alimentação/Refeição",
            "Secretária — Seguro de Vida",
            "Secretária PJ — Pagamento mensal",
            "Outro (digitar)"]
        cat = st.selectbox("Categoria", DESPESAS_PADRAO, key="desp_cat")
        desc_livre = ""
        if cat == "Outro (digitar)":
            desc_livre = st.text_input("Descrição", key="desp_desc")
        rec = st.checkbox("Despesa fixa (recorrente todo mês)",
            value=False, key="desp_rec",
            help="Útil para aluguel, salário, internet…")
        tem_fim = False
        if rec:
            tem_fim = st.checkbox("Tem data de término?", value=False,
                key="desp_tfim")
        hoje_ = datetime.now().date()
        ano_ini = mes_ini = dia_v = ano_fim = mes_fim_in = None
        if rec:
            cm1, cm2, cm3 = st.columns(3)
            ano_ini = cm1.number_input("Ano início", 2020, 2040,
                hoje_.year, key="desp_ano_ini")
            mes_ini = cm2.number_input("Mês início", 1, 12,
                hoje_.month, key="desp_mes_ini")
            dia_v = cm3.number_input("Dia do mês", 1, 31, 5,
                key="desp_dia_v")
            if tem_fim:
                cf1, cf2 = st.columns(2)
                ano_fim = cf1.number_input("Ano fim",
                    int(ano_ini), 2040, int(ano_ini),
                    key="desp_ano_fim")
                mes_fim_in = cf2.number_input("Mês fim", 1, 12,
                    int(mes_ini), key="desp_mes_fim")
        with st.form("desp"):
            val = st.number_input("Valor", min_value=0.0, step=50.0)
            if not rec:
                venc = st.date_input("Vencimento", format="DD/MM/YYYY")
            comp_file = st.file_uploader("Comprovante (PDF, Imagem)", type=["pdf", "png", "jpg", "jpeg"], key="new_desp_comp")
            if st.form_submit_button("Salvar"):
                descricao = desc_livre if cat == "Outro (digitar)" else cat
                ok_val, res_val = validar_valor_despesa(Decimal(str(val)))
                from app.services.financeiro import is_mes_fechado
                
                # Verifica se o período correspondente está fechado
                fechado = False
                if not rec:
                    if is_mes_fechado(db(), venc):
                        st.error(f"Erro: O período {venc.strftime('%m/%Y')} está fechado para novos lançamentos.")
                        fechado = True
                else:
                    ref_ini = f"{int(ano_ini):04d}-{int(mes_ini):02d}"
                    if is_mes_fechado(db(), ref_ini):
                        st.error(f"Erro: O período de início {int(mes_ini):02d}/{int(ano_ini)} está fechado para novos lançamentos.")
                        fechado = True
                
                if fechado:
                    pass
                elif not descricao or descricao == "— Selecione —":
                    st.error("Escolha uma categoria.")
                elif not ok_val:
                    st.error(res_val)
                elif rec and tem_fim and (int(ano_fim), int(mes_fim_in)) < (int(ano_ini), int(mes_ini)):
                    st.error("Mês fim não pode ser anterior ao Mês início.")
                else:
                    if rec:
                        import calendar as cal2
                        _, td = cal2.monthrange(int(ano_ini), int(mes_ini))
                        dia = min(int(dia_v), td)
                        venc_calc = date(int(ano_ini), int(mes_ini), dia)
                        mes_fim_str = (f"{int(ano_fim):04d}-{int(mes_fim_in):02d}"
                                       if tem_fim else None)
                        eh_pass = (int(ano_ini), int(mes_ini)) < (hoje_.year, hoje_.month)
                        nova_desp = Despesa(descricao=descricao,
                            valor=Decimal(str(val)),
                            data_vencimento=venc_calc,
                            mes_referencia=f"{int(ano_ini):04d}-{int(mes_ini):02d}",
                            recorrente=True,
                            dia_vencimento_mes=int(dia_v),
                            mes_fim=mes_fim_str,
                            paga=eh_pass,
                            data_pagamento=venc_calc if eh_pass else None)
                        db().add(nova_desp)
                    else:
                        eh_pass = venc < hoje_
                        nova_desp = Despesa(descricao=descricao,
                            valor=Decimal(str(val)), data_vencimento=venc,
                            mes_referencia=f"{venc.year:04d}-{venc.month:02d}",
                            recorrente=False,
                            paga=eh_pass,
                            data_pagamento=venc if eh_pass else None)
                        db().add(nova_desp)
                    
                    if comp_file:
                        db().flush()
                        from app.services.comprovantes import (
                            salvar_comprovante, aplicar_metadados_comprovante, ComprovantesError
                        )
                        from app.screens.shared import registrar
                        try:
                            meta = salvar_comprovante(comp_file, "despesa", nova_desp.id_despesa)
                            aplicar_metadados_comprovante(nova_desp, meta)
                            registrar(db(), st.session_state.username, "COMPROVANTE_ANEXADO",
                                      f"despesa_id={nova_desp.id_despesa} arquivo={meta['nome']} mime={meta['mime']} bytes={meta['tamanho']}")
                        except ComprovantesError as ce:
                            st.error(str(ce))
                    
                    db().commit()
                    if rec:
                        msg_mes = f"{int(mes_ini):02d}/{int(ano_ini)}"
                    else:
                        msg_mes = f"{venc.month:02d}/{venc.year}"
                    st.success(f"Despesa lançada no mês {msg_mes}. "
                        f"Mude o filtro 'Mês' acima para {msg_mes} para vê-la."
                        + (" Será gerada nos próximos meses do intervalo."
                           if rec else ""))

    # ===== DESPESAS FIXAS (RECORRENTES) =====
    with st.expander("📌 Despesas fixas cadastradas"):
        fixas = db().query(Despesa).filter(
            Despesa.recorrente == True).all()  # noqa: E712
        if not fixas:
            st.info("Nenhuma despesa fixa cadastrada.")
        for d in fixas:
            c1, c2, c3 = st.columns([5, 1, 1])
            c1.write(f"**{d.descricao}** — {fmt_br(d.valor)} — "
                     f"dia {d.dia_vencimento_mes or d.data_vencimento.day} "
                     f"de cada mês — desde {d.mes_referencia}")
            if c2.button("Editar valor", key=f"ev_{d.id_despesa}"):
                st.session_state[f"edd_{d.id_despesa}"] = True
            if c3.button("Remover fixa", key=f"rf_{d.id_despesa}"):
                d.recorrente = False
                db().commit(); st.rerun()
            if st.session_state.get(f"edd_{d.id_despesa}"):
                with st.form(f"fdd_{d.id_despesa}"):
                    nv = st.number_input("Novo valor",
                        min_value=0.0, value=float(d.valor), step=50.0,
                        key=f"nvd_{d.id_despesa}")
                    if st.form_submit_button("Salvar"):
                        ok_v, res_v = validar_valor_despesa(Decimal(str(nv)))
                        if not ok_v:
                            st.error(res_v)
                        else:
                            d.valor = Decimal(str(nv))
                            db().commit()
                            del st.session_state[f"edd_{d.id_despesa}"]
                            st.rerun()
