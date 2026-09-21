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
