"""Endpoints de gestion de organizaciones.

Todas las rutas estan protegidas por permiso, no por rol: hoy el unico perfil que tiene los
permisos `organizaciones:*` es el administrador, pero el dia que eso cambie no hay que tocar
este archivo, solo la matriz de `app/core/acceso/permisos.py`.

Formato de la respuesta
-----------------------
La misma ruta sirve a la interfaz y a los clientes JSON (ver `app.core.interfaz.vistas`): los GET
devuelven la pantalla o el diccionario de `servicios.a_diccionario()`, y los POST responden
con `redirigir(...)`. Si un formulario falla, `@plantilla_ante_error` lo vuelve a mostrar con
sus errores. Ver docs/contratos/interfaz.md.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user

from app.core.acceso.autorizacion import requiere_permiso
from app.core.acceso.permisos import (
    INVENTARIO_EDITAR,
    INVENTARIO_VER,
    ORGANIZACIONES_CAMBIAR_ESTADO,
    ORGANIZACIONES_CREAR,
    ORGANIZACIONES_EDITAR,
    ORGANIZACIONES_LISTAR,
)
from app.core.interfaz.formularios import (
    construir_formulario,
    parametro_booleano,
    validar_o_fallar,
)
from app.core.interfaz.navegacion import EntradaDeMenu
from app.core.interfaz.paginacion import parametros_de_paginacion
from app.core.interfaz.vistas import pide_json, plantilla_ante_error, redirigir
from app.modulos.emergencias.modelos import TipoNecesidad
from app.modulos.organizaciones import servicios
from app.modulos.organizaciones.formularios import (
    OPCIONES_DE_TIPO,
    FormularioEstado,
    FormularioInventarioItem,
    FormularioOrganizacion,
)

blueprint_organizaciones = Blueprint("organizaciones", __name__)

ENTRADA_DE_MENU = EntradaDeMenu(
    endpoint="organizaciones.listar",
    titulo="Organizaciones",
    permiso=ORGANIZACIONES_LISTAR,
    descripcion="Municipios, ONGs y centro coordinador",
    icono="organizaciones",
    orden=20,
)

ENTRADA_DE_MENU_INVENTARIO = EntradaDeMenu(
    endpoint="organizaciones.ver_inventario",
    titulo="Inventario",
    permiso=INVENTARIO_VER,
    descripcion="Existencias de tu organización",
    icono="banco",
    orden=30,
)

OPCIONES_DE_ESTADO = [("true", "Activas"), ("false", "Inactivas")]


def _contexto_del_formulario(organizacion_id: int | None = None) -> dict[str, Any]:
    return {
        "modo": "alta" if organizacion_id is None else "edicion",
        "organizacion": (
            servicios.a_diccionario(servicios.obtener(organizacion_id))
            if organizacion_id is not None
            else None
        ),
    }


@blueprint_organizaciones.get("")
@requiere_permiso(ORGANIZACIONES_LISTAR)
def listar():
    """Listado paginado de organizaciones, filtrable por tipo, estado y texto del nombre."""
    pagina, por_pagina = parametros_de_paginacion()
    resultado = servicios.paginar_listado(
        pagina=pagina,
        por_pagina=por_pagina,
        tipo=request.args.get("tipo") or None,
        activo=parametro_booleano("activo"),
        texto=request.args.get("texto") or None,
    ).mapear(servicios.a_diccionario)
    if pide_json():
        return jsonify(
            {"organizaciones": resultado.elementos, "paginacion": resultado.a_diccionario()}
        )
    return render_template(
        "organizaciones/listado.html",
        organizaciones=resultado.elementos,
        pagina=resultado,
        filtros=request.args,
        opciones_de_tipo=OPCIONES_DE_TIPO,
        opciones_de_estado=OPCIONES_DE_ESTADO,
    )


@blueprint_organizaciones.get("/nueva")
@requiere_permiso(ORGANIZACIONES_CREAR)
def formulario_de_alta():
    """Pantalla de alta de una organizacion."""
    return render_template(
        "organizaciones/formulario.html",
        formulario=FormularioOrganizacion(),
        **_contexto_del_formulario(),
    )


@blueprint_organizaciones.get("/<int:organizacion_id>")
@requiere_permiso(ORGANIZACIONES_LISTAR)
def ver(organizacion_id: int):
    """Detalle de una organizacion."""
    datos = servicios.a_diccionario(servicios.obtener(organizacion_id))
    if pide_json():
        return jsonify(datos)
    return render_template("organizaciones/detalle.html", organizacion=datos)


@blueprint_organizaciones.post("")
@requiere_permiso(ORGANIZACIONES_CREAR)
@plantilla_ante_error("organizaciones/formulario.html", contexto=_contexto_del_formulario)
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
    return redirigir(
        "organizaciones.ver",
        "Organización creada.",
        datos_json=servicios.a_diccionario(organizacion),
        estado_json=201,
        organizacion_id=organizacion.id,
    )


@blueprint_organizaciones.get("/<int:organizacion_id>/edicion")
@requiere_permiso(ORGANIZACIONES_EDITAR)
def formulario_de_edicion(organizacion_id: int):
    """Pantalla de edicion de una organizacion, precargada con sus datos actuales."""
    contexto = _contexto_del_formulario(organizacion_id)
    return render_template(
        "organizaciones/formulario.html",
        formulario=FormularioOrganizacion(data=contexto["organizacion"]),
        **contexto,
    )


@blueprint_organizaciones.post("/<int:organizacion_id>/edicion")
@requiere_permiso(ORGANIZACIONES_EDITAR)
@plantilla_ante_error("organizaciones/formulario.html", contexto=_contexto_del_formulario)
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
    return redirigir(
        "organizaciones.ver",
        "Cambios guardados.",
        datos_json=servicios.a_diccionario(organizacion),
        organizacion_id=organizacion.id,
    )


@blueprint_organizaciones.post("/<int:organizacion_id>/estado")
@requiere_permiso(ORGANIZACIONES_CAMBIAR_ESTADO)
def cambiar_estado(organizacion_id: int):
    """Alta o baja logica de una organizacion.

    En el navegador vuelve a la pantalla desde la que se hizo (el listado o el detalle).
    """
    formulario = construir_formulario(FormularioEstado)
    validar_o_fallar(formulario)

    organizacion = servicios.cambiar_estado(organizacion_id, activo=bool(formulario.activo.data))
    return redirigir(
        "organizaciones.listar",
        "Organización activada." if organizacion.activo else "Organización desactivada.",
        datos_json=servicios.a_diccionario(organizacion),
        preferir_origen=True,
    )

@blueprint_organizaciones.get("/inventario")
@requiere_permiso(INVENTARIO_VER)
def ver_inventario():
    """Inventario de una organizacion."""
    organizacion_id = current_user.organizacion_id
    categoria_seleccionada = request.args.get("categoria", "")
    texto = request.args.get("texto", "")
    pagina, por_pagina = parametros_de_paginacion()
    datos = servicios.obtener_inventario(organizacion_id)
    return render_template(
        "organizaciones/inventario.html",
        inventario=datos,
        pagina=servicios.paginar_items_de_inventario(
            organizacion_id,
            categoria_seleccionada,
            texto,
            pagina=pagina,
            por_pagina=por_pagina,
        ),
        categorias=servicios.categorias_de_inventario(organizacion_id),
        categoria_seleccionada=categoria_seleccionada,
        texto=texto,
    )


@blueprint_organizaciones.get("/inventario/nuevo")
@requiere_permiso(INVENTARIO_EDITAR)
def formulario_de_alta_de_item():
    """Pantalla para agregar un item al inventario de la organizacion autenticada."""
    return render_template(
        "organizaciones/nuevo_item.html",
        formulario=FormularioInventarioItem(),
        items=servicios.listar_items_disponibles(current_user.organizacion_id),
        categorias=list(TipoNecesidad),
    )


@blueprint_organizaciones.post("/inventario")
@requiere_permiso(INVENTARIO_EDITAR)
def crear_item_inventario():
    """Agrega un item al inventario de la organizacion autenticada."""
    formulario = construir_formulario(FormularioInventarioItem)
    validar_o_fallar(formulario)

    inventario_item = servicios.crear_item_inventario(
        current_user.organizacion_id,
        item_id=formulario.item_id.data,
        cantidad_disponible=formulario.cantidad_disponible.data,
    )
    return redirigir(
        "organizaciones.ver_inventario",
        "Item agregado al inventario.",
        datos_json=servicios.item_inventario_a_diccionario(inventario_item),
        estado_json=201,
    )


@blueprint_organizaciones.post("/inventario/<int:inventario_item_id>/editar")
@requiere_permiso(INVENTARIO_EDITAR)
def editar_item_inventario(inventario_item_id: int):
    """Actualiza la cantidad de un item del inventario de la organizacion autenticada."""
    inventario_item = servicios.obtener_item_inventario(
        current_user.organizacion_id,
        inventario_item_id,
    )
    formulario = construir_formulario(
        FormularioInventarioItem,
        items=[inventario_item.item],
    )
    validar_o_fallar(formulario)

    inventario_item = servicios.editar_item_inventario(
        current_user.organizacion_id,
        inventario_item_id,
        item_id=formulario.item_id.data,
        cantidad_disponible=formulario.cantidad_disponible.data,
    )
    return redirigir(
        "organizaciones.ver_inventario",
        "Cantidad actualizada.",
        datos_json=servicios.item_inventario_a_diccionario(inventario_item),
    )


@blueprint_organizaciones.post("/inventario/<int:inventario_item_id>/eliminar")
@requiere_permiso(INVENTARIO_EDITAR)
def eliminar_item_inventario(inventario_item_id: int):
    """Quita un item del inventario de la organizacion autenticada."""
    servicios.eliminar_item_inventario(
        current_user.organizacion_id,
        inventario_item_id,
    )
    return redirigir(
        "organizaciones.ver_inventario",
        "Item eliminado del inventario.",
        datos_json={"mensaje": "Item eliminado del inventario."},
    )
