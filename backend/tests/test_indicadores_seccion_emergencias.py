"""Seccion "Emergencias" del panel de auditoria: estados y cobertura, calculados con la BD.

Cada test se nombra por el criterio de aceptacion de la HU que verifica. Las emergencias se
registran en marzo de 2025: ninguna semilla cae en ese anio, asi que los conteos son exactos.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.modulos.emergencias.modelos import EstadoEmergencia, EstadoLote, NivelGravedad
from app.modulos.indicadores.periodo import Periodo
from app.modulos.indicadores.servicios import PorcionDeCobertura, obtener_seccion_de_emergencias
from app.modulos.ofertas.modelos import TipoAsignacion

MARZO_DE_2025 = Periodo(desde=date(2025, 3, 1), hasta=date(2025, 3, 31))
MEDIADOS_DE_MARZO = datetime(2025, 3, 15, 15, 0, tzinfo=UTC)
FINALIZADA = EstadoEmergencia.finalizada


def _por_estado(seccion) -> dict[EstadoEmergencia, int]:
    return {fila.estado: fila.cantidad for fila in seccion.por_estado}


def _cobertura(app, gravedad: NivelGravedad | None = None):
    with app.app_context():
        return obtener_seccion_de_emergencias(MARZO_DE_2025, gravedad).cobertura


# --- CA-01: distribucion por estado ----------------------------------------------


def test_ca01_cuenta_las_emergencias_del_periodo_en_cada_estado(app, crear_emergencias) -> None:
    crear_emergencias(
        *[(MEDIADOS_DE_MARZO, EstadoEmergencia.activa)] * 3,
        *[(MEDIADOS_DE_MARZO, EstadoEmergencia.en_evaluacion)] * 2,
        *[(MEDIADOS_DE_MARZO, FINALIZADA)] * 5,
        (datetime(2025, 4, 2, 15, tzinfo=UTC), EstadoEmergencia.activa),  # fuera del periodo
    )

    with app.app_context():
        seccion = obtener_seccion_de_emergencias(MARZO_DE_2025)

    # Todos los estados, en el orden del ciclo de vida, aunque no tengan emergencias.
    assert [fila.estado for fila in seccion.por_estado] == list(EstadoEmergencia)
    assert _por_estado(seccion) == {
        EstadoEmergencia.registrada: 0,
        EstadoEmergencia.en_evaluacion: 2,
        EstadoEmergencia.activa: 3,
        EstadoEmergencia.finalizada: 5,
        EstadoEmergencia.cancelada: 0,
    }
    assert seccion.registradas == 10


def test_los_graficos_de_la_seccion_se_arman_en_el_servidor(
    app, crear_emergencias, cargar_necesidades
) -> None:
    (completa,) = crear_emergencias((MEDIADOS_DE_MARZO, FINALIZADA))
    cargar_necesidades(completa, (100, 100))

    with app.app_context():
        seccion = obtener_seccion_de_emergencias(MARZO_DE_2025)

    por_estado = seccion.grafico_por_estado()
    assert por_estado["tipo"] == "barras"
    assert por_estado["etiquetas"][0] == "Registrada"
    assert por_estado["tonos"] == ["neutro", "info", "primario", "exito", "tenue"]
    assert por_estado["detalles"][0] == "Esperando la definición de lotes"
    assert por_estado["detalles"][3] is None, "una finalizada no espera nada"
    assert por_estado["unidad"] == ["emergencia", "emergencias"]

    cobertura = seccion.grafico_de_cobertura()
    assert cobertura["tipo"] == "dona"
    assert cobertura["etiquetas"] == ["Cobertura total", "Cobertura parcial"]
    assert cobertura["valores"] == [1, 0]
    assert cobertura["porcentajes"] == [100, 0]


# --- CA-02: cobertura de las finalizadas -----------------------------------------


def test_ca02_clasifica_las_finalizadas_en_cobertura_total_y_parcial(
    app, crear_emergencias, cargar_necesidades
) -> None:
    *completas, incompleta = crear_emergencias(*[(MEDIADOS_DE_MARZO, FINALIZADA)] * 5)
    for emergencia_id in completas:
        cargar_necesidades(emergencia_id, (100, 100))
    cargar_necesidades(incompleta, (50, 50), (50, 10))  # 60 de 100

    cobertura = _cobertura(app)

    assert cobertura.finalizadas == 5
    assert cobertura.total == PorcionDeCobertura(cantidad=4, porcentaje=80)
    assert cobertura.parcial == PorcionDeCobertura(cantidad=1, porcentaje=20)
    assert cobertura.sin_necesidades == 0
    assert [(e.id, e.porcentaje) for e in cobertura.con_faltantes] == [(incompleta, 60)]


def test_la_cobertura_suma_todos_los_lotes_de_la_emergencia(
    app, crear_emergencias, cargar_necesidades
) -> None:
    (emergencia_id,) = crear_emergencias((MEDIADOS_DE_MARZO, FINALIZADA))
    cargar_necesidades(emergencia_id, (30, 30))
    cargar_necesidades(emergencia_id, (70, 35))

    cobertura = _cobertura(app)

    assert cobertura.con_faltantes[0].porcentaje == 65  # 65 de 100


def test_lo_que_sobra_de_un_item_no_tapa_lo_que_falta_de_otro(
    app, crear_emergencias, cargar_necesidades
) -> None:
    """20 de agua para 10 pedidos y nada de los otros 10: cubre 10 de 20, no 20 de 20."""
    (emergencia_id,) = crear_emergencias((MEDIADOS_DE_MARZO, FINALIZADA))
    cargar_necesidades(emergencia_id, (10, 20), (10, 0))

    cobertura = _cobertura(app)

    assert cobertura.parcial.cantidad == 1
    assert cobertura.con_faltantes[0].porcentaje == 50


def test_solo_cubren_los_aportes_habilitados_por_el_sistema_nacional(
    app, crear_emergencias, cargar_necesidades
) -> None:
    (emergencia_id,) = crear_emergencias((MEDIADOS_DE_MARZO, FINALIZADA))
    cargar_necesidades(
        emergencia_id,
        (10, 10, TipoAsignacion.apoyo),
        (10, 10, TipoAsignacion.rechazada),
        (10, 10, TipoAsignacion.pendiente),
        (10, 10, TipoAsignacion.principal),
    )

    cobertura = _cobertura(app)

    assert cobertura.con_faltantes[0].porcentaje == 50  # apoyo y principal: 20 de 40


def test_los_lotes_cancelados_no_son_necesidades(
    app, crear_emergencias, cargar_necesidades
) -> None:
    (emergencia_id,) = crear_emergencias((MEDIADOS_DE_MARZO, FINALIZADA))
    cargar_necesidades(emergencia_id, (10, 10))
    cargar_necesidades(emergencia_id, (50, 0), estado_del_lote=EstadoLote.cancelado)

    assert _cobertura(app).total.cantidad == 1


def test_una_finalizada_sin_necesidades_queda_fuera_de_la_torta(
    app, crear_emergencias, cargar_necesidades
) -> None:
    con_lotes, _sin_lotes = crear_emergencias(*[(MEDIADOS_DE_MARZO, FINALIZADA)] * 2)
    cargar_necesidades(con_lotes, (10, 10))

    cobertura = _cobertura(app)

    assert cobertura.finalizadas == 2
    assert cobertura.evaluadas == 1
    assert cobertura.sin_necesidades == 1
    assert cobertura.total == PorcionDeCobertura(cantidad=1, porcentaje=100)


def test_solo_las_finalizadas_tienen_cobertura(app, crear_emergencias, cargar_necesidades) -> None:
    activa, cancelada = crear_emergencias(
        (MEDIADOS_DE_MARZO, EstadoEmergencia.activa),
        (MEDIADOS_DE_MARZO, EstadoEmergencia.cancelada),
    )
    cargar_necesidades(activa, (10, 0))
    cargar_necesidades(cancelada, (10, 0))

    cobertura = _cobertura(app)

    assert (cobertura.finalizadas, cobertura.evaluadas, cobertura.con_faltantes) == (0, 0, ())


def test_las_finalizadas_con_faltantes_van_de_peor_a_mejor_cobertura(
    app, crear_emergencias, cargar_necesidades
) -> None:
    al_80, al_20, al_50 = crear_emergencias(
        *[(MEDIADOS_DE_MARZO, FINALIZADA, NivelGravedad.critica)] * 3
    )
    cargar_necesidades(al_80, (10, 8))
    cargar_necesidades(al_20, (10, 2))
    cargar_necesidades(al_50, (10, 5))

    con_faltantes = _cobertura(app).con_faltantes

    assert [(e.id, e.porcentaje) for e in con_faltantes] == [(al_20, 20), (al_50, 50), (al_80, 80)]
    assert con_faltantes[0].gravedad is NivelGravedad.critica
    assert con_faltantes[0].titulo.startswith("Emergencia de prueba")


# --- CA-03: apertura por gravedad ------------------------------------------------


def test_ca03_la_gravedad_acota_toda_la_seccion(app, crear_emergencias, cargar_necesidades) -> None:
    alta, media, _activa = crear_emergencias(
        (MEDIADOS_DE_MARZO, FINALIZADA, NivelGravedad.alta),
        (MEDIADOS_DE_MARZO, FINALIZADA, NivelGravedad.media),
        (MEDIADOS_DE_MARZO, EstadoEmergencia.activa, NivelGravedad.media),
    )
    cargar_necesidades(alta, (10, 10))
    cargar_necesidades(media, (10, 5))

    with app.app_context():
        seccion = obtener_seccion_de_emergencias(MARZO_DE_2025, NivelGravedad.alta)

    assert seccion.gravedad is NivelGravedad.alta
    assert seccion.registradas == 1
    assert _por_estado(seccion)[EstadoEmergencia.activa] == 0
    assert seccion.cobertura.total == PorcionDeCobertura(cantidad=1, porcentaje=100)
    assert seccion.cobertura.parcial == PorcionDeCobertura(cantidad=0, porcentaje=0)


# --- Contrato del JSON -----------------------------------------------------------


def test_la_seccion_se_serializa_con_el_contrato_del_json(
    app, crear_emergencias, cargar_necesidades
) -> None:
    (emergencia_id,) = crear_emergencias((MEDIADOS_DE_MARZO, FINALIZADA, NivelGravedad.alta))
    cargar_necesidades(emergencia_id, (10, 6))

    with app.app_context():
        datos = obtener_seccion_de_emergencias(MARZO_DE_2025, NivelGravedad.alta).a_diccionario()

    assert datos["filtros"] == {"gravedad": "alta"}
    assert datos["registradas"] == 1
    finalizadas = datos["por_estado"][3]
    assert finalizadas == {"estado": "finalizada", "etiqueta": "Finalizada", "cantidad": 1}
    faltante = datos["cobertura"].pop("con_faltantes")
    assert datos["cobertura"] == {
        "finalizadas": 1,
        "evaluadas": 1,
        "sin_necesidades": 0,
        "total": {"cantidad": 0, "porcentaje": 0},
        "parcial": {"cantidad": 1, "porcentaje": 100},
    }
    assert faltante == [
        {
            "id": emergencia_id,
            "titulo": faltante[0]["titulo"],
            "gravedad": "alta",
            "gravedad_etiqueta": "Alta",
            "porcentaje": 60,
        }
    ]
