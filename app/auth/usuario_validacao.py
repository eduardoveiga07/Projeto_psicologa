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
