"""Agrega el estado persistido de cobertura nacional a las convocatorias."""

import sqlalchemy as sa
from alembic import op


revision = "c4f6a8b2d901"
down_revision = "8c4e1a7d93b2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "convocatoria",
        sa.Column(
            "cobertura_completa",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "convocatoria",
        sa.Column("cobertura_evaluada_en", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("convocatoria", "cobertura_evaluada_en")
    op.drop_column("convocatoria", "cobertura_completa")
