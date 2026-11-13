"""Persiste el porcentaje evaluado y la decisión sobre cobertura insuficiente."""

import sqlalchemy as sa
from alembic import op


revision = "f8a6c2d914e0"
down_revision = "314b662d0456"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "convocatoria",
        sa.Column(
            "porcentaje_cobertura",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
    )
    op.add_column(
        "convocatoria",
        sa.Column(
            "decision_cobertura",
            sa.String(length=30),
            nullable=False,
            server_default="pendiente",
        ),
    )


def downgrade():
    op.drop_column("convocatoria", "decision_cobertura")
    op.drop_column("convocatoria", "porcentaje_cobertura")
