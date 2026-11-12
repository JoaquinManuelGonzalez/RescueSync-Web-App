from datetime import datetime

from app.core.integraciones.bonita.api import (
    asignar_tarea,
    buscar_tarea_humana,
    ejecutar_tarea,
    instanciar_proceso,
    obtener_usuario_actual_id,
)

NOMBRE_TAREA_PUBLICAR = "Gestionar emergencia y publicar convocatoria"
NOMBRE_TAREA_SELECCIONAR = "Seleccionar ofertas"
NOMBRE_TAREA_FINALIZAR = "Esperar finalizacion de tareas"
NOMBRE_TAREA_DECIDIR_COBERTURA = "Decidir acción ante cobertura insuficiente"


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


def confirmar_seleccion_ofertas(
    username: str,
    case_id: str,
    adjudicacion_id: int,
    compromisos_json: str,
    ongs_no_seleccionadas_json: str,
) -> None:
    task_id = buscar_tarea_humana(username, case_id, NOMBRE_TAREA_SELECCIONAR)
    usuario_id = obtener_usuario_actual_id(username)
    asignar_tarea(username, task_id, usuario_id)

    ejecutar_tarea(
        username,
        task_id,
        {
            "adjudicacionIdInput": str(adjudicacion_id),
            "compromisosInput": compromisos_json,
            "ongsNoSeleccionadasInput": ongs_no_seleccionadas_json,
        },
    )


def finalizar_actividad_ong(
    username: str,
    case_id: str,
    ofertas_finalizadas_input: str,
) -> None:
    """Completa en Bonita la finalización de una ONG para una emergencia."""
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

    ejecutar_tarea(
        username,
        task_id,
        {"ofertasFinalizadasInput": ofertas_finalizadas_input},
    )


def decidir_cobertura_insuficiente(
    username: str,
    case_id: str,
    decision: str,
) -> None:
    """Comunica a Bonita la decisión ante cobertura insuficiente."""
    if decision not in {"continuar", "reiniciar"}:
        raise ValueError("La decisión de cobertura no es válida.")

    task_id = buscar_tarea_humana(
        username,
        case_id,
        NOMBRE_TAREA_DECIDIR_COBERTURA,
    )

    usuario_id = obtener_usuario_actual_id(username)
    asignar_tarea(username, task_id, usuario_id)

    ejecutar_tarea(
        username,
        task_id,
        {"decisionCoberturaInput": decision},
    )
