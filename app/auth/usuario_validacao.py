"""Validacoes reutilizaveis para cadastro de usuarios."""
import re


USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,50}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalizar_username(username: str) -> str:
    return (username or "").strip().lower()


def validar_username(username: str) -> tuple:
    username = normalizar_username(username)
    if not username:
        return False, "Login e obrigatorio."
    if not USERNAME_RE.fullmatch(username):
        return False, (
            "Login deve ter 3 a 50 caracteres e usar apenas letras, "
            "numeros, ponto, hifen ou underline."
        )
    return True, "OK"


def validar_nome(nome: str) -> tuple:
    if not (nome or "").strip():
        return False, "Nome completo e obrigatorio."
    return True, "OK"


def validar_email_opcional(email: str) -> tuple:
    email = (email or "").strip()
    if email and not EMAIL_RE.fullmatch(email):
        return False, "Email invalido."
    return True, "OK"


def obter_telas_permitidas(perfil: str) -> list[str]:
    """Retorna a lista de nomes de telas permitidas para um determinado perfil."""
    from app.db.models import Perfil

    todas = [
        "Minha conta",
        "Cadastro",
        "Agenda",
        "Calendário",
        "Pagamentos",
        "Financeiro",
        "Usuários",
        "Auditoria"
    ]
    if perfil == Perfil.DONA.value:
        return todas
    elif perfil == Perfil.SECRETARIA.value:
        return ["Minha conta", "Cadastro", "Agenda", "Calendário", "Pagamentos"]
    elif perfil == Perfil.FINANCEIRO.value:
        return ["Minha conta", "Pagamentos", "Financeiro"]
    elif perfil == Perfil.PROGRAMADOR.value:
        return todas
    return todas

