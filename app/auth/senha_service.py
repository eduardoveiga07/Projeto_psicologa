"""Servicos de troca de senha de usuario autenticado."""
from app.auth.login import gerar_hash, verificar_senha
from app.auth.senha_policy import validar_senha
from app.db.models import Usuario


def trocar_senha_usuario(db, username: str, senha_atual: str,
                         nova_senha: str, confirmar_senha: str) -> tuple:
    """Troca a senha do usuario logado.

    Retorna (ok, mensagem). Nao registra auditoria aqui para manter o servico
    independente da interface.
    """
    if not senha_atual:
        return False, "Informe a senha atual."
    if nova_senha != confirmar_senha:
        return False, "As senhas nao conferem."

    ok, msg = validar_senha(nova_senha)
    if not ok:
        return False, msg

    usuario = db.query(Usuario).filter(
        Usuario.username == username,
        Usuario.ativo == True,  # noqa: E712
    ).first()
    if not usuario:
        return False, "Usuario nao encontrado ou inativo."
    if not verificar_senha(senha_atual, usuario.senha_hash):
        return False, "Senha atual invalida."
    if verificar_senha(nova_senha, usuario.senha_hash):
        return False, "A nova senha deve ser diferente da senha atual."

    usuario.senha_hash = gerar_hash(nova_senha)
    db.commit()
    return True, "Senha alterada com sucesso."
