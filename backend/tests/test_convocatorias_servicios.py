"""Pruebas del servicio de apertura de convocatorias."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.errores import ConflictoDeEstado, ReglaDeNegocioIncumplida, SolicitudInvalida
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria, EstadoConvocatoria
from app.modulos.convocatorias.rutas import _parsear_fecha_cierre
from app.modulos.convocatorias.servicios import (
    cerrar_convocatoria,
    cerrar_convocatorias_vencidas,
    crear_convocatoria,
)
from app.modulos.emergencias.lotes.servicios import crear_lotes
from app.modulos.emergencias.modelos import (
    Emergencia,
    EstadoEmergencia,
    EstadoLote,
    Item,
    LoteNecesidad,
    NivelGravedad,
    TipoNecesidad,
)
from app.modulos.organizaciones.modelos import Organizacion, TipoOrganizacion
from app.modulos.usuarios_roles.modelos import Usuario

from .conftest import EMAIL_COORDINADOR


def test_parsear_fecha_cierre_interpreta_fecha_local_como_hora_de_argentina():
    assert _parsear_fecha_cierre("2026-09-28", "12:00") == datetime(2026, 9, 28, 15, 0, tzinfo=UTC)


def test_parsear_fecha_cierre_rechaza_fecha_que_no_llega_en_formato_iso():
    with pytest.raises(SolicitudInvalida) as error:
        _parsear_fecha_cierre("28/09/2026", "12:00")

    assert error.value.detalle == {"campo": "fecha_cierre"}


@pytest.fixture
def datos_convocatoria(app):
    with app.app_context():
        db.create_all()
        municipio = Organizacion(
            nombre="Municipio de prueba",
            tipo=TipoOrganizacion.municipio,
            activo=True,
        )
        usuario = Usuario(
            nombre_completo="Coordinadora de prueba",
            email="coordinadora@prueba.org",
            hash_contrasena="hash-prueba",
            activo=True,
        )
        db.session.add_all([municipio, usuario])
        db.session.flush()

        emergencia = Emergencia(
            titulo="Inundación de prueba",
            descripcion="Varias familias afectadas por la crecida.",
            nivel_gravedad=NivelGravedad.alta,
            zona_afectada="Zona norte",
            estado=EstadoEmergencia.en_evaluacion,
            municipio_id=municipio.id,
            usuario_id=usuario.id,
        )
        db.session.add(emergencia)
        db.session.flush()

        lotes = [
            LoteNecesidad(emergencia_id=emergencia.id, descripcion="Agua"),
            LoteNecesidad(emergencia_id=emergencia.id, descripcion="Abrigo"),
        ]
        db.session.add_all(lotes)
        db.session.commit()

        datos = {
            "emergencia_id": emergencia.id,
            "coordinador_id": usuario.id,
            "lote_ids": [lote.id for lote in lotes],
        }
        yield datos

        db.session.remove()
        db.drop_all()


def _crear(datos_convocatoria, **sobrescrituras):
    argumentos = {
        "emergencia_id": datos_convocatoria["emergencia_id"],
        "coordinador_id": datos_convocatoria["coordinador_id"],
        "resumen_situacion": "Familias evacuadas por la crecida del río.",
        "fecha_cierre": datetime.now(UTC) + timedelta(days=2),
    }
    argumentos.update(sobrescrituras)
    return crear_convocatoria(**argumentos)


def test_crear_convocatoria_publica_y_marca_todos_los_lotes(app, datos_convocatoria):
    with app.app_context():
        convocatoria = _crear(datos_convocatoria)

        assert convocatoria.id is not None
        assert convocatoria.estado == EstadoConvocatoria.abierta
        assert {lote.id for lote in convocatoria.lotes} == set(datos_convocatoria["lote_ids"])
        emergencia = db.session.get(Emergencia, datos_convocatoria["emergencia_id"])
        assert emergencia.estado == EstadoEmergencia.activa
        assert convocatoria.resumen_situacion == "Familias evacuadas por la crecida del río."
        assert convocatoria.fecha_inicio <= datetime.now(UTC).replace(tzinfo=None)
        assert convocatoria.fecha_cierre > convocatoria.fecha_inicio
        estados = (
            db.session.execute(
                db.select(LoteNecesidad.estado)
                .where(LoteNecesidad.id.in_(datos_convocatoria["lote_ids"]))
                .order_by(LoteNecesidad.id)
            )
            .scalars()
            .all()
        )
        assert estados == [EstadoLote.en_convocatoria, EstadoLote.en_convocatoria]


@pytest.mark.parametrize(
    ("sobrescrituras", "campo"),
    [
        ({"emergencia_id": None}, "emergencia_id"),
        ({"coordinador_id": None}, "coordinador_id"),
        ({"resumen_situacion": "  "}, "resumen_situacion"),
        ({"fecha_cierre": datetime.now(UTC) - timedelta(minutes=1)}, "fecha_cierre"),
    ],
)
def test_crear_convocatoria_rechaza_datos_invalidos(app, datos_convocatoria, sobrescrituras, campo):
    with app.app_context(), pytest.raises(SolicitudInvalida) as error:
        _crear(datos_convocatoria, **sobrescrituras)

    assert error.value.detalle == {"campo": campo}
    assert db.session.scalar(db.select(db.func.count()).select_from(Convocatoria)) == 0


def test_crear_convocatoria_exige_lotes(app, datos_convocatoria):
    with app.app_context():
        db.session.execute(
            db.delete(LoteNecesidad).where(
                LoteNecesidad.emergencia_id == datos_convocatoria["emergencia_id"]
            )
        )
        db.session.commit()

        with pytest.raises(SolicitudInvalida) as error:
            _crear(datos_convocatoria)

        assert error.value.detalle == {"campo": "lotes"}


def test_crear_lote_rechaza_emergencia_en_revision(app, datos_convocatoria):
    with app.app_context(), pytest.raises(ReglaDeNegocioIncumplida):
        crear_lotes(
            emergencia_id=datos_convocatoria["emergencia_id"],
            descripcion="No corresponde en revisión",
            items=[],
        )


def test_crear_lote_pasa_emergencia_registrada_a_revision(app, datos_convocatoria):
    with app.app_context():
        emergencia = db.session.get(Emergencia, datos_convocatoria["emergencia_id"])
        emergencia.estado = EstadoEmergencia.registrada
        item = Item(
            codigo_recurso="RSR-RECURSO_NUEVO_DE_PRUEBA",
            nombre="Recurso nuevo de prueba",
            categoria=TipoNecesidad.agua,
            unidad_medida="litros",
        )
        db.session.add(item)
        db.session.commit()

        crear_lotes(
            emergencia_id=emergencia.id,
            descripcion="Lote nuevo",
            items=[{"item_id": item.id, "cantidad_solicitada": "10"}],
        )

        assert emergencia.estado == EstadoEmergencia.en_evaluacion


def test_crear_convocatoria_rechaza_emergencia_fuera_de_evaluacion(app, datos_convocatoria):
    with app.app_context():
        emergencia = db.session.get(Emergencia, datos_convocatoria["emergencia_id"])
        emergencia.estado = EstadoEmergencia.registrada
        db.session.commit()

        with pytest.raises(ReglaDeNegocioIncumplida):
            _crear(datos_convocatoria)


def test_crear_convocatoria_excluye_lotes_de_rondas_anteriores(app, datos_convocatoria):
    with app.app_context():
        lotes = db.session.scalars(
            db.select(LoteNecesidad)
            .where(LoteNecesidad.emergencia_id == datos_convocatoria["emergencia_id"])
            .order_by(LoteNecesidad.id)
        ).all()
        lotes[0].estado = EstadoLote.en_convocatoria
        db.session.commit()

        convocatoria = _crear(datos_convocatoria)

        assert [lote.id for lote in convocatoria.lotes] == [lotes[1].id]


def test_crear_convocatoria_exige_lotes_pendientes(app, datos_convocatoria):
    with app.app_context():
        db.session.execute(
            db.update(LoteNecesidad)
            .where(LoteNecesidad.emergencia_id == datos_convocatoria["emergencia_id"])
            .values(estado=EstadoLote.en_convocatoria)
        )
        db.session.commit()

        with pytest.raises(ConflictoDeEstado):
            _crear(datos_convocatoria)


def test_cerrar_convocatoria_habilita_una_ronda_nueva_con_lotes_nuevos(app, datos_convocatoria):
    with app.app_context():
        convocatoria_anterior = _crear(datos_convocatoria)
        cerrar_convocatoria(convocatoria_anterior.id)

        emergencia = db.session.get(Emergencia, datos_convocatoria["emergencia_id"])
        assert convocatoria_anterior.estado == EstadoConvocatoria.cerrada
        assert emergencia.estado == EstadoEmergencia.registrada

        item_nuevo = Item(
            codigo_recurso="RSR-AGUA_PARA_NUEVA_RONDA",
            nombre="Agua para nueva ronda",
            categoria=TipoNecesidad.agua,
            unidad_medida="litros",
        )
        db.session.add(item_nuevo)
        db.session.commit()
        lote_nuevo = crear_lotes(
            emergencia_id=emergencia.id,
            descripcion="Necesidades corregidas",
            items=[{"item_id": item_nuevo.id, "cantidad_solicitada": "250"}],
        )[0]
        assert emergencia.estado == EstadoEmergencia.en_evaluacion

        convocatoria_nueva = _crear(datos_convocatoria)

        assert [lote.id for lote in convocatoria_nueva.lotes] == [lote_nuevo.id]
        assert {lote.id for lote in convocatoria_anterior.lotes} == set(
            datos_convocatoria["lote_ids"]
        )


def test_vencimiento_cierra_convocatoria_y_espera_evaluacion_de_cobertura(app, datos_convocatoria):
    with app.app_context():
        convocatoria = _crear(datos_convocatoria)
        convocatoria.fecha_cierre = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()

        cerradas = cerrar_convocatorias_vencidas(emergencia_id=datos_convocatoria["emergencia_id"])

        emergencia = db.session.get(Emergencia, datos_convocatoria["emergencia_id"])
        assert cerradas == 1
        assert convocatoria.estado == EstadoConvocatoria.cerrada
        assert emergencia.estado == EstadoEmergencia.activa


def test_coordinador_puede_cerrar_convocatoria_desde_el_detalle(
    app, base_de_datos, cliente_sembrado, ingresar, enviar_formulario
):
    with app.app_context():
        convocatoria = db.session.scalar(
            db.select(Convocatoria).where(Convocatoria.observaciones == "SEED_DEMO_OFERTAS")
        )
        assert convocatoria is not None
        convocatoria_id = convocatoria.id
        emergencia_id = convocatoria.emergencia_id

    assert ingresar(EMAIL_COORDINADOR).status_code == 200
    respuesta = enviar_formulario(f"/convocatorias/{convocatoria_id}/cerrar")

    assert respuesta.status_code == 302
    with app.app_context():
        convocatoria = db.session.get(Convocatoria, convocatoria_id)
        emergencia = db.session.get(Emergencia, emergencia_id)
        assert convocatoria.estado == EstadoConvocatoria.cerrada
        assert emergencia.estado == EstadoEmergencia.registrada


def test_coordinador_ve_acciones_de_lotes_segun_estado_de_emergencia(
    app, base_de_datos, cliente_sembrado, ingresar
):
    with app.app_context():
        municipio = db.session.scalar(
            db.select(Organizacion).where(Organizacion.tipo == TipoOrganizacion.municipio)
        )
        coordinador = db.session.scalar(
            db.select(Usuario).where(Usuario.email == EMAIL_COORDINADOR)
        )
        emergencia = Emergencia(
            titulo="Emergencia para revisar acciones de lotes",
            descripcion="Necesidad de prueba.",
            nivel_gravedad=NivelGravedad.media,
            zona_afectada="Zona de prueba",
            estado=EstadoEmergencia.registrada,
            municipio_id=municipio.id,
            usuario_id=coordinador.id,
        )
        db.session.add(emergencia)
        db.session.commit()
        emergencia_id = emergencia.id

    assert ingresar(EMAIL_COORDINADOR).status_code == 200
    headers = {"Accept": "text/html,application/xhtml+xml"}
    detalle = cliente_sembrado.get(f"/emergencias/{emergencia_id}", headers=headers)

    assert detalle.status_code == 200
    cuerpo = detalle.get_data(as_text=True)
    assert f"/lotes/emergencias/{emergencia_id}/lotes/nuevo" in cuerpo
    assert f"/convocatorias/emergencias/{emergencia_id}/nueva" not in cuerpo

    formulario_lote = cliente_sembrado.get(
        f"/lotes/emergencias/{emergencia_id}/lotes/nuevo", headers=headers
    )
    assert b'id="form-lote"' in formulario_lote.data

    with app.app_context():
        emergencia = db.session.get(Emergencia, emergencia_id)
        emergencia.estado = EstadoEmergencia.en_evaluacion
        db.session.commit()

    formulario_bloqueado = cliente_sembrado.get(
        f"/lotes/emergencias/{emergencia_id}/lotes/nuevo", headers=headers
    )
    assert (
        b"Solo se pueden generar lotes cuando la emergencia est\xc3\xa1 registrada"
        in formulario_bloqueado.data
    )
    assert b'id="form-lote"' not in formulario_bloqueado.data


def test_formulario_de_convocatoria_esta_disponible_desde_la_emergencia(
    app, base_de_datos, cliente_sembrado, ingresar
):
    with app.app_context():
        emergencia = db.session.execute(
            db.select(Emergencia).where(
                Emergencia.titulo == "Temporal severo con voladura de techos en Chascomús"
            )
        ).scalar_one_or_none()
        assert emergencia is not None

    respuesta_login = ingresar(EMAIL_COORDINADOR)
    assert respuesta_login.status_code == 200

    respuesta = cliente_sembrado.get(
        f"/convocatorias/emergencias/{emergencia.id}/nueva",
        headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "Ya hay una convocatoria abierta para esta emergencia" in cuerpo
    assert "Resumen de la situación" not in cuerpo
    assert "Fecha límite para presentar ofertas" not in cuerpo
