"""Errores de la integracion con Bonita (integracion 3).

Todo lo que puede fallar al hablar con Bonita sale como `ErrorDeAplicacion`, para que cada
pantalla lo muestre como aviso y una API lo devuelva con el envelope del contrato, en vez de
terminar en un 500.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.errores import (
    ErrorDeAplicacion,
    RespuestaExternaInvalida,
    ServicioExternoNoDisponible,
    SistemaExternoRechazo,
)
from app.core.integraciones.bonita import api, sesion
from app.core.integraciones.bonita.proceso import error_sin_guardar


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


def test_el_timeout_de_lectura_hacia_bonita_es_configurable(monkeypatch) -> None:
    from app.core.integraciones import cliente_http

    recibidos = []

    def _responder(solicitud: httpx.Request) -> httpx.Response:
        recibidos.append(solicitud.extensions["timeout"])
        return httpx.Response(200, json=[])

    with httpx.Client(transport=httpx.MockTransport(_responder)) as cliente:
        cliente_http.ejecutar_solicitud(
            cliente,
            componente=cliente_http.COMPONENTE_BONITA,
            metodo="GET",
            endpoint_normalizado="/API/bpm/case",
            url="http://bonita.invalido/bonita/API/bpm/case",
            idempotente=True,
            timeout_lectura_s=25,
        )

    assert recibidos[0]["read"] == 25
    assert recibidos[0]["connect"] == cliente_http.TIMEOUT_CONEXION_S


def test_las_llamadas_a_bonita_usan_bonita_timeout_s(monkeypatch) -> None:
    argumentos = {}
    monkeypatch.setattr(sesion, "obtener_cliente", lambda _username: None)
    monkeypatch.setattr(sesion, "BONITA_TIMEOUT_S", 42.0)
    monkeypatch.setattr(
        sesion, "ejecutar_solicitud", lambda _cliente, **kwargs: argumentos.update(kwargs)
    )

    sesion.ejecutar_solicitud_bonita(
        username="walter.bates",
        metodo="GET",
        endpoint_normalizado="/API/bpm/case",
        url="http://bonita.invalido/bonita/API/bpm/case",
        idempotente=True,
    )

    assert argumentos["timeout_lectura_s"] == 42.0


# --- Motivo de un rechazo de Bonita -----------------------------------------------


def _bonita_que_responde(monkeypatch, respuesta: httpx.Response) -> None:
    cliente = httpx.Client(transport=httpx.MockTransport(lambda _solicitud: respuesta))
    monkeypatch.setattr(sesion, "obtener_cliente", lambda _username: cliente)


def _ejecutar_tarea() -> None:
    sesion.ejecutar_solicitud_bonita(
        username="walter.bates",
        metodo="POST",
        endpoint_normalizado="/API/bpm/userTask/{id}/execution",
        url="http://bonita.invalido/bonita/API/bpm/userTask/140008/execution",
        idempotente=False,
        json={"adjudicacionIdInput": "01a1f0db-8d45-73b6-94e1-0ca9d49bc2cf"},
    )


def test_una_violacion_de_contrato_trae_el_motivo_y_queda_en_el_log(monkeypatch, caplog) -> None:
    """Sin el motivo, un 400 al ejecutar una tarea solo se diagnosticaba en el log de Tomcat."""
    _bonita_que_responde(
        monkeypatch,
        httpx.Response(
            400,
            json={
                "exception": "class org.bonitasoft.engine.bpm.contract.ContractViolationException",
                "message": "Error while validating constraints",
                "explanations": ["El identificador de adjudicación es inválido"],
            },
        ),
    )

    with caplog.at_level("WARNING"), pytest.raises(SistemaExternoRechazo) as error:
        _ejecutar_tarea()

    assert error.value.detalle == {
        "componente": "bonita",
        "codigo_estado": 400,
        "motivo": "El identificador de adjudicación es inválido",
    }
    (rechazo,) = [r for r in caplog.records if getattr(r, "evento", "") == "bonita_rechazo"]
    assert rechazo.campos["endpoint"] == "/API/bpm/userTask/{id}/execution"
    assert rechazo.campos["motivo"] == "El identificador de adjudicación es inválido"


def test_un_rechazo_sin_explicaciones_no_toma_nada_del_cuerpo(monkeypatch, caplog) -> None:
    # `message` puede repetir datos de la solicitud: solo se usan las `explanations`.
    _bonita_que_responde(
        monkeypatch, httpx.Response(404, json={"message": "Caso 01a1f0db no encontrado"})
    )

    with caplog.at_level("WARNING"), pytest.raises(SistemaExternoRechazo) as error:
        _ejecutar_tarea()

    assert error.value.detalle == {"componente": "bonita", "codigo_estado": 404}
    assert not [r for r in caplog.records if getattr(r, "evento", "") == "bonita_rechazo"]


@pytest.mark.parametrize(
    ("respuesta", "motivo"),
    [
        (httpx.Response(400, text="<html>Bad Request</html>"), None),
        (httpx.Response(400, json=["no es un objeto"]), None),
        (
            httpx.Response(400, json={"explanations": ["  ", "Falta el input x"]}),
            "Falta el input x",
        ),
        (httpx.Response(400, json={"explanations": ["Uno", "Dos"]}), "Uno | Dos"),
        (
            httpx.Response(400, json={"explanations": ["x" * 500]}),
            "x" * sesion.LARGO_MAXIMO_MOTIVO,
        ),
    ],
)
def test_motivo_del_rechazo_tolera_cualquier_cuerpo(respuesta, motivo) -> None:
    assert sesion.motivo_del_rechazo(respuesta) == motivo


# --- Mensaje de una operacion que no se guardo porque Bonita no la recibio --------


@pytest.mark.parametrize(
    ("error", "mensaje"),
    [
        (
            SistemaExternoRechazo(detalle={"codigo_estado": 400, "motivo": "El id es inválido"}),
            "El motor de procesos rechazó la selección: El id es inválido. No se guardó ningún "
            "cambio.",
        ),
        (
            SistemaExternoRechazo(detalle={"codigo_estado": 404}),
            "El motor de procesos rechazó la selección. No se guardó ningún cambio.",
        ),
        (
            ServicioExternoNoDisponible(detalle={"componente": "bonita"}),
            "No pudimos comunicar la selección al motor de procesos. No se guardó ningún cambio. "
            "Intentá de nuevo en unos minutos.",
        ),
        (
            SistemaExternoRechazo(codigo="TAREA_DE_PROCESO_NO_DISPONIBLE", detalle={}),
            "No pudimos comunicar la selección al motor de procesos. No se guardó ningún cambio. "
            "Intentá de nuevo en unos minutos.",
        ),
    ],
    ids=["rechazo-con-motivo", "rechazo-sin-motivo", "caido", "tarea-no-habilitada"],
)
def test_error_sin_guardar_solo_invita_a_reintentar_si_tiene_sentido(error, mensaje) -> None:
    resultado = error_sin_guardar(error, "la selección", "No se guardó ningún cambio.")

    assert resultado.mensaje == mensaje
    assert type(resultado) is type(error)
    assert (resultado.codigo, resultado.estado_http, resultado.detalle) == (
        error.codigo,
        error.estado_http,
        error.detalle,
    )
