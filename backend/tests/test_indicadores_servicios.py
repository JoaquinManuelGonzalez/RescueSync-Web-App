"""Las cifras del panel de auditoria, calculadas por los servicios de cada modulo.

Las emergencias de estos tests se registran en 2025: ninguna semilla cae en ese anio, asi que
los conteos son exactos.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.modulos.emergencias.modelos import EstadoEmergencia
from app.modulos.emergencias.servicios import ConteoDeEmergencias, contar_emergencias_registradas
from app.modulos.indicadores.periodo import Periodo
from app.modulos.indicadores.servicios import obtener_resumen_de_actividad
from app.modulos.ofertas.modelos import TipoAsignacion

MARZO_DE_2025 = Periodo(desde=date(2025, 3, 1), hasta=date(2025, 3, 31))


def _en_argentina(*partes: int) -> datetime:
    """Una hora de Argentina (UTC-3), expresada en UTC como se guarda."""
    return datetime(*partes, tzinfo=UTC) + timedelta(hours=3)


def test_el_conteo_clasifica_las_emergencias_segun_su_estado(app, crear_emergencias) -> None:
    """En curso es todo lo que no esta finalizado ni cancelado."""
    crear_emergencias(*((_en_argentina(2025, 3, 10, 12), estado) for estado in EstadoEmergencia))

    with app.app_context():
        conteo = contar_emergencias_registradas(
            desde=_en_argentina(2025, 3, 1), hasta=_en_argentina(2025, 4, 1)
        )

    assert conteo == ConteoDeEmergencias(registradas=5, en_curso=3, finalizadas=1, canceladas=1)


def test_el_periodo_respeta_los_bordes_del_dia_en_hora_argentina(app, crear_emergencias) -> None:
    crear_emergencias(
        (_en_argentina(2025, 3, 1, 0, 0), EstadoEmergencia.registrada),  # primer instante: entra
        (_en_argentina(2025, 3, 31, 23, 30), EstadoEmergencia.registrada),  # ultimo dia: entra
        (_en_argentina(2025, 2, 28, 23, 59), EstadoEmergencia.registrada),  # dia anterior
        (_en_argentina(2025, 4, 1, 0, 0), EstadoEmergencia.registrada),  # dia siguiente
    )

    with app.app_context():
        resumen = obtener_resumen_de_actividad(MARZO_DE_2025)

    assert resumen.emergencias_registradas == 2


def test_sin_adjudicaciones_las_ongs_con_adjudicacion_son_cero(app, crear_emergencias) -> None:
    crear_emergencias((_en_argentina(2025, 3, 10, 12), EstadoEmergencia.finalizada))

    with app.app_context():
        resumen = obtener_resumen_de_actividad(MARZO_DE_2025)

    assert resumen.a_diccionario() == {
        "emergencias_registradas": 1,
        "emergencias_activas": 0,
        "emergencias_finalizadas": 1,
        "ongs_con_adjudicacion": 0,
    }


def test_cuenta_una_vez_cada_ong_adjudicada_en_el_periodo(
    app, crear_emergencias, cargar_necesidades
) -> None:
    """Dos emergencias adjudicadas a la misma ONG cuentan una ONG; lo no adjudicado no suma."""
    primera, segunda, sin_adjudicar = crear_emergencias(
        *[(_en_argentina(2025, 3, 10, 12), EstadoEmergencia.finalizada)] * 3
    )
    cargar_necesidades(primera, (100, 100))
    cargar_necesidades(segunda, (50, 50))
    cargar_necesidades(sin_adjudicar, (10, 10, TipoAsignacion.rechazada))

    with app.app_context():
        resumen = obtener_resumen_de_actividad(MARZO_DE_2025)

    assert resumen.ongs_con_adjudicacion == 1
