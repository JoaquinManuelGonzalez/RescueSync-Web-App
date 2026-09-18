"""Pagina de inicio provisional.

Estos tests son los que verifican que Flask realmente encuentra las plantillas de `frontend/`
"""

from __future__ import annotations


def test_la_pagina_de_inicio_renderiza(cliente) -> None:
    respuesta = cliente.get("/")

    assert respuesta.status_code == 200
    assert "text/html" in respuesta.content_type


def test_la_pagina_muestra_el_nombre_de_la_aplicacion(cliente) -> None:
    cuerpo = cliente.get("/").get_data(as_text=True)

    assert "<!DOCTYPE html>" in cuerpo
    assert "RescueSync" in cuerpo


def test_la_pagina_enlaza_el_css_compilado(cliente) -> None:
    # Confirma de paso que `static_folder` apunta a frontend/estaticos.
    cuerpo = cliente.get("/").get_data(as_text=True)

    assert "/estaticos/css/app.css" in cuerpo
