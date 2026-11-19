"""Duraciones, promedios y porcentajes de los indicadores, sin base de datos.

Las duraciones son `timedelta`, exactas (al microsegundo) hasta que se promedian: el promedio se
redondea al segundo. Los porcentajes se informan como enteros ("50 %"). Los dos redondeos son
"mitad hacia arriba", con `Decimal`, que es como se redondea a mano: `round()` de Python redondea
al par (2,5 quedaria en 2).

Una duracion se escribe con dias, horas, minutos y segundos, omitiendo los que valen cero:
"1 d 4 h 12 min 5 s", "15 min 32 s", "2 d 5 min". Entre el numero y su unidad va un espacio duro,
para que al partirse el renglon (una cifra destacada, una tarjeta angosta) "33 min" no quede
separado. Sobre las barras de un grafico, donde no hay lugar, va abreviada a las dos unidades
mayores ("1 d 4 h"); el tooltip y la tabla la muestran completa.

En las exportaciones una duracion ocupa dos columnas: los segundos exactos, para calcular en una
planilla, y el texto, con espacios comunes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.core.interfaz.plantillas import SIN_DATO

_MICROSEGUNDOS_POR_SEGUNDO = 1_000_000
_UN_MICROSEGUNDO = timedelta(microseconds=1)
_ENTERO = Decimal("1")
_ESPACIO_DURO = "\u00a0"


@dataclass(frozen=True, slots=True)
class UnidadDeTiempo:
    """Una unidad en que se escribe una duracion ("4 h") o se lee el eje de un grafico."""

    abreviatura: str
    tamano: timedelta

    @property
    def segundos(self) -> int:
        return self.tamano // timedelta(seconds=1)


# De la mayor a la menor. Los dias son la mayor: 45 dias se escriben "45 d", no en semanas.
UNIDADES_DE_TIEMPO: tuple[UnidadDeTiempo, ...] = (
    UnidadDeTiempo("d", timedelta(days=1)),
    UnidadDeTiempo("h", timedelta(hours=1)),
    UnidadDeTiempo("min", timedelta(minutes=1)),
    UnidadDeTiempo("s", timedelta(seconds=1)),
)


def en_utc(fecha: datetime) -> datetime:
    """La fecha en UTC. Una fecha sin zona se toma como UTC, que es como se guardan.

    PostgreSQL devuelve las fechas con zona; el SQLite de los tests, sin ella.
    """
    if fecha.tzinfo is None:
        return fecha.replace(tzinfo=UTC)
    return fecha.astimezone(UTC)


def duracion_entre(inicio: datetime, fin: datetime) -> timedelta:
    """El tiempo transcurrido entre dos instantes, exacto (sin redondear) y nunca negativo.

    Un fin anterior al inicio solo puede salir de un dato inconsistente (por ejemplo, una fecha
    aproximada por una migracion): cuenta como 0 en vez de restar en los promedios.
    """
    return max(en_utc(fin) - en_utc(inicio), timedelta(0))


def _entero_mitad_hacia_arriba(valor: Decimal) -> int:
    return int(valor.quantize(_ENTERO, rounding=ROUND_HALF_UP))


def _microsegundos(duracion: timedelta) -> Decimal:
    return Decimal(duracion // _UN_MICROSEGUNDO)


def en_segundos(duracion: timedelta) -> int:
    """Los segundos enteros de una duracion, redondeados mitad hacia arriba."""
    return _entero_mitad_hacia_arriba(_microsegundos(duracion) / _MICROSEGUNDOS_POR_SEGUNDO)


def promedio_de_duraciones(duraciones: Iterable[timedelta]) -> timedelta | None:
    """El promedio redondeado al segundo, o None si no hay duraciones (sin dato, que no es 0)."""
    lista = list(duraciones)
    if not lista:
        return None
    total = _microsegundos(sum(lista, timedelta(0)))
    return timedelta(
        seconds=_entero_mitad_hacia_arriba(total / _MICROSEGUNDOS_POR_SEGUNDO / len(lista))
    )


def _como_texto(segundos: int, espacio: str) -> str:
    """Las unidades que no valen cero, de la mayor a la menor; "0 s" si no queda ninguna."""
    partes = []
    for unidad in UNIDADES_DE_TIEMPO:
        cantidad, segundos = divmod(segundos, unidad.segundos)
        if cantidad:
            partes.append(f"{cantidad}{espacio}{unidad.abreviatura}")
    return " ".join(partes) or f"0{espacio}s"


def duracion_como_texto(duracion: timedelta | None) -> str:
    """Una duracion completa, como se lee en pantalla: "1 d 4 h 12 min 5 s", o "—" sin dato."""
    if duracion is None:
        return SIN_DATO
    return _como_texto(en_segundos(duracion), _ESPACIO_DURO)


def duracion_abreviada(duracion: timedelta) -> str:
    """La unidad mayor y la siguiente, redondeando a esa segunda: "1 d 4 h", "15 min 32 s".

    Es para escribir sobre las barras de un grafico, donde la completa no entra (el tooltip la
    muestra). Redondea en vez de truncar: 23 h 59 min 40 s se escribe "1 d", no "23 h 59 min".
    """
    segundos = en_segundos(duracion)
    mayor = next(
        (indice for indice, unidad in enumerate(UNIDADES_DE_TIEMPO) if segundos >= unidad.segundos),
        len(UNIDADES_DE_TIEMPO) - 1,
    )
    if mayor + 1 < len(UNIDADES_DE_TIEMPO):
        paso = UNIDADES_DE_TIEMPO[mayor + 1].segundos
        segundos = _entero_mitad_hacia_arriba(Decimal(segundos) / paso) * paso
    return _como_texto(segundos, _ESPACIO_DURO)


def columnas_de_duracion(duracion: timedelta | None) -> tuple[int | None, str | None]:
    """(segundos, texto) de una duracion: las dos columnas con que se exporta.

    Los segundos son exactos, para calcular en una planilla; el texto lleva espacios comunes,
    para que se pueda buscar o filtrar. Sin dato, las dos quedan vacias.
    """
    if duracion is None:
        return None, None
    segundos = en_segundos(duracion)
    return segundos, _como_texto(segundos, " ")


def porcentaje_entero(parte: int, total: int) -> int | None:
    """`parte` sobre `total` como porcentaje entero, o None si `total` es 0 (no hay tasa)."""
    if total <= 0:
        return None
    return _entero_mitad_hacia_arriba(Decimal(parte) * 100 / Decimal(total))
