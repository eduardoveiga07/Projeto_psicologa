import unittest
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
import uuid

from app.db.models import Base, AgendaSessao, ContratoHistorico, Usuario, Perfil, Frequencia

class DbConstraintsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Banco SQLite em memória para validação rápida de constraints
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.session = self.Session()

    def tearDown(self):
        self.session.rollback()
        self.session.close()

    def test_sessao_fim_menor_que_inicio_falha(self):
        # Sessão com data_hora_fim anterior a data_hora_inicio deve falhar na constraint ck_sessoes_datas
        s = AgendaSessao(
            id_paciente=uuid.uuid4(),
            data_hora_inicio=datetime(2026, 6, 12, 10, 0),
            data_hora_fim=datetime(2026, 6, 12, 9, 0),  # Menor que início!
            valor_sessao=Decimal("150.00")
        )
        self.session.add(s)
        with self.assertRaises(IntegrityError):
            self.session.commit()

    def test_contrato_vigente_ate_menor_que_de_falha(self):
        # Contrato com data de fim anterior ao inicio deve falhar na constraint ck_contratos_datas
        c = ContratoHistorico(
            id_paciente=uuid.uuid4(),
            vigente_de=date(2026, 6, 12),
            vigente_ate=date(2026, 6, 10),  # Anterior ao de!
            frequencia=Frequencia.SEMANAL,
            valor_sessao=Decimal("150.00")
        )
        self.session.add(c)
        with self.assertRaises(IntegrityError):
            self.session.commit()

    def test_usuario_tentativas_negativas_falha(self):
        # Usuário com tentativas de login negativas deve falhar na constraint ck_tentativas_pos
        u = Usuario(
            username="test_constraints",
            nome="Test User",
            senha_hash="hash",
            perfil=Perfil.SECRETARIA,
            tentativas_login=-1  # Negativo!
        )
        self.session.add(u)
        with self.assertRaises(IntegrityError):
            self.session.commit()

    def test_dados_validos_salvam_com_sucesso(self):
        # Dados coerentes devem ser persistidos normalmente
        u = Usuario(
            username="test_constraints_ok",
            nome="Test User Ok",
            senha_hash="hash",
            perfil=Perfil.SECRETARIA,
            tentativas_login=0
        )
        self.session.add(u)
        self.session.commit()
        self.assertIsNotNone(u.id_usuario)

    def test_sessao_valor_negativo_falha(self):
        # Sessão com valor negativo deve falhar
        s = AgendaSessao(
            id_paciente=uuid.uuid4(),
            data_hora_inicio=datetime(2026, 6, 12, 10, 0),
            data_hora_fim=datetime(2026, 6, 12, 11, 0),
            valor_sessao=Decimal("-10.00")
        )
        self.session.add(s)
        with self.assertRaises(IntegrityError):
            self.session.commit()

    def test_contrato_valor_negativo_falha(self):
        # Contrato histórico com valor negativo deve falhar
        c = ContratoHistorico(
            id_paciente=uuid.uuid4(),
            vigente_de=date(2026, 6, 12),
            frequencia=Frequencia.SEMANAL,
            valor_sessao=Decimal("-50.00")
        )
        self.session.add(c)
        with self.assertRaises(IntegrityError):
            self.session.commit()

    def test_duplicidade_sessao_paciente_falha(self):
        # Duas sessões para o mesmo paciente no mesmo horário devem falhar por restrição de unicidade
        paciente_id = uuid.uuid4()
        s1 = AgendaSessao(
            id_paciente=paciente_id,
            data_hora_inicio=datetime(2026, 6, 12, 10, 0),
            data_hora_fim=datetime(2026, 6, 12, 11, 0),
            valor_sessao=Decimal("150.00")
        )
        s2 = AgendaSessao(
            id_paciente=paciente_id,
            data_hora_inicio=datetime(2026, 6, 12, 10, 0),  # Mesmo horário
            data_hora_fim=datetime(2026, 6, 12, 11, 0),
            valor_sessao=Decimal("150.00")
        )
        self.session.add(s1)
        self.session.add(s2)
        with self.assertRaises(IntegrityError):
            self.session.commit()

    def test_sessao_paga_sem_data_falha(self):
        # Sessão com status_pagamento = Pago sem data_pagamento deve falhar na constraint
        from app.db.models import StatusPagamento
        s = AgendaSessao(
            id_paciente=uuid.uuid4(),
            data_hora_inicio=datetime(2026, 6, 12, 10, 0),
            data_hora_fim=datetime(2026, 6, 12, 11, 0),
            valor_sessao=Decimal("150.00"),
            status_pagamento=StatusPagamento.PAGO,
            data_pagamento=None
        )
        self.session.add(s)
        with self.assertRaises(IntegrityError):
            self.session.commit()

    def test_despesa_paga_sem_data_falha(self):
        # Despesa paga = True sem data_pagamento deve falhar na constraint
        from app.db.models import Despesa
        d = Despesa(
            descricao="Despesa Inconsistente",
            valor=Decimal("100.00"),
            data_vencimento=date(2026, 6, 12),
            mes_referencia="2026-06",
            paga=True,
            data_pagamento=None
        )
        self.session.add(d)
        with self.assertRaises(IntegrityError):
            self.session.commit()

if __name__ == "__main__":
    unittest.main()
