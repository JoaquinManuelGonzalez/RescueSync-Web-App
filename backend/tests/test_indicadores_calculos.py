"""Calculos del panel de auditoria que no tocan la base: tiempos, series mensuales, exportacion
y duracion de las etapas del proceso."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.integraciones.bonita.consultas import NodoArchivado
from app.modulos.indicadores.etapas import duraciones_por_tarea
from app.modulos.indicadores.exportacion import (
    BOM_UTF8,
    TablaExportable,
    a_csv,
    a_json,
    nombre_de_archivo,
)
from app.modulos.indicadores.periodo import Periodo
from app.modulos.indicadores.series import etiqueta_de_mes, mes_de, mes_iso, meses_contiguos
from app.modulos.indicadores.tiempos import (
    dias_como_texto,
    duracion_en_dias,
    porcentaje_entero,
    promedio_en_dias,
)

# --- Tiempos ---------------------------------------------------------------------


def test_la_duracion_se_mide_en_dias_exactos() -> None:
    inicio = datetime(2026, 10, 1, 12, tzinfo=UTC)
    assert duracion_en_dias(inicio, inicio + timedelta(days=2, hours=12)) == Decimal("2.5")


def test_una_fecha_sin_zona_se_toma_como_utc() -> None:
    """SQLite devuelve las fechas sin zona; PostgreSQL, con zona. Restan igual."""
    con_zona = datetime(2026, 10, 1, 12, tzinfo=UTC)
    sin_zona = datetime(2026, 10, 3, 12)
    assert duracion_en_dias(con_zona, sin_zona) == Decimal(2)


def test_una_duracion_negativa_cuenta_como_cero() -> None:
    inicio = datetime(2026, 10, 5, tzinfo=UTC)
    assert duracion_en_dias(inicio, inicio - timedelta(days=1)) == Decimal(0)


def test_el_promedio_redondea_mitad_hacia_arriba() -> None:
    """La HU de resolucion en termino espera 7,3 para 5, 6, 8 y 10 dias (7,25)."""
    assert promedio_en_dias([Decimal(5), Decimal(6), Decimal(8), Decimal(10)]) == Decimal("7.3")


def test_sin_duraciones_no_hay_promedio() -> None:
    assert promedio_en_dias([]) is None


@pytest.mark.parametrize(
    ("parte", "total", "esperado"), [(1, 4, 25), (2, 5, 40), (1, 8, 13), (0, 3, 0), (3, 0, None)]
)
def test_porcentaje_entero(parte, total, esperado) -> None:
    assert porcentaje_entero(parte, total) == esperado


def test_dias_como_texto() -> None:
    assert dias_como_texto(Decimal("5.0")) == "5,0 días"
    assert dias_como_texto(None) == "—"


# --- Series mensuales --------------------------------------------------------------


def test_el_mes_se_toma_en_la_hora_de_argentina() -> None:
    """A las 22 h del 31/10 en Argentina ya es 01/11 en UTC, pero la adjudicacion es de octubre."""
    assert mes_de(datetime(2026, 11, 1, 1, 0, tzinfo=UTC)) == date(2026, 10, 1)


def test_el_eje_mensual_no_tiene_huecos() -> None:
    meses = meses_contiguos([date(2026, 11, 1), date(2026, 8, 15), date(2026, 8, 1)])
    assert meses == [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)]


def test_el_eje_mensual_cruza_el_anio() -> None:
    assert meses_contiguos([date(2026, 12, 1), date(2027, 1, 1)]) == [
        date(2026, 12, 1),
        date(2027, 1, 1),
    ]


def test_nombres_de_mes() -> None:
    assert etiqueta_de_mes(date(2026, 9, 1)) == "sep 2026"
    assert mes_iso(date(2026, 9, 1)) == "2026-09"


# --- Exportacion ---------------------------------------------------------------------


def test_ca03_sin_datos_el_csv_trae_solo_los_encabezados() -> None:
    assert a_csv(TablaExportable(columnas=("mes", "rubro", "unidades"))) == (
        f"{BOM_UTF8}mes,rubro,unidades\r\n"
    )


def test_el_csv_empieza_con_el_bom_para_que_excel_lea_los_acentos() -> None:
    contenido = a_csv(TablaExportable(columnas=("gravedad",), filas=(("Crítica",),)))

    assert contenido.encode("utf-8").startswith(b"\xef\xbb\xbf")
    assert contenido.removeprefix(BOM_UTF8).splitlines() == ["gravedad", "Crítica"]


def test_el_csv_usa_coma_punto_decimal_e_iso_8601() -> None:
    tabla = TablaExportable(
        columnas=("fecha", "ong", "dias", "tasa"),
        filas=((date(2026, 9, 1), "Cruz Solidaria, filial", Decimal("5.0"), None),),
    )
    assert a_csv(tabla).splitlines()[1] == '2026-09-01,"Cruz Solidaria, filial",5.0,'


def test_ca02_el_json_trae_los_filtros_y_los_datos() -> None:
    tabla = TablaExportable(columnas=("mes", "unidades"), filas=(("2026-09", 1005),))
    datos = a_json(
        indicador="recursos-movilizados",
        titulo="Recursos movilizados",
        filtros={"desde": date(2026, 9, 1), "hasta": date(2026, 10, 31), "rubro": None},
        tabla=tabla,
        generado_en=datetime(2026, 11, 1, tzinfo=UTC),
    )
    assert json.loads(json.dumps(datos))["filtros"] == {
        "desde": "2026-09-01",
        "hasta": "2026-10-31",
        "rubro": None,
    }
    assert datos["datos"] == [{"mes": "2026-09", "unidades": 1005}]


def test_ca01_nombre_del_archivo() -> None:
    periodo = Periodo(desde=date(2026, 9, 1), hasta=date(2026, 10, 31))
    assert (
        nombre_de_archivo("recursos-movilizados", periodo, "csv")
        == "rescuesync-recursos-movilizados-2026-09-01_2026-10-31.csv"
    )


def test_una_fila_con_otra_cantidad_de_columnas_es_un_error() -> None:
    with pytest.raises(ValueError):
        TablaExportable(columnas=("a", "b"), filas=((1,),))


# --- Duracion de las etapas del proceso -------------------------------------------------

INICIO = datetime(2026, 10, 1, 9, 0)


def _nodo(nodo_id, nombre, tipo, estado, horas) -> NodoArchivado:
    instante = INICIO + timedelta(hours=horas)
    return NodoArchivado(nodo_id, nombre, tipo, estado, instante, instante)


def test_sin_registro_ready_la_tarea_arranca_cuando_termina_el_nodo_anterior() -> None:
    linea = [
        _nodo("1", "Inicio", "START_EVENT", "completed", 0),
        _nodo("2", "Publicar", "USER_TASK", "completed", 24),
        _nodo("3", "Obtener ofertas", "AUTOMATIC_TASK", "completed", 72),
        _nodo("4", "Seleccionar ofertas", "USER_TASK", "completed", 120),
    ]
    assert duraciones_por_tarea(linea, INICIO) == {
        "Publicar": Decimal(1),
        "Seleccionar ofertas": Decimal(2),
    }


def test_con_registro_ready_la_tarea_arranca_cuando_quedo_disponible() -> None:
    linea = [
        _nodo("1", "Inicio", "START_EVENT", "completed", 0),
        _nodo("2", "Publicar", "USER_TASK", "ready", 12),
        _nodo("2", "Publicar", "USER_TASK", "completed", 36),
    ]
    assert duraciones_por_tarea(linea, INICIO) == {"Publicar": Decimal(1)}


def test_las_ejecuciones_repetidas_de_una_tarea_se_suman() -> None:
    """Una reapertura vuelve a ejecutar "Publicar": la etapa suma las dos ejecuciones."""
    linea = [
        _nodo("1", "Publicar", "USER_TASK", "completed", 24),
        _nodo("2", "Liberar recursos", "AUTOMATIC_TASK", "completed", 48),
        _nodo("3", "Publicar", "USER_TASK", "completed", 96),
    ]
    assert duraciones_por_tarea(linea, INICIO) == {"Publicar": Decimal(3)}
