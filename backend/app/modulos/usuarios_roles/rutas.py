"""Endpoints de sesion y de gestion de cuentas.

Dos blueprints, porque son dos areas distintas y conviene que las URLs lo digan:

- `sesion` en `/sesion`: lo que hace cualquier usuario con su propia cuenta (entrar, salir,
  ver quien es, cambiar su contrasena).
- `usuarios` en `/usuarios`: el panel de gestion de cuentas. Cada ruta declara su permiso
  `usuarios:*`, que hoy solo tiene el rol administrador.

Formato de la respuesta
-----------------------
La misma ruta sirve a la interfaz y a los clientes JSON (ver `app.core.interfaz.vistas`):

- Los GET devuelven la pantalla al navegador y el diccionario de `servicios.a_diccionario()`
  o `servicios.describir_sesion()` a un cliente JSON. Ese diccionario es tambien el contexto
  de la plantilla.
- Los POST responden con `redirigir(...)`: redirect con mensaje al navegador (Post/Redirect/Get)
  y JSON al resto. Si fallan, `@plantilla_ante_error` vuelve a mostrar el formulario con sus
  errores; la vista no escribe ningun `try`.
- Las pantallas de formulario son GET con funcion propia (`formulario_de_*`) sobre la misma URL
  que el POST que las procesa.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from app.core.acceso.autorizacion import requiere_autenticacion, requiere_permiso
from app.core.acceso.permisos import (
    TIPO_DE_ORGANIZACION_POR_ROL,
    USUARIOS_CAMBIAR_ESTADO,
    USUARIOS_CREAR,
    USUARIOS_EDITAR,
    USUARIOS_LISTAR,
    USUARIOS_RESTABLECER_CONTRASENA,
)
from app.core.acceso.sesion import cerrar_sesion, iniciar_sesion
from app.core.interfaz.formularios import (
    construir_formulario,
    parametro_booleano,
    parametro_id,
    validar_o_fallar,
)
from app.core.interfaz.navegacion import EntradaDeMenu
from app.core.interfaz.paginacion import parametros_de_paginacion
from app.core.interfaz.vistas import destino_seguro, pide_json, plantilla_ante_error, redirigir
from app.modulos.organizaciones import servicios as servicios_de_organizaciones
from app.modulos.usuarios_roles import servicios
from app.modulos.usuarios_roles.formularios import (
    OPCIONES_DE_ROL,
    FormularioAltaDeUsuario,
    FormularioCambioDeContrasena,
    FormularioEdicionDeUsuario,
    FormularioEstadoDeUsuario,
    FormularioIngreso,
    FormularioRestablecerContrasena,
)

blueprint_sesion = Blueprint("sesion", __name__)
blueprint_usuarios = Blueprint("usuarios", __name__)

ENTRADA_DE_MENU = EntradaDeMenu(
    endpoint="usuarios.listar",
    titulo="Usuarios",
    permiso=USUARIOS_LISTAR,
    descripcion="Alta y gestión de cuentas",
    icono="usuarios",
    orden=10,
)

OPCIONES_DE_ESTADO = [("true", "Activas"), ("false", "Inactivas")]


# --- Sesion -------------------------------------------------------------------


def _contexto_de_ingreso() -> dict[str, Any]:
    return {"siguiente": destino_seguro(request.values.get("next"))}


@blueprint_sesion.get("/ingreso")
def formulario_de_ingreso():
    """Pantalla de inicio de sesion. Publica a proposito: es la puerta de entrada."""
    if current_user.is_authenticated:
        return redirect(url_for("inicio.panel"))
    return render_template("login.html", formulario=FormularioIngreso(), **_contexto_de_ingreso())


@blueprint_sesion.post("/ingreso")
@plantilla_ante_error("login.html", contexto=_contexto_de_ingreso)
def ingresar():
    """Inicio de sesion por email y contraseña. Publica a proposito.

    En el navegador vuelve a la pantalla que la persona intentaba abrir (`next`), si es de esta
    misma aplicacion; si no, al panel de inicio.
    """
    formulario = construir_formulario(FormularioIngreso)
    validar_o_fallar(formulario)

    usuario = servicios.autenticar(formulario.email.data, formulario.contrasena.data)
    iniciar_sesion(usuario)

    if pide_json():
        return jsonify(servicios.describir_sesion(usuario))
    return redirect(destino_seguro(request.form.get("next")) or url_for("inicio.panel"))


@blueprint_sesion.post("/cierre")
@requiere_autenticacion
def cerrar():
    """Cierre de sesion. Deja la cookie sin contenido utilizable."""
    cerrar_sesion()
    return redirigir("inicio.raiz", "Sesión cerrada.")


@blueprint_sesion.get("/actual")
@requiere_autenticacion
def actual():
    """Datos del usuario en sesión, con sus roles y permisos efectivos.

    En el navegador es la pantalla "Mi perfil".
    """
    datos = servicios.describir_sesion(current_user)
    if pide_json():
        return jsonify(datos)
    return render_template("sesion/perfil.html", sesion=datos)


@blueprint_sesion.get("/contrasena")
@requiere_autenticacion
def formulario_de_contrasena():
    """Pantalla de cambio de la contraseña propia."""
    return render_template("sesion/contrasena.html", formulario=FormularioCambioDeContrasena())


@blueprint_sesion.post("/contrasena")
@requiere_autenticacion
@plantilla_ante_error("sesion/contrasena.html")
def cambiar_contrasena():
    """Cambio de la contraseña propia."""
    formulario = construir_formulario(FormularioCambioDeContrasena)
    validar_o_fallar(formulario)

    servicios.cambiar_contrasena_propia(
        current_user,
        formulario.contrasena_actual.data,
        formulario.contrasena_nueva.data,
    )
    return redirigir("inicio.panel", "Contraseña actualizada.")


# --- Gestion de cuentas (administrador) ---------------------------------------


def _opciones_de_organizacion(*, solo_activas: bool) -> list[tuple[int, str, str]]:
    """Organizaciones para los select de la interfaz: (id, nombre, tipo)."""
    organizaciones = servicios_de_organizaciones.listar(activo=True if solo_activas else None)
    return [(una.id, una.nombre, una.tipo.value) for una in organizaciones]


def _contexto_del_formulario(usuario_id: uuid.UUID | None = None) -> dict[str, Any]:
    """Lo que la plantilla de alta y edicion necesita además del formulario."""
    tipos_por_rol = {rol.value: tipo for rol, tipo in TIPO_DE_ORGANIZACION_POR_ROL.items()}
    return {
        "modo": "alta" if usuario_id is None else "edicion",
        "usuario": (
            servicios.a_diccionario(servicios.obtener_usuario(usuario_id))
            if usuario_id is not None
            else None
        ),
        "opciones_de_organizacion": _opciones_de_organizacion(solo_activas=True),
        # Texto JSON y no un dict: viaja en un atributo data-* y lo lee interfaz.js.
        "tipos_por_rol": json.dumps(tipos_por_rol),
    }


def _contexto_del_detalle(usuario_id: uuid.UUID) -> dict[str, Any]:
    return {
        "usuario": servicios.a_diccionario(servicios.obtener_usuario(usuario_id)),
        "formulario_contrasena": FormularioRestablecerContrasena(formdata=None),
    }


@blueprint_usuarios.get("")
@requiere_permiso(USUARIOS_LISTAR)
def listar():
    """Listado paginado de cuentas, filtrable por rol, organización, estado y texto."""
    pagina, por_pagina = parametros_de_paginacion()
    resultado = servicios.paginar_usuarios(
        pagina=pagina,
        por_pagina=por_pagina,
        nombre_rol=request.args.get("rol") or None,
        organizacion_id=parametro_id("organizacion_id"),
        activo=parametro_booleano("activo"),
        texto=request.args.get("texto") or None,
    ).mapear(servicios.a_diccionario)
    if pide_json():
        return jsonify({"usuarios": resultado.elementos, "paginacion": resultado.a_diccionario()})
    return render_template(
        "usuarios/listado.html",
        usuarios=resultado.elementos,
        pagina=resultado,
        filtros=request.args,
        opciones_de_rol=OPCIONES_DE_ROL,
        opciones_de_organizacion=[
            (valor, texto) for valor, texto, _ in _opciones_de_organizacion(solo_activas=False)
        ],
        opciones_de_estado=OPCIONES_DE_ESTADO,
    )


@blueprint_usuarios.get("/nuevo")
@requiere_permiso(USUARIOS_CREAR)
def formulario_de_alta():
    """Pantalla de alta de una cuenta.

    Con `?organizacion_id=` (el boton "Vincular cuenta" del detalle de una organizacion) llega
    con esa organizacion y el rol que su tipo exige ya elegidos.
    """
    return render_template(
        "usuarios/formulario.html",
        formulario=FormularioAltaDeUsuario(data=_datos_de_vinculo(parametro_id("organizacion_id"))),
        **_contexto_del_formulario(),
    )


def _datos_de_vinculo(organizacion_id: uuid.UUID | None) -> dict[str, Any]:
    """Organizacion y rol para precargar el alta, o nada si la organizacion no existe."""
    if organizacion_id is None:
        return {}
    tipo = servicios_de_organizaciones.obtener_tipo_de_organizacion(organizacion_id)
    if tipo is None:
        return {}
    rol = next(
        (rol for rol, exigido in TIPO_DE_ORGANIZACION_POR_ROL.items() if exigido == tipo),
        None,
    )
    if rol is None:
        return {}
    return {"organizacion_id": organizacion_id, "rol": rol.value}


@blueprint_usuarios.get("/<uuid:usuario_id>")
@requiere_permiso(USUARIOS_LISTAR)
def ver(usuario_id: uuid.UUID):
    """Detalle de una cuenta."""
    if pide_json():
        return jsonify(servicios.a_diccionario(servicios.obtener_usuario(usuario_id)))
    return render_template("usuarios/detalle.html", **_contexto_del_detalle(usuario_id))


@blueprint_usuarios.post("")
@requiere_permiso(USUARIOS_CREAR)
@plantilla_ante_error("usuarios/formulario.html", contexto=_contexto_del_formulario)
def crear():
    """Alta de una cuenta.

    Nace marcada para cambiar la contraseña: la clave inicial la elige el administrador y
    viaja por un canal externo al sistema, así que no debe quedar en uso.
    """
    formulario = construir_formulario(FormularioAltaDeUsuario)
    validar_o_fallar(formulario)

    usuario = servicios.crear_usuario(
        email=formulario.email.data,
        nombre_completo=formulario.nombre_completo.data,
        contrasena=formulario.contrasena.data,
        nombre_rol=formulario.rol.data,
        organizacion_id=formulario.organizacion_id.data,
    )
    return redirigir(
        "usuarios.ver",
        "Cuenta creada. La persona deberá cambiar la contraseña en su primer ingreso.",
        datos_json=servicios.a_diccionario(usuario),
        estado_json=201,
        usuario_id=usuario.id,
    )


@blueprint_usuarios.get("/<uuid:usuario_id>/edicion")
@requiere_permiso(USUARIOS_EDITAR)
def formulario_de_edicion(usuario_id: uuid.UUID):
    """Pantalla de edición de una cuenta, precargada con sus datos actuales."""
    usuario = servicios.obtener_usuario(usuario_id)
    formulario = FormularioEdicionDeUsuario(
        data={
            "nombre_completo": usuario.nombre_completo,
            "rol": usuario.rol_principal,
            "organizacion_id": usuario.organizacion_id,
        }
    )
    return render_template(
        "usuarios/formulario.html",
        formulario=formulario,
        **_contexto_del_formulario(usuario_id),
    )


@blueprint_usuarios.post("/<uuid:usuario_id>/edicion")
@requiere_permiso(USUARIOS_EDITAR)
@plantilla_ante_error("usuarios/formulario.html", contexto=_contexto_del_formulario)
def editar(usuario_id: uuid.UUID):
    """Edición del nombre, el rol y la organización de una cuenta."""
    formulario = construir_formulario(FormularioEdicionDeUsuario)
    validar_o_fallar(formulario)

    usuario = servicios.editar_usuario(
        usuario_id,
        nombre_completo=formulario.nombre_completo.data,
        nombre_rol=formulario.rol.data,
        organizacion_id=formulario.organizacion_id.data,
    )
    return redirigir(
        "usuarios.ver",
        "Cambios guardados.",
        datos_json=servicios.a_diccionario(usuario),
        usuario_id=usuario.id,
    )


@blueprint_usuarios.post("/<uuid:usuario_id>/estado")
@requiere_permiso(USUARIOS_CAMBIAR_ESTADO)
def cambiar_estado(usuario_id: uuid.UUID):
    """Activación o desactivación de una cuenta."""
    formulario = construir_formulario(FormularioEstadoDeUsuario)
    validar_o_fallar(formulario)

    usuario = servicios.cambiar_estado(usuario_id, activo=bool(formulario.activo.data))
    return redirigir(
        "usuarios.ver",
        "Cuenta activada." if usuario.activo else "Cuenta desactivada.",
        datos_json=servicios.a_diccionario(usuario),
        usuario_id=usuario.id,
    )


@blueprint_usuarios.post("/<uuid:usuario_id>/contrasena")
@requiere_permiso(USUARIOS_RESTABLECER_CONTRASENA)
@plantilla_ante_error(
    "usuarios/detalle.html",
    contexto=_contexto_del_detalle,
    nombre_formulario="formulario_contrasena",
)
def restablecer_contrasena(usuario_id: uuid.UUID):
    """Asignación de una contraseña nueva por parte del administrador.

    Reemplaza al 'olvidé mi contraseña' por correo, que la épica deja fuera de alcance.
    """
    formulario = construir_formulario(FormularioRestablecerContrasena)
    validar_o_fallar(formulario)

    usuario = servicios.restablecer_contrasena(usuario_id, formulario.contrasena.data)
    return redirigir(
        "usuarios.ver",
        "Contraseña restablecida. La persona deberá cambiarla en su próximo ingreso.",
        datos_json=servicios.a_diccionario(usuario),
        usuario_id=usuario.id,
    )


@blueprint_usuarios.post("/<uuid:usuario_id>/desbloqueo")
@requiere_permiso(USUARIOS_RESTABLECER_CONTRASENA)
def desbloquear(usuario_id: uuid.UUID):
    """Levanta el bloqueo por intentos fallidos, sin tocar la contraseña."""
    usuario = servicios.desbloquear(usuario_id)
    return redirigir(
        "usuarios.ver",
        "Cuenta desbloqueada.",
        datos_json=servicios.a_diccionario(usuario),
        usuario_id=usuario.id,
    )
