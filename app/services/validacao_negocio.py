"""Módulo de validações de regras de negócio para pacientes, despesas e calendário."""
import re
from datetime import date
from decimal import Decimal

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validar_telefone(telefone: str) -> tuple:
    """Valida se o telefone contém apenas números (limpo) e comprimento aceitável."""
    if not telefone:
        return False, "Telefone é obrigatório."
    
    # Remove formatações comuns: +, -, parênteses e espaços
    tel_limpo = re.sub(r"[+\-\(\)\s]", "", telefone)
    
    if not tel_limpo.isdigit():
        return False, "Telefone deve conter apenas números após a limpeza dos caracteres especiais."
        
    if not (8 <= len(tel_limpo) <= 15):
        return False, "Telefone deve conter entre 8 e 15 dígitos numéricos."
        
    return True, tel_limpo


def validar_email_paciente(email: str) -> tuple:
    """Valida se o e-mail possui um formato estrutural correto (se preenchido)."""
    email_limpo = (email or "").strip()
    if not email_limpo:
        return True, ""
        
    if not EMAIL_RE.fullmatch(email_limpo):
        return False, "E-mail com formato inválido."
        
    return True, email_limpo


def validar_data_nascimento(nasc: date) -> tuple:
    """Garante que a data de nascimento esteja estritamente no passado."""
    if not nasc:
        return False, "Data de nascimento é obrigatória."
        
    if nasc >= date.today():
        return False, "Data de nascimento deve ser no passado."
        
    return True, "OK"


def validar_valor_sessao(valor: Decimal, em_avaliacao: bool = False) -> tuple:
    """Garante valores válidos e limites para sessões e avaliações."""
    if valor is None:
        return False, "Valor é obrigatório."
        
    val_dec = Decimal(str(valor))
    
    if em_avaliacao:
        if val_dec < Decimal("0.0"):
            return False, "Valor da avaliação não pode ser negativo."
    else:
        if val_dec <= Decimal("0.0"):
            return False, "Valor por sessão deve ser maior que zero para pacientes recorrentes."
            
    return True, "OK"


def validar_valor_despesa(valor: Decimal) -> tuple:
    """Garante que as despesas possuam valor positivo maior que zero."""
    if valor is None:
        return False, "Valor da despesa é obrigatório."
        
    val_dec = Decimal(str(valor))
    if val_dec <= Decimal("0.0"):
        return False, "Valor da despesa deve ser maior que zero."
        
    return True, "OK"


def validar_datas_bloqueio(inicio: date, fim: date) -> tuple:
    """Garante que o intervalo de datas de bloqueio/indisponibilidade é cronológico."""
    if not inicio or not fim:
        return False, "Ambas as datas (início e fim) são obrigatórias."
        
    if fim < inicio:
        return False, "Data de término não pode ser anterior à data de início."
        
    return True, "OK"
