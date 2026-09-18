"""Registro de los modulos de dominio.

Cada modulo se crea como `app/modulos/<nombre>/` con `rutas.py`, `servicios.py`, `modelos.py`
y `formularios.py`.
"""

from __future__ import annotations

from flask import Flask


def importar_modelos() -> None:
    """Importa los modelos de todos los modulos.

    Alembic solo genera migraciones para los modelos que fueron importados: un modelo que
    nadie importa es invisible para `flask db migrate --autogenerate`. Por eso los imports
    se centralizan aca y los llama `migrations/env.py`.

    Todavia vacio: el esquema de dominio esta en definicion.
    """
    # from app.modulos.usuarios_roles import modelos as _usuarios_roles  # noqa: F401
    # from app.modulos.emergencias import modelos as _emergencias  # noqa: F401
    return


def registrar_modulos(app: Flask) -> None:
    """Registra el blueprint de cada modulo de dominio en la aplicacion.

    Todavia vacio: los modulos se crean en las epicas de dominio. El orden de registro no
    importa; el que importa es el de la cadena de dependencias de arriba.
    """
    importar_modelos()

    # from app.modulos.usuarios_roles.rutas import blueprint as usuarios_roles
    # app.register_blueprint(usuarios_roles, url_prefix="/usuarios-roles")
    return
