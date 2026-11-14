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
- `GET /API/bpm/archivedFlowNode?f=processId=...&o=archivedDate DESC`: los nodos archivados
  (tareas, compuertas, eventos) de todos los casos de una version, de lo mas reciente a lo mas
  viejo. De ahi salen cuando quedo disponible cada tarea humana y cuando se completo. Bonita no
  admite filtrar por `type` ni ordenar `archivedCase` (responde 500), por eso no se usan.

Bonita informa las fechas como `aaaa-mm-dd hh:mm:ss.mmm` en la hora de su servidor, sin zona. Se
usan solo para compararlas y restarlas entre si, asi que la zona no altera nada.

Memoria, para no repetir llamadas:

- La "foto" del proceso (versiones, casos terminados y casos abiertos) vale unos segundos: la
  pestaña, los cambios de filtro y las exportaciones de esa ventana la comparten.
- Un caso terminado ya no cambia: su linea de tiempo queda en memoria. Las que faltan se piden en
  lote (una busqueda paginada por version que se corta al llegar al inicio del caso mas viejo que
  se necesita), no una llamada por caso.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Iterable, Iterator
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
# Tope de seguridad: 50 paginas de 100 son 5000 registros, muy por encima del volumen esperado de
# versiones o casos.
MAXIMO_DE_PAGINAS = 50
# Los nodos archivados son unos 30 por caso; con el corte por fecha rara vez se llega a este tope.
MAXIMO_DE_PAGINAS_DE_NODOS = 200

FORMATOS_DE_FECHA = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S")

ESTADO_COMPLETADO = "completed"
ESTADO_LISTO = "ready"

SEGUNDOS_DE_VIGENCIA_DE_LA_FOTO = 60


@dataclass(frozen=True, slots=True)
class CasoArchivado:
    """Un caso terminado del proceso, con su inicio, su fin y la version que lo ejecuto."""

    caso_id: str
    iniciado_en: datetime
    finalizado_en: datetime
    definicion: str = ""


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


@dataclass(frozen=True, slots=True)
class FotoDelProceso:
    """Lo que el panel necesita saber de todos los casos del proceso en un momento dado."""

    definiciones: tuple[str, ...]
    casos_terminados: dict[str, CasoArchivado]
    casos_abiertos: frozenset[str]


def _fecha(valor: Any) -> datetime | None:
    if not valor:
        return None
    for formato in FORMATOS_DE_FECHA:
        try:
            return datetime.strptime(str(valor), formato)
        except ValueError:
            continue
    raise RespuestaExternaInvalida(detalle={"componente": "bonita", "fecha": str(valor)})


def _paginar(
    endpoint: str,
    filtros: list[tuple[str, str]],
    *,
    maximo_de_paginas: int = MAXIMO_DE_PAGINAS,
) -> Iterator[dict[str, Any]]:
    """Recorre las paginas de una busqueda de la REST API de Bonita.

    Es un generador: pide la pagina siguiente solo cuando se termina de leer la anterior, asi que
    quien deja de iterar corta tambien las llamadas.
    """
    for pagina in range(maximo_de_paginas):
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


def listar_casos_archivados(definiciones: Iterable[str]) -> dict[str, CasoArchivado]:
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
                casos[caso_id] = CasoArchivado(caso_id, iniciado_en, finalizado_en, definicion)
    except KeyError as error:
        raise RespuestaExternaInvalida(detalle={"componente": "bonita"}) from error
    return casos


def listar_ids_de_casos_abiertos(definiciones: Iterable[str]) -> set[str]:
    """Los ids de los casos todavia en curso de esas definiciones."""
    try:
        return {
            str(registro["id"])
            for definicion in definiciones
            for registro in _paginar("/API/bpm/case", [("f", f"processDefinitionId={definicion}")])
        }
    except KeyError as error:
        raise RespuestaExternaInvalida(detalle={"componente": "bonita"}) from error


# --- Memoria ----------------------------------------------------------------------------
# Por proceso del servidor y protegida por un candado. Si dos pedidos llegan con la foto vencida,
# los dos la piden: es un caso raro y no justifica coordinar mas.

_candado = threading.Lock()
_foto: tuple[float, str, FotoDelProceso] | None = None

# Una linea de tiempo ocupa poco; el tope solo evita que la memoria crezca sin limite.
MAXIMO_DE_LINEAS_EN_MEMORIA = 5000
_lineas_de_tiempo: dict[str, tuple[NodoArchivado, ...]] = {}


