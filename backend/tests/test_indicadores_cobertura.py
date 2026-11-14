"""Reglas de la cobertura de una emergencia: clasificacion y porcentajes, sin base de datos."""

from __future__ import annotations

import pytest

from app.modulos.adjudicaciones.servicios import UnidadesDeEmergencia
from app.modulos.indicadores.cobertura import (
    TipoDeCobertura,
    clasificar_cobertura,
    porcentaje_cubierto,
    porcentajes_que_suman_100,
)


def _unidades(requeridas: int, adjudicadas: int) -> UnidadesDeEmergencia:
    return UnidadesDeEmergencia(emergencia_id=1, requeridas=requeridas, adjudicadas=adjudicadas)


@pytest.mark.parametrize(
    ("requeridas", "adjudicadas", "esperado"),
    [
        (100, 100, TipoDeCobertura.total),
        (100, 60, TipoDeCobertura.parcial),
        (100, 0, TipoDeCobertura.parcial),
        (100, 99, TipoDeCobertura.parcial),
        (0, 0, None),  # sin necesidades: no hay cobertura que medir
    ],
)
def test_la_cobertura_es_total_solo_al_cien_por_ciento(requeridas, adjudicadas, esperado) -> None:
    assert clasificar_cobertura(_unidades(requeridas, adjudicadas)) is esperado


def test_el_porcentaje_cubierto_se_redondea_hacia_abajo() -> None:
    """Una emergencia al 99,6 % es parcial: no puede mostrarse como 100 %."""
    assert porcentaje_cubierto(_unidades(1000, 996)) == 99
    assert porcentaje_cubierto(_unidades(5, 3)) == 60
    assert porcentaje_cubierto(_unidades(0, 0)) == 0


@pytest.mark.parametrize(
    ("cantidades", "esperado"),
    [
        ([4, 1], [80, 20]),  # CA-02
        ([1, 7], [13, 87]),  # 12,5 y 87,5: sin el mayor resto sumarian 101
        ([1, 1, 1], [34, 33, 33]),
        ([0, 3], [0, 100]),
        ([0, 0], [0, 0]),
    ],
)
def test_los_porcentajes_siempre_suman_cien(cantidades, esperado) -> None:
    resultado = porcentajes_que_suman_100(cantidades)
    assert resultado == esperado
    if sum(cantidades):
        assert sum(resultado) == 100
