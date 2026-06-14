"""Autenticacao: senhas com hash bcrypt. LGPD: nunca logar senha."""
import bcrypt
from app.db.models import Usuario


def gerar_hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt(rounds=12)).decode()


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return bcrypt.checkpw(senha.encode(), senha_hash.encode())


def criar_usuario(db, username: str, nome: str, senha: str) -> Usuario:
    u = Usuario(username=username, nome=nome,
                senha_hash=gerar_hash(senha), ativo=True)
    db.add(u); db.commit()
    return u


from datetime import datetime, timedelta

def autenticar(db, username: str, senha: str):
    """Retorna (Usuario, status) se credenciais validas, senao (None, erro_msg)."""
    import time
    import secrets

    def _delay_falha():
        # Atraso aleatório entre 1.0 e 2.0 segundos para mitigar timing attacks e brute force
        time.sleep(1.0 + secrets.SystemRandom().uniform(0.0, 1.0))

    if not username:
        _delay_falha()
        return None, "Credenciais inválidas."
    
    u = db.query(Usuario).filter(
        Usuario.username == username, Usuario.ativo == True).first()  # noqa: E712
    if not u:
        _delay_falha()
        return None, "Credenciais inválidas."
        
    # Verifica se o usuário está sob bloqueio temporário
    if u.bloqueado_ate and u.bloqueado_ate > datetime.now():
        restante = int((u.bloqueado_ate - datetime.now()).total_seconds())
        minutos = (restante // 60) + 1
        return None, f"Conta bloqueada temporariamente. Tente novamente em {minutos} min."
        
    if verificar_senha(senha, u.senha_hash):
        # Sucesso: limpa tentativas e bloqueio
        u.tentativas_login = 0
        u.bloqueado_ate = None
        db.commit()
        
        if u.trocar_senha_proximo_login:
            return u, "trocar_senha"
        return u, "ok"
    else:
        # Falha: incrementa tentativas
        _delay_falha()
        u.tentativas_login += 1
        if u.tentativas_login >= 5:
            u.bloqueado_ate = datetime.now() + timedelta(minutes=15)
            db.commit()
            return None, "Conta bloqueada por 15 minutos após 5 tentativas incorretas."
            
        db.commit()
        restantes = 5 - u.tentativas_login
        return None, f"Credenciais inválidas. Você tem mais {restantes} tentativas antes do bloqueio."
