"""Datos semilla de una oferta demo para probar la interfaz y su trazabilidad."""

from __future__ import annotations

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria
from app.modulos.emergencias.modelos import Item
from app.modulos.ofertas.modelos import EstadoOferta, Oferta, OfertaLinea, OfertaOrganizacion
from app.modulos.organizaciones.modelos import Organizacion
from app.modulos.usuarios_roles.modelos import Usuario

MARCA_CONVOCATORIA_DEMO = "SEED_DEMO_OFERTAS"
EMAIL_REPRESENTANTE_DEMO = "representante@cruzsolidaria.test"


@registrar("ofertas")
def sembrar_ofertas() -> list[ResultadoSemilla]:
    """Crea una oferta inicial de Cruz Solidaria sobre la convocatoria demo."""
    convocatoria = Convocatoria.query.filter_by(observaciones=MARCA_CONVOCATORIA_DEMO).first()
    if convocatoria is None:
        raise ValueError("Convocatoria demo no encontrada.")

    usuario = Usuario.query.filter_by(email=EMAIL_REPRESENTANTE_DEMO).first()
    if usuario is None or usuario.organizacion_id is None:
        raise ValueError("Representante ONG demo no encontrado o sin organización.")
    organizacion = db.session.get(Organizacion, usuario.organizacion_id)
    if organizacion is None:
        raise ValueError("La organización del representante demo no existe.")

    oferta, oferta_creada = obtener_o_crear(
        Oferta,
        claves={"convocatoria_id": convocatoria.id, "usuario_id": usuario.id},
        valores={
            "version": 1,
            "estado": EstadoOferta.presentada,
            "observaciones": "Oferta demo para probar edición y trazabilidad.",
        },
    )
    resultado_oferta = ResultadoSemilla("ofertas")
    resultado_oferta.contar(oferta_creada)

    _, organizacion_creada = obtener_o_crear(
        OfertaOrganizacion,
        claves={"oferta_id": oferta.id, "organizacion_id": organizacion.id},
        valores={"rol_consorcio": "lider"},
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
                for lote in convocatoria.emergencia.lotes
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
            valores={"cantidad_ofrecida": cantidad},
        )
        resultado_lineas.contar(linea_creada)

    return [resultado_oferta, resultado_asociacion, resultado_lineas]