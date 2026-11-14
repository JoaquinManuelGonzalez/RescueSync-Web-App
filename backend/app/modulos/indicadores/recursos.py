"""Seccion "Recursos" del panel de auditoria.

- Recursos movilizados: unidades adjudicadas por mes y por rubro.
- Rubros: unidades que piden los lotes de cada rubro frente a la tasa de inhabilitacion del
  Sistema Nacional sobre lo ofertado.

Como todo el panel, se calcula sobre las emergencias registradas en el periodo. Los datos salen
de los servicios de cada modulo; aca solo se agrupan y se arman las tablas y los graficos.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.core.interfaz.plantillas import SIN_DATO, etiqueta_tipo_necesidad
from app.modulos.adjudicaciones import servicios as servicios_de_adjudicaciones
from app.modulos.emergencias import servicios as servicios_de_emergencias
from app.modulos.emergencias.modelos import TipoNecesidad
from app.modulos.indicadores import graficos
from app.modulos.indicadores.exportacion import TablaExportable
from app.modulos.indicadores.periodo import Periodo
from app.modulos.indicadores.series import etiqueta_de_mes, mes_de, mes_iso, meses_contiguos
from app.modulos.indicadores.tiempos import porcentaje_entero
from app.modulos.ofertas import servicios as servicios_de_ofertas

UNIDADES: graficos.Unidad = ("unidad", "unidades")
SIN_OFERTAS_EVALUADAS = "Sin ofertas evaluadas"

# --- Recursos movilizados (por mes y rubro) ---------------------------------------


@dataclass(frozen=True, slots=True)
class RecursosMovilizados:
    """Unidades adjudicadas por mes y rubro.

    `meses` es el eje completo, sin huecos: cubre el periodo y cualquier mes en que se haya
    adjudicado algo de sus emergencias. `rubros` son las series que se muestran, en el orden del
    catalogo: los rubros con alguna unidad o, con el filtro, solo el elegido.
    """

    rubro_filtrado: TipoNecesidad | None
    meses: tuple[date, ...]
    rubros: tuple[TipoNecesidad, ...]
    unidades: dict[tuple[date, TipoNecesidad], int]

    @property
    def total(self) -> int:
        return sum(self.unidades.values())

    def unidades_de(self, mes: date, rubro: TipoNecesidad) -> int:
        return self.unidades.get((mes, rubro), 0)

    @staticmethod
    def tono_de(rubro: TipoNecesidad) -> str:
        """El tono del rubro en los graficos: el mismo en todas las series y leyendas."""
        return graficos.TONO_POR_RUBRO[rubro]

    def total_del_rubro(self, rubro: TipoNecesidad) -> int:
        return sum(self.unidades_de(mes, rubro) for mes in self.meses)

    def total_del_mes(self, mes: date) -> int:
        return sum(self.unidades_de(mes, rubro) for rubro in self.rubros)

    @property
    def rubro_principal(self) -> TipoNecesidad | None:
        """El rubro con mas unidades movilizadas (ante un empate, el primero del catalogo)."""
        if not self.total:
            return None
        return max(self.rubros, key=self.total_del_rubro)

    @property
    def mes_pico(self) -> date | None:
        """El mes con mas unidades movilizadas (ante un empate, el primero)."""
        if not self.total:
            return None
        return max(self.meses, key=self.total_del_mes)

    def grafico(self) -> dict[str, Any]:
        return graficos.barras_apiladas(
            [etiqueta_de_mes(mes) for mes in self.meses],
            [
                graficos.Serie(
                    nombre=etiqueta_tipo_necesidad(rubro),
                    valores=[self.unidades_de(mes, rubro) for mes in self.meses],
                    tono=graficos.TONO_POR_RUBRO[rubro],
                    unidad=UNIDADES,
                )
                for rubro in self.rubros
            ],
        )

    def tabla(self) -> TablaExportable:
        """Una fila por mes y rubro con unidades adjudicadas."""
        return TablaExportable(
            columnas=("mes", "rubro", "unidades"),
            filas=tuple(
                (mes_iso(mes), etiqueta_tipo_necesidad(rubro), self.unidades_de(mes, rubro))
                for mes in self.meses
                for rubro in self.rubros
                if self.unidades_de(mes, rubro)
            ),
        )

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "rubro": self.rubro_filtrado.value if self.rubro_filtrado else None,
            "total": self.total,
            "datos": self.tabla().como_json(),
        }


def _recursos_movilizados(
    periodo: Periodo, emergencia_ids, rubro: TipoNecesidad | None
) -> RecursosMovilizados:
    unidades: dict[tuple[date, TipoNecesidad], int] = defaultdict(int)
    for fila in servicios_de_adjudicaciones.listar_unidades_adjudicadas_por_categoria(
        emergencia_ids=emergencia_ids
    ):
        if rubro is None or fila.categoria == rubro:
            unidades[(mes_de(fila.adjudicada_en), fila.categoria)] += fila.unidades

    meses = meses_contiguos(
        [periodo.desde.replace(day=1), periodo.hasta.replace(day=1), *(m for m, _ in unidades)]
    )
    con_unidades = {categoria for _, categoria in unidades}
    rubros = (rubro,) if rubro else tuple(r for r in TipoNecesidad if r in con_unidades)
    return RecursosMovilizados(
        rubro_filtrado=rubro, meses=tuple(meses), rubros=rubros, unidades=dict(unidades)
    )


# --- Rubros: demanda vs. inhabilitacion -------------------------------------------


@dataclass(frozen=True, slots=True)
class DemandaDeRubro:
    """Lo que pidieron los lotes de un rubro y que parte de lo ofertado no se habilito.

    `tasa_de_inhabilitacion` es un porcentaje entero, o None si ninguna oferta del rubro fue
    evaluada: sin evaluacion no hay tasa, y mostrarla como 0 % diria que todo se habilito.
    """

    rubro: TipoNecesidad
    demandadas: int
    evaluadas: int
    no_habilitadas: int

    @property
    def tasa_de_inhabilitacion(self) -> int | None:
        return porcentaje_entero(self.no_habilitadas, self.evaluadas)

    @property
    def etiqueta(self) -> str:
        return etiqueta_tipo_necesidad(self.rubro)

    @property
    def tasa_como_texto(self) -> str:
        tasa = self.tasa_de_inhabilitacion
        return SIN_DATO if tasa is None else f"{tasa} %"


@dataclass(frozen=True, slots=True)
class RubrosDemandados:
    """Los rubros con demanda, de mayor a menor cantidad de unidades pedidas."""

    filas: tuple[DemandaDeRubro, ...]

    def grafico_de_demanda(self) -> dict[str, Any]:
        """Unidades que piden los lotes de cada rubro, de mayor a menor."""
        return graficos.barras(
            [fila.etiqueta for fila in self.filas],
            [fila.demandadas for fila in self.filas],
            tonos=[graficos.TONO_POR_RUBRO[fila.rubro] for fila in self.filas],
            unidad=UNIDADES,
            horizontal=True,
        )

    def grafico_de_inhabilitacion(self) -> dict[str, Any]:
        """Porcentaje no habilitado de lo ofertado, en el mismo orden que la demanda.

        Va en su propio grafico (y no como una segunda escala del de demanda) porque mide otra
        cosa, en otra unidad. Un rubro sin ofertas evaluadas no tiene barra: dice por que.
        """
        return graficos.barras(
            [fila.etiqueta for fila in self.filas],
            [fila.tasa_de_inhabilitacion for fila in self.filas],
            tonos=[graficos.TONO_POR_RUBRO[fila.rubro] for fila in self.filas],
            unidad=graficos.PORCIENTO,
            detalles=[
                f"{fila.no_habilitadas} de {fila.evaluadas} unidades ofertadas no habilitadas"
                if fila.evaluadas
                else None
                for fila in self.filas
            ],
            horizontal=True,
            maximo=100,
            sin_dato=SIN_OFERTAS_EVALUADAS,
        )

    def tabla(self) -> TablaExportable:
        return TablaExportable(
            columnas=(
                "rubro",
                "unidades_demandadas",
                "unidades_ofertadas_evaluadas",
                "unidades_no_habilitadas",
                "tasa_de_inhabilitacion",
            ),
            filas=tuple(
                (
                    fila.etiqueta,
                    fila.demandadas,
                    fila.evaluadas,
                    fila.no_habilitadas,
                    fila.tasa_de_inhabilitacion,
                )
                for fila in self.filas
            ),
        )

    def a_diccionario(self) -> dict[str, Any]:
        return {"datos": self.tabla().como_json()}


def _rubros_demandados(emergencia_ids) -> RubrosDemandados:
    demandas = servicios_de_ofertas.listar_demanda_e_inhabilitacion_por_categoria(
        emergencia_ids=emergencia_ids
    )
    orden_del_catalogo = {rubro: indice for indice, rubro in enumerate(TipoNecesidad)}
    filas = sorted(
        (
            DemandaDeRubro(
                rubro=demanda.categoria,
                demandadas=demanda.demandadas,
                evaluadas=demanda.evaluadas,
                no_habilitadas=demanda.no_habilitadas,
            )
            for demanda in demandas
        ),
        key=lambda fila: (-fila.demandadas, orden_del_catalogo[fila.rubro]),
    )
    return RubrosDemandados(filas=tuple(filas))


# --- La seccion ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SeccionDeRecursos:
    movilizados: RecursosMovilizados
    rubros: RubrosDemandados

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "filtros": {
                "rubro": rubro.value if (rubro := self.movilizados.rubro_filtrado) else None
            },
            "recursos_movilizados": self.movilizados.a_diccionario(),
            "rubros": self.rubros.a_diccionario(),
        }


def obtener_seccion_de_recursos(
    periodo: Periodo, rubro: TipoNecesidad | None = None
) -> SeccionDeRecursos:
    """Recursos movilizados y demanda por rubro de las emergencias registradas en el periodo.

    `rubro`, si se indica, acota solo los recursos movilizados (es el filtro de ese grafico).
    """
    desde, hasta = periodo.limites_utc()
    emergencia_ids = servicios_de_emergencias.consultar_ids_de_emergencias_registradas(
        desde=desde, hasta=hasta
    )
    return SeccionDeRecursos(
        movilizados=_recursos_movilizados(periodo, emergencia_ids, rubro),
        rubros=_rubros_demandados(emergencia_ids),
    )
