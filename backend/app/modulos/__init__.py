"""Registro de los modulos de dominio.

Cada modulo se crea como `app/modulos/<nombre>/` con `rutas.py`, `servicios.py`, `modelos.py`
y `formularios.py`.
"""

from __future__ import annotations

# pyrefly: ignore [missing-import]
from flask import Flask


def importar_modelos() -> None:
    """Importa los modelos de todos los modulos.

    Alembic solo genera migraciones para los modelos que fueron importados: un modelo que
    nadie importa es invisible para `flask db migrate --autogenerate`. Por eso los imports
    se centralizan aca y los llama `migrations/env.py`.

    El orden importa: los modulos sin FK van primero para que SQLAlchemy resuelva
    las relaciones en el orden correcto.
    """
    from app.modulos.convocatorias import modelos as _convocatorias  # noqa: F401
    from app.modulos.emergencias import modelos as _emergencias  # noqa: F401
    from app.modulos.ofertas import modelos as _ofertas  # noqa: F401
    from app.modulos.organizaciones import modelos as _organizaciones  # noqa: F401
    from app.modulos.usuarios_roles import modelos as _usuarios_roles  # noqa: F401
    # from app.modulos.adjudicaciones import modelos as _adjudicaciones  # noqa: F401


def registrar_modulos(app: Flask) -> None:
    """Registra el blueprint de cada modulo de dominio en la aplicacion.

    El orden de registro no importa; el que importa es el de la cadena de dependencias de
    arriba. Los modulos que todavia no tienen rutas se van sumando en sus propias epicas.
    """
    importar_modelos()

    from app.modulos.organizaciones.rutas import blueprint_organizaciones
    from app.modulos.usuarios_roles.rutas import blueprint_sesion, blueprint_usuarios
    from app.modulos.usuarios_roles.servicios import instalar_cargador_de_sesion

    # Reemplaza el cargador de respaldo de la app factory por el que resuelve usuarios reales.
    instalar_cargador_de_sesion()

    app.register_blueprint(blueprint_sesion, url_prefix="/sesion")
    app.register_blueprint(blueprint_usuarios, url_prefix="/usuarios")
    app.register_blueprint(blueprint_organizaciones, url_prefix="/organizaciones")
