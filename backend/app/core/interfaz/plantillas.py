"""Filtros de Jinja compartidos por todas las plantillas.

Traducen valores internos (codigos de rol, tipos de organizacion, fechas ISO) a lo que ve una
persona. Viven en el servidor y no en cada plantilla para que "Operador Municipal" se escriba
en un solo lugar.

    {{ usuario.rol_principal|etiqueta_rol }}           -> Operador Municipal
    {{ organizacion.tipo|etiqueta_tipo_organizacion }} -> Municipio
    {{ emergencia.estado|etiqueta_estado_emergencia }} -> En revisión
    {{ emergencia.nivel_gravedad|etiqueta_gravedad }}  -> Crítica
    {{ permiso|descripcion_permiso }}                  -> Registrar una emergencia nueva.
    {{ usuario.ultimo_acceso_en|fecha }}               -> 21/09/2026 14:05
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from flask import Flask, current_app

from app.core.acceso.permisos import (
    CATALOGO_DE_PERMISOS,
    ETIQUETA_POR_ROL,
    ETIQUETA_POR_TIPO_DE_ORGANIZACION,
    NombreRol,
)
from app.core.acceso.seguridad import requisitos_de_contrasena
from app.core.interfaz.paginacion import url_de_pagina

# Las fechas se guardan en UTC y se muestran en la hora de Argentina. Es un desplazamiento fijo
# y no una zona IANA porque Argentina no aplica horario de verano, y asi no depende de que la
# imagen tenga instalada la base de zonas horarias.
ZONA_HORARIA_DE_LA_INTERFAZ = timezone(timedelta(hours=-3), "ART")

SIN_DATO = "—"

ETIQUETA_POR_ESTADO_DE_EMERGENCIA = {
    "registrada": "Registrada",
    "en_evaluacion": "En revisión",
    "activa": "Activa",
    "finalizada": "Finalizada",
    "cancelada": "Cancelada",
}

ETIQUETA_POR_NIVEL_DE_GRAVEDAD = {
    "baja": "Baja",
    "media": "Media",
    "alta": "Alta",
    "critica": "Crítica",
}


def etiqueta_rol(valor: Any) -> str:
    if not valor:
        return SIN_DATO
    try:
        return ETIQUETA_POR_ROL[NombreRol(str(valor))]
    except ValueError:
        return str(valor)


def etiqueta_tipo_organizacion(valor: Any) -> str:
    if not valor:
        return SIN_DATO
    clave = getattr(valor, "value", valor)
    return ETIQUETA_POR_TIPO_DE_ORGANIZACION.get(str(clave), str(clave))


def etiqueta_estado_emergencia(valor: Any) -> str:
    if not valor:
        return SIN_DATO
    clave = getattr(valor, "value", valor)
    return ETIQUETA_POR_ESTADO_DE_EMERGENCIA.get(str(clave), str(clave))


def etiqueta_gravedad(valor: Any) -> str:
    if not valor:
        return SIN_DATO
    clave = getattr(valor, "value", valor)
    return ETIQUETA_POR_NIVEL_DE_GRAVEDAD.get(str(clave), str(clave))


def descripcion_permiso(codigo: Any) -> str:
    return CATALOGO_DE_PERMISOS.get(str(codigo), str(codigo))


def fecha(valor: Any) -> str:
    """Fecha y hora en formato `dd/mm/aaaa hh:mm`. Acepta `datetime` o texto ISO-8601."""
    if not valor:
        return SIN_DATO
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor)
        except ValueError:
            return valor
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=UTC)
    return valor.astimezone(ZONA_HORARIA_DE_LA_INTERFAZ).strftime("%d/%m/%Y %H:%M")


def requisitos_de_contrasena_vigentes() -> dict[str, str]:
    """Los requisitos de contrasena con la longitud de la configuracion, para las plantillas."""
    return requisitos_de_contrasena(int(current_app.config["CONTRASENA_LONGITUD_MINIMA"]))


def registrar_filtros(app: Flask) -> None:
    app.jinja_env.globals["requisitos_de_contrasena"] = requisitos_de_contrasena_vigentes
    app.jinja_env.globals["url_de_pagina"] = url_de_pagina
    app.jinja_env.filters["etiqueta_rol"] = etiqueta_rol
    app.jinja_env.filters["etiqueta_tipo_organizacion"] = etiqueta_tipo_organizacion
    app.jinja_env.filters["etiqueta_estado_emergencia"] = etiqueta_estado_emergencia
    app.jinja_env.filters["etiqueta_gravedad"] = etiqueta_gravedad
    app.jinja_env.filters["descripcion_permiso"] = descripcion_permiso
    app.jinja_env.filters["fecha"] = fecha
