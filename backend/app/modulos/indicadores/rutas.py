"""Endpoints del panel de auditoria (perfil Auditor / Directivo).

Todo el blueprint vive bajo /auditoria y es de solo lectura: expone unicamente GET. Cada ruta se
protege con `al_denegar=SeccionAjenaAlRol`, de modo que los demas perfiles vuelven a su portal
desde el navegador y reciben 403 PERMISO_DENEGADO por JSON.

El panel se divide en secciones (pestañas), declaradas en `secciones.py`. Todas comparten el
periodo, que se resuelve con `_resolver_periodo`; los filtros propios de una seccion (como la
gravedad de "Emergencias") viajan solo en su URL. `_renderizar_seccion` concentra lo que tiene
cada ruta de seccion: periodo, filtros, JSON o pantalla, y 400 si un filtro es invalido.

Cada indicador se descarga en CSV o JSON desde `/auditoria/exportaciones/<slug>.<formato>`, con
los mismos filtros y calculado por la misma funcion que su grafico.

La seccion "Proceso" consulta Bonita. Su pantalla se arma sin esperar al motor y los datos llegan
despues, desde `/auditoria/proceso/datos`: si Bonita tarda o falla, solo esa region lo muestra.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from flask import (
    Blueprint,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.core.acceso.autorizacion import requiere_permiso
from app.core.acceso.permisos import INDICADORES_EXPORTAR, INDICADORES_VER
from app.core.errores import RecursoNoEncontrado, SeccionAjenaAlRol, SolicitudInvalida
from app.core.interfaz.formularios import errores_de
from app.core.interfaz.navegacion import EntradaDeMenu
from app.core.interfaz.vistas import ERROR, pide_json
from app.core.logging import registrar_evento
from app.modulos.indicadores import secciones
from app.modulos.indicadores.exportacion import a_csv, a_json, nombre_de_archivo
from app.modulos.indicadores.formularios import (
    MENSAJE_PERIODO_INVERTIDO,
    FiltroDeSeccion,
    FormularioDePeriodo,
)
from app.modulos.indicadores.periodo import (
    DIAS_DEL_PERIODO_POR_DEFECTO,
    Periodo,
    atajos_de_periodo,
    hoy_en_la_interfaz,
)
from app.modulos.indicadores.proceso import ERRORES_DEL_MOTOR, MENSAJE_MOTOR_NO_DISPONIBLE
from app.modulos.indicadores.secciones import SeccionDelPanel

blueprint_indicadores = Blueprint("indicadores", __name__)

ENTRADA_DE_MENU = EntradaDeMenu(
    endpoint="indicadores.panel",
    titulo="Panel de auditoría",
    permiso=INDICADORES_VER,
    descripcion="Resumen y métricas de la actividad de la red",
    icono="grafico",
    orden=10,
)

# La barra de pestañas la arma base.html con el catalogo de secciones.
PESTANAS_DEL_PANEL = secciones.SECCIONES

FORMATOS_DE_EXPORTACION = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json; charset=utf-8",
}

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

    Toda ruta del panel (secciones, datos diferidos, exportaciones) resuelve su periodo con esta
    funcion, para que todas las secciones muestren siempre el mismo.
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


@dataclass(frozen=True, slots=True)
class SolicitudDeSeccion:
    """El periodo y los filtros de una seccion, ya resueltos desde la URL.

    `valores` son los filtros listos para `obtener(periodo, **valores)` (un filtro invalido no
    se aplica y vale su valor por defecto); `aplicados`, los que viajan en las URLs para que el
    resto de los enlaces los conserve; `errores`, los de periodo y filtros juntos.
    """

    hoy: date
    periodo: Periodo
    formulario: FormularioDePeriodo
    filtros: dict[str, FiltroDeSeccion]
    valores: dict[str, Any]
    aplicados: dict[str, str]
    errores: dict[str, list[str]]


def _resolver_solicitud(seccion: SeccionDelPanel) -> SolicitudDeSeccion:
    hoy = hoy_en_la_interfaz()
    periodo, formulario = _resolver_periodo(hoy)
    filtros, valores, aplicados = {}, {}, {}
    errores = errores_de(formulario)
    for clase in seccion.filtros:
        filtro = clase(formdata=request.args)
        valor = filtro.valor_valido()
        filtros[clase.campo] = filtro
        valores[clase.campo] = valor
        aplicados.update(filtro.aplicado(valor))
        errores.update(errores_de(filtro))
    return SolicitudDeSeccion(hoy, periodo, formulario, filtros, valores, aplicados, errores)


def _enlaces_de_exportacion(solicitud: SolicitudDeSeccion) -> Callable[[str], dict[str, str]]:
    """Las descargas de un indicador con el periodo y los filtros vigentes.

    `csv` y `json` son las URLs de los datos; `png` es el nombre con que se guarda la imagen del
    grafico, que el navegador arma desde el lienzo (no pasa por el servidor). Cuando dos graficos
    comparten un indicador (y su tabla), `imagen` distingue el nombre del PNG de cada uno.
    """

    def _enlaces(slug: str, imagen: str | None = None) -> dict[str, str]:
        enlaces = {
            formato: url_for(
                "indicadores.exportar",
                slug=slug,
                formato=formato,
                desde=solicitud.periodo.desde.isoformat(),
                hasta=solicitud.periodo.hasta.isoformat(),
                **solicitud.aplicados,
            )
            for formato in FORMATOS_DE_EXPORTACION
        }
        enlaces["png"] = nombre_de_archivo(imagen or slug, solicitud.periodo, "png")
        return enlaces

    return _enlaces


def _contexto_del_panel(solicitud: SolicitudDeSeccion) -> dict[str, Any]:
    """Lo que necesita base.html: periodo, atajos, pestañas y filtros de la seccion.

    El formulario de periodo y sus atajos conservan los filtros de la seccion, para que cambiar
    el periodo no los borre.
    """
    return {
        "formulario": solicitud.formulario,
        "periodo": solicitud.periodo,
        "atajos": atajos_de_periodo(solicitud.hoy),
        "hoy": solicitud.hoy,
        "mensaje_periodo_invertido": MENSAJE_PERIODO_INVERTIDO,
        "pestanas": PESTANAS_DEL_PANEL,
        "filtros": solicitud.filtros,
        "filtros_de_la_seccion": solicitud.aplicados,
        "exportacion": _enlaces_de_exportacion(solicitud),
    }


def _renderizar_seccion(seccion: SeccionDelPanel):
    """Responde una seccion: JSON con sus datos o su pantalla.

    Un filtro invalido (de periodo o de la seccion) no se aplica: por JSON corta con 400
    SOLICITUD_INVALIDA; en la pantalla se muestra igual, con sus errores y estado 400.
    """
    solicitud = _resolver_solicitud(seccion)
    if solicitud.errores and pide_json():
        raise SolicitudInvalida(detalle=solicitud.errores)

    resultado = seccion.obtener(solicitud.periodo, **solicitud.valores)

    if pide_json():
        datos = resultado.a_diccionario()
        if seccion.clave_json:
            datos = {seccion.clave_json: datos}
        return jsonify({"periodo": solicitud.periodo.a_diccionario(), **datos})

    contexto = {**_contexto_del_panel(solicitud), "seccion": resultado}
    estado = 400 if solicitud.errores else 200
    return render_template(seccion.plantilla, **contexto), estado


@blueprint_indicadores.get("")
@requiere_permiso(INDICADORES_VER, al_denegar=SeccionAjenaAlRol)
def panel():
    return _renderizar_seccion(secciones.RESUMEN)


@blueprint_indicadores.get("/emergencias")
@requiere_permiso(INDICADORES_VER, al_denegar=SeccionAjenaAlRol)
def emergencias():
    """Emergencias por estado y cobertura de las finalizadas, con filtro de gravedad."""
    return _renderizar_seccion(secciones.EMERGENCIAS)


@blueprint_indicadores.get("/convocatorias")
@requiere_permiso(INDICADORES_VER, al_denegar=SeccionAjenaAlRol)
def convocatorias():
    """Decisiones ante cobertura insuficiente, con el detalle filtrable por decision."""
    return _renderizar_seccion(secciones.CONVOCATORIAS)


@blueprint_indicadores.get("/recursos")
@requiere_permiso(INDICADORES_VER, al_denegar=SeccionAjenaAlRol)
def recursos():
    """Recursos movilizados por mes y rubro, y demanda por rubro vs. inhabilitacion."""
    return _renderizar_seccion(secciones.RECURSOS)


@blueprint_indicadores.get("/red-de-ongs")
@requiere_permiso(INDICADORES_VER, al_denegar=SeccionAjenaAlRol)
def red_de_ongs():
    """Consorcios y ranking de ONGs, con el orden de la tabla del ranking como filtro."""
    return _renderizar_seccion(secciones.RED_DE_ONGS)


@blueprint_indicadores.get("/tiempos-de-respuesta")
@requiere_permiso(INDICADORES_VER, al_denegar=SeccionAjenaAlRol)
def tiempos_de_respuesta():
    """Tiempo medio entre el registro de la emergencia y su primera adjudicacion."""
    return _renderizar_seccion(secciones.TIEMPOS_DE_RESPUESTA)


def _url_de_la_seccion(endpoint: str, solicitud: SolicitudDeSeccion, **extra: str) -> str:
    return url_for(
        endpoint,
        desde=solicitud.periodo.desde.isoformat(),
        hasta=solicitud.periodo.hasta.isoformat(),
        **solicitud.aplicados,
        **extra,
    )


def _url_sin_javascript(solicitud: SolicitudDeSeccion) -> str:
    """La pantalla de "Proceso" con los datos incluidos, para navegadores sin JavaScript."""
    return _url_de_la_seccion("indicadores.proceso", solicitud, carga="completa")


def _datos_del_proceso(solicitud: SolicitudDeSeccion) -> dict[str, Any]:
    """Los datos de Bonita para la plantilla, o el aviso de que el motor no respondio.

    El error no corta la pantalla: se muestra en la region de datos, con un boton que la vuelve a
    pedir, y el resto del panel sigue funcionando.
    """
    try:
        resultado = secciones.PROCESO.obtener(solicitud.periodo, **solicitud.valores)
    except ERRORES_DEL_MOTOR as error:
        registrar_evento(
            logging.WARNING,
            "indicadores_bonita_no_disponible",
            "No se pudieron obtener los datos de Bonita para el panel de auditoria",
            codigo=error.codigo,
        )
        return {"seccion": None, "mensaje_de_error": MENSAJE_MOTOR_NO_DISPONIBLE}
    return {"seccion": resultado, "mensaje_de_error": None}


@blueprint_indicadores.get("/proceso")
@requiere_permiso(INDICADORES_VER, al_denegar=SeccionAjenaAlRol)
def proceso():
    """Etapas del proceso y resolucion en termino, con datos de Bonita.

    Por JSON responde los datos (o el error del motor, con su envelope). La pantalla se arma sin
    consultar Bonita y la region de datos la completa `proceso_datos` cuando el navegador la pide.
    Con `?carga=completa` (el enlace para navegadores sin JavaScript) los datos vienen incluidos.
    """
    if pide_json():
        return _renderizar_seccion(secciones.PROCESO)

    solicitud = _resolver_solicitud(secciones.PROCESO)
    contexto = {
        **_contexto_del_panel(solicitud),
        "url_de_datos": _url_de_la_seccion("indicadores.proceso_datos", solicitud),
        "url_sin_javascript": _url_sin_javascript(solicitud),
        "seccion": None,
        "mensaje_de_error": None,
        "con_datos": request.args.get("carga") == "completa",
    }
    if contexto["con_datos"]:
        contexto.update(_datos_del_proceso(solicitud))
    estado = 400 if solicitud.errores else 200
    return render_template(secciones.PROCESO.plantilla, **contexto), estado


@blueprint_indicadores.get("/proceso/datos")
@requiere_permiso(INDICADORES_VER, al_denegar=SeccionAjenaAlRol)
def proceso_datos():
    """Fragmento HTML con los datos de Bonita de la seccion "Proceso" (lo pide indicadores.js)."""
    solicitud = _resolver_solicitud(secciones.PROCESO)
    return render_template(
        "indicadores/proceso_datos.html",
        **_contexto_del_panel(solicitud),
        **_datos_del_proceso(solicitud),
        url_sin_javascript=_url_sin_javascript(solicitud),
    )


MENSAJE_EXPORTACION_SIN_MOTOR = (
    f"{MENSAJE_MOTOR_NO_DISPONIBLE} Reintentá la exportación en unos minutos."
)


@blueprint_indicadores.get("/exportaciones/<slug>.<formato>")
@requiere_permiso(INDICADORES_EXPORTAR, al_denegar=SeccionAjenaAlRol)
def exportar(slug: str, formato: str):
    """Descarga los datos de un indicador en CSV o JSON, con los filtros de la URL.

    Usa la misma funcion y la misma tabla que el grafico, asi lo descargado es lo que se ve.
    """
    entrada = secciones.INDICADORES_EXPORTABLES.get(slug)
    if entrada is None or formato not in FORMATOS_DE_EXPORTACION:
        raise RecursoNoEncontrado("No existe ese indicador o ese formato de exportación.")
    seccion, indicador = entrada

    solicitud = _resolver_solicitud(seccion)
    if solicitud.errores:
        raise SolicitudInvalida(detalle=solicitud.errores)

    try:
        datos = seccion.obtener(solicitud.periodo, **solicitud.valores)
    except ERRORES_DEL_MOTOR as error:
        # Solo los indicadores de Bonita llegan aca. Un cliente JSON recibe el envelope del
        # contrato; al navegador se lo devuelve a la seccion con el aviso, en vez de dejarlo
        # frente a un JSON de error en lugar del archivo.
        if pide_json():
            raise
        registrar_evento(
            logging.WARNING,
            "indicadores_bonita_no_disponible",
            "No se pudo exportar un indicador de Bonita",
            codigo=error.codigo,
            indicador=slug,
        )
        flash(MENSAJE_EXPORTACION_SIN_MOTOR, ERROR)
        return redirect(_url_de_la_seccion(seccion.endpoint, solicitud))
    tabla = indicador.tabla(datos)

    if formato == "csv":
        contenido = a_csv(tabla)
    else:
        filtros = {
            "desde": solicitud.periodo.desde,
            "hasta": solicitud.periodo.hasta,
            **solicitud.valores,
        }
        contenido = json.dumps(
            a_json(
                indicador=slug,
                titulo=indicador.titulo,
                filtros=filtros,
                tabla=tabla,
                generado_en=datetime.now(UTC),
            ),
            ensure_ascii=False,
            indent=2,
        )

    archivo = nombre_de_archivo(slug, solicitud.periodo, formato)
    return Response(
        contenido,
        content_type=FORMATOS_DE_EXPORTACION[formato],
        headers={"Content-Disposition": f'attachment; filename="{archivo}"'},
    )
