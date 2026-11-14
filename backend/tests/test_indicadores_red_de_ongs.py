"""Seccion "Red de ONGs" del panel de auditoria: consorcios y ranking de ONGs.

Cada test se nombra por el criterio de aceptacion de la HU que verifica. Las fechas son de 2025:
ninguna semilla cae en ese anio, asi que las cifras son exactas.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.modulos.emergencias.modelos import EstadoEmergencia
from app.modulos.indicadores.formularios import OrdenDelRanking
from app.modulos.indicadores.periodo import Periodo
from app.modulos.indicadores.red_de_ongs import (
    ONGS_EN_EL_GRAFICO,
    FilaDelRanking,
    RankingDeOngs,
    obtener_seccion_de_red_de_ongs,
)
from app.modulos.ofertas.modelos import TipoAsignacion

MARZO_DE_2025 = Periodo(desde=date(2025, 3, 1), hasta=date(2025, 3, 31))
MEDIADOS_DE_MARZO = datetime(2025, 3, 15, 15, tzinfo=UTC)
ADJUDICADA_EN = datetime(2025, 3, 18, 15, tzinfo=UTC)
A, B, C = "Cruz Solidaria", "Manos Unidas", "Grupo Scouts de Pergamino"


def _emergencias(crear_emergencias, cantidad: int) -> list[int]:
    return crear_emergencias(*[(MEDIADOS_DE_MARZO, EstadoEmergencia.activa)] * cantidad)


def _seccion(app, orden=OrdenDelRanking.volumen):
    with app.app_context():
        return obtener_seccion_de_red_de_ongs(MARZO_DE_2025, orden)


# --- Consorcios ---------------------------------------------------------------------


def test_ca01_y_ca02_proporcion_de_consorcios(app, crear_emergencias, cargar_necesidades) -> None:
    """10 ofertas adjudicadas, 3 de consorcio, en 2 de las 5 emergencias con adjudicaciones."""
    e1, e2, e3, e4, e5 = _emergencias(crear_emergencias, 5)
    for emergencia, consorcios in ((e1, 2), (e2, 1), (e3, 0), (e4, 0), (e5, 0)):
        for indice in range(2):
            consorcio = (B,) if indice < consorcios else ()
            cargar_necesidades(emergencia, (10, 10), ong=A, consorcio=consorcio)

    consorcios = _seccion(app).consorcios

    assert consorcios.porciones() == [
        ("Consorcio", 3, 30, "serie-1"),
        ("Individual", 7, 70, "serie-2"),
    ]
    assert consorcios.porcentaje_de_emergencias_con_consorcio == 40
    assert consorcios.tabla().filas == (("Consorcio", 3, 30), ("Individual", 7, 70))


def test_una_oferta_rechazada_no_cuenta(app, crear_emergencias, cargar_necesidades) -> None:
    (emergencia,) = _emergencias(crear_emergencias, 1)
    cargar_necesidades(emergencia, (10, 10))
    cargar_necesidades(emergencia, (10, 10, TipoAsignacion.rechazada), consorcio=(B,))

    assert _seccion(app).consorcios.adjudicadas == 1


def test_sin_adjudicaciones_no_hay_porcentaje(app, crear_emergencias) -> None:
    _emergencias(crear_emergencias, 1)

    consorcios = _seccion(app).consorcios

    assert consorcios.porcentaje_de_emergencias_con_consorcio is None
    assert consorcios.tabla().vacia


# --- Ranking de ONGs -------------------------------------------------------------------


def test_ca01_ranking_por_lotes_adjudicados(app, crear_emergencias, cargar_necesidades) -> None:
    """A tiene 5 lotes adjudicados, B 3 y C 1."""
    (emergencia,) = _emergencias(crear_emergencias, 1)
    for ong, lotes in ((C, 1), (A, 5), (B, 3)):
        for _ in range(lotes):
            cargar_necesidades(emergencia, (10, 10), ong=ong)

    grafico = _seccion(app).ranking.grafico()

    assert grafico["orientacion"] == "horizontal"
    assert grafico["etiquetas"] == [A, B, C]
    assert grafico["valores"] == [5, 3, 1]


def test_ca01_el_grafico_se_limita_a_las_diez_primeras() -> None:
    filas = tuple(FilaDelRanking(i, f"ONG {i:02d}", 20 - i, 0, None) for i in range(12))
    ranking = RankingDeOngs(orden=OrdenDelRanking.volumen, filas=filas)

    assert len(ranking.grafico()["etiquetas"]) == ONGS_EN_EL_GRAFICO
    assert len(ranking.tabla().filas) == 12


def test_en_un_consorcio_el_lote_cuenta_para_cada_participante(
    app, crear_emergencias, cargar_necesidades
) -> None:
    (emergencia,) = _emergencias(crear_emergencias, 1)
    cargar_necesidades(emergencia, (10, 10), ong=A, consorcio=(B,))

    lotes = {fila.nombre: fila.lotes_adjudicados for fila in _seccion(app).ranking.filas}

    assert lotes == {A: 1, B: 1}


def test_ca02_y_ca03_tiempo_medio_de_ejecucion(
    app, crear_emergencias, cargar_necesidades, finalizar_actividad
) -> None:
    """A tardo 4 y 6 dias en dos emergencias: 5,0. C no finalizo nada: "—"."""
    primera, segunda = _emergencias(crear_emergencias, 2)
    oferta_1 = cargar_necesidades(primera, (10, 10), ong=A, adjudicada_en=ADJUDICADA_EN)
    oferta_2 = cargar_necesidades(segunda, (10, 10), ong=A, adjudicada_en=ADJUDICADA_EN)
    oferta_c = cargar_necesidades(segunda, (10, 10), ong=C, adjudicada_en=ADJUDICADA_EN)
    finalizar_actividad(oferta_1, A, ADJUDICADA_EN + timedelta(days=4))
    finalizar_actividad(oferta_2, A, ADJUDICADA_EN + timedelta(days=6))
    finalizar_actividad(oferta_c, C, None)

    filas = {fila.nombre: fila for fila in _seccion(app).ranking.filas}

    assert filas[A].tiempo_medio_de_ejecucion == Decimal("5.0")
    assert filas[A].tiempo_como_texto == "5,0 días"
    assert filas[C].tiempo_medio_de_ejecucion is None
    assert filas[C].tiempo_como_texto == "—"
    assert filas[C].lotes_adjudicados == 1


def test_ca04_orden_por_tiempo_con_los_vacios_al_final(
    app, crear_emergencias, cargar_necesidades, finalizar_actividad
) -> None:
    (emergencia,) = _emergencias(crear_emergencias, 1)
    oferta_a = cargar_necesidades(emergencia, (10, 10), ong=A, adjudicada_en=ADJUDICADA_EN)
    oferta_b = cargar_necesidades(emergencia, (10, 10), ong=B, adjudicada_en=ADJUDICADA_EN)
    cargar_necesidades(emergencia, (10, 10), ong=C, adjudicada_en=ADJUDICADA_EN)
    finalizar_actividad(oferta_a, A, ADJUDICADA_EN + timedelta(days=5))
    finalizar_actividad(oferta_b, B, ADJUDICADA_EN + timedelta(days=2))

    ranking = _seccion(app, OrdenDelRanking.tiempo).ranking

    assert [fila.nombre for fila in ranking.filas] == [B, A, C]
    assert [fila[1] for fila in ranking.tabla().filas] == [B, A, C]
