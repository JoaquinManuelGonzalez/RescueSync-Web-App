"""Catalogo de roles y permisos de RescueSync.

Este modulo es la **fuente de verdad en codigo** del RBAC. La base de datos no decide nada:
`app/modulos/usuarios_roles/semillas.py` la llena a partir de lo que se declara aca, y
`flask seed` puede volver a correr las veces que haga falta sin duplicar ni desincronizar.

Por que un catalogo y no literales sueltos
------------------------------------------
La hipotesis de beneficio de la epica es que agregar una pantalla nueva no requiera codigo de
autorizacion propio, solo declarar el permiso. Eso solo se cumple si el permiso existe como
constante en un unico lugar: si cada ruta inventa su string, el primer error de tipeo abre un
agujero silencioso (un permiso mal escrito en un decorador no coincide con ninguno de la base y
la ruta queda inalcanzable; mal escrito en la matriz, el rol se queda sin el permiso y nadie lo
nota hasta la demostracion).

Como agregar un permiso nuevo
-----------------------------
1. Agregar la constante en la seccion del recurso que corresponda.
2. Sumarla a `CATALOGO_DE_PERMISOS` con su descripcion legible.
3. Sumarla al `frozenset` de cada rol que deba tenerla en `PERMISOS_POR_ROL`.
4. Correr `flask seed`: el seeder crea el permiso y los vinculos que falten.

No hace falta tocar ninguna ruta ni ningun decorador.

Convencion de nombres
---------------------
`recurso:accion`, todo en minusculas y sin tildes, como ya anticipaba el docstring de
`modelos.py`. El recurso va en plural cuando nombra una entidad (`usuarios`, `ofertas`) y en
singular cuando nombra un area de trabajo (`inventario`, `ejecucion`).
"""

from __future__ import annotations

from enum import StrEnum

# --- Roles --------------------------------------------------------------------


class NombreRol(StrEnum):
    """Los perfiles del sistema.

    Los cuatro primeros son los que exige el enunciado de la catedra. `ADMINISTRADOR` es un
    quinto perfil operativo que no participa del proceso BPMN: existe unicamente para dar de
    alta cuentas y organizaciones, porque en RescueSync no hay autorregistro. Ver
    docs/adr/ADR-009-autenticacion-y-rbac.md.
    """

    OPERADOR_MUNICIPAL = "operador_municipal"
    COORDINADOR_REGIONAL = "coordinador_regional"
    REPRESENTANTE_ONG = "representante_ong"
    AUDITOR = "auditor"
    ADMINISTRADOR = "administrador"


DESCRIPCION_POR_ROL: dict[NombreRol, str] = {
    NombreRol.OPERADOR_MUNICIPAL: (
        "Opera por un municipio: registra emergencias y selecciona las ofertas a adjudicar."
    ),
    NombreRol.COORDINADOR_REGIONAL: (
        "Opera por el Centro Coordinador Regional: revisa emergencias, arma lotes de necesidad, "
        "publica convocatorias y registra la adjudicación."
    ),
    NombreRol.REPRESENTANTE_ONG: (
        "Opera por una ONG: gestiona su inventario, presenta y edita ofertas de ayuda y marca "
        "sus actividades como finalizadas."
    ),
    NombreRol.AUDITOR: (
        "Perfil directivo de solo lectura: consulta el estado del proceso y los indicadores."
    ),
    NombreRol.ADMINISTRADOR: (
        "Administra cuentas y organizaciones. No participa del proceso de emergencias."
    ),
}


# --- Tipo de organizacion exigido por cada rol --------------------------------

# Se expresa como el *valor* del enum TipoOrganizacion y no importando el enum, porque la regla
# de dependencia de docs/arquitectura/componentes.md seccion 5 prohibe que un modulo importe los
# modelos de otro: la verificacion se hace contra lo que devuelve organizaciones.servicios.
TIPO_MUNICIPIO = "municipio"
TIPO_ONG = "ong"
TIPO_CENTRO_COORDINADOR = "centro_coordinador_regional"

# None significa que el rol NO debe tener organizacion asociada.
TIPO_DE_ORGANIZACION_POR_ROL: dict[NombreRol, str | None] = {
    NombreRol.OPERADOR_MUNICIPAL: TIPO_MUNICIPIO,
    NombreRol.COORDINADOR_REGIONAL: TIPO_CENTRO_COORDINADOR,
    NombreRol.REPRESENTANTE_ONG: TIPO_ONG,
    NombreRol.AUDITOR: None,
    NombreRol.ADMINISTRADOR: None,
}


# --- Permisos -----------------------------------------------------------------

# Gestion de cuentas y organizaciones (solo administrador).
USUARIOS_LISTAR = "usuarios:listar"
USUARIOS_CREAR = "usuarios:crear"
USUARIOS_EDITAR = "usuarios:editar"
USUARIOS_CAMBIAR_ESTADO = "usuarios:cambiar_estado"
USUARIOS_RESTABLECER_CONTRASENA = "usuarios:restablecer_contrasena"

