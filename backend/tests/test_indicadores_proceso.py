"""Seccion "Proceso" del panel de auditoria: etapas del proceso y resolucion en termino, con los
datos de Bonita simulados.

Bonita se reemplaza en `app.modulos.indicadores.proceso.consultas`, el unico punto por el que la
seccion habla con el motor. Cada test se nombra por el criterio de aceptacion que verifica.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.errores import ServicioExternoNoDisponible
from app.core.integraciones.bonita.consultas import CasoArchivado, NodoArchivado
from app.core.integraciones.bonita.proceso import NOMBRE_TAREA_SELECCIONAR
from app.extensiones import db
from app.modulos.emergencias.modelos import Emergencia, EstadoEmergencia, NivelGravedad
from app.modulos.indicadores import proceso
from app.modulos.indicadores.periodo import Periodo
from app.modulos.indicadores.proceso import MENSAJE_MOTOR_NO_DISPONIBLE, SIN_OCURRENCIAS

from .conftest import EMAIL_AUDITOR

MARZO_DE_2025 = Periodo(desde=date(2025, 3, 1), hasta=date(2025, 3, 31))
REGISTRO = datetime(2025, 3, 10, 15, tzinfo=UTC)
INICIO_DEL_CASO = datetime(2025, 3, 10, 12, 0)
ALTA, MEDIA = NivelGravedad.alta, NivelGravedad.media


class BonitaFalso:
    """Lo que devuelve el motor: casos terminados con su linea de tiempo y casos abiertos."""

    def __init__(self) -> None:
        self.terminados: dict[str, CasoArchivado] = {}
        self.lineas: dict[str, tuple[NodoArchivado, ...]] = {}
        self.abiertos: set[str] = set()

    def terminar(self, caso_id: str, *, dias: float, seleccionar_en_dias: float | None = None):
        self.terminados[caso_id] = CasoArchivado(
            caso_id, INICIO_DEL_CASO, INICIO_DEL_CASO + timedelta(days=dias)
        )
        nodos = [NodoArchivado("i", "Inicio", "START_EVENT", "completed", INICIO_DEL_CASO, None)]
        if seleccionar_en_dias is not None:
            fin = INICIO_DEL_CASO + timedelta(days=seleccionar_en_dias)
            nodos.append(
                NodoArchivado("s", NOMBRE_TAREA_SELECCIONAR, "USER_TASK", "completed", fin, fin)
            )
        self.lineas[caso_id] = tuple(nodos)


@pytest.fixture
def bonita(monkeypatch: pytest.MonkeyPatch) -> BonitaFalso:
    falso = BonitaFalso()
    consultas = proceso.consultas
    monkeypatch.setattr(
        consultas,
        "foto_del_proceso",
        lambda nombre: consultas.FotoDelProceso(
            definiciones=("1",),
            casos_terminados=dict(falso.terminados),
            casos_abiertos=frozenset(falso.abiertos),
        ),
    )
    monkeypatch.setattr(
        consultas,
        "lineas_de_tiempo",
        lambda casos: {caso.caso_id: falso.lineas[caso.caso_id] for caso in casos},
    )
    return falso


@pytest.fixture
def bonita_caido(monkeypatch: pytest.MonkeyPatch) -> None:
    def _falla(*_args, **_kwargs):
        raise ServicioExternoNoDisponible(detalle={"componente": "bonita"})

    monkeypatch.setattr(proceso.consultas, "foto_del_proceso", _falla)


@pytest.fixture
def emergencias_con_caso(app, crear_emergencias):
    """Registra emergencias del periodo con la gravedad y el caso de Bonita indicados."""

    def _crear(*casos: tuple[NivelGravedad, str]) -> None:
        ids = crear_emergencias(*((REGISTRO, EstadoEmergencia.finalizada, g) for g, _ in casos))
        with app.app_context():
            for emergencia_id, (_, caso_id) in zip(ids, casos, strict=True):
                db.session.get(Emergencia, emergencia_id).bonita_case_id = caso_id
            db.session.commit()

    return _crear


def _seccion(app, gravedad=None):
    with app.app_context():
        return proceso.obtener_seccion_de_proceso(MARZO_DE_2025, gravedad)


# --- Etapas del proceso ---------------------------------------------------------------


def test_ca01_promedio_por_etapa(app, bonita, emergencias_con_caso) -> None:
    """Tres casos cuya tarea "Seleccionar ofertas" tardo 1, 2 y 3 dias: 2,0 dias."""
    emergencias_con_caso((ALTA, "101"), (ALTA, "102"), (MEDIA, "103"))
    for caso, dias in (("101", 1), ("102", 2), ("103", 3)):
        bonita.terminar(caso, dias=10, seleccionar_en_dias=dias)

    etapas = {fila.etapa.etiqueta: fila for fila in _seccion(app).etapas.filas}

    assert etapas["Seleccionar ofertas"].promedio == Decimal("2.0")
    assert etapas["Seleccionar ofertas"].casos == 3
    assert len(etapas) == 4


def test_ca02_el_filtro_de_gravedad_usa_la_gravedad_local(
    app, bonita, emergencias_con_caso
) -> None:
    emergencias_con_caso((ALTA, "101"), (MEDIA, "102"))
    bonita.terminar("101", dias=10, seleccionar_en_dias=1)
    bonita.terminar("102", dias=10, seleccionar_en_dias=5)

    etapas = {fila.etapa.etiqueta: fila for fila in _seccion(app, ALTA).etapas.filas}

    assert etapas["Seleccionar ofertas"].promedio == Decimal("1.0")


def test_ca03_una_etapa_sin_ocurrencias_no_se_muestra_como_cero(
    app, bonita, emergencias_con_caso
) -> None:
    emergencias_con_caso((ALTA, "101"))
    bonita.terminar("101", dias=10, seleccionar_en_dias=1)

    etapas = _seccion(app).etapas
    decidir = next(f for f in etapas.filas if f.etapa.etiqueta.startswith("Decidir"))

    assert decidir.promedio is None
    assert decidir.promedio_como_texto == SIN_OCURRENCIAS
    grafico = etapas.grafico()
    assert grafico["sinDato"] == SIN_OCURRENCIAS
    assert grafico["valores"][1] is None


def test_los_casos_de_bonita_sin_emergencia_en_el_periodo_no_cuentan(
    app, bonita, emergencias_con_caso
) -> None:
    emergencias_con_caso((ALTA, "101"))
    bonita.terminar("101", dias=10, seleccionar_en_dias=1)
    bonita.terminar("999", dias=10, seleccionar_en_dias=9)

    assert _seccion(app).etapas.casos_terminados == 1


# --- Resolucion en termino -------------------------------------------------------------


def test_hu10_ca01_tasa_en_termino_y_tiempo_medio(app, bonita, emergencias_con_caso) -> None:
    """Plazo de 7 dias para Alta; 4 casos de 5, 6, 8 y 10 dias: 50 % y 7,3 dias."""
    emergencias_con_caso(*((ALTA, f"20{i}") for i in range(4)))
    for i, dias in enumerate((5, 6, 8, 10)):
        bonita.terminar(f"20{i}", dias=dias)

    alta = next(f for f in _seccion(app).resolucion.filas if f.gravedad == ALTA)

    assert alta.plazo_dias == 7
    assert alta.porcentaje_en_termino == 50
    assert alta.tiempo_medio == Decimal("7.3")


def test_hu10_ca02_porcentaje_y_tiempo_en_dos_graficos_por_gravedad(
    app, bonita, emergencias_con_caso
) -> None:
    """Sin doble eje: el porcentaje en termino y el tiempo medio van en graficos separados, y el
    del tiempo marca el plazo objetivo de cada gravedad."""
    emergencias_con_caso((ALTA, "301"), (MEDIA, "302"))
    bonita.terminar("301", dias=5)
    bonita.terminar("302", dias=20)

    resolucion = _seccion(app).resolucion
    en_termino = resolucion.grafico_en_termino()
    tiempo = resolucion.grafico_de_tiempo_medio()

    assert en_termino["etiquetas"] == tiempo["etiquetas"] == ["Baja", "Media", "Alta", "Crítica"]
    assert en_termino["valores"] == [None, 0, 100, None]
    assert en_termino["maximo"] == 100
    assert tiempo["valores"] == [None, 20.0, 5.0, None]
    assert tiempo["marcadores"] == {"nombre": "Plazo objetivo", "valores": [30, 15, 7, 3]}
    assert en_termino["sinDato"] == tiempo["sinDato"] == "Sin casos"


def test_hu10_ca03_los_casos_abiertos_no_entran_y_se_informan(
    app, bonita, emergencias_con_caso
) -> None:
    emergencias_con_caso((ALTA, "401"), (ALTA, "402"))
    bonita.terminar("401", dias=5)
    bonita.abiertos = {"402", "999"}

    resolucion = _seccion(app).resolucion

    assert resolucion.casos_terminados == 1
    assert resolucion.casos_abiertos == 1


# --- CA-04: Bonita no disponible -----------------------------------------------------------


def test_ca04_la_seccion_muestra_el_error_con_reintento(
    ingresar_por_formulario, navegar, bonita_caido
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    respuesta = navegar("/auditoria/proceso/datos")

    cuerpo = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert MENSAJE_MOTOR_NO_DISPONIBLE in cuerpo
    assert "Reintentar" in cuerpo
    assert "data-reintentar" in cuerpo


def test_ca04_el_resto_del_panel_sigue_funcionando(
    ingresar_por_formulario, navegar, bonita_caido
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    for ruta in ("", "/emergencias", "/recursos", "/red-de-ongs", "/tiempos-de-respuesta"):
        assert navegar(f"/auditoria{ruta}").status_code == 200, ruta
    # La pantalla de "Proceso" tampoco espera a Bonita: se arma y pide los datos aparte.
    pantalla = navegar("/auditoria/proceso")
    assert pantalla.status_code == 200
    assert "data-carga-diferida" in pantalla.get_data(as_text=True)


def test_ca04_por_json_responde_el_envelope_del_motor(
    cliente_sembrado, ingresar, bonita_caido
) -> None:
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get("/auditoria/proceso")

    assert respuesta.status_code == 503
    assert respuesta.get_json()["error"]["codigo"] == "SERVICIO_EXTERNO_NO_DISPONIBLE"


def test_sin_javascript_la_pantalla_trae_los_datos(
    ingresar_por_formulario, navegar, bonita, emergencias_con_caso
) -> None:
    emergencias_con_caso((ALTA, "101"))
    bonita.terminar("101", dias=5, seleccionar_en_dias=1)
    ingresar_por_formulario(EMAIL_AUDITOR)

    respuesta = navegar("/auditoria/proceso?desde=2025-03-01&hasta=2025-03-31&carga=completa")

    cuerpo = respuesta.get_data(as_text=True)
    assert 'id="grafico-etapas"' in cuerpo
    assert 'id="grafico-en-termino"' in cuerpo
    assert 'id="grafico-tiempo-medio"' in cuerpo
    assert "En término: 100 %" in cuerpo
    assert "data-carga-diferida" not in cuerpo


def test_los_datos_diferidos_conservan_el_periodo_y_el_filtro(
    ingresar_por_formulario, navegar
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    cuerpo = navegar("/auditoria/proceso?desde=2025-03-01&hasta=2025-03-31&gravedad=alta").get_data(
        as_text=True
    )

    assert (
        'data-carga-diferida="/auditoria/proceso/datos?desde=2025-03-01&amp;hasta=2025-03-31'
        '&amp;gravedad=alta"' in cuerpo
    )


def test_los_datos_diferidos_filtran_las_etapas_por_gravedad(
    ingresar_por_formulario, navegar, bonita, emergencias_con_caso
) -> None:
    emergencias_con_caso((ALTA, "101"), (MEDIA, "102"))
    bonita.terminar("101", dias=5, seleccionar_en_dias=1)
    bonita.terminar("102", dias=5, seleccionar_en_dias=3)
    ingresar_por_formulario(EMAIL_AUDITOR)

    respuesta = navegar("/auditoria/proceso/datos?desde=2025-03-01&hasta=2025-03-31&gravedad=alta")

    cuerpo = respuesta.get_data(as_text=True)
    assert respuesta.status_code == 200
    assert 'id="grafico-etapas"' in cuerpo
    assert re.search(r"1,0 día\b", cuerpo), "la etapa de la emergencia Alta (1 día)"
    assert "3,0 días" not in cuerpo


# --- Exportacion de los indicadores de Bonita -------------------------------------------------

PERIODO_DE_MARZO = {"desde": "2025-03-01", "hasta": "2025-03-31"}


@pytest.mark.parametrize("slug", ["etapas-del-proceso", "resolucion-en-termino"])
def test_los_indicadores_de_bonita_se_exportan_en_csv(
    cliente_sembrado, ingresar, bonita, emergencias_con_caso, slug
) -> None:
    emergencias_con_caso((ALTA, "101"))
    bonita.terminar("101", dias=5, seleccionar_en_dias=1)
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get(
        f"/auditoria/exportaciones/{slug}.csv", query_string=PERIODO_DE_MARZO
    )

    assert respuesta.status_code == 200
    assert respuesta.headers["Content-Disposition"].endswith(
        f'filename="rescuesync-{slug}-2025-03-01_2025-03-31.csv"'
    )
    assert len(respuesta.get_data(as_text=True).splitlines()) > 1


def test_el_json_de_etapas_lleva_el_filtro_de_gravedad(
    cliente_sembrado, ingresar, bonita, emergencias_con_caso
) -> None:
    emergencias_con_caso((ALTA, "101"))
    bonita.terminar("101", dias=5, seleccionar_en_dias=1)
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get(
        "/auditoria/exportaciones/etapas-del-proceso.json",
        query_string={**PERIODO_DE_MARZO, "gravedad": "alta"},
    )

    datos = respuesta.get_json(force=True)
    assert datos["filtros"] == {"desde": "2025-03-01", "hasta": "2025-03-31", "gravedad": "alta"}


def test_sin_motor_la_exportacion_vuelve_a_la_seccion_con_el_aviso(
    ingresar_por_formulario, navegar, bonita_caido
) -> None:
    ingresar_por_formulario(EMAIL_AUDITOR)

    respuesta = navegar(
        "/auditoria/exportaciones/etapas-del-proceso.csv?desde=2025-03-01&hasta=2025-03-31"
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].startswith("/auditoria/proceso?desde=2025-03-01")
    pantalla = navegar(respuesta.headers["Location"]).get_data(as_text=True)
    assert "Reintentá la exportación" in pantalla


def test_sin_motor_la_exportacion_por_json_responde_el_envelope(
    cliente_sembrado, ingresar, bonita_caido
) -> None:
    ingresar(EMAIL_AUDITOR)

    respuesta = cliente_sembrado.get(
        "/auditoria/exportaciones/resolucion-en-termino.json", query_string=PERIODO_DE_MARZO
    )

    assert respuesta.status_code == 503
    assert respuesta.get_json()["error"]["codigo"] == "SERVICIO_EXTERNO_NO_DISPONIBLE"
