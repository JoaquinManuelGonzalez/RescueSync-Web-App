"""Endpoints de gestion de organizaciones.

Todas las rutas estan protegidas por permiso, no por rol: hoy el unico perfil que tiene los
permisos `organizaciones:*` es el administrador, pero el dia que eso cambie no hay que tocar
este archivo, solo la matriz de `usuarios_roles/constantes.py`.

Formato de la respuesta
-----------------------
Hoy devuelven JSON, porque la plantilla de la interfaz todavia no existe. El diccionario que
arma `servicios.a_diccionario()` es exactamente el contexto que va a recibir la plantilla
cuando llegue: entonces cada vista suma su `render_template(...)` y ni el servicio ni el
formulario cambian. Ver docs/contratos/autorizacion.md.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.core.autorizacion import requiere_permiso
from app.core.formularios import (
    construir_formulario,
    parametro_booleano,
    validar_o_fallar,
)
from app.core.permisos import (
    ORGANIZACIONES_CAMBIAR_ESTADO,
    ORGANIZACIONES_CREAR,
    ORGANIZACIONES_EDITAR,
    ORGANIZACIONES_LISTAR,
)
from app.modulos.organizaciones import servicios
from app.modulos.organizaciones.formularios import FormularioEstado, FormularioOrganizacion

blueprint_organizaciones = Blueprint("organizaciones", __name__)


@blueprint_organizaciones.get("")
@requiere_permiso(ORGANIZACIONES_LISTAR)
def listar():
    """Listado de organizaciones, filtrable por tipo, estado y texto del nombre."""
    organizaciones = servicios.listar(
        tipo=request.args.get("tipo") or None,
        activo=parametro_booleano("activo"),
        texto=request.args.get("texto") or None,
    )
    return jsonify({"organizaciones": [servicios.a_diccionario(una) for una in organizaciones]})


@blueprint_organizaciones.get("/<int:organizacion_id>")
@requiere_permiso(ORGANIZACIONES_LISTAR)
def ver(organizacion_id: int):
    """Detalle de una organizacion."""
    return jsonify(servicios.a_diccionario(servicios.obtener(organizacion_id)))


@blueprint_organizaciones.post("")
@requiere_permiso(ORGANIZACIONES_CREAR)
def crear():
    """Alta de un municipio, una ONG o el centro coordinador regional."""
    formulario = construir_formulario(FormularioOrganizacion)
    validar_o_fallar(formulario)

    organizacion = servicios.crear(
        nombre=formulario.nombre.data,
        tipo=formulario.tipo.data,
        identificador_nacional=formulario.identificador_nacional.data,
        contacto_email=formulario.contacto_email.data,
        contacto_telefono=formulario.contacto_telefono.data,
        direccion=formulario.direccion.data,
    )
    return jsonify(servicios.a_diccionario(organizacion)), 201


@blueprint_organizaciones.post("/<int:organizacion_id>/edicion")
@requiere_permiso(ORGANIZACIONES_EDITAR)
def editar(organizacion_id: int):
    """Edicion de los datos de una organizacion."""
    formulario = construir_formulario(FormularioOrganizacion)
    validar_o_fallar(formulario)

    organizacion = servicios.editar(
        organizacion_id,
        nombre=formulario.nombre.data,
        tipo=formulario.tipo.data,
        identificador_nacional=formulario.identificador_nacional.data,
        contacto_email=formulario.contacto_email.data,
        contacto_telefono=formulario.contacto_telefono.data,
        direccion=formulario.direccion.data,
    )
    return jsonify(servicios.a_diccionario(organizacion))


@blueprint_organizaciones.post("/<int:organizacion_id>/estado")
@requiere_permiso(ORGANIZACIONES_CAMBIAR_ESTADO)
def cambiar_estado(organizacion_id: int):
    """Alta o baja logica de una organizacion."""
    formulario = construir_formulario(FormularioEstado)
    validar_o_fallar(formulario)

    organizacion = servicios.cambiar_estado(organizacion_id, activo=bool(formulario.activo.data))
    return jsonify(servicios.a_diccionario(organizacion))
