import uuid
from datetime import datetime

from app.core.errores import ErrorDeAplicacion, SistemaExternoRechazo
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
# Sin tilde: es el nombre exacto de la tarea en el BPMN y la busqueda de Bonita lo compara tal cual.
NOMBRE_TAREA_DECIDIR_COBERTURA = "Decidir accion ante cobertura insuficiente"

# Actores del BPMN con los que la app actua en nombre de sus usuarios: el operador municipal
# inicia el caso y el coordinador publica la convocatoria y decide ante cobertura insuficiente.
ACTOR_MUNICIPAL = "Empleado municipal"
ACTOR_CENTRO_COORDINADOR = "Empleado centro coordinador"


def error_sin_guardar(
    error: ErrorDeAplicacion, operacion: str, consecuencia: str
) -> ErrorDeAplicacion:
    """El mismo error de Bonita, con un mensaje que dice que la operación no quedó guardada.

    Para las operaciones que se comunican al motor antes del commit. Conserva tipo, código y
    detalle, y distingue lo que docs/contratos/errores.md exige distinguir: un rechazo de Bonita
    muestra su motivo y no invita a reintentar, porque con los mismos datos se repetiría; una
    caída o una tarea que el caso todavía no habilitó sí invitan a reintentar.

    `operacion` va con su artículo ("la selección") y `consecuencia` es una oración completa
    ("No se guardó ningún cambio.").
    """
    # TAREA_DE_PROCESO_NO_DISPONIBLE y PROCESO_NO_DESPLEGADO tambien son SistemaExternoRechazo,
    # pero con codigo propio: no son un rechazo de los datos enviados.
    if error.codigo == SistemaExternoRechazo.codigo:
        motivo = error.detalle.get("motivo") if isinstance(error.detalle, dict) else None
        sufijo = f": {motivo}" if motivo else ""
        mensaje = f"El motor de procesos rechazó {operacion}{sufijo}. {consecuencia}"
    else:
        mensaje = (
            f"No pudimos comunicar {operacion} al motor de procesos. {consecuencia} "
            "Intentá de nuevo en unos minutos."
        )
    return error.__class__(
        mensaje, codigo=error.codigo, estado_http=error.estado_http, detalle=error.detalle
    )


def iniciar_gestion(
    emergencia_id: uuid.UUID,
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
    convocatoria_id: uuid.UUID,
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
    adjudicacion_id: uuid.UUID,
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
