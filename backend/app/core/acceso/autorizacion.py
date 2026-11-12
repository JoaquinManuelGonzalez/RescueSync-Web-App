"""Control de accesos basado en roles (RBAC).

Este es el punto en el que la epica de identidad se vuelve util para el resto del sistema:
una pantalla nueva no escribe logica de autorizacion, **declara su permiso**.

    @blueprint_emergencias.post("/emergencias")
    @requiere_permiso(EMERGENCIAS_CREAR)
    def crear():
        ...

Eso es todo. El permiso ya existe en `core/acceso/permisos.py`, ya esta asignado a los roles que
corresponde y ya viajo a la base con `flask seed`.

Por que vive en `core` y no en `usuarios_roles`
-----------------------------------------------
`docs/arquitectura/componentes.md` seccion 4 le asigna a `core` la seguridad (autenticacion y
RBAC), y la seccion 5 dice que todo modulo puede depender de `core` pero `core` de ninguno. Si
los decoradores vivieran en `usuarios_roles`, `organizaciones` -que esta antes en la cadena de
dependencias- no podria proteger sus rutas sin crear una dependencia hacia adelante.

Este modulo tampoco importa el catalogo de `core/acceso/permisos.py`: recibe los codigos como
strings y trabaja contra la interfaz que expone el usuario autenticado (`tiene_permiso`,
`tiene_rol`).
Quien llama es el que importa la constante, y un modulo podria declarar un permiso propio sin
tocar el mecanismo.

Que NO resuelve
---------------
Los decoradores contestan *que accion* puede ejecutar un rol, no *sobre que filas*. Un operador
municipal tiene `emergencias:editar`, pero solo sobre las emergencias de su municipio. Ese
alcance por organizacion se verifica en la capa de servicios, con
`usuarios_roles.servicios.verificar_alcance_de_organizacion()`. Confundir las dos cosas es el
otro error clasico del RBAC, ademas de verificar solo en el front.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import Flask, request
from flask_login import current_user

from app.core.errores import NoAutenticado, PermisoDenegado
from app.core.logging import id_correlacion_actual, registrar_evento

MENSAJE_SIN_PERMISO = "Tu rol no tiene permiso para realizar esta acción."


def _endpoint_actual() -> str:
    """Ruta de la solicitud en curso, para el evento de log."""
    return request.path if request else ""


def _id_usuario_actual() -> str | None:
    identificador = getattr(current_user, "id", None)
    return None if identificador is None else str(identificador)


def _registrar_denegacion(motivo: str, exigido: str) -> None:
    """Deja constancia de todo acceso denegado, con el id de correlacion de la solicitud.

    Nunca se registra el email ni ningun otro dato personal: el contrato de logging lo prohibe
    y el identificador interno alcanza para reconstruir quien fue.
    """
    registrar_evento(
        logging.WARNING,
        "acceso_denegado",
        motivo=motivo,
        exigido=exigido,
        endpoint=_endpoint_actual(),
        metodo=request.method if request else "",
        id_usuario=_id_usuario_actual(),
        id_correlacion=id_correlacion_actual(),
    )


def _exigir_autenticacion(exigido: str) -> None:
    if not current_user.is_authenticated:
        _registrar_denegacion("sin_sesion", exigido)
        raise NoAutenticado()


def requiere_autenticacion[F: Callable[..., Any]](funcion: F) -> F:
    """Exige una sesion viva, sin mirar roles ni permisos.

    Para las rutas que cualquier usuario autenticado puede usar, como ver sus propios datos
    o cambiar su contrasena.
    """

    @wraps(funcion)
    def envoltorio(*args: Any, **kwargs: Any) -> Any:
        _exigir_autenticacion("autenticacion")
        return funcion(*args, **kwargs)

    return envoltorio  # type: ignore[return-value]


def requiere_permiso[F: Callable[..., Any]](
    *codigos_permiso: str,
    al_denegar: type[PermisoDenegado] = PermisoDenegado,
) -> Callable[[F], F]:
    """Exige que el usuario tenga **todos** los permisos indicados.

    Lo normal es declarar uno solo. Se aceptan varios para el caso de una ruta que combina
    dos operaciones distintas en una sola pantalla.

    Sin sesion devuelve 401 NO_AUTENTICADO; con sesion pero sin el permiso, 403
    PERMISO_DENEGADO. La distincion importa: el 401 le dice al usuario que inicie sesion, el
    403 que no insista con esa cuenta.

    `al_denegar` elige la subclase de `PermisoDenegado` que se lanza. El codigo y el estado
    HTTP no cambian; lo que cambia es la respuesta al navegador. Por ejemplo,
    `SeccionAjenaAlRol` lo devuelve a su portal en lugar de mostrarle la pagina 403.
    """

    def decorador(funcion: F) -> F:
        @wraps(funcion)
        def envoltorio(*args: Any, **kwargs: Any) -> Any:
            exigido = ", ".join(codigos_permiso)
            _exigir_autenticacion(exigido)

            faltantes = [
                codigo for codigo in codigos_permiso if not current_user.tiene_permiso(codigo)
            ]
            if faltantes:
                _registrar_denegacion("sin_permiso", ", ".join(faltantes))
                raise al_denegar(MENSAJE_SIN_PERMISO)

            return funcion(*args, **kwargs)

        return envoltorio  # type: ignore[return-value]

    return decorador


def requiere_rol[F: Callable[..., Any]](*nombres_de_rol: str) -> Callable[[F], F]:
    """Exige que el usuario tenga **alguno** de los roles indicados.

    Se usa poco y a proposito: razonar por permiso es lo que permite agregar una pantalla sin
    tocar la autorizacion. Queda para lo que es intrinsecamente de un perfil y no de una
    accion, como un panel entero.
    """

    def decorador(funcion: F) -> F:
        @wraps(funcion)
        def envoltorio(*args: Any, **kwargs: Any) -> Any:
            exigido = ", ".join(nombres_de_rol)
            _exigir_autenticacion(exigido)

            if not any(current_user.tiene_rol(nombre) for nombre in nombres_de_rol):
                _registrar_denegacion("sin_rol", exigido)
                raise PermisoDenegado(MENSAJE_SIN_PERMISO)

            return funcion(*args, **kwargs)

        return envoltorio  # type: ignore[return-value]

    return decorador


def puede(codigo_permiso: str) -> bool:
    """Indica si el usuario en sesion tiene un permiso. Devuelve False si no hay sesion.

    Se registra como global de Jinja para que las plantillas oculten lo que el usuario no
    puede hacer:

        {% if puede('emergencias:crear') %}<a href="...">Nueva emergencia</a>{% endif %}

    Es solo presentacion. La interfaz **oculta** lo que el servidor ya **prohibe**: cada ruta
    sigue protegida por su decorador, y borrar el `{% if %}` no habilita nada.
    """
    if not current_user.is_authenticated:
        return False
    return bool(current_user.tiene_permiso(codigo_permiso))


def tiene_rol(nombre_rol: str) -> bool:
    """Version para plantillas de `Usuario.tiene_rol`, tolerante a la sesion anonima."""
    if not current_user.is_authenticated:
        return False
    return bool(current_user.tiene_rol(nombre_rol))


def registrar_globales_de_plantilla(app: Flask) -> None:
    """Deja `puede()` y `tiene_rol()` disponibles en cualquier plantilla Jinja.

    Se registran aunque todavia no exista ninguna plantilla: es el punto de enganche para la
    interfaz, y dejarlo listo evita que la primera pantalla que llegue resuelva la visibilidad
    de los botones por su cuenta.
    """
    app.jinja_env.globals["puede"] = puede
    app.jinja_env.globals["tiene_rol"] = tiene_rol
