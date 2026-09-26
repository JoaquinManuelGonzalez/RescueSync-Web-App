"""Organizaciones por HTTP: alta con cobertura, busqueda, miembros y "Mi organizacion".

Incluye la verificacion de la hipotesis de beneficio de la EPIC-19: dos cuentas de la misma ONG
ven y editan la misma oferta.
"""

from __future__ import annotations

import re

import pytest

from .conftest import (
    CABECERA_NAVEGADOR,
    EMAIL_ADMINISTRADOR,
    EMAIL_AUDITOR,
    EMAIL_REPRESENTANTE,
    token_csrf_de,
)
from .test_ofertas_rutas import datos_ofertas_web  # noqa: F401 - fixture reutilizada

EMAIL_REPRESENTANTE_2 = "representante2@cruzsolidaria.test"


def _texto(respuesta) -> str:
    return respuesta.get_data(as_text=True)


def _cerrar_sesion(cliente) -> None:
    cliente.post("/sesion/cierre", headers={"X-CSRFToken": token_csrf_de(cliente)})


def _id_de_organizacion(cliente, nombre: str) -> int:
    organizaciones = cliente.get(f"/organizaciones?texto={nombre}").get_json()["organizaciones"]
    return next(una["id"] for una in organizaciones if una["nombre"] == nombre)


# --- Administrador, por JSON ---------------------------------------------------------


