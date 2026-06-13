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
    SEG = "Segunda-feira"
    TER = "Terça-feira"
    QUA = "Quarta-feira"
    QUI = "Quinta-feira"
    SEX = "Sexta-feira"
    SAB = "Sábado"


class StatusPaciente(str, enum.Enum):
    ATIVO = "Ativo"
    INATIVO = "Inativo"


class StatusPresenca(str, enum.Enum):
    AGENDADA = "Agendada"
    CONFIRMADA = "Confirmada"
    REALIZADA = "Realizada"
    FALTA = "Falta"
    CANCELADA = "Cancelada"
    CANCELOU_COM_ANTECEDENCIA = "Cancelou +24h (isento)"
    CANCELOU_EM_CIMA = "Cancelou -24h (cobra)"
    IMPREVISTO = "Imprevisto/Emergência (isento)"


class StatusPagamento(str, enum.Enum):
    PENDENTE = "Pendente"
    PAGO = "Pago"
    ATRASADO = "Atrasado"
    ISENTO = "Isento"


class Paciente(Base):
    __tablename__ = "pacientes"
    id_paciente = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String(150), nullable=False)
    telefone = Column(String(20), nullable=False)  # DDI+DDD ex: 5511999998888
    email = Column(String(150), nullable=True)  # para NF/comunicação
    data_nascimento = Column(Date, nullable=False)
    tipo_contrato = Column(Enum(TipoContrato), nullable=False)
    valor_sessao = Column(Numeric(10, 2), nullable=False)
    frequencia = Column(Enum(Frequencia), nullable=False)
    dia_atendimento = Column(Enum(DiaSemana), nullable=True)
    # Dias de atendimento separados por virgula, ex: "Segunda-feira,Quarta-feira"
    dias_semana = Column(String(120), nullable=True)
    horario_atendimento = Column(String(400), nullable=False)  # "Dia=HH:MM - HH:MM,..."
    # Usado so quando frequencia = Personalizado (sessoes previstas no mes)
    sessoes_mes_custom = Column(Integer, nullable=True)
    # Para freq Mensal: qual semana do mes (1=1a, 2=2a, 3=3a, 4=4a, 5=última)
    semana_do_mes = Column(Integer, nullable=True)
    # Para freq Quinzenal: 'par' ou 'impar' (paridade da semana ISO)
    paridade_quinzenal = Column(String(10), nullable=True)
    status = Column(Enum(StatusPaciente), nullable=False, default=StatusPaciente.ATIVO)
    # Data em que se tornou paciente ativo (para nao contar faturamento antes disso).
    ativo_desde = Column(Date, nullable=True)
    # Pacientes em avaliacao inicial (1-2 sessoes, nao recorrente ainda).
    em_avaliacao = Column(Boolean, default=False)
    avaliacao_paga = Column(Boolean, default=False)
    valor_avaliacao = Column(Numeric(10, 2), nullable=True)
    data_desativacao = Column(Date, nullable=True)  # para auto-exclusão após 2 anos
    criado_em = Column(DateTime, server_default=func.now())
    sessoes = relationship("AgendaSessao", back_populates="paciente",
                           cascade="all, delete-orphan")
    __table_args__ = (CheckConstraint("valor_sessao >= 0", name="ck_valor_sessao_pos"),)


