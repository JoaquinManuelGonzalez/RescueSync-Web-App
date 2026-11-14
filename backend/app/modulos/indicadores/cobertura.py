"""Reglas de la cobertura de una emergencia, sin base de datos.

Cobertura = unidades adjudicadas / unidades requeridas, sumando todos los lotes. Es total cuando
llega al 100 % y parcial cuando queda por debajo. Una emergencia que no pidio nada no tiene
cobertura: no es ni total ni parcial.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence

from app.modulos.adjudicaciones.servicios import UnidadesDeEmergencia


class TipoDeCobertura(enum.Enum):
    total = "total"
    parcial = "parcial"


def clasificar_cobertura(unidades: UnidadesDeEmergencia) -> TipoDeCobertura | None:
    """Total, parcial, o None si la emergencia no tiene unidades requeridas."""
    if unidades.requeridas <= 0:
        return None
    if unidades.adjudicadas >= unidades.requeridas:
        return TipoDeCobertura.total
    return TipoDeCobertura.parcial


def porcentaje_cubierto(unidades: UnidadesDeEmergencia) -> int:
    """Porcentaje entero cubierto, redondeado hacia abajo.

    Hacia abajo y no al mas cercano: una emergencia al 99,6 % es parcial y no puede mostrarse
    como "100 %".
    """
    if unidades.requeridas <= 0:
        return 0
    return min(100, unidades.adjudicadas * 100 // unidades.requeridas)


def porcentajes_que_suman_100(cantidades: Sequence[int]) -> list[int]:
    """Porcentajes enteros de cada cantidad sobre el total, que siempre suman 100.

    Usa el metodo del mayor resto: cada parte recibe la parte entera de su porcentaje y los
    puntos que faltan para llegar a 100 van a las de mayor parte decimal. Asi una torta de
    1 y 7 muestra 13 % y 87 %, y no 13 % y 88 %. Sin total, todo es 0.
    """
    total = sum(cantidades)
    if total == 0:
        return [0] * len(cantidades)

    enteros = [cantidad * 100 // total for cantidad in cantidades]
    restos = [cantidad * 100 % total for cantidad in cantidades]
    faltantes = 100 - sum(enteros)
    # Ante restos iguales gana la que aparece primero, para que el resultado sea estable.
    por_mayor_resto = sorted(range(len(cantidades)), key=lambda i: (-restos[i], i))
    for indice in por_mayor_resto[:faltantes]:
        enteros[indice] += 1
    return enteros
