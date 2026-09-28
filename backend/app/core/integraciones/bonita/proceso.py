from datetime import datetime

from app.core.integraciones.bonita.api import (
    asignar_tarea,
    buscar_tarea_humana,
    ejecutar_tarea,
    instanciar_proceso,
    obtener_usuario_actual_id,
)


NOMBRE_TAREA_PUBLICAR = "Gestionar emergencia y publicar convocatoria"


def iniciar_gestion(emergencia_id: int) -> str:
    return instanciar_proceso(
        {
            "emergenciaIdInput": str(emergencia_id),
        }
    )


def publicar_convocatoria(
    case_id: str,
    fecha_cierre: datetime,
) -> None:
    task_id = buscar_tarea_humana(
        case_id,
        NOMBRE_TAREA_PUBLICAR,
    )

    usuario_id = obtener_usuario_actual_id()

    asignar_tarea(
        task_id,
        usuario_id,
    )

    ejecutar_tarea(
        task_id,
        {
            "timerInput": fecha_cierre.isoformat(),
        },
    )