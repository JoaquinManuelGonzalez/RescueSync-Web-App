"""Periodo de analisis del panel de auditoria.

Todo lo que muestra el panel (tarjetas, graficos, exportaciones) se calcula sobre las
emergencias **registradas** dentro de un mismo periodo. El periodo se expresa en dias de
calendario de Argentina, que es como lo elige la persona, y se traduce a UTC recien al consultar,
que es como se guardan las fechas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from app.core.interfaz.plantillas import ZONA_HORARIA_DE_LA_INTERFAZ

DIAS_DEL_PERIODO_POR_DEFECTO = 30


def hoy_en_la_interfaz() -> date:
    """La fecha de hoy en Argentina. A las 22 h del 31/10 en Argentina, en UTC ya es 01/11."""
    return datetime.now(ZONA_HORARIA_DE_LA_INTERFAZ).date()


@dataclass(frozen=True, slots=True)
class Periodo:
    """Rango de fechas de calendario con ambos extremos incluidos."""

    desde: date
    hasta: date

    def __post_init__(self) -> None:
        if self.desde > self.hasta:
            raise ValueError("El inicio del período no puede ser posterior a su fin.")

    @classmethod
    def ultimos_dias(cls, dias: int, *, hoy: date) -> Periodo:
        """Los ultimos `dias` dias contando hoy: los ultimos 30 van de hoy-29 a hoy."""
        return cls(desde=hoy - timedelta(days=dias - 1), hasta=hoy)

    @property
    def dias(self) -> int:
        return (self.hasta - self.desde).days + 1

    def limites_utc(self) -> tuple[datetime, datetime]:
        """El periodo como rango semiabierto `[inicio, fin)` en UTC.

        El fin es la medianoche del dia siguiente a `hasta`: asi entra una emergencia registrada
        a las 23:59:59.999 del ultimo dia y no hace falta redondear nada.
        """
        inicio = datetime.combine(self.desde, time.min, tzinfo=ZONA_HORARIA_DE_LA_INTERFAZ)
        fin = datetime.combine(
            self.hasta + timedelta(days=1), time.min, tzinfo=ZONA_HORARIA_DE_LA_INTERFAZ
        )
        return inicio.astimezone(UTC), fin.astimezone(UTC)

    def a_diccionario(self) -> dict[str, str | int]:
        return {"desde": self.desde.isoformat(), "hasta": self.hasta.isoformat(), "dias": self.dias}


@dataclass(frozen=True, slots=True)
class AtajoDePeriodo:
    """Un periodo de uso frecuente, que la interfaz ofrece a un clic."""

    etiqueta: str
    periodo: Periodo


def atajos_de_periodo(hoy: date) -> list[AtajoDePeriodo]:
    inicio_del_mes = hoy.replace(day=1)
    fin_del_mes_anterior = inicio_del_mes - timedelta(days=1)
    return [
        AtajoDePeriodo("Últimos 7 días", Periodo.ultimos_dias(7, hoy=hoy)),
        AtajoDePeriodo("Últimos 30 días", Periodo.ultimos_dias(30, hoy=hoy)),
        AtajoDePeriodo("Últimos 90 días", Periodo.ultimos_dias(90, hoy=hoy)),
        AtajoDePeriodo("Este mes", Periodo(desde=inicio_del_mes, hasta=hoy)),
        AtajoDePeriodo(
            "Mes anterior",
            Periodo(desde=fin_del_mes_anterior.replace(day=1), hasta=fin_del_mes_anterior),
        ),
    ]
