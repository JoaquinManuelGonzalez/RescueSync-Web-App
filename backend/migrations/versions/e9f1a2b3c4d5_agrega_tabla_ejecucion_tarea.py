"""agrega tabla ejecucion_tarea para seguimiento de tareas de ONGs

Revision ID: e9f1a2b3c4d5
Revises: 8c4e1a7d93b2
Create Date: 2026-10-31 21:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "e9f1a2b3c4d5"
down_revision = "8c4e1a7d93b2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ejecucion_tarea",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("emergencia_id", sa.Integer(), nullable=False),
        sa.Column("oferta_id", sa.Integer(), nullable=False),
        sa.Column("organizacion_id", sa.Integer(), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "en_progreso",
                "finalizada",
                "cancelada",
                name="estado_tarea_ejecucion_enum",
            ),
            nullable=False,
            server_default="en_progreso",
        ),
        sa.Column(
            "fecha_inicio",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("fecha_fin", sa.DateTime(timezone=True), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["emergencia_id"], ["emergencia.id"], name=op.f("fk_ejecucion_tarea_emergencia_id")
        ),
        sa.ForeignKeyConstraint(
            ["oferta_id"], ["oferta.id"], name=op.f("fk_ejecucion_tarea_oferta_id")
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id"],
            ["organizacion.id"],
            name=op.f("fk_ejecucion_tarea_organizacion_id"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], name=op.f("fk_ejecucion_tarea_usuario_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ejecucion_tarea")),
    )

    with op.batch_alter_table("ejecucion_tarea", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_ejecucion_tarea_emergencia_id"), ["emergencia_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_ejecucion_tarea_oferta_id"), ["oferta_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_ejecucion_tarea_organizacion_id"), ["organizacion_id"], unique=False
        )


def downgrade():
    with op.batch_alter_table("ejecucion_tarea", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ejecucion_tarea_organizacion_id"))
        batch_op.drop_index(batch_op.f("ix_ejecucion_tarea_oferta_id"))
        batch_op.drop_index(batch_op.f("ix_ejecucion_tarea_emergencia_id"))

    op.drop_table("ejecucion_tarea")
    sa.Enum(name="estado_tarea_ejecucion_enum").drop(op.get_bind(), checkfirst=True)
