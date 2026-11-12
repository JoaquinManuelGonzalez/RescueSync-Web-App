"""Endpoints del panel de auditoria (perfil Auditor / Directivo).

Todo el blueprint vive bajo /auditoria y es de solo lectura: expone unicamente GET. Cada ruta se
protege con `al_denegar=SeccionAjenaAlRol`, de modo que los demas perfiles vuelven a su portal
desde el navegador y reciben 403 PERMISO_DENEGADO por JSON.

El panel se divide en secciones, cada una con su ruta y su pestaña (`PESTANAS_DEL_PANEL`). Todas
comparten el periodo, que se resuelve con `_resolver_periodo`; los filtros propios de una seccion
(como la gravedad de "Emergencias") viajan solo en su URL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from flask import Blueprint, jsonify, render_template, request, session

from app.core.acceso.autorizacion import requiere_permiso
from app.core.acceso.permisos import INDICADORES_VER
from app.core.errores import SeccionAjenaAlRol, SolicitudInvalida
from app.core.interfaz.formularios import errores_de
from app.core.interfaz.navegacion import EntradaDeMenu
from app.core.interfaz.vistas import pide_json
from app.modulos.emergencias.modelos import NivelGravedad
from app.modulos.indicadores import servicios
from app.modulos.indicadores.formularios import (
    MENSAJE_PERIODO_INVERTIDO,
    FormularioDeGravedad,
    FormularioDePeriodo,
)
from app.modulos.indicadores.periodo import (
    DIAS_DEL_PERIODO_POR_DEFECTO,
    Periodo,
    atajos_de_periodo,
    hoy_en_la_interfaz,
)

blueprint_indicadores = Blueprint("indicadores", __name__)

ENTRADA_DE_MENU = EntradaDeMenu(
    endpoint="indicadores.panel",
    titulo="Panel de auditoría",
    permiso=INDICADORES_VER,
    descripcion="Resumen y métricas de la actividad de la red",
    icono="grafico",
    orden=10,
)


@dataclass(frozen=True, slots=True)
class PestanaDelPanel:
    endpoint: str
    titulo: str
    icono: str


# Una seccion nueva del panel suma aca su pestaña; la barra de pestañas la arma base.html.
PESTANAS_DEL_PANEL = (
    PestanaDelPanel("indicadores.panel", "Resumen", "grafico"),
    PestanaDelPanel("indicadores.emergencias", "Emergencias", "advertencia"),
)

# El ultimo periodo aplicado se conserva durante la sesion: al volver al panel el auditor lo
# encuentra como lo dejo, y solo la primera vez ve el periodo por defecto.
CLAVE_DEL_PERIODO_EN_SESION = "indicadores.periodo"


def _periodo_recordado() -> Periodo | None:
    datos = session.get(CLAVE_DEL_PERIODO_EN_SESION)
    try:
        return Periodo(
            desde=date.fromisoformat(datos["desde"]), hasta=date.fromisoformat(datos["hasta"])
        )
    except KeyError, TypeError, ValueError:
        return None


def _recordar_periodo(periodo: Periodo) -> None:
    session[CLAVE_DEL_PERIODO_EN_SESION] = {
        "desde": periodo.desde.isoformat(),
        "hasta": periodo.hasta.isoformat(),
    }


def _resolver_periodo(hoy: date) -> tuple[Periodo, FormularioDePeriodo]:
    """El periodo sobre el que se calcula el panel, y el formulario que lo muestra.

    - Sin filtro en la URL: el ultimo aplicado en la sesion o, la primera vez, los ultimos 30 dias.
    - Con un filtro valido: se aplica y queda recordado.
    - Con un filtro invalido: no se aplica. El periodo sigue siendo el anterior y el formulario
      vuelve con lo que se tipeo y sus errores.

    Toda ruta nueva del panel (graficos, exportaciones) resuelve su periodo con esta funcion,
    para que todas las secciones muestren siempre el mismo.
    """
    vigente = _periodo_recordado() or Periodo.ultimos_dias(DIAS_DEL_PERIODO_POR_DEFECTO, hoy=hoy)

    if "desde" not in request.args and "hasta" not in request.args:
        formulario = FormularioDePeriodo(
            formdata=None, data={"desde": vigente.desde, "hasta": vigente.hasta}
        )
        return vigente, formulario

    formulario = FormularioDePeriodo(formdata=request.args)
    if not formulario.validate():
        return vigente, formulario

    periodo = formulario.periodo()
    _recordar_periodo(periodo)
    return periodo, formulario


def _contexto_del_panel(
    hoy: date,
    periodo: Periodo,
    formulario: FormularioDePeriodo,
    filtros_de_la_seccion: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Lo que necesita base.html: periodo, atajos y pestañas.

    `filtros_de_la_seccion` son los filtros propios de la seccion ya aplicados. El formulario de
    periodo y sus atajos los conservan, para que cambiar el periodo no los borre.
    """
    return {
        "formulario": formulario,
        "periodo": periodo,
        "atajos": atajos_de_periodo(hoy),
        "hoy": hoy,
        "mensaje_periodo_invertido": MENSAJE_PERIODO_INVERTIDO,
        "pestanas": PESTANAS_DEL_PANEL,
        "filtros_de_la_seccion": filtros_de_la_seccion or {},
    }


@blueprint_indicadores.get("")
@requiere_permiso(INDICADORES_VER, al_denegar=SeccionAjenaAlRol)
def panel():
    hoy = hoy_en_la_interfaz()
    periodo, formulario = _resolver_periodo(hoy)

    if formulario.errors and pide_json():
        raise SolicitudInvalida(detalle=errores_de(formulario))

    resumen = servicios.obtener_resumen_de_actividad(periodo)

    if pide_json():
        return jsonify({"periodo": periodo.a_diccionario(), "resumen": resumen.a_diccionario()})

    contexto = {**_contexto_del_panel(hoy, periodo, formulario), "resumen": resumen}
    # El filtro invalido no se aplico, pero la pantalla se muestra igual, con sus errores.
    estado = 400 if formulario.errors else 200
    return render_template("indicadores/panel.html", **contexto), estado


@blueprint_indicadores.get("/emergencias")
@requiere_permiso(INDICADORES_VER, al_denegar=SeccionAjenaAlRol)
def emergencias():
    """Emergencias por estado y cobertura de las finalizadas, con filtro de gravedad.

    Un filtro de gravedad invalido no se aplica (se muestran todas) y vuelve con su error, igual
    que el de periodo. Por JSON, cualquiera de los dos corta con 400 SOLICITUD_INVALIDA.
    """
    hoy = hoy_en_la_interfaz()
    periodo, formulario = _resolver_periodo(hoy)
    filtro = FormularioDeGravedad(formdata=request.args)
    gravedad = filtro.gravedad_elegida() if filtro.validate() else None

    errores = {**errores_de(formulario), **errores_de(filtro)}
    if errores and pide_json():
        raise SolicitudInvalida(detalle=errores)

    seccion = servicios.obtener_seccion_de_emergencias(periodo, gravedad)

    if pide_json():
        return jsonify({"periodo": periodo.a_diccionario(), **seccion.a_diccionario()})

    filtros_de_la_seccion = {"gravedad": gravedad.value} if gravedad else {}
    contexto = {
        **_contexto_del_panel(hoy, periodo, formulario, filtros_de_la_seccion),
        "seccion": seccion,
        "filtro_de_gravedad": filtro,
        "niveles_de_gravedad": list(NivelGravedad),
    }
    estado = 400 if errores else 200
    return render_template("indicadores/emergencias.html", **contexto), estado
