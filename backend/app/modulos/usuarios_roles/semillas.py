"""Datos semilla del RBAC: permisos, roles, vinculos y una cuenta por perfil.

La fuente de verdad es `app/core/permisos.py`; este modulo se limita a volcarla a la base.
Volver a correr `flask seed` despues de agregar un permiso al catalogo crea el permiso que
falta y **resincroniza la matriz de cada rol**, de modo que el catalogo en codigo y la base
nunca se separan.

Contrasena de las cuentas de demostracion
-----------------------------------------
Sale de `SEMILLA_CONTRASENA` y nunca esta escrita en este archivo. Las cuentas sembradas nacen
con `debe_cambiar_contrasena = False` a proposito: son cuentas de demostracion de un entorno
descartable, y obligar a cambiar la clave en cada una convertiria cualquier prueba en seis
cambios de contrasena. La marca se sigue demostrando con las cuentas que crea el administrador
desde el panel, que siempre nacen con ella en True.
"""

from __future__ import annotations

from flask import current_app
from sqlalchemy import select

from app.core.permisos import (
    CATALOGO_DE_PERMISOS,
    DESCRIPCION_POR_ROL,
    PERMISOS_POR_ROL,
    NombreRol,
)
from app.core.seguridad import hashear_contrasena
from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.extensiones import db
from app.modulos.organizaciones.modelos import Organizacion
from app.modulos.usuarios_roles.modelos import Permiso, Rol, Usuario

# email, rol, nombre de la organizacion a la que pertenece (None = sin organizacion).
USUARIOS_DE_DEMOSTRACION: tuple[tuple[str, NombreRol, str | None], ...] = (
    ("admin@rescuesync.test", NombreRol.ADMINISTRADOR, None),
    ("auditor@rescuesync.test", NombreRol.AUDITOR, None),
    (
        "coordinador@rescuesync.test",
        NombreRol.COORDINADOR_REGIONAL,
        "Centro Coordinador Regional Buenos Aires",
    ),
    ("operador@chascomus.test", NombreRol.OPERADOR_MUNICIPAL, "Municipio de Chascomús"),
    ("representante@cruzsolidaria.test", NombreRol.REPRESENTANTE_ONG, "Cruz Solidaria"),
    ("representante@manosunidas.test", NombreRol.REPRESENTANTE_ONG, "Manos Unidas"),
)

NOMBRE_COMPLETO_POR_ROL: dict[NombreRol, str] = {
    NombreRol.ADMINISTRADOR: "Administrador de RescueSync",
    NombreRol.AUDITOR: "Auditora directiva",
    NombreRol.COORDINADOR_REGIONAL: "Coordinadora regional",
    NombreRol.OPERADOR_MUNICIPAL: "Operador municipal",
    NombreRol.REPRESENTANTE_ONG: "Representante de la ONG",
}


def _contrasena_de_demostracion() -> str:
    return str(current_app.config["SEMILLA_CONTRASENA"])


@registrar("permisos")
def sembrar_permisos() -> list[ResultadoSemilla]:
    """Crea un permiso por cada entrada del catálogo de `core/permisos.py`."""
    resultado = ResultadoSemilla("permisos")

    for codigo, descripcion in CATALOGO_DE_PERMISOS.items():
        _, fue_creado = obtener_o_crear(
            Permiso,
            claves={"nombre": codigo},
            valores={"descripcion": descripcion},
        )
        resultado.contar(fue_creado)

    return [resultado]


@registrar("roles")
def sembrar_roles() -> list[ResultadoSemilla]:
    """Crea los cinco roles y deja sus permisos exactamente como los declara la matriz.

    Los permisos se **reasignan** en cada corrida, no solo al crear el rol: es lo que hace que
    agregar una acción al catálogo y volver a correr `flask seed` alcance para que el rol la
    tenga, sin tener que borrar la base.
    """
    resultado = ResultadoSemilla("roles")
    permisos_por_codigo = {
        permiso.nombre: permiso for permiso in db.session.execute(select(Permiso)).scalars()
    }

    for nombre_rol, codigos in PERMISOS_POR_ROL.items():
        rol, fue_creado = obtener_o_crear(
            Rol,
            claves={"nombre": nombre_rol.value},
            valores={"descripcion": DESCRIPCION_POR_ROL[nombre_rol]},
        )
        rol.permisos = [permisos_por_codigo[codigo] for codigo in sorted(codigos)]
        resultado.contar(fue_creado)

    return [resultado]


@registrar("usuarios")
def sembrar_usuarios() -> list[ResultadoSemilla]:
    """Crea una cuenta por perfil, asociada a la organización que su rol exige."""
    resultado = ResultadoSemilla("usuarios")

    roles_por_nombre = {rol.nombre: rol for rol in db.session.execute(select(Rol)).scalars()}
    organizaciones_por_nombre = {
        org.nombre: org for org in db.session.execute(select(Organizacion)).scalars()
    }
    hash_compartido = hashear_contrasena(_contrasena_de_demostracion())

    for email, nombre_rol, nombre_organizacion in USUARIOS_DE_DEMOSTRACION:
        organizacion = (
            organizaciones_por_nombre[nombre_organizacion] if nombre_organizacion else None
        )

        usuario, fue_creado = obtener_o_crear(
            Usuario,
            claves={"email": email},
            valores={
                "nombre_completo": NOMBRE_COMPLETO_POR_ROL[nombre_rol],
                "hash_contrasena": hash_compartido,
                "organizacion_id": organizacion.id if organizacion else None,
                "activo": True,
                "debe_cambiar_contrasena": False,
            },
        )
        # Tambien en las cuentas ya existentes: si se agrega un rol al catalogo, la cuenta de
        # demostracion de ese perfil queda con el rol correcto sin recrear la base.
        usuario.roles = [roles_por_nombre[nombre_rol.value]]
        resultado.contar(fue_creado, email=email)

    return [resultado]
