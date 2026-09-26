"""Agrega estados de invitación y propiedad de líneas en ofertas conjuntas."""

from alembic import op
import sqlalchemy as sa


revision = "b7c2d1e4f901"
down_revision = "af5d7513bb0f"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE estado_oferta_enum ADD VALUE IF NOT EXISTS 'pendiente'"
        )
    with op.batch_alter_table("oferta") as batch_op:
        batch_op.alter_column(
            "estado",
            existing_type=sa.Enum(
                "presentada", "modificada", "retirada", "adjudicada", "rechazada",
                name="estado_oferta_enum",
            ),
            type_=sa.Enum(
                "pendiente", "presentada", "modificada", "retirada", "adjudicada", "rechazada",
                name="estado_oferta_enum",
            ),
            existing_nullable=False,
        )

    with op.batch_alter_table("oferta_organizacion") as batch_op:
        batch_op.add_column(sa.Column("estado_participacion", sa.String(length=20), nullable=True))
    op.execute("UPDATE oferta_organizacion SET estado_participacion = 'aceptada'")
    with op.batch_alter_table("oferta_organizacion") as batch_op:
        batch_op.alter_column("estado_participacion", nullable=False, server_default="pendiente")

    with op.batch_alter_table("oferta_item") as batch_op:
        batch_op.add_column(sa.Column("organizacion_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_oferta_item_organizacion_id", ["organizacion_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_oferta_item_organizacion_id", "organizacion", ["organizacion_id"], ["id"]
        )
    op.execute(
        "UPDATE oferta_item SET organizacion_id = "
        "(SELECT organizacion_id FROM oferta_organizacion "
        "WHERE oferta_organizacion.oferta_id = oferta_item.oferta_id "
        "AND oferta_organizacion.rol_consorcio = 'lider')"
    )
    with op.batch_alter_table("oferta_item") as batch_op:
        batch_op.alter_column("organizacion_id", nullable=False)


def downgrade():
    with op.batch_alter_table("oferta_item") as batch_op:
        batch_op.drop_constraint("fk_oferta_item_organizacion_id", type_="foreignkey")
        batch_op.drop_index("ix_oferta_item_organizacion_id")
        batch_op.drop_column("organizacion_id")
    with op.batch_alter_table("oferta_organizacion") as batch_op:
        batch_op.drop_column("estado_participacion")