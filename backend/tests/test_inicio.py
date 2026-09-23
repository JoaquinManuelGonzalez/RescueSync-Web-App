"""Entrada a la aplicacion y panel de inicio.

Estos tests son tambien los que verifican que Flask realmente encuentra las plantillas y los
estaticos de `frontend/`.
"""

from __future__ import annotations

from .conftest import CABECERA_NAVEGADOR, EMAIL_ADMINISTRADOR


def test_la_raiz_sin_sesion_lleva_al_ingreso(cliente_sembrado) -> None:
    respuesta = cliente_sembrado.get("/", headers=CABECERA_NAVEGADOR)

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/sesion/ingreso")


def test_la_raiz_con_sesion_lleva_al_panel(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    respuesta = cliente_sembrado.get("/", headers=CABECERA_NAVEGADOR)

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/inicio")


def test_la_pantalla_de_ingreso_renderiza(cliente_sembrado) -> None:
    respuesta = cliente_sembrado.get("/sesion/ingreso", headers=CABECERA_NAVEGADOR)
    cuerpo = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "text/html" in respuesta.content_type
    assert "<!DOCTYPE html>" in cuerpo
    assert "RescueSync" in cuerpo


def test_la_pagina_enlaza_el_css_compilado_y_el_js(cliente_sembrado) -> None:
    # Confirma de paso que `static_folder` apunta a frontend/estaticos.
    cuerpo = cliente_sembrado.get("/sesion/ingreso", headers=CABECERA_NAVEGADOR).get_data(
        as_text=True
    )

    assert "/estaticos/css/app.css" in cuerpo
    assert "/estaticos/js/interfaz.js" in cuerpo


def test_el_js_de_la_interfaz_se_sirve(cliente) -> None:
    respuesta = cliente.get("/estaticos/js/interfaz.js")

    assert respuesta.status_code == 200
    respuesta.close()
