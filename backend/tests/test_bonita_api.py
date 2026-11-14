"""Errores de la integracion con Bonita (integracion 3).

Todo lo que puede fallar al hablar con Bonita sale como `ErrorDeAplicacion`, para que cada
pantalla lo muestre como aviso y una API lo devuelva con el envelope del contrato, en vez de
terminar en un 500.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.errores import ErrorDeAplicacion, RespuestaExternaInvalida, SistemaExternoRechazo
from app.core.integraciones.bonita import api, sesion


def test_sin_la_tarea_lista_es_un_rechazo_con_codigo_propio(monkeypatch) -> None:
    llamadas = []

    def _sin_tareas(**argumentos):
        llamadas.append(argumentos)
        return httpx.Response(200, json=[])

    monkeypatch.setattr(api, "ejecutar_solicitud_bonita", _sin_tareas)
    monkeypatch.setattr(api.time, "sleep", lambda _segundos: None)

    with pytest.raises(SistemaExternoRechazo) as error:
        api.buscar_tarea_humana("coordinador@rescuesync.test", "4001", "Seleccionar ofertas")

    assert error.value.codigo == "TAREA_DE_PROCESO_NO_DISPONIBLE"
    assert "Seleccionar ofertas" in error.value.mensaje
    assert error.value.detalle == {
        "componente": "bonita",
        "tarea": "Seleccionar ofertas",
        "caso": "4001",
    }
    assert len(llamadas) == 5, "espera a que el motor habilite la tarea antes de rendirse"


def test_un_proceso_no_desplegado_es_un_rechazo_con_codigo_propio(monkeypatch) -> None:
    monkeypatch.setattr(api, "_process_definition_id", None)
    monkeypatch.setattr(
        api, "ejecutar_solicitud_bonita", lambda **_argumentos: httpx.Response(200, json=[])
    )

    with pytest.raises(SistemaExternoRechazo) as error:
        api.obtener_process_definition_id("walter.bates")

    assert error.value.codigo == "PROCESO_NO_DESPLEGADO"
    assert api.BONITA_PROCESO_NOMBRE in error.value.mensaje


def test_una_instancia_sin_case_id_es_una_respuesta_invalida(monkeypatch) -> None:
    monkeypatch.setattr(api, "obtener_process_definition_id", lambda _username: "7")
    monkeypatch.setattr(
        api, "ejecutar_solicitud_bonita", lambda **_argumentos: httpx.Response(200, json={})
    )

    with pytest.raises(RespuestaExternaInvalida):
        api.instanciar_proceso("walter.bates", {"emergenciaIdInput": "1"})


def test_un_login_sin_token_es_una_respuesta_invalida(monkeypatch) -> None:
    # Bonita acepta el login (sin error) pero no devuelve la cookie del token.
    monkeypatch.setattr(sesion, "ejecutar_solicitud", lambda *_args, **_kwargs: None)

    with pytest.raises(RespuestaExternaInvalida) as error:
        sesion.iniciar_sesion(sesion.BONITA_USER)

    assert isinstance(error.value, ErrorDeAplicacion)
    assert error.value.detalle == {"componente": "bonita", "falta": "X-Bonita-API-Token"}
