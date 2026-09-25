"""agrega_cobertura_nacional

Revision ID: e7a2c5d91f30
Revises: d4e19a7c2b10
Create Date: 2026-09-25 19:40:00.000000

EPIC-19: `organizacion.cobertura_nacional` marca a las organizaciones que operan en todo el pais,
para no tener que cargar las 24 jurisdicciones una por una. Cuando esta en true, reemplaza a las
filas de `organizacion_zona_cobertura`. Las organizaciones existentes quedan en false.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e7a2c5d91f30"
down_revision = "d4e19a7c2b10"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "organizacion",
        sa.Column(
            "cobertura_nacional",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="True si opera en todo el país: reemplaza a las zonas de cobertura.",
        ),
    )


def downgrade():
    op.drop_column("organizacion", "cobertura_nacional")