class AgendaSessao(Base):
    __tablename__ = "agenda_sessoes"
    id_sessao = Column(Integer, primary_key=True, autoincrement=True)
    id_paciente = Column(UUID(as_uuid=True),
                         ForeignKey("pacientes.id_paciente", ondelete="CASCADE"),
                         nullable=False, index=True)
    data_hora_inicio = Column(DateTime, nullable=False, index=True)
    data_hora_fim = Column(DateTime, nullable=False)
    status_presenca = Column(Enum(StatusPresenca), nullable=False,
                             default=StatusPresenca.AGENDADA, index=True)
    status_pagamento = Column(Enum(StatusPagamento), nullable=False,
                              default=StatusPagamento.PENDENTE, index=True)
    confirmacao_enviada = Column(Boolean, default=False)
    # Quando uma sessao foi remarcada por causa de feriado/bloqueio,
    # registramos aqui a data original que foi "pulada" e o motivo.
    remarcada_de = Column(Date, nullable=True)
    remarcada_motivo = Column(String(120), nullable=True)
    
    # Novas colunas para sessões reais persistidas
    valor_sessao = Column(Numeric(10, 2), nullable=True)
    recorrente = Column(Boolean, nullable=False, default=True)
    
    # Data do pagamento real
    data_pagamento = Column(Date, nullable=True)

    # Comprovante de pagamento — metadados completos para auditoria/LGPD
    comprovante_nome = Column(String(200), nullable=True)        # nome gerado internamente (sem path)
    comprovante_nome_original = Column(String(300), nullable=True)  # nome original do arquivo enviado
    comprovante_mime = Column(String(100), nullable=True)          # ex: application/pdf, image/jpeg
    comprovante_tamanho = Column(Integer, nullable=True)           # tamanho em bytes
    comprovante_enviado_em = Column(DateTime, nullable=True)       # data/hora do upload
    
    paciente = relationship("Paciente", back_populates="sessoes")
    __table_args__ = (
        CheckConstraint("data_hora_fim > data_hora_inicio", name="ck_sessoes_datas"),
        CheckConstraint("valor_sessao >= 0", name="ck_valor_sessao_sess_pos"),
        UniqueConstraint("id_paciente", "data_hora_inicio", name="uq_paciente_horario"),
    )


class ContratoHistorico(Base):
    """Snapshot do contrato do paciente em um periodo de vigencia.
    Toda mudanca de frequencia/dias/valor/semana_do_mes/paridade fecha o
    registro vigente (vigente_ate = dia anterior a mudanca) e abre um novo
    (vigente_de = data da mudanca, vigente_ate = NULL).
    O financeiro consulta o registro vigente no mes para calcular previsto."""
    __tablename__ = "contratos_historico"
    id_contrato = Column(Integer, primary_key=True, autoincrement=True)
    id_paciente = Column(UUID(as_uuid=True),
        ForeignKey("pacientes.id_paciente", ondelete="CASCADE"),
        nullable=False)
    vigente_de = Column(Date, nullable=False)
    vigente_ate = Column(Date, nullable=True)  # NULL = ainda vigente
    frequencia = Column(Enum(Frequencia), nullable=False)
    valor_sessao = Column(Numeric(10, 2), nullable=False)
    dias_semana = Column(String(120), nullable=True)
    semana_do_mes = Column(Integer, nullable=True)
    paridade_quinzenal = Column(String(10), nullable=True)
    sessoes_mes_custom = Column(Integer, nullable=True)
    criado_em = Column(DateTime, server_default=func.now())
    __table_args__ = (
        CheckConstraint("vigente_ate >= vigente_de OR vigente_ate IS NULL", name="ck_contratos_datas"),
        CheckConstraint("valor_sessao >= 0", name="ck_valor_sessao_hist_pos"),
    )


class Despesa(Base):
    __tablename__ = "despesas"
    id_despesa = Column(Integer, primary_key=True, autoincrement=True)
    descricao = Column(String(120), nullable=False)
    valor = Column(Numeric(10, 2), nullable=False)
    data_vencimento = Column(Date, nullable=False)
    mes_referencia = Column(String(7), nullable=False)  # YYYY-MM
    paga = Column(Boolean, default=False)
    data_pagamento = Column(Date, nullable=True)
    # Recorrencia: se True, gera para meses seguintes automaticamente
    recorrente = Column(Boolean, default=False)
    dia_vencimento_mes = Column(Integer, nullable=True)  # ex: dia 5 todo mês
    # Coluna mes_fim opcional para despesas fixas com janela definida
    mes_fim = Column(String(7), nullable=True)

    # Comprovante da despesa — metadados completos para auditoria/LGPD
    comprovante_nome = Column(String(200), nullable=True)        # nome gerado internamente (sem path)
    comprovante_nome_original = Column(String(300), nullable=True)  # nome original do arquivo enviado
    comprovante_mime = Column(String(100), nullable=True)          # ex: application/pdf, image/jpeg
    comprovante_tamanho = Column(Integer, nullable=True)           # tamanho em bytes
    comprovante_enviado_em = Column(DateTime, nullable=True)       # data/hora do upload
    __table_args__ = (CheckConstraint("valor >= 0", name="ck_despesa_pos"),)


