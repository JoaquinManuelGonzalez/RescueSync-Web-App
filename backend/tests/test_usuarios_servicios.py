"""Alta de cuentas y coherencia entre rol y organizacion.

Se ejercita la capa de servicios directamente, sin pasar por HTTP: es la que usan tambien el
seeder y `flask crear-administrador`, asi que las reglas tienen que valer ahi tambien.
"""

from __future__ import annotations

import pytest

from app.core.acceso.permisos import NombreRol
from app.core.errores import ConflictoDeEstado, PermisoDenegado, SolicitudInvalida
from app.modulos.organizaciones import servicios as organizaciones
from app.modulos.usuarios_roles import servicios

CONTRASENA = "Clave-Larga-2026"


def _id_de_organizacion(nombre: str) -> int:
    return next(una.id for una in organizaciones.listar() if una.nombre == nombre)


def test_el_email_se_guarda_normalizado(app, base_de_datos: None) -> None:
    """Mayúsculas y espacios se descartan: el email es la clave natural del login."""
    with app.app_context():
        usuario = servicios.crear_usuario(
            email="  Nueva.Cuenta@RescueSync.TEST  ",
            nombre_completo="Cuenta nueva",
            contrasena=CONTRASENA,
            nombre_rol=NombreRol.AUDITOR,
        )
        assert usuario.email == "nueva.cuenta@rescuesync.test"


def test_dos_cuentas_con_el_mismo_email_en_distinta_caja_fallan(app, base_de_datos: None) -> None:
    """Sin normalizar, "Juan@x.test" y "juan@x.test" serian dos cuentas."""
    with app.app_context():
        servicios.crear_usuario(
            email="repetida@rescuesync.test",
            nombre_completo="Primera",
            contrasena=CONTRASENA,
            nombre_rol=NombreRol.AUDITOR,
        )
        with pytest.raises(ConflictoDeEstado):
            servicios.crear_usuario(
                email="REPETIDA@RescueSync.test",
                nombre_completo="Segunda",
                contrasena=CONTRASENA,
                nombre_rol=NombreRol.AUDITOR,
            )


def test_la_cuenta_nueva_nace_obligada_a_cambiar_la_contrasena(app, base_de_datos: None) -> None:
    with app.app_context():
        usuario = servicios.crear_usuario(
            email="reciente@rescuesync.test",
            nombre_completo="Reciente",
            contrasena=CONTRASENA,
            nombre_rol=NombreRol.AUDITOR,
        )
        assert usuario.debe_cambiar_contrasena is True


def test_contrasena_mas_corta_que_el_minimo_se_rechaza(app, base_de_datos: None) -> None:
    with app.app_context():
        with pytest.raises(SolicitudInvalida):
            servicios.crear_usuario(
                email="corta@rescuesync.test",
                nombre_completo="Clave corta",
                contrasena="corta",
                nombre_rol=NombreRol.AUDITOR,
            )


@pytest.mark.parametrize(
    ("rol", "nombre_de_organizacion"),
    [
        (NombreRol.OPERADOR_MUNICIPAL, "Municipio de Chascomús"),
        (NombreRol.REPRESENTANTE_ONG, "Cruz Solidaria"),
        (NombreRol.COORDINADOR_REGIONAL, "Centro Coordinador Regional Buenos Aires"),
    ],
)
def test_rol_con_la_organizacion_que_le_corresponde_se_acepta(
    app, base_de_datos: None, rol: NombreRol, nombre_de_organizacion: str
) -> None:
    with app.app_context():
        usuario = servicios.crear_usuario(
            email=f"{rol.value}@prueba.test",
            nombre_completo="Cuenta de prueba",
            contrasena=CONTRASENA,
            nombre_rol=rol,
            organizacion_id=_id_de_organizacion(nombre_de_organizacion),
        )
        assert usuario.tiene_rol(rol)


def test_representante_de_ong_apuntando_a_un_municipio_falla(app, base_de_datos: None) -> None:
    """Es el caso que rompe el alcance por organización del resto del sistema."""
    with app.app_context():
        with pytest.raises(SolicitudInvalida) as error:
            servicios.crear_usuario(
                email="mezcla@prueba.test",
                nombre_completo="Mezcla",
                contrasena=CONTRASENA,
                nombre_rol=NombreRol.REPRESENTANTE_ONG,
                organizacion_id=_id_de_organizacion("Municipio de Chascomús"),
            )
        assert "organizacion_id" in error.value.detalle


@pytest.mark.parametrize(
    "rol",
    [NombreRol.OPERADOR_MUNICIPAL, NombreRol.REPRESENTANTE_ONG, NombreRol.COORDINADOR_REGIONAL],
)
def test_rol_que_exige_organizacion_sin_organizacion_falla(
    app, base_de_datos: None, rol: NombreRol
) -> None:
    with app.app_context():
        with pytest.raises(SolicitudInvalida):
            servicios.crear_usuario(
                email=f"sin-organizacion-{rol.value}@prueba.test",
                nombre_completo="Sin organización",
                contrasena=CONTRASENA,
                nombre_rol=rol,
            )


@pytest.mark.parametrize("rol", [NombreRol.AUDITOR, NombreRol.ADMINISTRADOR])
def test_rol_sin_organizacion_con_organizacion_falla(
    app, base_de_datos: None, rol: NombreRol
) -> None:
    """El auditor y el administrador miran todo el sistema: atarlos a una organización
    sugeriría un alcance que no tienen."""
    with app.app_context():
        with pytest.raises(SolicitudInvalida):
            servicios.crear_usuario(
                email=f"con-organizacion-{rol.value}@prueba.test",
                nombre_completo="Con organización",
                contrasena=CONTRASENA,
                nombre_rol=rol,
                organizacion_id=_id_de_organizacion("Municipio de Chascomús"),
            )


def test_rol_inexistente_se_rechaza_como_solicitud_invalida(app, base_de_datos: None) -> None:
    with app.app_context():
        with pytest.raises(SolicitudInvalida):
            servicios.crear_usuario(
                email="rol-raro@prueba.test",
                nombre_completo="Rol raro",
                contrasena=CONTRASENA,
                nombre_rol="superusuario",
            )


# --- Alcance por organizacion -------------------------------------------------


def test_el_operador_solo_alcanza_a_su_propia_organizacion(app, base_de_datos: None) -> None:
    with app.app_context():
        municipio = _id_de_organizacion("Municipio de Chascomús")
        otra = _id_de_organizacion("Cruz Solidaria")
        operador = servicios.obtener_por_email("operador@chascomus.test")

        servicios.verificar_alcance_de_organizacion(operador, municipio)

        with pytest.raises(PermisoDenegado):
            servicios.verificar_alcance_de_organizacion(operador, otra)


def test_el_coordinador_y_el_auditor_alcanzan_a_cualquier_organizacion(
    app, base_de_datos: None
) -> None:
    """Ven el proceso completo: el coordinador porque lo orquesta, el auditor porque audita."""
    with app.app_context():
        otra = _id_de_organizacion("Cruz Solidaria")
        for email in ("coordinador@rescuesync.test", "auditor@rescuesync.test"):
            servicios.verificar_alcance_de_organizacion(servicios.obtener_por_email(email), otra)
