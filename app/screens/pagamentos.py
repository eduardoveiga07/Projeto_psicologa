import streamlit as st
from datetime import datetime, date, time
from app.screens.shared import (
    db, mostrar_flash, flash, Paciente, AgendaSessao, StatusPaciente,
    StatusPresenca, StatusPagamento, FAIXAS_HORARIO
)
from app.services.pdf_export import gerar_pdf


def tela_pagamentos():
    mostrar_flash()
    st.header("Controle de Pagamentos")
    st.caption("Regra: cancelou +24h ou imprevisto = isento. "
               "Cancelou -24h = cobra. Realizada = cobra.")

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
                        st.success(f"Sessão de {dt_r.strftime('%d/%m/%Y')} "
                                   "lançada.")
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
        p = db().get(Paciente, s.id_paciente)
        todas.append({
            "Paciente": p.nome if p else "?",
            "Data": s.data_hora_inicio.strftime("%d/%m/%Y %H:%M"),
            "Situação": s.status_presenca.value,
            "Pagamento": s.status_pagamento.value,
            "Valor": float(p.valor_sessao) if p else 0})
    st.download_button("Baixar PDF (todos os pagamentos)",
        gerar_pdf("Controle de Pagamentos", todas),
        file_name="pagamentos_todos.pdf", mime="application/pdf")

    for s in sessoes:
        p = db().get(Paciente, s.id_paciente)
        nome = p.nome if p else "?"
        quando = s.data_hora_inicio.strftime("%d/%m/%Y %H:%M")
        with st.expander(f"{nome} — {quando} — "
                         f"{s.status_presenca.value} / "
                         f"{s.status_pagamento.value}"):
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

    # Resumo de inadimplencia
    pend = db().query(AgendaSessao).filter(
        AgendaSessao.status_pagamento.in_([
            StatusPagamento.PENDENTE, StatusPagamento.ATRASADO]),
        AgendaSessao.status_presenca != StatusPresenca.CANCELADA).all()
    st.subheader(f"Pagamentos em aberto: {len(pend)}")
    linhas = []
    for s in pend:
        p = db().get(Paciente, s.id_paciente)
        linhas.append({
            "Paciente": p.nome if p else "?",
            "Data": s.data_hora_inicio.strftime("%d/%m/%Y %H:%M"),
            "Situação": s.status_presenca.value,
            "Pagamento": s.status_pagamento.value,
            "Valor": float(p.valor_sessao) if p else 0})
    if linhas:
        st.dataframe(linhas, use_container_width=True)
        st.download_button("Baixar PDF (em aberto)",
            gerar_pdf("Pagamentos em Aberto", linhas),
            file_name="pagamentos_aberto.pdf", mime="application/pdf")