class Perfil(str, enum.Enum):
    DONA = "Dona"                # ve tudo + gerencia usuarios
    SECRETARIA = "Secretaria"    # cadastro, agenda, pagamentos (sem financeiro)
    FINANCEIRO = "Financeiro"    # so financeiro/pagamentos (braco direito)
    PROGRAMADOR = "Programador"  # tudo + auditoria


class Usuario(Base):
    """Login do sistema. Senha em hash bcrypt."""
    __tablename__ = "usuarios"
    id_usuario = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    nome = Column(String(120), nullable=False)
    senha_hash = Column(Text, nullable=False)
    email = Column(String(150), nullable=True)
    ativo = Column(Boolean, default=True)
    perfil = Column(Enum(Perfil), nullable=False, default=Perfil.SECRETARIA)
    reset_token = Column(String(80), nullable=True)
    reset_expira = Column(DateTime, nullable=True)
    tentativas_login = Column(Integer, default=0, nullable=False)
    bloqueado_ate = Column(DateTime, nullable=True)
    trocar_senha_proximo_login = Column(Boolean, default=False, nullable=False)
    __table_args__ = (
        CheckConstraint("tentativas_login >= 0", name="ck_tentativas_pos"),
    )


class Auditoria(Base):
    """Trilha de auditoria: eventos criticos (login, alteracoes sensiveis)."""
    __tablename__ = "auditoria"
    id_log = Column(Integer, primary_key=True, autoincrement=True)
    quando = Column(DateTime, server_default=func.now())
    usuario = Column(String(50))      # quem
    acao = Column(String(120))        # ex: LOGIN, EDITOU_PACIENTE
    detalhe = Column(String(300))     # descricao sem dados sensiveis
    ip = Column(String(45))           # IPv4/IPv6


class MotivoIndisp(str, enum.Enum):
    FERIAS = "Férias"
    FERIADO_PROLONGADO = "Prolongou feriado"
    IMPREVISTO = "Imprevisto/Emergência"
    OUTRO = "Outro"


class Indisponibilidade(Base):
    """Datas/horarios em que a psicologa NAO atende (ferias, imprevistos)."""
    __tablename__ = "indisponibilidades"
    id_indisp = Column(Integer, primary_key=True, autoincrement=True)
    data = Column(Date, nullable=False)
    dia_todo = Column(Boolean, default=True)
    horario = Column(String(13), nullable=True)  # se nao for dia todo
    motivo = Column(Enum(MotivoIndisp), nullable=False, default=MotivoIndisp.OUTRO)
    observacao = Column(String(200), nullable=True)


class SistemaStatus(Base):
    """Status de rotinas do sistema (backups, restores)."""
    __tablename__ = "sistema_status"
    id_status = Column(Integer, primary_key=True, autoincrement=True)
    tipo = Column(String(30), nullable=False)  # 'backup' ou 'teste_restauracao'
    quando = Column(DateTime, server_default=func.now())
    status = Column(String(20), nullable=False)  # 'sucesso' ou 'falha'
    detalhe = Column(Text, nullable=True)


class FechamentoMensal(Base):
    """Fechamento financeiro mensal para bloquear edições retrógradas."""
    __tablename__ = "fechamentos_mensais"
    id_fechamento = Column(Integer, primary_key=True, autoincrement=True)
    mes_referencia = Column(String(7), unique=True, nullable=False)  # 'YYYY-MM'
    fechado_em = Column(DateTime, server_default=func.now())
    fechado_por = Column(String(50), nullable=False)  # Username do admin
    total_recebido = Column(Numeric(12, 2), nullable=False, default=0.0)
    total_despesas = Column(Numeric(12, 2), nullable=False, default=0.0)
