"""Seccion "Convocatorias" del panel de auditoria: emergencias que no se cubrieron en la primera
convocatoria y que decidio el Centro Coordinador en cada caso.

Ante una cobertura insuficiente el proceso tiene dos ramas, y son las dos barras del grafico:

- Reapertura ("Reiniciar convocatoria"): la convocatoria queda como historial y se publica otra.
- Continuar con parcial ("Enviar ofertas igualmente"): se seleccionan las ofertas que hay.

Cada decision suma en su barra: una emergencia reabierta dos veces cuenta dos veces en
"Reapertura" y una sola vez entre las emergencias que necesitaron una decision. Las coberturas
insuficientes que todavia esperan decision no son una barra (no hubo decision): se informan
aparte, para que los totales cierren.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.core.interfaz.plantillas import etiqueta_gravedad
from app.modulos.convocatorias import servicios as servicios_de_convocatorias
from app.modulos.convocatorias.servicios import HistorialDeConvocatorias
from app.modulos.emergencias import servicios as servicios_de_emergencias
from app.modulos.emergencias.modelos import NivelGravedad
from app.modulos.indicadores import graficos
from app.modulos.indicadores.exportacion import TablaExportable
from app.modulos.indicadores.formularios import ETIQUETA_POR_DECISION, DecisionDeCobertura
from app.modulos.indicadores.periodo import Periodo
from app.modulos.indicadores.tiempos import porcentaje_entero

DECISIONES: graficos.Unidad = ("decisión", "decisiones")

TONO_POR_DECISION = {
    DecisionDeCobertura.reapertura: "advertencia",
    DecisionDeCobertura.continuar_parcial: "info",
}


@dataclass(frozen=True, slots=True)
class EmergenciaConDecision:
    """Una emergencia del periodo que tuvo al menos una cobertura insuficiente."""

    emergencia_id: uuid.UUID
    titulo: str
    gravedad: NivelGravedad
    convocatorias_publicadas: int
    reaperturas: int
    continuaciones: int
    pendientes: int

    def tuvo(self, decision: DecisionDeCobertura) -> bool:
        if decision is DecisionDeCobertura.reapertura:
            return self.reaperturas > 0
        return self.continuaciones > 0


@dataclass(frozen=True, slots=True)
class SeccionDeConvocatorias:
    """Decisiones ante cobertura insuficiente de las emergencias registradas en el periodo.

    `decision` es el filtro del detalle: que emergencias lista (None, todas las afectadas).
    """

    decision: DecisionDeCobertura | None
    emergencias_con_convocatoria: int
    afectadas: tuple[EmergenciaConDecision, ...]

    @property
    def reaperturas(self) -> int:
        return sum(emergencia.reaperturas for emergencia in self.afectadas)

    @property
    def continuaciones(self) -> int:
        return sum(emergencia.continuaciones for emergencia in self.afectadas)

    @property
    def esperan_decision(self) -> int:
        """Emergencias con una cobertura insuficiente todavia sin resolver."""
        return sum(emergencia.pendientes > 0 for emergencia in self.afectadas)

    @property
    def porcentaje_afectadas(self) -> int | None:
        """Que parte de las emergencias con convocatoria necesito una decision, o None sin
        convocatorias (no hay tasa)."""
        return porcentaje_entero(len(self.afectadas), self.emergencias_con_convocatoria)

    @property
    def detalle(self) -> tuple[EmergenciaConDecision, ...]:
        if self.decision is None:
            return self.afectadas
        return tuple(emergencia for emergencia in self.afectadas if emergencia.tuvo(self.decision))

    def barras(self) -> list[tuple[DecisionDeCobertura, str, int, int]]:
        """(decision, etiqueta, decisiones, emergencias) de cada barra, en el orden del grafico."""
        return [
            (
                decision,
                ETIQUETA_POR_DECISION[decision],
                cantidad,
                sum(emergencia.tuvo(decision) for emergencia in self.afectadas),
            )
            for decision, cantidad in (
                (DecisionDeCobertura.reapertura, self.reaperturas),
                (DecisionDeCobertura.continuar_parcial, self.continuaciones),
            )
        ]

    @property
    def hubo_decisiones(self) -> bool:
        return bool(self.reaperturas or self.continuaciones)

    def grafico(self, enlaces: Sequence[str] | None = None) -> dict[str, Any]:
        """Una barra por decision. Con un filtro elegido, la otra barra queda atenuada para que
        se vea cual se esta detallando abajo."""
        barras = self.barras()
        return graficos.barras(
            [etiqueta for _, etiqueta, _, _ in barras],
            [cantidad for _, _, cantidad, _ in barras],
            tonos=[
                TONO_POR_DECISION[decision] if self.decision in (None, decision) else "tenue"
                for decision, *_ in barras
            ],
            unidad=DECISIONES,
            detalles=[
                f"En {emergencias} {'emergencia' if emergencias == 1 else 'emergencias'}"
                for *_, emergencias in barras
            ],
            enlaces=enlaces,
        )

    def tabla(self) -> TablaExportable:
        """Una fila por decision, como el grafico. Sin decisiones en el periodo queda vacia."""
        columnas = ("decision", "decisiones", "emergencias")
        if not self.hubo_decisiones:
            return TablaExportable(columnas=columnas)
        return TablaExportable(
            columnas=columnas,
            filas=tuple(
                (etiqueta, cantidad, emergencias)
                for _, etiqueta, cantidad, emergencias in self.barras()
            ),
        )

    def tabla_de_detalle(self) -> TablaExportable:
        """Las emergencias del detalle, con el filtro de decision aplicado."""
        return TablaExportable(
            columnas=(
                "emergencia",
                "gravedad",
                "convocatorias_publicadas",
                "reaperturas",
                "continuo_con_parcial",
                "espera_decision",
            ),
            filas=tuple(
                (
                    emergencia.titulo,
                    etiqueta_gravedad(emergencia.gravedad),
                    emergencia.convocatorias_publicadas,
                    emergencia.reaperturas,
                    emergencia.continuaciones > 0,
                    emergencia.pendientes > 0,
                )
                for emergencia in self.detalle
            ),
        )

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "filtros": {"decision": self.decision.value if self.decision else None},
            "emergencias_con_convocatoria": self.emergencias_con_convocatoria,
            "emergencias_con_cobertura_insuficiente": len(self.afectadas),
            "porcentaje_con_cobertura_insuficiente": self.porcentaje_afectadas,
            "emergencias_que_esperan_decision": self.esperan_decision,
            "decisiones": self.tabla().como_json(),
            "detalle": self.tabla_de_detalle().como_json(),
        }


def _afectadas(historiales: list[HistorialDeConvocatorias]) -> tuple[EmergenciaConDecision, ...]:
    con_insuficiencia = [h for h in historiales if h.tuvo_cobertura_insuficiente]
    datos = servicios_de_emergencias.obtener_datos_basicos(
        historial.emergencia_id for historial in con_insuficiencia
    )
    afectadas = [
        EmergenciaConDecision(
            emergencia_id=historial.emergencia_id,
            titulo=datos[historial.emergencia_id].titulo,
            gravedad=datos[historial.emergencia_id].nivel_gravedad,
            convocatorias_publicadas=historial.publicadas,
            reaperturas=historial.reaperturas,
            continuaciones=historial.aceptadas_parcialmente,
            pendientes=historial.pendientes_de_decision,
        )
        for historial in con_insuficiencia
    ]
    # Primero las que mas convocatorias necesitaron; a igual cantidad, por nombre.
    return tuple(
        sorted(afectadas, key=lambda e: (-e.convocatorias_publicadas, e.titulo.casefold()))
    )


def obtener_seccion_de_convocatorias(
    periodo: Periodo, decision: DecisionDeCobertura | None = None
) -> SeccionDeConvocatorias:
    """Decisiones ante cobertura insuficiente sobre las emergencias registradas en el periodo."""
    desde, hasta = periodo.limites_utc()
    emergencia_ids = servicios_de_emergencias.consultar_ids_de_emergencias_registradas(
        desde=desde, hasta=hasta
    )
    historiales = servicios_de_convocatorias.listar_historial_de_convocatorias(
        emergencia_ids=emergencia_ids
    )
    return SeccionDeConvocatorias(
        decision=decision,
        emergencias_con_convocatoria=len(historiales),
        afectadas=_afectadas(historiales),
    )
