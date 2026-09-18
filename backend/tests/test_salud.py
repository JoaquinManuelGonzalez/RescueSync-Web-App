"""El endpoint que mira el healthcheck del contenedor y el CA-01 de la HU de arranque."""

from __future__ import annotations


def test_health_responde_ok(cliente) -> None:
    respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"status": "ok", "db": "ok"}


def test_toda_respuesta_lleva_id_de_correlacion(cliente) -> None:
    respuesta = cliente.get("/health")

    assert respuesta.headers.get("X-Correlation-Id")


def test_se_respeta_el_id_de_correlacion_entrante(cliente) -> None:
    enviado = "8f3a1c22-5d6e-4f19-a0b1-2c3d4e5f6a7b"

    respuesta = cliente.get("/health", headers={"X-Correlation-Id": enviado})

    assert respuesta.headers["X-Correlation-Id"] == enviado
