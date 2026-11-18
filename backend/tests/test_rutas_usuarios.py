"""Panel de gestion de cuentas y de organizaciones.

Dos cosas que verificar: que el administrador puede hacer todo el circuito, y que ninguno de
los otros cuatro perfiles puede tocar nada de este panel.
"""

from __future__ import annotations

import pytest

from .conftest import (
    CONTRASENA_SEMILLA,
    EMAIL_ADMINISTRADOR,
    EMAIL_AUDITOR,
    EMAIL_COORDINADOR,
    EMAIL_OPERADOR,
    EMAIL_REPRESENTANTE,
)

CONTRASENA_NUEVA = "Clave-Nueva-2026"

PERFILES_SIN_ACCESO = [EMAIL_OPERADOR, EMAIL_COORDINADOR, EMAIL_REPRESENTANTE, EMAIL_AUDITOR]


def _id_de_organizacion(cliente, nombre: str) -> int:
    organizaciones = cliente.get("/organizaciones").get_json()["organizaciones"]
    return next(una["id"] for una in organizaciones if una["nombre"] == nombre)


# --- Circuito completo del administrador --------------------------------------


def test_el_administrador_da_de_alta_una_cuenta(cliente_sembrado, cabecera_csrf, ingresar) -> None:
    ingresar(EMAIL_ADMINISTRADOR)
    municipio = _id_de_organizacion(cliente_sembrado, "Municipio de Chascomús")

    respuesta = cliente_sembrado.post(
        "/usuarios",
        json={
            "email": "nuevo.operador@chascomus.test",
            "nombre_completo": "Operador nuevo",
            "contrasena": CONTRASENA_NUEVA,
            "rol": "operador_municipal",
            "organizacion_id": municipio,
        },
        headers=cabecera_csrf(),
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.get_json()
    assert cuerpo["email"] == "nuevo.operador@chascomus.test"
    assert cuerpo["roles"] == ["operador_municipal"]
    assert cuerpo["debe_cambiar_contrasena"] is True


def test_la_cuenta_nueva_tiene_que_cambiar_la_contrasena_antes_de_operar(
    cliente_sembrado, cabecera_csrf, ingresar
) -> None:
    """La clave inicial la eligió el administrador y viajó fuera del sistema."""
    ingresar(EMAIL_ADMINISTRADOR)
    municipio = _id_de_organizacion(cliente_sembrado, "Municipio de Chascomús")
    cliente_sembrado.post(
        "/usuarios",
        json={
            "email": "recien.creado@chascomus.test",
            "nombre_completo": "Recién creado",
            "contrasena": CONTRASENA_NUEVA,
            "rol": "operador_municipal",
            "organizacion_id": municipio,
        },
        headers=cabecera_csrf(),
    )
    cliente_sembrado.post("/sesion/cierre", headers=cabecera_csrf())

    ingresar("recien.creado@chascomus.test", CONTRASENA_NUEVA)
    bloqueado = cliente_sembrado.get("/organizaciones")

    assert bloqueado.status_code == 409
    assert bloqueado.get_json()["error"]["codigo"] == "CONFLICTO_DE_ESTADO"

    cambio = cliente_sembrado.post(
        "/sesion/contrasena",
        json={
            "contrasena_actual": CONTRASENA_NUEVA,
            "contrasena_nueva": "Otra-Clave-Larga-2026",
            "contrasena_nueva_repetida": "Otra-Clave-Larga-2026",
        },
        headers=cabecera_csrf(),
    )

    assert cambio.status_code == 200
    # Ya puede operar: ahora el 403 es por permiso, no por la contraseña pendiente.
    assert cliente_sembrado.get("/organizaciones").status_code == 403


def test_el_administrador_desactiva_una_cuenta(cliente_sembrado, cabecera_csrf, ingresar) -> None:
    ingresar(EMAIL_ADMINISTRADOR)
    usuarios = cliente_sembrado.get("/usuarios").get_json()["usuarios"]
    operador = next(uno for uno in usuarios if uno["email"] == EMAIL_OPERADOR)

    respuesta = cliente_sembrado.post(
        f"/usuarios/{operador['id']}/estado", json={"activo": False}, headers=cabecera_csrf()
    )

    assert respuesta.status_code == 200
    assert respuesta.get_json()["activo"] is False
    # Baja lógica: la cuenta sigue existiendo, con su historial intacto.
    assert cliente_sembrado.get(f"/usuarios/{operador['id']}").status_code == 200


def test_el_administrador_restablece_la_contrasena_y_desbloquea(
    app, cliente_sembrado, cabecera_csrf, ingresar
) -> None:
    """Reemplaza al 'olvidé mi contraseña' por correo, que la épica deja fuera de alcance."""
    for _ in range(app.config["LOGIN_MAX_INTENTOS"]):
        ingresar(EMAIL_OPERADOR, "una-contrasena-que-no-es")
    assert ingresar(EMAIL_OPERADOR).status_code == 403

    ingresar(EMAIL_ADMINISTRADOR)
    usuarios = cliente_sembrado.get("/usuarios").get_json()["usuarios"]
    operador = next(uno for uno in usuarios if uno["email"] == EMAIL_OPERADOR)
    assert operador["esta_bloqueado"] is True

    respuesta = cliente_sembrado.post(
        f"/usuarios/{operador['id']}/contrasena",
        json={"contrasena": CONTRASENA_NUEVA},
        headers=cabecera_csrf(),
    )

    assert respuesta.status_code == 200
    assert respuesta.get_json()["esta_bloqueado"] is False
    cliente_sembrado.post("/sesion/cierre", headers=cabecera_csrf())
    assert ingresar(EMAIL_OPERADOR, CONTRASENA_NUEVA).status_code == 200


def test_el_desbloqueo_no_toca_la_contrasena(
    app, cliente_sembrado, cabecera_csrf, ingresar
) -> None:
    for _ in range(app.config["LOGIN_MAX_INTENTOS"]):
        ingresar(EMAIL_OPERADOR, "una-contrasena-que-no-es")

    ingresar(EMAIL_ADMINISTRADOR)
    usuarios = cliente_sembrado.get("/usuarios").get_json()["usuarios"]
    operador = next(uno for uno in usuarios if uno["email"] == EMAIL_OPERADOR)
    cliente_sembrado.post(f"/usuarios/{operador['id']}/desbloqueo", headers=cabecera_csrf())
    cliente_sembrado.post("/sesion/cierre", headers=cabecera_csrf())

    assert ingresar(EMAIL_OPERADOR, CONTRASENA_SEMILLA).status_code == 200


def test_el_listado_se_filtra_por_rol_y_por_organizacion(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    representantes = cliente_sembrado.get("/usuarios?rol=representante_ong").get_json()["usuarios"]
    assert len(representantes) == 4
    assert all(uno["roles"] == ["representante_ong"] for uno in representantes)

    municipio = _id_de_organizacion(cliente_sembrado, "Municipio de Chascomús")
    del_municipio = cliente_sembrado.get(f"/usuarios?organizacion_id={municipio}").get_json()
    assert [uno["email"] for uno in del_municipio["usuarios"]] == [EMAIL_OPERADOR]


def test_un_filtro_no_numerico_se_rechaza_con_el_campo_en_el_detalle(
    cliente_sembrado, ingresar
) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    respuesta = cliente_sembrado.get("/usuarios?organizacion_id=no-es-un-numero")

    assert respuesta.status_code == 400
    assert "organizacion_id" in respuesta.get_json()["error"]["detalle"]


def test_una_cuenta_inexistente_devuelve_404(cliente_sembrado, ingresar) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    respuesta = cliente_sembrado.get("/usuarios/99999")

    assert respuesta.status_code == 404
    assert respuesta.get_json()["error"]["codigo"] == "RECURSO_NO_ENCONTRADO"


# --- Organizaciones -----------------------------------------------------------


def test_el_administrador_da_de_alta_y_edita_una_organizacion(
    cliente_sembrado, cabecera_csrf, ingresar
) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    alta = cliente_sembrado.post(
        "/organizaciones",
        json={
            "nombre": "ONG del Sur",
            "tipo": "ong",
            "identificador_nacional": "30-11111111-1",
            "contacto_email": "hola@ongdelsur.test",
            "zonas": [{"provincia": "Río Negro", "localidad": "Bariloche"}],
        },
        headers=cabecera_csrf(),
    )
    assert alta.status_code == 201

    identificador = alta.get_json()["id"]
    edicion = cliente_sembrado.post(
        f"/organizaciones/{identificador}/edicion",
        json={
            "nombre": "ONG del Sur Argentino",
            "tipo": "ong",
            "identificador_nacional": "30-11111111-1",
        },
        headers=cabecera_csrf(),
    )

    assert edicion.status_code == 200
    assert edicion.get_json()["nombre"] == "ONG del Sur Argentino"


def test_una_organizacion_con_nombre_repetido_se_rechaza(
    cliente_sembrado, cabecera_csrf, ingresar
) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    respuesta = cliente_sembrado.post(
        "/organizaciones",
        json={"nombre": "Cruz Solidaria", "tipo": "ong", "identificador_nacional": "30-11111111-1"},
        headers=cabecera_csrf(),
    )

    assert respuesta.status_code == 409
    assert respuesta.get_json()["error"]["codigo"] == "CONFLICTO_DE_ESTADO"


def test_un_tipo_de_organizacion_inexistente_se_rechaza(
    cliente_sembrado, cabecera_csrf, ingresar
) -> None:
    ingresar(EMAIL_ADMINISTRADOR)

    respuesta = cliente_sembrado.post(
        "/organizaciones",
        json={"nombre": "Algo raro", "tipo": "cooperativa"},
        headers=cabecera_csrf(),
    )

    assert respuesta.status_code == 400


# --- Ninguno de los otros perfiles entra --------------------------------------


@pytest.mark.parametrize("email", PERFILES_SIN_ACCESO)
def test_los_demas_perfiles_no_pueden_listar_cuentas(
    cliente_sembrado, ingresar, email: str
) -> None:
    ingresar(email)

    respuesta = cliente_sembrado.get("/usuarios")

    assert respuesta.status_code == 403
    assert respuesta.get_json()["error"]["codigo"] == "PERMISO_DENEGADO"


@pytest.mark.parametrize("email", PERFILES_SIN_ACCESO)
def test_los_demas_perfiles_no_pueden_crear_cuentas(
    cliente_sembrado, cabecera_csrf, ingresar, email: str
) -> None:
    """Es lo que sostiene que en RescueSync no haya autorregistro."""
    ingresar(email)

    respuesta = cliente_sembrado.post(
        "/usuarios",
        json={
            "email": "colado@rescuesync.test",
            "nombre_completo": "Colado",
            "contrasena": CONTRASENA_NUEVA,
            "rol": "coordinador_regional",
        },
        headers=cabecera_csrf(),
    )

    assert respuesta.status_code == 403


@pytest.mark.parametrize("email", PERFILES_SIN_ACCESO)
def test_los_demas_perfiles_no_pueden_crear_organizaciones(
    cliente_sembrado, cabecera_csrf, ingresar, email: str
) -> None:
    ingresar(email)

    respuesta = cliente_sembrado.post(
        "/organizaciones",
        json={"nombre": "ONG fantasma", "tipo": "ong"},
        headers=cabecera_csrf(),
    )

    assert respuesta.status_code == 403
