from __future__ import annotations

import os
import time

from app.core.integraciones.bonita.sesion import (
    BONITA_BASE_URL,
    obtener_cliente,
)
from app.core.integraciones.cliente_http import (
    COMPONENTE_BONITA,
    ejecutar_solicitud,
)

BONITA_PROCESO_NOMBRE = os.environ["BONITA_PROCESO_NOMBRE"]
BONITA_PROCESO_VERSION = os.environ["BONITA_PROCESO_VERSION"]

_process_definition_id: str | None = None

def obtener_process_definition_id(*, forzar_recarga: bool = False) -> str:
    global _process_definition_id

    if _process_definition_id is not None and not forzar_recarga:
        return _process_definition_id

    cliente = obtener_cliente()

    respuesta = ejecutar_solicitud(
        cliente,
        componente=COMPONENTE_BONITA,
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
        raise RuntimeError(
            "No se encontró el proceso de Bonita "
            f"{BONITA_PROCESO_NOMBRE} "
            f"versión {BONITA_PROCESO_VERSION}."
        )

    process_definition_id = str(procesos[0]["id"])

    _process_definition_id = process_definition_id

    return process_definition_id

def instanciar_proceso(
    variables_contrato: dict[str, object],
) -> str:
    cliente = obtener_cliente()
    process_definition_id = obtener_process_definition_id()

    try:
        respuesta = ejecutar_solicitud(
            cliente,
            componente=COMPONENTE_BONITA,
            metodo="POST",
            endpoint_normalizado="/API/bpm/process/{id}/instantiation",
            url=(
                f"{BONITA_BASE_URL}/API/bpm/process/"
                f"{process_definition_id}/instantiation"
            ),
            idempotente=False,
            json=variables_contrato,
        )
    except Exception:
        process_definition_id = obtener_process_definition_id(forzar_recarga=True)
        respuesta = ejecutar_solicitud(
            cliente,
            componente=COMPONENTE_BONITA,
            metodo="POST",
            endpoint_normalizado="/API/bpm/process/{id}/instantiation",
            url=(
                f"{BONITA_BASE_URL}/API/bpm/process/"
                f"{process_definition_id}/instantiation"
            ),
            idempotente=False,
            json=variables_contrato,
        )

    datos = respuesta.json()

    if "caseId" not in datos:
        raise RuntimeError(
            "Bonita creó la instancia pero no devolvió caseId."
        )

    return str(datos["caseId"])

def buscar_tarea_humana(
    case_id: str,
    nombre_tarea: str,
    *,
    reintentos: int = 5,
    espera_segundos: float = 0.5,
) -> str:
    cliente = obtener_cliente()

    for _ in range(reintentos):
        respuesta = ejecutar_solicitud(
            cliente,
            componente=COMPONENTE_BONITA,
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

    raise RuntimeError(
        f"No se encontró la tarea '{nombre_tarea}' "
        f"en estado ready para el caso {case_id}."
    )

def ejecutar_tarea(
    task_id: str,
    variables_contrato: dict[str, object],
) -> None:
    cliente = obtener_cliente()

    ejecutar_solicitud(
        cliente,
        componente=COMPONENTE_BONITA,
        metodo="POST",
        endpoint_normalizado="/API/bpm/userTask/{id}/execution",
        url=f"{BONITA_BASE_URL}/API/bpm/userTask/{task_id}/execution",
        idempotente=False,
        json=variables_contrato,
    )

def obtener_usuario_actual_id() -> str:
    cliente = obtener_cliente()

    respuesta = ejecutar_solicitud(
        cliente,
        componente=COMPONENTE_BONITA,
        metodo="GET",
        endpoint_normalizado="/API/system/session/1",
        url=f"{BONITA_BASE_URL}/API/system/session/1",
        idempotente=True,
    )

    datos = respuesta.json()

    return str(datos["user_id"])

def asignar_tarea(
    task_id: str,
    usuario_id: str,
) -> None:
    cliente = obtener_cliente()

    ejecutar_solicitud(
        cliente,
        componente=COMPONENTE_BONITA,
        metodo="PUT",
        endpoint_normalizado="/API/bpm/humanTask/{id}",
        url=f"{BONITA_BASE_URL}/API/bpm/humanTask/{task_id}",
        idempotente=True,
        json={
            "assigned_id": usuario_id,
        },
    )