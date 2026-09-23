"""Logica de negocio de identidad: autenticacion, cuentas y asignacion de roles.

Es el unico punto de entrada del modulo para los demas: nadie importa `modelos.py` de aca.
Tambien lo usan el seeder y los comandos de `flask`, que no tienen solicitud HTTP: por eso
ninguna funcion de este archivo toca `request`, `session` ni devuelve una respuesta.

Registro de cuentas
-------------------
En RescueSync **no hay autorregistro**. Todas las cuentas las crea un usuario con el rol
`administrador`. Permitir que alguien se autoasigne el rol de Centro Coordinador Regional
contradice el criterio de minimo privilegio, y no hay forma de verificar por fuera del sistema
que quien se registra pertenece de verdad al municipio o a la ONG que dice representar. Ver
docs/adr/ADR-009-autenticacion-y-rbac.md.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import Select, select

from app.core.errores import (
    ConflictoDeEstado,
    NoAutenticado,
    PermisoDenegado,
    RecursoNoEncontrado,
    SolicitudInvalida,
)
from app.core.logging import id_correlacion_actual, registrar_evento
from app.core.paginacion import Pagina, paginar
from app.core.permisos import TIPO_DE_ORGANIZACION_POR_ROL, NombreRol
from app.core.seguridad import (
    hashear_contrasena,
    mensaje_de_politica,
    requisitos_incumplidos,
    verificar_contrasena,
)
from app.core.sesion import registrar_cargador_de_usuario
from app.extensiones import db
from app.modulos.organizaciones import servicios as servicios_de_organizaciones
from app.modulos.usuarios_roles.modelos import Rol, Usuario

# Un unico mensaje para "no existe esa cuenta" y "la contrasena no es esa". Distinguirlos le
# diria a cualquiera que pruebe emails al azar cuales estan registrados, que es justamente lo
# que no queremos regalar. La cuenta desactivada tiene su propio aviso, pero solo se muestra a
# quien acerto la contrasena (ver `autenticar`).
MENSAJE_CREDENCIALES = "Email o contraseña incorrectos."
MENSAJE_BLOQUEADA = (
    "La cuenta está bloqueada temporalmente por intentos fallidos. "
    "Volvé a intentar en {duracion} o pedile a un administrador que la desbloquee."
)
MENSAJE_INACTIVA = (
    "Tu cuenta está desactivada. Pedile a un administrador que la vuelva a habilitar."
)
MENSAJE_EMAIL_EN_USO = "Ya existe una cuenta registrada con ese email."
MENSAJE_NO_ENCONTRADO = "No encontramos la cuenta solicitada."
MENSAJE_CONTRASENA_ACTUAL = "La contraseña actual no es correcta."
MENSAJE_CONTRASENA_REPETIDA = "La contraseña nueva tiene que ser distinta de la actual."
MENSAJE_FUERA_DE_ALCANCE = "No podés operar sobre datos de otra organización."


def mensaje_de_bloqueo(minutos: int) -> str:
    """El aviso de cuenta bloqueada, con la duracion real del bloqueo configurado."""
    duracion = "1 minuto" if minutos == 1 else f"{minutos} minutos"
    return MENSAJE_BLOQUEADA.format(duracion=duracion)


# Roles que ven el proceso completo y no solo lo de su propia organizacion.
ROLES_SIN_LIMITE_DE_ORGANIZACION = frozenset(
    {NombreRol.COORDINADOR_REGIONAL, NombreRol.AUDITOR, NombreRol.ADMINISTRADOR}
)

# Hash contra el que se verifica cuando el email no existe, para que un intento con un email
# inexistente tarde lo mismo que uno con la contrasena equivocada. Sin esto, la diferencia de
# tiempo de respuesta alcanza para enumerar que cuentas estan dadas de alta.
_hash_senuelo: str | None = None


def _obtener_hash_senuelo() -> str:
    global _hash_senuelo
    if _hash_senuelo is None:
        _hash_senuelo = hashear_contrasena("contrasena-que-no-usa-nadie")
    return _hash_senuelo


def _ahora() -> datetime:
    return datetime.now(UTC)


# --- Consultas ----------------------------------------------------------------


def normalizar_email(email: str) -> str:
    """Deja el email en la forma canonica con la que se guarda y se busca."""
    return (email or "").strip().lower()


def obtener_por_email(email: str) -> Usuario | None:
    return db.session.execute(
        select(Usuario).where(Usuario.email == normalizar_email(email))
    ).scalar_one_or_none()


def obtener_usuario(usuario_id: int) -> Usuario:
    """Devuelve la cuenta o corta con 404."""
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None:
        raise RecursoNoEncontrado(MENSAJE_NO_ENCONTRADO)
    return usuario


def listar_usuarios(
    *,
    nombre_rol: str | None = None,
    organizacion_id: int | None = None,
    activo: bool | None = None,
    texto: str | None = None,
) -> list[Usuario]:
    """Listado completo, sin paginar. Los filtros se combinan con AND."""
    consulta = _consulta_de_usuarios(
        nombre_rol=nombre_rol, organizacion_id=organizacion_id, activo=activo, texto=texto
    )
    return list(db.session.execute(consulta).scalars())


def paginar_usuarios(
    *,
    pagina: int,
    por_pagina: int,
    nombre_rol: str | None = None,
    organizacion_id: int | None = None,
    activo: bool | None = None,
    texto: str | None = None,
) -> Pagina[Usuario]:
    """Una pagina del listado del panel del administrador, con los mismos filtros."""
    consulta = _consulta_de_usuarios(
        nombre_rol=nombre_rol, organizacion_id=organizacion_id, activo=activo, texto=texto
    )
    return paginar(consulta, pagina, por_pagina)


def _consulta_de_usuarios(
    *,
    nombre_rol: str | None,
    organizacion_id: int | None,
    activo: bool | None,
    texto: str | None,
) -> Select:
    # El id desempata a dos personas con el mismo nombre: sin un orden total, la misma cuenta
    # podria aparecer en dos paginas seguidas o en ninguna.
    consulta = select(Usuario).order_by(Usuario.nombre_completo, Usuario.id)

    if nombre_rol:
        consulta = consulta.where(Usuario.roles.any(Rol.nombre == nombre_rol))
    if organizacion_id is not None:
        consulta = consulta.where(Usuario.organizacion_id == organizacion_id)
    if activo is not None:
        consulta = consulta.where(Usuario.activo.is_(activo))
    if texto:
        patron = f"%{texto.strip()}%"
        consulta = consulta.where(
            Usuario.nombre_completo.ilike(patron) | Usuario.email.ilike(patron)
        )

    return consulta


def obtener_rol(nombre_rol: str) -> Rol:
    """Devuelve el rol por su nombre. Si no esta sembrado, es un error de configuracion."""
    rol = db.session.execute(select(Rol).where(Rol.nombre == nombre_rol)).scalar_one_or_none()
    if rol is None:
        raise ConflictoDeEstado(
            f"El rol '{nombre_rol}' no existe en la base. Ejecutá `flask seed`."
        )
    return rol


# --- Sesion -------------------------------------------------------------------


def _cargar_usuario_de_sesion(id_usuario: str) -> Usuario | None:
    """`user_loader` de Flask-Login: traduce el id de la cookie a la cuenta.

    Devuelve None ante cualquier id que no corresponda a una cuenta existente, que es la forma
    en que Flask-Login entiende "esta sesion no vale".
    """
    try:
        identificador = int(id_usuario)
    except TypeError, ValueError:
        return None
    return db.session.get(Usuario, identificador)


def instalar_cargador_de_sesion() -> None:
    """Deja a Flask-Login resolviendo usuarios reales.

    Lo llama `registrar_modulos()` al arrancar. Es el reemplazo del cargador de respaldo que
    instala la app factory para que `current_user` no explote antes de que exista este modulo.
    """
    registrar_cargador_de_usuario(_cargar_usuario_de_sesion)


# --- Autenticacion ------------------------------------------------------------


def _limite_de_intentos() -> int:
    return int(current_app.config["LOGIN_MAX_INTENTOS"])


def _minutos_de_bloqueo() -> int:
    return int(current_app.config["LOGIN_BLOQUEO_MINUTOS"])


def _registrar_intento_fallido(usuario: Usuario) -> None:
    """Suma un intento fallido y bloquea la cuenta si se agotaron.

    El contador se reinicia al bloquear: cuando el bloqueo vence, la cuenta arranca de cero en
    vez de quedar a un intento de volver a bloquearse.
    """
    usuario.intentos_fallidos = (usuario.intentos_fallidos or 0) + 1

    if usuario.intentos_fallidos >= _limite_de_intentos():
        usuario.bloqueado_hasta = _ahora() + timedelta(minutes=_minutos_de_bloqueo())
        usuario.intentos_fallidos = 0
        registrar_evento(
            logging.WARNING,
            "cuenta_bloqueada",
            id_usuario=str(usuario.id),
            minutos=_minutos_de_bloqueo(),
            id_correlacion=id_correlacion_actual(),
        )

    db.session.commit()


def autenticar(email: str, contrasena: str) -> Usuario:
    """Verifica las credenciales y devuelve la cuenta.

    No abre la sesion: de eso se ocupa `app.core.sesion.iniciar_sesion()` desde la ruta. Asi
    esta funcion tambien sirve desde un comando de consola, donde no hay sesion que abrir.

    El orden de las verificaciones es parte de lo que la hace segura:
    se verifica el hash aunque el email no exista (para igualar los tiempos de respuesta), y
    todo fallo devuelve el mismo mensaje, salvo el bloqueo y la cuenta desactivada, que el
    usuario necesita entender. La desactivada se informa recien despues de validar la
    contrasena, asi el aviso no le sirve a quien esta probando emails.
    """
    usuario = obtener_por_email(email)

    if usuario is None:
        verificar_contrasena(_obtener_hash_senuelo(), contrasena)
        registrar_evento(
            logging.WARNING,
            "login_fallido",
            motivo="email_inexistente",
            id_correlacion=id_correlacion_actual(),
        )
        raise NoAutenticado(MENSAJE_CREDENCIALES)

    if usuario.esta_bloqueado():
        registrar_evento(
            logging.WARNING,
            "login_fallido",
            motivo="cuenta_bloqueada",
            id_usuario=str(usuario.id),
            id_correlacion=id_correlacion_actual(),
        )
        raise PermisoDenegado(mensaje_de_bloqueo(_minutos_de_bloqueo()))

    if not verificar_contrasena(usuario.hash_contrasena, contrasena):
        _registrar_intento_fallido(usuario)
        registrar_evento(
            logging.WARNING,
            "login_fallido",
            motivo="contrasena_incorrecta",
            id_usuario=str(usuario.id),
            id_correlacion=id_correlacion_actual(),
        )
        raise NoAutenticado(MENSAJE_CREDENCIALES)

    # Se avisa que la cuenta esta desactivada solo despues de verificar la contrasena: a quien
    # no la conoce le sale el mensaje generico de arriba, asi que no se revela que cuentas
    # existen; a la persona duena de la cuenta si se le explica por que no puede entrar.
    if not usuario.activo:
        registrar_evento(
            logging.WARNING,
            "login_fallido",
            motivo="cuenta_inactiva",
            id_usuario=str(usuario.id),
            id_correlacion=id_correlacion_actual(),
        )
        raise PermisoDenegado(MENSAJE_INACTIVA)

    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultimo_acceso_en = _ahora()
    db.session.commit()

    registrar_evento(
        logging.INFO,
        "login_exitoso",
        id_usuario=str(usuario.id),
        rol=usuario.rol_principal,
        id_correlacion=id_correlacion_actual(),
    )
    return usuario


# --- Politica de contrasena ---------------------------------------------------


def validar_politica_de_contrasena(contrasena: str, campo: str = "contrasena") -> None:
    """Exige la politica de `app.core.seguridad`: longitud minima, mayuscula, numero y
    caracter especial.

    Se valida tambien acá, y no solo en el formulario, porque el seeder y la CLI crean cuentas
    sin pasar por WTForms. `campo` es el nombre del campo al que se le pega el error.
    """
    minima = int(current_app.config["CONTRASENA_LONGITUD_MINIMA"])
    incumplidos = requisitos_incumplidos(contrasena, minima)
    if incumplidos:
        raise SolicitudInvalida(detalle={campo: [mensaje_de_politica(incumplidos, minima)]})


# --- Coherencia entre rol y organizacion --------------------------------------


def verificar_coherencia_rol_organizacion(nombre_rol: str, organizacion_id: int | None) -> None:
    """Comprueba que la organizacion asignada sea del tipo que el rol exige.

    No es una restriccion de base porque cruza `usuarios`, `usuario_rol` y `organizacion`, y
    eso no se expresa en un CHECK de columna. Sin esta verificacion se puede crear un
    "representante de ONG" apuntando a un municipio, y el alcance por organizacion del resto
    del sistema deja de significar nada.
    """
    try:
        rol = NombreRol(nombre_rol)
    except ValueError:
        validos = ", ".join(nombre.value for nombre in NombreRol)
        raise SolicitudInvalida(
            detalle={"rol": [f"Rol inválido. Valores admitidos: {validos}."]}
        ) from None

    tipo_exigido = TIPO_DE_ORGANIZACION_POR_ROL[rol]

    if tipo_exigido is None:
        if organizacion_id is not None:
            raise SolicitudInvalida(
                detalle={
                    "organizacion_id": [
                        f"El rol '{rol.value}' no se asocia a ninguna organización."
                    ]
                }
            )
        return

    if organizacion_id is None:
        raise SolicitudInvalida(
            detalle={
                "organizacion_id": [
                    f"El rol '{rol.value}' requiere una organización de tipo '{tipo_exigido}'."
                ]
            }
        )

    tipo_real = servicios_de_organizaciones.obtener_tipo_de_organizacion(organizacion_id)
    if tipo_real is None:
        raise SolicitudInvalida(
            detalle={"organizacion_id": ["La organización indicada no existe."]}
        )
    if tipo_real != tipo_exigido:
        raise SolicitudInvalida(
            detalle={
                "organizacion_id": [
                    f"El rol '{rol.value}' requiere una organización de tipo "
                    f"'{tipo_exigido}', y la indicada es de tipo '{tipo_real}'."
                ]
            }
        )


def verificar_alcance_de_organizacion(usuario: Usuario, organizacion_id: int | None) -> None:
    """Corta con 403 si el usuario no puede operar sobre datos de esa organizacion.

    Es la contraparte de los decoradores de `core/autorizacion.py`: ellos deciden *que accion*
    puede ejecutar un rol, esta funcion decide *sobre que filas*. Un operador municipal tiene
    `emergencias:editar`, pero solo sobre las emergencias de su propio municipio.

    La usan los modulos siguientes de la cadena (emergencias, ofertas, adjudicacion) antes de
    devolver o modificar cualquier fila que tenga dueno.
    """
    if usuario.nombres_de_rol() & ROLES_SIN_LIMITE_DE_ORGANIZACION:
        return
    if organizacion_id is None or usuario.organizacion_id != organizacion_id:
        raise PermisoDenegado(MENSAJE_FUERA_DE_ALCANCE)


# --- Alta y mantenimiento de cuentas ------------------------------------------


def _verificar_email_disponible(email: str, excluir_id: int | None = None) -> None:
    consulta = select(Usuario.id).where(Usuario.email == email)
    if excluir_id is not None:
        consulta = consulta.where(Usuario.id != excluir_id)
    if db.session.execute(consulta).scalar_one_or_none() is not None:
        raise ConflictoDeEstado(MENSAJE_EMAIL_EN_USO)


def crear_usuario(
    *,
    email: str,
    nombre_completo: str,
    contrasena: str,
    nombre_rol: str,
    organizacion_id: int | None = None,
    debe_cambiar_contrasena: bool = True,
    confirmar: bool = True,
) -> Usuario:
    """Da de alta una cuenta con un rol.

    `debe_cambiar_contrasena` viene en True a proposito: la clave que elige el administrador
    viaja por algun canal fuera del sistema, asi que se considera comprometida desde el primer
    ingreso y el usuario tiene que reemplazarla antes de poder operar.

    `confirmar=False` deja la fila en la sesion sin hacer commit, que es lo que necesitan los
    seeders: `flask seed` envuelve toda la carga en una unica transaccion.
    """
    email_normalizado = normalizar_email(email)
    if not email_normalizado:
        raise SolicitudInvalida(detalle={"email": ["El email es obligatorio."]})

    validar_politica_de_contrasena(contrasena)
    verificar_coherencia_rol_organizacion(nombre_rol, organizacion_id)
    _verificar_email_disponible(email_normalizado)

    usuario = Usuario(
        email=email_normalizado,
        nombre_completo=nombre_completo.strip(),
        hash_contrasena=hashear_contrasena(contrasena),
        organizacion_id=organizacion_id,
        activo=True,
        debe_cambiar_contrasena=debe_cambiar_contrasena,
    )
    usuario.roles.append(obtener_rol(nombre_rol))

    db.session.add(usuario)
    if confirmar:
        db.session.commit()
        registrar_evento(
            logging.INFO,
            "usuario_creado",
            id_usuario=str(usuario.id),
            rol=nombre_rol,
            id_correlacion=id_correlacion_actual(),
        )
    else:
        db.session.flush()
    return usuario


def editar_usuario(
    usuario_id: int,
    *,
    nombre_completo: str,
    nombre_rol: str,
    organizacion_id: int | None = None,
) -> Usuario:
    """Actualiza nombre, rol y organizacion. El email no se edita: es la clave natural."""
    usuario = obtener_usuario(usuario_id)
    verificar_coherencia_rol_organizacion(nombre_rol, organizacion_id)

    usuario.nombre_completo = nombre_completo.strip()
    usuario.organizacion_id = organizacion_id
    # El modelo admite varios roles; el panel asigna uno, que es lo que el enunciado pide.
    usuario.roles = [obtener_rol(nombre_rol)]

    db.session.commit()
    return usuario


def cambiar_estado(usuario_id: int, *, activo: bool) -> Usuario:
    """Activa o desactiva una cuenta.

    Baja logica y no borrado: las emergencias y ofertas ya cargadas referencian al usuario que
    las creo, y borrarlo dejaria el historial del proceso sin autor.
    """
    usuario = obtener_usuario(usuario_id)
    usuario.activo = activo
    db.session.commit()

    registrar_evento(
        logging.INFO,
        "usuario_cambio_de_estado",
        id_usuario=str(usuario.id),
        activo=activo,
        id_correlacion=id_correlacion_actual(),
    )
    return usuario


def restablecer_contrasena(usuario_id: int, nueva_contrasena: str) -> Usuario:
    """El administrador asigna una contrasena nueva y levanta el bloqueo.

    Es el reemplazo del "olvide mi contrasena" por correo, que la epica deja fuera de alcance.
    La cuenta queda marcada para cambiar la clave en el proximo ingreso.
    """
    validar_politica_de_contrasena(nueva_contrasena)

    usuario = obtener_usuario(usuario_id)
    usuario.hash_contrasena = hashear_contrasena(nueva_contrasena)
    usuario.debe_cambiar_contrasena = True
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    db.session.commit()

    registrar_evento(
        logging.INFO,
        "contrasena_restablecida",
        id_usuario=str(usuario.id),
        id_correlacion=id_correlacion_actual(),
    )
    return usuario


def desbloquear(usuario_id: int) -> Usuario:
    """Levanta el bloqueo por intentos fallidos sin tocar la contrasena."""
    usuario = obtener_usuario(usuario_id)
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    db.session.commit()

    registrar_evento(
        logging.INFO,
        "cuenta_desbloqueada",
        id_usuario=str(usuario.id),
        id_correlacion=id_correlacion_actual(),
    )
    return usuario


def cambiar_contrasena_propia(
    usuario: Usuario, contrasena_actual: str, contrasena_nueva: str
) -> Usuario:
    """Cambio de contrasena por parte del propio usuario.

    Exige la contrasena actual aunque haya sesion abierta: si alguien deja el navegador
    abierto, no debería alcanzar con eso para quedarse con la cuenta.

    La nueva tiene que ser distinta de la actual. Sin esto, el cambio obligatorio seria
    decorativo: la cuenta que crea el administrador podria "cambiar" la clave inicial por la
    misma y seguir usando una contraseña que viajo fuera del sistema.
    """
    if not verificar_contrasena(usuario.hash_contrasena, contrasena_actual):
        raise SolicitudInvalida(detalle={"contrasena_actual": [MENSAJE_CONTRASENA_ACTUAL]})

    validar_politica_de_contrasena(contrasena_nueva, campo="contrasena_nueva")

    if verificar_contrasena(usuario.hash_contrasena, contrasena_nueva):
        raise SolicitudInvalida(detalle={"contrasena_nueva": [MENSAJE_CONTRASENA_REPETIDA]})

    usuario.hash_contrasena = hashear_contrasena(contrasena_nueva)
    usuario.debe_cambiar_contrasena = False
    db.session.commit()

    registrar_evento(
        logging.INFO,
        "contrasena_cambiada",
        id_usuario=str(usuario.id),
        id_correlacion=id_correlacion_actual(),
    )
    return usuario


# --- Vista --------------------------------------------------------------------


def a_diccionario(usuario: Usuario) -> dict[str, Any]:
    """Representacion de la cuenta para la respuesta HTTP y para la plantilla futura."""
    return {
        "id": usuario.id,
        "email": usuario.email,
        "nombre_completo": usuario.nombre_completo,
        "roles": sorted(usuario.nombres_de_rol()),
        "organizacion_id": usuario.organizacion_id,
        "organizacion": (
            servicios_de_organizaciones.a_diccionario(usuario.organizacion)
            if usuario.organizacion is not None
            else None
        ),
        "activo": usuario.activo,
        "debe_cambiar_contrasena": usuario.debe_cambiar_contrasena,
        "esta_bloqueado": usuario.esta_bloqueado(),
        "ultimo_acceso_en": (
            usuario.ultimo_acceso_en.isoformat() if usuario.ultimo_acceso_en else None
        ),
        "creado_en": usuario.creado_en.isoformat() if usuario.creado_en else None,
    }


def describir_sesion(usuario: Usuario) -> dict[str, Any]:
    """Lo que necesita la interfaz para armar el menu del usuario en sesion.

    Incluye los permisos efectivos: con eso la plantilla decide que mostrar, sin volver a
    razonar sobre roles. La autorizacion real sigue estando en cada ruta.
    """
    datos = a_diccionario(usuario)
    datos["permisos"] = sorted(usuario.permisos_efectivos())
    return datos
