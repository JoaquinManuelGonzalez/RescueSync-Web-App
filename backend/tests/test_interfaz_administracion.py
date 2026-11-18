"""Panel del administrador desde el navegador: cuentas y organizaciones por formulario.

El circuito por JSON esta en test_rutas_usuarios.py. Aca se verifica que cada formulario
redirige al terminar y que, si falla, vuelve con el error al lado del campo en vez de mostrar
una pagina de error.
"""

from __future__ import annotations

import pytest

from .conftest import CABECERA_NAVEGADOR, EMAIL_ADMINISTRADOR, EMAIL_OPERADOR, token_csrf_de

CONTRASENA_NUEVA = "Clave-Nueva-2026"


def _texto(respuesta) -> str:
    return respuesta.get_data(as_text=True)


def _id_de_organizacion(cliente, nombre: str) -> int:
    organizaciones = cliente.get("/organizaciones").get_json()["organizaciones"]
    return next(una["id"] for una in organizaciones if una["nombre"] == nombre)


def _id_de_usuario(cliente, email: str) -> int:
    usuarios = cliente.get("/usuarios").get_json()["usuarios"]
    return next(uno["id"] for uno in usuarios if uno["email"] == email)


@pytest.fixture
def administrador(ingresar_por_formulario) -> None:
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)


def _datos_de_alta(**cambios: object) -> dict[str, object]:
    return {
        "email": "nuevo.operador@chascomus.test",
        "nombre_completo": "Operador nuevo",
        "contrasena": CONTRASENA_NUEVA,
        "rol": "operador_municipal",
        "organizacion_id": "",
        **cambios,
    }


# --- Cuentas ------------------------------------------------------------------


def test_el_listado_de_cuentas_muestra_perfiles_legibles_y_filtra(administrador, navegar) -> None:
    cuerpo = _texto(navegar("/usuarios?rol=operador_municipal"))

    assert EMAIL_OPERADOR in cuerpo
    assert "Operador Municipal" in cuerpo
    assert "admin@rescuesync.test" not in cuerpo


def test_la_pantalla_de_alta_ofrece_las_organizaciones_con_su_tipo(administrador, navegar) -> None:
    cuerpo = _texto(navegar("/usuarios/nuevo"))

    assert 'data-tipo="municipio"' in cuerpo
    assert "Municipio de Chascomús" in cuerpo
    assert "data-filtra-organizaciones" in cuerpo


def test_el_alta_por_formulario_lleva_al_detalle_de_la_cuenta(
    administrador, cliente_sembrado, enviar_formulario, navegar
) -> None:
    municipio = _id_de_organizacion(cliente_sembrado, "Municipio de Chascomús")

    respuesta = enviar_formulario("/usuarios", _datos_de_alta(organizacion_id=municipio))

    assert respuesta.status_code == 302
    detalle = navegar(respuesta.headers["Location"])
    cuerpo = _texto(detalle)
    assert "nuevo.operador@chascomus.test" in cuerpo
    assert "Cuenta creada." in cuerpo
    assert "Debe cambiar la contraseña" in cuerpo


def test_el_alta_incompleta_vuelve_con_el_error_en_el_campo(
    administrador, enviar_formulario
) -> None:
    respuesta = enviar_formulario("/usuarios", _datos_de_alta(nombre_completo=""))

    assert respuesta.status_code == 400
    cuerpo = _texto(respuesta)
    assert "El nombre completo es obligatorio." in cuerpo
    assert 'aria-invalid="true"' in cuerpo
    # Lo demas queda cargado.
    assert 'value="nuevo.operador@chascomus.test"' in cuerpo


def test_el_rol_incoherente_con_la_organizacion_marca_la_organizacion(
    administrador, enviar_formulario
) -> None:
    respuesta = enviar_formulario("/usuarios", _datos_de_alta(organizacion_id=""))

    assert respuesta.status_code == 400
    assert "requiere una organización de tipo" in _texto(respuesta)


def test_el_email_repetido_vuelve_con_el_aviso(
    administrador, cliente_sembrado, enviar_formulario
) -> None:
    municipio = _id_de_organizacion(cliente_sembrado, "Municipio de Chascomús")

    respuesta = enviar_formulario(
        "/usuarios", _datos_de_alta(email=EMAIL_OPERADOR, organizacion_id=municipio)
    )

    assert respuesta.status_code == 409
    assert "Ya existe una cuenta registrada con ese email." in _texto(respuesta)


def test_la_edicion_viene_precargada_y_guarda(
    administrador, cliente_sembrado, enviar_formulario, navegar
) -> None:
    operador = _id_de_usuario(cliente_sembrado, EMAIL_OPERADOR)
    municipio = _id_de_organizacion(cliente_sembrado, "Municipio de Chascomús")

    pantalla = _texto(navegar(f"/usuarios/{operador}/edicion"))
    assert 'value="Operador municipal"' in pantalla

    respuesta = enviar_formulario(
        f"/usuarios/{operador}/edicion",
        {
            "nombre_completo": "Operador renombrado",
            "rol": "operador_municipal",
            "organizacion_id": municipio,
        },
    )

    assert respuesta.status_code == 302
    assert "Operador renombrado" in _texto(navegar(respuesta.headers["Location"]))


