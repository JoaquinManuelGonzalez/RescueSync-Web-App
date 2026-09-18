"""Politica de fail-fast del contrato de configuracion (CA-02 de la HU de arranque)."""

from __future__ import annotations

import json

import pytest

from app.core.configuracion import obtener_faltantes, validar_o_terminar
from tests.conftest import VARIABLES_MINIMAS


def test_sin_faltantes_no_termina(entorno_completo: None) -> None:
    assert obtener_faltantes() == []
    validar_o_terminar()  # no debe levantar SystemExit


def test_falta_database_url_corta_el_arranque(
    entorno_completo: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("DATABASE_URL")

    with pytest.raises(SystemExit) as salida:
        validar_o_terminar()

    assert salida.value.code != 0

    capturado = capsys.readouterr()
    esperado = "Falta la variable de entorno obligatoria: DATABASE_URL"

    # En texto plano, para que sea legible en `docker compose logs`.
    assert esperado in capturado.err

    # Y como evento JSON, porque lo exige el contrato de logging.
    evento = json.loads(capturado.out.strip().splitlines()[-1])
    assert evento["evento"] == "configuracion_invalida"
    assert evento["nivel"] == "ERROR"
    assert evento["mensaje"] == esperado


def test_una_variable_vacia_cuenta_como_faltante(
    entorno_completo: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SECRET_KEY", "   ")

    assert "SECRET_KEY" in obtener_faltantes()


def test_nunca_se_loguea_el_valor_de_una_variable(
    entorno_completo: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.delenv("BONITA_CALLBACK_TOKEN")

    with pytest.raises(SystemExit):
        validar_o_terminar()

    salida = capsys.readouterr()
    completa = salida.out + salida.err
    assert VARIABLES_MINIMAS["BONITA_CALLBACK_TOKEN"] not in completa
    assert VARIABLES_MINIMAS["POSTGRES_PASSWORD"] not in completa
