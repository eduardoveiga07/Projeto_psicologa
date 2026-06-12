import streamlit as st
from datetime import datetime
from app.screens.shared import db, registrar, Usuario, Perfil
from app.auth.login import autenticar, gerar_hash
from app.services.email_srv import gerar_reset, aplicar_reset
from app.auth.usuario_validacao import (
    normalizar_username,
    validar_email_opcional,
    validar_nome,
    validar_username,
)
from app.auth.senha_policy import validar_senha
from app.services.logger import get_logger

logger = get_logger("login")


def tela_login():
    st.title("Gestão Consultório - Login")
    sem_usuarios = db().query(Usuario.id_usuario).first() is None
    if sem_usuarios:
        st.warning("Nenhum usuario cadastrado. Crie o primeiro acesso administrativo.")
        with st.expander("Primeiro acesso (criar usuario)", expanded=True):
            with st.form("primeiro_acesso"):
                c1, c2 = st.columns(2)
                un = c1.text_input("Login", value="dona")
                nm = c2.text_input("Nome completo")
                em = c1.text_input("Email")
                sn = c2.text_input("Senha", type="password",
                    help="Min. 6 letras + 1 numero + 1 caractere especial")
                cf = st.text_input("Confirmar senha", type="password")
                if st.form_submit_button("Criar primeiro usuario"):
                    un = normalizar_username(un)
                    nm = (nm or "").strip()
                    em = (em or "").strip()
                    ok_s, msg_s = validar_senha(sn)
                    ok_u, msg_u = validar_username(un)
                    ok_n, msg_n = validar_nome(nm)
                    ok_e, msg_e = validar_email_opcional(em)
                    if not ok_u:
                        st.error(msg_u)
                    elif not ok_n:
                        st.error(msg_n)
                    elif not ok_e:
                        st.error(msg_e)
                    elif sn != cf:
                        st.error("As senhas nao conferem.")
                    elif not ok_s:
                        st.error(msg_s)
                    else:
                        db().add(Usuario(username=un, nome=nm, email=em,
                            senha_hash=gerar_hash(sn), perfil=Perfil.DONA,
                            ativo=True))
                        db().commit()
                        registrar(db(), un, "PRIMEIRO_USUARIO_CRIADO",
                                  "perfil=Dona")
                        st.success("Primeiro usuario criado. Faca login.")
                        st.rerun()
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
                logger.info(f"Login bem-sucedido para o usuario '{user.username}' com perfil '{user.perfil.value}'")
                registrar(db(), user.username, "LOGIN",
                          "login bem-sucedido")
                st.rerun()
            else:
                logger.warning(f"Tentativa de login malsucedida para o usuario '{u or '?'}'")
                registrar(db(), u or "?", "LOGIN_FALHOU",
                          "tentativa de login invalida")
                st.error("Credenciais inválidas.")
    with st.expander("Esqueci minha senha"):
        with st.form("reset_pedido"):
            em = st.text_input("Seu email cadastrado")
            if st.form_submit_button("Enviar código"):
                logger.info(f"Solicitacao de redefinicao de senha para o e-mail '{em}'")
                ok, msg = gerar_reset(db(), em)
                st.info(msg)
    with st.expander("Tenho um código de redefinição"):
        with st.form("reset_aplicar"):
            tk = st.text_input("Código recebido")
            ns = st.text_input("Nova senha", type="password")
            if st.form_submit_button("Trocar senha"):
                logger.info("Tentando aplicar codigo de redefinicao de senha...")
                ok, msg = aplicar_reset(db(), tk, ns)
                if ok:
                    logger.info("Senha redefinida com sucesso via codigo.")
                else:
                    logger.warning(f"Falha ao redefinir senha via codigo: {msg}")
                (st.success if ok else st.error)(msg)
