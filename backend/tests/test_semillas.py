"""Datos semilla: idempotencia y sincronia entre el catalogo en codigo y la base."""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.acceso.permisos import CATALOGO_DE_PERMISOS, PERMISOS_POR_ROL, NombreRol
from app.core.semillas import SEEDERS, importar_seeders
from app.extensiones import db
from app.modulos.convocatorias.modelos import (
    Convocatoria,
    DecisionCobertura,
    EstadoConvocatoria,
)
from app.modulos.emergencias.modelos import Emergencia, EstadoEmergencia
from app.modulos.notificaciones.modelos import Notificacion
from app.modulos.ofertas.modelos import Oferta, TipoAsignacion
from app.modulos.organizaciones.modelos import Inventario, InventarioItem, Organizacion
from app.modulos.usuarios_roles.modelos import Permiso, Rol, Usuario


def _contar(modelo) -> int:
    return db.session.execute(select(func.count()).select_from(modelo)).scalar_one()


def _volver_a_sembrar() -> None:
    importar_seeders()
    for seeder in SEEDERS:
        seeder.funcion()
    db.session.commit()


def test_la_semilla_carga_el_catalogo_completo(app, base_de_datos: None) -> None:
    with app.app_context():
        assert _contar(Permiso) == len(CATALOGO_DE_PERMISOS)
        assert _contar(Rol) == len(NombreRol)
        assert _contar(Organizacion) == 10
        assert _contar(Inventario) == 5
        assert _contar(InventarioItem) == 53
        assert _contar(Usuario) == 11
        assert _contar(Notificacion) == 8


def test_la_semilla_incluye_el_caso_de_prueba_de_seleccion_sin_bonita(
    app, base_de_datos: None
) -> None:
    with app.app_context():
        emergencia = Emergencia.query.filter_by(
            titulo="PRUEBA - Selección municipal de ofertas en Pergamino"
        ).one()
        convocatoria = Convocatoria.query.filter_by(
            observaciones="SEED_PRUEBA_SELECCION_SIN_BONITA"
        ).one()

        assert emergencia.bonita_case_id is None
        assert convocatoria.cobertura_completa is True
        ofertas = Oferta.query.filter_by(convocatoria_id=convocatoria.id).all()
        lineas = [linea for oferta in ofertas for linea in oferta.items]
        assert len(ofertas) == 2
        assert len(lineas) == 4
        assert {linea.tipo_asignacion for linea in lineas} == {
            TipoAsignacion.principal,
            TipoAsignacion.apoyo,
        }


def test_la_semilla_incluye_cobertura_insuficiente_pendiente(app, base_de_datos: None) -> None:
    with app.app_context():
        emergencia = Emergencia.query.filter_by(
            titulo="PRUEBA - Cobertura parcial pendiente en Chascomús"
        ).one()
        convocatoria = Convocatoria.query.filter_by(
            observaciones="SEED_PRUEBA_COBERTURA_INSUFICIENTE"
        ).one()

        assert emergencia.estado == EstadoEmergencia.activa
        assert convocatoria.estado == EstadoConvocatoria.cerrada
        assert convocatoria.cobertura_completa is False
        assert convocatoria.cobertura_evaluada_en is not None
        assert convocatoria.porcentaje_cobertura == 75
        assert convocatoria.decision_cobertura == DecisionCobertura.pendiente

        lote_items = [linea for lote in convocatoria.lotes for linea in lote.lote_items]
        assert len(lote_items) == 1
        assert lote_items[0].cantidad_solicitada == 1000

        ofertas = Oferta.query.filter_by(convocatoria_id=convocatoria.id).all()
        lineas = [linea for oferta in ofertas for linea in oferta.items]
        assert len(ofertas) == 1
        assert len(lineas) == 1
        assert lineas[0].cantidad_ofrecida == 750
        assert lineas[0].tipo_asignacion == TipoAsignacion.principal

        centro = Organizacion.query.filter_by(
            nombre="Centro Coordinador Regional Buenos Aires"
        ).one()
        notificacion = Notificacion.query.filter_by(
            organizacion_id=centro.id,
            titulo="Cobertura insuficiente: decisión pendiente",
        ).one()
        assert notificacion.enlace == (f"/convocatorias/{convocatoria.id}/cobertura-insuficiente")


