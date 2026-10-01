"""Pruebas unitarias de la validación de cantidades de los lotes de necesidad."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errores import SolicitudInvalida
from app.modulos.emergencias.lotes.servicios import _parsear_cantidad


@pytest.mark.parametrize("valor", ["10", " 10 ", 10, "10.0", Decimal("10.00")])
def test_parsear_cantidad_devuelve_un_entero(valor):
    cantidad = _parsear_cantidad(valor)
    assert cantidad == 10
    assert isinstance(cantidad, int)


@pytest.mark.parametrize("valor", ["2.5", 0.5, "abc", "NaN", "Infinity", "0", "-3", "", None])
def test_parsear_cantidad_rechaza_valores_que_no_son_enteros_positivos(valor):
    with pytest.raises(SolicitudInvalida):
        _parsear_cantidad(valor)
