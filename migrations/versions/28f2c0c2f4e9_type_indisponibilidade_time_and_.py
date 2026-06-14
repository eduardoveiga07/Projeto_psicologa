"""type_indisponibilidade_time_and_auditoria

Revision ID: 28f2c0c2f4e9
Revises: a8de83320acd
Create Date: 2026-06-14 18:07:59.808076
"""
from alembic import op
import sqlalchemy as sa


revision = '28f2c0c2f4e9'
down_revision = 'a8de83320acd'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Adicionar novas colunas hora_inicio e hora_fim
    op.add_column('indisponibilidades', sa.Column('hora_inicio', sa.Time(), nullable=True))
    op.add_column('indisponibilidades', sa.Column('hora_fim', sa.Time(), nullable=True))

    # 2. Migrar os dados existentes parseando de forma robusta
    op.execute(sa.text("""
    DO $$
    DECLARE rec RECORD;
    BEGIN
        FOR rec IN SELECT id_indisp, horario FROM indisponibilidades
                   WHERE horario IS NOT NULL AND dia_todo = false LOOP
            BEGIN
                UPDATE indisponibilidades
                SET hora_inicio = CAST(split_part(rec.horario, ' - ', 1) AS TIME),
                    hora_fim = CAST(split_part(rec.horario, ' - ', 2) AS TIME)
                WHERE id_indisp = rec.id_indisp;
            EXCEPTION WHEN OTHERS THEN
                RAISE NOTICE 'Falha ao migrar id_indisp=% horario=%', rec.id_indisp, rec.horario;
            END;
        END LOOP;
    END $$;
    """))

    # 3. Remover a coluna antiga
    op.drop_column('indisponibilidades', 'horario')

    # 4. Adicionar a CheckConstraint ck_indisp_horario
    op.create_check_constraint(
        'ck_indisp_horario',
        'indisponibilidades',
        '(hora_inicio IS NULL AND hora_fim IS NULL) OR (hora_inicio IS NOT NULL AND hora_fim IS NOT NULL AND hora_fim > hora_inicio)'
    )

    # 5. Alterar Auditoria.detalhe para TEXT
    op.alter_column('auditoria', 'detalhe', type_=sa.Text(), existing_type=sa.String(length=300))


def downgrade():
    # 1. Recriar a coluna antiga horario
    op.add_column('indisponibilidades', sa.Column('horario', sa.String(length=13), nullable=True))

    # 2. Re-popular a coluna horario a partir de hora_inicio e hora_fim
    op.execute(sa.text("""
    UPDATE indisponibilidades
    SET horario = to_char(hora_inicio, 'HH24:MI') || ' - ' || to_char(hora_fim, 'HH24:MI')
    WHERE hora_inicio IS NOT NULL AND hora_fim IS NOT NULL;
    """))

    # 3. Remover a CheckConstraint
    op.drop_constraint('ck_indisp_horario', 'indisponibilidades')

    # 4. Remover as novas colunas
    op.drop_column('indisponibilidades', 'hora_inicio')
    op.drop_column('indisponibilidades', 'hora_fim')

    # 5. Alterar Auditoria.detalhe de volta para String(300)
    op.alter_column('auditoria', 'detalhe', type_=sa.String(length=300), existing_type=sa.Text())
