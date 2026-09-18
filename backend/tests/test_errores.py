"""Envelope unico de error (docs/contratos/errores.md)."""

from __future__ import annotations

from app.core.errores import ReglaDeNegocioIncumplida

CAMPOS_DEL_ENVELOPE = {"codigo", "mensaje", "detalle", "timestamp", "id_correlacion"}


def test_una_ruta_inexistente_devuelve_el_envelope(cliente) -> None:
    respuesta = cliente.get("/no-existe")

    assert respuesta.status_code == 404

    error = respuesta.get_json()["error"]
    assert set(error) == CAMPOS_DEL_ENVELOPE
    assert error["codigo"] == "RECURSO_NO_ENCONTRADO"
    assert error["id_correlacion"]


def test_el_envelope_arrastra_el_id_de_correlacion_entrante(cliente) -> None:
    enviado = "1a2b3c4d-1111-4a2b-8c3d-9f0e1d2c3b4a"

    respuesta = cliente.get("/no-existe", headers={"X-Correlation-Id": enviado})

    assert respuesta.get_json()["error"]["id_correlacion"] == enviado


def test_un_error_de_dominio_usa_su_codigo_y_su_estado(app, cliente) -> None:
    @app.get("/prueba-de-error")
    def _prueba_de_error():
        raise ReglaDeNegocioIncumplida(
            "La ventana de recepcion de ofertas esta cerrada.",
            detalle=[{"campo": "convocatoria_id", "motivo": "cerrada"}],
        )

    respuesta = cliente.get("/prueba-de-error")

    assert respuesta.status_code == 422
    error = respuesta.get_json()["error"]
    assert error["codigo"] == "REGLA_DE_NEGOCIO_INCUMPLIDA"
    assert error["detalle"] == [{"campo": "convocatoria_id", "motivo": "cerrada"}]
