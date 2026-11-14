"""agrega la fecha de adjudicacion a la convocatoria

El panel de auditoria mide tiempos y series mensuales desde el momento en que se adjudica.
Hasta ahora ese momento no quedaba registrado: `seleccionar_lineas` solo cambiaba estados.

Las convocatorias que ya estaban adjudicadas reciben una fecha aproximada, en este orden:
la ultima modificacion de sus ofertas adjudicadas (la seleccion es lo ultimo que las toca),
la fecha en que el Sistema Nacional evaluo la cobertura y, si no, el cierre de la ventana.

Revision ID: 4b8e2c6f1a93
Revises: 3d7f2a9c5e81
Create Date: 2026-11-12 22:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "4b8e2c6f1a93"
down_revision = "3d7f2a9c5e81"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "convocatoria",
        sa.Column("adjudicada_en", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE convocatoria
        SET adjudicada_en = COALESCE(
            (
                SELECT MAX(oferta.actualizado_en)
                FROM oferta
                WHERE oferta.convocatoria_id = convocatoria.id
                  AND oferta.estado = 'adjudicada'
            ),
            convocatoria.cobertura_evaluada_en,
            convocatoria.fecha_cierre
        )
        WHERE convocatoria.estado = 'adjudicada'
        """
    )


def downgrade():
    op.drop_column("convocatoria", "adjudicada_en")
