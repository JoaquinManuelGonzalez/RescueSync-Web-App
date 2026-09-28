from __future__ import annotations

from app.extensiones import db
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
