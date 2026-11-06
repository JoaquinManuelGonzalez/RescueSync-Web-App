from datetime import datetime

from app.core.integraciones.bonita.api import (
    asignar_tarea,
    buscar_tarea_humana,
    ejecutar_tarea,
    instanciar_proceso,
    obtener_usuario_actual_id,
)

NOMBRE_TAREA_PUBLICAR = "Gestionar emergencia y publicar convocatoria"
NOMBRE_TAREA_FINALIZAR = "Ejecutar y finalizar actividades"


def iniciar_gestion(
    emergencia_id: int,
    username: str,
) -> str:
    return instanciar_proceso(
        username,
        {
            "emergenciaIdInput": str(emergencia_id),
        },
    )


def publicar_convocatoria(
    username: str,
    case_id: str,
    convocatoria_id: int,
    fecha_cierre: datetime,
) -> None:
    task_id = buscar_tarea_humana(
        username,
        case_id,
        NOMBRE_TAREA_PUBLICAR,
    )

    usuario_id = obtener_usuario_actual_id(username)

    asignar_tarea(
        username,
        task_id,
        usuario_id,
    )

    ejecutar_tarea(
        username,
        task_id,
        {
            "timerInput": fecha_cierre.isoformat(),
            "convocatoriaIdInput": str(convocatoria_id),
        },
    )


def finalizar_actividad_ong(
    username: str,
    case_id: str,
    identificador_ong: str,
    observaciones: str | None = None,
) -> None:
    """Ejecuta en Bonita la tarea humana 'Ejecutar y finalizar actividades' asignada a la ONG."""
    task_id = buscar_tarea_humana(
        username,
        case_id,
        NOMBRE_TAREA_FINALIZAR,
    )

    usuario_id = obtener_usuario_actual_id(username)

    asignar_tarea(
        username,
        task_id,
        usuario_id,
    )

    # Según el proceso BPMN, la tarea humana no requiere inputs de contrato
    ejecutar_tarea(
        username,
        task_id,
        {},
    )

