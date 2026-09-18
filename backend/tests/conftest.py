"""Configuracion compartida de los tests."""

from __future__ import annotations

import pytest


VARIABLES_MINIMAS: dict[str, str] = {
    "SECRET_KEY": "clave-de-prueba",
    "POSTGRES_USER": "prueba",
    "POSTGRES_PASSWORD": "prueba",
    "DATABASE_URL": "sqlite://",
    "BONITA_BASE_URL": "http://bonita.invalido/bonita",
    "BONITA_USER": "prueba",
    "BONITA_PASSWORD": "prueba",
    "BONITA_CALLBACK_TOKEN": "token-de-prueba",
    "API_NACIONAL_BASE_URL": "http://api.invalido",
    "API_NACIONAL_CLIENT_ID": "prueba",
    "API_NACIONAL_CLIENT_SECRET": "prueba",
}


@pytest.fixture
def entorno_completo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deja en el entorno todas las variables obligatorias."""
    for nombre, valor in VARIABLES_MINIMAS.items():
        monkeypatch.setenv(nombre, valor)


@pytest.fixture
def app(entorno_completo: None):
    """Aplicacion de pruebas, contra SQLite en memoria."""
    from app import create_app

    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})


@pytest.fixture
def cliente(app):
    return app.test_client()