def foto_del_proceso(nombre: str) -> FotoDelProceso:
    """Versiones, casos terminados y casos abiertos del proceso `nombre`.

    Se reutiliza durante `SEGUNDOS_DE_VIGENCIA_DE_LA_FOTO`: un caso que termina en esa ventana
    aparece en la consulta siguiente.
    """
    global _foto
    ahora = time.monotonic()
    with _candado:
        if _foto is not None:
            tomada_en, nombre_de_la_foto, foto = _foto
            if nombre_de_la_foto == nombre and ahora - tomada_en < SEGUNDOS_DE_VIGENCIA_DE_LA_FOTO:
                return foto

    definiciones = tuple(listar_definiciones_del_proceso(nombre))
    foto = FotoDelProceso(
        definiciones=definiciones,
        casos_terminados=listar_casos_archivados(definiciones),
        casos_abiertos=frozenset(listar_ids_de_casos_abiertos(definiciones)),
    )
    with _candado:
        _foto = (ahora, nombre, foto)
    return foto


def _nodo(registro: dict[str, Any]) -> NodoArchivado:
    return NodoArchivado(
        nodo_id=str(registro["sourceObjectId"]),
        nombre=str(registro["name"]),
        tipo=str(registro.get("type", "")),
        estado=str(registro.get("state", "")),
        alcanzado_en=_fecha(registro.get("reached_state_date")),
        archivado_en=_fecha(registro.get("archivedDate")),
    )


def _ordenar(nodos: Iterable[NodoArchivado]) -> tuple[NodoArchivado, ...]:
    return tuple(sorted(nodos, key=lambda nodo: (nodo.archivado_en or datetime.min, nodo.nodo_id)))


def _pedir_lineas_de_tiempo(
    definicion: str, casos: list[CasoArchivado]
) -> dict[str, tuple[NodoArchivado, ...]]:
    """Las lineas de tiempo de esos casos de una misma version, en una busqueda paginada.

    Los nodos llegan del mas reciente al mas viejo. Ningun nodo de un caso se archiva antes de que
    el caso empiece, asi que al pasar el inicio del caso mas viejo pedido ya no queda nada util.
    """
    buscados = {caso.caso_id for caso in casos}
    corte = min(caso.iniciado_en for caso in casos)
    nodos: dict[str, list[NodoArchivado]] = defaultdict(list)
    try:
        for registro in _paginar(
            "/API/bpm/archivedFlowNode",
            [("f", f"processId={definicion}"), ("o", "archivedDate DESC")],
            maximo_de_paginas=MAXIMO_DE_PAGINAS_DE_NODOS,
        ):
            nodo = _nodo(registro)
            if nodo.archivado_en is not None and nodo.archivado_en < corte:
                break
            caso_id = str(registro.get("rootCaseId") or registro["caseId"])
            if caso_id in buscados:
                nodos[caso_id].append(nodo)
    except KeyError as error:
        raise RespuestaExternaInvalida(detalle={"componente": "bonita"}) from error
    return {caso_id: _ordenar(nodos_del_caso) for caso_id, nodos_del_caso in nodos.items()}


def lineas_de_tiempo(casos: Iterable[CasoArchivado]) -> dict[str, tuple[NodoArchivado, ...]]:
    """Los nodos archivados de esos casos terminados, por id de caso, en el orden en que se
    archivaron.

    Solo para casos terminados: como ya no cambian, quedan en memoria. Los que faltan se piden
    agrupados por version (`_pedir_lineas_de_tiempo`). Un caso del que Bonita no devuelve nodos
    no se guarda, para volver a intentarlo la proxima vez.
    """
    casos = list(casos)
    with _candado:
        conocidas = {
            caso.caso_id: _lineas_de_tiempo[caso.caso_id]
            for caso in casos
            if caso.caso_id in _lineas_de_tiempo
        }

    faltantes: dict[str, list[CasoArchivado]] = defaultdict(list)
    for caso in casos:
        if caso.caso_id not in conocidas:
            faltantes[caso.definicion].append(caso)

    nuevas: dict[str, tuple[NodoArchivado, ...]] = {}
    for definicion, casos_de_la_version in faltantes.items():
        nuevas.update(_pedir_lineas_de_tiempo(definicion, casos_de_la_version))

    if nuevas:
        with _candado:
            if len(_lineas_de_tiempo) + len(nuevas) > MAXIMO_DE_LINEAS_EN_MEMORIA:
                _lineas_de_tiempo.clear()
            _lineas_de_tiempo.update(nuevas)

    todas = {**nuevas, **conocidas}
    return {caso.caso_id: todas.get(caso.caso_id, ()) for caso in casos}


def vaciar_memoria() -> None:
    """Olvida la foto del proceso y las lineas de tiempo (para los tests)."""
    global _foto
    with _candado:
        _foto = None
        _lineas_de_tiempo.clear()
