"""cantidades_enteras

Revision ID: b5d2f8a3c614
Revises: a8e3f0c5b712
Create Date: 2026-10-01 12:00:00.000000

Las cantidades de lotes, ofertas e inventario representan personas, raciones o unidades:
siempre son enteras. Estaban como `Numeric(12, 2)` y Postgres las devolvia como `50.00`.
Se redondean los valores existentes al pasar la columna a `Integer`.
"""

from alembic import op
import sqlalchemy as sa


revision = "b5d2f8a3c614"
down_revision = "a8e3f0c5b712"
branch_labels = None
depends_on = None


COLUMNAS = (
    ("lote_item", "cantidad_solicitada"),
    ("oferta_item", "cantidad_ofrecida"),
    ("inventario_item", "cantidad_disponible"),
)


def upgrade():
    for tabla, columna in COLUMNAS:
        with op.batch_alter_table(tabla) as batch_op:
            batch_op.alter_column(
                columna,
                existing_type=sa.Numeric(12, 2),
                type_=sa.Integer(),
                existing_nullable=False,
                postgresql_using=f"ROUND({columna})::integer",
            )


def downgrade():
    for tabla, columna in COLUMNAS:
        with op.batch_alter_table(tabla) as batch_op:
            batch_op.alter_column(
                columna,
                existing_type=sa.Integer(),
                type_=sa.Numeric(12, 2),
                existing_nullable=False,
            )
