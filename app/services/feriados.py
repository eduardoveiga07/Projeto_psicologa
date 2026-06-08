"""Feriados nacionais brasileiros. Calcula moveis a partir da Pascoa."""
from datetime import date, timedelta


def _pascoa(ano: int) -> date:
    """Algoritmo de Gauss para a Pascoa Catolica."""
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    mes = (h + L - 7 * m + 114) // 31
    dia = ((h + L - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_brasil(ano: int) -> dict:
    """Retorna {date: (nome, tipo)} no ano. Tipo: Nacional/Estadual/Municipal."""
    p = _pascoa(ano)
    return {
        date(ano, 1, 1): ("Confraternização Universal", "Nacional"),
        date(ano, 1, 25): ("Aniversário de São Paulo", "Municipal SP"),
        p - timedelta(days=48): ("Carnaval (segunda)", "Nacional"),
        p - timedelta(days=47): ("Carnaval (terça)", "Nacional"),
        p - timedelta(days=2): ("Sexta-feira Santa", "Nacional"),
        p: ("Páscoa", "Nacional"),
        date(ano, 4, 21): ("Tiradentes", "Nacional"),
        date(ano, 5, 1): ("Dia do Trabalho", "Nacional"),
        p + timedelta(days=60): ("Corpus Christi", "Nacional"),
        date(ano, 7, 9): ("Revolução Constitucionalista", "Estadual SP"),
        date(ano, 9, 7): ("Independência", "Nacional"),
        date(ano, 10, 12): ("N. Sra. Aparecida", "Nacional"),
        date(ano, 11, 2): ("Finados", "Nacional"),
        date(ano, 11, 15): ("Proclamação da República", "Nacional"),
        date(ano, 11, 20): ("Consciência Negra", "Nacional"),
        date(ano, 12, 25): ("Natal", "Nacional"),
    }


def eh_feriado(d: date) -> str:
    """Retorna nome do feriado se d for feriado, senão ''."""
    fer = feriados_brasil(d.year).get(d)
    return fer[0] if fer else ""
