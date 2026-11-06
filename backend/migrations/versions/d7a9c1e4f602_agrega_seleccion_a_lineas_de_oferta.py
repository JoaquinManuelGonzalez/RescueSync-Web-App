"""Agrega la selección municipal a las líneas de oferta."""

import sqlalchemy as sa
from alembic import op


revision = "d7a9c1e4f602"
down_revision = "c4f6a8b2d901"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "oferta_item",
        sa.Column(
            "seleccionada",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade():
    op.drop_column("oferta_item", "seleccionada")
