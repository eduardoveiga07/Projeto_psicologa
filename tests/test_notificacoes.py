import unittest
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append('c:/Users/eduar/Downloads/projeto_consultorio')

from app.db.models import (
    Base, Paciente, AgendaSessao, StatusPaciente,
    StatusPresenca, StatusPagamento, SistemaStatus, TipoContrato, Frequencia
)
from app.services.notificacoes import obter_notificacoes


class NotificacoesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.session = self.Session()
        self.session.query(AgendaSessao).delete()
        self.session.query(Paciente).delete()
        self.session.query(SistemaStatus).delete()
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_backup_atrasado(self):
        # Sem backups -> deve notificar backup atrasado
        notifs = obter_notificacoes(self.session)
        backup_atrasado = [n for n in notifs if n["tipo"] == "backup_atrasado"]
        self.assertEqual(len(backup_atrasado), 1)
        self.assertIn("Nenhum backup", backup_atrasado[0]["detalhe"])

        # Backup recente (há 2 horas) -> não deve notificar backup atrasado
        self.session.add(SistemaStatus(
            tipo="backup",
            status="sucesso",
            quando=datetime.now() - timedelta(hours=2),
            detalhe="Backup efetuado com sucesso"
        ))
        self.session.commit()

        notifs = obter_notificacoes(self.session)
        backup_atrasado = [n for n in notifs if n["tipo"] == "backup_atrasado"]
        self.assertEqual(len(backup_atrasado), 0)

        # Backup antigo (há 30 horas) -> deve notificar backup atrasado
        self.session.query(SistemaStatus).delete()
        self.session.add(SistemaStatus(
            tipo="backup",
            status="sucesso",
            quando=datetime.now() - timedelta(hours=30),
            detalhe="Backup efetuado com sucesso"
        ))
        self.session.commit()

        notifs = obter_notificacoes(self.session)
        backup_atrasado = [n for n in notifs if n["tipo"] == "backup_atrasado"]
        self.assertEqual(len(backup_atrasado), 1)

    def test_erro_tecnico_recente(self):
        # Sem falhas técnicas recentes -> sem notificações de erro
        notifs = obter_notificacoes(self.session)
        erros = [n for n in notifs if n["tipo"] == "erro_tecnico"]
        self.assertEqual(len(erros), 0)

        # Falha técnica recente (há 1 dia) -> deve notificar erro
        self.session.add(SistemaStatus(
            tipo="backup",
            status="falha",
            quando=datetime.now() - timedelta(days=1),
            detalhe="Erro ao conectar no banco para backup"
        ))
        self.session.commit()

        notifs = obter_notificacoes(self.session)
        erros = [n for n in notifs if n["tipo"] == "erro_tecnico"]
        self.assertEqual(len(erros), 1)
        self.assertIn("Erro ao conectar", erros[0]["detalhe"])

    def test_paciente_sem_horario(self):
        # Paciente ativo com horário e dias de semana -> não deve notificar
        paciente = Paciente(
            nome="Paciente Valido",
            telefone="11999998888",
            email="paciente@test.com",
            data_nascimento=date(1990, 1, 1),
            tipo_contrato=TipoContrato.AVULSO,
            frequencia=Frequencia.SEMANAL,
            valor_sessao=Decimal("120.00"),
            dias_semana="Seg",
            horario_atendimento="Seg=09:00 - 10:00",
            status=StatusPaciente.ATIVO,
            ativo_desde=date(2026, 1, 1)
        )
        self.session.add(paciente)
        self.session.commit()

        notifs = obter_notificacoes(self.session)
        sem_horario = [n for n in notifs if n["tipo"] == "paciente_sem_horario"]
        self.assertEqual(len(sem_horario), 0)

        # Paciente ativo sem horário -> deve notificar
        paciente.horario_atendimento = ""
        self.session.commit()

        notifs = obter_notificacoes(self.session)
        sem_horario = [n for n in notifs if n["tipo"] == "paciente_sem_horario"]
        self.assertEqual(len(sem_horario), 1)

    def test_sessoes_sem_pagamento(self):
        paciente = Paciente(
            nome="Paciente Devedor",
            telefone="11999998888",
            email="paciente@test.com",
            data_nascimento=date(1990, 1, 1),
            tipo_contrato=TipoContrato.AVULSO,
            frequencia=Frequencia.SEMANAL,
            valor_sessao=Decimal("120.00"),
            dias_semana="Seg",
            horario_atendimento="Seg=09:00 - 10:00",
            status=StatusPaciente.ATIVO,
            ativo_desde=date(2026, 1, 1)
        )
        self.session.add(paciente)
        self.session.flush()

        # Sessão realizada pendente no passado -> deve notificar
        sessao = AgendaSessao(
            id_paciente=paciente.id_paciente,
            data_hora_inicio=datetime.now() - timedelta(days=2),
            data_hora_fim=datetime.now() - timedelta(days=2, hours=-1),
            status_presenca=StatusPresenca.REALIZADA,
            status_pagamento=StatusPagamento.PENDENTE
        )
        self.session.add(sessao)
        self.session.commit()

        notifs = obter_notificacoes(self.session)
        sem_pg = [n for n in notifs if n["tipo"] == "sessoes_sem_pagamento"]
        self.assertEqual(len(sem_pg), 1)
