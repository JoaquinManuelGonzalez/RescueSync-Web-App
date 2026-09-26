"""une_ofertas_conjuntas_y_organizaciones

Revision ID: f1a9c3e7d205
Revises: c8d3e5f7a902, b3f8d2e61a47
Create Date: 2026-09-26 14:00:00.000000

Migracion de union, sin cambios de esquema. Las ramas de consorcios (EPIC-21, ofertas conjuntas)
y de gestion de organizaciones (EPIC-19) salieron las dos de `af5d7513bb0f` y tocan tablas
distintas, asi que el orden entre ellas no importa. Juntarlas aca deja una sola cabeza sin
reescribir el `down_revision` de ninguna: una base que ya aplico cualquiera de las dos ramas
sigue actualizandose con `flask db upgrade`.
"""

# revision identifiers, used by Alembic.
revision = "f1a9c3e7d205"
down_revision = ("c8d3e5f7a902", "b3f8d2e61a47")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
