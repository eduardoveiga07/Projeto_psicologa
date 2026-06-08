"""Calendario: conta ocorrencias dos dias da semana num mes real."""
import calendar
from datetime import date
from app.db.models import DiaSemana, Frequencia
from app.services.feriados import feriados_brasil

# Mapa DiaSemana -> indice (Segunda=0 ... Domingo=6)
_DIA_IDX = {DiaSemana.SEG: 0, DiaSemana.TER: 1, DiaSemana.QUA: 2,
            DiaSemana.QUI: 3, DiaSemana.SEX: 4, DiaSemana.SAB: 5}


def ocorrencias_no_mes(ano: int, mes: int, dia: DiaSemana,
                       bloqueadas: set = None) -> int:
    """Quantas vezes 'dia' ocorre em ano/mes, descontando feriados e
    datas em 'bloqueadas' (set de date)."""
    idx = _DIA_IDX[dia]
    _, total = calendar.monthrange(ano, mes)
    fer = feriados_brasil(ano)
    bloq = bloqueadas or set()
    return sum(1 for d in range(1, total + 1)
               if calendar.weekday(ano, mes, d) == idx
               and date(ano, mes, d) not in fer
               and date(ano, mes, d) not in bloq)


def ocorrencias_dias(ano: int, mes: int, dias: list,
                     bloqueadas: set = None) -> int:
    """Soma ocorrencias de varios dias da semana no mes (desconta bloqueadas)."""
    total = 0
    for nome in dias:
        try:
            total += ocorrencias_no_mes(ano, mes, DiaSemana(nome), bloqueadas)
        except ValueError:
            pass
    return total


def sessoes_previstas_lista(ano: int, mes: int, dias: list,
                            freq: Frequencia, bloqueadas: set = None) -> int:
    """Previsao de sessoes (desconta bloqueadas)."""
    base = ocorrencias_dias(ano, mes, dias, bloqueadas)
    if freq == Frequencia.SEMANAL:
        return base
    if freq == Frequencia.QUINZENAL:
        return 2
    if freq == Frequencia.MENSAL:
        return 1
    if freq in (Frequencia.DUAS_SEMANA, Frequencia.TRES_SEMANA):
        # base ja soma os 2 ou 3 dias escolhidos no mes.
        return base
    # PERSONALIZADO: tratado via sessoes_mes_custom no financeiro.
    return base


# Compatibilidade com chamadas antigas (1 dia).
def sessoes_previstas(ano: int, mes: int, dia, freq: Frequencia) -> int:
    nome = dia.value if hasattr(dia, "value") else dia
    return sessoes_previstas_lista(ano, mes, [nome], freq)