ORGANIZACIONES_LISTAR = "organizaciones:listar"
ORGANIZACIONES_CREAR = "organizaciones:crear"
ORGANIZACIONES_EDITAR = "organizaciones:editar"
ORGANIZACIONES_CAMBIAR_ESTADO = "organizaciones:cambiar_estado"

# Etapa 1 del proceso: registro de la emergencia.
EMERGENCIAS_CREAR = "emergencias:crear"
EMERGENCIAS_LISTAR = "emergencias:listar"
EMERGENCIAS_VER = "emergencias:ver"
EMERGENCIAS_EDITAR = "emergencias:editar"

# Etapa 2: lotes de necesidad y convocatoria.
LOTES_CREAR = "lotes:crear"
LOTES_EDITAR = "lotes:editar"
LOTES_LISTAR = "lotes:listar"

CONVOCATORIAS_CREAR = "convocatorias:crear"
CONVOCATORIAS_PUBLICAR = "convocatorias:publicar"
CONVOCATORIAS_CERRAR = "convocatorias:cerrar"
CONVOCATORIAS_LISTAR = "convocatorias:listar"

# Etapa 3: ofertas de ayuda de las ONG.
OFERTAS_CREAR = "ofertas:crear"
OFERTAS_EDITAR = "ofertas:editar"
OFERTAS_RETIRAR = "ofertas:retirar"
OFERTAS_LISTAR = "ofertas:listar"

INVENTARIO_VER = "inventario:ver"
INVENTARIO_EDITAR = "inventario:editar"

# Etapa 5: adjudicacion.
ADJUDICACIONES_SELECCIONAR = "adjudicaciones:seleccionar"
ADJUDICACIONES_REGISTRAR = "adjudicaciones:registrar"
ADJUDICACIONES_LISTAR = "adjudicaciones:listar"

# Etapa 7: ejecucion y cierre.
EJECUCION_MARCAR_ACTIVIDAD = "ejecucion:marcar_actividad"
EJECUCION_INFORMAR_FINALIZACION = "ejecucion:informar_finalizacion"
EJECUCION_MONITOREAR = "ejecucion:monitorear"

# Dashboard del perfil Auditor/Directivo (entrega final).
INDICADORES_VER = "indicadores:ver"
INDICADORES_EXPORTAR = "indicadores:exportar"


# Codigo -> descripcion legible, que viaja a la columna `permisos.descripcion`.
# El catalogo cubre todo el proceso BPMN y no solo esta epica, para que las epicas siguientes
# declaren su permiso en la ruta y no tengan que volver a tocar el RBAC.
CATALOGO_DE_PERMISOS: dict[str, str] = {
    USUARIOS_LISTAR: "Ver el listado y el detalle de las cuentas de usuario.",
    USUARIOS_CREAR: "Dar de alta una cuenta de usuario.",
    USUARIOS_EDITAR: "Editar los datos y los roles de una cuenta de usuario.",
    USUARIOS_CAMBIAR_ESTADO: "Activar o desactivar una cuenta de usuario.",
    USUARIOS_RESTABLECER_CONTRASENA: (
        "Asignar una contraseña nueva a una cuenta y levantar su bloqueo."
    ),
    ORGANIZACIONES_LISTAR: "Ver el listado y el detalle de municipios, ONGs y centros.",
    ORGANIZACIONES_CREAR: "Dar de alta una organización.",
    ORGANIZACIONES_EDITAR: "Editar los datos de una organización.",
    ORGANIZACIONES_CAMBIAR_ESTADO: "Activar o desactivar una organización.",
    EMERGENCIAS_CREAR: "Registrar una emergencia nueva.",
    EMERGENCIAS_LISTAR: "Ver el listado de emergencias.",
    EMERGENCIAS_VER: "Ver el detalle de una emergencia.",
    EMERGENCIAS_EDITAR: "Editar los datos de una emergencia.",
    LOTES_CREAR: "Generar lotes de necesidad para una emergencia.",
    LOTES_EDITAR: "Reformular los lotes de necesidad de una emergencia.",
    LOTES_LISTAR: "Ver los lotes de necesidad de una emergencia.",
    CONVOCATORIAS_CREAR: "Crear una convocatoria sobre los lotes de una emergencia.",
    CONVOCATORIAS_PUBLICAR: "Publicar una convocatoria y abrir su ventana de ofertas.",
    CONVOCATORIAS_CERRAR: "Cerrar anticipadamente la ventana de ofertas de una convocatoria.",
    CONVOCATORIAS_LISTAR: "Ver las convocatorias publicadas.",
    OFERTAS_CREAR: "Presentar una oferta de ayuda, individual o en consorcio.",
    OFERTAS_EDITAR: "Modificar una oferta propia dentro de la ventana vigente.",
    OFERTAS_RETIRAR: "Retirar una oferta propia dentro de la ventana vigente.",
    OFERTAS_LISTAR: "Ver ofertas de ayuda.",
    INVENTARIO_VER: "Ver el inventario de la propia organización.",
    INVENTARIO_EDITAR: "Actualizar las cantidades del inventario de la propia organización.",
    ADJUDICACIONES_SELECCIONAR: "Seleccionar las ofertas que cubren los lotes de la emergencia.",
    ADJUDICACIONES_REGISTRAR: "Registrar formalmente la adjudicación de las ofertas seleccionadas.",
    ADJUDICACIONES_LISTAR: "Ver las adjudicaciones registradas.",
    EJECUCION_MARCAR_ACTIVIDAD: "Marcar una actividad propia como finalizada.",
    EJECUCION_INFORMAR_FINALIZACION: "Informar que la organización terminó su participación.",
    EJECUCION_MONITOREAR: "Monitorear el avance de la ejecución de todas las organizaciones.",
    INDICADORES_VER: "Ver el dashboard de indicadores.",
    INDICADORES_EXPORTAR: "Exportar los datos del dashboard de indicadores.",
}


