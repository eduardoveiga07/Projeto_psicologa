"""Validacao de forca de senha: min 6 letras, 1 numero, 1 especial."""
import re

ESPECIAIS = r"!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?~`"


def validar_senha(senha: str) -> tuple:
    """Retorna (ok, mensagem). ok=False se nao atender requisitos."""
    if not senha:
        return False, "Senha vazia."
    letras = sum(1 for c in senha if c.isalpha())
    tem_num = any(c.isdigit() for c in senha)
    tem_esp = bool(re.search(f"[{re.escape(ESPECIAIS)}]", senha))
    faltas = []
    if letras < 6:
        faltas.append(f"pelo menos 6 letras (tem {letras})")
    if not tem_num:
        faltas.append("pelo menos 1 número")
    if not tem_esp:
        faltas.append("pelo menos 1 caractere especial (ex: !@#$%)")
    if faltas:
        return False, "Senha fraca. Requer: " + "; ".join(faltas) + "."
    return True, "OK"
