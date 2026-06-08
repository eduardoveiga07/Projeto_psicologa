"""Autenticacao: senhas com hash bcrypt. LGPD: nunca logar senha."""
import bcrypt
from app.db.models import Usuario


def gerar_hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return bcrypt.checkpw(senha.encode(), senha_hash.encode())


def criar_usuario(db, username: str, nome: str, senha: str) -> Usuario:
    u = Usuario(username=username, nome=nome,
                senha_hash=gerar_hash(senha), ativo=True)
    db.add(u); db.commit()
    return u


def autenticar(db, username: str, senha: str):
    """Retorna Usuario se credenciais validas e ativo, senao None."""
    u = db.query(Usuario).filter(
        Usuario.username == username, Usuario.ativo == True).first()  # noqa: E712
    if u and verificar_senha(senha, u.senha_hash):
        return u
    return None
