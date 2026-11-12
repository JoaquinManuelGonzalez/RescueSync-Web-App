"""Servicios de negocio del modulo de adjudicaciones.

Por ahora solo expone las lecturas que necesita el panel de auditoria. El registro de la
adjudicacion (etapa 5 del proceso) todavia no esta implementado: `modelos.py` sigue vacio.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, case, func, select

from app.extensiones import db
from app.modulos.emergencias import servicios as servicios_de_emergencias
from app.modulos.ofertas import servicios as servicios_de_ofertas


@dataclass(frozen=True, slots=True)
class UnidadesDeEmergencia:
    """Unidades que pidio una emergencia, sumando todos sus lotes, y cuantas se le adjudicaron.

    `adjudicadas` nunca supera a `requeridas`: cada item cuenta como mucho lo que pidio, asi lo
    que sobra de un item no tapa lo que falta de otro.
    """

    emergencia_id: int
    requeridas: int
    adjudicadas: int


def contar_ongs_con_adjudicacion(*, emergencia_ids: Select[tuple[int]]) -> int | None:
    """Cantidad de ONGs distintas con al menos una adjudicacion sobre esas emergencias.

    `emergencia_ids` es una subconsulta de ids de emergencia (por ejemplo, la que arma
    `emergencias.servicios.consultar_ids_de_emergencias_registradas`): la implementacion la usa
    como `emergencia_id.in_(emergencia_ids)` para resolver todo en una sola consulta.

    Devuelve None mientras el modulo no registre adjudicaciones. El panel lo muestra como "sin
    datos" y no como un 0, que un directivo leeria como "ninguna ONG fue adjudicada".

    TODO(adjudicaciones): reemplazar el cuerpo cuando exista el modelo `Adjudicacion`. Se cuentan
    las organizaciones de tipo `ong` (`COUNT(DISTINCT organizacion_id)`) y la firma no cambia, asi
    que el panel no se toca.
    """
    return None


def consultar_unidades_por_emergencia(
    *, emergencia_ids: Select[tuple[int]]
) -> list[UnidadesDeEmergencia]:
    """Unidades requeridas y adjudicadas de cada una de esas emergencias, en una sola consulta.

    Las emergencias sin necesidades cargadas no aparecen: no tienen nada que cubrir.

    Mientras no exista la adjudicacion, "adjudicadas" son las unidades que el Sistema Nacional
    habilito en su evaluacion (aportes clasificados como principal o apoyo), que es lo que la
    integracion con Bonita ya informa como cobertura.

    TODO(adjudicaciones): cuando exista el modelo `Adjudicacion`, cambiar la subconsulta de
    habilitadas por la de unidades adjudicadas por `lote_item_id`. La firma no cambia, asi que el
    panel no se toca.
    """
    requeridas = servicios_de_emergencias.consultar_unidades_requeridas(
        emergencia_ids=emergencia_ids
    ).subquery()
    habilitadas = servicios_de_ofertas.consultar_unidades_habilitadas(
        lote_item_ids=select(requeridas.c.lote_item_id)
    ).subquery()

    cantidad_habilitada = func.coalesce(habilitadas.c.cantidad_habilitada, 0)
    # min(habilitada, requerida) por item, escrito con CASE para que funcione igual en
    # PostgreSQL y en el SQLite de los tests (SQLite no tiene LEAST).
    cubiertas_del_item = case(
        (cantidad_habilitada < requeridas.c.cantidad_requerida, cantidad_habilitada),
        else_=requeridas.c.cantidad_requerida,
    )

    filas = db.session.execute(
        select(
            requeridas.c.emergencia_id,
            func.sum(requeridas.c.cantidad_requerida),
            func.sum(cubiertas_del_item),
        )
        .select_from(requeridas)
        .outerjoin(habilitadas, habilitadas.c.lote_item_id == requeridas.c.lote_item_id)
        .group_by(requeridas.c.emergencia_id)
        .order_by(requeridas.c.emergencia_id)
    ).all()

    return [
        UnidadesDeEmergencia(
            emergencia_id=emergencia_id, requeridas=int(total), adjudicadas=int(cubiertas)
        )
        for emergencia_id, total, cubiertas in filas
    ]
