"""Pruebas unitarias y de integración para la capa de servicios de ofertas."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.errores import (
    ConflictoDeEstado,
    PermisoDenegado,
    RecursoNoEncontrado,
    ReglaDeNegocioIncumplida,
    SolicitudInvalida,
)
from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria, EstadoConvocatoria
from app.modulos.emergencias.modelos import (
    Emergencia,
    EstadoEmergencia,
    Item,
    LoteItem,
    LoteNecesidad,
    NivelGravedad,
    TipoNecesidad,
)
from app.modulos.ofertas.modelos import EstadoOferta
from app.modulos.ofertas.servicios import (
    aceptar_invitacion,
    crear_oferta,
    listar_ofertas_por_convocatoria,
    modificar_oferta,
    obtener_historial_de_oferta,
    obtener_oferta_por_id,
    obtener_ofertas_consolidadas_para_bonita,
    rechazar_invitacion,
    retirar_oferta,
)
from app.modulos.organizaciones.modelos import (
    Inventario,
    InventarioItem,
    Organizacion,
    TipoOrganizacion,
)
from app.modulos.usuarios_roles.modelos import Usuario


@pytest.fixture
def datos_base(app):
    """Inicializa la base de datos y crea entidades de soporte para las pruebas."""
    with app.app_context():
        db.create_all()

        # Usuario
        usuario = Usuario(
            nombre_completo="Juan Perez",
            email="juan@ongsolidaria.org",
            hash_contrasena="hash_dummy",
            activo=True,
        )
        db.session.add(usuario)

        # ONGs
        ong1 = Organizacion(
            nombre="Cruz Solidaria",
            tipo=TipoOrganizacion.ong,
            activo=True,
        )
        ong2 = Organizacion(
            nombre="Manos Unidas",
            tipo=TipoOrganizacion.ong,
            activo=True,
        )
        municipio = Organizacion(
            nombre="Municipio Central",
            tipo=TipoOrganizacion.municipio,
            activo=True,
        )
        db.session.add_all([ong1, ong2, municipio])
        db.session.flush()

        # Emergencia
        emergencia = Emergencia(
            titulo="Inundación Ribereña",
            descripcion="Crecida de río con familias evacuadas.",
            nivel_gravedad=NivelGravedad.alta,
            zona_afectada="Sector Este",
            estado=EstadoEmergencia.activa,
            municipio_id=municipio.id,
            usuario_id=usuario.id,
        )
        db.session.add(emergencia)
        db.session.flush()

        # Item del catálogo y Lote
        item_agua = Item(
            nombre="Agua potable",
            categoria=TipoNecesidad.agua,
            unidad_medida="litros",
        )
        item_frazadas = Item(
            nombre="Kits de abrigo",
            categoria=TipoNecesidad.abrigo,
            unidad_medida="unidades",
        )
        db.session.add_all([item_agua, item_frazadas])
        db.session.flush()

        lote = LoteNecesidad(
            emergencia_id=emergencia.id,
            descripcion="Lote de primeros auxilios",
        )
        db.session.add(lote)
        db.session.flush()

        lote_item1 = LoteItem(
            lote_id=lote.id,
            item_id=item_agua.id,
            cantidad_solicitada=Decimal("5000.00"),
        )
        lote_item2 = LoteItem(
            lote_id=lote.id,
            item_id=item_frazadas.id,
            cantidad_solicitada=Decimal("500.00"),
        )
        db.session.add_all([lote_item1, lote_item2])
        db.session.flush()

        inventario1 = Inventario(
            organizacion_id=ong1.id,
            nombre="Depósito Cruz Solidaria",
        )
        inventario2 = Inventario(
            organizacion_id=ong2.id,
            nombre="Depósito Manos Unidas",
        )
        db.session.add_all([inventario1, inventario2])
        db.session.flush()
        db.session.add_all(
            [
                InventarioItem(
                    inventario_id=inventario1.id,
                    item_id=item_agua.id,
                    cantidad_disponible=Decimal("4000"),
                ),
                InventarioItem(
                    inventario_id=inventario2.id,
                    item_id=item_frazadas.id,
                    cantidad_disponible=Decimal("500"),
                ),
            ]
        )

        # Convocatoria abierta y vigente
        ahora = datetime.now(UTC)
        convocatoria_abierta = Convocatoria(
            emergencia_id=emergencia.id,
            coordinador_id=usuario.id,
            fecha_inicio=ahora - timedelta(hours=1),
            fecha_cierre=ahora + timedelta(days=2),
            estado=EstadoConvocatoria.abierta,
        )

        # Convocatoria cerrada
        convocatoria_cerrada = Convocatoria(
            emergencia_id=emergencia.id,
            coordinador_id=usuario.id,
            fecha_inicio=ahora - timedelta(days=5),
            fecha_cierre=ahora - timedelta(days=1),
            estado=EstadoConvocatoria.cerrada,
        )
        db.session.add_all([convocatoria_abierta, convocatoria_cerrada])
        db.session.commit()

        yield {
            "usuario_id": usuario.id,
            "ong1_id": ong1.id,
            "ong2_id": ong2.id,
            "municipio_id": municipio.id,
            "emergencia_id": emergencia.id,
            "lote_item1_id": lote_item1.id,
            "lote_item2_id": lote_item2.id,
            "convocatoria_abierta_id": convocatoria_abierta.id,
            "convocatoria_cerrada_id": convocatoria_cerrada.id,
        }

        db.session.remove()
        db.drop_all()


def test_crear_oferta_individual_exitosa(app, datos_base):
    with app.app_context():
        # Puede pasarse directamente organizacion_id
        oferta = crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong1_id"],
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 1000}],
            observaciones="Entrega en 24 horas",
        )

        assert oferta.id is not None
        assert oferta.version == 1
        assert oferta.estado == EstadoOferta.presentada
        assert len(oferta.organizaciones_consorcio) == 1
        assert oferta.organizaciones_consorcio[0].rol_consorcio == "lider"
        assert len(oferta.items) == 1
        assert oferta.items[0].cantidad_ofrecida == Decimal("1000")


def test_oferta_conjunta_queda_pendiente_hasta_aceptacion(app, datos_base):
    with app.app_context():
        oferta = crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong1_id"],
            organizaciones_ids=[datos_base["ong2_id"]],
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 1000}],
        )

        assert oferta.estado == EstadoOferta.pendiente
        invitacion = next(
            miembro
            for miembro in oferta.organizaciones_consorcio
            if miembro.organizacion_id == datos_base["ong2_id"]
        )
        assert invitacion.estado_participacion == "pendiente"

        aceptada = aceptar_invitacion(
            oferta.id,
            organizacion_id=datos_base["ong2_id"],
            usuario_id=datos_base["usuario_id"],
            items=[{"lote_item_id": datos_base["lote_item2_id"], "cantidad_ofrecida": 50}],
        )

        assert aceptada.estado == EstadoOferta.presentada
        assert len(aceptada.items) == 2
        assert {
            linea.organizacion_id for linea in aceptada.items
        } == {datos_base["ong1_id"], datos_base["ong2_id"]}


def test_oferta_conjunta_no_supera_necesidad_acumulada(app, datos_base):
    with app.app_context():
        lote_item = db.session.get(LoteItem, datos_base["lote_item1_id"])
        inventario = db.session.execute(
            db.select(Inventario).where(Inventario.organizacion_id == datos_base["ong2_id"])
        ).scalar_one()
        db.session.add(
            InventarioItem(
                inventario_id=inventario.id,
                item_id=lote_item.item_id,
                cantidad_disponible=Decimal("2000"),
            )
        )
        db.session.commit()

        oferta = crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong1_id"],
            organizaciones_ids=[datos_base["ong2_id"]],
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 4000}],
        )

        with pytest.raises(ReglaDeNegocioIncumplida) as exc_info:
            aceptar_invitacion(
                oferta.id,
                organizacion_id=datos_base["ong2_id"],
                usuario_id=datos_base["usuario_id"],
                items=[
                    {"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 1001}
                ],
            )

        assert exc_info.value.codigo == "OFERTA_CONJUNTA_SUPERA_NECESIDAD"


def test_organizacion_puede_rechazar_invitacion(app, datos_base):
    with app.app_context():
        oferta = crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong1_id"],
            organizaciones_ids=[datos_base["ong2_id"]],
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 1000}],
        )

        rechazada = rechazar_invitacion(
            oferta.id,
            organizacion_id=datos_base["ong2_id"],
            usuario_id=datos_base["usuario_id"],
        )

        assert rechazada.estado == EstadoOferta.rechazada
        miembro = next(
            miembro
            for miembro in rechazada.organizaciones_consorcio
            if miembro.organizacion_id == datos_base["ong2_id"]
        )
        assert miembro.estado_participacion == "rechazada"
        with pytest.raises(ConflictoDeEstado):
            aceptar_invitacion(
                oferta.id,
                organizacion_id=datos_base["ong2_id"],
                usuario_id=datos_base["usuario_id"],
                items=[{"lote_item_id": datos_base["lote_item2_id"], "cantidad_ofrecida": 50}],
            )


def test_no_se_puede_responder_invitacion_de_oferta_retirada(app, datos_base):
    with app.app_context():
        oferta = crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong1_id"],
            organizaciones_ids=[datos_base["ong2_id"]],
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 1000}],
        )
        retirar_oferta(oferta.id, organizacion_id=datos_base["ong1_id"])

        with pytest.raises(ConflictoDeEstado):
            aceptar_invitacion(
                oferta.id,
                organizacion_id=datos_base["ong2_id"],
                usuario_id=datos_base["usuario_id"],
                items=[{"lote_item_id": datos_base["lote_item2_id"], "cantidad_ofrecida": 50}],
            )
        with pytest.raises(ConflictoDeEstado):
            rechazar_invitacion(
                oferta.id,
                organizacion_id=datos_base["ong2_id"],
                usuario_id=datos_base["usuario_id"],
            )


def test_miembro_solo_modifica_sus_lineas_y_puede_retirar(app, datos_base):
    with app.app_context():
        oferta = crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong1_id"],
            organizaciones_ids=[datos_base["ong2_id"]],
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 1000}],
        )
        aceptar_invitacion(
            oferta.id,
            organizacion_id=datos_base["ong2_id"],
            usuario_id=datos_base["usuario_id"],
            items=[{"lote_item_id": datos_base["lote_item2_id"], "cantidad_ofrecida": 50}],
        )

        modificar_oferta(
            oferta.id,
            organizacion_id=datos_base["ong2_id"],
            items=[{"lote_item_id": datos_base["lote_item2_id"], "cantidad_ofrecida": 75}],
        )
        db.session.expire_all()
        oferta_actualizada = obtener_oferta_por_id(oferta.id)
        cantidades = {
            linea.organizacion_id: linea.cantidad_ofrecida for linea in oferta_actualizada.items
        }
        assert cantidades[datos_base["ong1_id"]] == Decimal("1000")
        assert cantidades[datos_base["ong2_id"]] == Decimal("75")

        retirada = retirar_oferta(oferta.id, organizacion_id=datos_base["ong2_id"])
        assert retirada.estado == EstadoOferta.retirada


def test_crear_oferta_falla_sin_organizacion(app, datos_base):
    with app.app_context():
        with pytest.raises(SolicitudInvalida) as exc_info:
            crear_oferta(
                convocatoria_id=datos_base["convocatoria_abierta_id"],
                usuario_id=datos_base["usuario_id"],
                organizacion_id=0,
                items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 500}],
            )

        assert "Debe especificarse la organización" in exc_info.value.mensaje


def test_crear_oferta_falla_fuera_de_ventana(app, datos_base):
    with app.app_context():
        with pytest.raises(ReglaDeNegocioIncumplida) as exc_info:
            crear_oferta(
                convocatoria_id=datos_base["convocatoria_cerrada_id"],
                usuario_id=datos_base["usuario_id"],
                organizacion_id=datos_base["ong1_id"],
                items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 500}],
            )

        assert exc_info.value.codigo == "OFERTA_FUERA_DE_VENTANA"


def test_crear_oferta_falla_si_no_es_ong(app, datos_base):
    with app.app_context():
        with pytest.raises(ReglaDeNegocioIncumplida) as exc_info:
            crear_oferta(
                convocatoria_id=datos_base["convocatoria_abierta_id"],
                usuario_id=datos_base["usuario_id"],
                organizacion_id=datos_base["municipio_id"],
                items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 500}],
            )

        assert "debe ser de tipo ONG" in exc_info.value.mensaje


def test_crear_oferta_falla_si_supera_cantidad_solicitada(app, datos_base):
    with app.app_context():
        # lote_item1 tiene 5000 solicitado
        with pytest.raises(ReglaDeNegocioIncumplida) as exc_info:
            crear_oferta(
                convocatoria_id=datos_base["convocatoria_abierta_id"],
                usuario_id=datos_base["usuario_id"],
                organizacion_id=datos_base["ong1_id"],
                items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 6000}],
            )

        assert "supera la cantidad requerida" in exc_info.value.mensaje


def test_crear_oferta_falla_si_supera_stock_local(app, datos_base):
    with app.app_context():
        with pytest.raises(ReglaDeNegocioIncumplida) as exc_info:
            crear_oferta(
                convocatoria_id=datos_base["convocatoria_abierta_id"],
                usuario_id=datos_base["usuario_id"],
                organizacion_id=datos_base["ong1_id"],
                items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 4001}],
            )

        assert "stock disponible" in exc_info.value.mensaje


def test_crear_oferta_falla_si_recurso_no_esta_en_inventario(app, datos_base):
    with app.app_context():
        with pytest.raises(ReglaDeNegocioIncumplida) as exc_info:
            crear_oferta(
                convocatoria_id=datos_base["convocatoria_abierta_id"],
                usuario_id=datos_base["usuario_id"],
                organizacion_id=datos_base["ong1_id"],
                items=[{"lote_item_id": datos_base["lote_item2_id"], "cantidad_ofrecida": 1}],
            )

        assert "no tiene este recurso" in exc_info.value.mensaje


def test_modificar_oferta_incrementa_version(app, datos_base):
    with app.app_context():
        oferta = crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong1_id"],
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 1000}],
        )

        modificada = modificar_oferta(
            oferta.id,
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 1500}],
            observaciones="Ampliamos a 1500 litros",
        )

        assert modificada.version == 2
        assert modificada.estado == EstadoOferta.presentada
        assert modificada.observaciones == "Ampliamos a 1500 litros"
        assert modificada.items[0].cantidad_ofrecida == Decimal("1500")


def test_modificar_oferta_no_crea_nueva_version_si_no_hubo_cambios(app, datos_base):
    with app.app_context():
        oferta = crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong1_id"],
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 1000}],
            observaciones="Entrega en 24 horas",
        )

        sin_cambios = modificar_oferta(
            oferta.id,
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 1000}],
            observaciones="Entrega en 24 horas",
            organizacion_id=datos_base["ong1_id"],
            usuario_id=datos_base["usuario_id"],
        )

        assert sin_cambios.version == 1
        assert sin_cambios.estado == EstadoOferta.presentada
        assert sin_cambios.observaciones == "Entrega en 24 horas"


def test_modificar_oferta_rechaza_organizacion_ajena(app, datos_base):
    with app.app_context():
        oferta = crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong1_id"],
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 1000}],
        )

        with pytest.raises(PermisoDenegado):
            modificar_oferta(
                oferta.id,
                organizacion_id=datos_base["ong2_id"],
                observaciones="Intento de modificación ajena",
            )


def test_retirar_oferta_cambia_estado(app, datos_base):
    with app.app_context():
        oferta = crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong1_id"],
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 1000}],
        )

        retirada = retirar_oferta(oferta.id)
        assert retirada.estado == EstadoOferta.retirada

        # No se puede volver a retirar
        with pytest.raises(ConflictoDeEstado):
            retirar_oferta(oferta.id)

        # No se puede modificar una oferta retirada
        with pytest.raises(ConflictoDeEstado):
            modificar_oferta(oferta.id, observaciones="intento")


def test_retirar_oferta_rechaza_organizacion_ajena(app, datos_base):
    with app.app_context():
        oferta = crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong1_id"],
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 1000}],
        )

        with pytest.raises(PermisoDenegado):
            retirar_oferta(oferta.id, organizacion_id=datos_base["ong2_id"])


def test_listar_ofertas_por_convocatoria(app, datos_base):
    with app.app_context():
        of1 = crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong1_id"],
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 500}],
        )
        of2 = crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong2_id"],
            items=[{"lote_item_id": datos_base["lote_item2_id"], "cantidad_ofrecida": 100}],
        )
        retirar_oferta(of2.id)

        activas = listar_ofertas_por_convocatoria(
            datos_base["convocatoria_abierta_id"], incluir_retiradas=False
        )
        assert len(activas) == 1
        assert activas[0].id == of1.id

        todas = listar_ofertas_por_convocatoria(
            datos_base["convocatoria_abierta_id"], incluir_retiradas=True
        )
        assert len(todas) == 2


def test_obtener_oferta_por_id_no_existente(app, datos_base):
    with app.app_context():
        with pytest.raises(RecursoNoEncontrado):
            obtener_oferta_por_id(999999)


def test_obtener_ofertas_consolidadas_para_bonita(app, datos_base):
    with app.app_context():
        # Primera oferta individual
        crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong1_id"],
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 2000}],
        )

        # Segunda oferta individual
        crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong2_id"],
            items=[{"lote_item_id": datos_base["lote_item2_id"], "cantidad_ofrecida": 350}],
        )

        resultado = obtener_ofertas_consolidadas_para_bonita(datos_base["convocatoria_abierta_id"])

        assert resultado["convocatoria_id"] == datos_base["convocatoria_abierta_id"]
        assert resultado["emergencia_id"] == datos_base["emergencia_id"]
        assert "ventana_cerrada_en" in resultado
        assert len(resultado["ofertas"]) == 2

        of1 = [o for o in resultado["ofertas"] if o["ong_id"] == datos_base["ong1_id"]][0]
        assert of1["ong_nombre"] == "Cruz Solidaria"
        assert of1["tipo_recurso"] == "agua"
        assert of1["cantidad"] == 2000.0
        assert of1["unidad"] == "litros"
        assert not of1["es_consorcio"]
        assert "consorcio_con" not in of1

        of2 = [o for o in resultado["ofertas"] if o["ong_id"] == datos_base["ong2_id"]][0]
        assert of2["ong_nombre"] == "Manos Unidas"
        assert of2["tipo_recurso"] == "abrigo"
        assert of2["cantidad"] == 350.0
        assert of2["unidad"] == "unidades"
        assert not of2["es_consorcio"]
        assert "consorcio_con" not in of2


def test_historial_de_versiones_trazabilidad(app, datos_base):
    with app.app_context():
        # Crear oferta v1
        oferta = crear_oferta(
            convocatoria_id=datos_base["convocatoria_abierta_id"],
            usuario_id=datos_base["usuario_id"],
            organizacion_id=datos_base["ong1_id"],
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 500}],
            observaciones="Versión inicial 500L",
        )
        assert oferta.version == 1

        # Al crearse, todavía no tiene versiones archivadas
        historial_inicial = obtener_historial_de_oferta(oferta.id)
        assert len(historial_inicial) == 0

        # Modificar a v2
        modificar_oferta(
            oferta.id,
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 800}],
            observaciones="Versión 2: subimos a 800L",
            usuario_id=datos_base["usuario_id"],
        )

        historial = obtener_historial_de_oferta(oferta.id)
        assert len(historial) == 1
        snap1 = historial[0]
        assert snap1.version == 1
        assert snap1.estado_anterior == "presentada"
        assert snap1.observaciones_anteriores == "Versión inicial 500L"
        items_snap1 = json.loads(snap1.items_snapshot)
        assert len(items_snap1) == 1
        assert items_snap1[0]["cantidad_ofrecida"] == 500.0

        # Modificar a v3
        modificar_oferta(
            oferta.id,
            items=[{"lote_item_id": datos_base["lote_item1_id"], "cantidad_ofrecida": 1200}],
            observaciones="Versión 3: subimos a 1200L",
            usuario_id=datos_base["usuario_id"],
        )

        historial_v3 = obtener_historial_de_oferta(oferta.id)
        assert len(historial_v3) == 2
        assert historial_v3[0].version == 1
        assert historial_v3[1].version == 2
        assert historial_v3[1].estado_anterior == "presentada"
        assert historial_v3[1].observaciones_anteriores == "Versión 2: subimos a 800L"
        items_snap2 = json.loads(historial_v3[1].items_snapshot)
        assert items_snap2[0]["cantidad_ofrecida"] == 800.0
