"""Consultas de solo lectura a Bonita para el panel de auditoria (integracion 9).

Se reemplaza `ejecutar_solicitud_bonita` (la sesion, los reintentos y el logging ya tienen sus
propios tests) y se verifica como se recorren las paginas y se interpreta lo que responde Bonita.
"""

from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from app.core.errores import RespuestaExternaInvalida
from app.core.integraciones.bonita import consultas


class BonitaFalso:
    """Responde por endpoint con listas de registros, paginadas como la REST API de Bonita."""

    def __init__(self, registros_por_endpoint: dict[str, list]) -> None:
        self.registros = registros_por_endpoint
        self.llamadas: list[tuple[str, dict]] = []

    def __call__(self, *, endpoint_normalizado: str, params, idempotente: bool, **_):
        assert idempotente, "las consultas del panel son GET idempotentes"
        parametros = dict(params)
        self.llamadas.append((endpoint_normalizado, parametros))
        pagina, tamano = int(parametros["p"]), int(parametros["c"])
        registros = self.registros[endpoint_normalizado]
        return httpx.Response(200, json=registros[pagina * tamano : (pagina + 1) * tamano])


@pytest.fixture
def bonita(monkeypatch: pytest.MonkeyPatch):
    def _instalar(registros: dict[str, list]) -> BonitaFalso:
        falso = BonitaFalso(registros)
        monkeypatch.setattr(consultas, "ejecutar_solicitud_bonita", falso)
        return falso

    consultas.vaciar_memoria()
    yield _instalar
    consultas.vaciar_memoria()


def test_recorre_todas_las_paginas(bonita) -> None:
    casos = [{"id": str(i)} for i in range(consultas.TAMANO_DE_PAGINA + 3)]
    falso = bonita({"/API/bpm/case": casos})

    abiertos = consultas.listar_ids_de_casos_abiertos(["7"])

    assert len(abiertos) == consultas.TAMANO_DE_PAGINA + 3
    assert [parametros["p"] for _, parametros in falso.llamadas] == ["0", "1"]
    assert falso.llamadas[0][1]["f"] == "processDefinitionId=7"


def test_el_caso_archivado_se_identifica_por_su_caso_original(bonita) -> None:
    bonita(
        {
            "/API/bpm/archivedCase": [
                {
                    "id": "9001",
                    "sourceObjectId": "15",
                    "start": "2026-10-01 09:00:00.000",
                    "end_date": "2026-10-08 21:30:00.500",
                }
            ]
        }
    )

    casos = consultas.listar_casos_archivados(["7"])

    assert casos == {
        "15": consultas.CasoArchivado(
            "15", datetime(2026, 10, 1, 9, 0), datetime(2026, 10, 8, 21, 30, 0, 500000), "7"
        )
    }


def _nodo(caso: str, nodo: str, nombre: str, archivado: str) -> dict[str, str]:
    return {
        "sourceObjectId": nodo,
        "caseId": caso,
        "rootCaseId": caso,
        "name": nombre,
        "type": "USER_TASK",
        "state": "completed",
        "reached_state_date": archivado,
        "archivedDate": archivado,
    }


def _caso(caso_id: str, inicio: str, definicion: str = "7") -> consultas.CasoArchivado:
    iniciado_en = datetime.fromisoformat(inicio)
    return consultas.CasoArchivado(caso_id, iniciado_en, iniciado_en, definicion)


