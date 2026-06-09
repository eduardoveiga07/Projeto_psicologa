from datetime import date
from decimal import Decimal
from types import SimpleNamespace
import unittest

from app.db.models import DiaSemana, Frequencia, StatusPaciente
from app.services.calendario import (
    ocorrencias_no_mes,
    sessoes_previstas_lista,
)
from app.services.financeiro import fmt_br, previsto_paciente
from app.services.ocupacao import datas_paciente_no_mes, faixas_sobrepoem


def paciente_teste(**overrides):
    dados = {
        "nome": "Paciente Teste",
        "em_avaliacao": False,
        "status": StatusPaciente.ATIVO,
        "ativo_desde": None,
        "frequencia": Frequencia.SEMANAL,
        "dias_semana": DiaSemana.SEG.value,
        "dia_atendimento": None,
        "horario_atendimento": f"{DiaSemana.SEG.value}=09:00 - 10:00",
        "sessoes_mes_custom": None,
        "valor_sessao": Decimal("150.00"),
    }
    dados.update(overrides)
    return SimpleNamespace(**dados)


class RegrasAgendaFinanceiroTest(unittest.TestCase):
    def test_ocorrencias_desconta_datas_bloqueadas(self):
        bloqueadas = {date(2026, 6, 1)}

        total = ocorrencias_no_mes(2026, 6, DiaSemana.SEG, bloqueadas)

        self.assertEqual(total, 4)

    def test_sessoes_previstas_lista_soma_multiplos_dias(self):
        total = sessoes_previstas_lista(
            2026,
            6,
            [DiaSemana.SEG.value, DiaSemana.QUA.value],
            Frequencia.DUAS_SEMANA,
        )

        self.assertEqual(total, 9)

    def test_faixas_sobrepoem_considera_intersecao_real(self):
        self.assertTrue(faixas_sobrepoem("09:00 - 10:00", "09:30 - 10:30"))
        self.assertFalse(faixas_sobrepoem("09:00 - 10:00", "10:00 - 11:00"))

    def test_datas_paciente_respeita_inicio_da_recorrencia(self):
        paciente = paciente_teste(ativo_desde=date(2026, 6, 10))

        datas = datas_paciente_no_mes(paciente, 2026, 6)

        self.assertEqual(
            datas,
            [
                (date(2026, 6, 15), "09:00 - 10:00"),
                (date(2026, 6, 22), "09:00 - 10:00"),
                (date(2026, 6, 29), "09:00 - 10:00"),
            ],
        )

    def test_previsto_paciente_usa_regra_legada_sem_db(self):
        paciente = paciente_teste()

        previsto = previsto_paciente(
            paciente,
            2026,
            6,
            bloqueadas={date(2026, 6, 1)},
            db=None,
        )

        self.assertEqual(previsto["paciente"], "Paciente Teste")
        self.assertEqual(previsto["sessoes_previstas"], 4)
        self.assertEqual(previsto["faturamento_previsto"], Decimal("600.00"))

    def test_previsto_personalizado_usa_quantidade_fixa(self):
        paciente = paciente_teste(
            frequencia=Frequencia.PERSONALIZADO,
            sessoes_mes_custom=3,
            valor_sessao=Decimal("200.00"),
        )

        previsto = previsto_paciente(paciente, 2026, 6, db=None)

        self.assertEqual(previsto["sessoes_previstas"], 3)
        self.assertEqual(previsto["faturamento_previsto"], Decimal("600.00"))

    def test_fmt_br_formata_moeda_brasileira(self):
        self.assertEqual(fmt_br(Decimal("26280.00")), "R$ 26.280,00")


if __name__ == "__main__":
    unittest.main()
