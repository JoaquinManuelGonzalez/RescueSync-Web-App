"""Calculos del panel de auditoria que no tocan la base: tiempos, series mensuales, exportacion
y duracion de las etapas del proceso."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.integraciones.bonita.consultas import NodoArchivado
from app.modulos.indicadores import graficos
from app.modulos.indicadores.etapas import duraciones_por_tarea
from app.modulos.indicadores.exportacion import (
    BOM_UTF8,
    TablaExportable,
    a_csv,
    a_json,
    nombre_de_archivo,
)
from app.modulos.indicadores.graficos import escala_para
from app.modulos.indicadores.periodo import Periodo
from app.modulos.indicadores.series import etiqueta_de_mes, mes_de, mes_iso, meses_contiguos
from app.modulos.indicadores.tiempos import (
    columnas_de_duracion,
    duracion_abreviada,
    duracion_como_texto,
    duracion_entre,
    porcentaje_entero,
    promedio_de_duraciones,
)

# --- Porcentajes ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("parte", "total", "esperado"), [(1, 4, 25), (2, 5, 40), (1, 8, 13), (0, 3, 0), (3, 0, None)]
)
def test_porcentaje_entero(parte, total, esperado) -> None:
    assert porcentaje_entero(parte, total) == esperado


# --- Duraciones -----------------------------------------------------------------------


def _en_pantalla(texto: str) -> str:
    """El texto como se ve en pantalla: con espacio duro entre cada numero y su unidad."""
    return re.sub(r"(?<=\d) ", "\u00a0", texto)


def test_el_numero_y_su_unidad_no_se_separan_al_cambiar_de_renglon() -> None:
    assert duracion_como_texto(timedelta(minutes=33, seconds=5)) == "33\u00a0min 5\u00a0s"


def test_la_duracion_es_exacta() -> None:
    inicio = datetime(2026, 10, 1, 12, tzinfo=UTC)
    fin = inicio + timedelta(minutes=15, seconds=32, milliseconds=250)
    assert duracion_entre(inicio, fin) == timedelta(minutes=15, seconds=32, milliseconds=250)


def test_la_duracion_toma_sin_zona_como_utc_y_nunca_es_negativa() -> None:
    """SQLite devuelve las fechas sin zona; PostgreSQL, con zona. Restan igual. Un fin anterior
    al inicio (un dato inconsistente) cuenta como cero."""
    con_zona = datetime(2026, 10, 1, 12, tzinfo=UTC)
    assert duracion_entre(con_zona, datetime(2026, 10, 1, 12, 15)) == timedelta(minutes=15)
    assert duracion_entre(con_zona, con_zona - timedelta(days=1)) == timedelta(0)


def test_el_promedio_de_duraciones_redondea_al_segundo_mitad_hacia_arriba() -> None:
    assert promedio_de_duraciones([timedelta(seconds=1), timedelta(seconds=2)]) == timedelta(
        seconds=2
    )
    # 10 min y 20 min 1 s promedian 15 min 0,5 s: queda en 15 min 1 s.
    assert promedio_de_duraciones(
        [timedelta(minutes=10), timedelta(minutes=20, seconds=1)]
    ) == timedelta(minutes=15, seconds=1)
    # La HU de resolucion en termino: 5, 6, 8 y 10 dias promedian 7 d 6 h exactos.
    dias = [timedelta(days=n) for n in (5, 6, 8, 10)]
    assert promedio_de_duraciones(dias) == timedelta(days=7, hours=6)


def test_sin_duraciones_no_hay_promedio_de_duraciones() -> None:
    assert promedio_de_duraciones([]) is None


@pytest.mark.parametrize(
    ("duracion", "esperado"),
    [
        (timedelta(0), _en_pantalla("0 s")),
        (timedelta(milliseconds=400), _en_pantalla("0 s")),
        (timedelta(seconds=45), _en_pantalla("45 s")),
        (timedelta(minutes=15, seconds=32), _en_pantalla("15 min 32 s")),
        (timedelta(days=1, hours=4, minutes=12, seconds=5), _en_pantalla("1 d 4 h 12 min 5 s")),
        (timedelta(days=2, minutes=5), _en_pantalla("2 d 5 min")),
        (timedelta(days=45, seconds=1), _en_pantalla("45 d 1 s")),
        (None, "—"),
    ],
)
def test_duracion_como_texto(duracion, esperado) -> None:
    assert duracion_como_texto(duracion) == esperado


@pytest.mark.parametrize(
    ("duracion", "esperado"),
    [
        (timedelta(days=1, hours=4, minutes=12, seconds=5), _en_pantalla("1 d 4 h")),
        (timedelta(hours=23, minutes=59, seconds=40), _en_pantalla("1 d")),
        (timedelta(hours=1, minutes=59, seconds=40), _en_pantalla("2 h")),
        (timedelta(days=1, minutes=30), _en_pantalla("1 d 1 h")),
        (timedelta(minutes=15, seconds=32), _en_pantalla("15 min 32 s")),
        (timedelta(seconds=45), _en_pantalla("45 s")),
        (timedelta(0), _en_pantalla("0 s")),
    ],
)
def test_duracion_abreviada_redondea_a_la_segunda_unidad(duracion, esperado) -> None:
    assert duracion_abreviada(duracion) == esperado


def test_columnas_de_duracion_para_exportar() -> None:
    assert columnas_de_duracion(timedelta(days=1, hours=1, minutes=52, seconds=5)) == (
        93125,
        "1 d 1 h 52 min 5 s",
    )
    assert columnas_de_duracion(None) == (None, None)


# --- Graficos de duracion -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("maxima", "abreviatura"),
    [
        (timedelta(seconds=119), "s"),
        (timedelta(minutes=2), "min"),
        (timedelta(hours=1, minutes=59), "min"),
        (timedelta(hours=2), "h"),
        (timedelta(hours=47), "h"),
        (timedelta(days=2), "d"),
        (None, "s"),
    ],
)
def test_la_escala_es_la_mayor_unidad_en_que_el_maximo_llega_a_2(maxima, abreviatura) -> None:
    assert escala_para([timedelta(seconds=10), None, maxima]).abreviatura == abreviatura


def test_las_barras_de_duracion_traen_el_eje_y_los_textos() -> None:
    definicion = graficos.barras_de_duracion(
        ["Alta", "Baja"],
        [timedelta(hours=1, minutes=30), None],
        tonos=["advertencia", "neutro"],
        sin_dato="Sin casos",
    )

    assert definicion["valores"] == [90.0, None]
    assert definicion["unidadDelEje"] == "min"
    assert definicion["textos"] == [_en_pantalla("1 h 30 min"), None]
    assert definicion["textosCortos"] == [_en_pantalla("1 h 30 min"), None]
    assert definicion["sinDato"] == "Sin casos"
    assert "marcadores" not in definicion


def test_las_marcas_de_una_duracion_entran_en_la_escala() -> None:
    """El plazo de 3 dias lleva el eje a dias, aunque la barra dure 15 minutos."""
    definicion = graficos.barras_de_duracion(
        ["Crítica"],
        [timedelta(minutes=15)],
        tonos=["primario"],
        marcadores=graficos.Marcadores("Plazo objetivo", [timedelta(days=3)]),
    )

    assert definicion["unidadDelEje"] == "d"
    assert definicion["valores"] == [0.01]
    assert definicion["textosCortos"] == [_en_pantalla("15 min")]
    assert definicion["marcadores"] == {
        "nombre": "Plazo objetivo",
        "valores": [3.0],
        "textos": [_en_pantalla("3 d")],
    }


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
        "Publicar": timedelta(days=1),
        "Seleccionar ofertas": timedelta(days=2),
    }


def test_con_registro_ready_la_tarea_arranca_cuando_quedo_disponible() -> None:
    linea = [
        _nodo("1", "Inicio", "START_EVENT", "completed", 0),
        _nodo("2", "Publicar", "USER_TASK", "ready", 12),
        _nodo("2", "Publicar", "USER_TASK", "completed", 36),
    ]
    assert duraciones_por_tarea(linea, INICIO) == {"Publicar": timedelta(days=1)}


def test_las_ejecuciones_repetidas_de_una_tarea_se_suman() -> None:
    """Una reapertura vuelve a ejecutar "Publicar": la etapa suma las dos ejecuciones."""
    linea = [
        _nodo("1", "Publicar", "USER_TASK", "completed", 24),
        _nodo("2", "Liberar recursos", "AUTOMATIC_TASK", "completed", 48),
        _nodo("3", "Publicar", "USER_TASK", "completed", 96),
    ]
    assert duraciones_por_tarea(linea, INICIO) == {"Publicar": timedelta(days=3)}