def test_alta_de_una_ong_con_su_cobertura(cliente_sembrado, cabecera_csrf, ingresar) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    respuesta = cliente_sembrado.post(
        "/organizaciones",
        json={
            "nombre": "Brigada Andina",
            "tipo": "ong",
            "zonas": [
                {"provincia": "Mendoza", "localidad": "Malargüe"},
                {"provincia": "San Juan"},
            ],
        },
        headers=cabecera_csrf(),
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.get_json()
    assert cuerpo["zonas_de_cobertura"] == [
        {"provincia": "Mendoza", "localidad": "Malargüe"},
        {"provincia": "San Juan", "localidad": None},
    ]
    assert cuerpo["estado_verificacion"] == "verificada"


def test_una_ong_sin_zonas_vuelve_con_el_error_en_zonas(
    cliente_sembrado, cabecera_csrf, ingresar
) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    respuesta = cliente_sembrado.post(
        "/organizaciones", json={"nombre": "ONG sin zonas", "tipo": "ong"}, headers=cabecera_csrf()
    )

    assert respuesta.status_code == 400
    assert "zonas" in respuesta.get_json()["error"]["detalle"]


def test_zonas_con_formato_invalido_se_rechazan(cliente_sembrado, cabecera_csrf, ingresar) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    respuesta = cliente_sembrado.post(
        "/organizaciones",
        json={"nombre": "ONG rara", "tipo": "ong", "zonas": "Salta"},
        headers=cabecera_csrf(),
    )

    assert respuesta.status_code == 400
    assert "zonas" in respuesta.get_json()["error"]["detalle"]


def test_el_detalle_trae_las_cuentas_vinculadas(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_ADMINISTRADOR)
    ong = _id_de_organizacion(cliente_sembrado, "Cruz Solidaria")

    cuerpo = cliente_sembrado.get(f"/organizaciones/{ong}").get_json()

    assert {miembro["email"] for miembro in cuerpo["miembros"]} == {
        EMAIL_REPRESENTANTE,
        EMAIL_REPRESENTANTE_2,
    }


def test_el_listado_filtra_por_provincia_y_busca_por_localidad(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    por_provincia = cliente_sembrado.get(
        "/organizaciones?provincia=Ciudad Autónoma de Buenos Aires"
    ).get_json()["organizaciones"]
    por_localidad = cliente_sembrado.get("/organizaciones?texto=Ensenada").get_json()[
        "organizaciones"
    ]

    assert [una["nombre"] for una in por_provincia] == ["Cruz Solidaria"]
    assert [una["nombre"] for una in por_localidad] == ["Bomberos Voluntarios de La Plata"]


# --- Mi organizacion ---------------------------------------------------------------


def test_el_representante_ve_su_organizacion_y_sus_companeros(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_REPRESENTANTE)

    cuerpo = cliente_sembrado.get("/organizaciones/mia").get_json()

    assert cuerpo["nombre"] == "Cruz Solidaria"
    assert {miembro["email"] for miembro in cuerpo["miembros"]} == {
        EMAIL_REPRESENTANTE,
        EMAIL_REPRESENTANTE_2,
    }


def test_el_representante_actualiza_contacto_y_cobertura_pero_no_el_nombre(
    cliente_sembrado, cabecera_csrf, ingresar
) -> None:
    ingresar(EMAIL_REPRESENTANTE)

    respuesta = cliente_sembrado.post(
        "/organizaciones/mia/edicion",
        json={
            "nombre": "Nombre inventado",
            "tipo": "municipio",
            "contacto_telefono": "0800-555-1234",
            "zonas": [{"provincia": "Buenos Aires", "localidad": "Magdalena"}],
        },
        headers=cabecera_csrf(),
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_json()
    assert cuerpo["nombre"] == "Cruz Solidaria"
    assert cuerpo["tipo"] == "ong"
    assert cuerpo["contacto_telefono"] == "0800-555-1234"
    assert cuerpo["zonas_de_cobertura"] == [{"provincia": "Buenos Aires", "localidad": "Magdalena"}]


def test_editar_sin_mandar_zonas_por_json_conserva_la_cobertura(
    cliente_sembrado, cabecera_csrf, ingresar
) -> None:
    ingresar(EMAIL_REPRESENTANTE)
    antes = cliente_sembrado.get("/organizaciones/mia").get_json()["zonas_de_cobertura"]

    respuesta = cliente_sembrado.post(
        "/organizaciones/mia/edicion",
        json={"contacto_email": "contacto@cruzsolidaria.test"},
        headers=cabecera_csrf(),
    )

    assert respuesta.status_code == 200
    assert respuesta.get_json()["zonas_de_cobertura"] == antes


def test_el_representante_no_ve_otras_organizaciones(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_REPRESENTANTE)

    assert cliente_sembrado.get("/organizaciones").status_code == 403
    assert cliente_sembrado.get("/organizaciones/1").status_code == 403


@pytest.mark.parametrize("email", [EMAIL_ADMINISTRADOR, EMAIL_AUDITOR])
def test_los_perfiles_sin_organizacion_no_tienen_mi_organizacion(
    cliente_sembrado, ingresar, email
) -> None:
    ingresar(email)

    assert cliente_sembrado.get("/organizaciones/mia").status_code == 403


# --- Interfaz -----------------------------------------------------------------------


def test_el_menu_del_representante_ofrece_mi_organizacion(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_REPRESENTANTE)

    assert 'href="/organizaciones/mia"' in _texto(navegar("/inicio"))


def test_la_pantalla_de_mi_organizacion_lista_miembros_y_cobertura(
    ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_REPRESENTANTE)

    cuerpo = _texto(navegar("/organizaciones/mia"))

    assert "Cruz Solidaria" in cuerpo
    assert EMAIL_REPRESENTANTE_2 in cuerpo
    assert "Ciudad Autónoma de Buenos Aires" in cuerpo


def test_el_formulario_de_alta_trae_las_filas_de_cobertura(
    ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)

    cuerpo = _texto(navegar("/organizaciones/nueva"))

    assert 'name="zonas-0-provincia"' in cuerpo
    assert 'name="zonas-__indice__-provincia"' in cuerpo
    assert "zonas_de_cobertura.js" in cuerpo


def test_alta_por_formulario_con_zonas(ingresar_por_formulario, enviar_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)

    alta = enviar_formulario(
        "/organizaciones",
        {
            "nombre": "Rescate Serrano",
            "tipo": "ong",
            "zonas-0-provincia": "Córdoba",
            "zonas-0-localidad": "Villa Carlos Paz",
            "zonas-4-provincia": "San Luis",
            "zonas-4-localidad": "",
        },
    )

    assert alta.status_code == 302
    detalle = _texto(navegar(alta.headers["Location"]))
    assert "Villa Carlos Paz" in detalle
    assert "San Luis" in detalle


def test_la_ong_sin_zonas_por_formulario_vuelve_con_el_aviso(
    ingresar_por_formulario, enviar_formulario
) -> None:
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)

    respuesta = enviar_formulario(
        "/organizaciones",
        {"nombre": "ONG sin zonas", "tipo": "ong", "zonas-0-provincia": ""},
    )

    assert respuesta.status_code == 400
    assert "al menos una zona de cobertura" in _texto(respuesta)


def test_el_detalle_ofrece_vincular_una_cuenta_con_la_organizacion_precargada(
    ingresar_por_formulario, cliente_sembrado, navegar
) -> None:
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)
    ong = _id_de_organizacion(cliente_sembrado, "Manos Unidas")

    detalle = _texto(navegar(f"/organizaciones/{ong}"))
    assert f'href="/usuarios/nuevo?organizacion_id={ong}"' in detalle

    alta = _texto(navegar(f"/usuarios/nuevo?organizacion_id={ong}"))
    assert re.search(r'<option selected value="representante_ong">', alta)
    assert re.search(rf'<option value="{ong}"[^>]*selected', alta)


def test_cambiar_el_tipo_con_cuentas_vuelve_con_el_error_en_el_tipo(
    ingresar_por_formulario, enviar_formulario, cliente_sembrado
) -> None:
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)
    ong = _id_de_organizacion(cliente_sembrado, "Cruz Solidaria")

    respuesta = enviar_formulario(
        f"/organizaciones/{ong}/edicion",
        {"nombre": "Cruz Solidaria", "tipo": "municipio", "zonas-0-provincia": "Buenos Aires"},
    )

    assert respuesta.status_code == 409
    assert "cuenta(s) vinculada(s)" in _texto(respuesta)


