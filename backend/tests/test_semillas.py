"""Datos semilla: idempotencia y sincronia entre el catalogo en codigo y la base."""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.acceso.permisos import CATALOGO_DE_PERMISOS, PERMISOS_POR_ROL, NombreRol
from app.core.semillas import SEEDERS, importar_seeders
from app.extensiones import db
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
        assert _contar(Inventario) == 4
        assert _contar(InventarioItem) == 12
        assert _contar(Usuario) == 6


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
