"""App Streamlit - Gestao Consultorio Psicologia. Roda: streamlit run app/main.py"""
import locale
try:
    locale.setlocale(locale.LC_ALL, "pt_BR.UTF-8")
except locale.Error:
    pass
import streamlit as st
from sqlalchemy import extract
from datetime import datetime, date, time
from decimal import Decimal
from app.db.session import get_session, criar_tabelas
from app.db.models import (Paciente, AgendaSessao, Despesa, TipoContrato,
    Frequencia, DiaSemana, StatusPaciente, StatusPresenca, StatusPagamento,
    Usuario, Perfil)
from app.auth.login import autenticar, criar_usuario, gerar_hash
from app.services.email_srv import gerar_reset, aplicar_reset
from app.services.feriados import feriados_brasil
from app.services.indisponibilidade import (datas_dia_todo, horarios_bloqueados)
from app.db.models import Indisponibilidade, MotivoIndisp
from app.services.financeiro import consolidado_mes, consolidado_periodo
from app.services.pdf_export import gerar_pdf
from app.services.auditoria import registrar

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


# ---------- LOGIN ----------
def tela_login():
    st.title("Gestão Consultório - Login")
    with st.form("login"):
        u = st.text_input("Usuário")
        p = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            user = autenticar(db(), u, p)
            if user:
                st.session_state.user = user.nome
                st.session_state.username = user.username
                st.session_state.perfil = user.perfil.value
                st.session_state.last_active = datetime.now()
                registrar(db(), user.username, "LOGIN",
                          "login bem-sucedido")
                st.rerun()
            else:
                registrar(db(), u or "?", "LOGIN_FALHOU",
                          "tentativa de login invalida")
                st.error("Credenciais inválidas.")
    with st.expander("Esqueci minha senha"):
        with st.form("reset_pedido"):
            em = st.text_input("Seu email cadastrado")
            if st.form_submit_button("Enviar código"):
                ok, msg = gerar_reset(db(), em)
                st.info(msg)
    with st.expander("Tenho um código de redefinição"):
        with st.form("reset_aplicar"):
            tk = st.text_input("Código recebido")
            ns = st.text_input("Nova senha", type="password")
            if st.form_submit_button("Trocar senha"):
                ok, msg = aplicar_reset(db(), tk, ns)
                (st.success if ok else st.error)(msg)


