"""Modelagem de dados (SQLAlchemy) - Gestao Consultorio Psicologia. Banco: PostgreSQL."""
import uuid, enum
from sqlalchemy import (Column, String, Integer, Numeric, DateTime, Date, Enum,
                        ForeignKey, Boolean, Text, UniqueConstraint, CheckConstraint, func)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class TipoContrato(str, enum.Enum):
    MENSAL = "Mensal"
    AVULSO = "Avulso"


class Frequencia(str, enum.Enum):
    SEMANAL = "Semanal"
    QUINZENAL = "Quinzenal"
    MENSAL = "Mensal"
    DUAS_SEMANA = "2x por semana"
    TRES_SEMANA = "3x por semana"
    PERSONALIZADO = "Personalizado"


class DiaSemana(str, enum.Enum):
    SEG = "Segunda"
    TER = "Terca"
    QUA = "Quarta"
    QUI = "Quinta"
    SEX = "Sexta"


class StatusPaciente(str, enum.Enum):
    ATIVO = "Ativo"
    INATIVO = "Inativo"


class StatusPresenca(str, enum.Enum):
    AGENDADA = "Agendada"
    CONFIRMADA = "Confirmada"
    REALIZADA = "Realizada"
    FALTA = "Falta"
    CANCELADA = "Cancelada"


class StatusPagamento(str, enum.Enum):
    PENDENTE = "Pendente"
    PAGO = "Pago"
    ATRASADO = "Atrasado"


class Paciente(Base):
    __tablename__ = "pacientes"
    id_paciente = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String(150), nullable=False)
    telefone = Column(String(20), nullable=False)  # DDI+DDD ex: 5511999998888
    data_nascimento = Column(Date, nullable=False)
    tipo_contrato = Column(Enum(TipoContrato), nullable=False)
    valor_sessao = Column(Numeric(10, 2), nullable=False)
    frequencia = Column(Enum(Frequencia), nullable=False)
    dia_atendimento = Column(Enum(DiaSemana), nullable=False)
    horario_atendimento = Column(String(13), nullable=False)  # "14:00 - 15:00"
    # Usado so quando frequencia = Personalizado (sessoes previstas no mes)
    sessoes_mes_custom = Column(Integer, nullable=True)
    status = Column(Enum(StatusPaciente), nullable=False, default=StatusPaciente.ATIVO)
    criado_em = Column(DateTime, server_default=func.now())
    sessoes = relationship("AgendaSessao", back_populates="paciente",
                           cascade="all, delete-orphan")
    __table_args__ = (CheckConstraint("valor_sessao >= 0", name="ck_valor_sessao_pos"),)


class AgendaSessao(Base):
    __tablename__ = "agenda_sessoes"
    id_sessao = Column(Integer, primary_key=True, autoincrement=True)
    id_paciente = Column(UUID(as_uuid=True),
                         ForeignKey("pacientes.id_paciente", ondelete="CASCADE"),
                         nullable=False)
    data_hora_inicio = Column(DateTime, nullable=False)
    data_hora_fim = Column(DateTime, nullable=False)
    status_presenca = Column(Enum(StatusPresenca), nullable=False,
                             default=StatusPresenca.AGENDADA)
    status_pagamento = Column(Enum(StatusPagamento), nullable=False,
                              default=StatusPagamento.PENDENTE)
    confirmacao_enviada = Column(Boolean, default=False)
    paciente = relationship("Paciente", back_populates="sessoes")
    __table_args__ = (
        # Regra critica: nenhum horario de inicio duplicado.
        UniqueConstraint("data_hora_inicio", name="uq_horario_unico"),
        # Duracao de exatamente 1 hora (sintaxe PostgreSQL).
        CheckConstraint(
            "data_hora_fim = data_hora_inicio + interval '1 hour'",
            name="ck_duracao_1h").ddl_if(dialect="postgresql"),
    )


class Despesa(Base):
    __tablename__ = "despesas"
    id_despesa = Column(Integer, primary_key=True, autoincrement=True)
    descricao = Column(String(120), nullable=False)  # Aluguel, Internet, Impostos
    valor = Column(Numeric(10, 2), nullable=False)
    data_vencimento = Column(Date, nullable=False)
    mes_referencia = Column(String(7), nullable=False)  # YYYY-MM
    __table_args__ = (CheckConstraint("valor >= 0", name="ck_despesa_pos"),)


class Usuario(Base):
    """Login do sistema. Senha em hash bcrypt."""
    __tablename__ = "usuarios"
    id_usuario = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    nome = Column(String(120), nullable=False)
    senha_hash = Column(Text, nullable=False)
    ativo = Column(Boolean, default=True)