def test_desactivar_y_reactivar_una_cuenta(
    administrador, cliente_sembrado, enviar_formulario, navegar
) -> None:
    operador = _id_de_usuario(cliente_sembrado, EMAIL_OPERADOR)

    enviar_formulario(f"/usuarios/{operador}/estado", {})
    assert "Cuenta desactivada." in _texto(navegar(f"/usuarios/{operador}"))

    enviar_formulario(f"/usuarios/{operador}/estado", {"activo": "y"})
    assert "Cuenta activada." in _texto(navegar(f"/usuarios/{operador}"))


def test_restablecer_con_una_clave_corta_vuelve_al_detalle_con_el_error(
    administrador, cliente_sembrado, enviar_formulario
) -> None:
    operador = _id_de_usuario(cliente_sembrado, EMAIL_OPERADOR)

    respuesta = enviar_formulario(f"/usuarios/{operador}/contrasena", {"contrasena": "corta"})

    assert respuesta.status_code == 400
    cuerpo = _texto(respuesta)
    assert "Datos de la cuenta" in cuerpo
    assert 'aria-invalid="true"' in cuerpo


def test_restablecer_la_contrasena_por_formulario(
    administrador, cliente_sembrado, enviar_formulario, navegar
) -> None:
    operador = _id_de_usuario(cliente_sembrado, EMAIL_OPERADOR)

    respuesta = enviar_formulario(
        f"/usuarios/{operador}/contrasena", {"contrasena": CONTRASENA_NUEVA}
    )

    assert respuesta.status_code == 302
    assert "Contraseña restablecida." in _texto(navegar(respuesta.headers["Location"]))


# --- Organizaciones -----------------------------------------------------------


def test_el_listado_de_organizaciones_muestra_el_tipo_legible(administrador, navegar) -> None:
    cuerpo = _texto(navegar("/organizaciones"))

    assert "Municipio de Chascomús" in cuerpo
    assert "Centro Coordinador Regional" in cuerpo


def test_alta_y_edicion_de_una_organizacion_por_formulario(
    administrador, enviar_formulario, navegar
) -> None:
    alta = enviar_formulario(
        "/organizaciones",
        {"nombre": "Municipio de Lezama", "tipo": "municipio", "contacto_email": ""},
    )
    assert alta.status_code == 302
    detalle = alta.headers["Location"]
    assert "Municipio de Lezama" in _texto(navegar(detalle))

    organizacion_id = detalle.rstrip("/").rsplit("/", 1)[1]
    pantalla = _texto(navegar(f"/organizaciones/{organizacion_id}/edicion"))
    assert 'value="Municipio de Lezama"' in pantalla

    edicion = enviar_formulario(
        f"/organizaciones/{organizacion_id}/edicion",
        {"nombre": "Municipio de Lezama", "tipo": "municipio", "direccion": "Calle 1"},
    )
    assert edicion.status_code == 302
    assert "Calle 1" in _texto(navegar(edicion.headers["Location"]))


def test_la_organizacion_con_nombre_repetido_vuelve_con_el_aviso(
    administrador, enviar_formulario
) -> None:
    respuesta = enviar_formulario(
        "/organizaciones", {"nombre": "Municipio de Chascomús", "tipo": "municipio"}
    )

    assert respuesta.status_code == 409
    assert "Nueva organización" in _texto(respuesta)


def test_desactivar_una_organizacion_desde_el_listado_vuelve_al_listado(
    administrador, cliente_sembrado, enviar_formulario
) -> None:
    ong = _id_de_organizacion(cliente_sembrado, "Manos Unidas")

    respuesta = cliente_sembrado.post(
        f"/organizaciones/{ong}/estado",
        data={"csrf_token": token_csrf_de(cliente_sembrado)},
        headers={**CABECERA_NAVEGADOR, "Referer": "http://localhost/organizaciones?tipo=ong"},
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/organizaciones?tipo=ong")


def test_las_celdas_llevan_su_titulo_para_la_vista_angosta(administrador, navegar) -> None:
    """Sin scroll horizontal: en pantallas angostas cada dato se muestra con su titulo."""
    cuerpo = _texto(navegar("/usuarios"))

    assert "overflow-x-auto" not in cuerpo
    for etiqueta in ("Nombre", "Perfil", "Organización", "Estado", "Último acceso"):
        assert f'data-etiqueta="{etiqueta}"' in cuerpo


def test_desactivar_pide_confirmacion_con_el_modal_de_la_app(
    administrador, cliente_sembrado, navegar
) -> None:
    operador = _id_de_usuario(cliente_sembrado, EMAIL_OPERADOR)

    cuerpo = _texto(navegar(f"/usuarios/{operador}"))

    assert 'data-confirmar-titulo="¿Desactivar esta cuenta?"' in cuerpo
    assert 'data-confirmar-boton="Desactivar cuenta"' in cuerpo