# ---------- CADASTRO ----------
def tela_cadastro():
    mostrar_flash()
    st.header("Cadastro de Pacientes")

    tipo = st.radio("Tipo de paciente", ["Recorrente (ativo)",
        "Avaliação Inicial (sessão única)"], horizontal=True)
    em_aval = tipo.startswith("Avaliação")

    if em_aval:
        # Data e duração FORA do form para filtrar horários livres
        st.markdown("**Data e horário da avaliação:**")
        cd1, cd2 = st.columns(2)
        data_av = cd1.date_input("Data da avaliação",
            value=datetime.now().date(), format="DD/MM/YYYY", key="av_data")
        dur_av = cd2.selectbox("Duração", ["30 minutos", "1 hora"],
            key="av_dur")
        # Calcula horários LIVRES nesse dia
        from app.services.ocupacao import mapa_ocupacao_mes, faixas_sobrepoem
        FAIXAS_30 = [f"{h:02d}:{m:02d} - {h+ (0 if m==30 else 0):02d}:{m+30 if m==0 else 0:02d}"
                     for h in range(7,21) for m in (0,30)]
        # Faixas 30min ou 60min
        if dur_av == "30 minutos":
            faixas_pos = []
            for h in range(7, 22):
                for m in (0, 30):
                    if h == 21 and m == 30: break
                    fim_h = h if m == 0 else h + 1
                    fim_m = 30 if m == 0 else 0
                    faixas_pos.append(f"{h:02d}:{m:02d} - {fim_h:02d}:{fim_m:02d}")
        else:
            faixas_pos = FAIXAS_HORARIO  # 1h
        # Bloqueios e feriados
        fer = feriados_brasil(data_av.year).get(data_av)
        ind = db().query(Indisponibilidade).filter(
            Indisponibilidade.data == data_av).all()
        bloq_dia_todo = any(r.dia_todo for r in ind)
        bloq_horarios = [r.horario for r in ind if not r.dia_todo and r.horario]
        if fer:
            st.error(f"🔴 {data_av.strftime('%d/%m/%Y')} é feriado ({fer[1]}): {fer[0]}.")
        if bloq_dia_todo:
            st.error(f"🟠 Psicóloga indisponível o dia todo.")
            faixas_livres = []
        else:
            # ocupação por recorrências
            mapa = mapa_cached(data_av.year, data_av.month)
            ocupados_no_dia = list(mapa.get(data_av, {}).keys()) + bloq_horarios
            faixas_livres = [f for f in faixas_pos
                             if not any(faixas_sobrepoem(f, o)
                                        for o in ocupados_no_dia)]
        if not faixas_livres:
            st.warning("Nenhum horário livre nessa data. Escolha outra.")
            hr_av = None
        else:
            hr_av = cd1.selectbox(f"Horário livre ({len(faixas_livres)} opções)",
                faixas_livres, key="av_hr")

        _kfa = st.session_state.get("form_seed_av", 0)
        # "Sera cobrada" FORA do form para reagir
        paga = st.checkbox("Avaliação será cobrada", value=True, key="av_paga")
        with st.form(f"nova_aval_{_kfa}"):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome")
            tel = c2.text_input("Telefone (DDI+DDD)")
            email_p = c1.text_input("Email (opcional, para NF)")
            nasc = c2.date_input("Data de nascimento",
                min_value=date(1930, 1, 1), format="DD/MM/YYYY")
            valor_av = 0.0
            if paga:
                valor_av = c1.number_input("Valor da avaliação",
                    min_value=0.0, step=10.0)
            if st.form_submit_button("Cadastrar avaliação"):
                faltando = []
                if not nome: faltando.append("nome")
                if not tel: faltando.append("telefone")
                if not email_p: faltando.append("email")
                if not nasc: faltando.append("data de nascimento")
                if not hr_av: faltando.append("horário disponível")
                if faltando and not st.session_state.get("conf_aval"):
                    st.session_state.conf_aval = True
                    st.warning(f"⚠️ Faltam: {', '.join(faltando)}. "
                               "Tem certeza? Clique em **Cadastrar avaliação** "
                               "novamente para confirmar.")
                else:
                    try:
                        novo_pac = Paciente(
                            nome=nome, telefone=tel, email=email_p,
                            data_nascimento=nasc,
                            tipo_contrato=TipoContrato.AVULSO,
                            valor_sessao=Decimal(str(valor_av)),
                            frequencia=Frequencia.PERSONALIZADO,
                            horario_atendimento="",
                            em_avaliacao=True, avaliacao_paga=paga,
                            valor_avaliacao=Decimal(str(valor_av)),
                            status=StatusPaciente.ATIVO)
                        db().add(novo_pac)
                        db().flush()
                        if hr_av:
                            hi, fim = hr_av.split(" - ")
                            h, m = map(int, hi.split(":"))
                            hf, mf = map(int, fim.split(":"))
                            ini = datetime.combine(data_av, time(h, m))
                            fim_dt = datetime.combine(data_av, time(hf, mf))
                            # Limpa qualquer sessão preexistente no slot:
                            # - CANCELADA antiga (exceções/exclusões do calendário)
                            # - Órfã de paciente excluído
                            existentes = db().query(AgendaSessao).filter(
                                AgendaSessao.data_hora_inicio == ini).all()
                            for ja in existentes:
                                if ja.status_presenca == StatusPresenca.CANCELADA:
                                    db().delete(ja)
                                else:
                                    # Verifica se paciente ainda existe
                                    p_ext = db().query(Paciente).filter(
                                        Paciente.id_paciente == ja.id_paciente).first()
                                    if not p_ext:
                                        db().delete(ja)
                            db().flush()
                            db().add(AgendaSessao(
                                id_paciente=novo_pac.id_paciente,
                                data_hora_inicio=ini, data_hora_fim=fim_dt,
                                status_presenca=StatusPresenca.AGENDADA))
                        db().commit()
                        st.session_state.pop("conf_aval", None)
                        st.success(f"{nome} cadastrado(a). Sessão em "
                                   f"{data_av.strftime('%d/%m/%Y')} {hr_av}.")
                        st.session_state["form_seed_av"] = _kfa + 1
                        st.rerun()
                    except Exception as e:
                        db().rollback()
                        msg = str(e)
                        if "data_hora_inicio" in msg or "unique" in msg.lower():
                            st.error(f"⚠️ Já existe uma sessão em "
                                f"{data_av.strftime('%d/%m/%Y')} {hr_av}. "
                                "Escolha outro horário.")
                        else:
                            st.error(f"Erro: {type(e).__name__}")
    else:
        freq = st.selectbox("Frequência", [e.value for e in Frequencia])
        dias_opcoes = [e.value for e in DiaSemana]
        sessoes_custom = None
        semana_mes = None
        paridade_q = None
        if freq == Frequencia.DUAS_SEMANA.value:
            st.caption("Selecione 2 dias da semana.")
            dias_sel = st.multiselect("Dias", dias_opcoes, max_selections=2)
        elif freq == Frequencia.TRES_SEMANA.value:
            st.caption("Selecione 3 dias da semana.")
            dias_sel = st.multiselect("Dias", dias_opcoes, max_selections=3)
        elif freq == Frequencia.PERSONALIZADO.value:
            dias_sel = st.multiselect("Dias", dias_opcoes)
            sessoes_custom = st.number_input("Sessões/mês",
                min_value=1, max_value=31, value=4)
        elif freq == Frequencia.MENSAL.value:
            dias_sel = [st.selectbox("Dia de atendimento", dias_opcoes)]
            semana_mes = st.selectbox("Qual semana do mês?",
                [1, 2, 3, 4, 5],
                format_func=lambda n: {1: "1ª", 2: "2ª", 3: "3ª",
                                       4: "4ª", 5: "Última"}[n])
        elif freq == Frequencia.QUINZENAL.value:
            dias_sel = [st.selectbox("Dia de atendimento", dias_opcoes)]
            paridade_q = st.selectbox("Quinzenal — semanas",
                ["impar", "par"],
                format_func=lambda v: "Ímpares (1ª, 3ª, 5ª)" if v == "impar"
                                       else "Pares (2ª, 4ª)")
        else:
            dias_sel = [st.selectbox("Dia de atendimento", dias_opcoes)]

        _kf = st.session_state.get("form_seed", 0)
        with st.form(f"novo_paciente_{_kf}"):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome")
            tel = c2.text_input("Telefone (DDI+DDD)")
            email_p = c1.text_input("Email (opcional, para NF)")
            nasc = c2.date_input("Data de nascimento",
                min_value=date(1930, 1, 1), format="DD/MM/YYYY")
            valor = c1.number_input("Valor por sessão",
                min_value=0.0, step=10.0)
            contrato = c2.selectbox("Contrato",
                [e.value for e in TipoContrato])
            ativo_desde = c1.date_input("Ativo desde (início da recorrência)",
                value=datetime.now().date(), format="DD/MM/YYYY")
            horarios = {}
            if dias_sel:
                st.markdown("**Horário de cada dia:**")
                for d in dias_sel:
                    horarios[d] = st.selectbox(f"Horário — {d}",
                        FAIXAS_HORARIO, key=f"h_{d}")
            if st.form_submit_button("Cadastrar"):
                if not dias_sel:
                    st.error("Selecione ao menos um dia.")
                else:
                    # Checa campos vazios ANTES de salvar.
                    faltando = []
                    if not nome: faltando.append("nome")
                    if not tel: faltando.append("telefone")
                    if not email_p: faltando.append("email")
                    if not valor or valor == 0: faltando.append("valor por sessão")
                    if not nasc: faltando.append("data de nascimento")
                    if faltando and not st.session_state.get("conf_rec"):
                        st.session_state.conf_rec = True
                        st.warning(f"⚠️ Faltam: {', '.join(faltando)}. "
                                   "Tem certeza? Clique em **Cadastrar** "
                                   "novamente para confirmar.")
                    else:
                        # Checa conflitos ANTES de salvar (sem persistir)
                        novo_temp = Paciente(
                            nome=nome, telefone=tel or "", email=email_p,
                            data_nascimento=nasc,
                            tipo_contrato=TipoContrato(contrato),
                            valor_sessao=Decimal(str(valor)),
                            frequencia=Frequencia(freq),
                            dia_atendimento=DiaSemana(dias_sel[0]),
                            dias_semana=",".join(dias_sel),
                            horario_atendimento=",".join(f"{d}={h}"
                                for d, h in horarios.items()),
                            sessoes_mes_custom=int(sessoes_custom) if sessoes_custom else None,
                            semana_do_mes=semana_mes,
                            paridade_quinzenal=paridade_q,
                            ativo_desde=ativo_desde,
                            em_avaliacao=False,
                            status=StatusPaciente.ATIVO)
                        from app.services.ocupacao import detectar_conflitos
                        hj = datetime.now().date()
                        r_test = detectar_conflitos(db(), novo_temp,
                            hj.year, hj.month)
                        if r_test["conflitos"] and not st.session_state.get("conf_conflito"):
                            st.session_state.conf_conflito = True
                            st.error(f"⚠️ {len(r_test['conflitos'])} conflito(s) "
                                     "detectado(s):")
                            for dt, hr, nomes in r_test["conflitos"][:5]:
                                st.write(f"- {dt.strftime('%d/%m/%Y')} {hr} "
                                         f"— {', '.join(nomes)}")
                            st.warning("Cadastrar mesmo assim? Clique em "
                                       "**Cadastrar** novamente para confirmar.")
                        else:
                            db().add(novo_temp)
                            db().commit()
                            st.session_state.pop("conf_rec", None)
                            st.session_state.pop("conf_conflito", None)
                            novo_p = db().query(Paciente).filter(
                                Paciente.nome == nome).order_by(
                                Paciente.criado_em.desc()).first()
                            # Abre 1o periodo do historico de contrato
                            from app.services.contrato import abrir_periodo
                            abrir_periodo(db(), novo_p,
                                novo_p.ativo_desde or datetime.now().date())
                            hj = datetime.now().date()
                            r = detectar_conflitos(db(), novo_p, hj.year, hj.month,
                                                   id_excluir=novo_p.id_paciente)
                            from app.services.ocupacao import sugerir_horarios
                            sugs = sugerir_horarios(db(), novo_p, hj.year,
                                hj.month, FAIXAS_HORARIO,
                                id_excluir=novo_p.id_paciente)
                            st.session_state["ultimo_cad"] = {
                                "nome": nome, "conflitos": r["conflitos"],
                                "livres": len(r["datas_livres"]),
                                "freq": novo_p.frequencia.value,
                                "paridade": novo_p.paridade_quinzenal,
                                "dia": (novo_p.dias_semana or "").split(",")[0],
                                "sug_mesmo_dia": sugs["mesmo_dia"],
                                "sug_outros_dias": sugs["outros_dias"]}
                            st.session_state["form_seed"] = _kf + 1
                            st.rerun()

    # Mostra resultado do ultimo cadastro (apos rerun)
    if st.session_state.get("ultimo_cad"):
        uc = st.session_state["ultimo_cad"]
        st.success(f"✅ {uc['nome']} cadastrado.")
        if uc["conflitos"]:
            st.warning(f"⚠️ {len(uc['conflitos'])} conflito(s) no mês atual:")
            for dt, hr, nomes in uc["conflitos"]:
                st.write(f"- **{dt.strftime('%d/%m/%Y')}** {hr} — "
                         f"já ocupado por: {', '.join(nomes)}")
            st.info(f"✅ {uc['livres']} data(s) sem conflito.")
            st.markdown("**💡 Sugestões priorizadas:**")
            if uc["freq"] == "Quinzenal":
                outra = "par" if uc["paridade"] == "impar" else "impar"
                st.write(f"- ⚡ Trocar paridade quinzenal para **{outra}** "
                         f"(alterna sem conflito)")
            if uc.get("sug_mesmo_dia"):
                st.write(f"- 🕐 Horários livres em **{uc['dia']}**: "
                         f"{', '.join(uc['sug_mesmo_dia'])}")
            if uc.get("sug_outros_dias"):
                st.write(f"- 📅 Mesmo horário disponível em outros dias: "
                         f"{', '.join(uc['sug_outros_dias'])}")
            st.caption("Use **Editar** abaixo para aplicar uma das sugestões.")
        else:
            flash(f"✅ Todas as {uc['livres']} datas do mês estão livres.", "info")
        if st.button("Fechar aviso", key="fechar_uc"):
            del st.session_state["ultimo_cad"]
            st.rerun()

    # Listagens OCULTAS atras de expanders.
    with st.expander("📋 Ver pacientes em Avaliação Inicial"):
        avals = db().query(Paciente).filter(
            Paciente.em_avaliacao == True,  # noqa: E712
            Paciente.status == StatusPaciente.ATIVO).all()
        if not avals:
            st.info("Nenhum paciente em avaliação.")
        for p in avals:
            # Busca sessão agendada para mostrar data/horário
            sess_av = db().query(AgendaSessao).filter(
                AgendaSessao.id_paciente == p.id_paciente).order_by(
                AgendaSessao.data_hora_inicio.desc()).first()
            quando = ""
            if sess_av:
                dur_min = int((sess_av.data_hora_fim - sess_av.data_hora_inicio).total_seconds() // 60)
                quando = (f" — 📅 {sess_av.data_hora_inicio.strftime('%d/%m/%Y %H:%M')}"
                          f" ({dur_min}min)")
            c1, c2, c3, c4, c5 = st.columns([4, 2, 1, 1, 1])
            c1.markdown(f"**{p.nome}** — 📱 {p.telefone}{quando}  \n"
                        f"📧 `{p.email or '—'}` | 🎂 "
                        f"{p.data_nascimento.strftime('%d/%m/%Y') if p.data_nascimento else '—'}")
            c2.write(f"R$ {float(p.valor_avaliacao or 0):.2f} "
                     f"({'cobrada' if p.avaliacao_paga else 'gratuita'})")
            if c3.button("Editar", key=f"edav_{p.id_paciente}"):
                st.session_state[f"edit_av_{p.id_paciente}"] = True
            if c4.button("Recorrente", key=f"rec_{p.id_paciente}"):
                st.session_state[f"converter_{p.id_paciente}"] = True
            if c5.button("Excluir", key=f"delav_{p.id_paciente}"):
                db().query(AgendaSessao).filter(
                    AgendaSessao.id_paciente == p.id_paciente).delete()
                db().delete(p); db().commit(); st.rerun()
            # Form de edição
            if st.session_state.get(f"edit_av_{p.id_paciente}"):
                with st.form(f"feav_{p.id_paciente}"):
                    cc1, cc2 = st.columns(2)
                    n_nome = cc1.text_input("Nome", value=p.nome)
                    n_tel = cc2.text_input("Telefone", value=p.telefone)
                    n_email = cc1.text_input("Email", value=p.email or "")
                    n_nasc = cc2.date_input("Nascimento",
                        value=p.data_nascimento,
                        min_value=date(1930,1,1), format="DD/MM/YYYY")
                    n_paga = cc1.checkbox("Cobrada", value=p.avaliacao_paga)
                    n_val = cc2.number_input("Valor",
                        min_value=0.0, value=float(p.valor_avaliacao or 0))
                    bb1, bb2 = st.columns(2)
                    if bb1.form_submit_button("Salvar"):
                        p.nome = n_nome; p.telefone = n_tel; p.email = n_email
                        p.data_nascimento = n_nasc
                        p.avaliacao_paga = n_paga
                        p.valor_avaliacao = Decimal(str(n_val))
                        p.valor_sessao = Decimal(str(n_val))
                        db().commit()
                        del st.session_state[f"edit_av_{p.id_paciente}"]
                        st.rerun()
                    if bb2.form_submit_button("Cancelar"):
                        del st.session_state[f"edit_av_{p.id_paciente}"]
                        st.rerun()
            if st.session_state.get(f"converter_{p.id_paciente}"):
                with st.form(f"conv_{p.id_paciente}"):
                    st.write("**Configurar como recorrente:**")
                    fq = st.selectbox("Frequência",
                        [e.value for e in Frequencia], key=f"fq_{p.id_paciente}")
                    dia = st.selectbox("Dia",
                        [e.value for e in DiaSemana], key=f"di_{p.id_paciente}")
                    hr = st.selectbox("Horário", FAIXAS_HORARIO,
                        key=f"hr_{p.id_paciente}")
                    vl = st.number_input("Valor por sessão",
                        min_value=0.0, value=float(p.valor_sessao or 0),
                        step=10.0, key=f"vl_{p.id_paciente}")
                    ad = st.date_input("Ativo desde",
                        value=datetime.now().date(),
                        format="DD/MM/YYYY", key=f"ad_{p.id_paciente}")
                    if st.form_submit_button("Converter"):
                        p.em_avaliacao = False
                        p.frequencia = Frequencia(fq)
                        p.dia_atendimento = DiaSemana(dia)
                        p.dias_semana = dia
                        p.horario_atendimento = f"{dia}={hr}"
                        p.valor_sessao = Decimal(str(vl))
                        p.ativo_desde = ad
                        db().commit()
                        from app.services.contrato import abrir_periodo
                        abrir_periodo(db(), p, ad)
                        del st.session_state[f"converter_{p.id_paciente}"]
                        flash(f"{p.nome} agora é recorrente.", "success")
                        st.rerun()

    with st.expander("💤 Pacientes inativos (sem retorno)"):
        inativos = db().query(Paciente).filter(
            Paciente.status == StatusPaciente.INATIVO).all()
        if not inativos:
            st.info("Nenhum paciente inativo.")
        st.caption("Pacientes inativos por mais de 2 anos são excluídos "
                   "automaticamente do banco (LGPD - retenção mínima).")
        for p in inativos:
            c1, c2, c3 = st.columns([5, 1, 1])
            dd = p.data_desativacao.strftime("%d/%m/%Y") if p.data_desativacao else "?"
            c1.write(f"**{p.nome}** — {p.telefone} — inativo desde {dd}")
            if c2.button("Reativar", key=f"rea_{p.id_paciente}"):
                p.status = StatusPaciente.ATIVO
                p.data_desativacao = None
                db().commit()
                registrar(db(), st.session_state.username,
                          "PACIENTE_REATIVADO", "")
                st.rerun()
            if c3.button("Excluir", key=f"del_{p.id_paciente}"):
                db().query(AgendaSessao).filter(AgendaSessao.id_paciente == p.id_paciente).delete(); db().delete(p); db().commit()
                registrar(db(), st.session_state.username,
                          "PACIENTE_EXCLUIDO", "manual")
                st.rerun()

    with st.expander("👥 Ver pacientes ativos recorrentes"):
        ativos = db().query(Paciente).filter(
            Paciente.status == StatusPaciente.ATIVO,
            Paciente.em_avaliacao == False).all()  # noqa: E712
        if not ativos:
            st.info("Nenhum paciente recorrente.")
        for p in ativos:
            c1, c2, c3, c4 = st.columns([5, 1, 1, 1])
            ad = p.ativo_desde.strftime("%d/%m/%Y") if p.ativo_desde else "?"
            nasc = p.data_nascimento.strftime("%d/%m/%Y") if p.data_nascimento else "?"
            # Descricao da recorrencia, formato amigavel
            if p.frequencia == Frequencia.MENSAL and p.semana_do_mes:
                pos = ['1ª','2ª','3ª','4ª','Última'][min(p.semana_do_mes-1,4)]
                rec = f"Mensal — {pos} {p.dias_semana or ''} do mês"
            elif p.frequencia == Frequencia.QUINZENAL and p.paridade_quinzenal:
                par = "ímpares" if p.paridade_quinzenal == "impar" else "pares"
                rec = f"Quinzenal ({p.dias_semana or ''}, semanas {par})"
            else:
                rec = f"{p.frequencia.value} — {p.dias_semana or ''}"
            # Extrai horario do formato "Dia=HH:MM - HH:MM"
            hr_str = p.horario_atendimento or ""
            if "=" in hr_str:
                hr_str = hr_str.split("=", 1)[1].strip()
            valor_br = f"R$ {float(p.valor_sessao):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            # Resumo das excecoes para a linha do paciente
            from app.db.models import ExcecaoHorario
            excs_p = db().query(ExcecaoHorario).filter(
                ExcecaoHorario.id_paciente == p.id_paciente).all()
            exc_resumo = ""
            if excs_p:
                partes = []
                for e in excs_p:
                    if e.tipo == "recorrente":
                        rs = {1:"1ª",2:"2ª",3:"3ª",4:"4ª",5:"Última"}.get(
                            e.semana_do_mes, "?")
                        partes.append(f"{rs} sem.→{e.dia_alvo} {e.horario_alvo}")
                    else:
                        partes.append(f"{e.data_especifica.strftime('%d/%m')}→"
                                      f"{e.dia_alvo} {e.horario_alvo}")
                exc_resumo = f"  \n📅 **Exceções:** {' | '.join(partes)}"
            c1.markdown(f"**{p.nome}** &nbsp;|&nbsp; 📱 {p.telefone} &nbsp;|&nbsp; "
                f"Email: `{p.email or '—'}` &nbsp;|&nbsp; 🎂 {nasc}  \n"
                f"{rec} — {hr_str} — {valor_br}/sessão — ativo desde {ad}"
                + exc_resumo)
            if p.email and c2.button("✉️", key=f"cp_{p.id_paciente}",
                                     help="Copiar email"):
                st.session_state[f"showmail_{p.id_paciente}"] = True
            if st.session_state.get(f"showmail_{p.id_paciente}"):
                st.code(p.email, language=None)
                st.caption("Copie acima e cole no seu cliente de email.")
            if c3.button("Editar", key=f"ed_{p.id_paciente}"):
                st.session_state[f"editar_{p.id_paciente}"] = True
            if c4.button("Desativar", key=f"des_{p.id_paciente}"):
                p.status = StatusPaciente.INATIVO
                p.data_desativacao = datetime.now().date()
                db().commit()
                registrar(db(), st.session_state.username,
                          "PACIENTE_DESATIVADO", "")
                st.rerun()
            if st.session_state.get(f"editar_{p.id_paciente}"):
                # Frequencia FORA do form para reagir imediatamente
                nv_freq = st.selectbox("Frequência",
                    [e.value for e in Frequencia],
                    index=[e.value for e in Frequencia].index(p.frequencia.value),
                    key=f"nfq_{p.id_paciente}")
                nv_semana = None
                nv_paridade = None
                if nv_freq == Frequencia.MENSAL.value:
                    nv_semana = st.selectbox("Semana do mês",
                        [1, 2, 3, 4, 5],
                        index=(p.semana_do_mes or 1) - 1
                            if (p.semana_do_mes or 1) <= 5 else 0,
                        format_func=lambda n: {1: "1ª", 2: "2ª", 3: "3ª",
                                               4: "4ª", 5: "Última"}[n],
                        key=f"nsem_{p.id_paciente}")
                elif nv_freq == Frequencia.QUINZENAL.value:
                    nv_paridade = st.selectbox("Quinzenal",
                        ["impar", "par"],
                        index=0 if (p.paridade_quinzenal or "impar") == "impar" else 1,
                        format_func=lambda v: "Ímpares" if v == "impar" else "Pares",
                        key=f"npar_{p.id_paciente}")
                with st.form(f"edf_{p.id_paciente}"):
                    cc1, cc2 = st.columns(2)
                    nv_nome = cc1.text_input("Nome", value=p.nome,
                        key=f"nn_{p.id_paciente}")
                    nv_tel = cc2.text_input("Telefone", value=p.telefone,
                        key=f"nt_{p.id_paciente}")
                    nv_email = cc1.text_input("Email", value=p.email or "",
                        key=f"ne_{p.id_paciente}")
                    nv_nasc = cc2.date_input("Nascimento",
                        value=p.data_nascimento, min_value=date(1930, 1, 1),
                        format="DD/MM/YYYY", key=f"nb_{p.id_paciente}")
                    nv_dia = cc1.selectbox("Dia",
                        [e.value for e in DiaSemana],
                        index=[e.value for e in DiaSemana].index(
                            (p.dias_semana or "Segunda-feira").split(",")[0]),
                        key=f"ndi_{p.id_paciente}")
                    nv_hr = cc1.selectbox("Horário", FAIXAS_HORARIO,
                        key=f"nhr_{p.id_paciente}")
                    nv_vl = cc2.number_input("Valor por sessão",
                        min_value=0.0, value=float(p.valor_sessao),
                        step=10.0, key=f"nvl_{p.id_paciente}")
                    nv_ad = cc1.date_input("Ativo desde",
                        value=p.ativo_desde or datetime.now().date(),
                        format="DD/MM/YYYY", key=f"nad_{p.id_paciente}")
                    cb1, cb2 = st.columns(2)
                    if cb1.form_submit_button("Salvar alterações"):
                        # Captura estado antigo para detectar mudanca de contrato
                        antigo = dict(
                            frequencia=p.frequencia,
                            valor_sessao=p.valor_sessao,
                            dias_semana=p.dias_semana,
                            semana_do_mes=p.semana_do_mes,
                            paridade_quinzenal=p.paridade_quinzenal,
                        )
                        p.nome = nv_nome
                        p.telefone = nv_tel
                        p.email = nv_email
                        p.data_nascimento = nv_nasc
                        p.dia_atendimento = DiaSemana(nv_dia)
                        p.frequencia = Frequencia(nv_freq)
                        p.semana_do_mes = nv_semana
                        p.paridade_quinzenal = nv_paridade
                        p.dias_semana = nv_dia
                        p.horario_atendimento = f"{nv_dia}={nv_hr}"
                        p.valor_sessao = Decimal(str(nv_vl))
                        p.ativo_desde = nv_ad
                        db().commit()
                        # Se algum campo de contrato mudou, abre novo periodo
                        mudou = (
                            antigo["frequencia"] != p.frequencia or
                            Decimal(str(antigo["valor_sessao"])) != p.valor_sessao or
                            (antigo["dias_semana"] or "") != (p.dias_semana or "") or
                            antigo["semana_do_mes"] != p.semana_do_mes or
                            antigo["paridade_quinzenal"] != p.paridade_quinzenal
                        )
                        if mudou:
                            from app.services.contrato import abrir_periodo
                            abrir_periodo(db(), p, datetime.now().date())
                        del st.session_state[f"editar_{p.id_paciente}"]
                        registrar(db(), st.session_state.username,
                                  "PACIENTE_EDITADO", "alteracao de cadastro")
                        # Detectar conflitos apos edicao
                        from app.services.ocupacao import detectar_conflitos
                        hj = datetime.now().date()
                        r = detectar_conflitos(db(), p, hj.year, hj.month,
                                               id_excluir=p.id_paciente)
                        st.session_state["ultimo_cad"] = {
                            "nome": p.nome, "conflitos": r["conflitos"],
                            "livres": len(r["datas_livres"]),
                            "freq": p.frequencia.value,
                            "paridade": p.paridade_quinzenal,
                            "dia": (p.dias_semana or "").split(",")[0]}
                        st.rerun()
                    if cb2.form_submit_button("Cancelar"):
                        del st.session_state[f"editar_{p.id_paciente}"]
                        st.rerun()
            # ===== EXCEÇÕES DE HORÁRIO =====
            from app.db.models import ExcecaoHorario
            excs = db().query(ExcecaoHorario).filter(
                ExcecaoHorario.id_paciente == p.id_paciente).all()
            with st.expander(f"📅 Exceções de horário ({len(excs)})"):
                for ex in excs:
                    cx1, cx2 = st.columns([5, 1])
                    if ex.tipo == "recorrente":
                        rot_sem = {1:"1ª",2:"2ª",3:"3ª",4:"4ª",5:"Última"}.get(
                            ex.semana_do_mes, "?")
                        cx1.write(f"🔁 **Recorrente:** na {rot_sem} semana → "
                                  f"{ex.dia_alvo} {ex.horario_alvo}")
                    else:
                        cx1.write(f"📌 **Pontual:** "
                                  f"{ex.data_especifica.strftime('%d/%m/%Y')} → "
                                  f"{ex.dia_alvo} {ex.horario_alvo}")
                    if cx2.button("Remover", key=f"rmex_{ex.id_excecao}"):
                        db().delete(ex); db().commit(); st.rerun()
                # Form para nova exceção
                tipo_e = st.radio("Tipo", ["Recorrente (toda Nª semana)",
                    "Pontual (data específica)"],
                    key=f"tex_{p.id_paciente}", horizontal=True)
                with st.form(f"fex_{p.id_paciente}"):
                    if tipo_e.startswith("Recorrente"):
                        sm = st.selectbox("Em qual semana do mês?",
                            [1,2,3,4,5],
                            format_func=lambda n: {1:"1ª",2:"2ª",3:"3ª",
                                4:"4ª",5:"Última"}[n],
                            key=f"sm_{p.id_paciente}")
                        de = None
                    else:
                        de = st.date_input("Data específica",
                            format="DD/MM/YYYY", key=f"de_{p.id_paciente}")
                        sm = None
                    dia_a = st.selectbox("Atender em qual dia?",
                        [e.value for e in DiaSemana],
                        key=f"da_{p.id_paciente}")
                    hr_a = st.selectbox("Horário", FAIXAS_HORARIO,
                        key=f"ha_{p.id_paciente}")
                    if st.form_submit_button("Adicionar exceção"):
                        db().add(ExcecaoHorario(
                            id_paciente=p.id_paciente,
                            tipo="recorrente" if tipo_e.startswith("Recorrente") else "pontual",
                            semana_do_mes=sm, data_especifica=de,
                            dia_alvo=dia_a, horario_alvo=hr_a))
                        db().commit()
                        flash("Exceção adicionada.", "success")
                        st.rerun()
        dados_pac = [{"Nome": p.nome, "Tel": p.telefone,
            "Email": p.email or "", "Nasc": p.data_nascimento.strftime("%d/%m/%Y") if p.data_nascimento else "",
            "Freq": p.frequencia.value, "Dias": p.dias_semana or "",
            "Horario": p.horario_atendimento,
            "Valor": float(p.valor_sessao),
            "Ativo desde": p.ativo_desde.strftime("%d/%m/%Y") if p.ativo_desde else ""}
            for p in ativos]
        st.download_button("Baixar PDF",
            gerar_pdf("Pacientes Ativos", dados_pac),
            file_name="pacientes_ativos.pdf", mime="application/pdf")


# ---------- AGENDA ----------
def tela_agenda():
    mostrar_flash()
    st.header("Agenda de Sessões")
    st.caption("As sessões aparecem automaticamente conforme o cadastro de "
               "cada paciente (frequência, dia e horário). Para alterar uma "
               "data específica use Editar abaixo; para mudar permanente, "
               "edite o paciente em Cadastro.")
    # ---- Calendário mensal (a tela principal) ----
    st.subheader("Calendário mensal — quem atende em cada data")
    from datetime import timedelta
    from app.services.ocupacao import mapa_ocupacao_mes
    hoje = datetime.now().date()
    proximos = db().query(Indisponibilidade).filter(
        Indisponibilidade.data >= hoje,
        Indisponibilidade.data <= hoje + timedelta(days=60)).order_by(
        Indisponibilidade.data).all()
    if proximos:
        from app.services.indisponibilidade import (agrupar_em_ranges,
                                                     formatar_grupo)
        grupos_px = agrupar_em_ranges(proximos)
        with st.expander(f"⚠️ {len(proximos)} bloqueio(s) próximos (60 dias)"):
            for g in grupos_px:
                st.write(f"- {formatar_grupo(g)}")

    cc1, cc2 = st.columns(2)
    cal_ano = cc1.number_input("Ano", 2024, 2040,
        hoje.year, key="cal_ano")
    cal_mes = cc2.number_input("Mês", 1, 12, hoje.month, key="cal_mes")
    mapa = mapa_cached(int(cal_ano), int(cal_mes))

    # ===== FERIADOS E BLOQUEIOS DO MÊS =====
    fer_mes = feriados_brasil(int(cal_ano))
    fer_lista = [(d, n) for d, (n, t) in fer_mes.items()
                 if d.month == int(cal_mes)]
    bloq_lista = db().query(Indisponibilidade).filter(
        extract("year", Indisponibilidade.data) == int(cal_ano),
        extract("month", Indisponibilidade.data) == int(cal_mes)).order_by(
        Indisponibilidade.data).all()
    if fer_lista or bloq_lista:
        from app.services.indisponibilidade import (agrupar_em_ranges,
                                                     formatar_grupo)
        grupos_bloq = agrupar_em_ranges(bloq_lista)
        n_dias_bloq = sum(len(g["ids"]) for g in grupos_bloq)
        with st.expander(f"🔴 Feriados e bloqueios em "
                f"{int(cal_mes):02d}/{int(cal_ano)} "
                f"({len(fer_lista)} feriados + {n_dias_bloq} dias "
                f"de bloqueio)",
                expanded=True):
            for d, n in sorted(fer_lista):
                st.write(f"🔴 **{d.strftime('%d/%m')}** — {n} (feriado)")
            for g in grupos_bloq:
                st.write(f"🟠 {formatar_grupo(g)}")

    # Sessoes que cairiam mas estao bloqueadas (feriado/indisp) - REMARCAR
    from app.services.ocupacao import sessoes_perdidas_no_mes
    fer_dict = {d: n for d, n in fer_lista}
    indisp_set = set()
    for r in bloq_lista:
        indisp_set.add((r.data, "dia_todo" if r.dia_todo else r.horario))
    perdidas_total = []
    for p_a in db().query(Paciente).filter(
            Paciente.status == StatusPaciente.ATIVO,
            Paciente.em_avaliacao == False).all():  # noqa: E712
        for dt, hr, mot in sessoes_perdidas_no_mes(
                p_a, int(cal_ano), int(cal_mes), db(),
                indisp_set=indisp_set, feriados_set=fer_dict):
            perdidas_total.append((dt, hr, p_a.nome, mot))
    if perdidas_total:
        perdidas_total.sort()
        # Mapa nome->paciente p/ achar id
        pacs_ativos = {p.nome: p for p in db().query(Paciente).filter(
            Paciente.status == StatusPaciente.ATIVO).all()}
        with st.expander(
                f"⚠️ Sessões a remarcar/avisar pacientes "
                f"({len(perdidas_total)})", expanded=True):
            st.caption("Sessões que cairiam pela rotina mas coincidem "
                       "com feriado/bloqueio. Remarque para outra data ou "
                       "apenas avise o paciente.")
            for dt, hr, nome, mot in perdidas_total:
                pk = f"{dt.isoformat()}_{hr}_{nome}"
                ca, cb = st.columns([5, 1])
                ca.warning(f"**{dt.strftime('%d/%m')}** {hr} — "
                           f"**{nome}** — {mot}")
                if cb.button("Remarcar", key=f"rmk_{pk}"):
                    st.session_state[f"rmk_open_{pk}"] = True
                if st.session_state.get(f"rmk_open_{pk}"):
                    with st.form(f"rmk_f_{pk}"):
                        st.caption(f"Remarcar sessão de **{nome}** "
                                   f"que cairia em {dt.strftime('%d/%m/%Y')} "
                                   f"— motivo: _{mot}_")
                        cf1, cf2 = st.columns(2)
                        # Sugere proximo dia util (pula sabado/domingo)
                        from datetime import timedelta as _td
                        sug = dt + _td(days=1)
                        while sug.weekday() >= 5:
                            sug += _td(days=1)
                        nd = cf1.date_input("Nova data", value=sug,
                            min_value=dt + _td(days=1),
                            format="DD/MM/YYYY", key=f"rmk_d_{pk}")
                        idx_h = (FAIXAS_HORARIO.index(hr)
                                 if hr in FAIXAS_HORARIO else 0)
                        nh = cf2.selectbox("Novo horário", FAIXAS_HORARIO,
                            index=idx_h, key=f"rmk_h_{pk}")
                        cs1, cs2 = st.columns(2)
                        if cs1.form_submit_button("Confirmar"):
                            p_obj = pacs_ativos.get(nome)
                            if not p_obj:
                                st.error("Paciente não encontrado.")
                            else:
                                hi, _ = nh.split(" - ")
                                h_, m_ = map(int, hi.split(":"))
                                ini = datetime.combine(nd, time(h_, m_))
                                fim = ini.replace(hour=h_ + 1)
                                db().query(AgendaSessao).filter(
                                    AgendaSessao.data_hora_inicio == ini,
                                    AgendaSessao.status_presenca
                                    == StatusPresenca.CANCELADA).delete()
                                db().add(AgendaSessao(
                                    id_paciente=p_obj.id_paciente,
                                    data_hora_inicio=ini,
                                    data_hora_fim=fim,
                                    status_presenca=StatusPresenca.AGENDADA,
                                    remarcada_de=dt,
                                    remarcada_motivo=mot))
                                try:
                                    db().commit()
                                    invalidar_cache()
                                    registrar(db(), st.session_state.username,
                                              "SESSAO_REMARCADA",
                                              f"{nome} {dt}->{nd} {nh}")
                                    del st.session_state[f"rmk_open_{pk}"]
                                    flash(f"Sessão de {nome} remarcada "
                                          f"de {dt.strftime('%d/%m')} para "
                                          f"{nd.strftime('%d/%m')} {nh}.",
                                          "success")
                                    st.rerun()
                                except Exception:
                                    db().rollback()
                                    st.error("Esse horário já está ocupado.")
                        if cs2.form_submit_button("Cancelar"):
                            del st.session_state[f"rmk_open_{pk}"]
                            st.rerun()

    # Monta linhas agrupadas por dia da semana.
    DIAS_PT_FULL = ["Segunda-feira", "Terça-feira", "Quarta-feira",
                    "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    pacientes_map = {p.nome: p for p in db().query(Paciente).filter(
        Paciente.status == StatusPaciente.ATIVO).all()}
    if not mapa:
        st.info(f"Sem atendimentos recorrentes em {int(cal_mes):02d}/{int(cal_ano)}.")
    linhas_pdf = []
    # Agrupa: {dia_semana_idx: [(data, hr, nomes)]}
    por_dia = {}
    for data_d in sorted(mapa.keys()):
        for hr, nomes in sorted(mapa[data_d].items()):
            por_dia.setdefault(data_d.weekday(), []).append(
                (data_d, hr, nomes))
    for dia_idx in sorted(por_dia.keys()):
        st.markdown(f"### 📅 {DIAS_PT_FULL[dia_idx]}")
        for data_d, hr, nomes in por_dia[dia_idx]:
            conflito = "⚠️ CONFLITO: " if len(nomes) > 1 else ""
            label = (f"{data_d.strftime('%d/%m')} — {hr} — "
                     f"{conflito}{' + '.join(nomes)}")
            linhas_pdf.append({"Data": data_d.strftime('%d/%m'),
                "Horário": hr, "Paciente(s)": conflito + " + ".join(nomes)})
            uk = f"{data_d.isoformat()}_{hr}_{'_'.join(nomes)}"
            cA, cB, cC = st.columns([6, 1, 1])
            cA.write(label)
            if cB.button("Editar", key=f"calE_{uk}"):
                st.session_state[f"calEd_{uk}"] = True
            if cC.button("Excluir", key=f"calX_{uk}"):
                st.session_state[f"calEx_{uk}"] = True
            if st.session_state.get(f"calEx_{uk}"):
                with st.form(f"calFX_{uk}"):
                    alvo_x = st.selectbox("Qual paciente excluir nesta data?",
                        nomes, key=f"calXP_{uk}")
                    if st.form_submit_button("Confirmar exclusão"):
                        p_obj = pacientes_map.get(alvo_x)
                        if p_obj:
                            hi, _ = hr.split(" - ")
                            h, m = map(int, hi.split(":"))
                            ini = datetime.combine(data_d, time(h, m))
                            db().add(AgendaSessao(id_paciente=p_obj.id_paciente,
                                data_hora_inicio=ini,
                                data_hora_fim=ini.replace(hour=h + 1),
                                status_presenca=StatusPresenca.CANCELADA))
                            try: db().commit()
                            except Exception: db().rollback()
                        del st.session_state[f"calEx_{uk}"]
                        st.rerun()
            if st.session_state.get(f"calEd_{uk}"):
                with st.form(f"calF_{uk}"):
                    alvo = st.selectbox("Qual paciente alterar?", nomes,
                        key=f"calEP_{uk}")
                    tipo = st.radio("Tipo de alteração",
                        ["Só nesta data (exceção)",
                         "Permanente (mudar cadastro deste paciente)"],
                        key=f"calTipo_{uk}")
                    cf1, cf2 = st.columns(2)
                    nd = cf1.date_input("Nova data",
                        value=data_d, format="DD/MM/YYYY",
                        key=f"calND_{uk}")
                    nh = cf2.selectbox("Novo horário", FAIXAS_HORARIO,
                        index=FAIXAS_HORARIO.index(hr) if hr in FAIXAS_HORARIO else 0,
                        key=f"calNH_{uk}")
                    if st.form_submit_button("Salvar"):
                        p_obj = pacientes_map.get(alvo)
                        if not p_obj:
                            st.error("Paciente não encontrado.")
                        else:
                            hn, _ = nh.split(" - ")
                            hh, mm = map(int, hn.split(":"))
                            hi, _ = hr.split(" - ")
                            h, m = map(int, hi.split(":"))
                            if tipo.startswith("Permanente"):
                                dias_pt = ["Segunda-feira", "Terça-feira",
                                    "Quarta-feira", "Quinta-feira",
                                    "Sexta-feira", "Sábado"]
                                if nd.weekday() <= 5:
                                    novo_dia_nome = dias_pt[nd.weekday()]
                                    p_obj.dia_atendimento = DiaSemana(novo_dia_nome)
                                    p_obj.dias_semana = novo_dia_nome
                                    p_obj.horario_atendimento = f"{novo_dia_nome}={nh}"
                                    db().commit()
                                    db().expire_all()
                                    st.success(f"Cadastro de {alvo} atualizado "
                                               f"para {novo_dia_nome} {nh}.")
                                    del st.session_state[f"calEd_{uk}"]
                                    st.rerun()
                                else:
                                    st.error("Domingo não é permitido.")
                            else:
                                ini_orig = datetime.combine(data_d, time(h, m))
                                db().add(AgendaSessao(
                                    id_paciente=p_obj.id_paciente,
                                    data_hora_inicio=ini_orig,
                                    data_hora_fim=ini_orig.replace(hour=h + 1),
                                    status_presenca=StatusPresenca.CANCELADA))
                                ini_nova = datetime.combine(nd, time(hh, mm))
                                db().add(AgendaSessao(
                                    id_paciente=p_obj.id_paciente,
                                    data_hora_inicio=ini_nova,
                                    data_hora_fim=ini_nova.replace(hour=hh + 1),
                                    status_presenca=StatusPresenca.AGENDADA))
                                try:
                                    db().commit()
                                    db().expire_all()
                                except Exception as e:
                                    db().rollback()
                                    flash(f"Erro: {e}", "error")
                                del st.session_state[f"calEd_{uk}"]
                                st.rerun()
    if linhas_pdf:
        st.download_button("Baixar PDF (calendário do mês)",
            gerar_pdf(f"Calendário {int(cal_mes):02d}/{int(cal_ano)}", linhas_pdf),
            file_name="calendario_mes.pdf", mime="application/pdf")

    st.subheader("Sessões pontuais agendadas (editar/excluir)")
    st.caption("Aqui aparecem sessões avulsas criadas pelo botão 'Agendar' acima. "
               "Para alterar horário recorrente fixo, edite o cadastro do paciente.")
    futuras = db().query(AgendaSessao).filter(
        AgendaSessao.data_hora_inicio >= datetime.now(),
        extract("year", AgendaSessao.data_hora_inicio) == int(cal_ano),
        extract("month", AgendaSessao.data_hora_inicio) == int(cal_mes)
    ).order_by(AgendaSessao.data_hora_inicio).limit(50).all()
    if not futuras:
        st.info("Nenhuma sessão agendada.")
    for s in futuras:
        p = db().get(Paciente, s.id_paciente)
        c1, c2, c3 = st.columns([5, 1, 1])
        info = (f"**{p.nome if p else '?'}** — "
                f"{s.data_hora_inicio.strftime('%d/%m/%Y %H:%M')} — "
                f"{s.status_presenca.value}")
        if s.remarcada_de:
            info += (f"  \n_↻ Remarcada de "
                     f"{s.remarcada_de.strftime('%d/%m')}"
                     f"{' — ' + s.remarcada_motivo if s.remarcada_motivo else ''}_")
        c1.markdown(info)
        if c2.button("Editar", key=f"eds_{s.id_sessao}"):
            st.session_state[f"edsess_{s.id_sessao}"] = True
        if c3.button("Excluir", key=f"dls_{s.id_sessao}"):
            db().delete(s); db().commit()
            st.rerun()
        if st.session_state.get(f"edsess_{s.id_sessao}"):
            with st.form(f"fsess_{s.id_sessao}"):
                cc1, cc2 = st.columns(2)
                nd = cc1.date_input("Nova data",
                    value=s.data_hora_inicio.date(),
                    format="DD/MM/YYYY", key=f"nd_{s.id_sessao}")
                nh = cc2.selectbox("Novo horário", FAIXAS_HORARIO,
                    key=f"nh_{s.id_sessao}")
                if st.form_submit_button("Salvar"):
                    hi, _ = nh.split(" - ")
                    h, m = map(int, hi.split(":"))
                    ini = datetime.combine(nd, time(h, m))
                    s.data_hora_inicio = ini
                    s.data_hora_fim = ini.replace(hour=h + 1)
                    db().commit()
                    del st.session_state[f"edsess_{s.id_sessao}"]
                    st.rerun()
    rows = [{"Paciente": (db().get(Paciente, s.id_paciente).nome
                          if db().get(Paciente, s.id_paciente) else "?"),
             "Inicio": s.data_hora_inicio.strftime("%d/%m %H:%M"),
             "Presenca": s.status_presenca.value} for s in futuras]
    st.download_button("Baixar PDF", gerar_pdf("Próximas Sessões", rows),
        file_name="proximas_sessoes.pdf", mime="application/pdf")


