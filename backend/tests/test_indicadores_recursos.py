"""Seccion "Recursos" del panel de auditoria: recursos movilizados por mes y rubro, y demanda por
rubro frente a la tasa de inhabilitacion del Sistema Nacional.

Cada test se nombra por el criterio de aceptacion de la HU que verifica. Las fechas son de 2025:
ninguna semilla cae en ese anio, asi que las cifras son exactas.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.modulos.emergencias.modelos import EstadoEmergencia, TipoNecesidad
from app.modulos.indicadores.periodo import Periodo
from app.modulos.indicadores.recursos import obtener_seccion_de_recursos
from app.modulos.ofertas.modelos import TipoAsignacion

SEP_OCT_2025 = Periodo(desde=date(2025, 9, 1), hasta=date(2025, 10, 31))
ALIMENTOS = TipoNecesidad.alimentos
SANITARIO = TipoNecesidad.personal_medico
AGUA = TipoNecesidad.agua


def _en(anio, mes, dia) -> datetime:
    return datetime(anio, mes, dia, 15, tzinfo=UTC)


def _seccion(app, rubro=None):
    with app.app_context():
        return obtener_seccion_de_recursos(SEP_OCT_2025, rubro)


# --- Recursos movilizados --------------------------------------------------------


def test_ca01_serie_mensual_por_rubro(app, crear_emergencias, cargar_necesidades) -> None:
    """Septiembre: 1000 raciones y 5 paramedicos; octubre: 300 raciones."""
    septiembre, octubre = crear_emergencias(
        (_en(2025, 9, 10), EstadoEmergencia.activa), (_en(2025, 10, 5), EstadoEmergencia.activa)
    )
    cargar_necesidades(
        septiembre,
        (1000, 1000),
        (5, 5),
        categorias=[ALIMENTOS, SANITARIO],
        adjudicada_en=_en(2025, 9, 20),
    )
    cargar_necesidades(octubre, (300, 300), categorias=[ALIMENTOS], adjudicada_en=_en(2025, 10, 9))

    movilizados = _seccion(app).movilizados

    assert movilizados.tabla().filas == (
        ("2025-09", "Personal sanitario", 5),
        ("2025-09", "Alimentos", 1000),
        ("2025-10", "Alimentos", 300),
    )
    grafico = movilizados.grafico()
    assert grafico["apilado"] is True
    assert grafico["etiquetas"] == ["sep 2025", "oct 2025"]
    assert {serie["nombre"]: serie["valores"] for serie in grafico["series"]} == {
        "Personal sanitario": [5, 0],
        "Alimentos": [1000, 300],
    }


def test_ca01_cuenta_lo_adjudicado_y_no_lo_que_el_sistema_nacional_no_habilito(
    app, crear_emergencias, cargar_necesidades
) -> None:
    (emergencia,) = crear_emergencias((_en(2025, 9, 10), EstadoEmergencia.activa))
    cargar_necesidades(
        emergencia,
        (100, 80),
        (100, 40, TipoAsignacion.rechazada),
        categorias=[ALIMENTOS, ALIMENTOS],
        adjudicada_en=_en(2025, 9, 12),
    )

    assert _seccion(app).movilizados.total == 80


def test_ca02_el_filtro_de_rubro_deja_una_sola_serie(
    app, crear_emergencias, cargar_necesidades
) -> None:
    (emergencia,) = crear_emergencias((_en(2025, 9, 10), EstadoEmergencia.activa))
    cargar_necesidades(
        emergencia,
        (1000, 1000),
        (5, 5),
        categorias=[ALIMENTOS, SANITARIO],
        adjudicada_en=_en(2025, 9, 20),
    )

    grafico = _seccion(app, ALIMENTOS).movilizados.grafico()

    assert [serie["nombre"] for serie in grafico["series"]] == ["Alimentos"]


def test_el_mes_de_la_adjudicacion_se_toma_en_la_hora_de_argentina(
    app, crear_emergencias, cargar_necesidades
) -> None:
    (emergencia,) = crear_emergencias((_en(2025, 10, 20), EstadoEmergencia.activa))
    # 31/10 a las 22 h en Argentina: en UTC ya es 1/11.
    cargar_necesidades(
        emergencia,
        (10, 10),
        categorias=[AGUA],
        adjudicada_en=datetime(2025, 11, 1, 1, tzinfo=UTC),
    )

    assert _seccion(app).movilizados.tabla().filas == (("2025-10", "Agua", 10),)


def test_sin_adjudicaciones_no_hay_unidades(app, crear_emergencias) -> None:
    crear_emergencias((_en(2025, 9, 10), EstadoEmergencia.registrada))

    movilizados = _seccion(app).movilizados

    assert movilizados.total == 0
    assert movilizados.tabla().vacia
    assert movilizados.rubro_principal is None


# --- Rubros: demanda vs. inhabilitacion -----------------------------------------------


def test_hu11_ca01_demanda_y_tasa_de_inhabilitacion(
    app, crear_emergencias, cargar_necesidades
) -> None:
    """Alimentos pidio 1000; de las 800 ofertadas el Sistema Nacional no habilito 200: 25 %."""
    (emergencia,) = crear_emergencias((_en(2025, 9, 10), EstadoEmergencia.activa))
    cargar_necesidades(
        emergencia,
        (600, 600),
        (400, 200, TipoAsignacion.rechazada),
        categorias=[ALIMENTOS, ALIMENTOS],
    )

    (fila,) = _seccion(app).rubros.filas

    assert (fila.rubro, fila.demandadas, fila.evaluadas, fila.no_habilitadas) == (
        ALIMENTOS,
        1000,
        800,
        200,
    )
    assert fila.tasa_de_inhabilitacion == 25


def test_hu11_ca02_demanda_y_tasa_en_dos_graficos_con_el_mismo_orden(
    app, crear_emergencias, cargar_necesidades
) -> None:
    """Dos medidas de escala distinta van en dos graficos (sin doble eje), alineados por rubro."""
    (emergencia,) = crear_emergencias((_en(2025, 9, 10), EstadoEmergencia.activa))
    cargar_necesidades(
        emergencia,
        (50, 50),
        (900, 600),
        (300, 300, TipoAsignacion.rechazada),
        categorias=[AGUA, ALIMENTOS, ALIMENTOS],
    )

    rubros = _seccion(app).rubros
    demanda = rubros.grafico_de_demanda()
    tasa = rubros.grafico_de_inhabilitacion()

    assert demanda["etiquetas"] == tasa["etiquetas"] == ["Alimentos", "Agua"]
    assert demanda["valores"] == [1200, 50]
    assert tasa["valores"] == [33, 0]
    assert demanda["orientacion"] == tasa["orientacion"] == "horizontal"
    assert tasa["maximo"] == 100
    assert "series" not in demanda and "series" not in tasa
    # Cada rubro conserva su color en los dos graficos.
    assert demanda["tonos"] == tasa["tonos"] == ["serie-3", "serie-4"]


def test_hu11_ca03_un_rubro_sin_ofertas_evaluadas_no_tiene_tasa(
    app, crear_emergencias, cargar_necesidades
) -> None:
    (emergencia,) = crear_emergencias((_en(2025, 9, 10), EstadoEmergencia.activa))
    cargar_necesidades(emergencia, (50, 0), categorias=[AGUA])

    (fila,) = _seccion(app).rubros.filas

    assert fila.tasa_de_inhabilitacion is None
    assert fila.tasa_como_texto == "—"
    tasa = _seccion(app).rubros.grafico_de_inhabilitacion()
    assert tasa["valores"] == [None]
    assert tasa["sinDato"] == "Sin ofertas evaluadas"
