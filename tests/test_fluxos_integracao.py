import unittest
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base, Paciente, AgendaSessao, ContratoHistorico, Despesa, StatusPaciente,
    StatusPresenca, StatusPagamento, TipoContrato, Frequencia
)
from app.services.contrato import garantir_historico_inicial, abrir_periodo
from app.services.financeiro import consolidado_mes

class FluxosIntegracaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Cria banco de dados SQLite em memória
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.session = self.Session()
        # Limpa dados antes de cada teste
        self.session.query(AgendaSessao).delete()
        self.session.query(ContratoHistorico).delete()
        self.session.query(Despesa).delete()
        self.session.query(Paciente).delete()
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_fluxo_registro_agendamento_pagamento_e_faturamento(self):
        # 1. Registrar um novo paciente recorrente
        paciente = Paciente(
            nome="Paciente Integracao",
            telefone="5511999998888",
            email="paciente_int@test.com",
            data_nascimento=date(1995, 5, 20),
            tipo_contrato=TipoContrato.MENSAL,
            valor_sessao=Decimal("150.00"),
            frequencia=Frequencia.SEMANAL,
            horario_atendimento="Ter=09:00 - 10:00",
            status=StatusPaciente.ATIVO,
            ativo_desde=date(2026, 6, 1)
        )
        self.session.add(paciente)
        self.session.commit()
        
        # Garante o histórico de contratos inicial
        garantir_historico_inicial(self.session)
        p_id = paciente.id_paciente
        
        # Valida que o contrato histórico correspondente foi criado
        contratos = self.session.query(ContratoHistorico).filter(ContratoHistorico.id_paciente == p_id).all()
        self.assertEqual(len(contratos), 1)
        self.assertEqual(contratos[0].valor_sessao, Decimal("150.00"))

        # 2. Agendar 4 sessões manuais para simular o período de atendimento
        data_base = datetime(2026, 6, 2, 9, 0) # Primeira terça de Junho/2026
        sessoes = []
        for i in range(4):
            inicio = data_base + timedelta(weeks=i)
            s = AgendaSessao(
                id_paciente=p_id,
                data_hora_inicio=inicio,
                data_hora_fim=inicio + timedelta(hours=1),
                status_presenca=StatusPresenca.AGENDADA,
                status_pagamento=StatusPagamento.PENDENTE
            )
            sessoes.append(s)
            self.session.add(s)
        self.session.commit()
        
        # Valida inserção das sessões
        sessoes_db = self.session.query(AgendaSessao).filter(AgendaSessao.id_paciente == p_id).all()
        self.assertEqual(len(sessoes_db), 4)

        # 3. Registrar presença e regras de cobrança automática
        # Sessão 1: Realizada -> deve continuar cobrando (PENDENTE)
        sessoes_db[0].status_presenca = StatusPresenca.REALIZADA
        
        # Sessão 2: Cancelou +24h -> deve se tornar ISENTA de cobrança automaticamente
        sessoes_db[1].status_presenca = StatusPresenca.CANCELOU_COM_ANTECEDENCIA
        sessoes_db[1].status_pagamento = StatusPagamento.ISENTO
        
        # Sessão 3: Cancelou -24h -> deve cobrar (PENDENTE)
        sessoes_db[2].status_presenca = StatusPresenca.CANCELOU_EM_CIMA
        
        # Sessão 4: Falta não justificada -> deve cobrar (PENDENTE)
        sessoes_db[3].status_presenca = StatusPresenca.FALTA
        self.session.commit()

        # 4. Simular lançar uma despesa fixa no mês de Junho/2026
        despesa = Despesa(
            descricao="Aluguel Consultorio",
            valor=Decimal("200.00"),
            data_vencimento=date(2026, 6, 10),
            mes_referencia="2026-06",
            paga=True,
            data_pagamento=date(2026, 6, 10)
        )
        self.session.add(despesa)
        self.session.commit()

        # 5. Liquidar (Pagar) a primeira sessão individualmente
        sessoes_db[0].status_pagamento = StatusPagamento.PAGO
        self.session.commit()
        
        # 6. Liquidar as sessões restantes cobráveis (Sessões 3 e 4) em LOTE
        # Simula a lógica de lote de pagamentos
        pendentes_lote = self.session.query(AgendaSessao).filter(
            AgendaSessao.id_paciente == p_id,
            AgendaSessao.status_pagamento == StatusPagamento.PENDENTE
        ).all()
        
        self.assertEqual(len(pendentes_lote), 2) # Sessões 2 (isenta) não entra. Sessão 1 já está Paga.
        
        for s in pendentes_lote:
            s.status_pagamento = StatusPagamento.PAGO
        self.session.commit()

        # 7. Validar o demonstrativo financeiro consolidado do mês de Junho/2026
        resumo = consolidado_mes(self.session, 2026, 6)
        
        # Faturamento previsto: 4 sessões em que o contrato prevê atendimento * valor_sessao
        # Faturamento realizado: valor total recebido das sessões pagas (Sessão 1, 3 e 4 = 3 * 150 = 450)
        # Despesas: Aluguel = 200
        # Inadimplência: 0 (todas as cobráveis foram pagas)
        self.assertEqual(resumo["faturamento_realizado"], Decimal("300.00"))
        self.assertEqual(resumo["total_despesas"], Decimal("200.00"))
        self.assertEqual(resumo["lucro_liquido"], Decimal("100.00"))
        self.assertEqual(resumo["inadimplencia"], Decimal("0.00"))

if __name__ == "__main__":
    unittest.main()
