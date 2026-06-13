import unittest
import sys
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append('c:/Users/eduar/Downloads/projeto_consultorio')

from app.db.models import (
    Base, Paciente, AgendaSessao, StatusPaciente,
    StatusPresenca, StatusPagamento, TipoContrato, Frequencia
)
from app.services.financeiro import (
    realizado_paciente, consolidado_mes, consolidado_periodo,
    historico_ultimos_meses
)


class FinanceiroDbTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Cria banco de dados SQLite em memória para teste
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.session = self.Session()
        # Limpa tabelas de transação a cada teste
        self.session.query(AgendaSessao).delete()
        self.session.query(Paciente).delete()
        self.session.commit()

        # Criar paciente para teste
        self.paciente = Paciente(
            nome="Paciente Teste Financeiro",
            telefone="5511999998888",
            email="paciente@test.com",
            data_nascimento=date(1990, 1, 1),
            tipo_contrato=TipoContrato.AVULSO,
            valor_sessao=Decimal("120.00"),
            frequencia=Frequencia.SEMANAL,
            dias_semana="Seg",
            horario_atendimento="Seg=09:00 - 10:00",
            status=StatusPaciente.ATIVO,
            ativo_desde=date(2026, 1, 1)
        )
        self.session.add(self.paciente)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_realizado_e_inadimplencia_paciente(self):
        p_id = self.paciente.id_paciente

        # Sessão 1: Realizada e Paga
        s1 = AgendaSessao(
            id_paciente=p_id,
            data_hora_inicio=datetime(2026, 6, 1, 9, 0),
            data_hora_fim=datetime(2026, 6, 1, 10, 0),
            status_presenca=StatusPresenca.REALIZADA,
            status_pagamento=StatusPagamento.PAGO
        )
        # Sessão 2: Realizada e Pendente (Deve contar na Inadimplência)
        s2 = AgendaSessao(
            id_paciente=p_id,
            data_hora_inicio=datetime(2026, 6, 8, 9, 0),
            data_hora_fim=datetime(2026, 6, 8, 10, 0),
            status_presenca=StatusPresenca.REALIZADA,
            status_pagamento=StatusPagamento.PENDENTE
        )
        # Sessão 3: Cancelou em cima e Atrasada (Deve contar na Inadimplência)
        s3 = AgendaSessao(
            id_paciente=p_id,
            data_hora_inicio=datetime(2026, 6, 15, 9, 0),
            data_hora_fim=datetime(2026, 6, 15, 10, 0),
            status_presenca=StatusPresenca.CANCELOU_EM_CIMA,
            status_pagamento=StatusPagamento.ATRASADO
        )
        # Sessão 4: Realizada e Isenta
        s4 = AgendaSessao(
            id_paciente=p_id,
            data_hora_inicio=datetime(2026, 6, 22, 9, 0),
            data_hora_fim=datetime(2026, 6, 22, 10, 0),
            status_presenca=StatusPresenca.REALIZADA,
            status_pagamento=StatusPagamento.ISENTO
        )
        # Sessão 5: Falta (isenta de cobrança no faturamento realizado)
        s5 = AgendaSessao(
            id_paciente=p_id,
            data_hora_inicio=datetime(2026, 6, 29, 9, 0),
            data_hora_fim=datetime(2026, 6, 29, 10, 0),
            status_presenca=StatusPresenca.IMPREVISTO,
            status_pagamento=StatusPagamento.PENDENTE
        )

        self.session.add_all([s1, s2, s3, s4, s5])
        self.session.commit()

        res = realizado_paciente(self.session, self.paciente, 2026, 6)

        # Faturamento realizado deve somar s1, s2, s3, s4 = 4 * 120.00 = 480.00
        self.assertEqual(res["faturamento_realizado"], Decimal("480.00"))
        # Inadimplência deve somar s2, s3 = 2 * 120.00 = 240.00
        self.assertEqual(res["inadimplencia"], Decimal("240.00"))
        self.assertEqual(res["sessoes_realizadas"], 4)

    def test_consolidado_mes_inadimplencia(self):
        p_id = self.paciente.id_paciente
        # Adicionar uma sessão pendente e uma paga
        s1 = AgendaSessao(
            id_paciente=p_id,
            data_hora_inicio=datetime(2026, 6, 1, 9, 0),
            data_hora_fim=datetime(2026, 6, 1, 10, 0),
            status_presenca=StatusPresenca.REALIZADA,
            status_pagamento=StatusPagamento.PENDENTE
        )
        s2 = AgendaSessao(
            id_paciente=p_id,
            data_hora_inicio=datetime(2026, 6, 8, 9, 0),
            data_hora_fim=datetime(2026, 6, 8, 10, 0),
            status_presenca=StatusPresenca.REALIZADA,
            status_pagamento=StatusPagamento.PAGO
        )
        self.session.add_all([s1, s2])
        self.session.commit()

        c = consolidado_mes(self.session, 2026, 6)
        self.assertEqual(c["faturamento_realizado"], Decimal("240.00"))
        self.assertEqual(c["inadimplencia"], Decimal("120.00"))
        self.assertEqual(len(c["linhas"]), 1)
        self.assertEqual(c["linhas"][0]["inadimplencia"], Decimal("120.00"))

    def test_consolidado_periodo_inadimplencia(self):
        p_id = self.paciente.id_paciente
        s1 = AgendaSessao(
            id_paciente=p_id,
            data_hora_inicio=datetime(2026, 6, 1, 9, 0),
            data_hora_fim=datetime(2026, 6, 1, 10, 0),
            status_presenca=StatusPresenca.REALIZADA,
            status_pagamento=StatusPagamento.PENDENTE
        )
        s2 = AgendaSessao(
            id_paciente=p_id,
            data_hora_inicio=datetime(2026, 7, 1, 9, 0),
            data_hora_fim=datetime(2026, 7, 1, 10, 0),
            status_presenca=StatusPresenca.REALIZADA,
            status_pagamento=StatusPagamento.ATRASADO
        )
        self.session.add_all([s1, s2])
        self.session.commit()

        cp = consolidado_periodo(self.session, 2026, [6, 7])
        self.assertEqual(cp["faturamento_realizado"], Decimal("240.00"))
        self.assertEqual(cp["inadimplencia"], Decimal("240.00"))

    def test_historico_ultimos_meses(self):
        # Garante que roda sem quebrar
        hist = historico_ultimos_meses(self.session, 2026, 6, qtd=3)
        self.assertEqual(len(hist), 3)
        self.assertEqual(hist[0]["mes_rotulo"], "04/2026")
        self.assertEqual(hist[1]["mes_rotulo"], "05/2026")
        self.assertEqual(hist[2]["mes_rotulo"], "06/2026")

    def test_is_mes_fechado(self):
        from app.services.financeiro import is_mes_fechado
        from app.db.models import FechamentoMensal

        # Inicialmente deve estar aberto
        self.assertFalse(is_mes_fechado(self.session, date(2026, 6, 15)))
        self.assertFalse(is_mes_fechado(self.session, "2026-06"))

        # Adiciona fechamento
        f = FechamentoMensal(
            mes_referencia="2026-06",
            fechado_por="test_user",
            total_recebido=Decimal("1000.00"),
            total_despesas=Decimal("200.00")
        )
        self.session.add(f)
        self.session.commit()

        # Agora deve retornar True
        self.assertTrue(is_mes_fechado(self.session, date(2026, 6, 15)))
        self.assertTrue(is_mes_fechado(self.session, datetime(2026, 6, 10, 14, 30)))
        self.assertTrue(is_mes_fechado(self.session, "2026-06"))

        # Outros meses devem continuar abertos
        self.assertFalse(is_mes_fechado(self.session, date(2026, 7, 1)))
        self.assertFalse(is_mes_fechado(self.session, "2026-07"))


if __name__ == "__main__":
    unittest.main()
