"""Envio de email via SMTP. Se nao configurado, mostra na tela (modo dev)."""
import os, smtplib, secrets
from email.message import EmailMessage
from datetime import datetime, timedelta
from app.db.models import Usuario


def _smtp_configurado() -> bool:
    return all(os.getenv(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS"))


def enviar_email(destino: str, assunto: str, corpo: str) -> tuple:
    """Retorna (sucesso, mensagem). Modo dev: nao envia, devolve o corpo."""
    if not _smtp_configurado():
        return False, corpo  # modo dev: caller mostra na tela
    msg = EmailMessage()
    msg["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER"))
    msg["To"] = destino
    msg["Subject"] = assunto
    msg.set_content(corpo)
    try:
        with smtplib.SMTP_SSL(os.getenv("SMTP_HOST"),
                              int(os.getenv("SMTP_PORT", "465"))) as s:
            s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
            s.send_message(msg)
        return True, "Email enviado."
    except Exception:
        return False, "Falha ao enviar email."


def gerar_reset(db, email: str) -> tuple:
    """Gera token, salva no usuario e dispara email. Retorna (ok, msg/token)."""
    u = db.query(Usuario).filter(Usuario.email == email,
                                 Usuario.ativo == True).first()  # noqa: E712
    if not u:
        # Resposta generica por seguranca (nao revela se email existe).
        return True, "Se o email estiver cadastrado, instruções foram enviadas."
    u.reset_token = secrets.token_urlsafe(32)
    u.reset_expira = datetime.now() + timedelta(hours=1)
    db.commit()
    corpo = (f"Olá {u.nome},\n\nSeu código para redefinir a senha é:\n\n"
             f"{u.reset_token}\n\nVálido por 1 hora.")
    ok, msg = enviar_email(u.email, "Redefinição de senha", corpo)
    if ok:
        return True, "Email enviado. Verifique a caixa de entrada."
    # Modo dev: devolve o token na tela.
    return True, f"[MODO DEV - SMTP não configurado] Código: {u.reset_token}"


def aplicar_reset(db, token: str, nova_senha: str) -> tuple:
    from app.auth.login import gerar_hash
    from app.auth.senha_policy import validar_senha
    ok, msg = validar_senha(nova_senha)
    if not ok:
        return False, msg
    u = db.query(Usuario).filter(Usuario.reset_token == token).first()
    if not u or not u.reset_expira or u.reset_expira < datetime.now():
        return False, "Código inválido ou expirado."
    u.senha_hash = gerar_hash(nova_senha)
    u.reset_token = None
    u.reset_expira = None
    db.commit()
    return True, "Senha alterada com sucesso."
