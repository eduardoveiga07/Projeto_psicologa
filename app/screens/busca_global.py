import streamlit as st
from app.screens.shared import db, ui_header, Paciente, AgendaSessao, Despesa
from app.services.financeiro import fmt_br

# Limite máximo de resultados por categoria (evita lentidão com grandes bases)
_LIMITE_RESULTADOS = 10
# Mínimo de caracteres para realizar a busca
MIN_CHARS_BUSCA = 3


def tela_busca_global(query: str):
    """Tela de resultados de busca global no banco de dados.

    Limitada a 10 resultados por categoria e requer pelo menos 3 caracteres.
    """
    query = query.strip()

    if len(query) < MIN_CHARS_BUSCA:
        ui_header("Busca Global", icon="🔍")
        st.info(f"⌨️ Digite pelo menos {MIN_CHARS_BUSCA} caracteres para iniciar a busca. "
                f"(atual: {len(query)} {'caractere' if len(query) == 1 else 'caracteres'})")
        return

    ui_header("Resultados da Busca Global", f"Exibindo até {_LIMITE_RESULTADOS} resultados por categoria para: **'{query}'**", icon="🔍")

    # 1. Buscar Pacientes (top 10)
    pacs = db().query(Paciente).filter(
        (Paciente.nome.ilike(f"%{query}%")) |
        (Paciente.email.ilike(f"%{query}%")) |
        (Paciente.telefone.ilike(f"%{query}%"))
    ).limit(_LIMITE_RESULTADOS).all()

    # 2. Buscar Despesas (top 10)
    desps = db().query(Despesa).filter(
        Despesa.descricao.ilike(f"%{query}%")
    ).order_by(Despesa.data_vencimento.desc()).limit(_LIMITE_RESULTADOS).all()

    # 3. Buscar Sessões por nome do paciente (top 10 mais recentes)
    sessoes = db().query(AgendaSessao).join(Paciente).filter(
        Paciente.nome.ilike(f"%{query}%")
    ).order_by(AgendaSessao.data_hora_inicio.desc()).limit(_LIMITE_RESULTADOS).all()

    total = len(pacs) + len(desps) + len(sessoes)
    if total == 0:
        st.warning(f"Nenhum resultado encontrado para **'{query}'**.")
        return

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader(f"👥 Pacientes ({len(pacs)})")
        if not pacs:
            st.info("Nenhum paciente encontrado.")
        else:
            for p in pacs:
                status_cor = "🟢" if p.status.value == "Ativo" else "🔴"
                st.markdown(f"**{p.nome}** ({status_cor} {p.status.value})")
                st.caption(f"📞 {p.telefone or '-'} | ✉️ {p.email or '-'} | 💰 {fmt_br(p.valor_sessao)}/sessão")
                st.divider()

        st.subheader(f"💸 Despesas ({len(desps)})")
        if not desps:
            st.info("Nenhuma despesa encontrada.")
        else:
            for d in desps:
                paga_tag = "🟢 Paga" if d.paga else "🔴 Pendente"
                st.markdown(f"**{d.descricao}** — {fmt_br(d.valor)} ({paga_tag})")
                st.caption(f"📅 Vencimento: {d.data_vencimento.strftime('%d/%m/%Y')} | Ref: {d.mes_referencia}")
                st.divider()

    with col2:
        st.subheader(f"📅 Sessões ({len(sessoes)})")
        if not sessoes:
            st.info("Nenhuma sessão encontrada.")
        else:
            for s in sessoes:
                p = s.paciente
                pago_tag = "🟢 Pago" if s.status_pagamento.value == "Pago" else "🔴 Pendente"
                st.markdown(f"**{p.nome}** — {s.data_hora_inicio.strftime('%d/%m/%Y %H:%M')}")
                st.caption(f"⚡ {s.status_presenca.value} | 💰 {pago_tag} | Valor: {fmt_br(s.valor_sessao or p.valor_sessao)}")
                st.divider()
