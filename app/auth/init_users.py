"""Inicializa o primeiro administrador sem senhas fixas no codigo."""
import os

from app.auth.login import gerar_hash
from app.auth.senha_policy import validar_senha
from app.db.models import Perfil, Usuario
from app.db.session import get_session


def inicializar_usuarios():
    """Cria um usuario Dona via variaveis de ambiente, se configurado.

    Se ja existir qualquer usuario, nao altera nada. Se a senha de bootstrap
    nao estiver configurada, o primeiro usuario deve ser criado pela tela de
    primeiro acesso.
    """
    db = get_session()
    try:
        if db.query(Usuario).first():
            return

        senha = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
        if not senha:
            return

        ok, msg = validar_senha(senha)
        if not ok:
            raise ValueError("BOOTSTRAP_ADMIN_PASSWORD invalida: " + msg)

        db.add(Usuario(
            username=os.getenv("BOOTSTRAP_ADMIN_USERNAME", "dona"),
            nome=os.getenv("BOOTSTRAP_ADMIN_NAME", "Dona do Consultorio"),
            email=os.getenv("BOOTSTRAP_ADMIN_EMAIL") or None,
            senha_hash=gerar_hash(senha),
            perfil=Perfil.DONA,
            ativo=True,
        ))
        db.commit()
    finally:
        db.close()
