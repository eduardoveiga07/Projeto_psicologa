import unittest
import sys
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append('c:/Users/eduar/Downloads/projeto_consultorio')

from app.db.models import (
    Base, Paciente, AgendaSessao, Despesa, StatusPaciente,
    StatusPresenca, StatusPagamento, TipoContrato, Frequencia
)


class BuscaGlobalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.session = self.Session()
        self.session.query(AgendaSessao).delete()
        self.session.query(Paciente).delete()
        self.session.query(Despesa).delete()
        self.session.commit()

        # Add mock records
        self.pac1 = Paciente(
            nome="Eduardo da Silva",
            telefone="11999991111",
            email="eduardo@test.com",
            data_nascimento=date(1990, 1, 1),
            tipo_contrato=TipoContrato.AVULSO,
            frequencia=Frequencia.SEMANAL,
            valor_sessao=Decimal("120.00"),
            dias_semana="Seg",
            horario_atendimento="Seg=09:00 - 10:00",
            status=StatusPaciente.ATIVO,
            ativo_desde=date(2026, 1, 1)
        )
        self.pac2 = Paciente(
            nome="Aline Medeiros",
            telefone="11999992222",
            email="aline@test.com",
            data_nascimento=date(1992, 5, 5),
            tipo_contrato=TipoContrato.AVULSO,
            frequencia=Frequencia.SEMANAL,
            valor_sessao=Decimal("150.00"),
            dias_semana="Ter",
            horario_atendimento="Ter=10:00 - 11:00",
            status=StatusPaciente.ATIVO,
            ativo_desde=date(2026, 1, 1)
        )
        self.session.add_all([self.pac1, self.pac2])
        self.session.flush()

        self.desp1 = Despesa(
            descricao="Aluguel de Consultório",
            valor=Decimal("1500.00"),
            data_vencimento=date(2026, 6, 5),
            mes_referencia="2026-06",
            recorrente=False,
            paga=True,
            data_pagamento=date(2026, 6, 5)
        )
        self.desp2 = Despesa(
            descricao="Material de Escritório",
            valor=Decimal("200.00"),
            data_vencimento=date(2026, 6, 10),
            mes_referencia="2026-06",
            recorrente=False,
            paga=False
        )
        self.session.add_all([self.desp1, self.desp2])

        self.sess1 = AgendaSessao(
            id_paciente=self.pac1.id_paciente,
            data_hora_inicio=datetime(2026, 6, 12, 9, 0),
            data_hora_fim=datetime(2026, 6, 12, 10, 0),
            status_presenca=StatusPresenca.REALIZADA,
            status_pagamento=StatusPagamento.PENDENTE
        )
        self.session.add(self.sess1)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_busca_pacientes(self):
        # Busca por nome "Eduardo"
        query = "eduardo"
        pacs = self.session.query(Paciente).filter(
            (Paciente.nome.ilike(f"%{query}%")) |
            (Paciente.email.ilike(f"%{query}%")) |
            (Paciente.telefone.ilike(f"%{query}%"))
        ).all()
        self.assertEqual(len(pacs), 1)
        self.assertEqual(pacs[0].nome, "Eduardo da Silva")

        # Busca por parte do email "test.com"
        query = "test.com"
        pacs = self.session.query(Paciente).filter(
            (Paciente.nome.ilike(f"%{query}%")) |
            (Paciente.email.ilike(f"%{query}%")) |
            (Paciente.telefone.ilike(f"%{query}%"))
        ).all()
        self.assertEqual(len(pacs), 2)

    def test_busca_despesas(self):
        # Busca por "Aluguel"
        query = "aluguel"
        desps = self.session.query(Despesa).filter(
            Despesa.descricao.ilike(f"%{query}%")
        ).all()
        self.assertEqual(len(desps), 1)
        self.assertEqual(desps[0].descricao, "Aluguel de Consultório")

    def test_busca_sessoes(self):
        # Busca sessões por nome do paciente "Eduardo"
        query = "eduardo"
        sessoes = self.session.query(AgendaSessao).join(Paciente).filter(
            Paciente.nome.ilike(f"%{query}%")
        ).all()
        self.assertEqual(len(sessoes), 1)
        self.assertEqual(sessoes[0].id_paciente, self.pac1.id_paciente)
