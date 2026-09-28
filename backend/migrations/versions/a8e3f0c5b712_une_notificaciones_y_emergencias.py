"""une_notificaciones_y_emergencias

Revision ID: a8e3f0c5b712
Revises: c2a7b9d4e601, ee1fbf644017
Create Date: 2026-09-28 18:00:00.000000

Migracion de union, sin cambios de esquema. Las ramas de notificaciones (EPIC-27) y de
migracion de emergencias (HU-58) salieron las dos de `f1a9c3e7d205` y tocan tablas
distintas, asi que el orden entre ellas no importa. Juntarlas aca deja una sola cabeza sin
reescribir el `down_revision` de ninguna: una base que ya aplico cualquiera de las dos ramas
sigue actualizandose con `flask db upgrade`.
"""

# revision identifiers, used by Alembic.
revision = "a8e3f0c5b712"
down_revision = ("c2a7b9d4e601", "ee1fbf644017")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
