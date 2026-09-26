"""Endpoints de gestion de organizaciones.

Todas las rutas estan protegidas por permiso, no por rol: hoy el unico perfil que tiene los
permisos `organizaciones:*` es el administrador, pero el dia que eso cambie no hay que tocar
este archivo, solo la matriz de `app/core/acceso/permisos.py`.

"Mi organizacion" (`/organizaciones/mia`) es la vista de los miembros: cada cuenta ve y
actualiza solo la organizacion a la que pertenece (permisos `organizacion_propia:*`). El id sale
de la sesion y nunca de la URL, asi que no hay forma de pedir la de otro.

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
    ORGANIZACION_PROPIA_EDITAR,
    ORGANIZACION_PROPIA_VER,
    ORGANIZACIONES_CAMBIAR_ESTADO,
    ORGANIZACIONES_CREAR,
    ORGANIZACIONES_EDITAR,
    ORGANIZACIONES_LISTAR,
)
from app.core.errores import SolicitudInvalida
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
    FormularioDatosPropios,
    FormularioEstado,
    FormularioInventarioItem,
    FormularioOrganizacion,
)
from app.modulos.organizaciones.geografia import OPCIONES_DE_PROVINCIA

blueprint_organizaciones = Blueprint("organizaciones", __name__)

ENTRADA_DE_MENU = EntradaDeMenu(
    endpoint="organizaciones.listar",
    titulo="Organizaciones",
    permiso=ORGANIZACIONES_LISTAR,
    descripcion="Municipios, ONGs y centro coordinador",
    icono="organizaciones",
    orden=20,
    # El blueprint tambien aloja "Mi organizacion" e inventario: cada seccion declara sus
    # pantallas para que el navbar marque solo la actual (ver core/interfaz/navegacion.py).
    endpoints=frozenset(
        {
            "organizaciones.listar",
            "organizaciones.ver",
            "organizaciones.formulario_de_alta",
            "organizaciones.crear",
            "organizaciones.formulario_de_edicion",
            "organizaciones.editar",
            "organizaciones.cambiar_estado",
        }
    ),
)

ENTRADA_DE_MENU_INVENTARIO = EntradaDeMenu(
    endpoint="organizaciones.ver_inventario",
    titulo="Inventario",
    permiso=INVENTARIO_VER,
    descripcion="Existencias de tu organización",
    icono="banco",
    orden=30,
)

ENTRADA_DE_MENU_MI_ORGANIZACION = EntradaDeMenu(
    endpoint="organizaciones.mi_organizacion",
    titulo="Mi organización",
    permiso=ORGANIZACION_PROPIA_VER,
    descripcion="Datos, cobertura y miembros de tu organización",
    icono="organizaciones",
    orden=25,
    endpoints=frozenset(
        {
            "organizaciones.mi_organizacion",
            "organizaciones.formulario_de_mi_organizacion",
            "organizaciones.editar_mi_organizacion",
        }
    ),
)

OPCIONES_DE_ESTADO = [("true", "Activas"), ("false", "Inactivas")]

ETIQUETA_POR_ESTADO_DE_VERIFICACION = {
    "sin_verificar": "Sin verificar",
    "verificada": "Verificada",
    "rechazada": "Rechazada",
}


@blueprint_organizaciones.app_template_filter("etiqueta_verificacion")
def etiqueta_verificacion(valor: str | None) -> str:
    """{{ organizacion.estado_verificacion|etiqueta_verificacion }} -> Sin verificar"""
    return ETIQUETA_POR_ESTADO_DE_VERIFICACION.get(valor or "", valor or "")


def _zonas_enviadas(formulario: FormularioDatosPropios) -> list[dict[str, Any]] | None:
    """Las zonas enviadas, o None si un cliente JSON no mando la clave `zonas`.

    El formulario HTML siempre manda sus filas (`zonas-0-provincia`, ...) y las lee el
    `FieldList`. Un cliente JSON manda `"zonas": [{"provincia": ..., "localidad": ...}]`, que
    Flask-WTF no sabe desanidar (arma el formdata con las claves de primer nivel), asi que se
    toma del cuerpo tal cual. Si el cliente JSON edita sin mencionar la cobertura, se deja como
    esta en vez de borrarla sin querer.
    """
    if not request.is_json:
        return formulario.zonas.data
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict) or "zonas" not in cuerpo:
        return None
    zonas = cuerpo["zonas"]
    if not isinstance(zonas, list) or not all(isinstance(zona, dict) for zona in zonas):
        raise SolicitudInvalida(
            detalle={"zonas": ["Debe ser una lista de objetos con `provincia` y `localidad`."]}
        )
    return zonas


def _cobertura_nacional_enviada(formulario: FormularioDatosPropios) -> bool | None:
    """La casilla "Opera en todo el país", o None si un cliente JSON no la mando.

    En el formulario HTML una casilla sin marcar no viaja, asi que ausente es False. En JSON,
    ausente significa "no la cambio", igual que con las zonas.
    """
    if not request.is_json:
        return bool(formulario.cobertura_nacional.data)
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict) or "cobertura_nacional" not in cuerpo:
        return None
    valor = cuerpo["cobertura_nacional"]
    if not isinstance(valor, bool):
        raise SolicitudInvalida(detalle={"cobertura_nacional": ["Debe ser true o false."]})
    return valor


def _datos_para_el_formulario(organizacion: dict[str, Any]) -> dict[str, Any]:
    """El diccionario de la organizacion con las zonas bajo el nombre del campo del formulario.

    Una fila por provincia, con sus localidades juntas y separadas por comas: es la misma forma
    en que se cargan, asi que editar muestra lo que la persona escribio.
    """
    zonas = servicios.zonas_agrupadas_por_provincia(
        (zona["provincia"], zona["localidad"]) for zona in organizacion["zonas_de_cobertura"]
    )
    return {**organizacion, "zonas": zonas or [{}]}


def _contexto_del_formulario(organizacion_id: int | None = None) -> dict[str, Any]:
    return {
        "modo": "alta" if organizacion_id is None else "edicion",
        "organizacion": (
            servicios.a_diccionario(servicios.obtener(organizacion_id))
            if organizacion_id is not None
            else None
        ),
    }


def _contexto_de_mi_organizacion() -> dict[str, Any]:
    organizacion = servicios.obtener_propia(current_user.organizacion_id)
    return {"organizacion": servicios.a_diccionario(organizacion)}


@blueprint_organizaciones.get("")
@requiere_permiso(ORGANIZACIONES_LISTAR)
def listar():
    """Listado paginado de organizaciones.

    Filtra por tipo, estado y provincia de cobertura; el texto busca en el nombre, el
    identificador, el email de contacto y las localidades de cobertura.
    """
    pagina, por_pagina = parametros_de_paginacion()
    resultado = servicios.paginar_listado(
        pagina=pagina,
        por_pagina=por_pagina,
        tipo=request.args.get("tipo") or None,
        activo=parametro_booleano("activo"),
        texto=request.args.get("texto") or None,
        provincia=request.args.get("provincia") or None,
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
        opciones_de_provincia=OPCIONES_DE_PROVINCIA,
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
    """Detalle de una organizacion, con sus zonas de cobertura y las cuentas vinculadas."""
    datos = servicios.a_diccionario(servicios.obtener(organizacion_id))
    miembros = servicios.miembros(organizacion_id)
    if pide_json():
        return jsonify({**datos, "miembros": miembros})
    return render_template("organizaciones/detalle.html", organizacion=datos, miembros=miembros)


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
        zonas=_zonas_enviadas(formulario),
        cobertura_nacional=bool(_cobertura_nacional_enviada(formulario)),
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
        formulario=FormularioOrganizacion(data=_datos_para_el_formulario(contexto["organizacion"])),
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
        zonas=_zonas_enviadas(formulario),
        cobertura_nacional=_cobertura_nacional_enviada(formulario),
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


# --- Mi organizacion (miembros) -------------------------------------------------


@blueprint_organizaciones.get("/mia")
@requiere_permiso(ORGANIZACION_PROPIA_VER)
def mi_organizacion():
    """La organizacion de la cuenta en sesion: datos, cobertura y compañeros."""
    contexto = _contexto_de_mi_organizacion()
    miembros = servicios.miembros(contexto["organizacion"]["id"])
    if pide_json():
        return jsonify({**contexto["organizacion"], "miembros": miembros})
    return render_template("organizaciones/mi_organizacion.html", miembros=miembros, **contexto)


@blueprint_organizaciones.get("/mia/edicion")
@requiere_permiso(ORGANIZACION_PROPIA_EDITAR)
def formulario_de_mi_organizacion():
    """Pantalla de edicion del contacto y la cobertura de la propia organizacion."""
    contexto = _contexto_de_mi_organizacion()
    return render_template(
        "organizaciones/mi_organizacion_formulario.html",
        formulario=FormularioDatosPropios(data=_datos_para_el_formulario(contexto["organizacion"])),
        **contexto,
    )


@blueprint_organizaciones.post("/mia/edicion")
@requiere_permiso(ORGANIZACION_PROPIA_EDITAR)
@plantilla_ante_error(
    "organizaciones/mi_organizacion_formulario.html", contexto=_contexto_de_mi_organizacion
)
def editar_mi_organizacion():
    """Actualizacion del contacto y la cobertura por un miembro de la organizacion.

    Nombre, tipo, identificador y estado no viajan en este formulario: aunque un cliente los
    mande, `servicios.editar_datos_propios()` no los recibe.
    """
    formulario = construir_formulario(FormularioDatosPropios)
    validar_o_fallar(formulario)

    organizacion = servicios.obtener_propia(current_user.organizacion_id)
    zonas = _zonas_enviadas(formulario)
    if zonas is None:
        zonas = [servicios.zona_a_diccionario(zona) for zona in organizacion.zonas_de_cobertura]
    organizacion = servicios.editar_datos_propios(
        organizacion.id,
        contacto_email=formulario.contacto_email.data,
        contacto_telefono=formulario.contacto_telefono.data,
        direccion=formulario.direccion.data,
        zonas=zonas,
        cobertura_nacional=_cobertura_nacional_enviada(formulario),
    )
    return redirigir(
        "organizaciones.mi_organizacion",
        "Datos de tu organización actualizados.",
        datos_json=servicios.a_diccionario(organizacion),
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
