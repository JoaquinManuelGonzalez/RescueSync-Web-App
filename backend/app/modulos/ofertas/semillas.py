"""Datos semilla de ofertas: una demo para probar la interfaz y su trazabilidad, las pruebas de
cobertura parcial, y las ofertas ya evaluadas y adjudicadas de las emergencias historicas, para
que el panel de auditoria tenga que mostrar (cobertura, recursos por mes y rubro, consorcios,
inhabilitacion y ranking de ONGs)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

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
MARCA_CONVOCATORIA_COBERTURA_INSUFICIENTE = "SEED_PRUEBA_COBERTURA_INSUFICIENTE"

MARCA_CONVOCATORIA_HISTORICA = "SEED_COBERTURA_HISTORICA"
DESCRIPCION_LOTE_HISTORICO = "Necesidades atendidas"


@dataclass(frozen=True, slots=True)
class LineaHistorica:
    """Un aporte de una oferta: que item, cuanto, como lo clasifico el Sistema Nacional y, en un
    consorcio, que ONG lo aporta (sin ella, la lider). Las lineas habilitadas se seleccionan."""

    item: str
    cantidad: int
    clasificacion: TipoAsignacion = TipoAsignacion.principal
    aporta: str | None = None


@dataclass(frozen=True, slots=True)
class OfertaHistorica:
    """Una oferta: la presenta el representante de la ONG lider; `consorcio` son las demas ONGs
    participantes (aceptadas). Con alguna linea habilitada queda adjudicada; si no, rechazada."""

    representante: str
    lineas: tuple[LineaHistorica, ...]
    consorcio: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AdjudicacionHistorica:
    """Lo que pidio una emergencia historica, las ofertas que recibio y cuando se adjudico
    (`horas_hasta_adjudicar` desde su registro)."""

    emergencia: str
    necesidades: tuple[tuple[str, int], ...]
    horas_hasta_adjudicar: float
    ofertas: tuple[OfertaHistorica, ...]


CRUZ_SOLIDARIA = "representante@cruzsolidaria.test"
MANOS_UNIDAS = "representante@manosunidas.test"
CRUZ_ROJA = "representante@cruzroja.test"
BOMBEROS = "Bomberos Voluntarios de La Plata"
SCOUTS = "Grupo Scouts de Pergamino"
NO_HABILITADA = TipoAsignacion.rechazada

# Emergencias de emergencias/semillas_emergencias.py::EMERGENCIAS_HISTORICAS ya adjudicadas, para
# que cada seccion del panel de auditoria tenga datos: adjudicaciones en varios meses y rubros,
# consorcios, aportes que el Sistema Nacional no habilito y una cobertura parcial (la laguna).
# La finalizada "Anegamiento de calles..." queda sin necesidades a proposito: el panel la informa
# aparte. Lo que hizo cada ONG despues de la adjudicacion esta en ejecucion_cierre/semillas.py.
ADJUDICACIONES_HISTORICAS: tuple[AdjudicacionHistorica, ...] = (
    AdjudicacionHistorica(
        emergencia="Granizo sobre la zona hortícola de La Plata",
        necesidades=(
            ("Raciones de alimento no perecedero", 400),
            ("Agua potable envasada", 1500),
            ("Frazadas", 200),
        ),
        horas_hasta_adjudicar=84,
        ofertas=(
            OfertaHistorica(
                CRUZ_SOLIDARIA,
                (
                    LineaHistorica("Raciones de alimento no perecedero", 400),
                    LineaHistorica("Agua potable envasada", 1500),
                ),
            ),
            OfertaHistorica(
                MANOS_UNIDAS,
                (
                    LineaHistorica("Frazadas", 120, aporta=BOMBEROS),
                    LineaHistorica("Frazadas", 80),
                ),
                consorcio=(BOMBEROS,),
            ),
            OfertaHistorica(
                CRUZ_ROJA, (LineaHistorica("Agua potable envasada", 300, NO_HABILITADA),)
            ),
        ),
    ),
    AdjudicacionHistorica(
        emergencia="Desborde de la laguna de Chascomús",
        necesidades=(
            ("Agua potable envasada", 2000),
            ("Raciones de alimento no perecedero", 500),
            ("Colchones", 80),
        ),
        horas_hasta_adjudicar=50,
        ofertas=(
            OfertaHistorica(
                MANOS_UNIDAS,
                (LineaHistorica("Agua potable envasada", 1500), LineaHistorica("Colchones", 60)),
            ),
            OfertaHistorica(
                CRUZ_ROJA,
                (LineaHistorica("Raciones de alimento no perecedero", 300, NO_HABILITADA),),
            ),
        ),
    ),
    AdjudicacionHistorica(
        emergencia="Incendio de pastizales en el periurbano de La Plata",
        necesidades=(
            ("Paramédicos", 6),
            ("Agua potable envasada", 800),
            ("Botiquines de primeros auxilios", 50),
        ),
        horas_hasta_adjudicar=36,
        ofertas=(
            OfertaHistorica(
                CRUZ_SOLIDARIA,
                (
                    LineaHistorica("Paramédicos", 6),
                    LineaHistorica("Agua potable envasada", 1000, TipoAsignacion.apoyo, BOMBEROS),
                ),
                consorcio=(BOMBEROS,),
            ),
            OfertaHistorica(CRUZ_ROJA, (LineaHistorica("Botiquines de primeros auxilios", 50),)),
        ),
    ),
    AdjudicacionHistorica(
        emergencia="Temporal de viento y lluvia en Pergamino",
        necesidades=(
            ("Rescatistas", 20),
            ("Generadores eléctricos", 5),
            ("Raciones de alimento no perecedero", 600),
            ("Retroexcavadoras", 2),
        ),
        horas_hasta_adjudicar=20,
        ofertas=(
            OfertaHistorica(
                CRUZ_ROJA,
                (
                    LineaHistorica("Rescatistas", 20),
                    LineaHistorica("Generadores eléctricos", 5, aporta=SCOUTS),
                ),
                consorcio=(SCOUTS,),
            ),
            OfertaHistorica(
                MANOS_UNIDAS, (LineaHistorica("Raciones de alimento no perecedero", 600),)
            ),
            OfertaHistorica(
                CRUZ_SOLIDARIA, (LineaHistorica("Retroexcavadoras", 2, NO_HABILITADA),)
            ),
        ),
    ),
)


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


def _buscar_por(modelo: type, **claves):
    instancia = db.session.execute(select(modelo).filter_by(**claves)).scalar_one_or_none()
    if instancia is None:
        raise ValueError(f"{modelo.__name__} demo no encontrado: {claves!r}")
    return instancia


@registrar("cobertura_historica")
def sembrar_cobertura_historica() -> list[ResultadoSemilla]:
    """Lotes, convocatoria adjudicada y ofertas evaluadas de cada emergencia historica.

    Las filas de esta semilla llevan su marca y se reescriben en cada corrida (fecha de
    adjudicacion, clasificacion y seleccion de cada linea): asi una base sembrada antes de que
    existiera la fecha de adjudicacion queda igual que una nueva.
    """
    coordinador = _buscar_por(Usuario, email="coordinador@rescuesync.test")
    resultado_lotes = ResultadoSemilla("lotes_historicos")
    resultado_lineas = ResultadoSemilla("oferta_items_historicos")

    for historica in ADJUDICACIONES_HISTORICAS:
        emergencia = _buscar_por(Emergencia, titulo=historica.emergencia)
        adjudicada_en = emergencia.creado_en + timedelta(hours=historica.horas_hasta_adjudicar)

        convocatoria, _ = obtener_o_crear(
            Convocatoria,
            claves={"emergencia_id": emergencia.id, "observaciones": MARCA_CONVOCATORIA_HISTORICA},
            valores={
                "coordinador_id": coordinador.id,
                "fecha_inicio": emergencia.creado_en + timedelta(hours=6),
                "fecha_cierre": adjudicada_en - timedelta(hours=4),
                "resumen_situacion": emergencia.descripcion,
                "estado": EstadoConvocatoria.adjudicada,
            },
        )
        convocatoria.estado = EstadoConvocatoria.adjudicada
        convocatoria.adjudicada_en = adjudicada_en
        convocatoria.cobertura_evaluada_en = adjudicada_en - timedelta(hours=2)

        lote, lote_creado = obtener_o_crear(
            LoteNecesidad,
            claves={"emergencia_id": emergencia.id, "descripcion": DESCRIPCION_LOTE_HISTORICO},
            valores={"convocatoria_id": convocatoria.id, "estado": EstadoLote.adjudicado_total},
        )
        resultado_lotes.contar(lote_creado)

        lote_items = {}
        for nombre_item, requerida in historica.necesidades:
            item = _buscar_por(Item, nombre=nombre_item)
            lote_item, _ = obtener_o_crear(
                LoteItem,
                claves={"lote_id": lote.id, "item_id": item.id},
                valores={"cantidad_solicitada": requerida},
            )
            lote_item.cantidad_solicitada = requerida
            lote_items[nombre_item] = lote_item

        adjudicadas: dict[str, int] = {}
        for oferta_historica in historica.ofertas:
            lineas_creadas = _sembrar_oferta(
                convocatoria, oferta_historica, lote_items, adjudicada_en
            )
            for creada in lineas_creadas:
                resultado_lineas.contar(creada)
            for linea in oferta_historica.lineas:
                if linea.clasificacion != NO_HABILITADA:
                    adjudicadas[linea.item] = adjudicadas.get(linea.item, 0) + linea.cantidad

        cubre_todo = all(
            adjudicadas.get(nombre, 0) >= requerida for nombre, requerida in historica.necesidades
        )
        lote.estado = EstadoLote.adjudicado_total if cubre_todo else EstadoLote.adjudicado_parcial

    return [resultado_lotes, resultado_lineas]


def _sembrar_oferta(
    convocatoria: Convocatoria,
    historica: OfertaHistorica,
    lote_items: dict[str, LoteItem],
    adjudicada_en: datetime,
) -> list[bool]:
    """Crea o actualiza una oferta historica con sus participantes y lineas.

    Devuelve, por linea, si se creo (para el resumen del comando).
    """
    representante = _buscar_por(Usuario, email=historica.representante)
    lider_id = representante.organizacion_id
    organizacion_por_nombre = {
        nombre: _buscar_por(Organizacion, nombre=nombre).id for nombre in historica.consorcio
    }
    habilitada = any(linea.clasificacion != NO_HABILITADA for linea in historica.lineas)

    oferta, _ = obtener_o_crear(
        Oferta,
        claves={"convocatoria_id": convocatoria.id, "usuario_id": representante.id},
        valores={"estado": EstadoOferta.adjudicada},
    )
    oferta.estado = EstadoOferta.adjudicada if habilitada else EstadoOferta.rechazada
    # La seleccion es lo ultimo que toca la oferta: su ultima modificacion es la adjudicacion.
    oferta.actualizado_en = adjudicada_en

    participantes = {lider_id: "lider"}
    participantes.update(dict.fromkeys(organizacion_por_nombre.values(), "aportante"))
    for organizacion_id, rol in participantes.items():
        participacion, _ = obtener_o_crear(
            OfertaOrganizacion,
            claves={"oferta_id": oferta.id, "organizacion_id": organizacion_id},
            valores={"rol_consorcio": rol, "estado_participacion": "aceptada"},
        )
        participacion.estado_participacion = "aceptada"

    creadas = []
    declaradas: set[int] = set()
    for linea in historica.lineas:
        organizacion_id = organizacion_por_nombre[linea.aporta] if linea.aporta else lider_id
        oferta_linea, creada = obtener_o_crear(
            OfertaLinea,
            claves={
                "oferta_id": oferta.id,
                "lote_item_id": lote_items[linea.item].id,
                "organizacion_id": organizacion_id,
            },
            valores={"cantidad_ofrecida": linea.cantidad},
        )
        oferta_linea.cantidad_ofrecida = linea.cantidad
        oferta_linea.tipo_asignacion = linea.clasificacion
        oferta_linea.seleccionada = linea.clasificacion != NO_HABILITADA
        creadas.append(creada)
        declaradas.add(oferta_linea.id)

    # Una linea que la semilla ya no declara (de una version anterior) sobra: la oferta es de
    # una convocatoria historica marcada, asi que no hay datos de nadie mas en juego.
    for sobrante in db.session.scalars(
        select(OfertaLinea).where(
            OfertaLinea.oferta_id == oferta.id, OfertaLinea.id.not_in(declaradas)
        )
    ):
        db.session.delete(sobrante)
    return creadas
