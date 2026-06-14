import os
import streamlit as st
from datetime import datetime
from sqlalchemy import text

from app.screens.shared import db, ui_header, ui_kpi_card, registrar, flash, mostrar_flash
from app.db.models import SistemaStatus

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

    # 2. Busca informações de backups e restores (apenas em desenvolvimento)
    ambiente = os.getenv("AMBIENTE", "desenvolvimento").lower()
    is_prod = (ambiente == "producao")

    ult_backup = None
    ult_teste = None
    if not is_prod:
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
    ambiente_label = ambiente.capitalize()
    versao_app = "1.1.0"

    # Seção de Métricas Principais (KPIs)
    col1, col2, col3 = st.columns(3)
    with col1:
        ui_kpi_card("Conexão do Banco", status_db, delta=detalhes_db)
    
    if is_prod:
        with col2:
            ui_kpi_card("Backups em Produção", "NATIVO / ATIVO", delta="Gerenciado automaticamente pelo Neon DB", delta_color="normal")
        with col3:
            ui_kpi_card("Recuperação (PITR)", "7 A 30 DIAS", delta="Restauração contínua via console.neon.tech", delta_color="normal")
    else:
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
    cc2.metric("Ambiente de Execução", ambiente_label)
    cc3.metric("Revisão Alembic (Head)", versao_alembic)

    st.write("---")

    # Ações manuais administrativas
    st.subheader("⚡ Manutenção e Backups")
    st.info(
        "💎 **Estratégia de Backups Automáticos Nativos (Neon PITR)**\n\n"
        "Este aplicativo utiliza o banco de dados serverless **Neon**, que gerencia backups de forma nativa e contínua (Point-in-Time Recovery):\n"
        "- **Backups Contínuos:** Cada transação e alteração do banco de dados é salva em tempo real. Você pode restaurar o banco para qualquer segundo exato dos últimos 7 dias (plano gratuito) ou até 30 dias (planos pagos).\n"
        "- **Restauração Simples:** Acesse o painel do [Neon Console](https://console.neon.tech/), selecione seu projeto, vá em **Snapshots** ou **Branches**, escolha o ponto exato no tempo e restaure ou crie uma nova ramificação de testes instantaneamente.\n"
        "- **Performance Preservada:** Não há execução de dumps locais pesados na aplicação, prevenindo picos de consumo de RAM e CPU no Streamlit Cloud."
    )

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
