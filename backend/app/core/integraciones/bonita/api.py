from __future__ import annotations

import os
import time

from app.core.errores import RespuestaExternaInvalida, SistemaExternoRechazo
from app.core.integraciones.bonita.sesion import (
    BONITA_BASE_URL,
    ejecutar_solicitud_bonita,
)

BONITA_PROCESO_NOMBRE = os.environ["BONITA_PROCESO_NOMBRE"]
BONITA_PROCESO_VERSION = os.environ["BONITA_PROCESO_VERSION"]

_process_definition_id: str | None = None


def obtener_process_definition_id(
    username: str,
    *,
    forzar_recarga: bool = False,
) -> str:
    global _process_definition_id

    if _process_definition_id is not None and not forzar_recarga:
        return _process_definition_id

    respuesta = ejecutar_solicitud_bonita(
        username=username,
        metodo="GET",
        endpoint_normalizado="/API/bpm/process",
        url=f"{BONITA_BASE_URL}/API/bpm/process",
        idempotente=True,
        params=[
            ("p", "0"),
            ("c", "10"),
            ("f", f"name={BONITA_PROCESO_NOMBRE}"),
            ("f", f"version={BONITA_PROCESO_VERSION}"),
        ],
    )

    procesos = respuesta.json()

    if not procesos:
        raise SistemaExternoRechazo(
            f"El motor de procesos no tiene desplegado el proceso {BONITA_PROCESO_NOMBRE} "
            f"versión {BONITA_PROCESO_VERSION}.",
            codigo="PROCESO_NO_DESPLEGADO",
            detalle={
                "componente": "bonita",
                "proceso": BONITA_PROCESO_NOMBRE,
                "version": BONITA_PROCESO_VERSION,
            },
        )

    process_definition_id = str(procesos[0]["id"])
    _process_definition_id = process_definition_id

    return process_definition_id


def instanciar_proceso(
    username: str,
    variables_contrato: dict[str, object],
) -> str:
    process_definition_id = obtener_process_definition_id(username)

    respuesta = ejecutar_solicitud_bonita(
        username=username,
        metodo="POST",
        endpoint_normalizado="/API/bpm/process/{id}/instantiation",
        url=f"{BONITA_BASE_URL}/API/bpm/process/{process_definition_id}/instantiation",
        idempotente=False,
        json=variables_contrato,
    )

    datos = respuesta.json()

    if "caseId" not in datos:
        # Bonita creo la instancia pero no devolvio su caseId.
        raise RespuestaExternaInvalida(detalle={"componente": "bonita", "falta": "caseId"})

    return str(datos["caseId"])


def buscar_tarea_humana(
    username: str,
    case_id: str,
    nombre_tarea: str,
    *,
    reintentos: int = 5,
    espera_segundos: float = 0.5,
) -> str:
    for _ in range(reintentos):
        respuesta = ejecutar_solicitud_bonita(
            username=username,
            metodo="GET",
            endpoint_normalizado="/API/bpm/humanTask",
            url=f"{BONITA_BASE_URL}/API/bpm/humanTask",
            idempotente=True,
            params=[
                ("p", "0"),
                ("c", "10"),
                ("f", f"caseId={case_id}"),
                ("f", f"name={nombre_tarea}"),
                ("f", "state=ready"),
            ],
        )

        tareas = respuesta.json()
        if tareas:
            return str(tareas[0]["id"])

        time.sleep(espera_segundos)

    # El caso no llego (todavia) a esa tarea: el motor y la app no estan en el mismo paso. Es un
    # error de aplicacion para que cada pantalla lo muestre como aviso, no como un 500.
    raise SistemaExternoRechazo(
        f"El motor de procesos todavía no habilitó la tarea «{nombre_tarea}» para esta "
        "emergencia. Esperá unos segundos y volvé a intentar.",
        codigo="TAREA_DE_PROCESO_NO_DISPONIBLE",
        detalle={"componente": "bonita", "tarea": nombre_tarea, "caso": case_id},
    )


def ejecutar_tarea(
    username: str,
    task_id: str,
    variables_contrato: dict[str, object],
) -> None:
    ejecutar_solicitud_bonita(
        username=username,
        metodo="POST",
        endpoint_normalizado="/API/bpm/userTask/{id}/execution",
        url=f"{BONITA_BASE_URL}/API/bpm/userTask/{task_id}/execution",
        idempotente=False,
        json=variables_contrato,
    )


def obtener_usuario_actual_id(username: str) -> str:
    respuesta = ejecutar_solicitud_bonita(
        username=username,
        metodo="GET",
        endpoint_normalizado="/API/system/session/1",
        url=f"{BONITA_BASE_URL}/API/system/session/1",
        idempotente=True,
    )

    datos = respuesta.json()

    return str(datos["user_id"])


def asignar_tarea(
    username: str,
    task_id: str,
    usuario_id: str,
) -> None:
    ejecutar_solicitud_bonita(
        username=username,
        metodo="PUT",
        endpoint_normalizado="/API/bpm/humanTask/{id}",
        url=f"{BONITA_BASE_URL}/API/bpm/humanTask/{task_id}",
        idempotente=True,
        json={
            "assigned_id": usuario_id,
        },
    )
