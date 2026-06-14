"""remove_legacy_backup_logs

Revision ID: 5d58247016ff
Revises: 1d6ce1c4554b
Create Date: 2026-06-14 16:29:55.478948
"""
from alembic import op
import sqlalchemy as sa



revision = '5d58247016ff'
down_revision = '1d6ce1c4554b'
branch_labels = None
depends_on = None


def upgrade():
    # Limpa as notificações e logs antigos de backup e teste de restauração
    op.execute("DELETE FROM sistema_status WHERE tipo IN ('backup', 'teste_restauracao');")


def downgrade():
    pass

