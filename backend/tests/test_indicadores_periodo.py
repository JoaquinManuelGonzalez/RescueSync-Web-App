"""El periodo del panel de auditoria: dias de calendario de Argentina traducidos a UTC."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.modulos.indicadores.periodo import Periodo, atajos_de_periodo


def test_los_ultimos_30_dias_terminan_hoy_y_lo_incluyen() -> None:
    periodo = Periodo.ultimos_dias(30, hoy=date(2026, 11, 2))

    assert periodo == Periodo(desde=date(2026, 10, 4), hasta=date(2026, 11, 2))
    assert periodo.dias == 30


def test_los_limites_se_calculan_en_hora_argentina_con_el_fin_excluido() -> None:
    """01/10 00:00 en Argentina son las 03:00 UTC; el fin es la medianoche siguiente a `hasta`."""
    inicio, fin = Periodo(desde=date(2026, 10, 1), hasta=date(2026, 10, 31)).limites_utc()

    assert inicio == datetime(2026, 10, 1, 3, 0, tzinfo=UTC)
    assert fin == datetime(2026, 11, 1, 3, 0, tzinfo=UTC)


def test_un_periodo_de_un_solo_dia_es_valido() -> None:
    assert Periodo(desde=date(2026, 10, 1), hasta=date(2026, 10, 1)).dias == 1


def test_un_periodo_no_puede_terminar_antes_de_empezar() -> None:
    with pytest.raises(ValueError):
        Periodo(desde=date(2026, 10, 31), hasta=date(2026, 10, 1))


def test_los_atajos_de_mes_cruzan_bien_el_cambio_de_anio() -> None:
    atajos = {atajo.etiqueta: atajo.periodo for atajo in atajos_de_periodo(date(2027, 1, 15))}

    assert atajos["Este mes"] == Periodo(desde=date(2027, 1, 1), hasta=date(2027, 1, 15))
    assert atajos["Mes anterior"] == Periodo(desde=date(2026, 12, 1), hasta=date(2026, 12, 31))
    assert atajos["Últimos 7 días"] == Periodo(desde=date(2027, 1, 9), hasta=date(2027, 1, 15))
