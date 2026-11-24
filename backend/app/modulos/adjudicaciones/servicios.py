"""Servicios de negocio del modulo de adjudicaciones.

Reglas para seleccionar las ofertas evaluadas por el Sistema Nacional (etapa 5 del proceso) y,
al final, las lecturas agregadas que necesita el panel de auditoria.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import selectinload

from app.core.errores import (
    ConflictoDeEstado,
    ErrorDeAplicacion,
    RecursoNoEncontrado,
    ReglaDeNegocioIncumplida,
    SolicitudInvalida,
)
from app.core.integraciones.bonita.proceso import confirmar_seleccion_ofertas, error_sin_guardar
from app.core.integraciones.bonita.sesion import BONITA_USER
from app.core.logging import registrar_evento
from app.extensiones import db
from app.modulos.convocatorias import servicios as servicios_de_convocatorias
from app.modulos.convocatorias.modelos import (
    Convocatoria,
    DecisionCobertura,
    EstadoConvocatoria,
)
from app.modulos.emergencias import servicios as servicios_de_emergencias
from app.modulos.emergencias.modelos import Emergencia, EstadoEmergencia, TipoNecesidad
from app.modulos.notificaciones import servicios as servicios_de_notificaciones
from app.modulos.ofertas import servicios as servicios_de_ofertas
from app.modulos.ofertas.modelos import EstadoOferta, Oferta, TipoAsignacion


def obtener_convocatoria(convocatoria_id: uuid.UUID, municipio_id: uuid.UUID) -> Convocatoria:
    convocatoria = db.session.scalar(
        select(Convocatoria)
        .join(Emergencia)
        .where(Convocatoria.id == convocatoria_id, Emergencia.municipio_id == municipio_id)
        .options(
            selectinload(Convocatoria.emergencia),
            selectinload(Convocatoria.lotes),
            selectinload(Convocatoria.ofertas).selectinload(Oferta.items),
        ),
    )
    if not convocatoria:
        raise RecursoNoEncontrado("No encontramos la convocatoria solicitada.")
    if convocatoria.emergencia.estado != EstadoEmergencia.activa:
        raise ReglaDeNegocioIncumplida(
            "La emergencia ya no está pendiente de atención.",
            codigo="EMERGENCIA_NO_PENDIENTE",
        )
    if not (
        convocatoria.cobertura_completa
        or convocatoria.decision_cobertura == DecisionCobertura.aceptada_parcialmente
    ):
        raise ReglaDeNegocioIncumplida(
            "La selección solo está disponible cuando la cobertura fue completada.",
            codigo="COBERTURA_INCOMPLETA",
        )
    return convocatoria


def listar_convocatorias_pendientes(municipio_id: uuid.UUID) -> list[Convocatoria]:
    return list(
        db.session.scalars(
            select(Convocatoria)
            .join(Emergencia)
            .where(
                Emergencia.municipio_id == municipio_id,
                Emergencia.estado == EstadoEmergencia.activa,
                or_(
                    Convocatoria.cobertura_completa.is_(True),
                    Convocatoria.decision_cobertura
                    == DecisionCobertura.aceptada_parcialmente.value,
                ),
                Convocatoria.estado == EstadoConvocatoria.cerrada,
            )
            .options(selectinload(Convocatoria.emergencia))
            .order_by(Convocatoria.cobertura_evaluada_en.desc(), Convocatoria.id.desc())
        )
    )


def _limite_con_margen(cantidad: int) -> int:
    return int((Decimal(cantidad) * Decimal("1.50")).to_integral_value(rounding=ROUND_FLOOR))


def _cobertura_minima(cantidad: int) -> int:
    return int((Decimal(cantidad) * Decimal("0.75")).to_integral_value(rounding=ROUND_CEILING))


def seleccionar_lineas(convocatoria: Convocatoria, linea_ids: list[uuid.UUID]) -> list[Oferta]:
    if convocatoria.estado == EstadoConvocatoria.adjudicada:
        raise ConflictoDeEstado(
            "La selección de esta convocatoria ya fue confirmada y no puede modificarse."
        )
    if convocatoria.estado != EstadoConvocatoria.cerrada:
        raise ConflictoDeEstado("La convocatoria no está disponible para confirmar una selección.")
    if not isinstance(linea_ids, list) or any(
        not isinstance(linea_id, uuid.UUID) for linea_id in linea_ids
    ):
        raise SolicitudInvalida("La selección contiene líneas inválidas.")
    if not linea_ids:
        raise SolicitudInvalida("Seleccioná al menos una línea de oferta.")

    ofertas = list(
        db.session.scalars(
            select(Oferta)
            .where(Oferta.convocatoria_id == convocatoria.id)
            .options(selectinload(Oferta.items))
            .with_for_update()
        )
    )
    lineas = [linea for oferta in ofertas for linea in oferta.items]
    lineas_por_id = {linea.id: linea for linea in lineas}
    if len(set(linea_ids)) != len(linea_ids) or any(
        linea_id not in lineas_por_id for linea_id in linea_ids
    ):
        raise SolicitudInvalida("La selección contiene líneas que no pertenecen a la convocatoria.")

    linea_ids_seleccionadas = set(linea_ids)
    lineas_seleccionadas = [lineas_por_id[linea_id] for linea_id in linea_ids]
    cantidades_por_item: dict[uuid.UUID, int] = defaultdict(int)
    requeridas_por_item: dict[uuid.UUID, int] = {}
    limites = {
        lote_item.id: _limite_con_margen(int(lote_item.cantidad_solicitada))
        for lote in convocatoria.lotes
        for lote_item in lote.lote_items
    }
    for lote in convocatoria.lotes:
        for lote_item in lote.lote_items:
            requeridas_por_item[lote_item.id] = int(lote_item.cantidad_solicitada)

    for linea in lineas_seleccionadas:
        oferta = linea.oferta
        if oferta.estado not in (EstadoOferta.presentada, EstadoOferta.adjudicada):
            raise ConflictoDeEstado(
                "Solo se pueden seleccionar líneas de ofertas presentadas y evaluadas."
            )
        if linea.tipo_asignacion not in (TipoAsignacion.principal, TipoAsignacion.apoyo):
            raise ReglaDeNegocioIncumplida(
                "Solo se pueden seleccionar líneas habilitadas por el Sistema Nacional."
            )
        cantidades_por_item[linea.lote_item_id] += int(linea.cantidad_ofrecida)

    excedentes = [
        lote_item_id
        for lote_item_id, cantidad in cantidades_por_item.items()
        if cantidad > limites.get(lote_item_id, 0)
    ]
    if excedentes:
        raise ReglaDeNegocioIncumplida(
            "La selección supera el margen del 50% permitido para un lote de necesidad.",
            detalle={"lote_item_ids": excedentes},
            codigo="SELECCION_SUPERA_MARGEN",
        )

    faltantes = [
        lote_item_id
        for lote_item_id, requerida in requeridas_por_item.items()
        if cantidades_por_item[lote_item_id] < _cobertura_minima(requerida)
    ]
    if faltantes:
        raise ReglaDeNegocioIncumplida(
            "La selección debe cubrir al menos el 75% de cada ítem solicitado.",
            detalle={"lote_item_ids": faltantes},
            codigo="SELECCION_NO_CUBRE_MINIMO",
        )

    for linea in lineas:
        linea.seleccionada = linea.id in linea_ids_seleccionadas

    resultados: list[tuple[Oferta, bool]] = []
    for oferta in ofertas:
        tiene_lineas_seleccionadas = any(linea.seleccionada for linea in oferta.items)
        if tiene_lineas_seleccionadas:
            era_adjudicada = oferta.estado == EstadoOferta.adjudicada
            oferta.estado = EstadoOferta.adjudicada
            if not era_adjudicada:
                resultados.append((oferta, True))
        elif oferta.estado in (EstadoOferta.presentada, EstadoOferta.adjudicada):
            oferta.estado = EstadoOferta.rechazada
            resultados.append((oferta, False))

    for oferta, adjudicada in resultados:
        servicios_de_notificaciones.notificar_resultado_adjudicacion(oferta, adjudicada)
    convocatoria.estado = EstadoConvocatoria.adjudicada
    # El momento de la adjudicacion: desde aca miden los tiempos y las series mensuales del
    # panel de auditoria.
    convocatoria.adjudicada_en = datetime.now(UTC)
    _comunicar_seleccion_a_bonita(convocatoria)
    db.session.commit()
    return [oferta for oferta in ofertas if any(linea.seleccionada for linea in oferta.items)]


def _comunicar_seleccion_a_bonita(convocatoria: Convocatoria) -> None:
    """Completa en Bonita la tarea "Seleccionar ofertas" con la seleccion todavia sin guardar.

    Se llama antes del commit a proposito: si Bonita no recibe la seleccion, no se guarda nada y
    el municipio puede reintentar. Guardarla igual dejaria el caso trabado en esa tarea mientras
    la web sigue adelante, y al final la finalizacion de las ONG no encontraria su tarea.

    Una emergencia sin caso en Bonita (el motor estaba caido cuando se creo) no tiene ninguna
    tarea que completar: se deja constancia en el log y la seleccion sigue su curso local, para
    no bloquear al municipio para siempre.
    """
    emergencia = convocatoria.emergencia
    if not emergencia.bonita_case_id:
        registrar_evento(
            logging.WARNING,
            "bonita_seleccion_sin_caso",
            convocatoria_id=convocatoria.id,
            emergencia_id=emergencia.id,
        )
        return

    convocatoria_id, case_id = convocatoria.id, emergencia.bonita_case_id
    try:
        # Armar los datos tambien puede fallar (una ONG seleccionada sin CUIT): ese error ya
        # explica que corregir, asi que sale tal cual, pero tampoco se guarda nada.
        compromisos_json = construir_compromisos_json(convocatoria)
        ongs_no_seleccionadas_json = construir_ongs_no_seleccionadas_json(convocatoria)
    except ErrorDeAplicacion:
        db.session.rollback()
        raise

    try:
        confirmar_seleccion_ofertas(
            username=BONITA_USER,
            case_id=case_id,
            adjudicacion_id=convocatoria_id,
            compromisos_json=compromisos_json,
            ongs_no_seleccionadas_json=ongs_no_seleccionadas_json,
        )
    except ErrorDeAplicacion as error:
        db.session.rollback()
        registrar_evento(
            logging.WARNING,
            "bonita_seleccion_no_comunicada",
            convocatoria_id=convocatoria_id,
            bonita_case_id=case_id,
            codigo=error.codigo,
        )
        raise error_sin_guardar(error, "la selección", "No se guardó ningún cambio.") from error


def construir_compromisos_json(convocatoria: Convocatoria) -> str:
    """Construye el JSON de compromisos para el Sistema Nacional."""

    aportes_agrupados = {}

    for oferta in convocatoria.ofertas:
        for linea in oferta.items:
            if not linea.seleccionada:
                continue

            organizacion = linea.organizacion
            recurso = linea.lote_item.item

            identificador = organizacion.identificador_nacional

            if not identificador:
                raise ReglaDeNegocioIncumplida(
                    "Una ONG seleccionada no tiene identificador nacional."
                )

            clave = (identificador, recurso.codigo_recurso)

            if clave not in aportes_agrupados:
                aportes_agrupados[clave] = {
                    "identificador_nacional": identificador,
                    "codigo_recurso": recurso.codigo_recurso,
                    "cantidad": 0,
                    "tipo_asignacion": linea.tipo_asignacion.value,
                }
            elif aportes_agrupados[clave]["tipo_asignacion"] != linea.tipo_asignacion.value:
                raise ReglaDeNegocioIncumplida(
                    "Un mismo recurso de una ONG tiene tipos de asignación diferentes."
                )

            aportes_agrupados[clave]["cantidad"] += linea.cantidad_ofrecida

    if not aportes_agrupados:
        raise ReglaDeNegocioIncumplida("No hay líneas seleccionadas para generar compromisos.")

    emergencia = convocatoria.emergencia

    compromisos = {
        "emergencia_externa_id": str(emergencia.id),
        "nivel_gravedad": emergencia.nivel_gravedad.name.upper(),
        "aportes": list(aportes_agrupados.values()),
    }

    return json.dumps(compromisos, ensure_ascii=False)


def construir_ongs_no_seleccionadas_json(convocatoria: Convocatoria) -> str:
    """CUIT de las ONG que evaluó el Sistema Nacional y no tienen ninguna línea seleccionada.

    Con esta lista Bonita llama a la liberación por ONG de la API, que libera **todo** lo que la
    ONG tiene comprometido en la emergencia: la API no libera por línea. Por eso una ONG con al
    menos una línea seleccionada nunca entra, aunque tenga otras sin seleccionar o una oferta
    rechazada, porque liberarla le quitaría lo adjudicado. Limitación aceptada: las líneas no
    seleccionadas de esa ONG siguen comprometidas hasta que se finaliza la emergencia.

    Cuenta las líneas que clasificó el Sistema Nacional (las que no quedaron `pendiente`), no el
    estado de la oferta: una oferta también queda rechazada cuando una ONG del consorcio declina
    la invitación, y esa nunca se evaluó. Una ONG sin identificador nacional se omite: la API no
    pudo comprometerle nada.
    """
    identificadores_evaluadas: dict[uuid.UUID, str | None] = {}
    con_lineas_seleccionadas: set[uuid.UUID] = set()

    for oferta in convocatoria.ofertas:
        for linea in oferta.items:
            if linea.seleccionada:
                con_lineas_seleccionadas.add(linea.organizacion_id)
            elif linea.tipo_asignacion != TipoAsignacion.pendiente:
                identificadores_evaluadas[linea.organizacion_id] = (
                    linea.organizacion.identificador_nacional
                )

    identificadores = {
        identificador.strip()
        for organizacion_id, identificador in identificadores_evaluadas.items()
        if organizacion_id not in con_lineas_seleccionadas
        and identificador
        and identificador.strip()
    }
    return json.dumps(sorted(identificadores), ensure_ascii=False)


# --- Lectura agregada (panel de auditoria) ---------------------------------------


@dataclass(frozen=True, slots=True)
class UnidadesDeEmergencia:
    """Unidades que pidio una emergencia en su ultima ronda adjudicada y cuantas se le adjudicaron.

    Una ronda es una convocatoria con sus lotes. Las rondas anteriores que se reabrieron por
    cobertura insuficiente no cuentan: sus lotes se reformularon en la ronda siguiente.
    `adjudicadas` nunca supera a `requeridas`: cada item cuenta como mucho lo que pidio, asi lo
    que sobra de un item no tapa lo que falta de otro.
    """

    emergencia_id: uuid.UUID
    requeridas: int
    adjudicadas: int


def _ofertas_adjudicadas_de(emergencia_ids: Select[tuple[uuid.UUID]]):
    """Subconsulta con las ofertas adjudicadas de esas emergencias y cuando se adjudicaron.

    Columnas: `oferta_id`, `emergencia_id` y `adjudicada_en`. Cruza las convocatorias adjudicadas
    con sus ofertas adjudicadas, cada una desde la capa de servicios de su modulo.
    """
    adjudicaciones = servicios_de_convocatorias.consultar_adjudicaciones(
        emergencia_ids=emergencia_ids
    ).subquery()
    ofertas = servicios_de_ofertas.consultar_ofertas_adjudicadas(
        convocatoria_ids=select(adjudicaciones.c.convocatoria_id)
    ).subquery()
    return (
        select(
            ofertas.c.oferta_id,
            adjudicaciones.c.emergencia_id,
            adjudicaciones.c.adjudicada_en,
        )
        .join(adjudicaciones, adjudicaciones.c.convocatoria_id == ofertas.c.convocatoria_id)
        .subquery()
    )


def contar_ongs_con_adjudicacion(*, emergencia_ids: Select[tuple[uuid.UUID]]) -> int:
    """Cantidad de ONGs distintas con al menos una adjudicacion sobre esas emergencias.

    `emergencia_ids` es una subconsulta de ids de emergencia (por ejemplo, la que arma
    `emergencias.servicios.consultar_ids_de_emergencias_registradas`): la implementacion la usa
    como `emergencia_id.in_(emergencia_ids)` para resolver todo en una sola consulta.

    Una ONG cuenta si participa aceptada de una oferta adjudicada. En un consorcio cuentan todas
    sus participantes, igual que en el ranking de ONGs.
    """
    ofertas = _ofertas_adjudicadas_de(emergencia_ids)
    participantes = servicios_de_ofertas.consultar_participantes_aceptados(
        oferta_ids=select(ofertas.c.oferta_id)
    ).subquery()
    return db.session.scalar(select(func.count(func.distinct(participantes.c.organizacion_id))))


def consultar_unidades_por_emergencia(
    *, emergencia_ids: Select[tuple[uuid.UUID]]
) -> list[UnidadesDeEmergencia]:
    """Unidades requeridas y adjudicadas de cada una de esas emergencias, en una sola consulta.

    Se mide sobre los lotes de la ultima ronda adjudicada de cada emergencia: la convocatoria
    adjudicada mas reciente que tiene lotes vigentes. Si una emergencia se reabrio cinco veces y
    en la ultima pidio 10 unidades y recibio 8, cubrio el 80 %: lo pedido en las rondas
    reabiertas se reformulo en la siguiente y no se suma. Con dos rondas adjudicadas, cuenta la
    ultima. "Mas reciente" es la mayor `adjudicada_en`; una adjudicacion vieja sin fecha cuenta
    como anterior a cualquier fechada, entre ellas manda la publicacion y el id desempata.

    Las emergencias sin lotes en una convocatoria adjudicada no aparecen: no tienen una ronda
    que medir. "Adjudicadas" son las unidades de las lineas que el municipio selecciono en
    ofertas adjudicadas.
    """
    requeridas = servicios_de_emergencias.consultar_unidades_requeridas(
        emergencia_ids=emergencia_ids
    ).subquery()
    adjudicaciones = servicios_de_convocatorias.consultar_adjudicaciones(
        emergencia_ids=emergencia_ids
    ).subquery()
    # Se rankean las filas que ya tienen lotes pedidos: una convocatoria adjudicada sin lotes
    # vigentes no puede tapar a la ronda que si pidio algo.
    ronda = func.dense_rank().over(
        partition_by=requeridas.c.emergencia_id,
        order_by=(
            adjudicaciones.c.adjudicada_en.desc().nulls_last(),
            adjudicaciones.c.creado_en.desc(),
            adjudicaciones.c.convocatoria_id.desc(),
        ),
    )
    por_ronda = (
        select(
            requeridas.c.lote_item_id,
            requeridas.c.emergencia_id,
            requeridas.c.cantidad_requerida,
            ronda.label("ronda"),
        )
        .join(adjudicaciones, adjudicaciones.c.convocatoria_id == requeridas.c.convocatoria_id)
        .subquery()
    )
    ultima_ronda = select(por_ronda).where(por_ronda.c.ronda == 1).subquery()

    seleccionadas = servicios_de_ofertas.consultar_unidades_seleccionadas(
        lote_item_ids=select(ultima_ronda.c.lote_item_id)
    ).subquery()

    cantidad_seleccionada = func.coalesce(seleccionadas.c.cantidad_seleccionada, 0)
    # min(seleccionada, requerida) por item, escrito con CASE para que funcione igual en
    # PostgreSQL y en el SQLite de los tests (SQLite no tiene LEAST).
    cubiertas_del_item = case(
        (cantidad_seleccionada < ultima_ronda.c.cantidad_requerida, cantidad_seleccionada),
        else_=ultima_ronda.c.cantidad_requerida,
    )

    filas = db.session.execute(
        select(
            ultima_ronda.c.emergencia_id,
            func.sum(ultima_ronda.c.cantidad_requerida),
            func.sum(cubiertas_del_item),
        )
        .select_from(ultima_ronda)
        .outerjoin(seleccionadas, seleccionadas.c.lote_item_id == ultima_ronda.c.lote_item_id)
        .group_by(ultima_ronda.c.emergencia_id)
        .order_by(ultima_ronda.c.emergencia_id)
    ).all()

    return [
        UnidadesDeEmergencia(
            emergencia_id=emergencia_id, requeridas=int(total), adjudicadas=int(cubiertas)
        )
        for emergencia_id, total, cubiertas in filas
    ]


@dataclass(frozen=True, slots=True)
class OfertaAdjudicada:
    """Una oferta adjudicada, con quienes la integran y que lotes cubre.

    `organizacion_ids` son las ONGs que participan aceptadas (mas de una: consorcio) y `lote_ids`
    los lotes en los que el municipio selecciono alguna de sus lineas. `adjudicada_en` es None
    solo para adjudicaciones sin fecha registrada.
    """

    oferta_id: uuid.UUID
    emergencia_id: uuid.UUID
    adjudicada_en: datetime | None
    organizacion_ids: tuple[uuid.UUID, ...]
    lote_ids: frozenset[uuid.UUID]

    @property
    def es_de_consorcio(self) -> bool:
        return len(self.organizacion_ids) > 1


def listar_ofertas_adjudicadas(
    *, emergencia_ids: Select[tuple[uuid.UUID]]
) -> list[OfertaAdjudicada]:
    """Las ofertas adjudicadas de esas emergencias, ordenadas por id, en dos consultas.

    Una trae a los participantes aceptados y la otra los lotes de las lineas seleccionadas;
    se arman en memoria para no repetir cada participante por cada lote.
    """
    ofertas = _ofertas_adjudicadas_de(emergencia_ids)
    ids_de_ofertas = select(ofertas.c.oferta_id)

    participantes = servicios_de_ofertas.consultar_participantes_aceptados(
        oferta_ids=ids_de_ofertas
    ).subquery()
    filas_de_participantes = db.session.execute(
        select(
            ofertas.c.oferta_id,
            ofertas.c.emergencia_id,
            ofertas.c.adjudicada_en,
            participantes.c.organizacion_id,
        ).outerjoin(participantes, participantes.c.oferta_id == ofertas.c.oferta_id)
    ).all()

    lineas = servicios_de_ofertas.consultar_lineas_seleccionadas(
        oferta_ids=ids_de_ofertas
    ).subquery()
    requeridas = servicios_de_emergencias.consultar_unidades_requeridas(
        emergencia_ids=emergencia_ids
    ).subquery()
    filas_de_lotes = db.session.execute(
        select(lineas.c.oferta_id, requeridas.c.lote_id)
        .join(requeridas, requeridas.c.lote_item_id == lineas.c.lote_item_id)
        .distinct()
    ).all()

    lotes_por_oferta: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for oferta_id, lote_id in filas_de_lotes:
        lotes_por_oferta[oferta_id].add(lote_id)

    datos: dict[uuid.UUID, tuple[uuid.UUID, datetime | None]] = {}
    organizaciones_por_oferta: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for oferta_id, emergencia_id, adjudicada_en, organizacion_id in filas_de_participantes:
        datos[oferta_id] = (emergencia_id, adjudicada_en)
        if organizacion_id is not None:
            organizaciones_por_oferta[oferta_id].add(organizacion_id)

    return [
        OfertaAdjudicada(
            oferta_id=oferta_id,
            emergencia_id=emergencia_id,
            adjudicada_en=adjudicada_en,
            organizacion_ids=tuple(sorted(organizaciones_por_oferta[oferta_id])),
            lote_ids=frozenset(lotes_por_oferta[oferta_id]),
        )
        for oferta_id, (emergencia_id, adjudicada_en) in sorted(datos.items())
    ]


@dataclass(frozen=True, slots=True)
class UnidadesAdjudicadas:
    """Unidades de un rubro adjudicadas en una misma adjudicacion (una convocatoria)."""

    adjudicada_en: datetime
    categoria: TipoNecesidad
    unidades: int


def listar_unidades_adjudicadas_por_categoria(
    *, emergencia_ids: Select[tuple[uuid.UUID]]
) -> list[UnidadesAdjudicadas]:
    """Unidades adjudicadas a esas emergencias por adjudicacion y rubro, en una sola consulta.

    Son las unidades de las lineas seleccionadas tal como se adjudicaron, sin recortarlas a lo
    pedido: miden lo que la red movilizo. Las adjudicaciones sin fecha no aparecen, porque no
    se pueden ubicar en el tiempo. Agrupar por mes queda para quien consume, que conoce la zona
    horaria en la que se lee el reporte.
    """
    ofertas = _ofertas_adjudicadas_de(emergencia_ids)
    lineas = servicios_de_ofertas.consultar_lineas_seleccionadas(
        oferta_ids=select(ofertas.c.oferta_id)
    ).subquery()
    requeridas = servicios_de_emergencias.consultar_unidades_requeridas(
        emergencia_ids=emergencia_ids
    ).subquery()

    filas = db.session.execute(
        select(ofertas.c.adjudicada_en, requeridas.c.categoria, func.sum(lineas.c.cantidad))
        .select_from(lineas)
        .join(ofertas, ofertas.c.oferta_id == lineas.c.oferta_id)
        .join(requeridas, requeridas.c.lote_item_id == lineas.c.lote_item_id)
        .where(ofertas.c.adjudicada_en.is_not(None))
        .group_by(ofertas.c.adjudicada_en, requeridas.c.categoria)
        .order_by(ofertas.c.adjudicada_en, requeridas.c.categoria)
    ).all()
    return [
        UnidadesAdjudicadas(adjudicada_en=adjudicada_en, categoria=categoria, unidades=int(total))
        for adjudicada_en, categoria, total in filas
    ]
