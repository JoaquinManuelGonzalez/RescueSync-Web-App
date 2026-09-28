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
    from app.modulos.notificaciones import modelos as _notificaciones  # noqa: F401
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

    from app.core.interfaz.navegacion import registrar_entrada
    from app.modulos.emergencias import rutas as rutas_de_emergencias
    from app.modulos.emergencias.lotes import rutas as rutas_de_lotes
    from app.modulos.notificaciones import rutas as rutas_de_notificaciones
    from app.modulos.notificaciones import servicios as servicios_de_notificaciones
    from app.modulos.ofertas import rutas as rutas_de_ofertas
    from app.modulos.organizaciones import rutas as rutas_de_organizaciones
    from app.modulos.usuarios_roles import rutas as rutas_de_usuarios_roles
    from app.modulos.usuarios_roles.servicios import instalar_cargador_de_sesion

    # Reemplaza el cargador de respaldo de la app factory por el que resuelve usuarios reales.
    instalar_cargador_de_sesion()

    app.register_blueprint(rutas_de_usuarios_roles.blueprint_sesion, url_prefix="/sesion")
    app.register_blueprint(rutas_de_usuarios_roles.blueprint_usuarios, url_prefix="/usuarios")
    app.register_blueprint(
        rutas_de_organizaciones.blueprint_organizaciones, url_prefix="/organizaciones"
    )
    app.register_blueprint(rutas_de_ofertas.blueprint_ofertas, url_prefix="/ofertas")
    app.register_blueprint(rutas_de_emergencias.blueprint_emergencias, url_prefix="/emergencias")
    app.register_blueprint(rutas_de_lotes.blueprint_lotes, url_prefix="/lotes")
    app.register_blueprint(
        rutas_de_notificaciones.blueprint_notificaciones, url_prefix="/notificaciones"
    )
    servicios_de_notificaciones.registrar_contexto(app)


    # Cada pantalla con acceso propio en el menu declara su entrada junto a sus rutas; aca solo
    # se registra. Quien la ve lo decide su permiso (ver app/core/interfaz/navegacion.py).
    registrar_entrada(app, rutas_de_usuarios_roles.ENTRADA_DE_MENU)
    registrar_entrada(app, rutas_de_organizaciones.ENTRADA_DE_MENU)
    registrar_entrada(app, rutas_de_organizaciones.ENTRADA_DE_MENU_MI_ORGANIZACION)
    registrar_entrada(app, rutas_de_organizaciones.ENTRADA_DE_MENU_INVENTARIO)
    registrar_entrada(app, rutas_de_ofertas.ENTRADA_DE_MENU)
    registrar_entrada(app, rutas_de_emergencias.ENTRADA_DE_MENU)
