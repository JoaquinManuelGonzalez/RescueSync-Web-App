"""Datos semilla de ofertas demo y pruebas para la cobertura parcial."""

from __future__ import annotations

from sqlalchemy import select

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria
from app.modulos.emergencias.modelos import Item
from app.modulos.ofertas.modelos import (
    EstadoOferta,
    Oferta,
    OfertaLinea,
    OfertaOrganizacion,
    TipoAsignacion,
)
from app.modulos.organizaciones.modelos import Organizacion
from app.modulos.usuarios_roles.modelos import Usuario

MARCA_CONVOCATORIA_DEMO = "SEED_DEMO_OFERTAS"
EMAIL_REPRESENTANTE_DEMO = "representante@cruzsolidaria.test"
MARCA_CONVOCATORIA_COBERTURA_INSUFICIENTE = "SEED_PRUEBA_COBERTURA_INSUFICIENTE"


@registrar("ofertas")
def sembrar_ofertas() -> list[ResultadoSemilla]:
    """Crea ofertas iniciales para la demo y el caso de cobertura parcial."""
    convocatoria = Convocatoria.query.filter_by(observaciones=MARCA_CONVOCATORIA_DEMO).first()
    if convocatoria is None:
        raise ValueError("Convocatoria demo no encontrada.")

    usuario = Usuario.query.filter_by(email=EMAIL_REPRESENTANTE_DEMO).first()
    if usuario is None or usuario.organizacion_id is None:
        raise ValueError("Representante ONG demo no encontrado o sin organización.")
    organizacion = db.session.get(Organizacion, usuario.organizacion_id)
    if organizacion is None:
        raise ValueError("La organización del representante demo no existe.")

    oferta = (
        db.session.execute(
            select(Oferta)
            .where(Oferta.convocatoria_id == convocatoria.id, Oferta.usuario_id == usuario.id)
            .order_by(Oferta.id.asc())
        )
        .scalars()
        .first()
    )
    oferta_creada = oferta is None
    if oferta is None:
        oferta = Oferta(
            convocatoria_id=convocatoria.id,
            usuario_id=usuario.id,
            version=1,
            estado=EstadoOferta.presentada,
            observaciones="Oferta demo para probar edición y trazabilidad.",
        )
        db.session.add(oferta)
        db.session.flush()
    resultado_oferta = ResultadoSemilla("ofertas")
    resultado_oferta.contar(oferta_creada)

    _, organizacion_creada = obtener_o_crear(
        OfertaOrganizacion,
        claves={"oferta_id": oferta.id, "organizacion_id": organizacion.id},
        valores={"rol_consorcio": "lider", "estado_participacion": "aceptada"},
    )
    resultado_asociacion = ResultadoSemilla("oferta_organizaciones")
    resultado_asociacion.contar(organizacion_creada)

    resultado_lineas = ResultadoSemilla("oferta_items")
    for nombre_item, cantidad in (("Agua potable envasada", 250), ("Paramédicos", 2)):
        item = Item.query.filter_by(nombre=nombre_item).first()
        if item is None:
            raise ValueError(f"Item demo no encontrado: {nombre_item!r}")
        lote_item = next(
            (
                linea
                for lote in convocatoria.lotes
                for linea in lote.lote_items
                if linea.item_id == item.id
            ),
            None,
        )
        if lote_item is None:
            raise ValueError(f"Item {nombre_item!r} no está en el lote demo.")
        _, linea_creada = obtener_o_crear(
            OfertaLinea,
            claves={"oferta_id": oferta.id, "lote_item_id": lote_item.id},
            valores={"cantidad_ofrecida": cantidad, "organizacion_id": organizacion.id},
        )
        resultado_lineas.contar(linea_creada)

    convocatoria_cobertura = Convocatoria.query.filter_by(
        observaciones=MARCA_CONVOCATORIA_COBERTURA_INSUFICIENTE
    ).first()
    if convocatoria_cobertura is None:
        raise ValueError("Convocatoria de cobertura insuficiente no encontrada.")

    oferta_cobertura, oferta_cobertura_creada = obtener_o_crear(
        Oferta,
        claves={
            "convocatoria_id": convocatoria_cobertura.id,
            "usuario_id": usuario.id,
        },
        valores={
            "version": 1,
            "estado": EstadoOferta.presentada,
            "observaciones": "PRUEBA - Oferta con cobertura parcial del 75%.",
        },
    )
    resultado_oferta_cobertura = ResultadoSemilla("ofertas_cobertura_insuficiente")
    resultado_oferta_cobertura.contar(oferta_cobertura_creada)

    _, asociacion_cobertura_creada = obtener_o_crear(
        OfertaOrganizacion,
        claves={
            "oferta_id": oferta_cobertura.id,
            "organizacion_id": organizacion.id,
        },
        valores={"rol_consorcio": "lider", "estado_participacion": "aceptada"},
    )
    resultado_asociacion_cobertura = ResultadoSemilla(
        "oferta_organizaciones_cobertura_insuficiente"
    )
    resultado_asociacion_cobertura.contar(asociacion_cobertura_creada)

    lote_item_cobertura = next(
        (
            linea
            for lote in convocatoria_cobertura.lotes
            for linea in lote.lote_items
            if linea.item.nombre == "Agua potable envasada"
        ),
        None,
    )
    if lote_item_cobertura is None:
        raise ValueError("Item de agua no encontrado en la convocatoria de prueba.")
    _, linea_cobertura_creada = obtener_o_crear(
        OfertaLinea,
        claves={
            "oferta_id": oferta_cobertura.id,
            "lote_item_id": lote_item_cobertura.id,
        },
        valores={
            "cantidad_ofrecida": 750,
            "organizacion_id": organizacion.id,
            "tipo_asignacion": TipoAsignacion.principal,
        },
    )
    resultado_linea_cobertura = ResultadoSemilla("oferta_items_cobertura_insuficiente")
    resultado_linea_cobertura.contar(linea_cobertura_creada)

    return [
        resultado_oferta,
        resultado_asociacion,
        resultado_lineas,
        resultado_oferta_cobertura,
        resultado_asociacion_cobertura,
        resultado_linea_cobertura,
    ]
