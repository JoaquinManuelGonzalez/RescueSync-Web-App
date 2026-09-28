"""Control de accesos visto desde el navegador.

Lo que importa verificar aca es la regla de ADR-009: la interfaz **oculta**, el servidor
**prohibe**. Que un perfil no vea un acceso es presentacion; que no pueda abrirlo escribiendo la
URL a mano es la verificacion de verdad, y tiene que seguir funcionando igual con HTML.
"""

from __future__ import annotations

import pytest

from app.core.acceso.permisos import EMERGENCIAS_CREAR, PERMISOS_POR_ROL, NombreRol
from app.core.interfaz.navegacion import EntradaDeMenu, registrar_entrada

from .conftest import EMAIL_OPERADOR, EMAIL_POR_ROL, EMAIL_REPRESENTANTE


def _texto(respuesta) -> str:
    return respuesta.get_data(as_text=True)


def test_sin_permiso_el_navegador_ve_la_pagina_403_con_su_referencia(
    ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_OPERADOR)

    respuesta = navegar("/usuarios")

    assert respuesta.status_code == 403
    assert "text/html" in respuesta.content_type
    cuerpo = _texto(respuesta)
    assert "No tenés acceso a esta sección" in cuerpo
    assert respuesta.headers["X-Correlation-ID"] in cuerpo


def test_sin_permiso_el_cliente_json_sigue_recibiendo_el_envelope(
    cliente_sembrado, ingresar
) -> None:
    ingresar(EMAIL_OPERADOR)

    respuesta = cliente_sembrado.get("/usuarios")

    assert respuesta.status_code == 403
    assert respuesta.get_json()["error"]["codigo"] == "PERMISO_DENEGADO"


def test_un_post_sin_permiso_tampoco_pasa_desde_un_formulario(
    ingresar_por_formulario, enviar_formulario
) -> None:
    """Aunque alguien arme el formulario a mano, el servidor lo rechaza."""
    ingresar_por_formulario(EMAIL_REPRESENTANTE)

    respuesta = enviar_formulario(
        "/organizaciones", {"nombre": "Organizacion trucha", "tipo": "ong"}
    )

    assert respuesta.status_code == 403
    assert "Organizacion trucha" not in _texto(respuesta)


def test_una_ruta_inexistente_muestra_la_pagina_404(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_OPERADOR)

    respuesta = navegar("/no-existe")

    assert respuesta.status_code == 404
    assert "No encontramos esta página" in _texto(respuesta)


@pytest.mark.parametrize("rol", list(EMAIL_POR_ROL))
def test_el_hub_muestra_solo_lo_que_el_perfil_puede_usar(
    rol, ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_POR_ROL[rol])

    cuerpo = _texto(navegar("/inicio"))

    es_administrador = rol == NombreRol.ADMINISTRADOR
    assert ('href="/usuarios"' in cuerpo) is es_administrador
    assert ('href="/organizaciones"' in cuerpo) is es_administrador


def test_el_operador_municipal_ve_la_pantalla_de_ofertas(
    ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_OPERADOR)

    cuerpo = _texto(navegar("/inicio"))

    assert 'href="/ofertas"' in cuerpo
    assert "Ofertas de ayuda" in cuerpo


def test_el_representante_ve_el_estado_de_sus_ofertas_en_el_hub(
    ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_REPRESENTANTE)

    cuerpo = _texto(navegar("/inicio"))

    assert "Estado de tus últimas ofertas" in cuerpo
    assert "Oferta #" in cuerpo


def test_una_pantalla_nueva_aparece_en_el_menu_solo_declarando_su_entrada(
    app, ingresar_por_formulario, navegar
) -> None:
    """La hipotesis de la epica, en su version de interfaz.

    Se registra una pantalla de juguete con su permiso y su entrada de menu, sin tocar la
    plantilla del hub: tiene que aparecer para los perfiles con el permiso y para ningun otro.
    """

    @app.get("/pantalla-de-emergencias")
    def _pantalla_de_emergencias():
        return "ok"

    registrar_entrada(
        app,
        EntradaDeMenu(
            endpoint="_pantalla_de_emergencias",
            titulo="Emergencias de prueba",
            permiso=EMERGENCIAS_CREAR,
        ),
    )

    for rol, email in EMAIL_POR_ROL.items():
        ingresar_por_formulario(email)
        cuerpo = _texto(navegar("/inicio"))
        tiene_el_permiso = EMERGENCIAS_CREAR in PERMISOS_POR_ROL[NombreRol(rol)]
        assert ("Emergencias de prueba" in cuerpo) is tiene_el_permiso, rol


@pytest.mark.parametrize("rol", list(EMAIL_POR_ROL))
def test_el_navbar_muestra_las_secciones_que_el_perfil_puede_usar(
    rol, ingresar_por_formulario, navegar
) -> None:
    """En una pantalla sin tarjetas (Mi perfil), los enlaces solo pueden venir del navbar."""
    ingresar_por_formulario(EMAIL_POR_ROL[rol])

    cuerpo = _texto(navegar("/sesion/actual"))

    assert 'href="/inicio"' in cuerpo
    es_administrador = rol == NombreRol.ADMINISTRADOR
    assert ('href="/usuarios"' in cuerpo) is es_administrador
    assert ('href="/organizaciones"' in cuerpo) is es_administrador


def test_el_navbar_marca_la_seccion_actual(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_POR_ROL[NombreRol.ADMINISTRADOR])

    cuerpo = _texto(navegar("/usuarios/nuevo"))
    enlace = cuerpo.split('href="/usuarios"', 1)[1].split(">", 1)[0]

    assert "bg-acento/60 text-primario" in enlace
