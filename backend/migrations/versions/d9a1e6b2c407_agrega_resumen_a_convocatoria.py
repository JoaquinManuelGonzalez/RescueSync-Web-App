"""Agrega a convocatoria el resumen de situación publicado."""

from alembic import op
import sqlalchemy as sa


revision = "d9a1e6b2c407"
down_revision = "f1a9c3e7d205"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("convocatoria", sa.Column("resumen_situacion", sa.Text(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE convocatoria "
            "SET resumen_situacion = ("
            "SELECT emergencia.descripcion FROM emergencia "
            "WHERE emergencia.id = convocatoria.emergencia_id"
            ")"
        )
    )
    with op.batch_alter_table("convocatoria") as batch_op:
        batch_op.alter_column("resumen_situacion", existing_type=sa.Text(), nullable=False)


def downgrade():
    with op.batch_alter_table("convocatoria") as batch_op:
        batch_op.drop_column("resumen_situacion")
