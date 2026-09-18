"""linea base del esquema

Esta revision no crea ninguna tabla, y eso es deliberado.

El esquema de dominio de RescueSync todavia esta en definicion. Lo que esta revision aporta
es la tabla de control `alembic_version`: al aplicarla, la base queda registrada en la ultima
revision, que es lo que permite distinguir una base migrada de una base vacia. De eso
dependen el arranque automatico de migraciones y la verificacion que hace `flask seed` antes
de insertar nada.

La primera revision con tablas se genera cuando existan los modelos, con:

    docker compose exec web flask db migrate -m "descripcion del cambio"

Revision ID: 0001
Revises:
Create Date: 2026-09-17

"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Sin cambios de esquema: solo deja la base sellada en esta revision."""
    pass


def downgrade():
    """Sin cambios que revertir."""
    pass
