from __future__ import annotations

from app.extensiones import db
from app.modulos.emergencias.modelos import Emergencia, EstadoEmergencia
from app.modulos.notificaciones import servicios
from app.modulos.notificaciones.modelos import Notificacion
from app.modulos.organizaciones.modelos import Organizacion, TipoOrganizacion
from app.modulos.usuarios_roles.modelos import Usuario
from tests.conftest import CABECERA_NAVEGADOR, EMAIL_REPRESENTANTE


def test_un_aviso_se_comparte_y_se_marca_leido_por_la_organizacion(
    cliente_sembrado, ingresar, navegar
) -> None:
    with cliente_sembrado.application.app_context():
        representante = Usuario.query.filter_by(email=EMAIL_REPRESENTANTE).one()
        aviso = servicios.crear(
            organizacion_id=representante.organizacion_id,
            titulo="Convocatoria nueva",
            mensaje="Hay una convocatoria disponible.",
            enlace="/ofertas/convocatoria/1",
        )
        db.session.commit()
        aviso_id = aviso.id

    assert ingresar(EMAIL_REPRESENTANTE).status_code == 200
    respuesta = navegar("/notificaciones")
    assert respuesta.status_code == 200
    assert "Convocatoria nueva" in respuesta.get_data(as_text=True)

    respuesta = cliente_sembrado.get(
        f"/notificaciones/{aviso_id}/abrir", headers=CABECERA_NAVEGADOR
    )
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/ofertas/convocatoria/1"

    with cliente_sembrado.application.app_context():
        assert db.session.get(Notificacion, aviso_id).leida is True


def test_los_avisos_de_otra_organizacion_no_se_exponen(
    cliente_sembrado, ingresar, navegar
) -> None:
    with cliente_sembrado.application.app_context():
        centro = Organizacion.query.filter_by(
            tipo=TipoOrganizacion.centro_coordinador_regional
        ).one()
        aviso = servicios.crear(
            organizacion_id=centro.id,
            titulo="Solo para coordinadores",
            mensaje="Aviso privado.",
            enlace="/emergencias/1",
        )
        db.session.commit()
        aviso_id = aviso.id

    assert ingresar(EMAIL_REPRESENTANTE).status_code == 200
    respuesta = navegar(f"/notificaciones/{aviso_id}/abrir")
    assert respuesta.status_code == 404


def test_el_cambio_de_estado_se_notifica_al_municipio_que_registro_la_emergencia(
    app, base_de_datos
) -> None:
    with app.app_context():
        emergencia = Emergencia.query.first()
        assert emergencia is not None
        estado_anterior = emergencia.estado
        emergencia.estado = EstadoEmergencia.en_evaluacion

        aviso = servicios.notificar_cambio_estado_emergencia(emergencia, estado_anterior)
        db.session.commit()

        assert aviso.organizacion_id == emergencia.municipio_id
        assert aviso.titulo == "Estado de emergencia actualizado"
        assert estado_anterior.value.replace("_", " ").capitalize() in aviso.mensaje
        assert "En revisión" in aviso.mensaje
        assert aviso.enlace == f"/emergencias/{emergencia.id}"


def test_una_convocatoria_se_notifica_a_todas_las_ong_activas(app, base_de_datos) -> None:
    with app.app_context():
        convocatoria = next(
            convocatoria
            for emergencia in Emergencia.query.all()
            for convocatoria in emergencia.convocatorias
        )
        ong_ids = {
            organizacion.id
            for organizacion in Organizacion.query.filter_by(tipo=TipoOrganizacion.ong, activo=True)
        }

        avisos = servicios.notificar_convocatoria(convocatoria)
        db.session.commit()

        avisos_ong = [aviso for aviso in avisos if aviso.organizacion_id in ong_ids]
        assert {aviso.organizacion_id for aviso in avisos_ong} == ong_ids
        assert all(aviso.titulo == "Nueva convocatoria disponible" for aviso in avisos_ong)
        assert all(
            aviso.enlace == f"/convocatorias/{convocatoria.id}" for aviso in avisos_ong
        )


def test_el_cierre_de_convocatoria_notifica_a_municipio_ong_y_coordinador(
    app, base_de_datos
) -> None:
    with app.app_context():
        convocatoria = next(
            convocatoria
            for emergencia in Emergencia.query.all()
            for convocatoria in emergencia.convocatorias
        )
        avisos = servicios.notificar_cierre_convocatoria(convocatoria)
        db.session.commit()

        ids = {aviso.organizacion_id for aviso in avisos}
        assert convocatoria.emergencia.municipio_id in ids
        assert convocatoria.coordinador.organizacion_id in ids
        assert all(aviso.titulo == "Convocatoria cerrada" for aviso in avisos)
        assert all(aviso.enlace == f"/convocatorias/{convocatoria.id}" for aviso in avisos)
