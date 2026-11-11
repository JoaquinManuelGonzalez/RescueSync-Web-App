"""Tests del módulo ejecucion_cierre: seguimiento y finalización de tareas de ONGs."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.core.errores import ConflictoDeEstado, RecursoNoEncontrado
from app.core.integraciones.bonita.proceso import finalizar_actividad_ong
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria, EstadoConvocatoria
from app.modulos.ejecucion_cierre import servicios
from app.modulos.ejecucion_cierre.modelos import EstadoTareaEjecucion
from app.modulos.emergencias.modelos import (
    Emergencia,
    Item,
    LoteItem,
    LoteNecesidad,
    NivelGravedad,
    TipoNecesidad,
)
from app.modulos.ofertas.modelos import (
    EstadoOferta,
    Oferta,
    OfertaLinea,
    OfertaOrganizacion,
    TipoAsignacion,
)
from app.modulos.organizaciones.modelos import Organizacion, TipoOrganizacion
from app.modulos.usuarios_roles.modelos import Usuario


def test_finalizar_actividad_usa_nombre_de_tarea_del_bpmn():
    with (
        patch(
            "app.core.integraciones.bonita.proceso.buscar_tarea_humana",
            return_value="tarea-1",
        ) as buscar_tarea,
        patch(
            "app.core.integraciones.bonita.proceso.obtener_usuario_actual_id",
            return_value="usuario-1",
        ),
        patch("app.core.integraciones.bonita.proceso.asignar_tarea"),
        patch("app.core.integraciones.bonita.proceso.ejecutar_tarea") as ejecutar,
    ):
        finalizar_actividad_ong(
            username="ong@example.test",
            case_id="caso-1",
            ofertas_finalizadas_input='{"identificador_nacional":"30-11111111-1"}',
        )

    buscar_tarea.assert_called_once_with(
        "ong@example.test",
        "caso-1",
        "Esperar finalizacion de tareas",
    )
    ejecutar.assert_called_once_with(
        "ong@example.test",
        "tarea-1",
        {"ofertasFinalizadasInput": '{"identificador_nacional":"30-11111111-1"}'},
    )


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

        item = Item(
            codigo_recurso="agua-test",
            nombre="Agua potable",
            categoria=TipoNecesidad.alimentos,
            unidad_medida="litros",
        )
        lote = LoteNecesidad(
            emergencia_id=emergencia.id,
            convocatoria_id=convocatoria.id,
            descripcion="Necesidades de prueba",
        )
        db.session.add_all([item, lote])
        db.session.flush()
        lote_item = LoteItem(
            lote_id=lote.id,
            item_id=item.id,
            cantidad_solicitada=100,
        )
        db.session.add(lote_item)
        db.session.flush()

        oferta = Oferta(
            convocatoria_id=convocatoria.id,
            usuario_id=usuario_ong.id,
            estado=EstadoOferta.adjudicada,
        )
        db.session.add(oferta)
        oferta.organizaciones_consorcio.append(
            OfertaOrganizacion(
                organizacion_id=ong.id,
                rol_consorcio="lider",
                estado_participacion="aceptada",
            )
        )
        oferta.items.append(
            OfertaLinea(
                lote_item_id=lote_item.id,
                organizacion_id=ong.id,
                tipo_asignacion=TipoAsignacion.principal,
                seleccionada=True,
                cantidad_ofrecida=80,
            )
        )
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


def test_sincronizar_tareas_no_crea_tarea_si_ninguna_linea_propia_fue_seleccionada(
    app, datos_prueba
):
    with app.app_context():
        linea = db.session.scalar(
            db.select(OfertaLinea).where(OfertaLinea.oferta_id == datos_prueba["oferta_id"])
        )
        linea.seleccionada = False
        db.session.commit()

        assert servicios.sincronizar_tareas_para_ong(datos_prueba["ong_id"]) == []


def test_sincronizar_tareas_no_asigna_a_ong_lineas_seleccionadas_de_otra_ong(app, datos_prueba):
    with app.app_context():
        ong_invitada = Organizacion(
            nombre="ONG Invitada",
            tipo=TipoOrganizacion.ong,
            identificador_nacional="30-12345678-9",
            activo=True,
        )
        db.session.add(ong_invitada)
        db.session.flush()
        db.session.add(
            OfertaOrganizacion(
                oferta_id=datos_prueba["oferta_id"],
                organizacion_id=ong_invitada.id,
                rol_consorcio="aportante",
                estado_participacion="aceptada",
            )
        )
        linea = db.session.scalar(
            db.select(OfertaLinea).where(OfertaLinea.oferta_id == datos_prueba["oferta_id"])
        )
        linea.organizacion_id = ong_invitada.id
        db.session.commit()

        assert servicios.sincronizar_tareas_para_ong(datos_prueba["ong_id"]) == []
        tareas = servicios.sincronizar_tareas_para_ong(ong_invitada.id)
        assert len(tareas) == 1
        assert tareas[0].organizacion_id == ong_invitada.id


def test_sincronizar_tareas_oculta_tarea_existente_si_se_desadjudica_su_linea(app, datos_prueba):
    with app.app_context():
        ong_id = datos_prueba["ong_id"]
        tarea = servicios.sincronizar_tareas_para_ong(ong_id)[0]
        linea = db.session.scalar(
            db.select(OfertaLinea).where(OfertaLinea.oferta_id == datos_prueba["oferta_id"])
        )
        linea.seleccionada = False
        db.session.commit()

        assert servicios.sincronizar_tareas_para_ong(ong_id) == []
        assert db.session.get(type(tarea), tarea.id) is not None
        with pytest.raises(RecursoNoEncontrado):
            servicios.obtener_tarea_ong(tarea.id, ong_id)


@pytest.mark.parametrize("estado_participacion", ["pendiente", "rechazada"])
def test_sincronizar_tareas_excluye_participacion_no_aceptada(
    app, datos_prueba, estado_participacion
):
    with app.app_context():
        ong_invitada = Organizacion(
            nombre="ONG Invitada",
            tipo=TipoOrganizacion.ong,
            identificador_nacional="30-12345678-9",
            activo=True,
        )
        db.session.add(ong_invitada)
        db.session.flush()
        usuario_invitada = Usuario(
            nombre_completo="Ana ONG Invitada",
            email="ana@ong-invitada.test",
            hash_contrasena="hash",
            organizacion_id=ong_invitada.id,
            activo=True,
        )
        db.session.add(usuario_invitada)
        db.session.flush()
        db.session.add(
            OfertaOrganizacion(
                oferta_id=datos_prueba["oferta_id"],
                organizacion_id=ong_invitada.id,
                rol_consorcio="aportante",
                estado_participacion=estado_participacion,
            )
        )
        db.session.commit()

        tareas = servicios.sincronizar_tareas_para_ong(ong_invitada.id)

        assert tareas == []


def test_sincronizar_tareas_crea_tarea_para_miembro_que_acepto(app, datos_prueba):
    with app.app_context():
        ong_invitada = Organizacion(
            nombre="ONG Invitada",
            tipo=TipoOrganizacion.ong,
            identificador_nacional="30-12345678-9",
            activo=True,
        )
        db.session.add(ong_invitada)
        db.session.flush()
        participacion = OfertaOrganizacion(
            oferta_id=datos_prueba["oferta_id"],
            organizacion_id=ong_invitada.id,
            rol_consorcio="aportante",
            estado_participacion="pendiente",
        )
        db.session.add(participacion)
        linea = db.session.scalar(
            db.select(OfertaLinea).where(OfertaLinea.oferta_id == datos_prueba["oferta_id"])
        )
        linea.organizacion_id = ong_invitada.id
        db.session.commit()

        participacion.estado_participacion = "aceptada"
        db.session.commit()

        tareas = servicios.sincronizar_tareas_para_ong(ong_invitada.id)

        assert len(tareas) == 1
        assert tareas[0].organizacion_id == ong_invitada.id
        assert tareas[0].oferta_id == datos_prueba["oferta_id"]


def test_sincronizar_tareas_es_idempotente(app, datos_prueba):
    with app.app_context():
        ong_id = datos_prueba["ong_id"]

        primera_sincronizacion = servicios.sincronizar_tareas_para_ong(ong_id)
        segunda_sincronizacion = servicios.sincronizar_tareas_para_ong(ong_id)

        assert len(primera_sincronizacion) == len(segunda_sincronizacion) == 1
        assert primera_sincronizacion[0].id == segunda_sincronizacion[0].id


def test_finalizar_tarea_registra_finalizacion_localmente(app, datos_prueba):
    with app.app_context():
        ong_id = datos_prueba["ong_id"]
        usuario_id = datos_prueba["usuario_ong_id"]
        tareas = servicios.sincronizar_tareas_para_ong(ong_id)
        tarea = tareas[0]

        tarea_finalizada = servicios.finalizar_tarea_ong(
            tarea_id=tarea.id,
            organizacion_id=ong_id,
            usuario_id=usuario_id,
            observaciones="Misión cumplida en su totalidad",
        )

        assert tarea_finalizada.estado == EstadoTareaEjecucion.finalizada
        assert tarea_finalizada.fecha_fin is not None
        assert tarea_finalizada.usuario_id == usuario_id
        assert tarea_finalizada.observaciones == "Misión cumplida en su totalidad"


def test_estado_emergencia_incluye_participantes_sin_tarea_sincronizada(app, datos_prueba):
    with app.app_context():
        ong_principal_id = datos_prueba["ong_id"]
        usuario_id = datos_prueba["usuario_ong_id"]
        ong_invitada = Organizacion(
            nombre="ONG Invitada",
            tipo=TipoOrganizacion.ong,
            identificador_nacional="30-12345678-9",
            activo=True,
        )
        db.session.add(ong_invitada)
        db.session.flush()
        usuario_invitada = Usuario(
            nombre_completo="Ana ONG Invitada",
            email="ana@ong-invitada.test",
            hash_contrasena="hash",
            organizacion_id=ong_invitada.id,
            activo=True,
        )
        db.session.add(usuario_invitada)
        db.session.flush()
        db.session.add(
            OfertaOrganizacion(
                oferta_id=datos_prueba["oferta_id"],
                organizacion_id=ong_invitada.id,
                rol_consorcio="aportante",
                estado_participacion="aceptada",
            )
        )
        db.session.add(
            OfertaLinea(
                oferta_id=datos_prueba["oferta_id"],
                lote_item_id=db.session.scalar(
                    db.select(OfertaLinea.lote_item_id).where(
                        OfertaLinea.oferta_id == datos_prueba["oferta_id"]
                    )
                ),
                organizacion_id=ong_invitada.id,
                tipo_asignacion=TipoAsignacion.apoyo,
                seleccionada=True,
                cantidad_ofrecida=20,
            )
        )
        db.session.commit()

        estado = servicios.obtener_estado_finalizacion_emergencia(datos_prueba["emergencia_id"])
        assert estado == {
            "organizaciones_participantes": 2,
            "organizaciones_finalizadas": 0,
            "todas_finalizadas": False,
        }

        tarea_principal = servicios.sincronizar_tareas_para_ong(ong_principal_id)[0]
        servicios.finalizar_tarea_ong(
            tarea_id=tarea_principal.id,
            organizacion_id=ong_principal_id,
            usuario_id=usuario_id,
        )
        estado = servicios.obtener_estado_finalizacion_emergencia(datos_prueba["emergencia_id"])
        assert estado["organizaciones_finalizadas"] == 1
        assert estado["todas_finalizadas"] is False

        tarea_invitada = servicios.sincronizar_tareas_para_ong(ong_invitada.id)[0]
        servicios.finalizar_tarea_ong(
            tarea_id=tarea_invitada.id,
            organizacion_id=ong_invitada.id,
            usuario_id=usuario_invitada.id,
        )
        estado = servicios.obtener_estado_finalizacion_emergencia(datos_prueba["emergencia_id"])
        assert estado["organizaciones_finalizadas"] == 2
        assert estado["todas_finalizadas"] is True


def test_estado_emergencia_espera_todas_las_tareas_de_cada_ong(app, datos_prueba):
    with app.app_context():
        ong_id = datos_prueba["ong_id"]
        usuario_id = datos_prueba["usuario_ong_id"]
        oferta_adicional = Oferta(
            convocatoria_id=db.session.scalar(
                db.select(Oferta.convocatoria_id).where(Oferta.id == datos_prueba["oferta_id"])
            ),
            usuario_id=usuario_id,
            estado=EstadoOferta.adjudicada,
        )
        oferta_adicional.organizaciones_consorcio.append(
            OfertaOrganizacion(
                organizacion_id=ong_id,
                rol_consorcio="lider",
                estado_participacion="aceptada",
            )
        )
        oferta_adicional.items.append(
            OfertaLinea(
                lote_item_id=db.session.scalar(
                    db.select(OfertaLinea.lote_item_id).where(
                        OfertaLinea.oferta_id == datos_prueba["oferta_id"]
                    )
                ),
                organizacion_id=ong_id,
                tipo_asignacion=TipoAsignacion.principal,
                seleccionada=True,
                cantidad_ofrecida=10,
            )
        )
        db.session.add(oferta_adicional)
        db.session.commit()

        tareas = servicios.sincronizar_tareas_para_ong(ong_id)
        assert len(tareas) == 2
        servicios.finalizar_tarea_ong(
            tarea_id=tareas[0].id,
            organizacion_id=ong_id,
            usuario_id=usuario_id,
        )

        estado = servicios.obtener_estado_finalizacion_emergencia(datos_prueba["emergencia_id"])
        assert estado["organizaciones_participantes"] == 1
        assert estado["organizaciones_finalizadas"] == 0
        assert estado["todas_finalizadas"] is False

        servicios.finalizar_tarea_ong(
            tarea_id=tareas[1].id,
            organizacion_id=ong_id,
            usuario_id=usuario_id,
        )
        estado = servicios.obtener_estado_finalizacion_emergencia(datos_prueba["emergencia_id"])
        assert estado["organizaciones_finalizadas"] == 1
        assert estado["todas_finalizadas"] is True


def test_finalizar_tarea_ong_rechaza_si_no_esta_en_progreso(app, datos_prueba):
    with app.app_context():
        ong_id = datos_prueba["ong_id"]
        usuario_id = datos_prueba["usuario_ong_id"]
        tareas = servicios.sincronizar_tareas_para_ong(ong_id)
        tarea = tareas[0]

        servicios.finalizar_tarea_ong(
            tarea_id=tarea.id,
            organizacion_id=ong_id,
            usuario_id=usuario_id,
        )

        with pytest.raises(ConflictoDeEstado) as exc:
            servicios.finalizar_tarea_ong(
                tarea_id=tarea.id,
                organizacion_id=ong_id,
                usuario_id=usuario_id,
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


def test_ruta_finalizar_tarea_no_pasa_credenciales_de_bonita(
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
    assert "username" not in mock_finalizar.call_args.kwargs
