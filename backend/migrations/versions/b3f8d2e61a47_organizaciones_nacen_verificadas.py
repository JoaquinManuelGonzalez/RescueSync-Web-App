"""organizaciones_nacen_verificadas

Revision ID: b3f8d2e61a47
Revises: e7a2c5d91f30
Create Date: 2026-09-26 12:30:00.000000

EPIC-19: las organizaciones que se cargan en RescueSync ya fueron verificadas por el Sistema
Nacional, asi que `organizacion.estado_verificacion` pasa a nacer `verificada`. Las filas que
quedaron `sin_verificar` con la regla anterior se marcan `verificada`; las `rechazada` no se tocan.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b3f8d2e61a47"
down_revision = "e7a2c5d91f30"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "organizacion",
        "estado_verificacion",
        server_default="verificada",
        comment="Resultado de la validación contra el Sistema Nacional.",
        existing_comment="Resultado de la validación contra el Sistema Nacional (Entrega 3).",
        existing_nullable=False,
    )
    op.execute(
        sa.text(
            "UPDATE organizacion SET estado_verificacion = 'verificada' "
            "WHERE estado_verificacion = 'sin_verificar'"
        )
    )


def downgrade():
    # Solo se revierte el valor por defecto: no hay forma de saber que filas estaban
    # `sin_verificar` antes del upgrade.
    op.alter_column(
        "organizacion",
        "estado_verificacion",
        server_default="sin_verificar",
        comment="Resultado de la validación contra el Sistema Nacional (Entrega 3).",
        existing_comment="Resultado de la validación contra el Sistema Nacional.",
        existing_nullable=False,
    )
