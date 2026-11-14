"""merge adjudicada_en y decision de cobertura

Revision ID: 45558706fd3d
Revises: 4b8e2c6f1a93, f8a6c2d914e0
Create Date: 2026-11-14 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "45558706fd3d"
down_revision = ("4b8e2c6f1a93", "f8a6c2d914e0")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