# ---------- PAGAMENTOS ----------
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


# ---------- FINANCEIRO ----------
def tela_financeiro():
    mostrar_flash()
    from app.services.financeiro import fmt_br, expandir_recorrentes
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
    k1, k2, k3 = st.columns(3)
    k1.metric("Faturamento Previsto", fmt_br(r["faturamento_previsto"]))
    k2.metric("Faturamento Realizado", fmt_br(r["faturamento_realizado"]))
    k3.metric("Lucro Líquido", fmt_br(r["lucro_liquido"]))
    st.caption(f"💰 Total de despesas: {fmt_br(r['total_despesas'])} — detalhe na seção '💸 Despesas do período' mais abaixo")

    if r["linhas"]:
        import plotly.graph_objects as go
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
    fin_rows = [{**l, "faturamento_previsto": fmt_br(l["faturamento_previsto"]),
        "faturamento_realizado": fmt_br(l["faturamento_realizado"])}
        for l in r["linhas"]]
    st.dataframe(fin_rows, use_container_width=True)
    st.download_button("Baixar PDF",
        gerar_pdf(f"Financeiro — {rotulo}", fin_rows),
        file_name="financeiro.pdf", mime="application/pdf")

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
        # Checkboxes FORA do form para reagir imediatamente
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
        # Datas FORA do form para fim acompanhar inicio
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
                if not descricao or descricao == "— Selecione —":
                    st.error("Escolha uma categoria.")
                else:
                    if rec:
                        import calendar as cal2
                        _, td = cal2.monthrange(int(ano_ini), int(mes_ini))
                        dia = min(int(dia_v), td)
                        venc_calc = date(int(ano_ini), int(mes_ini), dia)
                        mes_fim_str = (f"{int(ano_fim):04d}-{int(mes_fim_in):02d}"
                                       if tem_fim else None)
                        # se mes de inicio for passado, marca como paga
                        hj_ = datetime.now().date()
                        eh_pass = (int(ano_ini), int(mes_ini)) < (hj_.year, hj_.month)
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
                        hj_ = datetime.now().date()
                        eh_pass = venc < hj_
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
                        d.valor = Decimal(str(nv))
                        db().commit()
                        del st.session_state[f"edd_{d.id_despesa}"]
                        st.rerun()


