"""Inicializa usuarios padrao. So roda se nao existir 'dona'."""
from app.db.session import get_session
from app.db.models import Usuario, Perfil
from app.auth.login import gerar_hash


def inicializar_usuarios():
    db = get_session()
    try:
        if db.query(Usuario).filter(Usuario.username == "dona").first():
            return
        db.query(Usuario).delete()
        db.add_all([
            Usuario(username="dona", nome="Dona do Consultório",
                    email="dona@exemplo.com", senha_hash=gerar_hash("Donaforte@1"),
                    perfil=Perfil.DONA, ativo=True),
            Usuario(username="secretaria", nome="Secretária",
                    email="secretaria@exemplo.com",
                    senha_hash=gerar_hash("Secret@123"),
                    perfil=Perfil.SECRETARIA, ativo=True),
            Usuario(username="financeiro", nome="Braço Direito Financeiro",
                    email="financeiro@exemplo.com",
                    senha_hash=gerar_hash("Financeiro@1"),
                    perfil=Perfil.FINANCEIRO, ativo=True),
            Usuario(username="dev", nome="Programador",
                    email="dev@exemplo.com", senha_hash=gerar_hash("Devforte@1"),
                    perfil=Perfil.PROGRAMADOR, ativo=True),
        ])
        db.commit()
    finally:
        db.close()
