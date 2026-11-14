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

    consultas.olvidar_lineas_de_tiempo()
    yield _instalar
    consultas.olvidar_lineas_de_tiempo()


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
            "15", datetime(2026, 10, 1, 9, 0), datetime(2026, 10, 8, 21, 30, 0, 500000)
        )
    }


def test_la_linea_de_tiempo_se_ordena_y_queda_en_memoria(bonita) -> None:
    falso = bonita(
        {
            "/API/bpm/archivedFlowNode": [
                {
                    "sourceObjectId": "2",
                    "name": "Seleccionar ofertas",
                    "type": "USER_TASK",
                    "state": "completed",
                    "reached_state_date": "2026-10-03 10:00:00",
                    "archivedDate": "2026-10-03 10:00:01",
                },
                {
                    "sourceObjectId": "1",
                    "name": "Inicio",
                    "type": "START_EVENT",
                    "state": "completed",
                    "reached_state_date": "2026-10-01 09:00:00",
                    "archivedDate": "2026-10-01 09:00:01",
                },
            ]
        }
    )

    primera = consultas.linea_de_tiempo_de_caso_terminado("15")
    segunda = consultas.linea_de_tiempo_de_caso_terminado("15")

    assert [nodo.nombre for nodo in primera] == ["Inicio", "Seleccionar ofertas"]
    assert segunda is primera
    assert len(falso.llamadas) == 1


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
