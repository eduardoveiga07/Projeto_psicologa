"""App Streamlit - Gestao Consultorio Psicologia. Roda: streamlit run app/main.py"""
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
from app.screens.shared import db

from app.auth.usuario_validacao import (
    normalizar_username,
    validar_email_opcional,
    validar_nome,
    validar_username,
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

# LGPD: auto-exclui pacientes inativos ha mais de 2 anos.
@st.cache_resource
def _limpar_inativos_antigos():
    from datetime import timedelta
    s = get_session()
    try:
        limite = datetime.now().date() - timedelta(days=730)
        antigos = s.query(Paciente).filter(
            Paciente.status == StatusPaciente.INATIVO,
            Paciente.data_desativacao != None,  # noqa: E711
            Paciente.data_desativacao < limite).all()
        for p in antigos:
            s.delete(p)
        s.commit()
    except Exception:
        s.rollback()
    finally:
        s.close()
    return True
_limpar_inativos_antigos()


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
             "Usuários": tela_usuarios}
    if perfil == Perfil.DONA.value:
        permitidas = ["Minha conta", "Cadastro", "Agenda", "Calendário",
                      "Pagamentos", "Financeiro", "Usuários"]
    elif perfil == Perfil.SECRETARIA.value:
        permitidas = ["Minha conta", "Cadastro", "Agenda", "Calendário",
                      "Pagamentos"]
    elif perfil == Perfil.FINANCEIRO.value:
        permitidas = ["Minha conta", "Pagamentos", "Financeiro"]
    else:  # PROGRAMADOR
        permitidas = list(TODAS.keys())

    aba = st.sidebar.radio("Menu", permitidas)
    TODAS[aba]()
