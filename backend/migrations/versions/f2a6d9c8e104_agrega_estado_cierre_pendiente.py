"""agrega estado de cierre pendiente a las tareas de ejecución

Revision ID: f2a6d9c8e104
Revises: e9f1a2b3c4d5
Create Date: 2026-11-05 21:30:00.000000
"""

from alembic import op

revision = "f2a6d9c8e104"
down_revision = "e9f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE estado_tarea_ejecucion_enum ADD VALUE IF NOT EXISTS 'cierre_pendiente'"
            )
    op.execute(
        "UPDATE ejecucion_tarea "
        "SET estado = 'cierre_pendiente', fecha_fin = NULL "
        "WHERE estado = 'finalizada'"
    )
    op.execute("UPDATE ejecucion_tarea SET fecha_fin = NULL WHERE estado = 'cierre_pendiente'")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "UPDATE ejecucion_tarea "
            "SET estado = 'en_progreso', fecha_fin = NULL "
            "WHERE estado = 'cierre_pendiente'"
        )
