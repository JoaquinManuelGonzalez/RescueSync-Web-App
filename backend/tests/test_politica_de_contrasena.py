"""Politica de contrasena: 8 caracteres, una mayuscula, un numero y un caracter especial.

La regla vive en `app/core/seguridad.py` y la exigen tres caminos: el formulario, el servicio
(para el seeder y la CLI, que no pasan por WTForms) y, como ayuda visual, la interfaz.
"""

from __future__ import annotations

import pytest

from app.core.seguridad import (
    REQUISITO_ESPECIAL,
    REQUISITO_LONGITUD,
    REQUISITO_MAYUSCULA,
    REQUISITO_NUMERO,
    generar_contrasena,
    mensaje_de_politica,
    requisitos_incumplidos,
)

from .conftest import EMAIL_ADMINISTRADOR, EMAIL_OPERADOR


def test_la_longitud_minima_por_defecto_es_8(app) -> None:
    assert app.config["CONTRASENA_LONGITUD_MINIMA"] == 8


@pytest.mark.parametrize(
    ("contrasena", "incumplidos"),
    [
        ("Clave.2026", []),
        ("Ab1.cdef", []),  # justo 8
        ("Ab1.cde", [REQUISITO_LONGITUD]),
        ("clave.2026", [REQUISITO_MAYUSCULA]),
        ("Clave.clave", [REQUISITO_NUMERO]),
        ("Clave2026", [REQUISITO_ESPECIAL]),
        ("Clave 2026", [REQUISITO_ESPECIAL]),  # un espacio no cuenta como especial
        ("Ñandú#2026", []),  # las mayusculas acentuadas cuentan
        ("", [REQUISITO_LONGITUD, REQUISITO_MAYUSCULA, REQUISITO_NUMERO, REQUISITO_ESPECIAL]),
    ],
)
def test_requisitos_incumplidos(contrasena: str, incumplidos: list[str]) -> None:
    assert requisitos_incumplidos(contrasena, 8) == incumplidos


def test_el_mensaje_dice_exactamente_que_falta() -> None:
    mensaje = mensaje_de_politica([REQUISITO_MAYUSCULA, REQUISITO_NUMERO], 8)

    assert mensaje == "La contraseña tiene que tener una letra mayúscula y un número."


def test_la_contrasena_generada_por_la_cli_cumple_la_politica() -> None:
    for _ in range(50):
        assert requisitos_incumplidos(generar_contrasena(), 8) == []


def test_el_alta_json_rechaza_una_contrasena_sin_especial(
    cliente_sembrado, cabecera_csrf, ingresar
) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    respuesta = cliente_sembrado.post(
        "/usuarios",
        json={
            "email": "auditor.nuevo@rescuesync.test",
            "nombre_completo": "Auditor nuevo",
            "contrasena": "ClaveSinEspecial2026",
            "rol": "auditor",
        },
        headers=cabecera_csrf(),
    )

    assert respuesta.status_code == 400
    assert respuesta.get_json()["error"]["detalle"]["contrasena"] == [
        "La contraseña tiene que tener un carácter especial (por ejemplo . - _ ! ? @ #)."
    ]


def test_el_servicio_exige_la_politica_aunque_no_haya_formulario(app, base_de_datos) -> None:
    """El seeder y la CLI crean cuentas sin WTForms: el servicio tiene que cortarlas igual."""
    from app.core.errores import SolicitudInvalida
    from app.modulos.usuarios_roles import servicios

    with app.test_request_context(), pytest.raises(SolicitudInvalida) as error:
        servicios.crear_usuario(
            email="sin.mayuscula@rescuesync.test",
            nombre_completo="Sin mayúscula",
            contrasena="clave.2026",
            nombre_rol="auditor",
        )

    assert "una letra mayúscula" in error.value.detalle["contrasena"][0]


def test_el_cambio_propio_marca_el_error_en_la_contrasena_nueva(
    ingresar_por_formulario, enviar_formulario
) -> None:
    ingresar_por_formulario(EMAIL_OPERADOR)

    respuesta = enviar_formulario(
        "/sesion/contrasena",
        {
            "contrasena_actual": "RescueSync.2026",
            "contrasena_nueva": "solominusculas",
            "contrasena_nueva_repetida": "solominusculas",
        },
    )

    assert respuesta.status_code == 400
    cuerpo = respuesta.get_data(as_text=True)
    assert "una letra mayúscula, un número y un carácter especial" in cuerpo


def test_las_contrasenas_nuevas_muestran_sus_requisitos(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)

    cuerpo = navegar("/usuarios/nuevo").get_data(as_text=True)

    assert 'data-requisitos-de="contrasena"' in cuerpo
    assert 'data-longitud-minima="8"' in cuerpo
    for requisito in ("longitud", "mayuscula", "numero", "especial"):
        assert f'data-requisito="{requisito}"' in cuerpo


def test_el_ingreso_no_exige_la_politica(ingresar_por_formulario) -> None:
    """Una clave vieja que no cumple la politica tiene que poder entrar a cambiarse: el
    formulario de ingreso solo exige que el campo no este vacio."""
    respuesta = ingresar_por_formulario(EMAIL_OPERADOR, contrasena="corta")

    assert respuesta.status_code == 401
    assert "tiene que tener" not in respuesta.get_data(as_text=True)
