"""App Streamlit - Gestao Consultorio Psicologia. Roda: streamlit run app/main.py"""
import sys
import os
# Adiciona o diretorio raiz ao path para garantir as importacoes do modulo 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import locale
try:
    locale.setlocale(locale.LC_ALL, "pt_BR.UTF-8")
except locale.Error:
    pass
import streamlit as st
from datetime import datetime
from app.db.session import get_session, criar_tabelas
from app.db.models import Paciente, StatusPaciente, Perfil
from app.services.auditoria import registrar

# Telas Modulares
from app.screens.minha_conta import tela_minha_conta
from app.screens.usuarios import tela_usuarios
from app.screens.login import tela_login
from app.screens.calendario import tela_calendario
from app.screens.pagamentos import tela_pagamentos
from app.screens.financeiro import tela_financeiro
from app.screens.agenda import tela_agenda
from app.screens.cadastro import tela_cadastro
from app.screens.auditoria import tela_auditoria
from app.screens.saude import tela_saude
from app.screens.shared import db
from app.version import __version__

from app.auth.usuario_validacao import (
    normalizar_username,
    validar_email_opcional,
    validar_nome,
    validar_username,
    obter_telas_permitidas,
)

st.set_page_config(page_title="Gestão Consultório", layout="wide")

# Corrige legibilidade das listas suspensas no tema escuro.
st.markdown("""
<style>
ul[role="listbox"], div[data-baseweb="popover"] {
    background-color: #1c1f26 !important;
    opacity: 1 !important;
    backdrop-filter: none !important;
}
ul[role="listbox"] li { color: #f0f0f0 !important; opacity: 1 !important; }
ul[role="listbox"] li:hover { background-color: #2e3340 !important; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def _bootstrap():
    criar_tabelas()
    from app.auth.init_users import inicializar_usuarios
    inicializar_usuarios()
    # Migracao: garante 1 periodo de historico de contrato p/ pacientes existentes
    from app.services.contrato import garantir_historico_inicial
    s = get_session()
    try:
        garantir_historico_inicial(s)
    except Exception:
        s.rollback()
    finally:
        s.close()
    return True

_bootstrap()

# LGPD: auto-exclui pacientes inativos e logs antigos de acordo com a politica de retencao.
@st.cache_resource
def _executar_retencao_lgpd():
    from app.services.retencao_lgpd import executar_limpeza_lgpd
    s = get_session()
    try:
        executar_limpeza_lgpd(s)
    finally:
        s.close()
    return True
_executar_retencao_lgpd()



# ---------- ROUTER ----------

try:
    # Inicializa CookieController e tenta restaurar sessão
    from streamlit_cookies_controller import CookieController
    from app.auth.sessao import validar_token, renovar_token
    import time

    cookie_controller = CookieController()
    token = cookie_controller.get("consultorio_session")

    # Caveat de renderização inicial do Streamlit: se for a primeira execução e o cookie
    # ainda não estiver disponível no session_state (mas existir no browser),
    # força um rerun inicial para sincronizar.
    if token is None and "user" not in st.session_state and not st.session_state.get("cookie_checked", False):
        st.session_state.cookie_checked = True
        st.rerun()

    # Restaura a sessão a partir do cookie se o st.session_state estiver vazio
    if token and "user" not in st.session_state:
        payload = validar_token(token)
        if payload:
            from app.db.models import Usuario
            s_db = db()
            user_db = s_db.query(Usuario).filter(Usuario.id_usuario == payload["usuario_id"]).first()
            if user_db and user_db.ativo:
                st.session_state.user = user_db.nome
                st.session_state.username = user_db.username
                st.session_state.perfil = user_db.perfil.value
                st.session_state.id_usuario = user_db.id_usuario
                st.session_state.last_active = datetime.now()
                st.session_state.token_criado_em = payload["criado_em"]

    if "user" not in st.session_state:
        tela_login()
    else:
        # Timeout de inatividade (configurável via env)
        try:
            timeout_min = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))
        except ValueError:
            timeout_min = 30

        agora = datetime.now()
        ultima = st.session_state.get("last_active", agora)
        if (agora - ultima).total_seconds() > timeout_min * 60:
            registrar(db(), st.session_state.get("username", "?"),
                      "SESSAO_EXPIRADA", f"timeout {timeout_min}min inatividade")
            cookie_controller.remove("consultorio_session")
            st.session_state.clear()
            st.warning("Sessão expirada por inatividade. Faça login novamente.")
            st.stop()
        st.session_state.last_active = agora

        # Debounce de renovação do cookie de sessão a cada 5 minutos
        # E proteção ativa contra Privilege Escalation (query rápida de verificação do usuário)
        criado_em = st.session_state.get("token_criado_em", 0)
        if time.time() - criado_em >= 300: # 5 minutos
            from app.db.models import Usuario
            user_db = db().query(Usuario).filter(Usuario.username == st.session_state.username).first()
            if not user_db or not user_db.ativo or user_db.perfil.value != st.session_state.perfil:
                # O perfil mudou, ou o usuário foi inativado/removido
                cookie_controller.remove("consultorio_session")
                st.session_state.clear()
                st.warning("Sua sessão foi encerrada por alteração cadastral ou inativação.")
                st.stop()
            else:
                # Renova o token e atualiza o cookie
                payload_renov = {
                    "usuario_id": st.session_state.get("id_usuario"),
                    "username": st.session_state.username,
                    "perfil": user_db.perfil
                }
                novo_token = renovar_token(payload_renov)
                cookie_controller.set(
                    "consultorio_session",
                    novo_token,
                    secure=(os.getenv("AMBIENTE", "desenvolvimento").lower() == "producao"),
                    same_site="lax",
                    max_age=timeout_min * 60
                )
                st.session_state.token_criado_em = time.time()

        st.sidebar.write(f"Logado: {st.session_state.user}")
        st.sidebar.caption(f"Perfil: {st.session_state.perfil}")
        if st.sidebar.button("Sair"):
            registrar(db(), st.session_state.get("username", "?"),
                      "LOGOUT", "logout manual")
            cookie_controller.remove("consultorio_session")
            st.session_state.clear()
            st.rerun()

        # Permissoes por perfil:
        perfil = st.session_state.perfil
        TODAS = {"Minha conta": tela_minha_conta,
                 "Cadastro": tela_cadastro, "Agenda": tela_agenda,
                 "Calendário": tela_calendario,
                 "Pagamentos": tela_pagamentos, "Financeiro": tela_financeiro,
                 "Usuários": tela_usuarios,
                 "Auditoria": tela_auditoria,
                 "Saúde do Sistema": tela_saude}
        permitidas = obter_telas_permitidas(perfil)

        aba = st.sidebar.radio("Menu", permitidas)
        
        # Busca Global (mínimo 3 caracteres para evitar queries lentas)
        st.sidebar.markdown("---")
        busca_global = st.sidebar.text_input(
            "🔍 Busca Global",
            placeholder="Mín. 3 caracteres…",
            key="sys_busca_global",
            help="Busca pacientes (nome, e-mail, telefone), despesas e sessões."
        )

        # Notificações no Sidebar
        from app.services.notificacoes import obter_notificacoes
        notifs = obter_notificacoes(db())
        if notifs:
            with st.sidebar.expander(f"🔔 Notificações ({len(notifs)})", expanded=False):
                for n in notifs:
                    st.markdown(f"{n['icone']} **{n['titulo']}**  \n*{n['detalhe']}*")
                    st.markdown("---")
        else:
            st.sidebar.caption("✅ Nenhuma notificação pendente.")
        
        st.sidebar.divider()
        st.sidebar.caption(f"Versão: v{__version__}")
        
        # Exibe busca se o usuário digitou algo (a tela interna valida mínimo de chars)
        if busca_global.strip():
            from app.screens.busca_global import tela_busca_global
            tela_busca_global(busca_global.strip())
        else:
            TODAS[aba]()
finally:
    # Garante liberação de conexões do banco a cada render do Streamlit
    if "db" in st.session_state:
        try:
            st.session_state.db.close()
        except Exception:
            pass
        del st.session_state.db
