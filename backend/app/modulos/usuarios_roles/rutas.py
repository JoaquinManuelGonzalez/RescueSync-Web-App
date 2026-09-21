"""Endpoints de sesion y de gestion de cuentas.

Dos blueprints, porque son dos areas distintas y conviene que las URLs lo digan:

- `sesion` en `/sesion`: lo que hace cualquier usuario con su propia cuenta (entrar, salir,
  ver quien es, cambiar su contrasena).
- `usuarios` en `/usuarios`: el panel de gestion de cuentas. Cada ruta declara su permiso
  `usuarios:*`, que hoy solo tiene el rol administrador.

Formato de la respuesta
-----------------------
Hoy devuelven JSON, porque la plantilla de la interfaz todavia no existe. Los diccionarios que
arman `servicios.a_diccionario()` y `servicios.describir_sesion()` son exactamente el contexto
que va a recibir la plantilla: cuando llegue, cada vista suma su `render_template(...)` y ni el
servicio ni el formulario cambian.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user
from flask_wtf.csrf import generate_csrf

from app.core.autorizacion import requiere_autenticacion, requiere_permiso
from app.core.formularios import (
    construir_formulario,
    parametro_booleano,
    parametro_entero,
    validar_o_fallar,
)
from app.core.permisos import (
    USUARIOS_CAMBIAR_ESTADO,
    USUARIOS_CREAR,
    USUARIOS_EDITAR,
    USUARIOS_LISTAR,
    USUARIOS_RESTABLECER_CONTRASENA,
)
from app.core.sesion import cerrar_sesion, iniciar_sesion
from app.modulos.usuarios_roles import servicios
from app.modulos.usuarios_roles.formularios import (
    FormularioAltaDeUsuario,
    FormularioCambioDeContrasena,
    FormularioEdicionDeUsuario,
    FormularioEstadoDeUsuario,
    FormularioIngreso,
    FormularioRestablecerContrasena,
)

blueprint_sesion = Blueprint("sesion", __name__)
blueprint_usuarios = Blueprint("usuarios", __name__)


# --- Sesion -------------------------------------------------------------------


@blueprint_sesion.get("/token-csrf")
def token_csrf():
    """Entrega un token CSRF valido para la sesion en curso.

    PROVISIONAL. Existe solo mientras no haya formularios HTML: permite ejercitar los POST con
    `curl` y desde los tests. Cuando llegue la plantilla, el token viaja en el campo oculto que
    renderiza `{{ csrf_token() }}` y esta ruta se elimina.
    """
    return jsonify({"csrf_token": generate_csrf()})


@blueprint_sesion.post("/ingreso")
def ingresar():
    """Inicio de sesion por email y contraseña."""
    formulario = construir_formulario(FormularioIngreso)
    validar_o_fallar(formulario)

    usuario = servicios.autenticar(formulario.email.data, formulario.contrasena.data)
    iniciar_sesion(usuario)

    return jsonify(servicios.describir_sesion(usuario))


@blueprint_sesion.post("/cierre")
@requiere_autenticacion
def cerrar():
    """Cierre de sesion. Deja la cookie sin contenido utilizable."""
    cerrar_sesion()
    return jsonify({"mensaje": "Sesión cerrada."})


@blueprint_sesion.get("/actual")
@requiere_autenticacion
def actual():
    """Datos del usuario en sesión, con sus roles y permisos efectivos.

    Es lo que la interfaz va a consultar para armar el menú: qué ve cada perfil sale de acá y
    no de una lista de roles repetida en la plantilla.
    """
    return jsonify(servicios.describir_sesion(current_user))


@blueprint_sesion.post("/contrasena")
@requiere_autenticacion
def cambiar_contrasena():
    """Cambio de la contraseña propia."""
    formulario = construir_formulario(FormularioCambioDeContrasena)
    validar_o_fallar(formulario)

    servicios.cambiar_contrasena_propia(
        current_user,
        formulario.contrasena_actual.data,
        formulario.contrasena_nueva.data,
    )
    return jsonify({"mensaje": "Contraseña actualizada."})


# --- Gestion de cuentas (administrador) ---------------------------------------


@blueprint_usuarios.get("")
@requiere_permiso(USUARIOS_LISTAR)
def listar():
    """Listado de cuentas, filtrable por rol, organización, estado y texto."""
    usuarios = servicios.listar_usuarios(
        nombre_rol=request.args.get("rol") or None,
        organizacion_id=parametro_entero("organizacion_id"),
        activo=parametro_booleano("activo"),
        texto=request.args.get("texto") or None,
    )
    return jsonify({"usuarios": [servicios.a_diccionario(uno) for uno in usuarios]})


@blueprint_usuarios.get("/<int:usuario_id>")
@requiere_permiso(USUARIOS_LISTAR)
def ver(usuario_id: int):
    """Detalle de una cuenta."""
    return jsonify(servicios.a_diccionario(servicios.obtener_usuario(usuario_id)))


@blueprint_usuarios.post("")
@requiere_permiso(USUARIOS_CREAR)
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
    return jsonify(servicios.a_diccionario(usuario)), 201


@blueprint_usuarios.post("/<int:usuario_id>/edicion")
@requiere_permiso(USUARIOS_EDITAR)
def editar(usuario_id: int):
    """Edición del nombre, el rol y la organización de una cuenta."""
    formulario = construir_formulario(FormularioEdicionDeUsuario)
    validar_o_fallar(formulario)

    usuario = servicios.editar_usuario(
        usuario_id,
        nombre_completo=formulario.nombre_completo.data,
        nombre_rol=formulario.rol.data,
        organizacion_id=formulario.organizacion_id.data,
    )
    return jsonify(servicios.a_diccionario(usuario))


@blueprint_usuarios.post("/<int:usuario_id>/estado")
@requiere_permiso(USUARIOS_CAMBIAR_ESTADO)
def cambiar_estado(usuario_id: int):
    """Activación o desactivación de una cuenta."""
    formulario = construir_formulario(FormularioEstadoDeUsuario)
    validar_o_fallar(formulario)

    usuario = servicios.cambiar_estado(usuario_id, activo=bool(formulario.activo.data))
    return jsonify(servicios.a_diccionario(usuario))


@blueprint_usuarios.post("/<int:usuario_id>/contrasena")
@requiere_permiso(USUARIOS_RESTABLECER_CONTRASENA)
def restablecer_contrasena(usuario_id: int):
    """Asignación de una contraseña nueva por parte del administrador.

    Reemplaza al 'olvidé mi contraseña' por correo, que la épica deja fuera de alcance.
    """
    formulario = construir_formulario(FormularioRestablecerContrasena)
    validar_o_fallar(formulario)

    usuario = servicios.restablecer_contrasena(usuario_id, formulario.contrasena.data)
    return jsonify(servicios.a_diccionario(usuario))


@blueprint_usuarios.post("/<int:usuario_id>/desbloqueo")
@requiere_permiso(USUARIOS_RESTABLECER_CONTRASENA)
def desbloquear(usuario_id: int):
    """Levanta el bloqueo por intentos fallidos, sin tocar la contraseña."""
    return jsonify(servicios.a_diccionario(servicios.desbloquear(usuario_id)))
