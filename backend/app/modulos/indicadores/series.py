"""Series mensuales de los indicadores, sin base de datos.

Un mes se identifica por la fecha de su primer dia. El mes de un instante se toma en la hora de
Argentina, como lee el reporte una persona: una adjudicacion a las 22 h del 31/10 en Argentina
ya es 01/11 en UTC, pero es de octubre.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime

from app.core.interfaz.plantillas import ZONA_HORARIA_DE_LA_INTERFAZ
from app.modulos.indicadores.tiempos import en_utc

_NOMBRES_DE_MES = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)


def mes_de(instante: datetime) -> date:
    """El mes (su primer dia) de un instante, en la hora de Argentina."""
    return en_utc(instante).astimezone(ZONA_HORARIA_DE_LA_INTERFAZ).date().replace(day=1)


def _mes_siguiente(mes: date) -> date:
    return date(mes.year + mes.month // 12, mes.month % 12 + 1, 1)


def meses_contiguos(meses: Iterable[date]) -> list[date]:
    """Todos los meses entre el primero y el ultimo de `meses`, sin huecos y en orden.

    Un eje de tiempo con un mes faltante esconde justo lo que importa: que ese mes no hubo nada.
    """
    conocidos = sorted({mes.replace(day=1) for mes in meses})
    if not conocidos:
        return []
    resultado = [conocidos[0]]
    while resultado[-1] < conocidos[-1]:
        resultado.append(_mes_siguiente(resultado[-1]))
    return resultado


def etiqueta_de_mes(mes: date) -> str:
    """Como se nombra un mes en un grafico: "sep 2026"."""
    return f"{_NOMBRES_DE_MES[mes.month - 1]} {mes.year}"


def mes_iso(mes: date) -> str:
    """El mes en formato ISO 8601 ("2026-09"), para las exportaciones."""
    return f"{mes.year:04d}-{mes.month:02d}"
