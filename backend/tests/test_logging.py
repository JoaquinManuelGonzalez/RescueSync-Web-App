"""Formato y redaccion del contrato de logging."""

from __future__ import annotations

import json
import logging
import re

from app.core.logging import (
    VALOR_REDACTADO,
    FormateadorJsonLines,
    marca_de_tiempo,
    redactar,
    redactar_cabeceras,
)

PATRON_ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def _formatear(**campos) -> dict:
    registro = logging.LogRecord(
        name="rescuesync",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="",
        args=(),
        exc_info=None,
    )
    registro.evento = "llamada_saliente"
    registro.campos = campos
    return json.loads(FormateadorJsonLines().format(registro))


def test_el_timestamp_cumple_el_formato_del_contrato() -> None:
    assert PATRON_ISO_UTC.match(marca_de_tiempo())


def test_cada_evento_es_una_sola_linea_de_json_valido() -> None:
    evento = _formatear(componente_destino="bonita", codigo_estado=200)

    assert evento["evento"] == "llamada_saliente"
    assert evento["nivel"] == "INFO"
    assert evento["componente_destino"] == "bonita"
    assert PATRON_ISO_UTC.match(evento["timestamp"])


def test_el_nivel_warning_se_emite_como_warn() -> None:
    # El contrato nombra el nivel "WARN"; Python lo llama "WARNING".
    registro = logging.LogRecord(
        name="rescuesync",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="",
        args=(),
        exc_info=None,
    )
    evento = json.loads(FormateadorJsonLines().format(registro))

    assert evento["nivel"] == "WARN"


def test_se_redactan_los_campos_sensibles_anidados() -> None:
    entrada = {
        "ong_id": 12,
        "contacto": {"email": "persona@ong.test", "telefono": "11-5555-5555"},
        "ofertas": [{"cantidad": 3, "dni": "30111222"}],
    }

    salida = redactar(entrada)

    assert salida["ong_id"] == 12
    assert salida["contacto"]["email"] == VALOR_REDACTADO
    assert salida["contacto"]["telefono"] == VALOR_REDACTADO
    assert salida["ofertas"][0]["dni"] == VALOR_REDACTADO
    assert salida["ofertas"][0]["cantidad"] == 3


def test_se_redactan_las_cabeceras_enteras_sin_dejar_prefijo() -> None:
    salida = redactar_cabeceras(
        {"Authorization": "Bearer abc.def.ghi", "Accept": "application/json"}
    )

    assert salida["Authorization"] == VALOR_REDACTADO
    assert "abc" not in salida["Authorization"]
    assert salida["Accept"] == "application/json"
