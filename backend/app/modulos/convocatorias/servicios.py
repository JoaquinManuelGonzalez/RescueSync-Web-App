"""Servicios de negocio para la apertura de convocatorias."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import selectinload

from app.core.errores import (
    ConflictoDeEstado,
    RecursoNoEncontrado,
    ReglaDeNegocioIncumplida,
    SolicitudInvalida,
)
from app.core.interfaz.paginacion import Pagina, paginar
from app.core.logging import registrar_evento
from app.extensiones import db
from app.modulos.convocatorias.modelos import (
    Convocatoria,
    DecisionCobertura,
    EstadoConvocatoria,
)
from app.modulos.emergencias.modelos import (
    Emergencia,
    EstadoEmergencia,
    EstadoLote,
    LoteItem,
    LoteNecesidad,
)
from app.modulos.notificaciones import servicios as servicios_de_notificaciones
from app.modulos.ofertas.modelos import Oferta, OfertaLinea, TipoAsignacion
from app.modulos.usuarios_roles.modelos import Usuario

PORCENTAJE_MINIMO_COBERTURA_PARCIAL = Decimal("75.00")


def _consulta_de_convocatorias(
    *, estado: str | None = None, texto: str | None = None, municipio_id: int | None = None
) -> Select:
    consulta = select(Convocatoria).join(Emergencia)
    if estado:
        consulta = consulta.where(Convocatoria.estado == estado)
    if municipio_id is not None:
        consulta = consulta.where(Emergencia.municipio_id == municipio_id)
    if texto:
        busqueda = f"%{texto.strip()}%"
        consulta = consulta.where(
            or_(
                Emergencia.titulo.ilike(busqueda),
                Emergencia.zona_afectada.ilike(busqueda),
                Convocatoria.resumen_situacion.ilike(busqueda),
            )
        )
    return consulta.order_by(Convocatoria.fecha_cierre.desc(), Convocatoria.id.desc())


def listar_convocatorias(
    *, estado: str | None = None, texto: str | None = None, municipio_id: int | None = None
) -> list[Convocatoria]:
    """Lista convocatorias aplicando los filtros de la pantalla."""
    consulta = _consulta_de_convocatorias(estado=estado, texto=texto, municipio_id=municipio_id)
    return list(db.session.execute(consulta).scalars())


def paginar_convocatorias(
    *,
    pagina: int,
    por_pagina: int,
    estado: str | None = None,
    texto: str | None = None,
    municipio_id: int | None = None,
) -> Pagina[Convocatoria]:
    """Obtiene una página de convocatorias aplicando los mismos filtros."""
    return paginar(
        _consulta_de_convocatorias(estado=estado, texto=texto, municipio_id=municipio_id),
        pagina,
        por_pagina,
    )


def _validar_resumen(resumen_situacion: str | None) -> str:
    """Valida y normaliza el resumen requerido para publicar la convocatoria."""
    if not isinstance(resumen_situacion, str) or not resumen_situacion.strip():
        raise SolicitudInvalida(
            "El resumen de situación es obligatorio.",
            detalle={"campo": "resumen_situacion"},
        )
    return resumen_situacion.strip()


def _normalizar_fecha(fecha: datetime | None) -> datetime:
    """Valida el vencimiento y lo devuelve en UTC; las fechas sin zona se interpretan como UTC."""
    if not isinstance(fecha, datetime):
        raise SolicitudInvalida(
            "La fecha límite para presentar ofertas es obligatoria.",
            detalle={"campo": "fecha_cierre"},
        )

    if fecha.tzinfo is None:
        return fecha.replace(tzinfo=UTC)
    return fecha.astimezone(UTC)


def cerrar_convocatorias_vencidas(*, emergencia_id: int | None = None) -> int:
    """Cierra convocatorias vencidas sin adelantar la decisión de cobertura."""
    ahora = datetime.now(UTC)
    consulta = select(Convocatoria).where(
        Convocatoria.estado == EstadoConvocatoria.abierta,
        Convocatoria.fecha_cierre <= ahora,
    )
    if emergencia_id is not None:
        consulta = consulta.where(Convocatoria.emergencia_id == emergencia_id)
    vencidas = db.session.execute(consulta.with_for_update()).scalars().all()
    if not vencidas:
        return 0

    for convocatoria in vencidas:
        convocatoria.estado = EstadoConvocatoria.cerrada
        servicios_de_notificaciones.notificar_cierre_convocatoria(convocatoria)

    db.session.commit()
    return len(vencidas)


def cerrar_convocatoria(convocatoria_id: int) -> Convocatoria:
    """Cierra la recepción de ofertas y habilita una nueva evaluación de necesidades."""
    convocatoria = db.session.execute(
        select(Convocatoria).where(Convocatoria.id == convocatoria_id).with_for_update()
    ).scalar_one_or_none()
    if convocatoria is None:
        raise RecursoNoEncontrado(f"Convocatoria con id {convocatoria_id} no encontrada.")
    if convocatoria.estado == EstadoConvocatoria.cerrada:
        return convocatoria
    if convocatoria.estado != EstadoConvocatoria.abierta:
        raise ConflictoDeEstado(
            "Solo se puede cerrar una convocatoria que esté abierta.",
            detalle={"convocatoria_id": convocatoria.id, "estado": convocatoria.estado.value},
        )

    convocatoria.estado = EstadoConvocatoria.cerrada
    servicios_de_notificaciones.notificar_cierre_convocatoria(convocatoria)
    sigue_abierta = db.session.execute(
        select(Convocatoria.id).where(
            Convocatoria.emergencia_id == convocatoria.emergencia_id,
            Convocatoria.id != convocatoria.id,
            Convocatoria.estado == EstadoConvocatoria.abierta,
            Convocatoria.fecha_cierre > datetime.now(UTC),
        )
    ).scalar_one_or_none()
    if sigue_abierta is None:
        emergencia = db.session.execute(
            select(Emergencia).where(Emergencia.id == convocatoria.emergencia_id).with_for_update()
        ).scalar_one_or_none()
        if emergencia and emergencia.estado == EstadoEmergencia.activa:
            estado_anterior = emergencia.estado
            emergencia.estado = EstadoEmergencia.registrada
            servicios_de_notificaciones.notificar_cambio_estado_emergencia(
                emergencia, estado_anterior
            )

    db.session.commit()
    registrar_evento(
        logging.INFO,
        "convocatoria_cerrada",
        convocatoria_id=convocatoria.id,
        emergencia_id=convocatoria.emergencia_id,
    )
    return convocatoria


def crear_convocatoria(
    *,
    emergencia_id: int,
    coordinador_id: int,
    resumen_situacion: str,
    fecha_cierre: datetime,
    observaciones: str | None = None,
) -> Convocatoria:
    """Publica una convocatoria para los lotes pendientes de una emergencia en revisión."""
    if not emergencia_id:
        raise SolicitudInvalida(
            "La emergencia es obligatoria.",
            detalle={"campo": "emergencia_id"},
        )
    if not coordinador_id:
        raise SolicitudInvalida(
            "El usuario coordinador es obligatorio.",
            detalle={"campo": "coordinador_id"},
        )

    cerrar_convocatorias_vencidas(emergencia_id=emergencia_id)

    resumen = _validar_resumen(resumen_situacion)
    cierre = _normalizar_fecha(fecha_cierre)
    inicio = datetime.now(UTC)
    if cierre <= inicio:
        raise SolicitudInvalida(
            "La fecha límite debe ser posterior al momento de publicación.",
            detalle={"campo": "fecha_cierre"},
        )

    emergencia = db.session.execute(
        select(Emergencia).where(Emergencia.id == emergencia_id).with_for_update()
    ).scalar_one_or_none()
    if emergencia is None:
        raise RecursoNoEncontrado(f"Emergencia con id {emergencia_id} no encontrada.")
    if emergencia.estado != EstadoEmergencia.en_evaluacion:
        raise ReglaDeNegocioIncumplida(
            "La emergencia debe estar en revisión antes de abrir la convocatoria.",
            detalle={"emergencia_id": emergencia.id, "estado": emergencia.estado.value},
        )

    coordinador = db.session.get(Usuario, coordinador_id)
    if coordinador is None:
        raise RecursoNoEncontrado(f"Usuario coordinador con id {coordinador_id} no encontrado.")

    convocatoria_abierta = db.session.execute(
        select(Convocatoria.id)
        .where(
            Convocatoria.emergencia_id == emergencia.id,
            Convocatoria.estado == EstadoConvocatoria.abierta,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if convocatoria_abierta is not None:
        raise ConflictoDeEstado(
            "Ya existe una convocatoria abierta para esta emergencia.",
            detalle={"emergencia_id": emergencia.id, "estado": EstadoConvocatoria.abierta.value},
        )

    lotes_existentes = (
        db.session.execute(
            select(LoteNecesidad)
            .where(LoteNecesidad.emergencia_id == emergencia.id)
            .order_by(LoteNecesidad.id)
            .with_for_update()
        )
        .scalars()
        .all()
    )
    if not lotes_existentes:
        raise SolicitudInvalida(
            "La emergencia debe tener al menos un lote de necesidad para publicar.",
            detalle={"campo": "lotes"},
        )
    lotes = [lote for lote in lotes_existentes if lote.estado == EstadoLote.pendiente]
    if not lotes:
        raise ConflictoDeEstado(
            "Agregá necesidades nuevas antes de abrir otra convocatoria.",
            detalle={"emergencia_id": emergencia.id, "campo": "lotes"},
        )

    convocatoria = Convocatoria(
        emergencia_id=emergencia.id,
        coordinador_id=coordinador.id,
        fecha_inicio=inicio,
        fecha_cierre=cierre,
        resumen_situacion=resumen,
        observaciones=observaciones.strip() if observaciones and observaciones.strip() else None,
        estado=EstadoConvocatoria.abierta,
    )
    estado_anterior = emergencia.estado
    emergencia.estado = EstadoEmergencia.activa
    db.session.add(convocatoria)
    db.session.flush()
    for lote in lotes:
        lote.convocatoria = convocatoria
        lote.estado = EstadoLote.en_convocatoria
    servicios_de_notificaciones.notificar_convocatoria(convocatoria)
    servicios_de_notificaciones.notificar_cambio_estado_emergencia(emergencia, estado_anterior)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    registrar_evento(
        logging.INFO,
        "convocatoria_publicada",
        convocatoria_id=convocatoria.id,
        emergencia_id=emergencia.id,
        coordinador_id=coordinador.id,
        lotes=len(lotes),
    )

    # --- Integración con Bonita: enviar el timer de la ventana temporal -------
    _notificar_bonita_timer(emergencia, convocatoria, coordinador.email)

    return convocatoria


def obtener_convocatoria_con_cobertura_insuficiente(convocatoria_id: int) -> Convocatoria:
    """Obtiene una convocatoria que todavía espera una decisión del coordinador."""
    convocatoria = db.session.scalar(
        select(Convocatoria)
        .where(Convocatoria.id == convocatoria_id)
        .options(
            selectinload(Convocatoria.emergencia),
            selectinload(Convocatoria.ofertas)
            .selectinload(Oferta.items)
            .selectinload(OfertaLinea.organizacion),
            selectinload(Convocatoria.ofertas)
            .selectinload(Oferta.items)
            .selectinload(OfertaLinea.lote_item)
            .selectinload(LoteItem.item),
        )
    )
    if (
        convocatoria is None
        or convocatoria.estado != EstadoConvocatoria.cerrada
        or convocatoria.cobertura_evaluada_en is None
        or convocatoria.cobertura_completa
        or convocatoria.decision_cobertura != DecisionCobertura.pendiente
        or convocatoria.emergencia.estado
        not in (EstadoEmergencia.registrada, EstadoEmergencia.activa)
    ):
        raise RecursoNoEncontrado("No encontramos una cobertura insuficiente pendiente.")
    return convocatoria


def puede_aceptar_cobertura_parcial(convocatoria: Convocatoria) -> bool:
    """Compara cantidades exactas para que el redondeo de pantalla no habilite un 74,99%."""
    lote_items = db.session.scalars(
        select(LoteItem).join(LoteNecesidad).where(LoteNecesidad.convocatoria_id == convocatoria.id)
    ).all()
    cantidades_requeridas = {
        lote_item.id: int(lote_item.cantidad_solicitada) for lote_item in lote_items
    }
    cantidad_total_solicitada = sum(cantidades_requeridas.values())
    if not cantidad_total_solicitada:
        return False

    cantidades_habilitadas: defaultdict[int, int] = defaultdict(int)
    lineas_habilitadas = db.session.scalars(
        select(OfertaLinea)
        .join(Oferta)
        .where(
            Oferta.convocatoria_id == convocatoria.id,
            OfertaLinea.tipo_asignacion.in_((TipoAsignacion.principal, TipoAsignacion.apoyo)),
        )
    ).all()
    for linea in lineas_habilitadas:
        cantidades_habilitadas[linea.lote_item_id] += int(linea.cantidad_ofrecida)
    cantidad_total_cubierta = sum(
        min(cantidad, cantidades_habilitadas[lote_item_id])
        for lote_item_id, cantidad in cantidades_requeridas.items()
    )
    return (
        cantidad_total_cubierta * 100
        >= cantidad_total_solicitada * PORCENTAJE_MINIMO_COBERTURA_PARCIAL
    )


def _obtener_cobertura_pendiente_para_actualizar(convocatoria_id: int) -> Convocatoria:
    convocatoria = db.session.execute(
        select(Convocatoria).where(Convocatoria.id == convocatoria_id).with_for_update()
    ).scalar_one_or_none()
    if (
        convocatoria is None
        or convocatoria.estado != EstadoConvocatoria.cerrada
        or convocatoria.cobertura_evaluada_en is None
        or convocatoria.cobertura_completa
        or convocatoria.decision_cobertura != DecisionCobertura.pendiente
    ):
        raise RecursoNoEncontrado("No encontramos una cobertura insuficiente pendiente.")
    return convocatoria


def reabrir_convocatoria_por_cobertura_insuficiente(convocatoria_id: int) -> Emergencia:
    """Devuelve la emergencia al registro y conserva esta convocatoria como historial."""
    convocatoria = _obtener_cobertura_pendiente_para_actualizar(convocatoria_id)
    emergencia = db.session.execute(
        select(Emergencia).where(Emergencia.id == convocatoria.emergencia_id).with_for_update()
    ).scalar_one()
    if emergencia.estado not in (EstadoEmergencia.registrada, EstadoEmergencia.activa):
        raise ConflictoDeEstado("La emergencia no está disponible para reabrir la convocatoria.")
    convocatoria.decision_cobertura = DecisionCobertura.convocatoria_reabierta
    if emergencia.estado != EstadoEmergencia.registrada:
        estado_anterior = emergencia.estado
        emergencia.estado = EstadoEmergencia.registrada
        servicios_de_notificaciones.notificar_cambio_estado_emergencia(emergencia, estado_anterior)
    db.session.commit()
    return emergencia


def aceptar_cobertura_parcial(convocatoria_id: int) -> Convocatoria:
    """Aprueba una cobertura de al menos 75% y habilita la selección municipal."""
    convocatoria = _obtener_cobertura_pendiente_para_actualizar(convocatoria_id)
    if not puede_aceptar_cobertura_parcial(convocatoria):
        raise ReglaDeNegocioIncumplida(
            "La cobertura parcial solo se puede aceptar cuando alcanza al menos el 75%.",
            detalle={"porcentaje_cobertura": str(convocatoria.porcentaje_cobertura)},
            codigo="COBERTURA_PARCIAL_MENOR_AL_MINIMO",
        )

    emergencia = db.session.execute(
        select(Emergencia).where(Emergencia.id == convocatoria.emergencia_id).with_for_update()
    ).scalar_one()
    if emergencia.estado not in (EstadoEmergencia.registrada, EstadoEmergencia.activa):
        raise ConflictoDeEstado("La emergencia no está disponible para seleccionar ofertas.")
    convocatoria.decision_cobertura = DecisionCobertura.aceptada_parcialmente
    if emergencia.estado != EstadoEmergencia.activa:
        estado_anterior = emergencia.estado
        emergencia.estado = EstadoEmergencia.activa
        servicios_de_notificaciones.notificar_cambio_estado_emergencia(emergencia, estado_anterior)
    servicios_de_notificaciones.notificar_cobertura_parcial_aceptada(convocatoria)
    db.session.commit()
    return convocatoria


def _notificar_bonita_timer(
    emergencia: Emergencia, convocatoria: Convocatoria, username: str
) -> None:
    """Inicia el proceso en Bonita (si aún no existe) y envía la fecha de cierre.

    1. Si la emergencia no tiene ``bonita_case_id``, llama a
       ``iniciar_gestion()`` para instanciar el proceso y persiste el
       ``case_id`` en la emergencia.
    2. Ejecuta la tarea humana de publicación pasando el ``timerInput``
       con la fecha de cierre de la convocatoria.

    Si Bonita no está disponible se registra un warning y la convocatoria
    se crea igual — no se interrumpe el flujo principal.
    """
    try:
        from app.core.integraciones.bonita.proceso import (
            iniciar_gestion as _bonita_iniciar,
        )
        from app.core.integraciones.bonita.proceso import (
            publicar_convocatoria as _bonita_publicar,
        )

        case_id = emergencia.bonita_case_id

        if not case_id:
            case_id = _bonita_iniciar(emergencia.id, username)
            emergencia.bonita_case_id = case_id
            db.session.commit()
            registrar_evento(
                logging.INFO,
                "bonita_proceso_iniciado",
                convocatoria_id=convocatoria.id,
                emergencia_id=emergencia.id,
                bonita_case_id=case_id,
            )

        _bonita_publicar(
            username=username,
            case_id=case_id,
            convocatoria_id=convocatoria.id,
            fecha_cierre=convocatoria.fecha_cierre,
        )
        registrar_evento(
            logging.INFO,
            "bonita_timer_enviado",
            convocatoria_id=convocatoria.id,
            emergencia_id=emergencia.id,
            bonita_case_id=case_id,
            fecha_cierre=convocatoria.fecha_cierre.isoformat(),
        )
    except Exception:
        registrar_evento(
            logging.WARNING,
            "bonita_timer_error",
            convocatoria_id=convocatoria.id,
            emergencia_id=emergencia.id,
            motivo="No se pudo comunicar con Bonita; la convocatoria se creó igual.",
        )
