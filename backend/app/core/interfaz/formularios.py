"""Puente entre la entrada HTTP y los formularios WTForms.

RescueSync es una aplicacion renderizada en el servidor: la entrada natural de un formulario
es `request.form`, que es lo que manda la interfaz. Las mismas rutas se ejercitan tambien por
JSON (con `curl` y en los tests).

Este modulo hace que **la misma ruta y el mismo formulario** sirvan a los dos casos. Como
responder a cada uno lo resuelve `app.core.interfaz.vistas`.

Sobre CSRF
----------
La proteccion CSRF es de toda la aplicacion (`CSRFProtect` en la app factory), y valida cada
POST antes de que la vista corra, leyendo el campo `csrf_token` del formulario o la cabecera
`X-CSRFToken`. Cuando el cuerpo viene en JSON no hay campo oculto que validar, asi que el
formulario se construye con su CSRF propio apagado: la verificacion ya la hizo `CSRFProtect`,
y dejarla encendida haria fallar todo POST JSON con un error de validacion enganoso.
"""

from __future__ import annotations

import uuid

from flask import g, request
from flask_wtf import FlaskForm
from wtforms import StringField

from app.core.errores import SolicitudInvalida
from app.core.identificadores import parsear_id


def construir_formulario[T: FlaskForm](clase_formulario: type[T], **kwargs: object) -> T:
    """Instancia un formulario desde el cuerpo de la solicitud, venga como venga.

    - `Content-Type: application/json` -> se alimenta del objeto JSON.
    - Cualquier otro caso -> comportamiento normal de Flask-WTF sobre `request.form`.

    El formulario queda ademas en `g.formulario_en_curso`: si la vista falla, el manejador de
    errores lo vuelve a mostrar con sus mensajes (ver
    `app.core.interfaz.vistas.plantilla_ante_error`).
    """
    if request.is_json:
        datos = request.get_json(silent=True)
        if not isinstance(datos, dict):
            datos = {}
        formulario = clase_formulario(data=datos, meta={"csrf": False}, **kwargs)
    else:
        formulario = clase_formulario(**kwargs)
    g.formulario_en_curso = formulario
    return formulario


def errores_de(formulario: FlaskForm) -> dict[str, list[str]]:
    """Errores de validacion en la forma `{campo: [mensajes]}`."""
    return {campo: list(mensajes) for campo, mensajes in formulario.errors.items()}


def validar_o_fallar(formulario: FlaskForm) -> None:
    """Valida el formulario y, si no pasa, corta con 400 SOLICITUD_INVALIDA.

    El detalle del envelope lleva los errores campo por campo, que es lo que la interfaz va a
    necesitar para pintarlos al lado de cada input.
    """
    if not formulario.validate():
        raise SolicitudInvalida(detalle=errores_de(formulario))


def parametro_booleano(nombre: str) -> bool | None:
    """Lee un filtro booleano de la query string. Devuelve None si no vino.

    Sirve para filtros como `?activo=true`, donde "no filtrar" y "filtrar por false" son cosas
    distintas y un `bool()` directo las confundiria.
    """
    valor = request.args.get(nombre)
    if valor is None or valor == "":
        return None
    return valor.strip().lower() in {"1", "true", "t", "si", "sí"}


def parametro_entero(nombre: str) -> int | None:
    """Lee un filtro numerico de la query string, o None si no vino o no es un entero."""
    valor = request.args.get(nombre)
    if valor is None or valor.strip() == "":
        return None
    try:
        return int(valor)
    except ValueError:
        raise SolicitudInvalida(detalle={nombre: ["Debe ser un número entero."]}) from None


def parametro_id(nombre: str) -> uuid.UUID | None:
    """Lee el id (UUID) de otra entidad de la query string, o None si no vino.

    Un valor que no es un UUID corta con 400, igual que `parametro_entero` con un número.
    """
    valor = request.args.get(nombre)
    if valor is None or valor.strip() == "":
        return None
    identificador = parsear_id(valor)
    if identificador is None:
        raise SolicitudInvalida(detalle={nombre: ["Debe ser un identificador válido."]})
    return identificador


class CampoId(StringField):
    """Campo con el id (UUID) de otra entidad, por ejemplo la organización de una cuenta.

    `data` queda como `uuid.UUID`, o None si el campo vino vacío. Un valor que no es un UUID es
    un error de validación del campo, venga del formulario HTML o del cuerpo JSON.
    """

    MENSAJE_INVALIDO = "No es un identificador válido."

    def process_data(self, value: object) -> None:
        if value is None or value == "":
            self.data = None
            return
        self.data = parsear_id(value)
        if self.data is None:
            raise ValueError(self.MENSAJE_INVALIDO)

    def process_formdata(self, valuelist: list[str]) -> None:
        if not valuelist or not valuelist[0].strip():
            self.data = None
            return
        self.data = parsear_id(valuelist[0])
        if self.data is None:
            raise ValueError(self.MENSAJE_INVALIDO)

    def _value(self) -> str:
        return str(self.data) if self.data is not None else ""
