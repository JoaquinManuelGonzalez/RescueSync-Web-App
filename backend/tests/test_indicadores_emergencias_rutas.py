"""Seccion "Emergencias" del panel de auditoria, por navegador y por JSON.

Cada test se nombra por el criterio de aceptacion de la HU que verifica. "Hoy" se fija en abril
de 2025 y las emergencias se registran dentro de los ultimos 30 dias (el periodo por defecto),
asi ninguna semilla altera los conteos.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime

import pytest

from app.modulos.emergencias.modelos import EstadoEmergencia, NivelGravedad
from app.modulos.indicadores import rutas as rutas_de_indicadores
from app.modulos.indicadores.exportacion import BOM_UTF8
from app.modulos.indicadores.formularios import MENSAJE_GRAVEDAD_INVALIDA

from .conftest import EMAIL_AUDITOR, EMAIL_OPERADOR

URL = "/auditoria/emergencias"
HOY = date(2025, 4, 15)
EN_EL_PERIODO = datetime(2025, 4, 10, 15, 0, tzinfo=UTC)
FINALIZADA = EstadoEmergencia.finalizada


@pytest.fixture(autouse=True)
def hoy_fijo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rutas_de_indicadores, "hoy_en_la_interfaz", lambda: HOY)


@pytest.fixture
def escenario_de_la_hu(crear_emergencias, cargar_necesidades) -> int:
    """El de la HU: 3 activas, 2 en revision y 5 finalizadas, 4 al 100 % y 1 al 60 %.

    La parcial es la unica de gravedad alta. Devuelve su id.
    """
    ids = crear_emergencias(
        *[(EN_EL_PERIODO, EstadoEmergencia.activa)] * 3,
        *[(EN_EL_PERIODO, EstadoEmergencia.en_evaluacion)] * 2,
        *[(EN_EL_PERIODO, FINALIZADA)] * 4,
        (EN_EL_PERIODO, FINALIZADA, NivelGravedad.alta),
    )
    *completas, alta = ids[5:]
    for emergencia_id in completas:
        cargar_necesidades(emergencia_id, (10, 10))
    cargar_necesidades(alta, (10, 6))
    return alta


def _texto(respuesta) -> str:
    return respuesta.get_data(as_text=True)


def _graficos(cuerpo: str) -> list[dict]:
    """Las definiciones que la pagina le pasa a graficos.js."""
    bloques = re.findall(r'<script type="application/json" data-grafico>(.*?)</script>', cuerpo)
    return [json.loads(bloque) for bloque in bloques]


# --- Acceso y navegacion ---------------------------------------------------------


def test_el_auditor_ve_la_seccion_con_su_pestana_activa(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    respuesta = navegar(URL)

    assert respuesta.status_code == 200
    cuerpo = _texto(respuesta)
    assert 'aria-label="Secciones del panel"' in cuerpo
    assert re.search(r'href="/auditoria/emergencias"\s+aria-current="page"', cuerpo)
    assert "js/vendor/chart-4.4.9.umd.js" in cuerpo


def test_otro_perfil_vuelve_a_su_portal(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_OPERADOR)

    respuesta = navegar(URL)

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/inicio")


def test_la_seccion_usa_el_periodo_recordado_en_la_sesion(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_AUDITOR)
    cliente_sembrado.get("/auditoria?desde=2025-03-01&hasta=2025-03-31")

    datos = cliente_sembrado.get(URL).get_json()

    assert datos["periodo"] == {"desde": "2025-03-01", "hasta": "2025-03-31", "dias": 31}


# --- CA-01: distribucion por estado ----------------------------------------------


def test_ca01_el_json_trae_la_cantidad_de_cada_estado(
    cliente_sembrado, ingresar, escenario_de_la_hu
) -> None:
    ingresar(EMAIL_AUDITOR)

    datos = cliente_sembrado.get(URL).get_json()

    assert {fila["estado"]: fila["cantidad"] for fila in datos["por_estado"]} == {
        "registrada": 0,
        "en_evaluacion": 2,
        "activa": 3,
        "finalizada": 5,
        "cancelada": 0,
    }


def test_ca01_la_pantalla_dibuja_un_grafico_de_barras_por_estado(
    ingresar_por_formulario, navegar, escenario_de_la_hu
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    cuerpo = _texto(navegar(URL))

    barras = _graficos(cuerpo)[0]
    assert barras["tipo"] == "barras"
    assert barras["etiquetas"] == ["Registrada", "En revisión", "Activa", "Finalizada", "Cancelada"]
    assert barras["valores"] == [0, 2, 3, 5, 0]
    assert 'id="grafico-estados"' in cuerpo
    # La misma informacion, en una tabla para lectores de pantalla y sin JavaScript.
    assert re.search(r"<th scope=\"row\">Activa</th>\s*<td>3</td>", cuerpo)


# --- CA-02: cobertura de las finalizadas -----------------------------------------


def test_ca02_la_pantalla_muestra_la_torta_de_cobertura(
    ingresar_por_formulario, navegar, escenario_de_la_hu
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    cuerpo = _texto(navegar(URL))

    dona = _graficos(cuerpo)[1]
    assert dona["tipo"] == "dona"
    assert dona["etiquetas"] == ["Cobertura total", "Cobertura parcial"]
    assert dona["valores"] == [4, 1]
    assert dona["porcentajes"] == [80, 20]
    assert re.search(r"Cobertura total:</span>\s*<span[^>]*>4 \(80 %\)", cuerpo)
    assert re.search(r"Cobertura parcial:</span>\s*<span[^>]*>1 \(20 %\)", cuerpo)


def test_ca02_la_tabla_lista_las_finalizadas_con_faltantes(
    ingresar_por_formulario, navegar, escenario_de_la_hu
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    cuerpo = _texto(navegar(URL))

    assert "Finalizadas con faltantes" in cuerpo
    assert cuerpo.count('class="tabla-fila"') == 1
    assert "60 %" in cuerpo


def test_ca02_sin_finalizadas_la_torta_explica_por_que_no_hay_grafico(
    ingresar_por_formulario, navegar, crear_emergencias
) -> None:
    crear_emergencias((EN_EL_PERIODO, EstadoEmergencia.activa))
    ingresar_por_formulario(EMAIL_AUDITOR)

    cuerpo = _texto(navegar(URL))

    assert "Ninguna emergencia finalizó en este período." in cuerpo
    assert 'id="grafico-cobertura"' not in cuerpo


# --- CA-03: apertura por gravedad ------------------------------------------------


def test_ca03_con_gravedad_alta_la_torta_muestra_solo_esas_finalizadas(
    cliente_sembrado, ingresar, escenario_de_la_hu
) -> None:
    ingresar(EMAIL_AUDITOR)

    datos = cliente_sembrado.get(f"{URL}?gravedad=alta").get_json()

    assert datos["filtros"] == {"gravedad": "alta"}
    assert datos["registradas"] == 1
    assert datos["cobertura"]["total"] == {"cantidad": 0, "porcentaje": 0}
    assert datos["cobertura"]["parcial"] == {"cantidad": 1, "porcentaje": 100}
    assert [e["id"] for e in datos["cobertura"]["con_faltantes"]] == [str(escenario_de_la_hu)]


def test_ca03_la_pastilla_de_la_gravedad_elegida_queda_marcada(
    ingresar_por_formulario, navegar, escenario_de_la_hu
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    cuerpo = _texto(navegar(f"{URL}?gravedad=alta"))

    assert re.search(r'href="/auditoria/emergencias\?gravedad=alta"\s+aria-current="true"', cuerpo)
    assert _graficos(cuerpo)[1]["valores"] == [0, 1]


def test_ca03_cambiar_el_periodo_conserva_la_gravedad(
    ingresar_por_formulario, navegar, escenario_de_la_hu
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    cuerpo = _texto(navegar(f"{URL}?gravedad=alta"))

    assert '<input type="hidden" name="gravedad" value="alta">' in cuerpo
    atajo = r"/auditoria/emergencias\?desde=[\d-]+&amp;hasta=[\d-]+&amp;gravedad=alta"
    assert re.search(atajo, cuerpo)


def test_ca03_una_gravedad_invalida_por_json_es_400(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get(f"{URL}?gravedad=extrema")

    assert respuesta.status_code == 400
    error = respuesta.get_json()["error"]
    assert error["codigo"] == "SOLICITUD_INVALIDA"
    assert error["detalle"] == {"gravedad": [MENSAJE_GRAVEDAD_INVALIDA]}


def test_ca03_una_gravedad_invalida_en_el_navegador_no_se_aplica(
    ingresar_por_formulario, navegar, escenario_de_la_hu
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    respuesta = navegar(f"{URL}?gravedad=extrema")

    assert respuesta.status_code == 400
    cuerpo = _texto(respuesta)
    assert "El filtro de gravedad no se aplicó" in cuerpo
    # Se muestran todas las emergencias: "Todas" queda marcada.
    assert re.search(r'href="/auditoria/emergencias"\s+aria-current="true"', cuerpo)
    assert _graficos(cuerpo)[0]["valores"] == [0, 2, 3, 5, 0]


# --- Exportacion de las finalizadas con faltantes ----------------------------------


def test_la_tabla_de_faltantes_se_exporta_en_csv_con_la_ultima_ronda(
    cliente_sembrado, ingresar, crear_emergencias, cargar_necesidades
) -> None:
    """El caso del bug: pidio 100 y se reabrio; en la ronda adjudicada pidio 10 y recibio 8."""
    (emergencia_id,) = crear_emergencias((EN_EL_PERIODO, FINALIZADA))
    cargar_necesidades(emergencia_id, (100, 0), reabierta=True)
    cargar_necesidades(emergencia_id, (10, 8))
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get("/auditoria/exportaciones/finalizadas-con-faltantes.csv")

    assert respuesta.status_code == 200
    assert respuesta.headers["Content-Disposition"] == (
        'attachment; filename="rescuesync-finalizadas-con-faltantes-2025-03-17_2025-04-15.csv"'
    )
    encabezado, fila = _texto(respuesta).removeprefix(BOM_UTF8).splitlines()
    assert encabezado == (
        "emergencia,gravedad,unidades_requeridas,unidades_adjudicadas,porcentaje_cubierto"
    )
    assert fila.endswith(",Media,10,8,80")


def test_la_tabla_de_faltantes_tiene_su_menu_de_exportacion_con_la_gravedad(
    ingresar_por_formulario, navegar, escenario_de_la_hu
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    cuerpo = _texto(navegar(f"{URL}?gravedad=alta"))

    assert re.search(
        r'href="/auditoria/exportaciones/finalizadas-con-faltantes\.csv\?[^"]*gravedad=alta"',
        cuerpo,
    )
    assert "los datos de Finalizadas con faltantes" in cuerpo
