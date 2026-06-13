import streamlit as st
from datetime import datetime, date, time, timedelta
import plotly.graph_objects as go

from app.screens.shared import db, Usuario, ui_header
from app.db.models import Auditoria
from app.services.pdf_export import gerar_pdf


def tela_auditoria():
    if st.session_state.get("perfil") not in ["Dona", "Programador"]:
        st.error("Acesso negado. Permissão insuficiente para ver logs de auditoria.")
        st.stop()
    ui_header("Painel de Auditoria e Logs", icon="🛡️")
    st.caption("Acompanhe o histórico de todas as operações críticas e eventos de segurança realizados na plataforma.")

    # Obter a lista de usuários e ações para os filtros
    s = db()
    usuarios_db = s.query(Usuario).order_by(Usuario.username).all()
    lista_usuarios = ["Todos"] + [u.username for u in usuarios_db]

    acoes_db = s.query(Auditoria.acao).distinct().all()
    lista_acoes = ["Todas"] + [a[0] for a in acoes_db if a[0]]

    # Painel de filtros
    st.subheader("🔍 Filtros de Auditoria")
    c1, c2, c3, c4 = st.columns(4)
    
    hoje = date.today()
    trinta_dias_atras = hoje - timedelta(days=30)
    
    d_ini = c1.date_input("De", value=trinta_dias_atras, format="DD/MM/YYYY", key="aud_ini")
    d_fim = c2.date_input("Até", value=hoje, format="DD/MM/YYYY", key="aud_fim")
    user_sel = c3.selectbox("Usuário", lista_usuarios, key="aud_user")
    acao_sel = c4.selectbox("Ação", lista_acoes, key="aud_acao")

    # Conversão de datas para datetime cobrindo o dia completo
    dt_ini = datetime.combine(d_ini, time.min)
    dt_fim = datetime.combine(d_fim, time.max)

    # Executar query com os filtros
    query = s.query(Auditoria).filter(Auditoria.quando.between(dt_ini, dt_fim))
    
    if user_sel != "Todos":
        query = query.filter(Auditoria.usuario == user_sel)
    if acao_sel != "Todas":
        query = query.filter(Auditoria.acao == acao_sel)

    logs = query.order_by(Auditoria.quando.desc()).limit(1000).all()

    if not logs:
        st.info("Nenhum log de auditoria encontrado para os filtros selecionados.")
    else:
        st.subheader("📋 Histórico de Eventos")
        
        # Mapeamento para exibição na tabela e PDF
        linhas = [{
            "Data/Hora": l.quando.strftime("%d/%m/%Y %H:%M:%S"),
            "Usuário": l.usuario,
            "Ação": l.acao,
            "Detalhes": l.detalhe or "",
            "IP": l.ip or ""
        } for l in logs]

        st.dataframe(linhas, use_container_width=True, height=350)

        # Botão de exportação PDF
        pdf_titulo = "Trilha de Auditoria"
        filtros_pdf = {
            "Período": f"{d_ini.strftime('%d/%m/%Y')} a {d_fim.strftime('%d/%m/%Y')}",
            "Usuário": user_sel,
            "Ação": acao_sel
        }
        st.download_button(
            label="📥 Baixar Relatório de Auditoria (PDF)",
            data=gerar_pdf(pdf_titulo, linhas, filtros=filtros_pdf),
            file_name=f"auditoria_{d_ini.strftime('%Y%m%d')}_{d_fim.strftime('%Y%m%d')}.pdf",
            mime="application/pdf"
        )

        st.divider()

        # Gráfico Plotly com contagem das ações no período
        st.subheader("📊 Estatísticas das Ações")
        
        contagem = {}
        for l in logs:
            contagem[l.acao] = contagem.get(l.acao, 0) + 1
            
        acoes = list(contagem.keys())
        valores = list(contagem.values())

        fig = go.Figure(data=[
            go.Bar(
                x=acoes, 
                y=valores, 
                marker_color="#4a90e2",
                text=valores, 
                textposition="auto"
            )
        ])
        
        fig.update_layout(
            title="Distribuição de Ações no Período",
            xaxis_title="Ações", 
            yaxis_title="Quantidade",
            template="plotly_dark",
            margin=dict(t=40, b=40, l=10, r=10)
        )
        
        st.plotly_chart(fig, use_container_width=True)
