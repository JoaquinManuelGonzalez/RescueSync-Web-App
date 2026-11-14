"""Lecturas del modulo de adjudicaciones que consume el panel de auditoria."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import event

from app.extensiones import db
from app.modulos.adjudicaciones.servicios import (
    UnidadesDeEmergencia,
    consultar_unidades_por_emergencia,
)
from app.modulos.emergencias.modelos import EstadoEmergencia
from app.modulos.emergencias.servicios import consultar_ids_de_emergencias_registradas

MARZO = (datetime(2025, 3, 1, 3, tzinfo=UTC), datetime(2025, 4, 1, 3, tzinfo=UTC))
MEDIADOS_DE_MARZO = datetime(2025, 3, 15, 15, tzinfo=UTC)


def test_suma_las_unidades_de_cada_emergencia_en_una_sola_consulta(
    app, crear_emergencias, cargar_necesidades
) -> None:
    primera, segunda, sin_lotes = crear_emergencias(
        *[(MEDIADOS_DE_MARZO, EstadoEmergencia.finalizada)] * 3
    )
    cargar_necesidades(primera, (100, 100), (50, 80))  # el excedente no suma: 150 de 150
    cargar_necesidades(segunda, (40, 10))
    cargar_necesidades(segunda, (60, 0))

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
        UnidadesDeEmergencia(emergencia_id=segunda, requeridas=100, adjudicadas=10),
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
