"""Diagnostico de la conexion con Bonita (`flask bonita-diagnostico`).

Revisa, en orden, lo que la app necesita del motor y, ante cada falla, dice como resolverla:

1. Que Bonita responda en `BONITA_BASE_URL`.
2. Que `BONITA_USER` inicie sesion con `BONITA_PASSWORD`. Un 401 casi siempre significa que el
   motor tiene desplegada otra organizacion (la ACME de fabrica, con contraseña `bpm`).
3. Que el proceso `BONITA_PROCESO_NOMBRE`/`BONITA_PROCESO_VERSION` este desplegado y habilitado,
   con su fecha de despliegue a la vista para detectar uno viejo.
4. Que cada actor del proceso tenga miembros y que el usuario tecnico sea candidato: la app
   ejecuta con el varias tareas y lo usa cuando un usuario propio no existe en Bonita.
5. Que los usuarios de la app que hablan con Bonita (por su email) inicien sesion y sean
   candidatos del actor de su perfil. Si no inician sesion, la app usa el usuario tecnico en su
   lugar: es un aviso, no un error.

Es de solo lectura (GET, salvo los logins) y usa sus propios clientes HTTP: no toca las sesiones
que la app tiene en memoria.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.errores import ErrorDeAplicacion, SistemaExternoRechazo
from app.core.integraciones.bonita import sesion
from app.core.integraciones.bonita.api import BONITA_PROCESO_NOMBRE, BONITA_PROCESO_VERSION
from app.core.integraciones.cliente_http import COMPONENTE_BONITA, ejecutar_solicitud

SIN_ID = "-1"


class Resultado(enum.StrEnum):
    OK = "ok"
    AVISO = "aviso"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Chequeo:
    nombre: str
    resultado: Resultado
    detalle: str
    pista: str | None = None


@dataclass(frozen=True, slots=True)
class _Miembro:
    usuario: str
    rol: str
    grupo: str


def _pedir(
    cliente: httpx.Client, endpoint: str, params: list[tuple[str, str]] | None = None
) -> Any:
    respuesta = ejecutar_solicitud(
        cliente,
        componente=COMPONENTE_BONITA,
        metodo="GET",
        endpoint_normalizado=endpoint,
        url=f"{sesion.BONITA_BASE_URL}{endpoint}",
        idempotente=True,
        timeout_lectura_s=sesion.BONITA_TIMEOUT_S,
        params=params or [],
    )
    return respuesta.json()


def _iniciar_sesion(username: str) -> httpx.Client:
    """Un login sin el reemplazo silencioso por el usuario tecnico que hace `sesion`."""
    cliente = httpx.Client()
    try:
        ejecutar_solicitud(
            cliente,
            componente=COMPONENTE_BONITA,
            metodo="POST",
            endpoint_normalizado="/loginservice",
            url=f"{sesion.BONITA_BASE_URL}/loginservice",
            idempotente=False,
            timeout_lectura_s=sesion.BONITA_TIMEOUT_S,
            data={"username": username, "password": sesion.BONITA_PASSWORD, "redirect": "false"},
        )
    except ErrorDeAplicacion:
        cliente.close()
        raise
    token = cliente.cookies.get(sesion.NOMBRE_COOKIE_TOKEN)
    if token:
        cliente.headers[sesion.NOMBRE_COOKIE_TOKEN] = token
    return cliente


def _membresias(cliente: httpx.Client, usuario_id: str) -> set[tuple[str, str]]:
    """Los pares (rol, grupo) del usuario en la organizacion."""
    return {
        (str(membresia["role_id"]), str(membresia["group_id"]))
        for membresia in _pedir(
            cliente,
            "/API/identity/membership",
            [("p", "0"), ("c", "100"), ("f", f"user_id={usuario_id}")],
        )
    }


def _es_candidato(
    usuario_id: str, membresias: set[tuple[str, str]], miembros: Iterable[_Miembro]
) -> bool:
    """Si el usuario esta mapeado al actor, directamente o por rol, grupo o membresia.

    No contempla subgrupos: un actor mapeado a un grupo padre se informa como no candidato.
    """
    roles = {rol for rol, _ in membresias}
    grupos = {grupo for _, grupo in membresias}
    for miembro in miembros:
        if miembro.usuario == usuario_id:
            return True
        if miembro.usuario != SIN_ID:
            continue
        if miembro.grupo == SIN_ID and miembro.rol in roles:
            return True
        if miembro.rol == SIN_ID and miembro.grupo in grupos:
            return True
        if (miembro.rol, miembro.grupo) in membresias:
            return True
    return False


def _conexion() -> Chequeo:
    with httpx.Client() as cliente:
        try:
            ejecutar_solicitud(
                cliente,
                componente=COMPONENTE_BONITA,
                metodo="GET",
                endpoint_normalizado="/",
                url=f"{sesion.BONITA_BASE_URL}/",
                idempotente=False,
                timeout_lectura_s=sesion.BONITA_TIMEOUT_S,
            )
        except SistemaExternoRechazo:
            pass  # Respondio, aunque sea con un 4xx: hay alguien escuchando.
        except ErrorDeAplicacion:
            return Chequeo(
                "Conexión",
                Resultado.ERROR,
                f"Bonita no responde en {sesion.BONITA_BASE_URL}.",
                "Verificá que Bonita Studio esté abierto con su servidor iniciado. Desde el "
                "contenedor la URL es http://host.docker.internal:8080/bonita.",
            )
    return Chequeo("Conexión", Resultado.OK, f"Bonita responde en {sesion.BONITA_BASE_URL}.")


def _chequear_login_tecnico() -> tuple[Chequeo, httpx.Client | None]:
    nombre = f"Login de {sesion.BONITA_USER}"
    try:
        cliente = _iniciar_sesion(sesion.BONITA_USER)
    except SistemaExternoRechazo as error:
        return (
            Chequeo(
                nombre,
                Resultado.ERROR,
                f"Bonita rechazó las credenciales (HTTP {error.detalle.get('codigo_estado')}).",
                "El motor tiene desplegada otra organización (la ACME de fábrica usa la "
                "contraseña 'bpm'). En Bonita Studio: Organizations → ACME.xml → clic derecho → "
                "Desplegar, con este usuario como usuario por defecto.",
            ),
            None,
        )
    except ErrorDeAplicacion:
        return Chequeo(nombre, Resultado.ERROR, "Bonita no respondió al login."), None
    return Chequeo(nombre, Resultado.OK, "Sesión iniciada."), cliente


def _chequear_proceso(cliente: httpx.Client) -> tuple[Chequeo, str | None]:
    nombre = f"Proceso {BONITA_PROCESO_NOMBRE} {BONITA_PROCESO_VERSION}"
    procesos = _pedir(
        cliente,
        "/API/bpm/process",
        [
            ("p", "0"),
            ("c", "10"),
            ("f", f"name={BONITA_PROCESO_NOMBRE}"),
            ("f", f"version={BONITA_PROCESO_VERSION}"),
        ],
    )
    if not procesos:
        return (
            Chequeo(
                nombre,
                Resultado.ERROR,
                "No está desplegado.",
                "En Bonita Studio abrí el diagrama y usá Ejecutar (o Desplegar).",
            ),
            None,
        )
    proceso = procesos[0]
    desplegado = str(proceso.get("deploymentDate", ""))[:16]
    if proceso.get("activationState") != "ENABLED":
        return (
            Chequeo(
                nombre,
                Resultado.ERROR,
                f"Está desplegado ({desplegado}) pero deshabilitado.",
                "Habilitalo desde el portal de Bonita o volvé a desplegarlo desde Studio.",
            ),
            str(proceso["id"]),
        )
    return (
        Chequeo(
            nombre,
            Resultado.OK,
            f"Desplegado y habilitado el {desplegado}. Si el diagrama cambió después de esa "
            "fecha, volvé a desplegarlo.",
        ),
        str(proceso["id"]),
    )


def _miembros_por_actor(cliente: httpx.Client, proceso_id: str) -> dict[str, list[_Miembro]]:
    actores = _pedir(
        cliente, "/API/bpm/actor", [("p", "0"), ("c", "50"), ("f", f"process_id={proceso_id}")]
    )
    return {
        str(actor["name"]): [
            _Miembro(str(m["user_id"]), str(m["role_id"]), str(m["group_id"]))
            for m in _pedir(
                cliente,
                "/API/bpm/actorMember",
                [("p", "0"), ("c", "100"), ("f", f"actor_id={actor['id']}")],
            )
        ]
        for actor in actores
    }


def _chequear_actores(
    cliente: httpx.Client, miembros_por_actor: dict[str, list[_Miembro]]
) -> Iterator[Chequeo]:
    sesion_actual = _pedir(cliente, "/API/system/session/unusedid")
    usuario_id = str(sesion_actual["user_id"])
    membresias = _membresias(cliente, usuario_id)
    pista = (
        "En Bonita Studio: Configurar → entorno Local → Actor mapping, mapeá los actores al rol "
        "'member' y volvé a desplegar el proceso."
    )
    for actor, miembros in sorted(miembros_por_actor.items()):
        if not miembros:
            yield Chequeo(f"Actor «{actor}»", Resultado.ERROR, "No tiene a nadie mapeado.", pista)
        elif _es_candidato(usuario_id, membresias, miembros):
            yield Chequeo(
                f"Actor «{actor}»",
                Resultado.OK,
                f"{len(miembros)} mapeo(s); {sesion.BONITA_USER} es candidato.",
            )
        else:
            yield Chequeo(
                f"Actor «{actor}»",
                Resultado.ERROR,
                f"{sesion.BONITA_USER} no es candidato.",
                pista,
            )


def _chequear_usuario_de_la_app(
    cliente: httpx.Client, email: str, actor: str, miembros: list[_Miembro] | None
) -> Chequeo:
    """Si la cuenta de la app inicia sesion en Bonita y es candidata del actor de su perfil."""
    nombre = f"Usuario {email}"
    try:
        _iniciar_sesion(email).close()
    except ErrorDeAplicacion:
        return Chequeo(
            nombre,
            Resultado.AVISO,
            f"No inicia sesión en Bonita: la app va a usar {sesion.BONITA_USER} en su lugar.",
            "Si querés que los casos queden a su nombre, agregalo a la organización de Bonita "
            "(ACME.xml) con la contraseña de BONITA_PASSWORD y volvé a desplegarla.",
        )
    if miembros is None:
        return Chequeo(
            nombre,
            Resultado.AVISO,
            f"Inicia sesión, pero el proceso no tiene el actor «{actor}».",
            "Revisá que el diagrama desplegado sea el actual.",
        )
    encontrados = _pedir(
        cliente, "/API/identity/user", [("p", "0"), ("c", "1"), ("f", f"userName={email}")]
    )
    usuario_id = str(encontrados[0]["id"]) if encontrados else SIN_ID
    if not _es_candidato(usuario_id, _membresias(cliente, usuario_id), miembros):
        return Chequeo(
            nombre,
            Resultado.AVISO,
            f"Inicia sesión pero no es candidato de «{actor}»: Bonita no lo va a dejar "
            "iniciar casos ni tomar sus tareas.",
            f"En Bonita Studio: Configurar → entorno Local → Actor mapping, sumalo a «{actor}» "
            "(o mapeá el actor al rol 'member') y volvé a desplegar el proceso.",
        )
    return Chequeo(nombre, Resultado.OK, f"Inicia sesión y es candidato de «{actor}».")


def diagnosticar(usuarios_por_actor: Mapping[str, Iterable[str]] | None = None) -> list[Chequeo]:
    """Corre los chequeos en orden; si uno impide seguir, los siguientes no se intentan.

    `usuarios_por_actor` son los emails de las cuentas de la app que actuan en Bonita, por el
    actor del proceso que les corresponde (el operador inicia el caso como "Empleado municipal",
    por ejemplo). Cada una se compara solo con su actor.
    """
    chequeos = [_conexion()]
    if chequeos[-1].resultado is Resultado.ERROR:
        return chequeos

    login, cliente = _chequear_login_tecnico()
    chequeos.append(login)
    if cliente is None:
        return chequeos

    # Sin `with`: httpx no deja usar como contexto un cliente que ya hizo una solicitud.
    try:
        proceso, proceso_id = _chequear_proceso(cliente)
        chequeos.append(proceso)
        if proceso_id is None:
            return chequeos
        miembros_por_actor = _miembros_por_actor(cliente, proceso_id)
        chequeos.extend(_chequear_actores(cliente, miembros_por_actor))
        chequeos.extend(
            _chequear_usuario_de_la_app(cliente, email, actor, miembros_por_actor.get(actor))
            for actor, emails in (usuarios_por_actor or {}).items()
            for email in emails
        )
    except (ErrorDeAplicacion, KeyError, ValueError) as error:
        chequeos.append(
            Chequeo(
                "Consulta a Bonita",
                Resultado.ERROR,
                f"Bonita respondió algo inesperado ({type(error).__name__}).",
                "Revisá que BONITA_USER tenga el perfil Administrator en Bonita.",
            )
        )
    finally:
        cliente.close()
    return chequeos
