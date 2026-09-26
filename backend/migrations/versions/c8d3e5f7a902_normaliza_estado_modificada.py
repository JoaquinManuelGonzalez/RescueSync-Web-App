"""Normaliza el estado obsoleto de ofertas modificadas."""

from alembic import op


revision = "c8d3e5f7a902"
down_revision = "b7c2d1e4f901"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE oferta SET estado = 'presentada' WHERE estado = 'modificada'")


def downgrade():
    pass