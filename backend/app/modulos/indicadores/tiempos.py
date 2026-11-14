"""Duraciones, promedios y porcentajes de los indicadores, sin base de datos.

Los tiempos del panel se informan en dias con un decimal ("5,0 días") y los porcentajes como
enteros ("50 %"). Se calculan con `Decimal` y redondeo "mitad hacia arriba", que es como se
redondea a mano: con `round()` de Python, 7,25 dias quedaria en 7,2 (redondeo bancario sobre un
float que en realidad vale 7,2499...) y la HU espera 7,3.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.core.interfaz.plantillas import SIN_DATO

_MICROSEGUNDOS_POR_DIA = Decimal(86_400 * 1_000_000)
_UN_DECIMAL = Decimal("0.1")
_ENTERO = Decimal("1")


def en_utc(fecha: datetime) -> datetime:
    """La fecha en UTC. Una fecha sin zona se toma como UTC, que es como se guardan.

    PostgreSQL devuelve las fechas con zona; el SQLite de los tests, sin ella.
    """
    if fecha.tzinfo is None:
        return fecha.replace(tzinfo=UTC)
    return fecha.astimezone(UTC)


def duracion_en_dias(inicio: datetime, fin: datetime) -> Decimal:
    """Dias transcurridos entre dos instantes, exactos (sin redondear) y nunca negativos.

    Un fin anterior al inicio solo puede salir de un dato inconsistente (por ejemplo, una fecha
    aproximada por una migracion): cuenta como 0 en vez de restar en los promedios.
    """
    delta = en_utc(fin) - en_utc(inicio)
    if delta < timedelta(0):
        return Decimal(0)
    return Decimal(delta // timedelta(microseconds=1)) / _MICROSEGUNDOS_POR_DIA


def redondear_a_un_decimal(valor: Decimal) -> Decimal:
    return valor.quantize(_UN_DECIMAL, rounding=ROUND_HALF_UP)


def promedio_en_dias(duraciones: Iterable[Decimal]) -> Decimal | None:
    """El promedio con un decimal, o None si no hay duraciones (sin dato, que no es 0 dias)."""
    lista = list(duraciones)
    if not lista:
        return None
    return redondear_a_un_decimal(sum(lista, Decimal(0)) / len(lista))


def porcentaje_entero(parte: int, total: int) -> int | None:
    """`parte` sobre `total` como porcentaje entero, o None si `total` es 0 (no hay tasa)."""
    if total <= 0:
        return None
    return int((Decimal(parte) * 100 / Decimal(total)).quantize(_ENTERO, rounding=ROUND_HALF_UP))


def decimal_como_texto(valor: Decimal) -> str:
    """Un decimal con coma, como se escribe en Argentina: 5,0."""
    return f"{valor}".replace(".", ",")


def dias_como_texto(dias: Decimal | None) -> str:
    """Una duracion como texto: "5,0 días", o "—" si no hay dato."""
    if dias is None:
        return SIN_DATO
    return f"{decimal_como_texto(dias)} {'día' if dias == 1 else 'días'}"
