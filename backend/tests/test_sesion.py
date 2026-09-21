"""Ciclo de vida de la sesion: expiracion por inactividad, rotacion y cookie.

La expiracion por inactividad a los 30 minutos es el requisito no funcional de la epica, y se
verifica del lado del servidor. Los tests la ejercitan envejeciendo la marca `ultima_actividad`
que guarda la sesion, en vez de esperar media hora.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.sesion import CLAVE_ULTIMA_ACTIVIDAD, MENSAJE_SESION_EXPIRADA

from .conftest import EMAIL_OPERADOR


def _envejecer_sesion(cliente, minutos: int) -> None:
    """Retrasa la marca de actividad como si hubieran pasado `minutos` sin tocar nada."""
    with cliente.session_transaction() as sesion:
        sesion[CLAVE_ULTIMA_ACTIVIDAD] = (
            datetime.now(UTC) - timedelta(minutes=minutos)
        ).isoformat()


def test_la_sesion_dura_los_minutos_configurados(app) -> None:
    assert app.config["SESION_MINUTOS_INACTIVIDAD"] == 30
    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(minutes=30)


def test_la_sesion_expira_por_inactividad(app, cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_OPERADOR)
    assert cliente_sembrado.get("/sesion/actual").status_code == 200

    _envejecer_sesion(cliente_sembrado, app.config["SESION_MINUTOS_INACTIVIDAD"] + 1)
    respuesta = cliente_sembrado.get("/sesion/actual")

    assert respuesta.status_code == 401
    assert respuesta.get_json()["error"]["codigo"] == "NO_AUTENTICADO"
    assert respuesta.get_json()["error"]["mensaje"] == MENSAJE_SESION_EXPIRADA


def test_la_actividad_renueva_la_sesion(app, cliente_sembrado, ingresar) -> None:
    """Es una expiración por inactividad, no un plazo absoluto desde el ingreso."""
    ingresar(EMAIL_OPERADOR)

    for _ in range(3):
        _envejecer_sesion(cliente_sembrado, app.config["SESION_MINUTOS_INACTIVIDAD"] - 1)
        assert cliente_sembrado.get("/sesion/actual").status_code == 200


def test_una_marca_de_actividad_corrupta_invalida_la_sesion(cliente_sembrado, ingresar) -> None:
    """Ante una sesión que no se puede interpretar, se cierra: no se asume que es válida."""
    ingresar(EMAIL_OPERADOR)

    with cliente_sembrado.session_transaction() as sesion:
        sesion[CLAVE_ULTIMA_ACTIVIDAD] = "no-es-una-fecha"

    assert cliente_sembrado.get("/sesion/actual").status_code == 401


def test_al_ingresar_se_descarta_el_contenido_previo_de_la_sesion(
    cliente_sembrado, ingresar
) -> None:
    """Rotación de sesión: lo que hubiera dejado un tercero en la sesión anónima desaparece."""
    with cliente_sembrado.session_transaction() as sesion:
        sesion["rastro_anonimo"] = "algo que dejo alguien mas"

    ingresar(EMAIL_OPERADOR)

    with cliente_sembrado.session_transaction() as sesion:
        assert "rastro_anonimo" not in sesion
        assert "_user_id" in sesion


def test_al_cerrar_sesion_la_cookie_queda_sin_usuario(
    cliente_sembrado, cabecera_csrf, ingresar
) -> None:
    ingresar(EMAIL_OPERADOR)
    assert cliente_sembrado.post("/sesion/cierre", headers=cabecera_csrf()).status_code == 200

    with cliente_sembrado.session_transaction() as sesion:
        assert "_user_id" not in sesion

    assert cliente_sembrado.get("/sesion/actual").status_code == 401


def test_la_cookie_de_sesion_es_httponly_y_samesite(cliente_sembrado, ingresar) -> None:
    """HttpOnly la esconde de JavaScript; SameSite=Lax corta el envío desde otro sitio."""
    respuesta = ingresar(EMAIL_OPERADOR)

    cookies = respuesta.headers.getlist("Set-Cookie")
    cookie_de_sesion = next(una for una in cookies if una.startswith("session="))

    assert "HttpOnly" in cookie_de_sesion
    assert "SameSite=Lax" in cookie_de_sesion


def test_en_local_la_cookie_no_exige_https(app) -> None:
    """Marcarla Secure en local la volvería invisible y nadie podría iniciar sesión."""
    assert app.config["APP_ENV"] == "local"
    assert app.config["SESSION_COOKIE_SECURE"] is False


def test_fuera_de_local_la_cookie_exige_https(monkeypatch, entorno_completo: None) -> None:
    from app import create_app

    monkeypatch.setenv("APP_ENV", "evaluacion")
    aplicacion = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})

    assert aplicacion.config["SESSION_COOKIE_SECURE"] is True


def test_el_recordarme_esta_deshabilitado(app) -> None:
    """La cookie "recordarme" sobrevive al cierre del navegador y volvería decorativa la
    expiración por inactividad."""
    assert app.config["REMEMBER_COOKIE_DURATION"] == timedelta(0)
