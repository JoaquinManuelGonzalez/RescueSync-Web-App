"""Control de accesos: los decoradores y la matriz de permisos.

El test central de este archivo es
`test_una_pantalla_nueva_solo_declara_su_permiso`: es la verificacion literal de la hipotesis
de beneficio de la epica ("lo confirmaremos cuando agregar una pantalla nueva no requiera
codigo de autorizacion propio, solo declarar el permiso").
"""

from __future__ import annotations

import pytest
from flask import jsonify

from app.core.acceso.autorizacion import requiere_autenticacion, requiere_permiso, requiere_rol
from app.core.acceso.permisos import EMERGENCIAS_CREAR, PERMISOS_POR_ROL, NombreRol

from .conftest import (
    EMAIL_ADMINISTRADOR,
    EMAIL_AUDITOR,
    EMAIL_COORDINADOR,
    EMAIL_OPERADOR,
    EMAIL_POR_ROL,
    EMAIL_REPRESENTANTE,
)

# Acciones que modifican estado. Todo lo demas es lectura.
ACCIONES_DE_LECTURA = frozenset({"listar", "ver"})


@pytest.fixture
def rutas_de_prueba(app):
    """Registra pantallas de juguete, protegidas solo con un decorador.

    Se registran antes de la primera solicitud porque Flask cierra el registro de rutas en
    cuanto atiende una.
    """

    @app.get("/pantalla-de-emergencias")
    @requiere_permiso(EMERGENCIAS_CREAR)
    def _pantalla_de_emergencias():
        return jsonify({"ok": True})

    @app.get("/pantalla-de-cualquiera")
    @requiere_autenticacion
    def _pantalla_de_cualquiera():
        return jsonify({"ok": True})

    @app.get("/pantalla-de-auditoria")
    @requiere_rol(NombreRol.AUDITOR)
    def _pantalla_de_auditoria():
        return jsonify({"ok": True})

    return app


def _codigo(respuesta) -> str:
    return respuesta.get_json()["error"]["codigo"]


# --- La hipotesis de beneficio de la epica ------------------------------------


def test_una_pantalla_nueva_solo_declara_su_permiso(
    rutas_de_prueba, cliente_sembrado, ingresar
) -> None:
    """La pantalla no tiene una sola línea de lógica de autorización propia.

    Solo declara `@requiere_permiso(EMERGENCIAS_CREAR)`. Con eso, el único perfil que la abre
    es el que tiene ese permiso en la matriz, y los otros cuatro reciben 403.
    """
    ingresar(EMAIL_OPERADOR)
    assert cliente_sembrado.get("/pantalla-de-emergencias").status_code == 200

    for email in (EMAIL_COORDINADOR, EMAIL_REPRESENTANTE, EMAIL_AUDITOR, EMAIL_ADMINISTRADOR):
        ingresar(email)
        respuesta = cliente_sembrado.get("/pantalla-de-emergencias")
        assert respuesta.status_code == 403, email
        assert _codigo(respuesta) == "PERMISO_DENEGADO"


# --- Respuesta ante acceso no autorizado --------------------------------------


def test_sin_sesion_la_respuesta_es_401_con_el_envelope_del_contrato(
    rutas_de_prueba, cliente_sembrado
) -> None:
    respuesta = cliente_sembrado.get("/pantalla-de-emergencias")

    assert respuesta.status_code == 401
    error = respuesta.get_json()["error"]
    assert error["codigo"] == "NO_AUTENTICADO"
    assert error["mensaje"]
    assert error["timestamp"]
    assert error["id_correlacion"]


def test_el_id_de_correlacion_del_error_es_el_de_la_solicitud(
    rutas_de_prueba, cliente_sembrado
) -> None:
    """Permite atar el 401 que vio el usuario con la línea de log que lo registró."""
    respuesta = cliente_sembrado.get(
        "/pantalla-de-emergencias", headers={"X-Correlation-Id": "correlacion-de-prueba"}
    )

    assert respuesta.get_json()["error"]["id_correlacion"] == "correlacion-de-prueba"
    assert respuesta.headers["X-Correlation-Id"] == "correlacion-de-prueba"


def test_con_sesion_pero_sin_el_permiso_la_respuesta_es_403(
    rutas_de_prueba, cliente_sembrado, ingresar
) -> None:
    """La distinción importa: el 401 pide iniciar sesión, el 403 dice que no insista."""
    ingresar(EMAIL_AUDITOR)

    assert cliente_sembrado.get("/pantalla-de-emergencias").status_code == 403


# --- Los tres decoradores -----------------------------------------------------


