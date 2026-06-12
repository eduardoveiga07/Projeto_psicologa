import streamlit as st
from datetime import datetime, date
from decimal import Decimal
from app.screens.shared import db, mostrar_flash, flash, Despesa, Perfil
from app.services.financeiro import fmt_br, expandir_recorrentes, consolidado_periodo, historico_ultimos_meses
from app.services.pdf_export import gerar_pdf

# Importa o validador de despesas
from app.services.validacao_negocio import validar_valor_despesa


def tela_financeiro():
    mostrar_flash()
    st.header("Financeiro — Previsto vs Realizado")
    c1, c2, c3 = st.columns(3)
    ano = c1.number_input("Ano", 2024, 2040, datetime.now().year)
    periodo = c2.selectbox("Período",
        ["Mensal", "Trimestral", "Semestral", "Anual"])

    if periodo == "Mensal":
        m = c3.number_input("Mês", 1, 12, datetime.now().month)
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
    k1.metric("Faturamento Previsto", fmt_br(r["faturamento_previsto"]))
    k2.metric("Faturamento Realizado", fmt_br(r["faturamento_realizado"]))
    k3.metric("Inadimplência / Pendente", fmt_br(r.get("inadimplencia", Decimal(0))))
    k4.metric("Lucro Líquido", fmt_br(r["lucro_liquido"]))
    st.caption(f"💰 Total de despesas: {fmt_br(r['total_despesas'])} — detalhe na seção '💸 Despesas do período' mais abaixo")

    if r["linhas"]:
        import plotly.graph_objects as go
        
        tab_evolucao, tab_pacientes, tab_despesas = st.tabs([
            "📈 Evolução Temporal",
            "👥 Faturamento por Paciente",
            "💸 Distribuição de Despesas"
        ])
        
        with tab_evolucao:
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

        with tab_pacientes:
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

        with tab_despesas:
            # Buscar despesas do período agrupadas por descrição
            refs_periodo = [f"{int(ano):04d}-{mm:02d}" for mm in meses]
            despesas_db = db().query(Despesa).filter(
                Despesa.mes_referencia.in_(refs_periodo)).all()
                
            contagem_desp = {}
            for d in despesas_db:
                contagem_desp[d.descricao] = contagem_desp.get(d.descricao, Decimal(0)) + d.valor
                
            if contagem_desp:
                labels = list(contagem_desp.keys())
                valores_desp = [float(v) for v in contagem_desp.values()]
                
                fig_desp = go.Figure(data=[go.Pie(
                    labels=labels,
                    values=valores_desp,
                    hole=0.4,
                    hoverinfo="label+percent+value",
                    textinfo="percent"
                )])
                
                fig_desp.update_layout(
                    title="Divisão de Despesas por Categoria",
                    template="plotly_dark",
                    margin=dict(t=40, b=20, l=10, r=10),
                    height=350
                )
                st.plotly_chart(fig_desp, use_container_width=True)
            else:
                st.info("Sem despesas lançadas no período para exibir o gráfico.")

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
    
    st.download_button("Baixar PDF",
        gerar_pdf(f"Financeiro — {rotulo}", fin_rows, filtros=filtros_pdf, totais=totais_pdf),
        file_name=f"financeiro_{rotulo.replace('/', '_')}.pdf", mime="application/pdf")

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
        c1, c2, c3, c4 = st.columns([5, 1, 1, 1])
        fixa_tag = " 📌FIXA" if d.recorrente else ""
        c1.write(f"{cor} **{d.descricao}**{fixa_tag} — {fmt_br(d.valor)} — "
                 f"venc. {d.data_vencimento.strftime('%d/%m/%Y')} — {status}")
        if not d.paga and c2.button("Pagar", key=f"pg_{d.id_despesa}"):
            d.paga = True
            d.data_pagamento = hoje
            db().commit(); st.rerun()
        if c3.button("Editar", key=f"ed_{d.id_despesa}"):
            st.session_state[f"edd_{d.id_despesa}"] = True
        if c4.button("Excluir", key=f"dd_{d.id_despesa}"):
            try:
                if not d.recorrente:
                    mae = db().query(Despesa).filter(
                        Despesa.descricao == d.descricao,
                        Despesa.recorrente == True).first()  # noqa: E712
                    if mae and mae.id_despesa != d.id_despesa:
                        db().delete(mae)
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
                cb1, cb2 = st.columns(2)
                if cb1.form_submit_button("Salvar"):
                    ok_v, res_v = validar_valor_despesa(Decimal(str(nval)))
                    if not ok_v:
                        st.error(res_v)
                    else:
                        d.descricao = ndesc
                        d.valor = Decimal(str(nval))
                        d.data_vencimento = nvenc
                        d.mes_referencia = f"{nvenc.year:04d}-{nvenc.month:02d}"
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
            if st.form_submit_button("Salvar"):
                descricao = desc_livre if cat == "Outro (digitar)" else cat
                ok_val, res_val = validar_valor_despesa(Decimal(str(val)))
                
                if not descricao or descricao == "— Selecione —":
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
                        db().add(Despesa(descricao=descricao,
                            valor=Decimal(str(val)),
                            data_vencimento=venc_calc,
                            mes_referencia=f"{int(ano_ini):04d}-{int(mes_ini):02d}",
                            recorrente=True,
                            dia_vencimento_mes=int(dia_v),
                            mes_fim=mes_fim_str,
                            paga=eh_pass,
                            data_pagamento=venc_calc if eh_pass else None))
                    else:
                        eh_pass = venc < hoje_
                        db().add(Despesa(descricao=descricao,
                            valor=Decimal(str(val)), data_vencimento=venc,
                            mes_referencia=f"{venc.year:04d}-{venc.month:02d}",
                            recorrente=False,
                            paga=eh_pass,
                            data_pagamento=venc if eh_pass else None))
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
