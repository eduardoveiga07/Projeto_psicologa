"""Inicializa o primeiro administrador sem senhas fixas no codigo."""
import os

from app.auth.login import gerar_hash
from app.auth.senha_policy import validar_senha
from app.auth.usuario_validacao import (
    normalizar_username,
    validar_email_opcional,
    validar_nome,
    validar_username,
)
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

        username = normalizar_username(os.getenv("BOOTSTRAP_ADMIN_USERNAME", "dona"))
        nome = (os.getenv("BOOTSTRAP_ADMIN_NAME", "Dona do Consultorio") or "").strip()
        email = (os.getenv("BOOTSTRAP_ADMIN_EMAIL") or "").strip()
        for ok_v, msg_v in (
            validar_username(username),
            validar_nome(nome),
            validar_email_opcional(email),
        ):
            if not ok_v:
                raise ValueError("Bootstrap admin invalido: " + msg_v)

        db.add(Usuario(
            username=username,
            nome=nome,
            email=email or None,
            senha_hash=gerar_hash(senha),
            perfil=Perfil.DONA,
            ativo=True,
        ))
        db.commit()
    finally:
        db.close()
