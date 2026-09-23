"""La sesion vista desde el navegador: ingreso, cierre, expiracion y cambio obligatorio.

Los mismos flujos por JSON estan en test_autenticacion.py y test_sesion.py; aca se verifica
que la interfaz los lleva a pantallas y redirects, y no a JSON crudo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.sesion import CLAVE_ULTIMA_ACTIVIDAD, MENSAJE_SESION_EXPIRADA
from app.modulos.usuarios_roles.servicios import MENSAJE_CREDENCIALES, mensaje_de_bloqueo

from .conftest import CABECERA_NAVEGADOR, EMAIL_ADMINISTRADOR, EMAIL_OPERADOR

CONTRASENA_NUEVA = "Clave-Nueva-2026"


def _texto(respuesta) -> str:
    return respuesta.get_data(as_text=True)


# --- Pantalla de ingreso ------------------------------------------------------


def test_la_pantalla_de_ingreso_tiene_email_contrasena_y_csrf(navegar) -> None:
    cuerpo = _texto(navegar("/sesion/ingreso"))

    assert 'name="email"' in cuerpo
    assert 'type="email"' in cuerpo
    assert 'name="contrasena"' in cuerpo
    assert 'name="csrf_token"' in cuerpo
    assert 'action="/sesion/ingreso"' in cuerpo


def test_con_sesion_abierta_la_pantalla_de_ingreso_lleva_al_panel(
    navegar, ingresar_por_formulario
) -> None:
    ingresar_por_formulario(EMAIL_OPERADOR)

    respuesta = navegar("/sesion/ingreso")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/inicio")


def test_el_ingreso_por_formulario_lleva_al_panel(ingresar_por_formulario, navegar) -> None:
    respuesta = ingresar_por_formulario(EMAIL_OPERADOR)

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/inicio")
    panel = navegar("/inicio")
    assert panel.status_code == 200
    assert "¿Qué deseas hacer?" in _texto(panel)


def test_el_ingreso_vuelve_a_la_pantalla_que_se_pedia(ingresar_por_formulario) -> None:
    respuesta = ingresar_por_formulario(EMAIL_ADMINISTRADOR, siguiente="/usuarios?rol=auditor")

    assert respuesta.headers["Location"].endswith("/usuarios?rol=auditor")


def test_el_ingreso_no_redirige_a_otro_sitio(ingresar_por_formulario) -> None:
    for destino in ("//evil.test/robar", "https://evil.test", "/\\evil.test", "javascript:x"):
        respuesta = ingresar_por_formulario(EMAIL_OPERADOR, siguiente=destino)
        assert respuesta.headers["Location"].endswith("/inicio"), destino


def test_credenciales_incorrectas_muestran_el_mensaje_generico(ingresar_por_formulario) -> None:
    respuesta = ingresar_por_formulario(EMAIL_OPERADOR, contrasena="no-es-esta-clave")

    assert respuesta.status_code == 401
    assert "text/html" in respuesta.content_type
    cuerpo = _texto(respuesta)
    assert MENSAJE_CREDENCIALES in cuerpo
    # El formulario vuelve con el email cargado, para no tener que escribirlo de nuevo.
    assert f'value="{EMAIL_OPERADOR}"' in cuerpo


def test_el_formulario_incompleto_marca_el_campo(ingresar_por_formulario) -> None:
    respuesta = ingresar_por_formulario(EMAIL_OPERADOR, contrasena="")

    assert respuesta.status_code == 400
    assert "El formulario tiene campos inválidos o incompletos." in _texto(respuesta)


def test_la_cuenta_bloqueada_muestra_el_aviso_de_bloqueo(app, ingresar_por_formulario) -> None:
    for _ in range(app.config["LOGIN_MAX_INTENTOS"]):
        ingresar_por_formulario(EMAIL_OPERADOR, contrasena="no-es-esta-clave")

    respuesta = ingresar_por_formulario(EMAIL_OPERADOR)

    assert respuesta.status_code == 403
    assert mensaje_de_bloqueo(app.config["LOGIN_BLOQUEO_MINUTOS"]) in _texto(respuesta)
    assert "Volvé a intentar en 1 minuto" in _texto(respuesta)


def test_el_ingreso_sin_csrf_vuelve_a_la_pantalla_con_un_aviso(cliente_sembrado) -> None:
    respuesta = cliente_sembrado.post(
        "/sesion/ingreso",
        data={"email": EMAIL_OPERADOR, "contrasena": "x"},
        headers={**CABECERA_NAVEGADOR, "Referer": "http://localhost/sesion/ingreso"},
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/sesion/ingreso")


# --- Cierre y expiracion ------------------------------------------------------


def test_cerrar_sesion_por_formulario_vuelve_al_ingreso(
    ingresar_por_formulario, enviar_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_OPERADOR)

    respuesta = enviar_formulario("/sesion/cierre")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/sesion/ingreso")
    assert "Sesión cerrada." in _texto(navegar("/sesion/ingreso"))
    assert navegar("/inicio").status_code == 302


def test_el_navbar_cierra_sesion_con_un_post(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_OPERADOR)

    cuerpo = _texto(navegar("/inicio"))

    assert '<form method="post" action="/sesion/cierre"' in cuerpo


def test_sin_sesion_una_pantalla_lleva_al_ingreso_conservando_el_destino(navegar) -> None:
    respuesta = navegar("/usuarios?rol=auditor")

    assert respuesta.status_code == 302
    assert "/sesion/ingreso?next=/usuarios?rol%3Dauditor" in respuesta.headers["Location"]


def test_la_sesion_vencida_lleva_al_ingreso_con_el_aviso(
    app, cliente_sembrado, ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_OPERADOR)
    with cliente_sembrado.session_transaction() as sesion:
        sesion[CLAVE_ULTIMA_ACTIVIDAD] = (
            datetime.now(UTC) - timedelta(minutes=app.config["SESION_MINUTOS_INACTIVIDAD"] + 1)
        ).isoformat()

    respuesta = navegar("/inicio")

    assert respuesta.status_code == 302
    assert "/sesion/ingreso" in respuesta.headers["Location"]
    assert MENSAJE_SESION_EXPIRADA in _texto(navegar(respuesta.headers["Location"]))


def test_las_pantallas_publican_los_minutos_de_sesion_para_el_aviso(
    app, ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_OPERADOR)

    cuerpo = _texto(navegar("/inicio"))

    assert f'data-minutos-sesion="{app.config["SESION_MINUTOS_INACTIVIDAD"]}"' in cuerpo


# --- Cambio de contrasena -----------------------------------------------------


def _crear_cuenta_con_cambio_pendiente(ingresar_por_formulario, enviar_formulario) -> str:
    """El administrador da de alta una cuenta (nace con el cambio pendiente) y cierra sesion."""
    ingresar_por_formulario(EMAIL_ADMINISTRADOR)
    email = "auditor.nuevo@rescuesync.test"
    enviar_formulario(
        "/usuarios",
        {
            "email": email,
            "nombre_completo": "Auditor nuevo",
            "contrasena": CONTRASENA_NUEVA,
            "rol": "auditor",
            "organizacion_id": "",
        },
    )
    enviar_formulario("/sesion/cierre")
    return email


def test_con_el_cambio_pendiente_toda_pantalla_lleva_al_cambio(
    ingresar_por_formulario, enviar_formulario, navegar
) -> None:
    email = _crear_cuenta_con_cambio_pendiente(ingresar_por_formulario, enviar_formulario)
    ingresar_por_formulario(email, CONTRASENA_NUEVA)

    respuesta = navegar("/inicio")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/sesion/contrasena")
    pantalla = _texto(navegar("/sesion/contrasena"))
    assert "Cambio obligatorio" in pantalla


def test_tras_cambiar_la_contrasena_llega_al_panel(
    ingresar_por_formulario, enviar_formulario, navegar
) -> None:
    email = _crear_cuenta_con_cambio_pendiente(ingresar_por_formulario, enviar_formulario)
    ingresar_por_formulario(email, CONTRASENA_NUEVA)

    respuesta = enviar_formulario(
        "/sesion/contrasena",
        {
            "contrasena_actual": CONTRASENA_NUEVA,
            "contrasena_nueva": "Otra-Clave-Segura-1",
            "contrasena_nueva_repetida": "Otra-Clave-Segura-1",
        },
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/inicio")
    assert navegar("/inicio").status_code == 200


def test_el_cambio_con_la_clave_actual_incorrecta_marca_el_campo(
    ingresar_por_formulario, enviar_formulario
) -> None:
    ingresar_por_formulario(EMAIL_OPERADOR)

    respuesta = enviar_formulario(
        "/sesion/contrasena",
        {
            "contrasena_actual": "no-es-esta-clave",
            "contrasena_nueva": "Otra-Clave-Segura-1",
            "contrasena_nueva_repetida": "Otra-Clave-Segura-1",
        },
    )

    assert respuesta.status_code == 400
    assert "La contraseña actual no es correcta." in _texto(respuesta)


def test_mi_perfil_muestra_la_cuenta_y_sus_permisos(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_OPERADOR)

    cuerpo = _texto(navegar("/sesion/actual"))

    assert "Operador Municipal" in cuerpo
    assert "Municipio de Chascomús" in cuerpo
    assert "Registrar una emergencia nueva." in cuerpo


# --- Avisos y campos ------------------------------------------------------------


def test_los_mensajes_flash_se_pueden_cerrar_y_se_van_solos(
    ingresar_por_formulario, enviar_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_OPERADOR)
    enviar_formulario("/sesion/cierre")

    cuerpo = _texto(navegar("/sesion/ingreso"))

    assert "Sesión cerrada." in cuerpo
    assert "data-alerta-descartable" in cuerpo
    assert 'data-segundos="5"' in cuerpo
    assert "data-cerrar-alerta" in cuerpo


def test_un_aviso_fijo_de_la_pantalla_no_se_va_solo(
    ingresar_por_formulario, enviar_formulario, navegar
) -> None:
    email = _crear_cuenta_con_cambio_pendiente(ingresar_por_formulario, enviar_formulario)
    ingresar_por_formulario(email, CONTRASENA_NUEVA)

    cuerpo = _texto(navegar("/sesion/contrasena"))
    aviso = cuerpo.split("Cambio obligatorio")[0].rsplit('<div class="alerta', 1)[1]

    assert "data-alerta-descartable" not in aviso


def test_los_campos_de_contrasena_se_pueden_mostrar(navegar) -> None:
    cuerpo = _texto(navegar("/sesion/ingreso"))

    assert 'data-alternar-contrasena="contrasena"' in cuerpo
    assert 'aria-label="Mostrar contraseña"' in cuerpo


def test_la_contrasena_nueva_no_puede_ser_la_actual(
    ingresar_por_formulario, enviar_formulario
) -> None:
    ingresar_por_formulario(EMAIL_OPERADOR)

    respuesta = enviar_formulario(
        "/sesion/contrasena",
        {
            "contrasena_actual": "RescueSync.2026",
            "contrasena_nueva": "RescueSync.2026",
            "contrasena_nueva_repetida": "RescueSync.2026",
        },
    )

    assert respuesta.status_code == 400
    assert "La contraseña nueva tiene que ser distinta de la actual." in _texto(respuesta)


def test_el_cambio_obligatorio_no_acepta_repetir_la_clave_inicial(
    ingresar_por_formulario, enviar_formulario, navegar
) -> None:
    """Si pudiera "cambiarla" por la misma, el cambio obligatorio seria decorativo."""
    email = _crear_cuenta_con_cambio_pendiente(ingresar_por_formulario, enviar_formulario)
    ingresar_por_formulario(email, CONTRASENA_NUEVA)

    enviar_formulario(
        "/sesion/contrasena",
        {
            "contrasena_actual": CONTRASENA_NUEVA,
            "contrasena_nueva": CONTRASENA_NUEVA,
            "contrasena_nueva_repetida": CONTRASENA_NUEVA,
        },
    )

    # Sigue encerrada en el cambio de contraseña.
    assert navegar("/inicio").headers["Location"].endswith("/sesion/contrasena")


def test_la_cuenta_desactivada_ve_su_aviso_en_la_pantalla_de_ingreso(
    app, ingresar_por_formulario
) -> None:
    from app.modulos.usuarios_roles import servicios

    with app.app_context():
        usuario = servicios.obtener_por_email(EMAIL_OPERADOR)
        servicios.cambiar_estado(usuario.id, activo=False)

    respuesta = ingresar_por_formulario(EMAIL_OPERADOR)

    assert respuesta.status_code == 403
    assert servicios.MENSAJE_INACTIVA in _texto(respuesta)
