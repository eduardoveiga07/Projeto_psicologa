import streamlit as st
from datetime import datetime, date, time
from decimal import Decimal
from app.db.session import get_session
from app.db.models import (
    Paciente, AgendaSessao, Despesa, TipoContrato, Frequencia, DiaSemana,
    StatusPaciente, StatusPresenca, StatusPagamento, Usuario, Perfil,
    Indisponibilidade, MotivoIndisp
)
from app.services.auditoria import registrar

# Faixas de atendimento: 1h de duracao, inicios a cada 30min (07:00 -> 20:00 inicio)
FAIXAS_HORARIO = [
    f"{h:02d}:{m:02d} - {(h + 1):02d}:{m:02d}"
    for h in range(7, 21) for m in (0, 30)
]

# Horarios "soltos" para uso em duracao variavel (indisponibilidades)
HORARIOS_INICIO = [f"{h:02d}:{m:02d}" for h in range(7, 23) for m in (0, 30)]
HORARIOS_FIM = [f"{h:02d}:{m:02d}" for h in range(7, 24) for m in (0, 30)
                if not (h == 7 and m == 0)]


def db():
    if "db" not in st.session_state:
        st.session_state.db = get_session()
    return st.session_state.db


def mapa_cached(ano, mes):
    """Cache curto (2s) do mapa_ocupacao_mes para evitar recálculos no mesmo render."""
    from app.services.ocupacao import mapa_ocupacao_mes
    import time as _t
    k = f"_mapa_{ano}_{mes}"
    kt = f"_mapa_t_{ano}_{mes}"
    agora = _t.time()
    if k in st.session_state and (agora - st.session_state.get(kt, 0)) < 2:
        return st.session_state[k]
    st.session_state[k] = mapa_ocupacao_mes(db(), ano, mes)
    st.session_state[kt] = agora
    return st.session_state[k]


def invalidar_cache():
    for k in list(st.session_state.keys()):
        if k.startswith("_mapa_"):
            del st.session_state[k]


def flash(msg, tipo="success"):
    """Guarda mensagem para o próximo render."""
    st.session_state["_flash"] = {"msg": msg, "tipo": tipo}


def mostrar_flash():
    """Mostra flash uma vez e remove."""
    f = st.session_state.pop("_flash", None)
    if not f:
        return
    fn = {"success": st.success, "info": st.info,
          "warning": st.warning, "error": st.error}.get(f["tipo"], st.success)
    fn(f["msg"])