# --- Hipotesis de beneficio -----------------------------------------------------------


def test_dos_cuentas_de_la_misma_ong_ven_y_editan_la_misma_oferta(
    cliente_sembrado,
    cabecera_csrf,
    ingresar,
    datos_ofertas_web,  # noqa: F811
) -> None:
    """La organizacion es el titular de la oferta, no la persona que la cargo."""
    ingresar(EMAIL_REPRESENTANTE)
    alta = cliente_sembrado.post(
        "/ofertas",
        json={
            "convocatoria_id": datos_ofertas_web["convocatoria_id"],
            "items": [
                {"lote_item_id": datos_ofertas_web["lote_item1_id"], "cantidad_ofrecida": 100}
            ],
        },
        headers=cabecera_csrf(),
    )
    assert alta.status_code == 201
    oferta_id = alta.get_json()["id"]

    _cerrar_sesion(cliente_sembrado)
    ingresar(EMAIL_REPRESENTANTE_2)

    listado = cliente_sembrado.get("/ofertas", headers={"Accept": "application/json"}).get_json()
    assert oferta_id in [oferta["id"] for oferta in listado["ofertas"]]

    edicion = cliente_sembrado.put(
        f"/ofertas/{oferta_id}",
        json={
            "items": [
                {"lote_item_id": datos_ofertas_web["lote_item1_id"], "cantidad_ofrecida": 150}
            ]
        },
        headers=cabecera_csrf(),
    )
    assert edicion.status_code == 200
    assert edicion.get_json()["version"] == 2


def test_una_cuenta_de_otra_ong_no_ve_la_oferta(
    cliente_sembrado,
    cabecera_csrf,
    ingresar,
    datos_ofertas_web,  # noqa: F811
) -> None:
    ingresar(EMAIL_REPRESENTANTE)
    alta = cliente_sembrado.post(
        "/ofertas",
        json={
            "convocatoria_id": datos_ofertas_web["convocatoria_id"],
            "items": [
                {"lote_item_id": datos_ofertas_web["lote_item1_id"], "cantidad_ofrecida": 100}
            ],
        },
        headers=cabecera_csrf(),
    )
    oferta_id = alta.get_json()["id"]

    _cerrar_sesion(cliente_sembrado)
    ingresar("representante@cruzroja.test")

    respuesta = cliente_sembrado.get(f"/ofertas/{oferta_id}", headers=CABECERA_NAVEGADOR)
    assert respuesta.status_code == 404


# --- Cobertura nacional ---------------------------------------------------------------


def test_alta_por_json_de_una_ong_nacional(cliente_sembrado, cabecera_csrf, ingresar) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    respuesta = cliente_sembrado.post(
        "/organizaciones",
        json={"nombre": "Red Solidaria Argentina", "tipo": "ong", "cobertura_nacional": True},
        headers=cabecera_csrf(),
    )

    assert respuesta.status_code == 201
    assert respuesta.get_json()["cobertura_nacional"] is True
    assert respuesta.get_json()["zonas_de_cobertura"] == []


def test_la_cobertura_nacional_tiene_que_ser_booleana(
    cliente_sembrado, cabecera_csrf, ingresar
) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    respuesta = cliente_sembrado.post(
        "/organizaciones",
        json={"nombre": "Red rara", "tipo": "ong", "cobertura_nacional": "si"},
        headers=cabecera_csrf(),
    )

    assert respuesta.status_code == 400
    assert "cobertura_nacional" in respuesta.get_json()["error"]["detalle"]