def test_la_semilla_activa_una_emergencia_de_cobertura_insuficiente_existente(
    app, base_de_datos: None
) -> None:
    with app.app_context():
        emergencia = Emergencia.query.filter_by(
            titulo="PRUEBA - Cobertura parcial pendiente en Chascomús"
        ).one()
        emergencia.estado = EstadoEmergencia.registrada
        db.session.flush()

        _volver_a_sembrar()

        assert emergencia.estado == EstadoEmergencia.activa


def test_volver_a_sembrar_no_duplica_nada(app, base_de_datos: None) -> None:
    """`flask seed` se puede correr las veces que haga falta."""
    with app.app_context():
        antes = (
            _contar(Permiso),
            _contar(Rol),
            _contar(Organizacion),
            _contar(Inventario),
            _contar(InventarioItem),
            _contar(Usuario),
            _contar(Notificacion),
        )
        _volver_a_sembrar()
        _volver_a_sembrar()

        assert (
            _contar(Permiso),
            _contar(Rol),
            _contar(Organizacion),
            _contar(Inventario),
            _contar(InventarioItem),
            _contar(Usuario),
            _contar(Notificacion),
        ) == antes


def test_cada_rol_queda_con_los_permisos_que_declara_la_matriz(app, base_de_datos: None) -> None:
    """El catálogo en código y la base no pueden separarse: si se separan, el RBAC miente."""
    with app.app_context():
        for rol in db.session.execute(select(Rol)).scalars():
            esperados = PERMISOS_POR_ROL[NombreRol(rol.nombre)]
            asignados = {permiso.nombre for permiso in rol.permisos}

            assert asignados == set(esperados), rol.nombre


def test_un_permiso_agregado_al_catalogo_se_asigna_al_volver_a_sembrar(
    app, base_de_datos: None, monkeypatch
) -> None:
    """Agregar una acción al catálogo y correr `flask seed` alcanza: no hay que borrar la base."""
    permisos_ampliados = dict(CATALOGO_DE_PERMISOS)
    permisos_ampliados["emergencias:archivar"] = "Archivar una emergencia cerrada."

    matriz_ampliada = dict(PERMISOS_POR_ROL)
    matriz_ampliada[NombreRol.AUDITOR] = frozenset(
        PERMISOS_POR_ROL[NombreRol.AUDITOR] | {"emergencias:archivar"}
    )

    monkeypatch.setattr(
        "app.modulos.usuarios_roles.semillas.CATALOGO_DE_PERMISOS", permisos_ampliados
    )
    monkeypatch.setattr("app.modulos.usuarios_roles.semillas.PERMISOS_POR_ROL", matriz_ampliada)

    with app.app_context():
        _volver_a_sembrar()

        auditor = db.session.execute(
            select(Rol).where(Rol.nombre == NombreRol.AUDITOR.value)
        ).scalar_one()

        assert "emergencias:archivar" in {permiso.nombre for permiso in auditor.permisos}


def test_las_cuentas_sembradas_tienen_la_organizacion_que_su_rol_exige(
    app, base_de_datos: None
) -> None:
    from app.core.acceso.permisos import TIPO_DE_ORGANIZACION_POR_ROL

    with app.app_context():
        for usuario in db.session.execute(select(Usuario)).scalars():
            exigido = TIPO_DE_ORGANIZACION_POR_ROL[NombreRol(usuario.rol_principal)]

            if exigido is None:
                assert usuario.organizacion_id is None, usuario.email
            else:
                assert usuario.organizacion is not None, usuario.email
                assert usuario.organizacion.tipo.value == exigido, usuario.email


def test_ninguna_contrasena_sembrada_se_guarda_en_claro(app, base_de_datos: None) -> None:
    with app.app_context():
        contrasena = app.config["SEMILLA_CONTRASENA"]

        for usuario in db.session.execute(select(Usuario)).scalars():
            assert usuario.hash_contrasena.startswith("scrypt:")
            assert contrasena not in usuario.hash_contrasena
