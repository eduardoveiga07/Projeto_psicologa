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


if "user" not in st.session_state:
    tela_login()
else:
    # Timeout de sessao: 15 min de inatividade (ambiente clinico).
    agora = datetime.now()
    ultima = st.session_state.get("last_active", agora)
    if (agora - ultima).total_seconds() > 15 * 60:
        registrar(db(), st.session_state.get("username", "?"),
                  "SESSAO_EXPIRADA", "timeout 15min inatividade")
        st.session_state.clear()
        st.warning("Sessão expirada por inatividade. Faça login novamente.")
        st.stop()
    st.session_state.last_active = agora

    st.sidebar.write(f"Logado: {st.session_state.user}")
    st.sidebar.caption(f"Perfil: {st.session_state.perfil}")
    if st.sidebar.button("Sair"):
        registrar(db(), st.session_state.get("username", "?"),
                  "LOGOUT", "logout manual")
        st.session_state.clear()
        st.rerun()

    # Permissoes por perfil:
    perfil = st.session_state.perfil
    TODAS = {"Minha conta": tela_minha_conta,
             "Cadastro": tela_cadastro, "Agenda": tela_agenda,
             "Calendário": tela_calendario,
             "Pagamentos": tela_pagamentos, "Financeiro": tela_financeiro,
             "Usuários": tela_usuarios,
             "Auditoria": tela_auditoria}
    permitidas = obter_telas_permitidas(perfil)

    aba = st.sidebar.radio("Menu", permitidas)
    
    st.sidebar.divider()
    st.sidebar.caption(f"Versão: v{__version__}")
    
    TODAS[aba]()
