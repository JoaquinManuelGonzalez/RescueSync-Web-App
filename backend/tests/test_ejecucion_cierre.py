"""Tests del módulo ejecucion_cierre: seguimiento y finalización de tareas de ONGs."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.core.errores import ConflictoDeEstado, RecursoNoEncontrado
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria, EstadoConvocatoria
from app.modulos.ejecucion_cierre import servicios
from app.modulos.ejecucion_cierre.modelos import EstadoTareaEjecucion
from app.modulos.emergencias.modelos import Emergencia, NivelGravedad
from app.modulos.ofertas.modelos import EstadoOferta, Oferta
from app.modulos.organizaciones.modelos import Organizacion, TipoOrganizacion
from app.modulos.usuarios_roles.modelos import Usuario


@pytest.fixture
def datos_prueba(app):
    with app.app_context():
        db.create_all()

        ong = Organizacion(
            nombre="Cruz Humanitaria",
            tipo=TipoOrganizacion.ong,
            identificador_nacional="30-71122334-9",
            activo=True,
        )
        municipio = Organizacion(
            nombre="Municipio Central",
            tipo=TipoOrganizacion.municipio,
            identificador_nacional="30-99887766-1",
            activo=True,
        )
        db.session.add_all([ong, municipio])
        db.session.flush()

        usuario_ong = Usuario(
            nombre_completo="Juan ONG",
            email="juan@ong.test",
            hash_contrasena="hash",
            organizacion_id=ong.id,
            activo=True,
        )
        usuario_muni = Usuario(
            nombre_completo="Maria Muni",
            email="maria@muni.test",
            hash_contrasena="hash",
            organizacion_id=municipio.id,
            activo=True,
        )
        db.session.add_all([usuario_ong, usuario_muni])
        db.session.flush()

        emergencia = Emergencia(
            titulo="Inundación Ribereña",
            descripcion="Desborde del río",
            nivel_gravedad=NivelGravedad.media,
            zona_afectada="Ribera Este",
            municipio_id=municipio.id,
            usuario_id=usuario_muni.id,
            bonita_case_id="10042",
        )
        db.session.add(emergencia)
        db.session.flush()

        convocatoria = Convocatoria(
            emergencia_id=emergencia.id,
            coordinador_id=usuario_muni.id,
            fecha_inicio=datetime.now(UTC),
            fecha_cierre=datetime.now(UTC),
            resumen_situacion="Convocatoria activa",
            estado=EstadoConvocatoria.adjudicada,
        )
        db.session.add(convocatoria)
        db.session.flush()

        oferta = Oferta(
            convocatoria_id=convocatoria.id,
            usuario_id=usuario_ong.id,
            estado=EstadoOferta.adjudicada,
        )
        db.session.add(oferta)
        db.session.commit()

        return {
            "ong_id": ong.id,
            "municipio_id": municipio.id,
            "usuario_ong_id": usuario_ong.id,
            "emergencia_id": emergencia.id,
            "oferta_id": oferta.id,
        }


def test_sincronizar_tareas_para_ong_crea_tarea_si_oferta_esta_adjudicada(app, datos_prueba):
    with app.app_context():
        ong_id = datos_prueba["ong_id"]
        tareas = servicios.sincronizar_tareas_para_ong(ong_id)

        assert len(tareas) == 1
        tarea = tareas[0]
        assert tarea.organizacion_id == ong_id
        assert tarea.oferta_id == datos_prueba["oferta_id"]
        assert tarea.estado == EstadoTareaEjecucion.en_progreso
        assert tarea.fecha_fin is None


def test_finalizar_tarea_ong_finaliza_solo_despues_de_confirmacion_bonita(app, datos_prueba):
    with app.app_context():
        ong_id = datos_prueba["ong_id"]
        usuario_id = datos_prueba["usuario_ong_id"]
        tareas = servicios.sincronizar_tareas_para_ong(ong_id)
        tarea = tareas[0]

        with patch("app.modulos.ejecucion_cierre.servicios.finalizar_actividad_ong") as mock_bonita:
            tarea_finalizada = servicios.finalizar_tarea_ong(
                tarea_id=tarea.id,
                organizacion_id=ong_id,
                usuario_id=usuario_id,
                username="juan_ong",
                observaciones="Misión cumplida en su totalidad",
            )

            assert tarea_finalizada.estado == EstadoTareaEjecucion.finalizada
            assert tarea_finalizada.fecha_fin is not None
            assert tarea_finalizada.usuario_id == usuario_id
            assert tarea_finalizada.observaciones == "Misión cumplida en su totalidad"
            mock_bonita.assert_called_once_with(
                username="juan_ong",
                case_id="10042",
                identificador_ong="30-71122334-9",
                observaciones="Misión cumplida en su totalidad",
            )


def test_finalizar_tarea_ong_deja_cierre_pendiente_si_bonita_falla(app, datos_prueba):
    with app.app_context():
        ong_id = datos_prueba["ong_id"]
        usuario_id = datos_prueba["usuario_ong_id"]
        tarea = servicios.sincronizar_tareas_para_ong(ong_id)[0]

        with patch(
            "app.modulos.ejecucion_cierre.servicios.finalizar_actividad_ong",
            side_effect=RuntimeError("Bonita no encontró la tarea lista"),
        ):
            tarea_actualizada = servicios.finalizar_tarea_ong(
                tarea_id=tarea.id,
                organizacion_id=ong_id,
                usuario_id=usuario_id,
                username="juan@ong.test",
                observaciones="Cierre reportado",
            )

        assert tarea_actualizada.estado == EstadoTareaEjecucion.cierre_pendiente
        assert tarea_actualizada.fecha_fin is None
        assert tarea_actualizada.usuario_id == usuario_id
        assert tarea_actualizada.observaciones == "Cierre reportado"


def test_finalizar_tarea_ong_rechaza_si_no_esta_en_progreso(app, datos_prueba):
    with app.app_context():
        ong_id = datos_prueba["ong_id"]
        usuario_id = datos_prueba["usuario_ong_id"]
        tareas = servicios.sincronizar_tareas_para_ong(ong_id)
        tarea = tareas[0]

        # Finalizar una primera vez
        with patch("app.modulos.ejecucion_cierre.servicios.finalizar_actividad_ong"):
            servicios.finalizar_tarea_ong(
                tarea_id=tarea.id,
                organizacion_id=ong_id,
                usuario_id=usuario_id,
                username="juan_ong",
            )

        # Intentar finalizar de nuevo debe arrojar ConflictoDeEstado
        with pytest.raises(ConflictoDeEstado) as exc:
            servicios.finalizar_tarea_ong(
                tarea_id=tarea.id,
                organizacion_id=ong_id,
                usuario_id=usuario_id,
                username="juan_ong",
            )
        assert "no se encuentra en curso" in str(exc.value)


def test_obtener_tarea_ong_rechaza_si_pertenece_a_otra_organizacion(app, datos_prueba):
    with app.app_context():
        ong_id = datos_prueba["ong_id"]
        municipio_id = datos_prueba["municipio_id"]
        tareas = servicios.sincronizar_tareas_para_ong(ong_id)
        tarea = tareas[0]

        with pytest.raises(RecursoNoEncontrado):
            servicios.obtener_tarea_ong(tarea.id, organizacion_id=municipio_id)


def test_ruta_panel_tareas_requiere_login(cliente):
    resp = cliente.get("/ejecucion/tareas")
    # Redirige a inicio de sesión
    assert resp.status_code in (302, 401)


def test_ruta_panel_tareas_para_representante_ong(cliente_sembrado, ingresar):
    from .conftest import CABECERA_NAVEGADOR, EMAIL_REPRESENTANTE

    ingresar(EMAIL_REPRESENTANTE)
    resp = cliente_sembrado.get("/ejecucion/tareas", headers=CABECERA_NAVEGADOR)
    assert resp.status_code == 200
    cuerpo = resp.get_data(as_text=True)
    assert "Mis Tareas de Ejecución" in cuerpo
    assert "En Ejecución" in cuerpo


def test_ruta_finalizar_tarea_usa_email_como_usuario_de_bonita(
    cliente_sembrado, ingresar, enviar_formulario
):
    from .conftest import EMAIL_REPRESENTANTE

    ingresar(EMAIL_REPRESENTANTE)

    with patch(
        "app.modulos.ejecucion_cierre.rutas.servicios.finalizar_tarea_ong"
    ) as mock_finalizar:
        respuesta = enviar_formulario(
            "/ejecucion/tareas/1/finalizar",
            {"confirmacion": "y"},
        )

    assert respuesta.status_code == 302
    assert mock_finalizar.call_args.kwargs["username"] == EMAIL_REPRESENTANTE
