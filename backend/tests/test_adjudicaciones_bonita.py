"""La seleccion de ofertas completa la tarea "Seleccionar ofertas" de Bonita antes de guardarse.

Si el motor no la recibe no se guarda nada: antes la web adjudicaba igual, el caso quedaba
trabado en esa tarea y la finalizacion de las ONG fallaba al final del proceso.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from app.core.errores import SistemaExternoRechazo
from app.core.integraciones.bonita.sesion import BONITA_USER
from app.extensiones import db
from app.modulos.adjudicaciones import servicios
from app.modulos.convocatorias.modelos import Convocatoria, EstadoConvocatoria
from app.modulos.emergencias.modelos import Emergencia, EstadoEmergencia
from app.modulos.notificaciones.modelos import Notificacion
from app.modulos.ofertas.modelos import EstadoOferta, Oferta, OfertaLinea

from .conftest import CABECERA_NAVEGADOR, EMAIL_OPERADOR

CASO_DE_BONITA = "7001"
RECHAZO_DE_CONTRATO = SistemaExternoRechazo(
    detalle={
        "componente": "bonita",
        "codigo_estado": 400,
        "motivo": "El identificador de adjudicación es inválido",
    }
)


@pytest.fixture
def selecciones_enviadas(monkeypatch) -> list[dict[str, object]]:
    """Reemplaza el envio de la seleccion a Bonita y devuelve las llamadas que recibio."""
    llamadas: list[dict[str, object]] = []
    monkeypatch.setattr(
        servicios,
        "confirmar_seleccion_ofertas",
        lambda **argumentos: llamadas.append(argumentos),
    )
    return llamadas


@pytest.fixture
def bonita_rechaza(monkeypatch) -> None:
    def _rechazar(**_argumentos):
        raise RECHAZO_DE_CONTRATO

    monkeypatch.setattr(servicios, "confirmar_seleccion_ofertas", _rechazar)


@pytest.fixture
def convocatoria_evaluada(app, crear_emergencias, cargar_necesidades):
    """Convocatoria como la deja Bonita al evaluar: cerrada, cubierta y sin nada seleccionado.

    Devuelve `(convocatoria_id, linea_id, oferta_id, emergencia_id)`. La emergencia tiene caso en
    Bonita; un test que quiera probar sin caso se lo quita.
    """
    (emergencia_id,) = crear_emergencias(
        (datetime(2025, 3, 15, 15, tzinfo=UTC), EstadoEmergencia.activa)
    )
    oferta_id = cargar_necesidades(emergencia_id, (100, 100))

    with app.app_context():
        oferta = db.session.get(Oferta, oferta_id)
        convocatoria = oferta.convocatoria
        convocatoria.estado = EstadoConvocatoria.cerrada
        convocatoria.cobertura_completa = True
        convocatoria.adjudicada_en = None
        convocatoria.emergencia.bonita_case_id = CASO_DE_BONITA
        oferta.estado = EstadoOferta.presentada
        (linea,) = db.session.query(OfertaLinea).filter_by(oferta_id=oferta_id).all()
        linea.seleccionada = False
        db.session.commit()
        return convocatoria.id, linea.id, oferta_id, emergencia_id


def _seleccionar(convocatoria_id: uuid.UUID, linea_id: uuid.UUID) -> None:
    servicios.seleccionar_lineas(db.session.get(Convocatoria, convocatoria_id), [linea_id])


def test_la_seleccion_completa_la_tarea_de_bonita_con_ids_uuid(
    app, convocatoria_evaluada, selecciones_enviadas
) -> None:
    convocatoria_id, linea_id, _, emergencia_id = convocatoria_evaluada

    with app.app_context():
        _seleccionar(convocatoria_id, linea_id)

        assert db.session.get(Convocatoria, convocatoria_id).estado == (
            EstadoConvocatoria.adjudicada
        )

    (llamada,) = selecciones_enviadas
    assert llamada["username"] == BONITA_USER
    assert llamada["case_id"] == CASO_DE_BONITA
    # proceso.py lo manda como str(uuid): es lo que la restriccion del contrato valida.
    assert llamada["adjudicacion_id"] == convocatoria_id
    compromisos = json.loads(llamada["compromisos_json"])
    assert compromisos["emergencia_externa_id"] == str(emergencia_id)
    assert [aporte["cantidad"] for aporte in compromisos["aportes"]] == [100]


def test_si_bonita_rechaza_la_seleccion_no_se_guarda_ningun_cambio(
    app, convocatoria_evaluada, bonita_rechaza
) -> None:
    convocatoria_id, linea_id, oferta_id, _ = convocatoria_evaluada

    with app.app_context():
        with pytest.raises(SistemaExternoRechazo) as error:
            _seleccionar(convocatoria_id, linea_id)

        assert error.value.mensaje == (
            "El motor de procesos rechazó la selección: El identificador de adjudicación es "
            "inválido. No se guardó ningún cambio."
        )
        assert error.value.detalle == RECHAZO_DE_CONTRATO.detalle

        convocatoria = db.session.get(Convocatoria, convocatoria_id)
        assert convocatoria.estado == EstadoConvocatoria.cerrada
        assert convocatoria.adjudicada_en is None
        assert db.session.get(OfertaLinea, linea_id).seleccionada is False
        assert db.session.get(Oferta, oferta_id).estado == EstadoOferta.presentada
        avisos = db.session.query(Notificacion).filter_by(enlace=f"/ofertas/{oferta_id}").all()
        assert avisos == [], "no avisa a las ONG de una adjudicacion que no se guardo"


def test_sin_caso_en_bonita_la_seleccion_se_guarda_sin_llamar_al_motor(
    app, convocatoria_evaluada, selecciones_enviadas
) -> None:
    convocatoria_id, linea_id, _, emergencia_id = convocatoria_evaluada

    with app.app_context():
        db.session.get(Emergencia, emergencia_id).bonita_case_id = None
        db.session.commit()

        _seleccionar(convocatoria_id, linea_id)

        assert db.session.get(Convocatoria, convocatoria_id).estado == (
            EstadoConvocatoria.adjudicada
        )

    assert selecciones_enviadas == []


def test_la_pantalla_avisa_que_no_se_guardo_y_deja_reintentar(
    app,
    cliente_sembrado,
    convocatoria_evaluada,
    bonita_rechaza,
    ingresar,
    enviar_formulario,
) -> None:
    convocatoria_id, linea_id, _, _ = convocatoria_evaluada
    ingresar(EMAIL_OPERADOR)

    respuesta = enviar_formulario(
        f"/adjudicaciones/convocatoria/{convocatoria_id}", {"linea_id": str(linea_id)}
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(f"/adjudicaciones/convocatoria/{convocatoria_id}")
    pantalla = cliente_sembrado.get(respuesta.headers["Location"], headers=CABECERA_NAVEGADOR)
    cuerpo = pantalla.get_data(as_text=True)
    assert "El motor de procesos rechazó la selección" in cuerpo
    assert "No se guardó ningún cambio." in cuerpo
    with app.app_context():
        assert db.session.get(Convocatoria, convocatoria_id).estado == EstadoConvocatoria.cerrada
