"""Servicios del modulo de adjudicaciones: seleccion, datos para Bonita y lecturas del panel."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import event

from app.extensiones import db
from app.modulos.adjudicaciones.servicios import (
    UnidadesDeEmergencia,
    construir_ongs_no_seleccionadas_json,
    consultar_unidades_por_emergencia,
)
from app.modulos.convocatorias.modelos import Convocatoria
from app.modulos.emergencias.modelos import EstadoEmergencia
from app.modulos.emergencias.servicios import consultar_ids_de_emergencias_registradas
from app.modulos.ofertas.modelos import EstadoOferta, Oferta, OfertaLinea, TipoAsignacion
from app.modulos.organizaciones.modelos import Organizacion

MARZO = (datetime(2025, 3, 1, 3, tzinfo=UTC), datetime(2025, 4, 1, 3, tzinfo=UTC))
MEDIADOS_DE_MARZO = datetime(2025, 3, 15, 15, tzinfo=UTC)


def test_suma_las_unidades_de_cada_emergencia_en_una_sola_consulta(
    app, crear_emergencias, cargar_necesidades
) -> None:
    primera, segunda, tercera, sin_lotes = crear_emergencias(
        *[(MEDIADOS_DE_MARZO, EstadoEmergencia.finalizada)] * 4
    )
    cargar_necesidades(primera, (100, 100), (50, 80))  # el excedente no suma: 150 de 150
    # Solo cuenta la ultima ronda adjudicada: ni la reabierta ni la adjudicacion anterior.
    cargar_necesidades(segunda, (60, 0), reabierta=True)
    cargar_necesidades(segunda, (40, 10))
    cargar_necesidades(tercera, (20, 20), adjudicada_en=datetime(2025, 1, 3, tzinfo=UTC))
    cargar_necesidades(tercera, (30, 15), adjudicada_en=datetime(2025, 2, 3, tzinfo=UTC))

    consultas: list[str] = []
    with app.app_context():
        ids = consultar_ids_de_emergencias_registradas(desde=MARZO[0], hasta=MARZO[1])

        def _contar(_conexion, _cursor, sentencia, *_args) -> None:
            consultas.append(sentencia)

        event.listen(db.engine, "before_cursor_execute", _contar)
        try:
            unidades = consultar_unidades_por_emergencia(emergencia_ids=ids)
        finally:
            event.remove(db.engine, "before_cursor_execute", _contar)

    assert unidades == [
        UnidadesDeEmergencia(emergencia_id=primera, requeridas=150, adjudicadas=150),
        UnidadesDeEmergencia(emergencia_id=segunda, requeridas=40, adjudicadas=10),
        UnidadesDeEmergencia(emergencia_id=tercera, requeridas=30, adjudicadas=15),
    ]
    assert sin_lotes not in {u.emergencia_id for u in unidades}
    assert len(consultas) == 1


def test_confirmar_la_seleccion_registra_cuando_se_adjudico(
    app, crear_emergencias, cargar_necesidades
) -> None:
    """La fecha de adjudicacion es la que usan los tiempos y las series del panel de auditoria."""
    from app.modulos.adjudicaciones.servicios import seleccionar_lineas
    from app.modulos.convocatorias.modelos import EstadoConvocatoria
    from app.modulos.ofertas.modelos import EstadoOferta, Oferta, OfertaLinea

    (emergencia,) = crear_emergencias((MEDIADOS_DE_MARZO, EstadoEmergencia.activa))
    oferta_id = cargar_necesidades(emergencia, (100, 100))

    with app.app_context():
        oferta = db.session.get(Oferta, oferta_id)
        convocatoria = oferta.convocatoria
        # Como la deja Bonita al evaluar: cerrada, con la oferta presentada y nada seleccionado.
        convocatoria.estado = EstadoConvocatoria.cerrada
        convocatoria.adjudicada_en = None
        oferta.estado = EstadoOferta.presentada
        (linea,) = db.session.query(OfertaLinea).filter_by(oferta_id=oferta_id).all()
        linea.seleccionada = False
        db.session.commit()

        antes = datetime.now(UTC)
        seleccionar_lineas(convocatoria, [linea.id])

        assert convocatoria.estado == EstadoConvocatoria.adjudicada
        assert convocatoria.adjudicada_en is not None
        assert convocatoria.adjudicada_en.replace(tzinfo=UTC) >= antes.replace(microsecond=0)


# --- ONG que Bonita libera al confirmar la seleccion -----------------------------
#
# La liberacion por ONG de la API libera todo el compromiso de la ONG en la emergencia, asi que
# la lista nunca puede incluir a una ONG con alguna linea seleccionada. Estos tests arman la
# convocatoria en memoria: la funcion solo lee las ofertas y sus lineas.


def _ong(identificador: str | None) -> Organizacion:
    return Organizacion(
        id=uuid.uuid4(), nombre=f"ONG {identificador}", identificador_nacional=identificador
    )


def _linea(
    ong: Organizacion,
    tipo: TipoAsignacion = TipoAsignacion.principal,
    *,
    seleccionada: bool = False,
) -> OfertaLinea:
    return OfertaLinea(
        organizacion=ong,
        organizacion_id=ong.id,
        tipo_asignacion=tipo,
        seleccionada=seleccionada,
        cantidad_ofrecida=10,
    )


def _ongs_no_seleccionadas(*ofertas: Oferta) -> list[str]:
    convocatoria = Convocatoria(ofertas=list(ofertas))
    return json.loads(construir_ongs_no_seleccionadas_json(convocatoria))


def test_no_libera_a_la_ong_que_tiene_otra_oferta_adjudicada(app) -> None:
    """Antes entraba toda ONG con una linea en una oferta rechazada y perdia lo adjudicado."""
    adjudicada_y_rechazada = _ong("30-11111111-1")
    solo_rechazada = _ong("30-22222222-2")
    rechazada_por_el_sistema = _ong("30-33333333-3")

    resultado = _ongs_no_seleccionadas(
        Oferta(
            estado=EstadoOferta.rechazada,
            items=[
                _linea(adjudicada_y_rechazada),
                _linea(solo_rechazada, TipoAsignacion.apoyo),
                # Sin compromiso en la API: la liberacion da 404 y Bonita lo cuenta como "sin
                # compromisos". Se incluye igual por si la evaluacion la marco mal (reintento).
                _linea(rechazada_por_el_sistema, TipoAsignacion.rechazada),
            ],
        ),
        Oferta(
            estado=EstadoOferta.adjudicada,
            items=[_linea(adjudicada_y_rechazada, seleccionada=True)],
        ),
    )

    assert resultado == ["30-22222222-2", "30-33333333-3"]


def test_una_ong_con_parte_de_sus_lineas_seleccionadas_no_se_libera(app) -> None:
    """Limitacion aceptada: lo no seleccionado de esa ONG queda comprometido hasta finalizar."""
    parcial = _ong("30-11111111-1")
    socia_sin_seleccion = _ong("30-22222222-2")

    resultado = _ongs_no_seleccionadas(
        Oferta(
            estado=EstadoOferta.adjudicada,
            items=[
                _linea(parcial, seleccionada=True),
                _linea(parcial),
                # Integra el consorcio adjudicado, pero el municipio no eligio nada suyo.
                _linea(socia_sin_seleccion),
            ],
        ),
    )

    assert resultado == ["30-22222222-2"]


def test_ignora_las_ofertas_que_no_llegaron_a_evaluarse(app) -> None:
    """Una oferta tambien queda rechazada si una ONG del consorcio declina la invitacion."""
    resultado = _ongs_no_seleccionadas(
        Oferta(
            estado=EstadoOferta.rechazada,
            items=[
                _linea(_ong("30-11111111-1"), TipoAsignacion.pendiente),
                _linea(_ong(None), TipoAsignacion.pendiente),
            ],
        ),
    )

    assert resultado == []


def test_omite_las_ong_evaluadas_sin_identificador_nacional(app) -> None:
    """Sin CUIT la API no pudo comprometerle nada; antes cortaba la confirmacion ya guardada."""
    resultado = _ongs_no_seleccionadas(
        Oferta(
            estado=EstadoOferta.rechazada,
            items=[
                _linea(_ong(None), TipoAsignacion.rechazada),
                _linea(_ong("   "), TipoAsignacion.rechazada),
                _linea(_ong(" 30-11111111-1 ")),
            ],
        ),
    )

    assert resultado == ["30-11111111-1"]
