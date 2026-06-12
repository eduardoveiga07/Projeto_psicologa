import streamlit as st
from app.screens.shared import db, registrar, mostrar_flash
from app.auth.senha_service import trocar_senha_usuario


def tela_minha_conta():
    mostrar_flash()
    st.header("Minha conta")
    st.subheader("Alterar senha")
    with st.form("alterar_senha"):
        senha_atual = st.text_input("Senha atual", type="password")
        nova_senha = st.text_input("Nova senha", type="password",
            help="Min. 6 letras + 1 numero + 1 caractere especial")
        confirmar = st.text_input("Confirmar nova senha", type="password")
        if st.form_submit_button("Salvar nova senha"):
            ok, msg = trocar_senha_usuario(
                db(), st.session_state.username,
                senha_atual, nova_senha, confirmar)
            if ok:
                registrar(db(), st.session_state.username,
                          "SENHA_ALTERADA", "alteracao pelo usuario logado")
                st.session_state.clear()
                st.success(msg + " Faca login novamente.")
                st.stop()
            else:
                registrar(db(), st.session_state.get("username", "?"),
                          "SENHA_ALTERACAO_FALHOU",
                          "tentativa sem dados sensiveis")
                st.error(msg)