def test_las_lineas_de_tiempo_se_piden_en_lote_y_quedan_en_memoria(bonita) -> None:
    # Como responde Bonita: de lo mas reciente a lo mas viejo, mezclando casos.
    falso = bonita(
        {
            "/API/bpm/archivedFlowNode": [
                _nodo("16", "4", "Seleccionar ofertas", "2026-10-05 10:00:00"),
                _nodo("99", "9", "Seleccionar ofertas", "2026-10-04 10:00:00"),
                _nodo("15", "2", "Seleccionar ofertas", "2026-10-03 10:00:00"),
                _nodo("16", "3", "Gestionar emergencia", "2026-10-02 10:00:00"),
                _nodo("15", "1", "Gestionar emergencia", "2026-10-01 09:00:01"),
            ]
        }
    )
    casos = [_caso("15", "2026-10-01 09:00:00"), _caso("16", "2026-10-02 09:00:00")]

    primera = consultas.lineas_de_tiempo(casos)
    segunda = consultas.lineas_de_tiempo(casos)

    assert [nodo.nodo_id for nodo in primera["15"]] == ["1", "2"]
    assert [nodo.nodo_id for nodo in primera["16"]] == ["3", "4"]
    assert "99" not in primera, "solo se devuelven los casos pedidos"
    assert segunda == primera
    assert len(falso.llamadas) == 1, "una sola busqueda para todos los casos, y luego memoria"
    _, parametros = falso.llamadas[0]
    assert parametros["f"] == "processId=7"
    assert parametros["o"] == "archivedDate DESC"


def test_la_busqueda_de_nodos_se_corta_al_pasar_el_inicio_del_caso_mas_viejo(bonita) -> None:
    recientes = [
        _nodo("15", str(i), "Seleccionar ofertas", "2026-10-03 10:00:00")
        for i in range(consultas.TAMANO_DE_PAGINA)
    ]
    viejos = [
        _nodo("8", str(1000 + i), "Seleccionar ofertas", "2026-09-01 10:00:00")
        for i in range(2 * consultas.TAMANO_DE_PAGINA)
    ]
    falso = bonita({"/API/bpm/archivedFlowNode": recientes + viejos})

    lineas = consultas.lineas_de_tiempo([_caso("15", "2026-10-01 09:00:00")])

    assert len(lineas["15"]) == consultas.TAMANO_DE_PAGINA
    assert [parametros["p"] for _, parametros in falso.llamadas] == ["0", "1"]


def test_un_caso_sin_nodos_no_queda_en_memoria(bonita) -> None:
    falso = bonita({"/API/bpm/archivedFlowNode": []})
    casos = [_caso("15", "2026-10-01 09:00:00")]

    assert consultas.lineas_de_tiempo(casos) == {"15": ()}
    consultas.lineas_de_tiempo(casos)

    assert len(falso.llamadas) == 2


def test_la_foto_del_proceso_se_reutiliza_mientras_esta_vigente(bonita, monkeypatch) -> None:
    falso = bonita(
        {
            "/API/bpm/process": [{"id": "7"}],
            "/API/bpm/archivedCase": [
                {"sourceObjectId": "15", "start": "2026-10-01 09:00:00", "end_date": None},
            ],
            "/API/bpm/case": [{"id": "16"}],
        }
    )
    reloj = iter([0.0, 30.0, consultas.SEGUNDOS_DE_VIGENCIA_DE_LA_FOTO + 1])
    monkeypatch.setattr(consultas.time, "monotonic", lambda: next(reloj))

    foto = consultas.foto_del_proceso("RescueSync")
    assert foto.definiciones == ("7",)
    assert foto.casos_terminados == {}, "un caso sin fecha de fin no esta terminado"
    assert foto.casos_abiertos == frozenset({"16"})
    assert len(falso.llamadas) == 3

    assert consultas.foto_del_proceso("RescueSync") is foto
    assert len(falso.llamadas) == 3

    consultas.foto_del_proceso("RescueSync")
    assert len(falso.llamadas) == 6, "vencida la vigencia, se vuelve a consultar"


@pytest.mark.parametrize(
    "registro",
    [
        {"id": "1", "start": "ayer", "end_date": "hoy", "sourceObjectId": "1"},
        {"id": "1", "start": "2026-10-01 09:00:00"},
    ],
)
def test_una_respuesta_con_otra_forma_es_invalida(bonita, registro) -> None:
    bonita({"/API/bpm/archivedCase": [registro]})

    with pytest.raises(RespuestaExternaInvalida):
        consultas.listar_casos_archivados(["7"])
