"""Datos semilla para el módulo de usuarios, roles y permisos (RBAC)."""

from __future__ import annotations

from app.core.seguridad import hashear_contrasena
from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.modulos.organizaciones.modelos import Organizacion
from app.modulos.usuarios_roles.modelos import Permiso, Rol, Usuario

# # # # # # # # # # # # Permisos atómicos # # # # # # # # # # # #
# El nombre es el código que se consulta desde `Usuario.tiene_permiso(...)`.
# Por ahora defino los permisos báscios de CRUD.
# De ser necesario, se pueden agregar o especificar permisos.
# Listado de permisos irá creciendo con el tiempo
PERMISOS: list[tuple[str, str]] = [
    ("organizaciones:crear", "Dar de alta una nueva organización"),
    ("organizaciones:editar", "Editar la organizacion de pertenencia"),
    ("organizaciones:listar", "Listar organizaciones existentes"),
    ("organizaciones:borrar", "Borrado lógico de una organización"),
    ("organizaciones:mostrar", "Mostrar detalle de una organización existente"),
    ("emergencias:crear", "Registrar una nueva emergencia"),
    ("emergencias:editar", "Modificar una emergencia existente"),
    ("emergencias:listar", "Listar emergencias existentes"),
    ("emergencias:borrar", "Borrado lógico de una emergencia"),
    ("emergencias:mostrar", "Mostrar detalle de una emergencia existente"),
    ("ofertas:crear", "Publicar una oferta de ayuda"),
    ("ofertas:editar", "Editar ofertas propias"),
    ("ofertas:listar", "Listar ofertas existentes"),
    ("ofertas:borrar", "Borrado lógico de una oferta"),
    ("ofertas:mostrar", "Mostrar detalle de una oferta existente"),
    ("usuarios:crear", "Crear un nuevo usuario"),
    ("usuarios:editar", "Editar perfil usuario"),
    ("usuarios:listar", "Listar usuarios existentes"),
    ("usuarios:borrar", "Borrado lógico de un usuario"),
    ("usuarios:mostrar", "Mostrar detalle de un usuario existente"),
]

# # # # # # # # # # # # Roles y los permisos que agrupan # # # # # # # # # # # #
ROLES: dict[str, dict] = {
    "operador_municipal": {
        "descripcion": "Operador de un municipio que gestiona emergencias locales.",
        "permisos": [
            "emergencias:crear",
            "emergencias:editar",
            "emergencias:mostrar",
            "usuarios:editar",
            "usuarios:mostrar",
            "ofertas:editar",
            "ofertas:listar",
            "ofertas:mostrar",
        ],
    },
    "coordinador_regional": {
        "descripcion": "Coordina esfuerzos en contextos de emergencia a nivel regional.",
        "permisos": [
            "organizaciones:listar",
            "emergencias:crear",
            "emergencias:listar",
            "emergencias:mostrar",
            "ofertas:listar",
            "ofertas:mostrar",
        ],
    },
    "representante_ong": {
        "descripcion": "Representante de una ONG que postula ofertas de ayuda.",
        "permisos": [
            "organizaciones:editar",
            "organizaciones:mostrar",
            "ofertas:crear",
            "ofertas:editar",
            "ofertas:listar",
            "ofertas:mostrar",
        ],
    },
    "auditor": {
        "descripcion": "Revisa bitácoras sin modificar datos operativos.",
        "permisos": [
            "organizaciones:listar",
            "organizaciones:mostrar",
            "emergencias:listar",
            "emergencias:mostrar",
            "ofertas:listar",
            "ofertas:mostrar",
            "usuarios:listar",
            "usuarios:mostrar",
        ],
    },
    "admin": {
        "descripcion": "Administrador del sistema con acceso total.",
        "permisos": [p[0] for p in PERMISOS],  # todos
    },
}

