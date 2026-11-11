"""merge adjudicacion y cierre ong

Revision ID: 314b662d0456
Revises: d7a9c1e4f602, f2a6d9c8e104
Create Date: 2026-11-09 01:13:38.050494

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "314b662d0456"
down_revision = ("d7a9c1e4f602", "f2a6d9c8e104")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
