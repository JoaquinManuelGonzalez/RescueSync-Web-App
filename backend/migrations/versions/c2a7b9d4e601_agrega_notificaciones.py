"""Agrega notificaciones compartidas por organización."""

from alembic import op
import sqlalchemy as sa


revision = "c2a7b9d4e601"
down_revision = "f1a9c3e7d205"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notificacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organizacion_id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=False),
        sa.Column("enlace", sa.String(length=500), nullable=False),
        sa.Column("leida", sa.Boolean(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["organizacion_id"], ["organizacion.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notificacion_organizacion_id", "notificacion", ["organizacion_id"])
    op.create_index("ix_notificacion_leida", "notificacion", ["leida"])


def downgrade():
    op.drop_index("ix_notificacion_leida", table_name="notificacion")
    op.drop_index("ix_notificacion_organizacion_id", table_name="notificacion")
    op.drop_table("notificacion")
