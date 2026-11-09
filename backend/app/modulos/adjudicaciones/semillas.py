"""Fixtures de selección municipal.

Estos datos están marcados como PRUEBA y se crean directamente en la base.
No invocan servicios de convocatorias ni la integración con Bonita.
"""

from __future__ import annotations

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.modulos.convocatorias.modelos import Convocatoria
from app.modulos.ofertas.modelos import (
    EstadoOferta,
    Oferta,
    OfertaLinea,
    OfertaOrganizacion,
    TipoAsignacion,
)
from app.modulos.organizaciones.modelos import Organizacion
from app.modulos.usuarios_roles.modelos import Usuario

MARCA_CONVOCATORIA_PRUEBA = "SEED_PRUEBA_SELECCION_SIN_BONITA"
EMAIL_COORDINADOR = "coordinador@rescuesync.test"
EMAIL_CRUZ = "representante@cruzsolidaria.test"
EMAIL_CRUZ_ROJA = "representante@cruzroja.test"


@registrar("adjudicaciones_prueba")
def sembrar_adjudicaciones_prueba() -> list[ResultadoSemilla]:
    """Crea ofertas evaluadas con líneas principal y apoyo para probar el panel."""
    convocatoria = Convocatoria.query.filter_by(observaciones=MARCA_CONVOCATORIA_PRUEBA).first()
    if convocatoria is None:
        raise ValueError("Convocatoria de prueba no encontrada.")

    coordinador = Usuario.query.filter_by(email=EMAIL_COORDINADOR).first()
    cruz = Organizacion.query.filter_by(nombre="Cruz Solidaria").first()
    cruz_roja = Organizacion.query.filter_by(
        nombre="Cruz Roja Argentina - Filial Bahía Blanca"
    ).first()
    if coordinador is None or cruz is None or cruz_roja is None:
        raise ValueError("Faltan organizaciones o usuario para las ofertas de prueba.")

    items = {
        lote_item.item.nombre: lote_item
        for lote in convocatoria.lotes
        for lote_item in lote.lote_items
    }
    resultado = ResultadoSemilla("ofertas_prueba")
    ofertas = (
        (
            "PRUEBA - Oferta principal Cruz Solidaria",
            EMAIL_CRUZ,
            cruz,
            800,
            6,
            TipoAsignacion.principal,
        ),
        (
            "PRUEBA - Oferta de apoyo Cruz Roja",
            EMAIL_CRUZ_ROJA,
            cruz_roja,
            300,
            3,
            TipoAsignacion.apoyo,
        ),
    )
    for titulo, email, organizacion, agua, paramedicos, asignacion in ofertas:
        usuario = Usuario.query.filter_by(email=email).first()
        if usuario is None:
            raise ValueError(f"Usuario de prueba no encontrado: {email!r}")
        oferta, creada = obtener_o_crear(
            Oferta,
            claves={"convocatoria_id": convocatoria.id, "usuario_id": usuario.id},
            valores={
                "version": 1,
                "estado": EstadoOferta.presentada,
                "observaciones": titulo,
            },
        )
        resultado.contar(creada)
        obtener_o_crear(
            OfertaOrganizacion,
            claves={"oferta_id": oferta.id, "organizacion_id": organizacion.id},
            valores={"rol_consorcio": "lider", "estado_participacion": "aceptada"},
        )
        for nombre_item, cantidad in (
            ("Agua potable envasada", agua),
            ("Paramédicos", paramedicos),
        ):
            obtener_o_crear(
                OfertaLinea,
                claves={"oferta_id": oferta.id, "lote_item_id": items[nombre_item].id},
                valores={
                    "organizacion_id": organizacion.id,
                    "cantidad_ofrecida": cantidad,
                    "tipo_asignacion": asignacion,
                    "seleccionada": False,
                },
            )
    return [resultado]
