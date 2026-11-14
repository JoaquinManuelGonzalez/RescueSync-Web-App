"""Rutas de las secciones del panel de auditoria y exportacion de sus indicadores (HU de
exportacion en CSV y JSON).

Las fechas son de 2025 (ninguna semilla cae ahi) y "hoy" se fija en abril de 2025.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from app.modulos.emergencias.modelos import EstadoEmergencia, TipoNecesidad
from app.modulos.indicadores import rutas as rutas_de_indicadores
from app.modulos.indicadores.formularios import MENSAJE_RUBRO_INVALIDO
from app.modulos.indicadores.secciones import INDICADORES_EXPORTABLES

from .conftest import (
    EMAIL_ADMINISTRADOR,
    EMAIL_AUDITOR,
    EMAIL_COORDINADOR,
    EMAIL_OPERADOR,
    EMAIL_REPRESENTANTE,
)

PERFILES_SIN_ACCESO = [EMAIL_OPERADOR, EMAIL_COORDINADOR, EMAIL_REPRESENTANTE, EMAIL_ADMINISTRADOR]
SEP_OCT = {"desde": "2025-09-01", "hasta": "2025-10-31"}


@pytest.fixture(autouse=True)
def hoy_fijo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rutas_de_indicadores, "hoy_en_la_interfaz", lambda: date(2025, 11, 15))


@pytest.fixture
def recursos_de_la_hu(crear_emergencias, cargar_necesidades) -> None:
    """Septiembre: 1000 raciones y 5 paramedicos; octubre: 300 raciones."""
    septiembre, octubre = crear_emergencias(
        (datetime(2025, 9, 10, 15, tzinfo=UTC), EstadoEmergencia.activa),
        (datetime(2025, 10, 5, 15, tzinfo=UTC), EstadoEmergencia.activa),
    )
    cargar_necesidades(
        septiembre,
        (1000, 1000),
        (5, 5),
        categorias=[TipoNecesidad.alimentos, TipoNecesidad.personal_medico],
        adjudicada_en=datetime(2025, 9, 20, 15, tzinfo=UTC),
    )
    cargar_necesidades(
        octubre,
        (300, 300),
        categorias=[TipoNecesidad.alimentos],
        adjudicada_en=datetime(2025, 10, 9, 15, tzinfo=UTC),
    )


# --- Secciones -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ruta", "graficos"),
    [
        (
            "/auditoria/recursos",
            ["grafico-movilizados", "grafico-demanda", "grafico-inhabilitacion"],
        ),
        ("/auditoria/red-de-ongs", ["grafico-consorcios", "grafico-ranking"]),
        ("/auditoria/tiempos-de-respuesta", ["grafico-tiempos"]),
    ],
)
def test_el_auditor_ve_cada_seccion_con_sus_graficos(
    ruta, graficos, ingresar_por_formulario, navegar, crear_emergencias, cargar_necesidades
) -> None:
    (emergencia,) = crear_emergencias(
        (datetime(2025, 9, 10, 15, tzinfo=UTC), EstadoEmergencia.activa)
    )
    cargar_necesidades(emergencia, (10, 10), adjudicada_en=datetime(2025, 9, 12, tzinfo=UTC))
    ingresar_por_formulario(EMAIL_AUDITOR)

    respuesta = navegar(ruta, query_string=SEP_OCT)

    cuerpo = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    for grafico in graficos:
        assert f'id="{grafico}"' in cuerpo
    assert "Exportar" in cuerpo


def test_la_pestana_de_proceso_aparece_en_el_panel(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    cuerpo = navegar("/auditoria").get_data(as_text=True)

    for titulo in ("Recursos", "Red de ONGs", "Tiempos de respuesta", "Proceso"):
        assert f"<span>{titulo}</span>" in cuerpo


def test_recursos_por_json(cliente_sembrado, ingresar, recursos_de_la_hu) -> None:
    ingresar(EMAIL_AUDITOR)

    datos = cliente_sembrado.get("/auditoria/recursos", query_string=SEP_OCT).get_json()

    assert datos["recursos_movilizados"]["total"] == 1305
    assert datos["filtros"] == {"rubro": None}


def test_un_rubro_invalido_no_se_aplica(cliente_sembrado, ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    pantalla = navegar("/auditoria/recursos", query_string={**SEP_OCT, "rubro": "nafta"})

    assert pantalla.status_code == 400
    assert MENSAJE_RUBRO_INVALIDO in pantalla.get_data(as_text=True)
    respuesta = cliente_sembrado.get("/auditoria/recursos?rubro=nafta")
    assert respuesta.status_code == 400
    assert respuesta.get_json()["error"]["codigo"] == "SOLICITUD_INVALIDA"


def test_el_orden_del_ranking_se_anuncia_en_la_tabla(
    ingresar_por_formulario, navegar, crear_emergencias, cargar_necesidades
) -> None:
    (emergencia,) = crear_emergencias(
        (datetime(2025, 9, 10, 15, tzinfo=UTC), EstadoEmergencia.activa)
    )
    cargar_necesidades(emergencia, (10, 10))
    ingresar_por_formulario(EMAIL_AUDITOR)

    cuerpo = navegar(
        "/auditoria/red-de-ongs", query_string={**SEP_OCT, "orden": "tiempo"}
    ).get_data(as_text=True)

    assert 'aria-sort="ascending"' in cuerpo
    assert "ordenado por tiempo medio de ejecución" in cuerpo


# --- Exportacion ----------------------------------------------------------------------


def test_ca01_exportar_csv(cliente_sembrado, ingresar, recursos_de_la_hu) -> None:
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get(
        "/auditoria/exportaciones/recursos-movilizados.csv",
        query_string={"desde": "2025-09-01", "hasta": "2025-10-31"},
    )

    assert respuesta.status_code == 200
    assert respuesta.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert respuesta.headers["Content-Disposition"] == (
        'attachment; filename="rescuesync-recursos-movilizados-2025-09-01_2025-10-31.csv"'
    )
    assert respuesta.get_data(as_text=True).splitlines() == [
        "mes,rubro,unidades",
        "2025-09,Personal sanitario,5",
        "2025-09,Alimentos,1000",
        "2025-10,Alimentos,300",
    ]


def test_ca02_exportar_json_con_los_filtros(cliente_sembrado, ingresar, recursos_de_la_hu) -> None:
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get(
        "/auditoria/exportaciones/recursos-movilizados.json",
        query_string={**SEP_OCT, "rubro": "alimentos"},
    )

    assert respuesta.headers["Content-Disposition"].endswith(
        'filename="rescuesync-recursos-movilizados-2025-09-01_2025-10-31.json"'
    )
    datos = json.loads(respuesta.get_data(as_text=True))
    assert datos["filtros"] == {"desde": "2025-09-01", "hasta": "2025-10-31", "rubro": "alimentos"}
    assert datos["datos"] == [
        {"mes": "2025-09", "rubro": "Alimentos", "unidades": 1000},
        {"mes": "2025-10", "rubro": "Alimentos", "unidades": 300},
    ]


def test_lo_exportado_coincide_con_lo_que_muestra_la_seccion(
    cliente_sembrado, ingresar, recursos_de_la_hu
) -> None:
    ingresar(EMAIL_AUDITOR)

    seccion = cliente_sembrado.get("/auditoria/recursos", query_string=SEP_OCT).get_json()
    exportado = json.loads(
        cliente_sembrado.get(
            "/auditoria/exportaciones/recursos-movilizados.json", query_string=SEP_OCT
        ).get_data(as_text=True)
    )

    assert exportado["datos"] == seccion["recursos_movilizados"]["datos"]


@pytest.mark.parametrize(
    "slug", sorted(set(INDICADORES_EXPORTABLES) - {"etapas-del-proceso", "resolucion-en-termino"})
)
def test_ca03_sin_datos_el_csv_trae_solo_encabezados(cliente_sembrado, ingresar, slug) -> None:
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get(
        f"/auditoria/exportaciones/{slug}.csv",
        query_string={"desde": "2025-01-01", "hasta": "2025-01-31"},
    )

    assert respuesta.status_code == 200
    lineas = respuesta.get_data(as_text=True).splitlines()
    if slug == "resumen-de-actividad":
        # El resumen siempre tiene sus cuatro cifras, aunque sean 0.
        assert len(lineas) == 5
    else:
        assert len(lineas) == 1, lineas


@pytest.mark.parametrize("email", PERFILES_SIN_ACCESO)
def test_ca04_otro_perfil_recibe_403(cliente_sembrado, ingresar, email) -> None:
    ingresar(email)

    respuesta = cliente_sembrado.get("/auditoria/exportaciones/recursos-movilizados.csv")

    assert respuesta.status_code == 403
    assert respuesta.get_json()["error"]["codigo"] == "PERMISO_DENEGADO"


@pytest.mark.parametrize(
    "ruta",
    [
        "/auditoria/exportaciones/no-existe.csv",
        "/auditoria/exportaciones/recursos-movilizados.xlsx",
    ],
)
def test_un_indicador_o_formato_desconocido_es_404(cliente_sembrado, ingresar, ruta) -> None:
    ingresar(EMAIL_AUDITOR)

    assert cliente_sembrado.get(ruta).status_code == 404


def test_un_periodo_invalido_no_se_exporta(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get(
        "/auditoria/exportaciones/recursos-movilizados.csv",
        query_string={"desde": "2025-10-31", "hasta": "2025-09-01"},
    )

    assert respuesta.status_code == 400
