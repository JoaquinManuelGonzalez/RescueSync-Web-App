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
from app.core.acceso.autorizacion import registrar_globales_de_plantilla
from app.core.acceso.sesion import configurar_sesion
from app.core.configuracion import construir_configuracion, validar_o_terminar
from app.core.errores import registrar_manejadores
from app.core.interfaz.inicio import blueprint_inicio
from app.core.interfaz.navegacion import registrar_navegacion
from app.core.interfaz.plantillas import registrar_filtros
from app.core.logging import configurar_logging, registrar_middleware
from app.core.salud import blueprint_salud
from app.extensiones import csrf, db, login_manager, migrate
from app.modulos import registrar_modulos

RAIZ_FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend"
DIRECTORIO_PLANTILLAS = RAIZ_FRONTEND / "plantillas"
DIRECTORIO_ESTATICOS = RAIZ_FRONTEND / "estaticos"


def _registrar_cargador_de_respaldo() -> None:
    """Deja a Flask-Login con un cargador que no devuelve a nadie.

    Sin un `user_loader` registrado, Flask-Login levanta una excepcion la primera vez que
    alguien toca `current_user`. `usuarios_roles` instala el cargador real al registrarse
    (ver `app.core.acceso.sesion.registrar_cargador_de_usuario`); este queda como red de seguridad
    para el caso en que la aplicacion se construya sin los modulos de dominio, por ejemplo en
    un test que solo ejercite `core`.
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
    # Proteccion CSRF para toda la aplicacion. Los endpoints que no se autentican por sesion
    # (el callback de Bonita, integracion 4) se eximen con @csrf.exempt en su propio modulo.
    csrf.init_app(app)
    _registrar_cargador_de_respaldo()
    configurar_sesion(app)

    registrar_middleware(app)
    registrar_manejadores(app)
    registrar_comandos(app)
    registrar_globales_de_plantilla(app)
    registrar_navegacion(app)
    registrar_filtros(app)

    app.register_blueprint(blueprint_salud)
    app.register_blueprint(blueprint_inicio)

    # Los modulos de dominio se registran al final, ya con la configuracion validada.
    registrar_modulos(app)

    return app
