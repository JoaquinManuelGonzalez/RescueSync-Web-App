"""Inicio de sesion: respuesta uniforme, cuenta inactiva y bloqueo por intentos fallidos."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.extensiones import db
from app.modulos.usuarios_roles import servicios

from .conftest import CONTRASENA_SEMILLA, EMAIL_OPERADOR


def _mensaje(respuesta) -> str:
    return respuesta.get_json()["error"]["mensaje"]


def _codigo(respuesta) -> str:
    return respuesta.get_json()["error"]["codigo"]


def test_ingreso_con_credenciales_correctas_devuelve_la_sesion(ingresar) -> None:
    respuesta = ingresar(EMAIL_OPERADOR)

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_json()
    assert cuerpo["email"] == EMAIL_OPERADOR
    assert cuerpo["roles"] == ["operador_municipal"]
    assert "emergencias:crear" in cuerpo["permisos"]


def test_el_email_se_puede_escribir_con_mayusculas(ingresar) -> None:
    """El email es la clave natural y se normaliza: la caja no debería importar al entrar."""
    respuesta = ingresar(EMAIL_OPERADOR.upper())

    assert respuesta.status_code == 200
    assert respuesta.get_json()["email"] == EMAIL_OPERADOR


def test_contrasena_incorrecta_y_email_inexistente_dan_la_misma_respuesta(ingresar) -> None:
    """Distinguirlos permitiria enumerar que cuentas existen probando emails al azar."""
    con_contrasena_mala = ingresar(EMAIL_OPERADOR, "una-contrasena-que-no-es")
    con_email_inexistente = ingresar("no.existe@rescuesync.test", "una-contrasena-que-no-es")

    assert con_contrasena_mala.status_code == con_email_inexistente.status_code == 401
    assert _codigo(con_contrasena_mala) == _codigo(con_email_inexistente) == "NO_AUTENTICADO"
    assert _mensaje(con_contrasena_mala) == _mensaje(con_email_inexistente)


def _desactivar_operador(app) -> None:
    with app.app_context():
        usuario = servicios.obtener_por_email(EMAIL_OPERADOR)
        servicios.cambiar_estado(usuario.id, activo=False)


def test_cuenta_desactivada_con_la_contrasena_correcta_avisa_que_esta_desactivada(
    app, ingresar
) -> None:
    """Quien sabe la contraseña es la dueña de la cuenta: se le explica por qué no entra."""
    _desactivar_operador(app)

    respuesta = ingresar(EMAIL_OPERADOR)

    assert respuesta.status_code == 403
    assert _mensaje(respuesta) == servicios.MENSAJE_INACTIVA


def test_cuenta_desactivada_con_otra_contrasena_da_el_mensaje_generico(app, ingresar) -> None:
    """A quien no sabe la contraseña no se le revela que la cuenta existe y está de baja."""
    _desactivar_operador(app)

    respuesta = ingresar(EMAIL_OPERADOR, contrasena="no-es-esta-clave")

    assert respuesta.status_code == 401
    assert _mensaje(respuesta) == servicios.MENSAJE_CREDENCIALES


def test_la_cuenta_se_bloquea_al_agotar_los_intentos(app, ingresar) -> None:
    """Al quinto fallo la cuenta queda bloqueada, y la contraseña correcta ya no alcanza."""
    limite = app.config["LOGIN_MAX_INTENTOS"]

    for _ in range(limite):
        assert ingresar(EMAIL_OPERADOR, "una-contrasena-que-no-es").status_code == 401

    respuesta = ingresar(EMAIL_OPERADOR)

    assert respuesta.status_code == 403
    assert _codigo(respuesta) == "PERMISO_DENEGADO"


def test_el_contador_de_intentos_se_reinicia_tras_un_ingreso_exitoso(app, ingresar) -> None:
    """Cuatro fallos y un acierto no dejan la cuenta a un intento de bloquearse."""
    for _ in range(app.config["LOGIN_MAX_INTENTOS"] - 1):
        ingresar(EMAIL_OPERADOR, "una-contrasena-que-no-es")

    assert ingresar(EMAIL_OPERADOR).status_code == 200

    with app.app_context():
        usuario = servicios.obtener_por_email(EMAIL_OPERADOR)
        assert usuario.intentos_fallidos == 0
        assert usuario.bloqueado_hasta is None


def test_el_bloqueo_se_levanta_solo_al_vencer(app, ingresar) -> None:
    with app.app_context():
        usuario = servicios.obtener_por_email(EMAIL_OPERADOR)
        usuario.bloqueado_hasta = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()

    assert ingresar(EMAIL_OPERADOR).status_code == 200


def test_el_ingreso_exitoso_registra_el_ultimo_acceso(app, ingresar) -> None:
    with app.app_context():
        assert servicios.obtener_por_email(EMAIL_OPERADOR).ultimo_acceso_en is None

    ingresar(EMAIL_OPERADOR)

    with app.app_context():
        assert servicios.obtener_por_email(EMAIL_OPERADOR).ultimo_acceso_en is not None


def test_el_ingreso_sin_token_csrf_se_rechaza(cliente_sembrado) -> None:
    """La protección CSRF es de toda la aplicación, incluido el propio formulario de ingreso."""
    respuesta = cliente_sembrado.post(
        "/sesion/ingreso",
        json={"email": EMAIL_OPERADOR, "contrasena": CONTRASENA_SEMILLA},
    )

    assert respuesta.status_code == 400


def test_el_formulario_de_ingreso_incompleto_detalla_los_campos(
    cliente_sembrado, cabecera_csrf
) -> None:
    respuesta = cliente_sembrado.post(
        "/sesion/ingreso", json={"email": ""}, headers=cabecera_csrf()
    )

    assert respuesta.status_code == 400
    detalle = respuesta.get_json()["error"]["detalle"]
    assert "email" in detalle
    assert "contrasena" in detalle


def test_el_bloqueo_dura_un_minuto_y_se_activa_a_los_cinco_intentos(app) -> None:
    """Valores de demostracion: se bloquea rapido y se desbloquea solo en un minuto."""
    assert app.config["LOGIN_MAX_INTENTOS"] == 5
    assert app.config["LOGIN_BLOQUEO_MINUTOS"] == 1
