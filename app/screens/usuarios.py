import streamlit as st
from app.screens.shared import db, registrar, mostrar_flash, flash, Usuario, Perfil, ui_header
from app.auth.senha_policy import validar_senha
from app.auth.login import gerar_hash
from app.auth.usuario_validacao import (
    normalizar_username,
    validar_email_opcional,
    validar_nome,
    validar_username,
)


def tela_usuarios():
    if st.session_state.get("perfil") not in ["Dona", "Programador"]:
        st.error("Acesso negado. Apenas administradores podem gerenciar usuários.")
        st.stop()
    mostrar_flash()
    ui_header("Gerenciamento de Acessos", icon="👥")
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
            elif not ok_s:
                st.error(msg_s)
            elif db().query(Usuario).filter(Usuario.username == un).first():
                st.error("Usuário já existe.")
                db().add(Usuario(username=un, nome=nm, email=em,
                    senha_hash=gerar_hash(sn), perfil=Perfil(pf), ativo=True,
                    trocar_senha_proximo_login=True))
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
