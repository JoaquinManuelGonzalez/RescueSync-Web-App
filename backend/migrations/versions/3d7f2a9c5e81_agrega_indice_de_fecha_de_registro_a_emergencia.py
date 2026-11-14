"""agrega indice sobre la fecha de registro de la emergencia

El panel de auditoria filtra las emergencias por periodo de registro (`creado_en`).

Revision ID: 3d7f2a9c5e81
Revises: 314b662d0456
Create Date: 2026-11-02 21:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "3d7f2a9c5e81"
down_revision = "314b662d0456"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("emergencia") as batch_op:
        batch_op.create_index("ix_emergencia_creado_en", ["creado_en"], unique=False)


def downgrade():
    with op.batch_alter_table("emergencia") as batch_op:
        batch_op.drop_index("ix_emergencia_creado_en")