# # # # # # # # # # # # Usuarios # # # # # # # # # # # #
# Contraseña única para todos: "Contra123!" (solo entorno de desarrollo).
PASSWORD_SEMILLA = "Contra123!"

USUARIOS: list[dict] = [
    {
        "email": "admin@test.com",
        "nombre_completo": "Abril Álvarez",
        "roles": ["admin"],
    },
    {
        "email": "operador_municipal1@test.com",
        "nombre_completo": "Beatriz Bertoldi",
        "roles": ["operador_municipal"],
        "organizacion_nombre": "Municipalidad de Bahía Blanca",
    },
    {
        "email": "operador_municipal2@test.com",
        "nombre_completo": "Camila Calle",
        "roles": ["operador_municipal"],
        "organizacion_nombre": "Municipalidad de Pergamino",
    },
    {
        "email": "operador_municipal3@test.com",
        "nombre_completo": "Daniel Daer",
        "roles": ["operador_municipal"],
        "organizacion_nombre": "Municipalidad de La Plata",
    },
    {
        "email": "coordinador_regional1@test.com",
        "nombre_completo": "Estela Echeverría",
        "roles": ["coordinador_regional"],
    },
    {
        "email": "coordinador_regional2@test.com",
        "nombre_completo": "Franco Ferro",
        "roles": ["coordinador_regional"],
    },
    {
        "email": "ong1@test.com",
        "nombre_completo": "Graciela Gratarolla",
        "roles": ["representante_ong"],
        "organizacion_nombre": "Bomberos Voluntarios de La Plata",
    },
    {
        "email": "ong2@test.com",
        "nombre_completo": "Héctor Heredia",
        "roles": ["representante_ong"],
        "organizacion_nombre": "Cruz Roja Argentina - Filial Bahía Blanca",
    },
    {
        "email": "ong3@test.com",
        "nombre_completo": "Inés Insaurralde",
        "roles": ["representante_ong"],
        "organizacion_nombre": "Grupo Scouts de Pergamino",
    },
    {
        "email": "auditor@test.com",
        "nombre_completo": "Javier Justo",
        "roles": ["auditor"],
    },
]


@registrar("permisos")
def sembrar_permisos() -> list[ResultadoSemilla]:
    resultado = ResultadoSemilla("permisos")
    for nombre, descripcion in PERMISOS:
        _, creado = obtener_o_crear(
            Permiso,
            claves={"nombre": nombre},
            valores={"descripcion": descripcion},
        )
        resultado.contar(creado)
    return [resultado]


@registrar("roles")
def sembrar_roles() -> list[ResultadoSemilla]:
    resultado = ResultadoSemilla("roles")
    for nombre, datos in ROLES.items():
        rol, creado = obtener_o_crear(
            Rol,
            claves={"nombre": nombre},
            valores={"descripcion": datos["descripcion"]},
        )
        # Asociar permisos (idempotente: `set` de ORM no duplica filas en la M:N).
        permisos_orm = Permiso.query.filter(Permiso.nombre.in_(datos["permisos"])).all()
        rol.permisos = permisos_orm
        resultado.contar(creado)
    return [resultado]


@registrar("usuarios")
def sembrar_usuarios() -> list[ResultadoSemilla]:
    resultado = ResultadoSemilla("usuarios")
    for datos in USUARIOS:
        organizacion = None
        if nombre_org := datos.get("organizacion_nombre"):
            organizacion = Organizacion.query.filter_by(nombre=nombre_org).first()

        usuario, creado = obtener_o_crear(
            Usuario,
            claves={"email": datos["email"]},
            valores={
                "nombre_completo": datos["nombre_completo"],
                "hash_contrasena": hashear_contrasena(PASSWORD_SEMILLA),
                "activo": True,
                "organizacion_id": organizacion.id if organizacion else None,
            },
        )
        if creado:
            usuario.roles = Rol.query.filter(Rol.nombre.in_(datos["roles"])).all()
        resultado.contar(creado, email=datos["email"])
    return [resultado]

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
