"""Configuracion compartida de los tests.

Una advertencia que cuesta cara si se pasa por alto: **no hay que dejar un `app_context`
abierto mientras se hacen solicitudes con el cliente de pruebas**. Flask reutiliza el contexto
de aplicacion que ya esta arriba en vez de empujar uno nuevo por solicitud, y entonces `g`
sobrevive de una solicitud a la siguiente. Eso hace, por ejemplo, que `generate_csrf()` devuelva
el token cacheado en `g` de la solicitud anterior y que la validacion CSRF falle sin motivo
aparente. Por eso `base_de_datos` abre el contexto, prepara el esquema y lo cierra antes de
devolver el control.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import Any

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

# Cuentas que deja `flask seed`, una por perfil. Los tests de autorizacion recorren esta tabla.
CONTRASENA_SEMILLA = "RescueSync.2026"

EMAIL_ADMINISTRADOR = "admin@rescuesync.test"
EMAIL_AUDITOR = "auditor@rescuesync.test"
EMAIL_COORDINADOR = "coordinador@rescuesync.test"
EMAIL_OPERADOR = "operador@chascomus.test"
EMAIL_REPRESENTANTE = "representante@cruzsolidaria.test"

EMAIL_POR_ROL: dict[str, str] = {
    "administrador": EMAIL_ADMINISTRADOR,
    "auditor": EMAIL_AUDITOR,
    "coordinador_regional": EMAIL_COORDINADOR,
    "operador_municipal": EMAIL_OPERADOR,
    "representante_ong": EMAIL_REPRESENTANTE,
}


# Lo que manda un navegador al navegar: HTML antes que cualquier otra cosa. Con esta cabecera
# la aplicacion responde con pantallas; sin ella, con JSON (ver app/core/interfaz/vistas.py).
CABECERA_NAVEGADOR = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}

_PATRON_META_CSRF = re.compile(r'<meta name="csrf-token" content="([^"]+)"')


def token_csrf_de(cliente) -> str:
    """Token CSRF de la sesion en curso, leido de la pagina como lo haria el navegador.

    Cualquier pantalla sirve: todas extienden `base.html`, que lo publica en un <meta>. Se pide
    la de ingreso siguiendo los redirects, asi funciona con y sin sesion abierta (con sesion,
    termina en el panel o en el cambio de contrasena pendiente).
    """
    respuesta = cliente.get("/sesion/ingreso", headers=CABECERA_NAVEGADOR, follow_redirects=True)
    coincidencia = _PATRON_META_CSRF.search(respuesta.get_data(as_text=True))
    assert coincidencia, "La pagina no publica el token CSRF en <meta name='csrf-token'>"
    return coincidencia.group(1)


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
def base_de_datos(app) -> Iterator[None]:
    """Esquema creado y datos semilla cargados, como los deja `flask seed`.

    El contexto de aplicacion se cierra antes del `yield` a proposito (ver el docstring del
    modulo). Todo test que necesite tocar el ORM directamente abre el suyo.
    """
    from app.core.semillas import SEEDERS, importar_seeders
    from app.extensiones import db

    with app.app_context():
        db.create_all()
        importar_seeders()
        for seeder in SEEDERS:
            seeder.funcion()
        db.session.commit()

    yield

    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def cliente(app):
    """Cliente sin base de datos, para los tests que solo ejercitan `core`."""
    return app.test_client()


@pytest.fixture
def cliente_sembrado(app, base_de_datos: None):
    """Cliente sobre una base ya sembrada."""
    return app.test_client()


@pytest.fixture
def cabecera_csrf(cliente_sembrado) -> Callable[[], dict[str, str]]:
    """Devuelve una cabecera con un token CSRF fresco.

    Se pide uno nuevo en cada llamada porque el token esta atado a la sesion, y la sesion se
    rota al iniciar y al cerrar sesion: reutilizar el token viejo despues de un ingreso falla,
    que es exactamente lo que tiene que pasar.
    """

    def _cabecera() -> dict[str, str]:
        return {"X-CSRFToken": token_csrf_de(cliente_sembrado)}

    return _cabecera


@pytest.fixture
def ingresar(cliente_sembrado, cabecera_csrf) -> Callable[..., Any]:
    """Inicia sesion con una de las cuentas sembradas."""

    def _ingresar(email: str, contrasena: str = CONTRASENA_SEMILLA):
        return cliente_sembrado.post(
            "/sesion/ingreso",
            json={"email": email, "contrasena": contrasena},
            headers=cabecera_csrf(),
        )

    return _ingresar


# --- La interfaz, como la usa un navegador --------------------------------------


@pytest.fixture
def enviar_formulario(cliente_sembrado) -> Callable[..., Any]:
    """Envia un formulario HTML como el navegador: form-encoded, con su csrf_token y
    pidiendo HTML. No sigue los redirects, para poder verificar a donde apuntan."""

    def _enviar(url: str, datos: dict[str, Any] | None = None):
        cuerpo = {"csrf_token": token_csrf_de(cliente_sembrado), **(datos or {})}
        return cliente_sembrado.post(url, data=cuerpo, headers=CABECERA_NAVEGADOR)

    return _enviar


@pytest.fixture
def ingresar_por_formulario(enviar_formulario) -> Callable[..., Any]:
    """Inicia sesion desde la pantalla de ingreso."""

    def _ingresar(email: str, contrasena: str = CONTRASENA_SEMILLA, siguiente: str | None = None):
        datos = {"email": email, "contrasena": contrasena}
        if siguiente is not None:
            datos["next"] = siguiente
        return enviar_formulario("/sesion/ingreso", datos)

    return _ingresar


@pytest.fixture
def navegar(cliente_sembrado) -> Callable[..., Any]:
    """GET pidiendo HTML, como un navegador."""

    def _navegar(url: str, **kwargs: Any):
        return cliente_sembrado.get(url, headers=CABECERA_NAVEGADOR, **kwargs)

    return _navegar