@pytest.mark.parametrize("email", sorted(EMAIL_POR_ROL.values()))
def test_requiere_autenticacion_deja_pasar_a_cualquier_perfil(
    rutas_de_prueba, cliente_sembrado, ingresar, email: str
) -> None:
    ingresar(email)

    assert cliente_sembrado.get("/pantalla-de-cualquiera").status_code == 200


def test_requiere_autenticacion_corta_sin_sesion(rutas_de_prueba, cliente_sembrado) -> None:
    assert cliente_sembrado.get("/pantalla-de-cualquiera").status_code == 401


def test_requiere_rol_solo_deja_pasar_al_rol_indicado(
    rutas_de_prueba, cliente_sembrado, ingresar
) -> None:
    ingresar(EMAIL_AUDITOR)
    assert cliente_sembrado.get("/pantalla-de-auditoria").status_code == 200

    ingresar(EMAIL_ADMINISTRADOR)
    assert cliente_sembrado.get("/pantalla-de-auditoria").status_code == 403


# --- La matriz de minimo privilegio -------------------------------------------


def test_el_auditor_no_tiene_ninguna_accion_de_escritura() -> None:
    """El alcance de la épica le da al auditor acceso de lectura, y nada más."""
    escrituras = [
        permiso
        for permiso in PERMISOS_POR_ROL[NombreRol.AUDITOR]
        if permiso.split(":", 1)[1] not in ACCIONES_DE_LECTURA
    ]

    assert escrituras == ["indicadores:exportar"], escrituras


def test_el_administrador_no_participa_del_proceso() -> None:
    """Mínimo privilegio aplicado también al administrador: administra cuentas y nada más."""
    recursos = {permiso.split(":", 1)[0] for permiso in PERMISOS_POR_ROL[NombreRol.ADMINISTRADOR]}

    assert recursos == {"usuarios", "organizaciones"}


def test_ningun_otro_rol_administra_cuentas() -> None:
    """Sin esto, el 'no hay autorregistro' sería una formalidad."""
    for rol, permisos in PERMISOS_POR_ROL.items():
        if rol is NombreRol.ADMINISTRADOR:
            continue
        assert not [uno for uno in permisos if uno.startswith("usuarios:")], rol


def test_solo_la_ong_carga_ofertas_y_solo_el_municipio_crea_emergencias() -> None:
    """Los dos límites que vienen directo de los lanes del BPMN de la Entrega 1."""
    for rol, permisos in PERMISOS_POR_ROL.items():
        tiene_ofertas_crear = "ofertas:crear" in permisos
        tiene_emergencias_crear = "emergencias:crear" in permisos

        assert tiene_ofertas_crear == (rol is NombreRol.REPRESENTANTE_ONG), rol
        assert tiene_emergencias_crear == (rol is NombreRol.OPERADOR_MUNICIPAL), rol


# --- El enganche para la interfaz ---------------------------------------------


def test_puede_y_tiene_rol_estan_disponibles_en_las_plantillas(app) -> None:
    """Es el punto en el que la interfaz va a ocultar lo que el servidor ya prohíbe."""
    assert callable(app.jinja_env.globals["puede"])
    assert callable(app.jinja_env.globals["tiene_rol"])


def test_puede_devuelve_falso_sin_sesion(app) -> None:
    from app.core.acceso.autorizacion import puede

    with app.test_request_context("/"):
        assert puede(EMERGENCIAS_CREAR) is False


def test_puede_refleja_los_permisos_del_usuario_en_sesion(
    app, base_de_datos: None, ingresar, cliente_sembrado
) -> None:
    ingresar(EMAIL_OPERADOR)

    cuerpo = cliente_sembrado.get("/sesion/actual").get_json()

    assert EMERGENCIAS_CREAR in cuerpo["permisos"]
    assert "usuarios:crear" not in cuerpo["permisos"]


# --- Registro de la denegacion ------------------------------------------------


def test_la_denegacion_queda_registrada_sin_datos_personales(
    rutas_de_prueba, cliente_sembrado, ingresar, caplog
) -> None:
    """El log del acceso denegado lleva el permiso exigido, nunca el email."""
    ingresar(EMAIL_AUDITOR)

    with caplog.at_level("WARNING"):
        cliente_sembrado.get("/pantalla-de-emergencias")

    denegaciones = [
        uno for uno in caplog.records if getattr(uno, "evento", "") == "acceso_denegado"
    ]

    assert denegaciones, "no se registro el evento acceso_denegado"
    campos = denegaciones[-1].campos
    assert campos["exigido"] == EMERGENCIAS_CREAR
    assert campos["motivo"] == "sin_permiso"
    assert campos["endpoint"] == "/pantalla-de-emergencias"
    assert EMAIL_AUDITOR not in str(campos)
