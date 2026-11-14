"""Servicios del panel de auditoria: secciones "Resumen" y "Emergencias".

Cada metrica sale de la capa de servicios del modulo al que pertenece el dato: este modulo
compone los resultados y nunca importa modelos ni consulta tablas ajenas
(docs/arquitectura/componentes.md seccion 5, reglas 3 y 4).

Las demas secciones viven cada una en su modulo (`recursos`, `red_de_ongs`, `respuesta`,
`proceso`) con la misma forma: una funcion `obtener_seccion_de_*(periodo, **filtros)` que
devuelve un resultado con `a_diccionario()` para JSON y una `tabla()` por indicador para la
exportacion. `secciones.py` las reune.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.core.interfaz.plantillas import etiqueta_estado_emergencia, etiqueta_gravedad
from app.modulos.adjudicaciones import servicios as servicios_de_adjudicaciones
from app.modulos.adjudicaciones.servicios import UnidadesDeEmergencia
from app.modulos.emergencias import servicios as servicios_de_emergencias
from app.modulos.emergencias.modelos import EstadoEmergencia, NivelGravedad
from app.modulos.indicadores.cobertura import (
    TipoDeCobertura,
    clasificar_cobertura,
    porcentaje_cubierto,
    porcentajes_que_suman_100,
)
from app.modulos.indicadores.exportacion import TablaExportable
from app.modulos.indicadores.periodo import Periodo


@dataclass(frozen=True, slots=True)
class ResumenDeActividad:
    """Las cuatro cifras de la cabecera del panel, sobre las emergencias del periodo."""

    emergencias_registradas: int
    # En curso: ni finalizadas ni canceladas.
    emergencias_activas: int
    emergencias_finalizadas: int
    ongs_con_adjudicacion: int

    def a_diccionario(self) -> dict[str, int]:
        return asdict(self)

    def tabla(self) -> TablaExportable:
        """Una fila por cifra: indicador y valor."""
        return TablaExportable(
            columnas=("indicador", "valor"),
            filas=(
                ("Emergencias registradas", self.emergencias_registradas),
                ("Emergencias activas", self.emergencias_activas),
                ("Emergencias finalizadas", self.emergencias_finalizadas),
                ("ONGs con adjudicación", self.ongs_con_adjudicacion),
            ),
        )


def obtener_resumen_de_actividad(periodo: Periodo) -> ResumenDeActividad:
    desde, hasta = periodo.limites_utc()
    conteo = servicios_de_emergencias.contar_emergencias_registradas(desde=desde, hasta=hasta)
    emergencias_del_periodo = servicios_de_emergencias.consultar_ids_de_emergencias_registradas(
        desde=desde, hasta=hasta
    )
    return ResumenDeActividad(
        emergencias_registradas=conteo.registradas,
        emergencias_activas=conteo.en_curso,
        emergencias_finalizadas=conteo.finalizadas,
        ongs_con_adjudicacion=servicios_de_adjudicaciones.contar_ongs_con_adjudicacion(
            emergencia_ids=emergencias_del_periodo
        ),
    )


# --- Seccion "Emergencias" -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CantidadPorEstado:
    estado: EstadoEmergencia
    cantidad: int

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "estado": self.estado.value,
            "etiqueta": etiqueta_estado_emergencia(self.estado),
            "cantidad": self.cantidad,
        }


@dataclass(frozen=True, slots=True)
class PorcionDeCobertura:
    """Una porcion de la torta: cuantas emergencias y que porcentaje de las evaluadas son."""

    cantidad: int
    porcentaje: int

    def a_diccionario(self) -> dict[str, int]:
        return {"cantidad": self.cantidad, "porcentaje": self.porcentaje}


@dataclass(frozen=True, slots=True)
class EmergenciaConFaltantes:
    """Una emergencia que se cerro sin cubrir todo lo que pidio."""

    id: int
    titulo: str
    gravedad: NivelGravedad
    porcentaje: int

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "titulo": self.titulo,
            "gravedad": self.gravedad.value,
            "gravedad_etiqueta": etiqueta_gravedad(self.gravedad),
            "porcentaje": self.porcentaje,
        }


@dataclass(frozen=True, slots=True)
class CoberturaDeFinalizadas:
    """Cobertura de las emergencias finalizadas.

    `sin_necesidades` son las finalizadas que nunca cargaron lotes: no tienen cobertura y quedan
    fuera de la torta. `con_faltantes` lista las parciales de peor a mejor cobertura.
    """

    finalizadas: int
    total: PorcionDeCobertura
    parcial: PorcionDeCobertura
    sin_necesidades: int
    con_faltantes: tuple[EmergenciaConFaltantes, ...]

    @property
    def evaluadas(self) -> int:
        return self.total.cantidad + self.parcial.cantidad

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "finalizadas": self.finalizadas,
            "evaluadas": self.evaluadas,
            "sin_necesidades": self.sin_necesidades,
            "total": self.total.a_diccionario(),
            "parcial": self.parcial.a_diccionario(),
            "con_faltantes": [emergencia.a_diccionario() for emergencia in self.con_faltantes],
        }


@dataclass(frozen=True, slots=True)
class SeccionDeEmergencias:
    """Lo que muestra la seccion "Emergencias" del panel, para un periodo y una gravedad."""

    gravedad: NivelGravedad | None
    por_estado: tuple[CantidadPorEstado, ...]
    cobertura: CoberturaDeFinalizadas

    @property
    def registradas(self) -> int:
        return sum(fila.cantidad for fila in self.por_estado)

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "filtros": {"gravedad": self.gravedad.value if self.gravedad else None},
            "registradas": self.registradas,
            "por_estado": [fila.a_diccionario() for fila in self.por_estado],
            "cobertura": self.cobertura.a_diccionario(),
        }

    def tabla_por_estado(self) -> TablaExportable:
        """Una fila por estado, como las barras del grafico. Sin emergencias, vacia."""
        return TablaExportable(
            columnas=("estado", "emergencias"),
            filas=tuple(
                (etiqueta_estado_emergencia(fila.estado), fila.cantidad) for fila in self.por_estado
            )
            if self.registradas
            else (),
        )

    def tabla_de_cobertura(self) -> TablaExportable:
        """Las dos porciones de la torta de cobertura. Sin finalizadas evaluadas, vacia."""
        cobertura = self.cobertura
        return TablaExportable(
            columnas=("cobertura", "emergencias", "porcentaje"),
            filas=(
                ("Cobertura total", cobertura.total.cantidad, cobertura.total.porcentaje),
                ("Cobertura parcial", cobertura.parcial.cantidad, cobertura.parcial.porcentaje),
            )
            if cobertura.evaluadas
            else (),
        )


def obtener_seccion_de_emergencias(
    periodo: Periodo, gravedad: NivelGravedad | None = None
) -> SeccionDeEmergencias:
    """Emergencias por estado y cobertura de las finalizadas, registradas en el periodo.

    `gravedad`, si se indica, acota las dos metricas.
    """
    desde, hasta = periodo.limites_utc()
    por_estado = servicios_de_emergencias.contar_emergencias_por_estado(
        desde=desde, hasta=hasta, gravedad=gravedad
    )
    finalizadas = servicios_de_emergencias.consultar_ids_de_emergencias_registradas(
        desde=desde, hasta=hasta, gravedad=gravedad, estado=EstadoEmergencia.finalizada
    )
    return SeccionDeEmergencias(
        gravedad=gravedad,
        por_estado=tuple(CantidadPorEstado(estado, n) for estado, n in por_estado.items()),
        cobertura=_cobertura_de_finalizadas(
            finalizadas=por_estado[EstadoEmergencia.finalizada],
            unidades=servicios_de_adjudicaciones.consultar_unidades_por_emergencia(
                emergencia_ids=finalizadas
            ),
        ),
    )


def _cobertura_de_finalizadas(
    *, finalizadas: int, unidades: list[UnidadesDeEmergencia]
) -> CoberturaDeFinalizadas:
    por_tipo: dict[TipoDeCobertura, list[UnidadesDeEmergencia]] = {t: [] for t in TipoDeCobertura}
    for unidades_de_emergencia in unidades:
        tipo = clasificar_cobertura(unidades_de_emergencia)
        if tipo is not None:
            por_tipo[tipo].append(unidades_de_emergencia)

    totales, parciales = por_tipo[TipoDeCobertura.total], por_tipo[TipoDeCobertura.parcial]
    porcentaje_total, porcentaje_parcial = porcentajes_que_suman_100([len(totales), len(parciales)])
    return CoberturaDeFinalizadas(
        finalizadas=finalizadas,
        total=PorcionDeCobertura(len(totales), porcentaje_total),
        parcial=PorcionDeCobertura(len(parciales), porcentaje_parcial),
        sin_necesidades=finalizadas - len(totales) - len(parciales),
        con_faltantes=_con_faltantes(parciales),
    )


def _con_faltantes(
    parciales: list[UnidadesDeEmergencia],
) -> tuple[EmergenciaConFaltantes, ...]:
    datos = servicios_de_emergencias.obtener_datos_basicos(u.emergencia_id for u in parciales)
    emergencias = (
        EmergenciaConFaltantes(
            id=u.emergencia_id,
            titulo=datos[u.emergencia_id].titulo,
            gravedad=datos[u.emergencia_id].nivel_gravedad,
            porcentaje=porcentaje_cubierto(u),
        )
        for u in parciales
    )
    return tuple(sorted(emergencias, key=lambda e: (e.porcentaje, e.titulo)))
