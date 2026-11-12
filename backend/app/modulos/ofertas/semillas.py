"""Datos semilla de ofertas: una demo para probar la interfaz y su trazabilidad, y las ofertas ya
evaluadas de las emergencias historicas, para que el panel de auditoria tenga cobertura que
mostrar."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.core.semillas import ResultadoSemilla, obtener_o_crear, registrar
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria, EstadoConvocatoria
from app.modulos.emergencias.modelos import Emergencia, EstadoLote, Item, LoteItem, LoteNecesidad
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

MARCA_CONVOCATORIA_HISTORICA = "SEED_COBERTURA_HISTORICA"
DESCRIPCION_LOTE_HISTORICO = "Necesidades atendidas"

# Emergencias finalizadas de emergencias/semillas_emergencias.py::EMERGENCIAS_HISTORICAS, con lo
# que pidieron y lo que el Sistema Nacional habilito: (item, requerida, habilitada).
# Dos se cubrieron completas y una al 60 % (1500 de 2500). La cuarta finalizada historica
# ("Anegamiento de calles...") queda sin necesidades a proposito: el panel la informa aparte.
COBERTURA_HISTORICA: tuple[tuple[str, str, tuple[tuple[str, int, int], ...]], ...] = (
    (
        "Granizo sobre la zona hortícola de La Plata",
        "representante@cruzsolidaria.test",
        (("Raciones de alimento no perecedero", 400, 400), ("Agua potable envasada", 1500, 1500)),
    ),
    (
        "Desborde de la laguna de Chascomús",
        "representante@manosunidas.test",
        (("Agua potable envasada", 2000, 1500), ("Raciones de alimento no perecedero", 500, 0)),
    ),
    (
        "Incendio de pastizales en el periurbano de La Plata",
        "representante@cruzsolidaria.test",
        (("Paramédicos", 6, 6), ("Agua potable envasada", 800, 1000)),
    ),
)


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

    return [resultado_oferta, resultado_asociacion, resultado_lineas]


def _buscar_por(modelo: type, **claves):
    instancia = db.session.execute(select(modelo).filter_by(**claves)).scalar_one_or_none()
    if instancia is None:
        raise ValueError(f"{modelo.__name__} demo no encontrado: {claves!r}")
    return instancia


@registrar("cobertura_historica")
def sembrar_cobertura_historica() -> list[ResultadoSemilla]:
    """Lote, convocatoria adjudicada y oferta evaluada de cada emergencia historica finalizada."""
    coordinador = _buscar_por(Usuario, email="coordinador@rescuesync.test")
    resultado_lotes = ResultadoSemilla("lotes_historicos")
    resultado_lineas = ResultadoSemilla("oferta_items_historicos")

    for titulo, email_representante, items in COBERTURA_HISTORICA:
        emergencia = _buscar_por(Emergencia, titulo=titulo)
        representante = _buscar_por(Usuario, email=email_representante)
        cubre_todo = all(habilitada >= requerida for _, requerida, habilitada in items)
        estado_del_lote = (
            EstadoLote.adjudicado_total if cubre_todo else EstadoLote.adjudicado_parcial
        )

        convocatoria, _ = obtener_o_crear(
            Convocatoria,
            claves={"emergencia_id": emergencia.id, "observaciones": MARCA_CONVOCATORIA_HISTORICA},
            valores={
                "coordinador_id": coordinador.id,
                "fecha_inicio": emergencia.creado_en + timedelta(days=1),
                "fecha_cierre": emergencia.creado_en + timedelta(days=4),
                "resumen_situacion": emergencia.descripcion,
                "estado": EstadoConvocatoria.adjudicada,
            },
        )
        lote, lote_creado = obtener_o_crear(
            LoteNecesidad,
            claves={"emergencia_id": emergencia.id, "descripcion": DESCRIPCION_LOTE_HISTORICO},
            valores={
                "convocatoria_id": convocatoria.id,
                "estado": estado_del_lote,
            },
        )
        resultado_lotes.contar(lote_creado)
        oferta, _ = obtener_o_crear(
            Oferta,
            claves={"convocatoria_id": convocatoria.id, "usuario_id": representante.id},
            valores={"estado": EstadoOferta.adjudicada},
        )
        obtener_o_crear(
            OfertaOrganizacion,
            claves={"oferta_id": oferta.id, "organizacion_id": representante.organizacion_id},
            valores={"rol_consorcio": "lider", "estado_participacion": "aceptada"},
        )

        for nombre_item, requerida, habilitada in items:
            item = _buscar_por(Item, nombre=nombre_item)
            lote_item, _ = obtener_o_crear(
                LoteItem,
                claves={"lote_id": lote.id, "item_id": item.id},
                valores={"cantidad_solicitada": requerida},
            )
            if not habilitada:
                continue
            _, linea_creada = obtener_o_crear(
                OfertaLinea,
                claves={"oferta_id": oferta.id, "lote_item_id": lote_item.id},
                valores={
                    "organizacion_id": representante.organizacion_id,
                    "cantidad_ofrecida": habilitada,
                    "tipo_asignacion": TipoAsignacion.principal,
                },
            )
            resultado_lineas.contar(linea_creada)

    return [resultado_lotes, resultado_lineas]
