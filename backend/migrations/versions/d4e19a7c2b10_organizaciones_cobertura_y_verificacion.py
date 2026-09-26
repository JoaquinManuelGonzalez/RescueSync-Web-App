"""organizaciones_cobertura_y_verificacion

Revision ID: d4e19a7c2b10
Revises: af5d7513bb0f
Create Date: 2026-09-25 19:00:00.000000

EPIC-19, gestion de organizaciones de la red:

- Tabla `organizacion_zona_cobertura`: una fila por provincia (y localidad opcional) en la que
  opera cada organizacion.
- `organizacion.estado_verificacion`: resultado de la validacion contra el Sistema Nacional, que
  completa la Entrega 3. Las filas existentes quedan `sin_verificar`.
- `organizacion.actualizado_en`: marca de la ultima modificacion.
- Indice unico funcional sobre lower(nombre), que autogenerate no detecta y va escrito a mano
  (mismo criterio que `uq_usuarios_email_normalizado`).

Si otra rama agrega una migracion sobre `af5d7513bb0f` (por ejemplo la de consorcios), quien
mergee segundo tiene que apuntar su `down_revision` a la cabeza vigente: `flask db heads` tiene
que devolver una sola.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d4e19a7c2b10"
down_revision = "af5d7513bb0f"
branch_labels = None
depends_on = None

estado_verificacion_enum = sa.Enum(
    "sin_verificar", "verificada", "rechazada", name="estado_verificacion_enum"
)


def upgrade():
    op.create_table(
        "organizacion_zona_cobertura",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organizacion_id", sa.Integer(), nullable=False),
        sa.Column(
            "provincia",
            sa.String(length=60),
            nullable=False,
            comment="Nombre oficial de la provincia (lista cerrada de geografia.PROVINCIAS).",
        ),
        sa.Column(
            "localidad",
            sa.String(length=150),
            nullable=True,
            comment="Partido o localidad. NULL significa toda la provincia.",
        ),
        sa.ForeignKeyConstraint(["organizacion_id"], ["organizacion.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organizacion_id",
            "provincia",
            "localidad",
            name="uq_organizacion_zona_cobertura",
        ),
    )
    op.create_index(
        "ix_organizacion_zona_cobertura_organizacion_id",
        "organizacion_zona_cobertura",
        ["organizacion_id"],
    )
    op.create_index(
        "ix_organizacion_zona_cobertura_provincia",
        "organizacion_zona_cobertura",
        ["provincia"],
    )

    estado_verificacion_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "organizacion",
        sa.Column(
            "estado_verificacion",
            estado_verificacion_enum,
            server_default="sin_verificar",
            nullable=False,
            comment="Resultado de la validación contra el Sistema Nacional (Entrega 3).",
        ),
    )
    op.add_column(
        "organizacion",
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # El UNIQUE de la columna distingue mayusculas y dejaria convivir "Cruz Solidaria" y
    # "cruz solidaria" como dos organizaciones distintas.
    op.create_index(
        "uq_organizacion_nombre_normalizado",
        "organizacion",
        [sa.text("lower(nombre)")],
        unique=True,
    )


def downgrade():
    op.drop_index("uq_organizacion_nombre_normalizado", table_name="organizacion")
    op.drop_column("organizacion", "actualizado_en")
    op.drop_column("organizacion", "estado_verificacion")
    estado_verificacion_enum.drop(op.get_bind(), checkfirst=True)

    op.drop_index(
        "ix_organizacion_zona_cobertura_provincia", table_name="organizacion_zona_cobertura"
    )
    op.drop_index(
        "ix_organizacion_zona_cobertura_organizacion_id",
        table_name="organizacion_zona_cobertura",
    )
    op.drop_table("organizacion_zona_cobertura")
