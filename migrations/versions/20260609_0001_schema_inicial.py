"""Schema inicial

Revision ID: 20260609_0001
Revises: None
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260609_0001"
down_revision = None
branch_labels = None
depends_on = None


tipo_contrato = postgresql.ENUM(
    "MENSAL", "AVULSO", name="tipocontrato", create_type=False
)
frequencia = postgresql.ENUM(
    "SEMANAL",
    "QUINZENAL",
    "MENSAL",
    "DUAS_SEMANA",
    "TRES_SEMANA",
    "PERSONALIZADO",
    name="frequencia",
    create_type=False,
)
dia_semana = postgresql.ENUM(
    "SEG", "TER", "QUA", "QUI", "SEX", "SAB", name="diasemana", create_type=False
)
status_paciente = postgresql.ENUM(
    "ATIVO", "INATIVO", name="statuspaciente", create_type=False
)
status_presenca = postgresql.ENUM(
    "AGENDADA",
    "CONFIRMADA",
    "REALIZADA",
    "FALTA",
    "CANCELADA",
    "CANCELOU_COM_ANTECEDENCIA",
    "CANCELOU_EM_CIMA",
    "IMPREVISTO",
    name="statuspresenca",
    create_type=False,
)
status_pagamento = postgresql.ENUM(
    "PENDENTE", "PAGO", "ATRASADO", "ISENTO", name="statuspagamento", create_type=False
)
perfil = postgresql.ENUM(
    "DONA", "SECRETARIA", "FINANCEIRO", "PROGRAMADOR", name="perfil", create_type=False
)
motivo_indisp = postgresql.ENUM(
    "FERIAS",
    "FERIADO_PROLONGADO",
    "IMPREVISTO",
    "OUTRO",
    name="motivoindisp",
    create_type=False,
)


def upgrade():
    bind = op.get_bind()
    for enum_type in (
        tipo_contrato,
        frequencia,
        dia_semana,
        status_paciente,
        status_presenca,
        status_pagamento,
        perfil,
        motivo_indisp,
    ):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "pacientes",
        sa.Column("id_paciente", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("telefone", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=True),
        sa.Column("data_nascimento", sa.Date(), nullable=False),
        sa.Column("tipo_contrato", tipo_contrato, nullable=False),
        sa.Column("valor_sessao", sa.Numeric(10, 2), nullable=False),
        sa.Column("frequencia", frequencia, nullable=False),
        sa.Column("dia_atendimento", dia_semana, nullable=True),
        sa.Column("dias_semana", sa.String(length=120), nullable=True),
        sa.Column("horario_atendimento", sa.String(length=400), nullable=False),
        sa.Column("sessoes_mes_custom", sa.Integer(), nullable=True),
        sa.Column("semana_do_mes", sa.Integer(), nullable=True),
        sa.Column("paridade_quinzenal", sa.String(length=10), nullable=True),
        sa.Column("status", status_paciente, nullable=False),
        sa.Column("ativo_desde", sa.Date(), nullable=True),
        sa.Column("em_avaliacao", sa.Boolean(), nullable=True),
        sa.Column("avaliacao_paga", sa.Boolean(), nullable=True),
        sa.Column("valor_avaliacao", sa.Numeric(10, 2), nullable=True),
        sa.Column("data_desativacao", sa.Date(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint("valor_sessao >= 0", name="ck_valor_sessao_pos"),
        sa.PrimaryKeyConstraint("id_paciente"),
    )

    op.create_table(
        "despesas",
        sa.Column("id_despesa", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("descricao", sa.String(length=120), nullable=False),
        sa.Column("valor", sa.Numeric(10, 2), nullable=False),
        sa.Column("data_vencimento", sa.Date(), nullable=False),
        sa.Column("mes_referencia", sa.String(length=7), nullable=False),
        sa.Column("paga", sa.Boolean(), nullable=True),
        sa.Column("data_pagamento", sa.Date(), nullable=True),
        sa.Column("recorrente", sa.Boolean(), nullable=True),
        sa.Column("dia_vencimento_mes", sa.Integer(), nullable=True),
        sa.Column("mes_fim", sa.String(length=7), nullable=True),
        sa.CheckConstraint("valor >= 0", name="ck_despesa_pos"),
        sa.PrimaryKeyConstraint("id_despesa"),
    )

    op.create_table(
        "usuarios",
        sa.Column("id_usuario", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("senha_hash", sa.Text(), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=True),
        sa.Column("perfil", perfil, nullable=False),
        sa.Column("reset_token", sa.String(length=80), nullable=True),
        sa.Column("reset_expira", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id_usuario"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "auditoria",
        sa.Column("id_log", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("quando", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("usuario", sa.String(length=50), nullable=True),
        sa.Column("acao", sa.String(length=120), nullable=True),
        sa.Column("detalhe", sa.String(length=300), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.PrimaryKeyConstraint("id_log"),
    )

    op.create_table(
        "indisponibilidades",
        sa.Column("id_indisp", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("dia_todo", sa.Boolean(), nullable=True),
        sa.Column("horario", sa.String(length=13), nullable=True),
        sa.Column("motivo", motivo_indisp, nullable=False),
        sa.Column("observacao", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("id_indisp"),
    )

    op.create_table(
        "agenda_sessoes",
        sa.Column("id_sessao", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_paciente", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_hora_inicio", sa.DateTime(), nullable=False),
        sa.Column("data_hora_fim", sa.DateTime(), nullable=False),
        sa.Column("status_presenca", status_presenca, nullable=False),
        sa.Column("status_pagamento", status_pagamento, nullable=False),
        sa.Column("confirmacao_enviada", sa.Boolean(), nullable=True),
        sa.Column("remarcada_de", sa.Date(), nullable=True),
        sa.Column("remarcada_motivo", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["id_paciente"], ["pacientes.id_paciente"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id_sessao"),
        sa.UniqueConstraint("data_hora_inicio", name="uq_horario_unico"),
    )

    op.create_table(
        "contratos_historico",
        sa.Column("id_contrato", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_paciente", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vigente_de", sa.Date(), nullable=False),
        sa.Column("vigente_ate", sa.Date(), nullable=True),
        sa.Column("frequencia", frequencia, nullable=False),
        sa.Column("valor_sessao", sa.Numeric(10, 2), nullable=False),
        sa.Column("dias_semana", sa.String(length=120), nullable=True),
        sa.Column("semana_do_mes", sa.Integer(), nullable=True),
        sa.Column("paridade_quinzenal", sa.String(length=10), nullable=True),
        sa.Column("sessoes_mes_custom", sa.Integer(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["id_paciente"], ["pacientes.id_paciente"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id_contrato"),
    )

    op.create_table(
        "excecoes_horario",
        sa.Column("id_excecao", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id_paciente", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tipo", sa.String(length=15), nullable=False),
        sa.Column("semana_do_mes", sa.Integer(), nullable=True),
        sa.Column("data_especifica", sa.Date(), nullable=True),
        sa.Column("dia_alvo", sa.String(length=20), nullable=False),
        sa.Column("horario_alvo", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["id_paciente"], ["pacientes.id_paciente"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id_excecao"),
    )


def downgrade():
    op.drop_table("excecoes_horario")
    op.drop_table("contratos_historico")
    op.drop_table("agenda_sessoes")
    op.drop_table("indisponibilidades")
    op.drop_table("auditoria")
    op.drop_table("usuarios")
    op.drop_table("despesas")
    op.drop_table("pacientes")

    bind = op.get_bind()
    for enum_type in reversed((
        tipo_contrato,
        frequencia,
        dia_semana,
        status_paciente,
        status_presenca,
        status_pagamento,
        perfil,
        motivo_indisp,
    )):
        enum_type.drop(bind, checkfirst=True)
