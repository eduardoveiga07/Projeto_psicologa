import os
import streamlit as st
from datetime import datetime
from sqlalchemy import text

from app.screens.shared import db, ui_header, ui_kpi_card, registrar, flash, mostrar_flash
from app.db.models import SistemaStatus
from app.services.scheduler import executar_backup_diario, executar_teste_restauracao

def tela_saude():
    # Segurança de acesso fora da UI
    if st.session_state.get("perfil") not in ["Dona", "Programador"]:
        st.error("Acesso negado. Permissão insuficiente para visualizar o painel de saúde do sistema.")
        st.stop()

    mostrar_flash()
    ui_header("Painel de Saúde do Sistema", icon="🛡️")
    st.caption("Monitore a integridade do banco de dados, backups automáticos, testes estruturais e logs técnicos do sistema.")

    s = db()

    # 1. Verifica conexão com o banco de dados
    status_db = "🔴 Desconectado"
    detalhes_db = "Falha crítica ao tentar pingar o banco de dados."
    try:
        s.execute(text("SELECT 1;"))
        status_db = "🟢 Saudável (Conectado)"
        detalhes_db = "PostgreSQL operacional na nuvem/host."
    except Exception as e:
        detalhes_db = f"Erro: {e}"

    # 2. Busca informações de backups e restores
    ult_backup = s.query(SistemaStatus).filter(SistemaStatus.tipo == "backup").order_by(SistemaStatus.quando.desc()).first()
    ult_teste = s.query(SistemaStatus).filter(SistemaStatus.tipo == "teste_restauracao").order_by(SistemaStatus.quando.desc()).first()

    # 3. Busca última migração Alembic
    versao_alembic = "Desconhecida"
    try:
        res = s.execute(text("SELECT version_num FROM alembic_version;")).scalar()
        if res:
            versao_alembic = res
    except Exception:
        versao_alembic = "Sem tabela de controle (Alembic não executado ou tabela ausente)"

    # Ambiente de execução e Versão
    ambiente = os.getenv("AMBIENTE", "desenvolvimento").capitalize()
    versao_app = "1.1.0"

    # Seção de Métricas Principais (KPIs)
    col1, col2, col3 = st.columns(3)
    with col1:
        ui_kpi_card("Conexão do Banco", status_db, delta=detalhes_db)
    with col2:
        if ult_backup:
            status_cor = "normal" if ult_backup.status == "sucesso" else "inverse"
            det_bk = f"Status: {ult_backup.status.capitalize()} em {ult_backup.quando.strftime('%d/%m %H:%M')}"
            ui_kpi_card("Último Backup", ult_backup.status.upper(), delta=det_bk, delta_color=status_cor)
        else:
            ui_kpi_card("Último Backup", "Nenhum realizado", delta="Nenhum log encontrado")
    with col3:
        if ult_teste:
            status_cor = "normal" if ult_teste.status == "sucesso" else "inverse"
            det_ts = f"Status: {ult_teste.status.capitalize()} em {ult_teste.quando.strftime('%d/%m %H:%M')}"
            ui_kpi_card("Teste Restauração", ult_teste.status.upper(), delta=det_ts, delta_color=status_cor)
        else:
            ui_kpi_card("Teste Restauração", "Nenhum realizado", delta="Nenhum log encontrado")

    st.markdown("<br>", unsafe_allow_html=True)
    
    st.subheader("⚙️ Propriedades do Ambiente")
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("Versão da Aplicação", f"v{versao_app}")
    cc2.metric("Ambiente de Execução", ambiente)
    cc3.metric("Revisão Alembic (Head)", versao_alembic)

    st.write("---")

    # Ações manuais administrativas
    st.subheader("⚡ Ações de Manutenção Manual")
    ca1, ca2 = st.columns(2)
    
    if ca1.button("📁 Executar Backup Diário Agora", type="primary", use_container_width=True):
        with st.spinner("Executando backup e criptografia do banco de dados..."):
            executar_backup_diario()
            registrar(s, st.session_state.username, "MANUAL_BACKUP", "sucesso")
            flash("Backup manual executado com sucesso e log registrado.", "success")
            st.rerun()

    if ca2.button("🔍 Executar Teste de Restauração Agora", use_container_width=True):
        with st.spinner("Descriptografando e testando integridade estrutural do dump..."):
            executar_teste_restauracao()
            registrar(s, st.session_state.username, "MANUAL_RESTORE_TEST", "sucesso")
            flash("Teste manual de restauração executado. Veja o log do sistema abaixo.", "info")
            st.rerun()

    st.write("---")

    # Histórico de Rotinas de Sistema
    st.subheader("📋 Histórico das Rotinas de Sistema")
    rotinas = s.query(SistemaStatus).order_by(SistemaStatus.quando.desc()).limit(20).all()
    if not rotinas:
        st.info("Nenhum log de rotina (backup/teste) registrado no banco ainda.")
    else:
        dados_tabela = [{
            "Data/Hora": r.quando.strftime("%d/%m/%Y %H:%M:%S"),
            "Rotina": r.tipo.upper().replace("_", " "),
            "Resultado": r.status.upper(),
            "Detalhes Técnicos": r.detalhe or ""
        } for r in rotinas]
        st.dataframe(dados_tabela, use_container_width=True)

    st.write("---")

    # Visualizador de Logs Técnicos do Sistema
    st.subheader("🔍 Logs Técnicos Recentes (tecnico.log)")
    log_file_path = os.path.join("logs", "tecnico.log")
    
    if os.path.exists(log_file_path):
        try:
            with open(log_file_path, "r", encoding="utf-8") as f:
                linhas = f.readlines()
                # Pega as últimas 50 linhas
                ultimas_linhas = linhas[-50:]
                conteudo_log = "".join(ultimas_linhas)
                
            st.text_area("Exibindo as últimas 50 linhas do arquivo de log técnico:", 
                         value=conteudo_log, 
                         height=300, 
                         disabled=True)
            
            # Botão para limpar log técnico se for Programador
            if st.session_state.get("perfil") == "Programador":
                if st.button("Limpar Arquivo de Logs Técnicos"):
                    with open(log_file_path, "w", encoding="utf-8") as f:
                        f.write("")
                    registrar(s, st.session_state.username, "LOG_TECNICO_LIMPO", "sucesso")
                    flash("Arquivo de logs técnicos reiniciado.", "success")
                    st.rerun()
        except Exception as e:
            st.error(f"Erro ao ler arquivo de logs técnicos: {e}")
    else:
        st.info("O log em arquivo físico não está disponível ou está desativado neste ambiente (logs são direcionados diretamente ao console do servidor).")
