"""Asocia cada lote publicado con su convocatoria."""

from alembic import op
import sqlalchemy as sa


revision = "e4b7c2a91d63"
down_revision = "d9a1e6b2c407"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("lote_necesidad") as batch_op:
        batch_op.add_column(sa.Column("convocatoria_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_lote_necesidad_convocatoria_id", ["convocatoria_id"])
        batch_op.create_foreign_key(
            "fk_lote_necesidad_convocatoria_id_convocatoria",
            "convocatoria",
            ["convocatoria_id"],
            ["id"],
        )
    op.execute(
        sa.text(
            "UPDATE lote_necesidad "
            "SET convocatoria_id = ("
            "SELECT convocatoria.id FROM convocatoria "
            "WHERE convocatoria.emergencia_id = lote_necesidad.emergencia_id "
            "ORDER BY convocatoria.fecha_inicio DESC, convocatoria.id DESC LIMIT 1"
            ") "
            "WHERE lote_necesidad.estado = 'en_convocatoria' "
            "AND EXISTS ("
            "SELECT 1 FROM convocatoria "
            "WHERE convocatoria.emergencia_id = lote_necesidad.emergencia_id"
            ")"
        )
    )


def downgrade():
    with op.batch_alter_table("lote_necesidad") as batch_op:
        batch_op.drop_constraint(
            "fk_lote_necesidad_convocatoria_id_convocatoria", type_="foreignkey"
        )
        batch_op.drop_index("ix_lote_necesidad_convocatoria_id")
        batch_op.drop_column("convocatoria_id")