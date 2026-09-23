"""Respuesta segun el cliente: HTML para el navegador, JSON para todo lo demas.

La misma ruta sirve a la interfaz y a los clientes JSON (los tests, `curl`, un `fetch` futuro).
Ni el formulario ni el servicio cambian segun el formato: lo unico que cambia es la ultima
linea de la vista, y eso es lo que resuelven las funciones de este modulo.

Como se decide
--------------
`pide_json()` mira la cabecera `Accept`. Un navegador que navega manda `text/html` con mas
prioridad que cualquier otra cosa; un cliente que no dice nada, o que pide JSON, recibe JSON.
Asi los tests existentes, que no mandan `Accept`, siguen viendo el envelope del contrato.

Formularios que fallan
----------------------
Las vistas siguen cortando con excepciones (`validar_o_fallar`, los errores del servicio). En el
navegador eso no puede terminar en una pagina de error: hay que volver a mostrar el formulario
con los mensajes al lado de cada campo. `@plantilla_ante_error` declara que plantilla mostrar, y
el manejador global de `core/errores.py` la usa. La vista no escribe ningun `try`.

    @blueprint_usuarios.post("")
    @requiere_permiso(USUARIOS_CREAR)
    @plantilla_ante_error("usuarios/formulario.html", contexto=_contexto_del_formulario)
    def crear():
        formulario = construir_formulario(FormularioAltaDeUsuario)
        validar_o_fallar(formulario)
        usuario = servicios.crear_usuario(...)
        return redirigir("usuarios.ver", "Cuenta creada.", usuario_id=usuario.id)

El decorador va **debajo** del de autorizacion: si el usuario no tiene permiso, el formulario
nunca se registra y el 403 sale como pagina de error, no como formulario re-renderizado.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import wraps
from typing import Any
from urllib.parse import urlsplit

from flask import flash, g, jsonify, redirect, render_template, request, url_for

# Categorias de los mensajes flash: las que dibuja `frontend/plantillas/layout.html`.
EXITO = "success"
ERROR = "error"
ADVERTENCIA = "warning"
INFO = "info"


def pide_json() -> bool:
    """Indica si la respuesta tiene que ser JSON y no HTML."""
    if request.is_json:
        return True
    aceptados = request.accept_mimetypes
    return aceptados["application/json"] >= aceptados["text/html"]


def redirigir(
    endpoint: str,
    mensaje: str | None = None,
    categoria: str = EXITO,
    *,
    datos_json: Any = None,
    estado_json: int = 200,
    preferir_origen: bool = False,
    **valores_url: Any,
):
    """Respuesta de un POST exitoso: redirect con mensaje (navegador) o JSON (resto).

    Es el patron Post/Redirect/Get: despues de modificar algo, el navegador pide la pantalla de
    destino con un GET, y recargarla no vuelve a enviar el formulario.

    Si no se indica `datos_json`, el cliente JSON recibe `{"mensaje": mensaje}`.
    `preferir_origen` vuelve a la pantalla desde la que se envio el formulario, si es propia.
    """
    if pide_json():
        cuerpo = datos_json if datos_json is not None else {"mensaje": mensaje}
        return jsonify(cuerpo), estado_json

    if mensaje:
        flash(mensaje, categoria)
    destino = (preferir_origen and origen_propio()) or url_for(endpoint, **valores_url)
    return redirect(destino)


def destino_seguro(destino: str | None) -> str | None:
    """Devuelve `destino` solo si es una ruta de esta misma aplicacion.

    Protege el `?next=` del ingreso contra redirecciones abiertas: `//otro.sitio`,
    `https://otro.sitio` o `/\\otro.sitio` los navegadores los interpretan como otro host.
    """
    if not destino:
        return None
    if not destino.startswith("/") or destino.startswith("//"):
        return None
    if "\\" in destino or any(ord(caracter) < 32 for caracter in destino):
        return None
    partes = urlsplit(destino)
    if partes.scheme or partes.netloc:
        return None
    return destino


def origen_propio() -> str | None:
    """La ruta de la pantalla anterior (`Referer`), si pertenece a esta aplicacion."""
    referente = request.referrer
    if not referente:
        return None
    partes = urlsplit(referente)
    if partes.netloc and partes.netloc != request.host:
        return None
    ruta = partes.path + (f"?{partes.query}" if partes.query else "")
    return destino_seguro(ruta)


# --- Formularios que fallan ---------------------------------------------------


@dataclass(frozen=True)
class PlantillaAnteError:
    plantilla: str
    contexto: Callable[..., Mapping[str, Any]] | None
    nombre_formulario: str


def plantilla_ante_error[F: Callable[..., Any]](
    plantilla: str,
    contexto: Callable[..., Mapping[str, Any]] | None = None,
    nombre_formulario: str = "formulario",
) -> Callable[[F], F]:
    """Declara que plantilla volver a mostrar si el formulario o el servicio fallan.

    `contexto` recibe los mismos argumentos de URL que la vista (`usuario_id`, ...) y devuelve
    el resto de lo que la plantilla necesita. El formulario, con sus errores, viaja con el
    nombre `nombre_formulario`.
    """

    def decorador(funcion: F) -> F:
        @wraps(funcion)
        def envoltorio(*args: Any, **kwargs: Any) -> Any:
            g.plantilla_ante_error = PlantillaAnteError(plantilla, contexto, nombre_formulario)
            return funcion(*args, **kwargs)

        return envoltorio  # type: ignore[return-value]

    return decorador


def _volcar_errores_en_campos(formulario: Any, detalle: Any) -> list[str]:
    """Pega a cada campo los mensajes que el `detalle` del error trae para el.

    Devuelve los mensajes que no corresponden a ningun campo del formulario, para mostrarlos
    arriba de todo.
    """
    if not isinstance(detalle, Mapping):
        return []

    sueltos: list[str] = []
    for nombre, mensajes in detalle.items():
        if isinstance(mensajes, list | tuple):
            lista = [str(uno) for uno in mensajes]
        else:
            lista = [str(mensajes)]
        campo = formulario._fields.get(nombre)
        if campo is None:
            sueltos.extend(lista)
            continue
        campo.errors = [*campo.errors, *(uno for uno in lista if uno not in campo.errors)]
    return sueltos


def respuesta_de_formulario_con_errores(mensaje: str, detalle: Any, estado: int):
    """Vuelve a mostrar el formulario en curso con sus errores, o None si no corresponde.

    Corresponde cuando la vista declaro `@plantilla_ante_error`, ya construyo su formulario y la
    solicitud es un POST del navegador.
    """
    declaracion: PlantillaAnteError | None = g.get("plantilla_ante_error")
    formulario = g.get("formulario_en_curso")
    if declaracion is None or formulario is None or request.method != "POST":
        return None

    flash(mensaje, ERROR)
    for suelto in _volcar_errores_en_campos(formulario, detalle):
        flash(suelto, ERROR)

    contexto: dict[str, Any] = {}
    if declaracion.contexto is not None:
        contexto.update(declaracion.contexto(**(request.view_args or {})))
    contexto[declaracion.nombre_formulario] = formulario
    return render_template(declaracion.plantilla, **contexto), estado