# ---------- CALENDÁRIO (indisponibilidades) ----------
def tela_calendario():
    mostrar_flash()
    st.header("📅 Calendário do Consultório")
    ABAS = ["Visão geral", "Feriados oficiais",
            "Indisponibilidades (férias/imprevistos)"]
    aba_sel = st.radio("Seção", ABAS, horizontal=True,
                       key="cal_aba", label_visibility="collapsed")
    st.divider()

    if aba_sel == "Visão geral":
        st.caption("Tudo o que afeta o atendimento no ano: feriados oficiais "
                   "+ bloqueios cadastrados (férias, imprevistos).")
        ano_v = st.number_input("Ano", 2025, 2040, datetime.now().year,
                                key="ano_visao")
        # Feriados
        fer = feriados_brasil(int(ano_v))
        eventos = [{"Data": d, "Tipo": t, "Descrição": n}
                   for d, (n, t) in fer.items()]
        # Indisponibilidades do ano
        indisps = db().query(Indisponibilidade).all()
        for r in indisps:
            if r.data.year == int(ano_v):
                # Se motivo "Outro" e ha observacao, usa a obs como motivo
                if r.motivo.value == "Outro" and r.observacao:
                    motivo_label = r.observacao
                    obs_extra = ""
                else:
                    motivo_label = r.motivo.value
                    obs_extra = r.observacao or ""
                desc = (motivo_label +
                        ("" if r.dia_todo else f" ({r.horario})") +
                        (f" — {obs_extra}" if obs_extra else ""))
                eventos.append({"Data": r.data,
                                "Tipo": "Bloqueio (consultório)",
                                "Descrição": desc})
        eventos.sort(key=lambda x: x["Data"])
        linhas_v = [{"Data": e["Data"].strftime("%d/%m/%Y"),
                     "Dia": ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"][e["Data"].weekday()],
                     "Tipo": e["Tipo"], "Descrição": e["Descrição"]}
                    for e in eventos]
        st.dataframe(linhas_v, use_container_width=True, height=600)
        st.download_button("Baixar PDF (visão geral)",
            gerar_pdf(f"Calendário {ano_v} — Visão geral", linhas_v),
            file_name=f"calendario_{ano_v}.pdf", mime="application/pdf")

    elif aba_sel == "Feriados oficiais":
        c1, c2 = st.columns([1, 3])
        ano_f = c1.number_input("Ano", 2025, 2040, datetime.now().year, key="ano_fer")
        tipos = c2.multiselect("Filtrar tipo",
            ["Nacional", "Estadual SP", "Municipal SP"],
            default=["Nacional", "Estadual SP", "Municipal SP"])
        fer = feriados_brasil(int(ano_f))
        linhas = sorted(
            [{"Data": d.strftime("%d/%m/%Y"),
              "Dia da semana": ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"][d.weekday()],
              "Feriado": nome, "Tipo": tipo}
             for d, (nome, tipo) in fer.items() if tipo in tipos],
            key=lambda x: datetime.strptime(x["Data"], "%d/%m/%Y"))
        st.dataframe(linhas, use_container_width=True, height=600)
        st.download_button("Baixar PDF (feriados do ano)",
            gerar_pdf(f"Feriados {ano_f}", linhas),
            file_name=f"feriados_{ano_f}.pdf", mime="application/pdf")
        st.caption("Fontes: Portaria MGI 11.460/2025 (federal), "
                   "Lei 9.497/1997 (estadual SP - 9/jul), "
                   "Lei 14.485/2007 (municipal SP - 25/jan). "
                   "Datas móveis (Carnaval, Páscoa, Corpus Christi) "
                   "calculadas automaticamente até 2040.")

    elif aba_sel == "Indisponibilidades (férias/imprevistos)":
        st.caption("Marque dias/horários em que não vai atender (férias, "
                   "feriado prolongado, imprevisto, compromisso fixo). "
                   "Já entram no cálculo financeiro e na grade de horários.")
        dia_todo = st.checkbox("Dia inteiro", value=True, key="ind_dia")
        recor = st.checkbox("Repetir toda semana (compromisso fixo)",
            value=False, key="ind_rec",
            help="Ex: fisioterapia toda terça 10-14h e quinta 16-18h")
        ci1, ci2 = st.columns(2)
        d_ini = ci1.date_input("De", format="DD/MM/YYYY",
            value=datetime.now().date(), key="ind_de")
        d_fim = ci2.date_input("Até (inclusive)", format="DD/MM/YYYY",
            value=d_ini, min_value=d_ini, key="ind_ate")
        motivo = st.selectbox("Motivo", [m.value for m in MotivoIndisp],
                              key="ind_motivo")
        motivo_outro = ""
        if motivo == "Outro":
            motivo_outro = st.text_input("Especifique o motivo (opcional)",
                key="ind_motivo_outro",
                placeholder="Ex: Fisioterapia, reunião, curso...")

        # Dias da semana selecionados (so se recor)
        DIAS_LISTA = [e.value for e in DiaSemana]
        dias_selecionados = []
        if recor:
            dias_selecionados = st.multiselect(
                "Repetir em qual(is) dia(s) da semana?",
                DIAS_LISTA, default=[DIAS_LISTA[0]], key="ind_dias_sem")

        # Horarios: por-dia se recor+multiplos dias; senao 1 par geral
        horarios_por_dia = {}  # nome_dia -> "HH:MM - HH:MM"
        horario_geral = None
        if not dia_todo:
            if recor and len(dias_selecionados) > 1:
                st.markdown("**Horário de cada dia:**")
                for d_nome in dias_selecionados:
                    ch1, ch2 = st.columns(2)
                    h_das = ch1.selectbox(f"{d_nome} — Das", HORARIOS_INICIO,
                        index=HORARIOS_INICIO.index("13:00")
                            if "13:00" in HORARIOS_INICIO else 0,
                        key=f"ind_das_{d_nome}")
                    h_ate = ch2.selectbox(f"{d_nome} — Até", HORARIOS_FIM,
                        index=HORARIOS_FIM.index("14:00")
                            if "14:00" in HORARIOS_FIM else 0,
                        key=f"ind_ate_{d_nome}")
                    if h_ate <= h_das:
                        st.error(f"{d_nome}: 'Até' deve ser depois de 'Das'.")
                    horarios_por_dia[d_nome] = f"{h_das} - {h_ate}"
            else:
                ch1, ch2 = st.columns(2)
                h_das = ch1.selectbox("Das", HORARIOS_INICIO,
                    index=HORARIOS_INICIO.index("13:00")
                        if "13:00" in HORARIOS_INICIO else 0,
                    key="ind_das")
                h_ate = ch2.selectbox("Até", HORARIOS_FIM,
                    index=HORARIOS_FIM.index("14:00")
                        if "14:00" in HORARIOS_FIM else 0,
                    key="ind_ate_h")
                if h_ate <= h_das:
                    st.error("'Até' deve ser depois de 'Das'.")
                horario_geral = f"{h_das} - {h_ate}"

        with st.form("nova_indisp"):
            obs = st.text_input("Observação (opcional)")
            if st.form_submit_button("Adicionar"):
                if d_fim < d_ini:
                    st.error("Data final anterior à inicial.")
                elif recor and not dias_selecionados:
                    st.error("Selecione ao menos um dia da semana.")
                else:
                    # Valida horarios
                    erro_hr = False
                    if not dia_todo:
                        if horarios_por_dia:
                            for d_nome, hr in horarios_por_dia.items():
                                das, ate = hr.split(" - ")
                                if ate <= das:
                                    erro_hr = True; break
                        elif horario_geral:
                            das, ate = horario_geral.split(" - ")
                            if ate <= das:
                                erro_hr = True
                    if erro_hr:
                        st.error("Corrija os horários (Até deve ser > Das).")
                    else:
                        obs_final = obs
                        if motivo == "Outro" and motivo_outro.strip():
                            obs_final = motivo_outro.strip()
                            if obs:
                                obs_final += f" — {obs}"
                        from datetime import timedelta
                        dias_idx = {"Segunda-feira":0,"Terça-feira":1,
                            "Quarta-feira":2,"Quinta-feira":3,
                            "Sexta-feira":4,"Sábado":5}
                        alvos_idx = ({dias_idx[n] for n in dias_selecionados}
                                     if recor else None)
                        # idx->nome para olhar horario_por_dia
                        idx_para_nome = {dias_idx[n]: n
                                         for n in dias_selecionados}
                        d = d_ini
                        qtd = 0
                        while d <= d_fim:
                            if recor and d.weekday() not in alvos_idx:
                                d += timedelta(days=1); continue
                            if dia_todo:
                                hr = None
                            elif horarios_por_dia:
                                hr = horarios_por_dia[idx_para_nome[
                                    d.weekday()]]
                            else:
                                hr = horario_geral
                            db().add(Indisponibilidade(
                                data=d, dia_todo=dia_todo,
                                horario=hr,
                                motivo=MotivoIndisp(motivo),
                                observacao=obs_final))
                            qtd += 1
                            d += timedelta(days=1)
                        db().commit()
                        registrar(db(), st.session_state.username,
                                  "INDISP_CRIADA",
                                  f"{d_ini}..{d_fim} {motivo}")
                        flash(f"{qtd} bloqueio(s) registrado(s).",
                              "success")
                        st.rerun()

        st.subheader("Bloqueios cadastrados")
        from app.services.indisponibilidade import (agrupar_em_ranges,
                                                     formatar_grupo)
        regs = db().query(Indisponibilidade).order_by(
            Indisponibilidade.data.desc()).limit(500).all()
        grupos = agrupar_em_ranges(regs)
        if not grupos:
            st.info("Nenhum bloqueio cadastrado.")
        for g in grupos:
            gkey = f"g_{g['ids'][0]}"
            txt = formatar_grupo(g)
            c1, c2, c3 = st.columns([6, 1, 1])
            c1.write(txt)
            if c2.button("Editar", key=f"edi_{gkey}"):
                st.session_state[f"edi_open_{gkey}"] = True
            if c3.button("Remover", key=f"rmi_{gkey}"):
                for rid in g["ids"]:
                    obj = db().query(Indisponibilidade).get(rid)
                    if obj: db().delete(obj)
                db().commit()
                registrar(db(), st.session_state.username,
                          "INDISP_REMOVIDA",
                          f"{txt} ({len(g['ids'])} dias)")
                flash(f"{len(g['ids'])} bloqueio(s) removido(s).", "success")
                st.rerun()
            if st.session_state.get(f"edi_open_{gkey}"):
                with st.form(f"edi_f_{gkey}"):
                    st.caption("Editar bloqueio (aplica a todos os dias do grupo)")
                    ce1, ce2 = st.columns(2)
                    nv_ini = ce1.date_input("De", value=g["ini"],
                        format="DD/MM/YYYY", key=f"edi_de_{gkey}")
                    nv_fim = ce2.date_input("Até", value=g["fim"],
                        format="DD/MM/YYYY", min_value=nv_ini,
                        key=f"edi_ate_{gkey}")
                    nv_mot = st.selectbox("Motivo",
                        [m.value for m in MotivoIndisp],
                        index=[m.value for m in MotivoIndisp].index(g["motivo"]),
                        key=f"edi_mot_{gkey}")
                    nv_diatd = st.checkbox("Dia inteiro",
                        value=g["dia_todo"], key=f"edi_dt_{gkey}")
                    eh_multi = g.get("padrao") == "semanal_multi"
                    eh_semanal = g.get("padrao") == "semanal"
                    nv_hr = None
                    nv_slots = []  # so para multi: lista de {weekday, horario}
                    DIAS_PT = ["Segunda-feira","Terça-feira","Quarta-feira",
                               "Quinta-feira","Sexta-feira","Sábado","Domingo"]
                    if not nv_diatd and eh_multi:
                        st.markdown("**Horário de cada dia:**")
                        for s in g.get("slots", []):
                            d_nome = s["dia_semana"]
                            cur_das, cur_ate = "13:00", "14:00"
                            if s.get("horario") and " - " in s["horario"]:
                                try:
                                    cur_das, cur_ate = s["horario"].split(" - ")
                                except Exception:
                                    pass
                            cm1, cm2 = st.columns(2)
                            nd = cm1.selectbox(f"{d_nome} — Das",
                                HORARIOS_INICIO,
                                index=(HORARIOS_INICIO.index(cur_das)
                                       if cur_das in HORARIOS_INICIO else 0),
                                key=f"edi_das_{gkey}_{s['weekday']}")
                            na = cm2.selectbox(f"{d_nome} — Até",
                                HORARIOS_FIM,
                                index=(HORARIOS_FIM.index(cur_ate)
                                       if cur_ate in HORARIOS_FIM else 0),
                                key=f"edi_ate_{gkey}_{s['weekday']}")
                            nv_slots.append({"weekday": s["weekday"],
                                "horario": f"{nd} - {na}"})
                    elif not nv_diatd:
                        cur_das, cur_ate = "13:00", "14:00"
                        if g["horario"] and " - " in g["horario"]:
                            try:
                                cur_das, cur_ate = g["horario"].split(" - ")
                            except Exception:
                                pass
                        ceh1, ceh2 = st.columns(2)
                        nv_das = ceh1.selectbox("Das", HORARIOS_INICIO,
                            index=(HORARIOS_INICIO.index(cur_das)
                                   if cur_das in HORARIOS_INICIO else 0),
                            key=f"edi_das_{gkey}")
                        nv_ate = ceh2.selectbox("Até", HORARIOS_FIM,
                            index=(HORARIOS_FIM.index(cur_ate)
                                   if cur_ate in HORARIOS_FIM else 0),
                            key=f"edi_ate_h_{gkey}")
                        nv_hr = f"{nv_das} - {nv_ate}"
                    nv_obs = st.text_input(
                        "Especifique" if g["motivo"] == "Outro"
                        else "Observação",
                        value=g["obs"] or "",
                        key=f"edi_obs_{gkey}",
                        placeholder=("Ex: Médico, reunião, curso..."
                            if g["motivo"] == "Outro" else ""),
                        help=("Aparece no lugar de 'Outro' nas listagens."
                              if g["motivo"] == "Outro" else None))
                    cb1, cb2 = st.columns(2)
                    if cb1.form_submit_button("Salvar"):
                        erro = False
                        if not nv_diatd and eh_multi:
                            for s in nv_slots:
                                das, ate = s["horario"].split(" - ")
                                if ate <= das:
                                    erro = True; break
                        elif not nv_diatd and nv_ate <= nv_das:
                            erro = True
                        if erro:
                            st.error("Corrija os horários (Até > Das).")
                        else:
                            for rid in g["ids"]:
                                obj = db().query(Indisponibilidade).get(rid)
                                if obj: db().delete(obj)
                            from datetime import timedelta
                            wd_map = ({s["weekday"]: s["horario"]
                                       for s in nv_slots} if eh_multi
                                      else None)
                            wds_alvo = (set(wd_map.keys()) if eh_multi
                                        else ({g["ini"].weekday()}
                                              if eh_semanal else None))
                            d = nv_ini
                            while d <= nv_fim:
                                if wds_alvo is not None \
                                        and d.weekday() not in wds_alvo:
                                    d += timedelta(days=1); continue
                                if nv_diatd:
                                    hr_d = None
                                elif eh_multi:
                                    hr_d = wd_map[d.weekday()]
                                else:
                                    hr_d = nv_hr
                                db().add(Indisponibilidade(
                                    data=d, dia_todo=nv_diatd,
                                    horario=hr_d,
                                    motivo=MotivoIndisp(nv_mot),
                                    observacao=nv_obs))
                                d += timedelta(days=1)
                            db().commit()
                            registrar(db(), st.session_state.username,
                                      "INDISP_EDITADA", formatar_grupo(g))
                            del st.session_state[f"edi_open_{gkey}"]
                            flash("Bloqueio atualizado.", "success")
                            st.rerun()
                    if cb2.form_submit_button("Cancelar"):
                        del st.session_state[f"edi_open_{gkey}"]
                        st.rerun()


