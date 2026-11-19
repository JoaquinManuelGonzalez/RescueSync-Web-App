"""Seccion "Tiempos de respuesta" del panel de auditoria: tiempo medio entre el registro de una
emergencia y su primera adjudicacion.

Cada test se nombra por el criterio de aceptacion de la HU que verifica. Las fechas son de 2025:
ninguna semilla cae en ese anio, asi que las cifras son exactas.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.modulos.emergencias.modelos import EstadoEmergencia, NivelGravedad
from app.modulos.indicadores.exportacion import BOM_UTF8
from app.modulos.indicadores.periodo import Periodo
from app.modulos.indicadores.respuesta import obtener_seccion_de_tiempos

from .conftest import EMAIL_AUDITOR

MARZO_DE_2025 = Periodo(desde=date(2025, 3, 1), hasta=date(2025, 3, 31))
REGISTRO = datetime(2025, 3, 10, 15, tzinfo=UTC)
ACTIVA = EstadoEmergencia.activa


def _seccion(app):
    with app.app_context():
        return obtener_seccion_de_tiempos(MARZO_DE_2025)


def test_ca01_promedio_general_y_por_gravedad(app, crear_emergencias, cargar_necesidades) -> None:
    """Alta adjudicadas en 2 y 4 dias, Media en 9: Alta 3 d; Media 9 d; general 5 d."""
    alta_1, alta_2, media = crear_emergencias(
        (REGISTRO, ACTIVA, NivelGravedad.alta),
        (REGISTRO, ACTIVA, NivelGravedad.alta),
        (REGISTRO, ACTIVA, NivelGravedad.media),
    )
    for emergencia, dias in ((alta_1, 2), (alta_2, 4), (media, 9)):
        cargar_necesidades(emergencia, (10, 10), adjudicada_en=REGISTRO + timedelta(days=dias))

    seccion = _seccion(app)

    promedios = {fila.gravedad: fila.promedio for fila in seccion.por_gravedad}
    assert promedios[NivelGravedad.alta] == timedelta(days=3)
    assert promedios[NivelGravedad.media] == timedelta(days=9)
    assert promedios[NivelGravedad.baja] is None
    assert seccion.promedio_general == timedelta(days=5)
    grafico = seccion.grafico()
    assert grafico["valores"] == [None, 9.0, 3.0, None]
    assert grafico["unidadDelEje"] == "d"
    assert grafico["sinDato"] == "Sin adjudicaciones"


def test_un_tiempo_de_minutos_no_se_redondea_a_cero_dias(
    app, crear_emergencias, cargar_necesidades
) -> None:
    """Regresion: una emergencia adjudicada a los 15 minutos se mostraba como "0,0 días"."""
    (emergencia,) = crear_emergencias((REGISTRO, ACTIVA, NivelGravedad.critica))
    cargar_necesidades(
        emergencia, (10, 10), adjudicada_en=REGISTRO + timedelta(minutes=15, seconds=32)
    )

    seccion = _seccion(app)

    assert seccion.promedio_general == timedelta(minutes=15, seconds=32)
    assert seccion.promedio_general_como_texto == "15\xa0min 32\xa0s"
    grafico = seccion.grafico()
    assert grafico["unidadDelEje"] == "min"
    assert grafico["valores"] == [None, None, None, 15.533]
    assert grafico["textosCortos"][-1] == "15\xa0min 32\xa0s"


def test_cuenta_desde_la_primera_adjudicacion(app, crear_emergencias, cargar_necesidades) -> None:
    (emergencia,) = crear_emergencias((REGISTRO, ACTIVA, NivelGravedad.alta))
    cargar_necesidades(emergencia, (10, 10), adjudicada_en=REGISTRO + timedelta(days=6))
    cargar_necesidades(emergencia, (10, 10), adjudicada_en=REGISTRO + timedelta(days=2))

    assert _seccion(app).promedio_general == timedelta(days=2)


def test_ca02_las_emergencias_sin_adjudicar_no_entran_en_el_promedio(
    app, crear_emergencias, cargar_necesidades
) -> None:
    adjudicada, _sin_adjudicar, _cancelada = crear_emergencias(
        (REGISTRO, ACTIVA, NivelGravedad.alta),
        (REGISTRO, EstadoEmergencia.registrada, NivelGravedad.alta),
        (REGISTRO, EstadoEmergencia.cancelada, NivelGravedad.alta),
    )
    cargar_necesidades(adjudicada, (10, 10), adjudicada_en=REGISTRO + timedelta(days=3))

    seccion = _seccion(app)

    assert seccion.promedio_general == timedelta(days=3)
    assert seccion.adjudicadas == 1
    assert seccion.sin_adjudicar == 1


def test_ca02_la_pantalla_avisa_cuantas_quedan_sin_adjudicar(
    ingresar_por_formulario, navegar, crear_emergencias
) -> None:
    crear_emergencias((REGISTRO, EstadoEmergencia.registrada, NivelGravedad.alta))
    ingresar_por_formulario(EMAIL_AUDITOR)

    respuesta = navegar("/auditoria/tiempos-de-respuesta?desde=2025-03-01&hasta=2025-03-31")

    assert respuesta.status_code == 200
    assert "1 emergencia aún sin adjudicar" in respuesta.get_data(as_text=True)


def test_la_exportacion_trae_los_segundos_y_el_texto(
    cliente_sembrado, ingresar, crear_emergencias, cargar_necesidades
) -> None:
    (emergencia,) = crear_emergencias((REGISTRO, ACTIVA, NivelGravedad.alta))
    cargar_necesidades(
        emergencia, (10, 10), adjudicada_en=REGISTRO + timedelta(hours=26, seconds=5)
    )
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get(
        "/auditoria/exportaciones/tiempos-de-respuesta.csv",
        query_string={"desde": "2025-03-01", "hasta": "2025-03-31"},
    )

    lineas = respuesta.get_data(as_text=True).removeprefix(BOM_UTF8).splitlines()
    assert lineas[0] == "gravedad,emergencias_adjudicadas,tiempo_medio_segundos,tiempo_medio"
    assert "Alta,1,93605,1 d 2 h 5 s" in lineas
    assert "Baja,0,," in lineas
