from __future__ import annotations

import os

from app.core.integraciones.cliente_http import (
    COMPONENTE_BONITA,
    ejecutar_solicitud,
)
from app.core.integraciones.bonita.sesion import (
    BONITA_BASE_URL,
    obtener_cliente,
)

BONITA_PROCESO_NOMBRE = os.environ["BONITA_PROCESO_NOMBRE"]
BONITA_PROCESO_VERSION = os.environ["BONITA_PROCESO_VERSION"]

_process_definition_id: str | None = None

def obtener_process_definition_id() -> str:
    global _process_definition_id

    if _process_definition_id is not None:
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