# ---------- USUARIOS (so Dona/Programador) ----------
def tela_usuarios():
    mostrar_flash()
    st.header("Gerenciamento de Usuários")
    st.subheader("Criar novo usuário")
    with st.form("novo_u"):
        c1, c2 = st.columns(2)
        un = c1.text_input("Login (username)")
        nm = c2.text_input("Nome completo")
        em = c1.text_input("Email")
        pf = c2.selectbox("Perfil", [p.value for p in Perfil])
        sn = st.text_input("Senha inicial", type="password",
                           help="Mín. 6 letras + 1 número + 1 caractere especial")
        if st.form_submit_button("Criar"):
            from app.auth.senha_policy import validar_senha
            ok_s, msg_s = validar_senha(sn)
            if not un:
                st.error("Login é obrigatório.")
            elif not ok_s:
                st.error(msg_s)
            elif db().query(Usuario).filter(Usuario.username == un).first():
                st.error("Usuário já existe.")
            else:
                db().add(Usuario(username=un, nome=nm, email=em,
                    senha_hash=gerar_hash(sn), perfil=Perfil(pf), ativo=True))
                db().commit()
                registrar(db(), st.session_state.username,
                          "USUARIO_CRIADO", f"perfil={pf}")
                flash(f"Usuário '{un}' criado.", "success")
                st.rerun()
    st.subheader("Usuários existentes")
    for u in db().query(Usuario).all():
        c1, c2, c3 = st.columns([3, 2, 1])
        c1.write(f"**{u.username}** — {u.nome} ({u.email or 'sem email'})")
        c2.write(f"{u.perfil.value} — {'Ativo' if u.ativo else 'Inativo'}")
        if u.username != st.session_state.username:
            if c3.button("Excluir", key=f"del_{u.id_usuario}"):
                db().delete(u); db().commit()
                registrar(db(), st.session_state.username,
                          "USUARIO_EXCLUIDO", f"alvo={u.username}")
                st.rerun()


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
    TODAS = {"Cadastro": tela_cadastro, "Agenda": tela_agenda,
             "Calendário": tela_calendario,
             "Pagamentos": tela_pagamentos, "Financeiro": tela_financeiro,
             "Usuários": tela_usuarios}
    if perfil == Perfil.DONA.value:
        permitidas = ["Cadastro", "Agenda", "Calendário",
                      "Pagamentos", "Financeiro", "Usuários"]
    elif perfil == Perfil.SECRETARIA.value:
        permitidas = ["Cadastro", "Agenda", "Calendário", "Pagamentos"]
    elif perfil == Perfil.FINANCEIRO.value:
        permitidas = ["Pagamentos", "Financeiro"]
    else:  # PROGRAMADOR
        permitidas = list(TODAS.keys())

    aba = st.sidebar.radio("Menu", permitidas)
    TODAS[aba]()
