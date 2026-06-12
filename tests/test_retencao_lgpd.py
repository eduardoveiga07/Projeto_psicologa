import unittest
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base, Paciente, Auditoria, StatusPaciente, TipoContrato, Frequencia
)
from app.services.retencao_lgpd import executar_limpeza_lgpd, RETENCAO_PACIENTES_DIAS, RETENCAO_AUDITORIA_DIAS

class RetencaoLgpdTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Banco SQLite em memória
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.session = self.Session()
        # Limpa dados
        self.session.query(Paciente).delete()
        self.session.query(Auditoria).delete()
        self.session.commit()

        # Paciente Ativo
        self.p_ativo = Paciente(
            nome="Paciente Ativo",
            telefone="5511999998888",
            email="ativo@test.com",
            data_nascimento=date(1990, 1, 1),
            tipo_contrato=TipoContrato.AVULSO,
            valor_sessao=Decimal("150.00"),
            frequencia=Frequencia.SEMANAL,
            horario_atendimento="Seg=09:00 - 10:00",
            status=StatusPaciente.ATIVO,
            ativo_desde=date(2026, 1, 1)
        )
        
        # Paciente Inativo recente (desativado há 10 dias)
        self.p_inativo_recente = Paciente(
            nome="Paciente Inativo Recente",
            telefone="5511999997777",
            email="recente@test.com",
            data_nascimento=date(1991, 1, 1),
            tipo_contrato=TipoContrato.AVULSO,
            valor_sessao=Decimal("150.00"),
            frequencia=Frequencia.SEMANAL,
            horario_atendimento="Seg=09:00 - 10:00",
            status=StatusPaciente.INATIVO,
            data_desativacao=datetime.now().date() - timedelta(days=10)
        )
        
        # Paciente Inativo antigo (desativado há RETENCAO_PACIENTES_DIAS + 10 dias)
        self.p_inativo_antigo = Paciente(
            nome="Paciente Inativo Antigo",
            telefone="5511999996666",
            email="antigo@test.com",
            data_nascimento=date(1992, 1, 1),
            tipo_contrato=TipoContrato.AVULSO,
            valor_sessao=Decimal("150.00"),
            frequencia=Frequencia.SEMANAL,
            horario_atendimento="Seg=09:00 - 10:00",
            status=StatusPaciente.INATIVO,
            data_desativacao=datetime.now().date() - timedelta(days=RETENCAO_PACIENTES_DIAS + 10)
        )
        
        self.session.add_all([self.p_ativo, self.p_inativo_recente, self.p_inativo_antigo])
        
        # Log de Auditoria recente
        self.log_recente = Auditoria(
            quando=datetime.now() - timedelta(days=5),
            usuario="dona",
            acao="LOGIN",
            detalhe="sucesso"
        )
        
        # Log de Auditoria antigo (criado há RETENCAO_AUDITORIA_DIAS + 10 dias)
        # Atenção: sqlite em memória não suporta server_default=func.now() para a data customizada no insert,
        # mas como estamos passando explicitamente a data de criação no modelo, o SQLAlchemy fará o insert correto.
        self.log_antigo = Auditoria(
            quando=datetime.now() - timedelta(days=RETENCAO_AUDITORIA_DIAS + 10),
            usuario="dona",
            acao="LOGIN_FALHOU",
            detalhe="tentativa inválida"
        )
        
        self.session.add_all([self.log_recente, self.log_antigo])
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_executar_limpeza_lgpd(self):
        # Executa a limpeza
        stats = executar_limpeza_lgpd(self.session)
        
        # Valida contadores retornados
        self.assertEqual(stats["pacientes_removidos"], 1)
        self.assertEqual(stats["logs_removidos"], 1)
        
        # Verifica no banco quais dados sobraram
        pacientes_restantes = self.session.query(Paciente).all()
        nomes_restantes = [p.nome for p in pacientes_restantes]
        
        self.assertIn("Paciente Ativo", nomes_restantes)
        self.assertIn("Paciente Inativo Recente", nomes_restantes)
        self.assertNotIn("Paciente Inativo Antigo", nomes_restantes)
        
        logs_restantes = self.session.query(Auditoria).all()
        acoes_restantes = [l.acao for l in logs_restantes]
        
        self.assertIn("LOGIN", acoes_restantes)
        self.assertNotIn("LOGIN_FALHOU", acoes_restantes)

if __name__ == "__main__":
    unittest.main()
