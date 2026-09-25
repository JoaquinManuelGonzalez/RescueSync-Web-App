"""Baja de una organizacion: sus cuentas pierden el acceso mientras dure, sin tocarlas.

Tambien cubre el hueco que tenian las cuentas desactivadas con una sesion ya abierta.
"""

from __future__ import annotations

import pytest

from app.core.errores import SolicitudInvalida
from app.modulos.organizaciones import servicios as organizaciones
from app.modulos.usuarios_roles import servicios as usuarios

from .conftest import CONTRASENA_SEMILLA, EMAIL_OPERADOR, EMAIL_REPRESENTANTE


def _cambiar_estado_de(app, nombre: str, *, activo: bool) -> None:
    with app.app_context():
        organizacion = next(una for una in organizaciones.listar() if una.nombre == nombre)
        organizaciones.cambiar_estado(organizacion.id, activo=activo)


def test_la_cuenta_de_una_organizacion_inactiva_no_puede_ingresar(app, ingresar) -> None:
    _cambiar_estado_de(app, "Cruz Solidaria", activo=False)

    respuesta = ingresar(EMAIL_REPRESENTANTE)

    assert respuesta.status_code == 403
    assert respuesta.get_json()["error"]["mensaje"] == usuarios.MENSAJE_ORGANIZACION_INACTIVA


def test_con_la_contrasena_equivocada_no_se_revela_la_baja(app, ingresar) -> None:
    _cambiar_estado_de(app, "Cruz Solidaria", activo=False)

    respuesta = ingresar(EMAIL_REPRESENTANTE, "una-contrasena-que-no-es")

    assert respuesta.status_code == 401
    assert respuesta.get_json()["error"]["mensaje"] == usuarios.MENSAJE_CREDENCIALES


def test_la_sesion_abierta_se_corta_al_desactivar_la_organizacion(
    app, cliente_sembrado, ingresar
) -> None:
    assert ingresar(EMAIL_REPRESENTANTE).status_code == 200
    assert cliente_sembrado.get("/sesion/actual").status_code == 200

    _cambiar_estado_de(app, "Cruz Solidaria", activo=False)

    assert cliente_sembrado.get("/sesion/actual").status_code == 401


def test_la_sesion_abierta_se_corta_al_desactivar_la_cuenta(
    app, cliente_sembrado, ingresar
) -> None:
    assert ingresar(EMAIL_OPERADOR).status_code == 200

    with app.app_context():
        usuarios.cambiar_estado(usuarios.obtener_por_email(EMAIL_OPERADOR).id, activo=False)

    assert cliente_sembrado.get("/sesion/actual").status_code == 401


def test_al_reactivar_la_organizacion_sus_cuentas_vuelven_a_entrar(app, ingresar) -> None:
    _cambiar_estado_de(app, "Cruz Solidaria", activo=False)
    _cambiar_estado_de(app, "Cruz Solidaria", activo=True)

    assert ingresar(EMAIL_REPRESENTANTE, CONTRASENA_SEMILLA).status_code == 200


def test_la_baja_no_afecta_a_las_cuentas_de_otras_organizaciones(app, ingresar) -> None:
    _cambiar_estado_de(app, "Cruz Solidaria", activo=False)

    assert ingresar("representante@cruzroja.test").status_code == 200


def test_no_se_vincula_una_cuenta_nueva_a_una_organizacion_inactiva(
    app, base_de_datos: None
) -> None:
    _cambiar_estado_de(app, "Manos Unidas", activo=False)

    with app.app_context():
        manos_unidas = next(una for una in organizaciones.listar() if una.nombre == "Manos Unidas")
        with pytest.raises(SolicitudInvalida) as error:
            usuarios.crear_usuario(
                email="nueva@manosunidas.test",
                nombre_completo="Cuenta nueva",
                contrasena="Clave-Nueva-2026",
                nombre_rol="representante_ong",
                organizacion_id=manos_unidas.id,
            )

    assert error.value.detalle["organizacion_id"] == [
        usuarios.MENSAJE_ORGANIZACION_VINCULADA_INACTIVA
    ]


def test_se_puede_editar_una_cuenta_que_ya_pertenecia_a_la_organizacion_inactiva(
    app, base_de_datos: None
) -> None:
    _cambiar_estado_de(app, "Manos Unidas", activo=False)

    with app.app_context():
        cuenta = usuarios.obtener_por_email("representante@manosunidas.test")
        editada = usuarios.editar_usuario(
            cuenta.id,
            nombre_completo="Representante renombrado",
            nombre_rol="representante_ong",
            organizacion_id=cuenta.organizacion_id,
        )

        assert editada.nombre_completo == "Representante renombrado"
