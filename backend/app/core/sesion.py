"""Gestion de la sesion de usuario.

Concentra el ciclo de vida de la sesion: como se abre, como se cierra, cuanto vive y que pasa
cuando alguien golpea una ruta sin estar autenticado. Es el *mecanismo*; quien es el usuario lo
sabe el modulo `usuarios_roles`, que registra su propio cargador con
`registrar_cargador_de_usuario()`. Por eso este modulo no importa ningun modelo: la regla de
dependencia de docs/arquitectura/componentes.md seccion 5 dice que `core` no depende de ningun
modulo de dominio, y el RBAC no es la excepcion.

Expiracion por inactividad
--------------------------
Es el requisito no funcional de la epica de identidad y se cumple en dos capas, a proposito:

1. La cookie de sesion de Flask va firmada y con `max_age = PERMANENT_SESSION_LIFETIME`. Al
   deserializarla, **el servidor** rechaza una cookie vencida aunque el cliente la siga
   mandando. Es la garantia dura: no depende de que el navegador colabore.
2. Ademas se guarda `ultima_actividad` dentro de la sesion y se verifica en cada solicitud.
   Es redundante con lo anterior, y esta puesto igual porque permite distinguir "sesion
   vencida" de "nunca inicio sesion": dan mensajes distintos al usuario y eventos de log
   distintos, cosa que el rechazo silencioso de la cookie no permite.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from flask import Flask, session
from flask_login import current_user, login_user, logout_user

from app.core.errores import NoAutenticado
from app.core.logging import id_correlacion_actual, registrar_evento
from app.extensiones import login_manager

CLAVE_ULTIMA_ACTIVIDAD = "ultima_actividad"

MENSAJE_SESION_EXPIRADA = "Tu sesión expiró por inactividad. Volvé a iniciar sesión."


def _ahora() -> datetime:
    return datetime.now(UTC)


def marcar_actividad() -> None:
    """Deja la marca de tiempo que usa la verificacion de inactividad."""
    session[CLAVE_ULTIMA_ACTIVIDAD] = _ahora().isoformat()


def iniciar_sesion(usuario: Any) -> None:
    """Abre la sesion del usuario, descartando cualquier contenido previo.

    `session.clear()` antes de `login_user()` es la rotacion de sesion: todo lo que hubiera en
    la sesion anonima (por ejemplo, datos dejados por un tercero en una maquina compartida)
    desaparece, y la cookie que sale es una nueva firma sobre un contenido nuevo.

    `remember=False` es deliberado: la cookie "recordarme" de Flask-Login sobrevive al cierre
    del navegador y volveria decorativa la expiracion por inactividad.
    """
    session.clear()
    login_user(usuario, remember=False)
    session.permanent = True
    marcar_actividad()


def cerrar_sesion() -> None:
    """Cierra la sesion y borra su contenido."""
    logout_user()
    session.clear()


def registrar_cargador_de_usuario(cargador: Callable[[str], Any]) -> None:
    """Instala el `user_loader` de Flask-Login.

    Lo llama `usuarios_roles` al registrarse. Se hace asi, y no importando el modelo desde
    `core`, para no invertir la direccion de dependencias entre `core` y los modulos.
    """
    login_manager.user_loader(cargador)


def configurar_sesion(app: Flask) -> None:
    """Deja la sesion lista: proteccion, respuesta ante no autenticado e inactividad.

    Las claves de configuracion de la cookie (duracion, HttpOnly, SameSite, Secure) las arma
    `app.core.configuracion` a partir de las variables de entorno del contrato; aca solo se
    engancha el comportamiento.
    """
    # "strong" invalida la sesion si cambia la huella del cliente (IP y user agent).
    login_manager.session_protection = "strong"

    @login_manager.unauthorized_handler
    def _sin_autenticar():
        """Respuesta ante acceso no autorizado, con el envelope unico del contrato.

        Por defecto Flask-Login redirige a `login_view`; mientras no exista la pantalla de
        ingreso eso seria un 302 hacia ninguna parte. Levantar la excepcion deja que el
        manejador global de `core/errores.py` devuelva 401 NO_AUTENTICADO con su codigo,
        su timestamp y su id de correlacion, igual que cualquier otro error del sistema.
        """
        raise NoAutenticado()

    @app.before_request
    def _verificar_inactividad() -> None:
        if not current_user.is_authenticated:
            return

        marca = session.get(CLAVE_ULTIMA_ACTIVIDAD)
        if marca is not None:
            try:
                ultima_actividad = datetime.fromisoformat(str(marca))
            except ValueError:
                # Sesion con una marca corrupta: se trata como vencida, no como valida.
                ultima_actividad = datetime.min.replace(tzinfo=UTC)

            if _ahora() - ultima_actividad > app.config["PERMANENT_SESSION_LIFETIME"]:
                id_usuario = str(getattr(current_user, "id", ""))
                cerrar_sesion()
                registrar_evento(
                    logging.INFO,
                    "sesion_expirada",
                    id_usuario=id_usuario,
                    id_correlacion=id_correlacion_actual(),
                )
                raise NoAutenticado(MENSAJE_SESION_EXPIRADA)

        session.permanent = True
        marcar_actividad()
