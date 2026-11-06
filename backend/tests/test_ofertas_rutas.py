"""Pruebas de integración para las rutas del módulo de ofertas simples.

Verifica:
- Autorización RBAC en endpoints de ofertas (401 sin sesión, 403 sin permiso).
- Alta de oferta simple (POST /ofertas).
- Consulta de detalle de oferta (GET /ofertas/<id>).
- Modificación de oferta incrementando versión (PUT /ofertas/<id>).
- Retiro de oferta (POST /ofertas/<id>/retirar).
- Listado de ofertas por convocatoria (GET /ofertas/convocatoria/<id>).
- Integración #4 con Bonita (GET /ofertas/consolidadas/<convocatoria_id>) con token de servicio.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria, EstadoConvocatoria
from app.modulos.emergencias.modelos import (
    Emergencia,
    EstadoEmergencia,
    EstadoLote,
    Item,
    LoteItem,
    LoteNecesidad,
    NivelGravedad,
    TipoNecesidad,
)
from app.modulos.ofertas.modelos import EstadoOferta, Oferta, OfertaOrganizacion
from app.modulos.organizaciones.modelos import InventarioItem, Organizacion, TipoOrganizacion
from app.modulos.usuarios_roles.modelos import Usuario

from .conftest import (
    EMAIL_COORDINADOR,
    EMAIL_OPERADOR,
    EMAIL_REPRESENTANTE,
)


@pytest.fixture
def datos_ofertas_web(app, base_de_datos: None):
    """Prepara una convocatoria abierta con lotes y recursos en la base sembrada."""
    with app.app_context():
        # Obtener el representante y su organización
        rep = db.session.execute(
            db.select(Usuario).where(Usuario.email == EMAIL_REPRESENTANTE)
        ).scalar_one()

        ong = db.session.execute(
            db.select(Organizacion).where(Organizacion.nombre == "Cruz Solidaria")
        ).scalar_one()

        municipio = (
            db.session.execute(
                db.select(Organizacion).where(Organizacion.tipo == TipoOrganizacion.municipio)
            )
            .scalars()
            .first()
        )

        # Crear emergencia
        emergencia = Emergencia(
            titulo="Inundación Ribereña",
            descripcion="Evacuación y asistencia a afectados.",
            nivel_gravedad=NivelGravedad.alta,
            zona_afectada="Sector Este",
            estado=EstadoEmergencia.activa,
            municipio_id=municipio.id,
            usuario_id=rep.id,
        )
        db.session.add(emergencia)
        db.session.flush()

        # Crear ítems
        item1 = Item(
            codigo_recurso="RSR-AGUA_POTABLE",
            nombre="Agua potable",
            categoria=TipoNecesidad.agua,
            unidad_medida="litros",
        )
        item2 = Item(
            codigo_recurso="RSR-KITS_DE_ABRIGO",
            nombre="Kits de abrigo",
            categoria=TipoNecesidad.abrigo,
            unidad_medida="unidades",
        )
        db.session.add_all([item1, item2])
        db.session.flush()

        # Lote de necesidades
        lote = LoteNecesidad(
            emergencia_id=emergencia.id,
            descripcion="Lote de primeros auxilios",
        )
        db.session.add(lote)
        db.session.flush()

        lote_item1 = LoteItem(
            lote_id=lote.id,
            item_id=item1.id,
            cantidad_solicitada=2000,
        )
        lote_item2 = LoteItem(
            lote_id=lote.id,
            item_id=item2.id,
            cantidad_solicitada=500,
        )
        db.session.add_all([lote_item1, lote_item2])
        db.session.flush()

        db.session.add_all(
            [
                InventarioItem(
                    inventario_id=ong.inventario.id,
                    item_id=item1.id,
                    cantidad_disponible=1000,
                ),
                InventarioItem(
                    inventario_id=ong.inventario.id,
                    item_id=item2.id,
                    cantidad_disponible=5000,
                ),
            ]
        )

        # Convocatoria abierta
        ahora = datetime.now(UTC)
        convocatoria = Convocatoria(
            emergencia_id=emergencia.id,
            coordinador_id=rep.id,
            fecha_inicio=ahora - timedelta(hours=1),
            fecha_cierre=ahora + timedelta(days=2),
            resumen_situacion="Crecida de río con familias evacuadas.",
            estado=EstadoConvocatoria.abierta,
        )
        lote.convocatoria = convocatoria
        lote.estado = EstadoLote.en_convocatoria
        db.session.add(convocatoria)
        db.session.commit()

        return {
            "convocatoria_id": convocatoria.id,
            "emergencia_id": emergencia.id,
            "ong_id": ong.id,
            "usuario_id": rep.id,
            "lote_item1_id": lote_item1.id,
            "lote_item2_id": lote_item2.id,
        }


def test_crear_oferta_sin_sesion_da_401(cliente_sembrado, cabecera_csrf, datos_ofertas_web):
    """Una llamada sin sesión es rechazada con 401 NO_AUTENTICADO."""
    resp = cliente_sembrado.post(
        "/ofertas",
        json={
            "convocatoria_id": datos_ofertas_web["convocatoria_id"],
            "items": [
                {"lote_item_id": datos_ofertas_web["lote_item1_id"], "cantidad_ofrecida": 100}
            ],
        },
        headers=cabecera_csrf(),
    )
    assert resp.status_code == 401
    assert resp.get_json()["error"]["codigo"] == "NO_AUTENTICADO"


def test_ong_puede_seleccionar_convocatoria_vigente(cliente_sembrado, ingresar, datos_ofertas_web):
    ingresar(EMAIL_REPRESENTANTE)

    respuesta = cliente_sembrado.get(
        "/convocatorias",
        headers={"Accept": "text/html,application/xhtml+xml"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "Inundación Ribereña" in cuerpo
    assert "Agua potable" in cuerpo
    assert "Presentar oferta" in cuerpo
    assert f"/ofertas/nueva?convocatoria_id={datos_ofertas_web['convocatoria_id']}" in cuerpo


def test_coordinador_no_ve_opcion_de_presentar_oferta(
    cliente_sembrado, ingresar, datos_ofertas_web
):
    ingresar(EMAIL_COORDINADOR)
    ruta_de_oferta = f"/ofertas/nueva?convocatoria_id={datos_ofertas_web['convocatoria_id']}"

    listado = cliente_sembrado.get(
        "/convocatorias",
        headers={"Accept": "text/html,application/xhtml+xml"},
    )
    detalle = cliente_sembrado.get(
        f"/convocatorias/{datos_ofertas_web['convocatoria_id']}",
        headers={"Accept": "text/html,application/xhtml+xml"},
    )

    assert listado.status_code == 200
    assert detalle.status_code == 200
    assert ruta_de_oferta not in listado.get_data(as_text=True)
    assert ruta_de_oferta not in detalle.get_data(as_text=True)


def test_listado_de_ofertas_admite_busqueda_por_emergencia(
    app, cliente_sembrado, ingresar, datos_ofertas_web
):
    with app.app_context():
        oferta = Oferta(
            convocatoria_id=datos_ofertas_web["convocatoria_id"],
            usuario_id=datos_ofertas_web["usuario_id"],
            estado=EstadoOferta.presentada,
        )
        oferta.organizaciones_consorcio.append(
            OfertaOrganizacion(
                organizacion_id=datos_ofertas_web["ong_id"],
                rol_consorcio="lider",
                estado_participacion="aceptada",
            )
        )
        db.session.add(oferta)
        db.session.commit()

    ingresar(EMAIL_REPRESENTANTE)
    respuesta = cliente_sembrado.get(
        "/ofertas?texto=Ribere",
        headers={"Accept": "text/html,application/xhtml+xml"},
    )

    assert respuesta.status_code == 200
    assert "Inundación Ribereña" in respuesta.get_data(as_text=True)


def test_ong_puede_ver_convocatorias_cerradas(app, cliente_sembrado, ingresar, datos_ofertas_web):
    with app.app_context():
        convocatoria_cerrada = Convocatoria(
            emergencia_id=datos_ofertas_web["emergencia_id"],
            coordinador_id=datos_ofertas_web["usuario_id"],
            fecha_inicio=datetime.now(UTC) - timedelta(days=3),
            fecha_cierre=datetime.now(UTC) - timedelta(days=1),
            resumen_situacion="Convocatoria finalizada.",
            estado=EstadoConvocatoria.cerrada,
        )
        db.session.add(convocatoria_cerrada)
        db.session.commit()
        convocatoria_cerrada_id = convocatoria_cerrada.id

    ingresar(EMAIL_REPRESENTANTE)
    respuesta = cliente_sembrado.get(
        "/convocatorias",
        headers={"Accept": "application/json"},
    )

    assert respuesta.status_code == 200
    assert convocatoria_cerrada_id in {
        convocatoria["id"] for convocatoria in respuesta.get_json()["convocatorias"]
    }


def test_formulario_de_oferta_no_se_muestra_si_la_convocatoria_vencio(
    app, cliente_sembrado, ingresar, datos_ofertas_web
):
    with app.app_context():
        convocatoria = db.session.get(Convocatoria, datos_ofertas_web["convocatoria_id"])
        convocatoria.fecha_cierre = datetime.now(UTC) - timedelta(minutes=1)
        db.session.commit()

    assert ingresar(EMAIL_REPRESENTANTE).status_code == 200
    respuesta = cliente_sembrado.get(
        f"/ofertas/nueva?convocatoria_id={datos_ofertas_web['convocatoria_id']}",
        headers={"Accept": "text/html,application/xhtml+xml"},
    )

    assert respuesta.status_code == 302
    with app.app_context():
        convocatoria = db.session.get(Convocatoria, datos_ofertas_web["convocatoria_id"])
        emergencia = db.session.get(Emergencia, datos_ofertas_web["emergencia_id"])
        assert convocatoria.estado == EstadoConvocatoria.cerrada
        assert emergencia.estado == EstadoEmergencia.registrada


def test_crear_oferta_con_rol_sin_permiso_da_403(
    cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web
):
    """Un usuario sin ofertas:crear (como operador municipal) recibe 403 PERMISO_DENEGADO."""
    ingresar(EMAIL_OPERADOR)
    resp = cliente_sembrado.post(
        "/ofertas",
        json={
            "convocatoria_id": datos_ofertas_web["convocatoria_id"],
            "items": [
                {"lote_item_id": datos_ofertas_web["lote_item1_id"], "cantidad_ofrecida": 100}
            ],
        },
        headers=cabecera_csrf(),
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"]["codigo"] == "PERMISO_DENEGADO"


def test_crear_oferta_simple_exitosa(cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web):
    """Un representante de ONG crea exitosamente una oferta simple."""
    ingresar(EMAIL_REPRESENTANTE)

    payload = {
        "convocatoria_id": datos_ofertas_web["convocatoria_id"],
        "organizacion_id": datos_ofertas_web["ong_id"],
        "observaciones": "Entrega en camión propio dentro de las 24 horas",
        "items": [
            {
                "lote_item_id": datos_ofertas_web["lote_item1_id"],
                "cantidad_ofrecida": 500,
                "observaciones": "Botellones de 5L",
            }
        ],
    }

    resp = cliente_sembrado.post("/ofertas", json=payload, headers=cabecera_csrf())
    assert resp.status_code == 201

    cuerpo = resp.get_json()
    assert cuerpo["id"] is not None
    assert cuerpo["convocatoria_id"] == datos_ofertas_web["convocatoria_id"]
    assert cuerpo["version"] == 1
    assert cuerpo["estado"] == "presentada"
    assert cuerpo["observaciones"] == "Entrega en camión propio dentro de las 24 horas"
    assert cuerpo["organizacion"]["id"] == datos_ofertas_web["ong_id"]
    assert len(cuerpo["items"]) == 1
    assert cuerpo["items"][0]["cantidad_ofrecida"] == 500.0


def test_formulario_de_edicion_no_muestra_none_si_hay_valores_nulos(
    cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web
):
    """El formulario web no debe renderizar la cadena literal 'None' en campos opcionales."""
    ingresar(EMAIL_REPRESENTANTE)

    resp = cliente_sembrado.post(
        "/ofertas",
        json={
            "convocatoria_id": datos_ofertas_web["convocatoria_id"],
            "items": [
                {
                    "lote_item_id": datos_ofertas_web["lote_item1_id"],
                    "cantidad_ofrecida": 50,
                    "observaciones": None,
                }
            ],
            "observaciones": None,
        },
        headers=cabecera_csrf(),
    )

    assert resp.status_code == 201
    oferta_id = resp.get_json()["id"]

    resp = cliente_sembrado.get(f"/ofertas/{oferta_id}/edicion")

    assert resp.status_code == 200
    assert b"None" not in resp.data


def test_crear_oferta_validacion_invalida(
    cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web
):
    """Si faltan items o se superan los límites, devuelve 400 o regla de negocio incumplicada."""
    ingresar(EMAIL_REPRESENTANTE)

    # Sin items
    resp = cliente_sembrado.post(
        "/ofertas",
        json={"convocatoria_id": datos_ofertas_web["convocatoria_id"]},
        headers=cabecera_csrf(),
    )
    assert resp.status_code == 400


def test_formulario_conjunto_exige_una_organizacion_invitada(
    cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web
):
    ingresar(EMAIL_REPRESENTANTE)

    resp = cliente_sembrado.post(
        "/ofertas/nueva",
        data={
            "convocatoria_id": datos_ofertas_web["convocatoria_id"],
            "tipo_oferta": "conjunta",
            f"item_{datos_ofertas_web['lote_item1_id']}": "100",
        },
        headers=cabecera_csrf(),
    )

    assert resp.status_code == 400
    assert "Seleccioná al menos una organización" in resp.get_json()["error"]["mensaje"]


def test_obtener_modificar_y_retirar_oferta(
    cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web
):
    """Flujo completo: crear, obtener detalle, modificar versión y retirar."""
    ingresar(EMAIL_REPRESENTANTE)

    # 1. Crear oferta
    resp_crear = cliente_sembrado.post(
        "/ofertas",
        json={
            "convocatoria_id": datos_ofertas_web["convocatoria_id"],
            "organizacion_id": datos_ofertas_web["ong_id"],
            "items": [
                {
                    "lote_item_id": datos_ofertas_web["lote_item1_id"],
                    "cantidad_ofrecida": 300,
                }
            ],
        },
        headers=cabecera_csrf(),
    )
    assert resp_crear.status_code == 201
    oferta_id = resp_crear.get_json()["id"]

    # 2. Obtener oferta por id
    resp_get = cliente_sembrado.get(f"/ofertas/{oferta_id}")
    assert resp_get.status_code == 200
    assert resp_get.get_json()["id"] == oferta_id

    # 3. Modificar oferta (incrementa versión a 2)
    resp_mod = cliente_sembrado.put(
        f"/ofertas/{oferta_id}",
        json={
            "observaciones": "Ajuste de logística",
            "items": [
                {
                    "lote_item_id": datos_ofertas_web["lote_item1_id"],
                    "cantidad_ofrecida": 450,
                }
            ],
        },
        headers=cabecera_csrf(),
    )
    assert resp_mod.status_code == 200
    cuerpo_mod = resp_mod.get_json()
    assert cuerpo_mod["version"] == 2
    assert cuerpo_mod["estado"] == "presentada"
    assert cuerpo_mod["items"][0]["cantidad_ofrecida"] == 450.0

    # 4. Retirar oferta
    resp_ret = cliente_sembrado.post(
        f"/ofertas/{oferta_id}/retirar",
        headers=cabecera_csrf(),
    )
    assert resp_ret.status_code == 200
    assert resp_ret.get_json()["estado"] == "retirada"

    # 5. Intentar modificar una oferta retirada da 409
    resp_mod_ret = cliente_sembrado.put(
        f"/ofertas/{oferta_id}",
        json={"observaciones": "Intento tras retiro"},
        headers=cabecera_csrf(),
    )
    assert resp_mod_ret.status_code == 409


def test_detalle_html_muestra_el_historial_de_versiones(
    cliente_sembrado, cabecera_csrf, ingresar, navegar, datos_ofertas_web
):
    """El detalle HTML renderiza snapshots luego de editar una oferta."""
    ingresar(EMAIL_REPRESENTANTE)
    crear = cliente_sembrado.post(
        "/ofertas",
        json={
            "convocatoria_id": datos_ofertas_web["convocatoria_id"],
            "organizacion_id": datos_ofertas_web["ong_id"],
            "items": [
                {
                    "lote_item_id": datos_ofertas_web["lote_item1_id"],
                    "cantidad_ofrecida": 300,
                }
            ],
        },
        headers=cabecera_csrf(),
    )
    oferta_id = crear.get_json()["id"]

    cliente_sembrado.put(
        f"/ofertas/{oferta_id}",
        json={
            "items": [
                {
                    "lote_item_id": datos_ofertas_web["lote_item1_id"],
                    "cantidad_ofrecida": 450,
                }
            ]
        },
        headers=cabecera_csrf(),
    )

    respuesta = navegar(f"/ofertas/{oferta_id}")

    assert respuesta.status_code == 200
    assert "Historial de cambios" in respuesta.get_data(as_text=True)
    assert "Actualización registrada" in respuesta.get_data(as_text=True)


def test_retirar_oferta_desde_html_redirige_a_la_convocatoria(
    cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web
):
    ingresar(EMAIL_REPRESENTANTE)
    crear = cliente_sembrado.post(
        "/ofertas",
        json={
            "convocatoria_id": datos_ofertas_web["convocatoria_id"],
            "items": [
                {
                    "lote_item_id": datos_ofertas_web["lote_item1_id"],
                    "cantidad_ofrecida": 300,
                }
            ],
        },
        headers=cabecera_csrf(),
    )
    oferta_id = crear.get_json()["id"]

    respuesta = cliente_sembrado.post(
        f"/ofertas/{oferta_id}/retirar",
        headers={**cabecera_csrf(), "Accept": "text/html"},
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(
        f"/convocatorias/{datos_ofertas_web['convocatoria_id']}"
    )


def test_alta_html_muestra_error_de_stock_en_el_formulario(
    cliente_sembrado, cabecera_csrf, ingresar, navegar, datos_ofertas_web
):
    ingresar(EMAIL_REPRESENTANTE)

    respuesta = cliente_sembrado.post(
        "/ofertas/nueva",
        data={
            "convocatoria_id": datos_ofertas_web["convocatoria_id"],
            f"item_{datos_ofertas_web['lote_item1_id']}": "1001",
        },
        headers={**cabecera_csrf(), "Accept": "text/html"},
    )

    cuerpo = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert "No se pudo guardar la oferta" in cuerpo
    assert "stock disponible" in cuerpo
    assert 'value="1001"' in cuerpo


def test_listar_ofertas_por_convocatoria(
    cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web
):
    """Listado de ofertas de una convocatoria con y sin incluir retiradas."""
    ingresar(EMAIL_REPRESENTANTE)
    cid = datos_ofertas_web["convocatoria_id"]

    # Crear una oferta y retirarla para poder presentar otra de la misma organización
    resp1 = cliente_sembrado.post(
        "/ofertas",
        json={
            "convocatoria_id": cid,
            "organizacion_id": datos_ofertas_web["ong_id"],
            "items": [
                {"lote_item_id": datos_ofertas_web["lote_item1_id"], "cantidad_ofrecida": 100}
            ],
        },
        headers=cabecera_csrf(),
    )
    of1_id = resp1.get_json()["id"]
    cliente_sembrado.post(f"/ofertas/{of1_id}/retirar", headers=cabecera_csrf())

    resp2 = cliente_sembrado.post(
        "/ofertas",
        json={
            "convocatoria_id": cid,
            "organizacion_id": datos_ofertas_web["ong_id"],
            "items": [
                {"lote_item_id": datos_ofertas_web["lote_item2_id"], "cantidad_ofrecida": 50}
            ],
        },
        headers=cabecera_csrf(),
    )
    of2_id = resp2.get_json()["id"]

    # Listar activas
    resp_activas = cliente_sembrado.get(f"/ofertas/convocatoria/{cid}")
    assert resp_activas.status_code == 200
    assert len(resp_activas.get_json()["ofertas"]) == 1
    assert resp_activas.get_json()["ofertas"][0]["id"] == of2_id

    # Listar incluyendo retiradas
    resp_todas = cliente_sembrado.get(f"/ofertas/convocatoria/{cid}?incluir_retiradas=true")
    assert resp_todas.status_code == 200
    assert len(resp_todas.get_json()["ofertas"]) == 2


def test_integracion_bonita_consolidadas_autenticacion(cliente_sembrado, datos_ofertas_web):
    """El endpoint para Bonita exige BONITA_CALLBACK_TOKEN."""
    cid = datos_ofertas_web["convocatoria_id"]

    # 1. Sin token -> 401
    resp_sin_token = cliente_sembrado.get(f"/ofertas/consolidadas/{cid}")
    assert resp_sin_token.status_code == 401
    assert resp_sin_token.get_json()["error"]["codigo"] == "NO_AUTENTICADO"

    # 2. Con token inválido -> 401
    resp_invalido = cliente_sembrado.get(
        f"/ofertas/consolidadas/{cid}",
        headers={"Authorization": "Bearer token-falso"},
    )
    assert resp_invalido.status_code == 401

    # 3. Con token válido en Authorization: Bearer
    resp_valido = cliente_sembrado.get(
        f"/ofertas/consolidadas/{cid}",
        headers={"Authorization": "Bearer token-de-prueba"},
    )
    assert resp_valido.status_code == 200
    cuerpo = resp_valido.get_json()
    assert cuerpo["convocatoria_id"] == cid
    assert cuerpo["emergencia_id"] == datos_ofertas_web["emergencia_id"]
    assert "ofertas" in cuerpo
    assert isinstance(cuerpo["ofertas"], list)

    # 4. Con token válido en cabecera X-Bonita-Token
    resp_x_token = cliente_sembrado.get(
        f"/ofertas/consolidadas/{cid}",
        headers={"X-Bonita-Token": "token-de-prueba"},
    )
    assert resp_x_token.status_code == 200


def test_historial_oferta_ruta(cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web):
    """Verifica que el endpoint GET /ofertas/<id>/historial retorne las versiones anteriores."""
    ingresar(EMAIL_REPRESENTANTE)

    # 1. Crear oferta v1
    resp_crear = cliente_sembrado.post(
        "/ofertas",
        json={
            "convocatoria_id": datos_ofertas_web["convocatoria_id"],
            "organizacion_id": datos_ofertas_web["ong_id"],
            "items": [
                {
                    "lote_item_id": datos_ofertas_web["lote_item1_id"],
                    "cantidad_ofrecida": 200,
                }
            ],
            "observaciones": "Versión 1",
        },
        headers=cabecera_csrf(),
    )
    assert resp_crear.status_code == 201
    oferta_id = resp_crear.get_json()["id"]

    # Historial v1 (aún no modificada -> 0 versiones archivadas)
    resp_hist0 = cliente_sembrado.get(f"/ofertas/{oferta_id}/historial")
    assert resp_hist0.status_code == 200
    assert resp_hist0.get_json()["versiones"] == []

    # 2. Modificar a v2
    resp_mod = cliente_sembrado.put(
        f"/ofertas/{oferta_id}",
        json={
            "observaciones": "Versión 2 modificada",
            "items": [
                {
                    "lote_item_id": datos_ofertas_web["lote_item1_id"],
                    "cantidad_ofrecida": 350,
                }
            ],
        },
        headers=cabecera_csrf(),
    )
    assert resp_mod.status_code == 200

    # 3. Consultar historial
    resp_hist = cliente_sembrado.get(f"/ofertas/{oferta_id}/historial")
    assert resp_hist.status_code == 200
    cuerpo_hist = resp_hist.get_json()
    assert cuerpo_hist["oferta_id"] == oferta_id
    versiones = cuerpo_hist["versiones"]
    assert len(versiones) == 1
    assert versiones[0]["version"] == 1
    assert versiones[0]["estado_anterior"] == "presentada"
    assert versiones[0]["observaciones_anteriores"] == "Versión 1"
    assert versiones[0]["items"][0]["cantidad_ofrecida"] == 200.0


# --- Alcance del operador municipal ---------------------------------------------


def _crear_oferta_como_ong(cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web) -> int:
    ingresar(EMAIL_REPRESENTANTE)
    resp = cliente_sembrado.post(
        "/ofertas",
        json={
            "convocatoria_id": datos_ofertas_web["convocatoria_id"],
            "items": [
                {"lote_item_id": datos_ofertas_web["lote_item1_id"], "cantidad_ofrecida": 100}
            ],
        },
        headers=cabecera_csrf(),
    )
    assert resp.status_code == 201
    cliente_sembrado.post("/sesion/cierre", headers=cabecera_csrf())
    return resp.get_json()["id"]


def _asignar_emergencia_a_municipio(app, emergencia_id: int, *, propio: bool) -> None:
    """Deja la emergencia en el municipio del operador sembrado o en otro distinto."""
    with app.app_context():
        operador = db.session.execute(
            db.select(Usuario).where(Usuario.email == EMAIL_OPERADOR)
        ).scalar_one()
        if propio:
            municipio_id = operador.organizacion_id
        else:
            otro = Organizacion(
                nombre="Municipio Vecino",
                tipo=TipoOrganizacion.municipio,
                activo=True,
            )
            db.session.add(otro)
            db.session.flush()
            municipio_id = otro.id
        db.session.get(Emergencia, emergencia_id).municipio_id = municipio_id
        db.session.commit()


def test_operador_ve_convocatorias_y_ofertas_de_su_municipio(
    app, cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web
):
    oferta_id = _crear_oferta_como_ong(cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web)
    _asignar_emergencia_a_municipio(app, datos_ofertas_web["emergencia_id"], propio=True)
    convocatoria_id = datos_ofertas_web["convocatoria_id"]

    assert ingresar(EMAIL_OPERADOR).status_code == 200

    convocatorias = cliente_sembrado.get("/convocatorias").get_json()["convocatorias"]
    assert convocatoria_id in [c["id"] for c in convocatorias]
    assert cliente_sembrado.get(f"/convocatorias/{convocatoria_id}").status_code == 200

    ofertas = cliente_sembrado.get("/ofertas").get_json()["ofertas"]
    assert oferta_id in [o["id"] for o in ofertas]
    assert cliente_sembrado.get(f"/ofertas/{oferta_id}").status_code == 200
    assert cliente_sembrado.get(f"/ofertas/{oferta_id}/historial").status_code == 200
    assert cliente_sembrado.get(f"/ofertas/convocatoria/{convocatoria_id}").status_code == 200


def test_operador_no_ve_convocatorias_ni_ofertas_de_otro_municipio(
    app, cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web
):
    oferta_id = _crear_oferta_como_ong(cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web)
    _asignar_emergencia_a_municipio(app, datos_ofertas_web["emergencia_id"], propio=False)
    convocatoria_id = datos_ofertas_web["convocatoria_id"]
    emergencia_id = datos_ofertas_web["emergencia_id"]

    assert ingresar(EMAIL_OPERADOR).status_code == 200

    convocatorias = cliente_sembrado.get("/convocatorias").get_json()["convocatorias"]
    assert convocatoria_id not in [c["id"] for c in convocatorias]
    assert cliente_sembrado.get(f"/convocatorias/{convocatoria_id}").status_code == 404

    ofertas = cliente_sembrado.get("/ofertas").get_json()["ofertas"]
    assert oferta_id not in [o["id"] for o in ofertas]
    filtradas = cliente_sembrado.get(f"/ofertas?convocatoria_id={convocatoria_id}")
    assert filtradas.get_json()["ofertas"] == []
    assert cliente_sembrado.get(f"/ofertas/{oferta_id}").status_code == 404
    assert cliente_sembrado.get(f"/ofertas/{oferta_id}/historial").status_code == 404
    assert cliente_sembrado.get(f"/ofertas/convocatoria/{convocatoria_id}").status_code == 404

    assert cliente_sembrado.get(f"/emergencias/{emergencia_id}/lotes").status_code == 404


def test_coordinador_sigue_viendo_convocatorias_y_ofertas_de_todos_los_municipios(
    app, cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web
):
    oferta_id = _crear_oferta_como_ong(cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web)
    _asignar_emergencia_a_municipio(app, datos_ofertas_web["emergencia_id"], propio=False)

    assert ingresar(EMAIL_COORDINADOR).status_code == 200

    convocatorias = cliente_sembrado.get("/convocatorias").get_json()["convocatorias"]
    assert datos_ofertas_web["convocatoria_id"] in [c["id"] for c in convocatorias]
    ofertas = cliente_sembrado.get("/ofertas").get_json()["ofertas"]
    assert oferta_id in [o["id"] for o in ofertas]
    assert cliente_sembrado.get(f"/ofertas/{oferta_id}").status_code == 200


def test_crear_oferta_rechaza_cantidades_no_enteras(
    cliente_sembrado, cabecera_csrf, ingresar, datos_ofertas_web
):
    ingresar(EMAIL_REPRESENTANTE)
    resp = cliente_sembrado.post(
        "/ofertas",
        json={
            "convocatoria_id": datos_ofertas_web["convocatoria_id"],
            "items": [
                {"lote_item_id": datos_ofertas_web["lote_item1_id"], "cantidad_ofrecida": 1.5}
            ],
        },
        headers=cabecera_csrf(),
    )
    assert resp.status_code == 400
    assert "entero" in resp.get_json()["error"]["mensaje"]
