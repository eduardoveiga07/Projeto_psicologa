import unittest
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.models import (
    Base, Paciente, AgendaSessao, ContratoHistorico, Indisponibilidade,
    StatusPaciente, StatusPresenca, StatusPagamento, TipoContrato, Frequencia, DiaSemana
)
from app.services.contrato import abrir_periodo
from app.services.agenda_geracao import AgendaGeracaoService

class AgendaGeracaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.session = self.Session()
        self.session.query(AgendaSessao).delete()
        self.session.query(ContratoHistorico).delete()
        self.session.query(Indisponibilidade).delete()
        self.session.query(Paciente).delete()
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_geracao_sessoes_semanais(self):
        # 1. Registrar paciente recorrente Terça-feira
        p = Paciente(
            nome="Paciente Terça",
            telefone="5511999998888",
            data_nascimento=date(1995, 5, 20),
            tipo_contrato=TipoContrato.MENSAL,
            valor_sessao=Decimal("150.00"),
            frequencia=Frequencia.SEMANAL,
            dias_semana="Terça-feira",
            horario_atendimento="Terça-feira=09:00 - 10:00",
            status=StatusPaciente.ATIVO,
            ativo_desde=date(2026, 6, 1)
        )
        self.session.add(p)
        self.session.commit()
        
        abrir_periodo(self.session, p, date(2026, 6, 1))
        
        # 2. Gerar sessões futuras a partir de 01/06/2026 para 1 mês (limite_meses=1)
        # Terças-feiras são 2, 9, 16, 23, 30 de Junho.
        AgendaGeracaoService.gerar_sessoes_futuras(self.session, p, date(2026, 6, 1), limite_meses=1)
        self.session.commit()
        
        sessoes = self.session.query(AgendaSessao).filter(AgendaSessao.id_paciente == p.id_paciente).order_by(AgendaSessao.data_hora_inicio).all()
        self.assertEqual(len(sessoes), 5)
        
        # Datas geradas
        datas = [s.data_hora_inicio.date() for s in sessoes]
        self.assertEqual(datas, [
            date(2026, 6, 2),
            date(2026, 6, 9),
            date(2026, 6, 16),
            date(2026, 6, 23),
            date(2026, 6, 30)
        ])
        
        # Valores
        for s in sessoes:
            self.assertEqual(s.valor_sessao, Decimal("150.00"))
            self.assertEqual(s.status_presenca, StatusPresenca.AGENDADA)
            self.assertEqual(s.status_pagamento, StatusPagamento.PENDENTE)

    def test_geracao_com_bloqueios_e_feriados(self):
        # 1. Registrar paciente recorrente
        p = Paciente(
            nome="Paciente Bloqueio",
            telefone="5511999998888",
            data_nascimento=date(1995, 5, 20),
            tipo_contrato=TipoContrato.MENSAL,
            valor_sessao=Decimal("150.00"),
            frequencia=Frequencia.SEMANAL,
            dias_semana="Terça-feira",
            horario_atendimento="Terça-feira=09:00 - 10:00",
            status=StatusPaciente.ATIVO,
            ativo_desde=date(2026, 6, 1)
        )
        self.session.add(p)
        self.session.commit()
        
        abrir_periodo(self.session, p, date(2026, 6, 1))
        
        # 2. Cadastrar bloqueio/indisponibilidade dia 09/06/2026
        ind = Indisponibilidade(
            data=date(2026, 6, 9),
            dia_todo=True,
            observacao="Viagem"
        )
        self.session.add(ind)
        self.session.commit()
        
        # 3. Gerar sessões
        AgendaGeracaoService.gerar_sessoes_futuras(self.session, p, date(2026, 6, 1), limite_meses=1)
        self.session.commit()
        
        sessoes = self.session.query(AgendaSessao).filter(AgendaSessao.id_paciente == p.id_paciente).order_by(AgendaSessao.data_hora_inicio).all()
        self.assertEqual(len(sessoes), 5)
        
        # A sessão do dia 09/06/2026 deve ser cancelada/bloqueada
        s_bloq = [s for s in sessoes if s.data_hora_inicio.date() == date(2026, 6, 9)][0]
        self.assertEqual(s_bloq.status_presenca, StatusPresenca.CANCELADA)
        self.assertEqual(s_bloq.status_pagamento, StatusPagamento.ISENTO)
        self.assertEqual(s_bloq.remarcada_motivo, "Bloqueio (dia todo)")

    def test_remover_sessoes_futuras(self):
        # Registrar paciente
        p = Paciente(
            nome="Paciente Remover",
            telefone="5511999998888",
            data_nascimento=date(1995, 5, 20),
            tipo_contrato=TipoContrato.MENSAL,
            valor_sessao=Decimal("150.00"),
            frequencia=Frequencia.SEMANAL,
            dias_semana="Terça-feira",
            horario_atendimento="Terça-feira=09:00 - 10:00",
            status=StatusPaciente.ATIVO,
            ativo_desde=date(2026, 6, 1)
        )
        self.session.add(p)
        self.session.commit()
        abrir_periodo(self.session, p, date(2026, 6, 1))
        
        # Gerar sessões
        AgendaGeracaoService.gerar_sessoes_futuras(self.session, p, date(2026, 6, 1), limite_meses=1)
        self.session.commit()
        
        # Marcar uma sessão como realizada
        sessoes = self.session.query(AgendaSessao).order_by(AgendaSessao.data_hora_inicio).all()
        sessoes[0].status_presenca = StatusPresenca.REALIZADA
        self.session.commit()
        
        # Remover sessões a partir de 05/06/2026
        AgendaGeracaoService.remover_sessoes_futuras(self.session, p.id_paciente, date(2026, 6, 5))
        self.session.commit()
        
        # Apenas a sessão de 02/06 (realizada) deve restar
        restantes = self.session.query(AgendaSessao).all()
        self.assertEqual(len(restantes), 1)
        self.assertEqual(restantes[0].data_hora_inicio.date(), date(2026, 6, 2))

if __name__ == "__main__":
    unittest.main()
