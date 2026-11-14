"""Panel de auditoria: acceso, periodo y tarjetas, por navegador y por JSON.

Cada test se nombra por el criterio de aceptacion de la HU que verifica. Las emergencias se
registran en 2025 y "hoy" se fija en abril de 2025, asi ninguna semilla altera los conteos.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.core.acceso.autorizacion import MENSAJE_SIN_PERMISO
from app.modulos.emergencias.modelos import EstadoEmergencia
from app.modulos.indicadores import rutas as rutas_de_indicadores
from app.modulos.indicadores.formularios import MENSAJE_FECHA_INVALIDA, MENSAJE_PERIODO_INVERTIDO

from .conftest import (
    EMAIL_ADMINISTRADOR,
    EMAIL_AUDITOR,
    EMAIL_COORDINADOR,
    EMAIL_OPERADOR,
    EMAIL_POR_ROL,
    EMAIL_REPRESENTANTE,
)

PERFILES_SIN_ACCESO = [EMAIL_OPERADOR, EMAIL_COORDINADOR, EMAIL_REPRESENTANTE, EMAIL_ADMINISTRADOR]

HOY = date(2025, 4, 15)

ETIQUETAS_DE_LAS_TARJETAS = (
    "Emergencias registradas",
    "Emergencias activas",
    "Emergencias finalizadas",
    "ONGs con adjudicación",
)


@pytest.fixture(autouse=True)
def hoy_fijo(monkeypatch: pytest.MonkeyPatch) -> date:
    monkeypatch.setattr(rutas_de_indicadores, "hoy_en_la_interfaz", lambda: HOY)
    return HOY


def _al_mediodia(anio: int, mes: int, dia: int) -> datetime:
    """Mediodia en Argentina, en UTC: lejos de cualquier borde de dia."""
    return datetime(anio, mes, dia, 15, 0, tzinfo=UTC)


def _texto(respuesta) -> str:
    return respuesta.get_data(as_text=True)


def _endpoints_del_panel(app) -> list[str]:
    return [
        regla.rule
        for regla in app.url_map.iter_rules()
        if regla.endpoint.startswith("indicadores.") and not regla.arguments
    ]


# --- CA-01: acceso permitido -----------------------------------------------------


def test_ca01_el_auditor_ve_el_panel_con_las_cuatro_tarjetas(
    ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    respuesta = navegar("/auditoria")

    assert respuesta.status_code == 200
    cuerpo = _texto(respuesta)
    for etiqueta in ETIQUETAS_DE_LAS_TARJETAS:
        assert etiqueta in cuerpo
    assert cuerpo.count('class="kpi kpi-') == 4


def test_ca01_las_cifras_se_calculan_sobre_el_periodo_seleccionado(
    cliente_sembrado, ingresar, crear_emergencias
) -> None:
    crear_emergencias(
        (_al_mediodia(2025, 4, 10), EstadoEmergencia.registrada),
        (_al_mediodia(2025, 4, 1), EstadoEmergencia.en_evaluacion),
        (_al_mediodia(2025, 3, 25), EstadoEmergencia.activa),
        (_al_mediodia(2025, 3, 20), EstadoEmergencia.finalizada),
        (_al_mediodia(2025, 3, 18), EstadoEmergencia.cancelada),
        (_al_mediodia(2025, 3, 1), EstadoEmergencia.finalizada),  # fuera de los ultimos 30 dias
    )
    ingresar(EMAIL_AUDITOR)

    datos = cliente_sembrado.get("/auditoria").get_json()

    assert datos["resumen"] == {
        "emergencias_registradas": 5,
        "emergencias_activas": 3,
        "emergencias_finalizadas": 1,
        "ongs_con_adjudicacion": 0,
    }


def test_ca01_la_tarjeta_de_ongs_cuenta_las_adjudicadas_del_periodo(
    cliente_sembrado, ingresar, crear_emergencias, cargar_necesidades
) -> None:
    (emergencia,) = crear_emergencias((_al_mediodia(2025, 4, 10), EstadoEmergencia.activa))
    cargar_necesidades(emergencia, (100, 100))
    ingresar(EMAIL_AUDITOR)

    datos = cliente_sembrado.get("/auditoria").get_json()

    assert datos["resumen"]["ongs_con_adjudicacion"] == 1


# --- CA-02: acceso denegado a otros roles ----------------------------------------


@pytest.mark.parametrize("email", PERFILES_SIN_ACCESO)
def test_ca02_otro_perfil_vuelve_a_su_portal_desde_el_navegador(
    email, ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(email)

    respuesta = navegar("/auditoria")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/inicio")
    assert MENSAJE_SIN_PERMISO in _texto(navegar("/inicio"))


@pytest.mark.parametrize("email", PERFILES_SIN_ACCESO)
def test_ca02_otro_perfil_recibe_403_en_cualquier_endpoint_del_panel(
    email, app, cliente_sembrado, ingresar
) -> None:
    """Recorre el mapa de rutas: un endpoint que se sume al panel sin protegerse falla aca."""
    endpoints = _endpoints_del_panel(app)
    assert endpoints
    ingresar(email)

    for endpoint in endpoints:
        respuesta = cliente_sembrado.get(endpoint)
        assert respuesta.status_code == 403, endpoint
        assert respuesta.get_json()["error"]["codigo"] == "PERMISO_DENEGADO"


def test_ca02_sin_sesion_el_panel_pide_iniciar_sesion(navegar) -> None:
    respuesta = navegar("/auditoria")

    assert respuesta.status_code == 302
    assert "/sesion/ingreso?next=/auditoria" in respuesta.headers["Location"]


@pytest.mark.parametrize(("rol", "email"), list(EMAIL_POR_ROL.items()))
def test_ca02_la_tarjeta_del_panel_aparece_solo_para_el_auditor(
    rol, email, ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(email)

    cuerpo = _texto(navegar("/inicio"))

    assert ("Panel de auditoría" in cuerpo) is (rol == "auditor")


# --- CA-03: periodo por defecto --------------------------------------------------


def test_ca03_la_primera_vez_el_periodo_son_los_ultimos_30_dias(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_AUDITOR)

    datos = cliente_sembrado.get("/auditoria").get_json()

    assert datos["periodo"] == {"desde": "2025-03-17", "hasta": "2025-04-15", "dias": 30}


def test_ca03_el_formulario_muestra_el_periodo_por_defecto(
    ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    cuerpo = _texto(navegar("/auditoria"))

    assert 'value="2025-03-17"' in cuerpo
    assert 'value="2025-04-15"' in cuerpo
    assert "<strong>17/03/2025</strong> al <strong>15/04/2025</strong>" in cuerpo


def test_ca03_el_periodo_aplicado_se_conserva_durante_la_sesion(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_AUDITOR)
    cliente_sembrado.get("/auditoria?desde=2025-03-01&hasta=2025-03-31")

    datos = cliente_sembrado.get("/auditoria").get_json()

    assert datos["periodo"]["desde"] == "2025-03-01"
    assert datos["periodo"]["hasta"] == "2025-03-31"


def test_ca03_una_sesion_nueva_vuelve_al_periodo_por_defecto(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_AUDITOR)
    cliente_sembrado.get("/auditoria?desde=2025-03-01&hasta=2025-03-31")

    ingresar(EMAIL_AUDITOR)
    datos = cliente_sembrado.get("/auditoria").get_json()

    assert datos["periodo"]["desde"] == "2025-03-17"


# --- CA-04: cambio de periodo ----------------------------------------------------


def test_ca04_las_tarjetas_se_recalculan_con_las_emergencias_del_periodo_elegido(
    cliente_sembrado, ingresar, crear_emergencias
) -> None:
    crear_emergencias(
        (_al_mediodia(2025, 2, 27), EstadoEmergencia.finalizada),
        (_al_mediodia(2025, 3, 5), EstadoEmergencia.registrada),
        (_al_mediodia(2025, 3, 12), EstadoEmergencia.finalizada),
        (_al_mediodia(2025, 3, 30), EstadoEmergencia.cancelada),
        (_al_mediodia(2025, 4, 2), EstadoEmergencia.activa),
    )
    ingresar(EMAIL_AUDITOR)

    datos = cliente_sembrado.get("/auditoria?desde=2025-03-01&hasta=2025-03-31").get_json()

    assert datos["periodo"] == {"desde": "2025-03-01", "hasta": "2025-03-31", "dias": 31}
    assert datos["resumen"]["emergencias_registradas"] == 3
    assert datos["resumen"]["emergencias_activas"] == 1
    assert datos["resumen"]["emergencias_finalizadas"] == 1


def test_ca04_la_pantalla_muestra_el_periodo_aplicado(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    respuesta = navegar("/auditoria?desde=2025-03-01&hasta=2025-03-31")

    assert respuesta.status_code == 200
    assert "<strong>01/03/2025</strong> al <strong>31/03/2025</strong>" in _texto(respuesta)


def test_ca04_un_periodo_de_un_solo_dia_es_valido(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get("/auditoria?desde=2025-03-10&hasta=2025-03-10")

    assert respuesta.status_code == 200
    assert respuesta.get_json()["periodo"]["dias"] == 1


# --- CA-05: periodo invalido -----------------------------------------------------


def test_ca05_un_periodo_invertido_muestra_el_error_y_no_se_aplica(
    cliente_sembrado, ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)
    navegar("/auditoria?desde=2025-03-01&hasta=2025-03-31")

    respuesta = navegar("/auditoria?desde=2025-03-31&hasta=2025-03-01")

    assert respuesta.status_code == 400
    cuerpo = _texto(respuesta)
    assert MENSAJE_PERIODO_INVERTIDO in cuerpo
    assert 'aria-invalid="true"' in cuerpo
    # Las cifras siguen siendo las del periodo anterior, y la sesion no cambio.
    assert "<strong>01/03/2025</strong> al <strong>31/03/2025</strong>" in cuerpo
    assert "se mantiene el período anterior" in cuerpo
    assert cliente_sembrado.get("/auditoria").get_json()["periodo"]["desde"] == "2025-03-01"


def test_ca05_un_periodo_invertido_por_json_es_400_con_el_error_del_campo(
    cliente_sembrado, ingresar
) -> None:
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get("/auditoria?desde=2025-03-31&hasta=2025-03-01")

    assert respuesta.status_code == 400
    error = respuesta.get_json()["error"]
    assert error["codigo"] == "SOLICITUD_INVALIDA"
    assert error["detalle"] == {"desde": [MENSAJE_PERIODO_INVERTIDO]}


@pytest.mark.parametrize(
    ("consulta", "campo", "mensaje"),
    [
        ("desde=31/03/2025&hasta=2025-04-01", "desde", MENSAJE_FECHA_INVALIDA),
        ("desde=2025-03-01&hasta=", "hasta", "Elegí la fecha de fin."),
        ("hasta=2025-03-01", "desde", "Elegí la fecha de inicio."),
    ],
)
def test_ca05_una_fecha_invalida_o_faltante_se_informa_en_castellano(
    cliente_sembrado, ingresar, consulta, campo, mensaje
) -> None:
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get(f"/auditoria?{consulta}")

    assert respuesta.status_code == 400
    assert respuesta.get_json()["error"]["detalle"][campo] == [mensaje]


# --- Regla de negocio: solo lectura ----------------------------------------------


def test_el_panel_es_de_solo_lectura(app) -> None:
    """El auditor no crea, edita ni elimina nada: el panel no expone ningun metodo de escritura."""
    metodos = {
        metodo
        for regla in app.url_map.iter_rules()
        if regla.endpoint.startswith("indicadores.")
        for metodo in regla.methods
    }

    assert metodos <= {"GET", "HEAD", "OPTIONS"}
