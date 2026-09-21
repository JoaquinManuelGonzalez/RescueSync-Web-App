"""agrega_datos_de_sesion_y_bloqueo_a_usuarios

Revision ID: a1c4f7b93d20
Revises: 6691e7d89ae4
Create Date: 2026-09-21 19:40:00.000000

Agrega a `usuarios` las columnas que sostienen el control de acceso de la EPIC-17:
bloqueo por intentos fallidos, ultimo acceso, cambio obligatorio de contrasena y la marca
de actualizacion. Suma ademas el indice unico funcional sobre lower(email), que Alembic no
detecta por autogenerate y va escrito a mano.

Las columnas NOT NULL llevan server_default para que las filas ya existentes queden con un
valor valido al aplicar el ALTER TABLE.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1c4f7b93d20"
down_revision = "6691e7d89ae4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "usuarios",
        sa.Column(
            "debe_cambiar_contrasena",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment=(
                "True obliga a cambiar la contraseña antes de operar. Las cuentas creadas por "
                "el administrador nacen así, para que la clave inicial no quede en uso."
            ),
        ),
    )
    op.add_column(
        "usuarios",
        sa.Column(
            "intentos_fallidos",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Intentos de ingreso fallidos consecutivos. Se resetea al ingresar bien.",
        ),
    )
    op.add_column(
        "usuarios",
        sa.Column(
            "bloqueado_hasta",
            sa.DateTime(timezone=True),
            nullable=True,
            comment=(
                "Momento hasta el cual la cuenta no puede iniciar sesión. NULL si no está "
                "bloqueada."
            ),
        ),
    )
    op.add_column(
        "usuarios",
        sa.Column(
            "ultimo_acceso_en",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Último ingreso exitoso.",
        ),
    )
    op.add_column(
        "usuarios",
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.alter_column(
        "usuarios",
        "email",
        existing_type=sa.String(length=254),
        existing_nullable=False,
        comment="Clave natural, siempre normalizada a minúsculas. Identificador del login.",
        existing_comment="Clave natural. Se usa como identificador en el login.",
    )
    # Indice funcional: el UNIQUE de la columna distingue mayusculas y dejaria entrar
    # "Juan@x.com" y "juan@x.com" como dos cuentas distintas.
    op.create_index(
        "uq_usuarios_email_normalizado",
        "usuarios",
        [sa.text("lower(email)")],
        unique=True,
    )


def downgrade():
    op.drop_index("uq_usuarios_email_normalizado", table_name="usuarios")
    op.alter_column(
        "usuarios",
        "email",
        existing_type=sa.String(length=254),
        existing_nullable=False,
        comment="Clave natural. Se usa como identificador en el login.",
        existing_comment="Clave natural, siempre normalizada a minúsculas. Identificador del login.",
    )
    op.drop_column("usuarios", "actualizado_en")
    op.drop_column("usuarios", "ultimo_acceso_en")
    op.drop_column("usuarios", "bloqueado_hasta")
    op.drop_column("usuarios", "intentos_fallidos")
    op.drop_column("usuarios", "debe_cambiar_contrasena")
