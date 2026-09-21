"""App factory de RescueSync.

El orden de esta funcion es parte del contrato de configuracion: la validacion fail-fast
corre una unica vez, antes de registrar los modulos de dominio, para que el proceso muera sin
llegar a levantar el servidor HTTP si falta una variable obligatoria.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# pyrefly: ignore [missing-import]
from flask import Flask

from app.cli import registrar_comandos
from app.core.configuracion import construir_configuracion, validar_o_terminar
from app.core.errores import registrar_manejadores
from app.core.inicio import blueprint_inicio
from app.core.logging import configurar_logging, registrar_middleware
from app.core.salud import blueprint_salud
from app.extensiones import db, login_manager, migrate
from app.modulos import registrar_modulos

RAIZ_FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend"
DIRECTORIO_PLANTILLAS = RAIZ_FRONTEND / "plantillas"
DIRECTORIO_ESTATICOS = RAIZ_FRONTEND / "estaticos"


def _registrar_cargador_de_usuario_por_defecto() -> None:
    """Deja a Flask-Login con un cargador que no devuelve a nadie.

    Sin un `user_loader` registrado, Flask-Login levanta una excepcion la primera vez que
    alguien toca `current_user`, y eso tumbaria cualquier ruta antes de que exista el modulo
    usuarios_roles. Ese modulo reemplaza este cargador por el suyo cuando se cree.
    """

    @login_manager.user_loader
    def _cargar_usuario(id_usuario: str):  # noqa: ARG001
        return None


def create_app(overrides: dict[str, Any] | None = None) -> Flask:
    """Construye la aplicacion. `overrides` es solo para los tests."""
    validar_o_terminar()

    configuracion = construir_configuracion()
    configurar_logging(str(configuracion["LOG_LEVEL"]))

    app = Flask(
        __name__,
        template_folder=str(DIRECTORIO_PLANTILLAS),
        static_folder=str(DIRECTORIO_ESTATICOS),
        static_url_path="/estaticos",
    )
    app.config.update(configuracion)
    if overrides:
        app.config.update(overrides)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    _registrar_cargador_de_usuario_por_defecto()

    registrar_middleware(app)
    registrar_manejadores(app)
    registrar_comandos(app)

    app.register_blueprint(blueprint_salud)
    app.register_blueprint(blueprint_inicio)

    # Los modulos de dominio se registran al final, ya con la configuracion validada.
    registrar_modulos(app)

    return app
