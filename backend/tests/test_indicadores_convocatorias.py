"""Seccion "Convocatorias" del panel de auditoria: emergencias que requirieron una decision ante
cobertura insuficiente (HU de reapertura de convocatorias).

Solo hay dos decisiones, las dos ramas del proceso: "Reiniciar convocatoria" (Reapertura) y
"Enviar ofertas igualmente" (Continuar con parcial). Las fechas son de 2025, que ninguna semilla
toca, para que los conteos sean exactos. Cada test se nombra por el criterio que verifica.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from app.extensiones import db
from app.modulos.convocatorias.modelos import Convocatoria, DecisionCobertura, EstadoConvocatoria
from app.modulos.emergencias.modelos import EstadoEmergencia, NivelGravedad
from app.modulos.indicadores.convocatorias import obtener_seccion_de_convocatorias
from app.modulos.indicadores.exportacion import BOM_UTF8
from app.modulos.indicadores.formularios import DecisionDeCobertura
from app.modulos.indicadores.periodo import Periodo
from app.modulos.usuarios_roles.modelos import Usuario

from .conftest import EMAIL_AUDITOR, EMAIL_COORDINADOR

OCTUBRE = Periodo(desde=date(2025, 10, 1), hasta=date(2025, 10, 31))
EN_OCTUBRE = {"desde": "2025-10-01", "hasta": "2025-10-31"}
REGISTRO = datetime(2025, 10, 10, 15, tzinfo=UTC)

# Resultado de cada convocatoria: (estado, cobertura completa, evaluada, decision).
RESULTADOS = {
    "completa": (EstadoConvocatoria.adjudicada, True, True, DecisionCobertura.pendiente),
    "reabierta": (
        EstadoConvocatoria.cerrada,
        False,
        True,
        DecisionCobertura.convocatoria_reabierta,
    ),
    "parcial": (
        EstadoConvocatoria.adjudicada,
        False,
        True,
        DecisionCobertura.aceptada_parcialmente,
    ),
    "pendiente": (EstadoConvocatoria.cerrada, False, True, DecisionCobertura.pendiente),
    "abierta": (EstadoConvocatoria.abierta, False, False, DecisionCobertura.pendiente),
    "borrador": (EstadoConvocatoria.borrador, False, False, DecisionCobertura.pendiente),
}


@pytest.fixture
def emergencia_con_convocatorias(app, crear_emergencias):
    """Registra una emergencia de octubre de 2025 con una convocatoria por resultado, en orden."""

    def _crear(*resultados: str, gravedad: NivelGravedad = NivelGravedad.media) -> int:
        (emergencia_id,) = crear_emergencias((REGISTRO, EstadoEmergencia.activa, gravedad))
        with app.app_context():
            coordinador = db.session.execute(
                db.select(Usuario).filter_by(email=EMAIL_COORDINADOR)
            ).scalar_one()
            for resultado in resultados:
                estado, completa, evaluada, decision = RESULTADOS[resultado]
                db.session.add(
                    Convocatoria(
                        emergencia_id=emergencia_id,
                        coordinador_id=coordinador.id,
                        fecha_inicio=REGISTRO,
                        fecha_cierre=REGISTRO,
                        resumen_situacion="Convocatoria creada por un test.",
                        estado=estado,
                        cobertura_completa=completa,
                        cobertura_evaluada_en=REGISTRO if evaluada else None,
                        decision_cobertura=decision,
                    )
                )
            db.session.commit()
        return emergencia_id

    return _crear


@pytest.fixture
def escenario_de_la_hu(emergencia_con_convocatorias) -> dict[str, int]:
    """10 emergencias con convocatoria; 4 con cobertura insuficiente: 2 reabiertas, 1 que
    continuo con parcial y 1 que espera la decision."""
    ids = {
        "reabierta_a": emergencia_con_convocatorias(
            "reabierta", "completa", gravedad=NivelGravedad.alta
        ),
        "reabierta_b": emergencia_con_convocatorias("reabierta", "completa"),
        "parcial": emergencia_con_convocatorias("parcial"),
        "pendiente": emergencia_con_convocatorias("pendiente"),
    }
    for _ in range(6):
        emergencia_con_convocatorias("completa")
    return ids


def _seccion(app, decision=None):
    with app.app_context():
        return obtener_seccion_de_convocatorias(OCTUBRE, decision)


# --- Calculo ---------------------------------------------------------------------------


def test_ca01_una_barra_por_decision(app, escenario_de_la_hu) -> None:
    seccion = _seccion(app)

    assert [(etiqueta, cantidad) for _, etiqueta, cantidad, _ in seccion.barras()] == [
        ("Reapertura", 2),
        ("Continuar con parcial", 1),
    ]
    grafico = seccion.grafico()
    assert grafico["etiquetas"] == ["Reapertura", "Continuar con parcial"]
    assert grafico["valores"] == [2, 1]
    assert grafico["unidad"] == ["decisión", "decisiones"]


def test_ca02_tasa_sobre_las_emergencias_con_convocatoria(app, escenario_de_la_hu) -> None:
    seccion = _seccion(app)

    assert seccion.emergencias_con_convocatoria == 10
    assert len(seccion.afectadas) == 4
    assert seccion.porcentaje_afectadas == 40
    assert seccion.esperan_decision == 1


def test_dos_reaperturas_cuentan_dos_veces_en_la_barra_y_una_en_las_afectadas(
    app, emergencia_con_convocatorias
) -> None:
    emergencia_con_convocatorias("reabierta", "reabierta", "completa")

    seccion = _seccion(app)

    assert seccion.reaperturas == 2
    assert len(seccion.afectadas) == 1
    assert seccion.afectadas[0].convocatorias_publicadas == 3
    assert seccion.barras()[0][3] == 1, "la barra informa en cuantas emergencias ocurrio"


def test_ca03_el_detalle_lista_las_emergencias_de_la_decision_elegida(
    app, escenario_de_la_hu
) -> None:
    seccion = _seccion(app, DecisionDeCobertura.reapertura)

    assert {emergencia.emergencia_id for emergencia in seccion.detalle} == {
        escenario_de_la_hu["reabierta_a"],
        escenario_de_la_hu["reabierta_b"],
    }
    primera = next(
        e for e in seccion.detalle if e.emergencia_id == escenario_de_la_hu["reabierta_a"]
    )
    assert primera.gravedad == NivelGravedad.alta
    assert primera.convocatorias_publicadas == 2
    assert primera.titulo.startswith("Emergencia de prueba")
    # La barra no elegida queda atenuada.
    assert seccion.grafico()["tonos"] == ["advertencia", "tenue"]


def test_sin_filtro_el_detalle_lista_todas_las_afectadas(app, escenario_de_la_hu) -> None:
    seccion = _seccion(app)

    assert len(seccion.detalle) == 4
    assert seccion.grafico()["tonos"] == ["advertencia", "info"]


def test_los_borradores_y_las_convocatorias_abiertas_no_son_coberturas_insuficientes(
    app, emergencia_con_convocatorias
) -> None:
    emergencia_con_convocatorias("borrador")
    emergencia_con_convocatorias("abierta")

    seccion = _seccion(app)

    assert seccion.emergencias_con_convocatoria == 1, "el borrador no se publico"
    assert seccion.afectadas == ()
    assert seccion.porcentaje_afectadas == 0


def test_un_periodo_sin_convocatorias_no_tiene_tasa_ni_filas(app, base_de_datos) -> None:
    seccion = _seccion(app)

    assert seccion.porcentaje_afectadas is None
    assert not seccion.hubo_decisiones
    assert seccion.tabla().vacia
    assert seccion.tabla_de_detalle().vacia


# --- Pantalla y JSON -------------------------------------------------------------------


def test_la_pantalla_muestra_grafico_tarjetas_y_detalle(
    ingresar_por_formulario, navegar, escenario_de_la_hu
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    respuesta = navegar("/auditoria/convocatorias?desde=2025-10-01&hasta=2025-10-31")

    cuerpo = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert 'id="grafico-decisiones"' in cuerpo
    assert "Necesitaron una decisión" in cuerpo
    assert "40 %" in cuerpo
    assert "(4 de 10)" in cuerpo
    assert "Esperan decisión" in cuerpo
    assert "Espera decisión" in cuerpo, "la emergencia pendiente se marca en el detalle"
    # Tocar una barra lleva al mismo enlace que el filtro de esa decision.
    assert '"enlaces": ["/auditoria/convocatorias?decision=reapertura"' in cuerpo
    assert 'href="/auditoria/convocatorias?decision=reapertura"' in cuerpo


def test_la_barra_elegida_vuelve_a_todas(
    ingresar_por_formulario, navegar, escenario_de_la_hu
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    cuerpo = navegar(
        "/auditoria/convocatorias?desde=2025-10-01&hasta=2025-10-31&decision=reapertura"
    ).get_data(as_text=True)

    assert (
        '"enlaces": ["/auditoria/convocatorias", '
        '"/auditoria/convocatorias?decision=continuar_parcial"]' in cuerpo
    )
    assert "2 emergencias con reapertura." in cuerpo


def test_una_decision_invalida_no_se_aplica(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    respuesta = navegar("/auditoria/convocatorias?decision=reformulacion")

    assert respuesta.status_code == 400
    assert "El filtro de decisión no se aplicó" in respuesta.get_data(as_text=True)


def test_por_json_responde_decisiones_y_detalle(
    cliente_sembrado, ingresar, escenario_de_la_hu
) -> None:
    ingresar(EMAIL_AUDITOR)

    datos = cliente_sembrado.get(
        "/auditoria/convocatorias", query_string={**EN_OCTUBRE, "decision": "continuar_parcial"}
    ).get_json()

    assert datos["filtros"] == {"decision": "continuar_parcial"}
    assert datos["porcentaje_con_cobertura_insuficiente"] == 40
    assert datos["decisiones"] == [
        {"decision": "Reapertura", "decisiones": 2, "emergencias": 2},
        {"decision": "Continuar con parcial", "decisiones": 1, "emergencias": 1},
    ]
    assert len(datos["detalle"]) == 1
    assert datos["detalle"][0]["continuo_con_parcial"] is True


def test_la_pestana_aparece_en_el_panel(ingresar_por_formulario, navegar) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    assert 'href="/auditoria/convocatorias' in navegar("/auditoria").get_data(as_text=True)


# --- Exportacion -----------------------------------------------------------------------


def test_se_exportan_las_decisiones_en_csv(cliente_sembrado, ingresar, escenario_de_la_hu) -> None:
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get(
        "/auditoria/exportaciones/decisiones-de-cobertura.csv", query_string=EN_OCTUBRE
    )

    assert respuesta.headers["Content-Disposition"].endswith(
        'filename="rescuesync-decisiones-de-cobertura-2025-10-01_2025-10-31.csv"'
    )
    assert respuesta.get_data(as_text=True).removeprefix(BOM_UTF8).splitlines() == [
        "decision,decisiones,emergencias",
        "Reapertura,2,2",
        "Continuar con parcial,1,1",
    ]


def test_el_detalle_exportado_respeta_el_filtro_de_decision(
    cliente_sembrado, ingresar, escenario_de_la_hu
) -> None:
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get(
        "/auditoria/exportaciones/emergencias-con-cobertura-insuficiente.json",
        query_string={**EN_OCTUBRE, "decision": "reapertura"},
    )

    datos = json.loads(respuesta.get_data(as_text=True))
    assert datos["filtros"]["decision"] == "reapertura"
    assert len(datos["datos"]) == 2
    assert {fila["gravedad"] for fila in datos["datos"]} == {"Alta", "Media"}
    assert all(fila["reaperturas"] == 1 for fila in datos["datos"])
