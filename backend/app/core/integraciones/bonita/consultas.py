"""Consultas de solo lectura a Bonita para los indicadores de proceso (integracion 9).

El panel de auditoria combina los tiempos que registra el motor de procesos con datos propios
(gravedad y fecha de cada emergencia). Todo pasa por `ejecutar_solicitud_bonita`, asi que hereda
la sesion, los reintentos de las operaciones idempotentes (todas estas son GET), el logging de
`llamada_saliente` y la traduccion de errores: Bonita caido o lento -> 503
SERVICIO_EXTERNO_NO_DISPONIBLE, Bonita rechazando -> 422 SISTEMA_EXTERNO_RECHAZO. Una respuesta
con otra forma de la esperada se informa como 502 RESPUESTA_EXTERNA_INVALIDA.

Las consultas se hacen con el usuario tecnico (`BONITA_USER`): el auditor no tiene cuenta en
Bonita, y el usuario tecnico tiene que poder ver todos los casos del proceso.

Endpoints que se usan (REST API de Bonita):

- `GET /API/bpm/process?f=name=...`: todas las versiones desplegadas del proceso, para no perder
  los casos que se iniciaron con una version anterior.
- `GET /API/bpm/archivedCase?f=processDefinitionId=...`: casos terminados. El id del caso es
  `sourceObjectId`; `id` es el del registro archivado.
- `GET /API/bpm/case?f=processDefinitionId=...`: casos en curso.
- `GET /API/bpm/archivedFlowNode?f=caseId=...`: la linea de tiempo de un caso, con cada nodo
  (tareas, compuertas, eventos) que se completo. De ahi salen cuando quedo disponible cada tarea
  humana y cuando se completo.

Bonita informa las fechas como `aaaa-mm-dd hh:mm:ss.mmm` en la hora de su servidor, sin zona. Se
usan solo para restar entre si, asi que la zona no altera las duraciones.

Un caso terminado ya no cambia: su linea de tiempo se guarda en memoria y no se vuelve a pedir.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.errores import RespuestaExternaInvalida
from app.core.integraciones.bonita.sesion import (
    BONITA_BASE_URL,
    BONITA_USER,
    ejecutar_solicitud_bonita,
)

TAMANO_DE_PAGINA = 100
# Tope de seguridad: 50 paginas de 100 son 5000 registros, muy por encima del volumen esperado.
MAXIMO_DE_PAGINAS = 50

FORMATOS_DE_FECHA = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S")

ESTADO_COMPLETADO = "completed"
ESTADO_LISTO = "ready"


@dataclass(frozen=True, slots=True)
class CasoArchivado:
    """Un caso terminado del proceso, con su inicio y su fin."""

    caso_id: str
    iniciado_en: datetime
    finalizado_en: datetime


@dataclass(frozen=True, slots=True)
class NodoArchivado:
    """Un registro de la linea de tiempo de un caso.

    `nodo_id` identifica la ejecucion del nodo (`sourceObjectId`): una tarea que se ejecuta dos
    veces en el mismo caso (por ejemplo, tras una reapertura) tiene dos ids distintos. `tipo` es
    el de Bonita (`USER_TASK`, `HUMAN_TASK`, `GATEWAY`, `START_EVENT`, ...).
    """

    nodo_id: str
    nombre: str
    tipo: str
    estado: str
    alcanzado_en: datetime | None
    archivado_en: datetime | None


def _fecha(valor: Any) -> datetime | None:
    if not valor:
        return None
    for formato in FORMATOS_DE_FECHA:
        try:
            return datetime.strptime(str(valor), formato)
        except ValueError:
            continue
    raise RespuestaExternaInvalida(detalle={"componente": "bonita", "fecha": str(valor)})


def _paginar(endpoint: str, filtros: list[tuple[str, str]]) -> Iterator[dict[str, Any]]:
    """Recorre todas las paginas de una busqueda de la REST API de Bonita."""
    for pagina in range(MAXIMO_DE_PAGINAS):
        respuesta = ejecutar_solicitud_bonita(
            username=BONITA_USER,
            metodo="GET",
            endpoint_normalizado=endpoint,
            url=f"{BONITA_BASE_URL}{endpoint}",
            idempotente=True,
            params=[("p", str(pagina)), ("c", str(TAMANO_DE_PAGINA)), *filtros],
        )
        try:
            registros = respuesta.json()
        except ValueError as error:
            raise RespuestaExternaInvalida(detalle={"componente": "bonita"}) from error
        if not isinstance(registros, list):
            raise RespuestaExternaInvalida(detalle={"componente": "bonita"})
        yield from registros
        if len(registros) < TAMANO_DE_PAGINA:
            return


def listar_definiciones_del_proceso(nombre: str) -> list[str]:
    """Los ids de todas las versiones desplegadas del proceso `nombre`."""
    try:
        return [
            str(proceso["id"])
            for proceso in _paginar("/API/bpm/process", [("f", f"name={nombre}")])
        ]
    except KeyError as error:
        raise RespuestaExternaInvalida(detalle={"componente": "bonita"}) from error


def listar_casos_archivados(definiciones: list[str]) -> dict[str, CasoArchivado]:
    """Los casos terminados de esas definiciones, por id de caso."""
    casos: dict[str, CasoArchivado] = {}
    try:
        for definicion in definiciones:
            for registro in _paginar(
                "/API/bpm/archivedCase", [("f", f"processDefinitionId={definicion}")]
            ):
                iniciado_en, finalizado_en = _fecha(registro["start"]), _fecha(registro["end_date"])
                if iniciado_en is None or finalizado_en is None:
                    continue
                caso_id = str(registro["sourceObjectId"])
                casos[caso_id] = CasoArchivado(caso_id, iniciado_en, finalizado_en)
    except KeyError as error:
        raise RespuestaExternaInvalida(detalle={"componente": "bonita"}) from error
    return casos


def listar_ids_de_casos_abiertos(definiciones: list[str]) -> set[str]:
    """Los ids de los casos todavia en curso de esas definiciones."""
    try:
        return {
            str(registro["id"])
            for definicion in definiciones
            for registro in _paginar("/API/bpm/case", [("f", f"processDefinitionId={definicion}")])
        }
    except KeyError as error:
        raise RespuestaExternaInvalida(detalle={"componente": "bonita"}) from error


# Una linea de tiempo ocupa poco; el tope solo evita que la memoria crezca sin limite.
MAXIMO_DE_LINEAS_EN_MEMORIA = 5000
_lineas_de_tiempo: dict[str, tuple[NodoArchivado, ...]] = {}
_candado = threading.Lock()


def linea_de_tiempo_de_caso_terminado(caso_id: str) -> tuple[NodoArchivado, ...]:
    """Los nodos archivados de un caso terminado, en el orden en que se archivaron.

    Solo para casos terminados: como ya no cambian, la respuesta queda en memoria.
    """
    with _candado:
        conocida = _lineas_de_tiempo.get(caso_id)
    if conocida is not None:
        return conocida

    try:
        nodos = tuple(
            sorted(
                (
                    NodoArchivado(
                        nodo_id=str(registro["sourceObjectId"]),
                        nombre=str(registro["name"]),
                        tipo=str(registro.get("type", "")),
                        estado=str(registro.get("state", "")),
                        alcanzado_en=_fecha(registro.get("reached_state_date")),
                        archivado_en=_fecha(registro.get("archivedDate")),
                    )
                    for registro in _paginar(
                        "/API/bpm/archivedFlowNode", [("f", f"caseId={caso_id}")]
                    )
                ),
                key=lambda nodo: (nodo.archivado_en or datetime.min, nodo.nodo_id),
            )
        )
    except KeyError as error:
        raise RespuestaExternaInvalida(detalle={"componente": "bonita"}) from error

    with _candado:
        if len(_lineas_de_tiempo) >= MAXIMO_DE_LINEAS_EN_MEMORIA:
            _lineas_de_tiempo.clear()
        _lineas_de_tiempo[caso_id] = nodos
    return nodos


def olvidar_lineas_de_tiempo() -> None:
    """Vacia la memoria de lineas de tiempo (para los tests)."""
    with _candado:
        _lineas_de_tiempo.clear()