def test_alta_por_formulario_con_la_casilla_nacional(
    ingresar_por_formulario, enviar_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)

    alta = enviar_formulario(
        "/organizaciones",
        {
            "nombre": "Red Solidaria Argentina",
            "tipo": "ong",
            "cobertura_nacional": "y",
            "zonas-0-provincia": "",
        },
    )

    assert alta.status_code == 302
    assert "Todo el país" in _texto(navegar(alta.headers["Location"]))


def test_el_formulario_ofrece_la_casilla_nacional(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)

    cuerpo = _texto(navegar("/organizaciones/nueva"))

    assert 'name="cobertura_nacional"' in cuerpo
    assert "Opera en todo el país" in cuerpo


def test_el_representante_marca_que_su_ong_opera_en_todo_el_pais(
    ingresar_por_formulario, enviar_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_REPRESENTANTE)

    respuesta = enviar_formulario(
        "/organizaciones/mia/edicion",
        {"cobertura_nacional": "y", "zonas-0-provincia": ""},
    )

    assert respuesta.status_code == 302
    assert "Todo el país" in _texto(navegar("/organizaciones/mia"))
    edicion = _texto(navegar("/organizaciones/mia/edicion"))
    assert re.search(
        r'name="cobertura_nacional"[^>]*checked|checked[^>]*name="cobertura_nacional"', edicion
    )
    assert "data-zonas-detalle hidden" in edicion


# --- Varias localidades separadas por comas ---------------------------------------------


def test_alta_por_formulario_con_localidades_separadas_por_comas(
    ingresar_por_formulario, enviar_formulario, cliente_sembrado, navegar
) -> None:
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)

    alta = enviar_formulario(
        "/organizaciones",
        {
            "nombre": "Cáritas La Plata",
            "tipo": "ong",
            "zonas-0-provincia": "Buenos Aires",
            "zonas-0-localidad": "La Plata, Berisso, Los Hornos",
        },
    )
    assert alta.status_code == 302

    organizacion_id = int(alta.headers["Location"].rstrip("/").rsplit("/", 1)[1])
    cuerpo = cliente_sembrado.get(f"/organizaciones/{organizacion_id}").get_json()
    assert [zona["localidad"] for zona in cuerpo["zonas_de_cobertura"]] == [
        "Berisso",
        "La Plata",
        "Los Hornos",
    ]

    edicion = _texto(navegar(f"/organizaciones/{organizacion_id}/edicion"))
    assert 'value="Berisso, La Plata, Los Hornos"' in edicion
    assert 'name="zonas-1-provincia"' not in edicion


def test_un_campo_con_solo_comas_vuelve_con_el_aviso(
    ingresar_por_formulario, enviar_formulario
) -> None:
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)

    respuesta = enviar_formulario(
        "/organizaciones",
        {
            "nombre": "ONG con comas",
            "tipo": "ong",
            "zonas-0-provincia": "Salta",
            "zonas-0-localidad": ", ,",
        },
    )

    assert respuesta.status_code == 400
    assert "no tiene ninguna localidad" in _texto(respuesta)


# --- Navbar: una sola seccion activa -------------------------------------------------

_PATRON_SECCION_ACTIVA = re.compile(r'<a\s+href="([^"]+)"\s+class="[^"]*bg-acento/60 text-primario')


def _secciones_activas(cuerpo: str) -> set[str]:
    """Los href marcados como activos en el navbar (escritorio y menu movil)."""
    return set(_PATRON_SECCION_ACTIVA.findall(cuerpo))


@pytest.mark.parametrize(
    ("pantalla", "activa"),
    [
        ("/organizaciones/mia", "/organizaciones/mia"),
        ("/organizaciones/mia/edicion", "/organizaciones/mia"),
        ("/organizaciones/inventario", "/organizaciones/inventario"),
        ("/organizaciones/inventario/nuevo", "/organizaciones/inventario"),
    ],
)
def test_el_navbar_del_representante_marca_solo_la_pantalla_actual(
    ingresar_por_formulario, navegar, pantalla, activa
) -> None:
    ingresar_por_formulario(EMAIL_REPRESENTANTE)

    assert _secciones_activas(_texto(navegar(pantalla))) == {activa}


@pytest.mark.parametrize(
    "pantalla", ["/organizaciones", "/organizaciones/nueva", "/organizaciones/1"]
)
def test_el_navbar_del_administrador_marca_organizaciones(
    ingresar_por_formulario, navegar, pantalla
) -> None:
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)

    assert _secciones_activas(_texto(navegar(pantalla))) == {"/organizaciones"}


def test_el_panel_de_inicio_no_marca_ninguna_seccion_del_menu(
    ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_REPRESENTANTE)

    assert _secciones_activas(_texto(navegar("/inicio"))) == {"/inicio"}
