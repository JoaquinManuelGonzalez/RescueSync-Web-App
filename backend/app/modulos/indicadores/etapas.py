"""Etapas del proceso RescueSync y plazos objetivo, sin red ni base de datos.

Las etapas son las tareas humanas del BPMN vigente (no las que suponia la HU, que se escribio
antes de cerrar el modelo): "Ejecutar y finalizar actividades" y "Monitorear ejecucion" ya no
existen, y la ejecucion queda representada por "Esperar finalizacion de tareas", que se completa
cuando todas las ONGs terminan. Los nombres para buscar en Bonita son las constantes de
`core/integraciones/bonita/proceso.py`; aca se les da el nombre que ve una persona.

Duracion de una etapa = cuando se completo la tarea - cuando quedo disponible. Si la tarea se
ejecuto mas de una vez en el caso (por ejemplo, tras una reapertura), se suman sus ejecuciones.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.integraciones.bonita.consultas import (
    ESTADO_COMPLETADO,
    ESTADO_LISTO,
    NodoArchivado,
)
from app.core.integraciones.bonita.proceso import (
    NOMBRE_TAREA_DECIDIR_COBERTURA,
    NOMBRE_TAREA_FINALIZAR,
    NOMBRE_TAREA_PUBLICAR,
    NOMBRE_TAREA_SELECCIONAR,
)
from app.modulos.emergencias.modelos import NivelGravedad
from app.modulos.indicadores.tiempos import duracion_entre


@dataclass(frozen=True, slots=True)
class Etapa:
    nombre_en_bonita: str
    etiqueta: str


# En el orden en que ocurren en el proceso.
ETAPAS: tuple[Etapa, ...] = (
    Etapa(NOMBRE_TAREA_PUBLICAR, "Gestionar emergencia y publicar convocatoria"),
    Etapa(NOMBRE_TAREA_DECIDIR_COBERTURA, "Decidir acción ante cobertura insuficiente"),
    Etapa(NOMBRE_TAREA_SELECCIONAR, "Seleccionar ofertas"),
    Etapa(NOMBRE_TAREA_FINALIZAR, "Ejecución y finalización de actividades"),
)

# Plazo objetivo de resolucion de una emergencia segun su gravedad, en dias. Definido con el
# equipo para la HU de resolucion en termino; cambiarlo aca cambia el indicador.
PLAZO_OBJETIVO_DIAS: dict[NivelGravedad, int] = {
    NivelGravedad.critica: 3,
    NivelGravedad.alta: 7,
    NivelGravedad.media: 15,
    NivelGravedad.baja: 30,
}

TIPOS_DE_TAREA_HUMANA = frozenset({"USER_TASK", "HUMAN_TASK", "MANUAL_TASK"})


def _instante(nodo: NodoArchivado) -> datetime | None:
    return nodo.alcanzado_en or nodo.archivado_en


def duraciones_por_tarea(
    linea_de_tiempo: Iterable[NodoArchivado], inicio_del_caso: datetime
) -> dict[str, timedelta]:
    """Tiempo que estuvo disponible cada tarea humana del caso, sumando sus ejecuciones.

    Cuando quedo disponible una ejecucion:

    - si Bonita archivo su estado `ready`, es la fecha de ese registro;
    - si no, es cuando termino el nodo anterior del caso (o el inicio del caso). Vale porque el
      proceso es secuencial: mientras una tarea humana espera, no termina ningun otro nodo.
    """
    nodos = sorted(
        (nodo for nodo in linea_de_tiempo if _instante(nodo) is not None),
        key=lambda nodo: (_instante(nodo), nodo.estado == ESTADO_COMPLETADO),
    )
    disponible_desde = {
        nodo.nodo_id: _instante(nodo) for nodo in nodos if nodo.estado == ESTADO_LISTO
    }

    totales: dict[str, timedelta] = defaultdict(timedelta)
    ultimo_fin = inicio_del_caso
    for nodo in nodos:
        if nodo.estado == ESTADO_LISTO:
            continue
        fin = _instante(nodo)
        if nodo.tipo in TIPOS_DE_TAREA_HUMANA and nodo.estado == ESTADO_COMPLETADO:
            inicio = disponible_desde.get(nodo.nodo_id, ultimo_fin)
            totales[nodo.nombre] += duracion_entre(inicio, fin)
        ultimo_fin = max(ultimo_fin, fin)
    return dict(totales)