# --- Matriz rol -> permisos ---------------------------------------------------

# Derivada de los lanes del BPMN de la Entrega 1 (Municipio, Centro coordinador regional, ONG) y
# del punto 2 del enunciado. Cada rol recibe lo minimo que necesita para cumplir su parte del
# proceso: eso es el criterio de minimo privilegio de la epica, aplicado tambien al administrador.
PERMISOS_POR_ROL: dict[NombreRol, frozenset[str]] = {
    # Carga la emergencia y, al final del proceso, elige que ofertas se adjudican.
    NombreRol.OPERADOR_MUNICIPAL: frozenset(
        {
            EMERGENCIAS_CREAR,
            EMERGENCIAS_LISTAR,
            EMERGENCIAS_VER,
            EMERGENCIAS_EDITAR,
            LOTES_LISTAR,
            CONVOCATORIAS_LISTAR,
            OFERTAS_LISTAR,
            ADJUDICACIONES_SELECCIONAR,
            ADJUDICACIONES_LISTAR,
        }
    ),
    # Desglosa la emergencia en lotes, publica la convocatoria y monitorea la ejecucion.
    NombreRol.COORDINADOR_REGIONAL: frozenset(
        {
            EMERGENCIAS_LISTAR,
            EMERGENCIAS_VER,
            LOTES_CREAR,
            LOTES_EDITAR,
            LOTES_LISTAR,
            CONVOCATORIAS_CREAR,
            CONVOCATORIAS_PUBLICAR,
            CONVOCATORIAS_CERRAR,
            CONVOCATORIAS_LISTAR,
            OFERTAS_LISTAR,
            ADJUDICACIONES_REGISTRAR,
            ADJUDICACIONES_LISTAR,
            EJECUCION_MONITOREAR,
        }
    ),
    # Exactamente lo que el enunciado le pide al perfil 3: inventario, ofertas y cierre propio.
    NombreRol.REPRESENTANTE_ONG: frozenset(
        {
            CONVOCATORIAS_LISTAR,
            OFERTAS_CREAR,
            OFERTAS_EDITAR,
            OFERTAS_RETIRAR,
            OFERTAS_LISTAR,
            INVENTARIO_VER,
            INVENTARIO_EDITAR,
            EJECUCION_MARCAR_ACTIVIDAD,
            EJECUCION_INFORMAR_FINALIZACION,
        }
    ),
    # Solo lectura. La epica excluye su dashboard: aca se crea el perfil con acceso de lectura.
    NombreRol.AUDITOR: frozenset(
        {
            EMERGENCIAS_LISTAR,
            EMERGENCIAS_VER,
            LOTES_LISTAR,
            CONVOCATORIAS_LISTAR,
            OFERTAS_LISTAR,
            ADJUDICACIONES_LISTAR,
            INVENTARIO_VER,
            INDICADORES_VER,
            INDICADORES_EXPORTAR,
        }
    ),
    # Ni una sola accion del proceso: el administrador no ve emergencias, lotes, ofertas ni
    # adjudicaciones. Administra cuentas y organizaciones, y nada mas.
    NombreRol.ADMINISTRADOR: frozenset(
        {
            USUARIOS_LISTAR,
            USUARIOS_CREAR,
            USUARIOS_EDITAR,
            USUARIOS_CAMBIAR_ESTADO,
            USUARIOS_RESTABLECER_CONTRASENA,
            ORGANIZACIONES_LISTAR,
            ORGANIZACIONES_CREAR,
            ORGANIZACIONES_EDITAR,
            ORGANIZACIONES_CAMBIAR_ESTADO,
        }
    ),
}
