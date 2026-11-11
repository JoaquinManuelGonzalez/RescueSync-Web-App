"""Rutas y vistas del módulo de ejecución y cierre."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.core.acceso.autorizacion import requiere_permiso
from app.core.acceso.permisos import EJECUCION_MARCAR_ACTIVIDAD
from app.core.errores import ErrorDeAplicacion
from app.core.interfaz.navegacion import EntradaDeMenu
from app.modulos.ejecucion_cierre import servicios
from app.modulos.ejecucion_cierre.formularios import FormularioFinalizarTarea
from app.modulos.ejecucion_cierre.modelos import EstadoTareaEjecucion

blueprint_ejecucion = Blueprint("ejecucion", __name__)

ENTRADA_DE_MENU = EntradaDeMenu(
    endpoint="ejecucion.listar_tareas",
    titulo="Mis Tareas",
    permiso=EJECUCION_MARCAR_ACTIVIDAD,
    descripcion="Seguimiento y finalización de tareas adjudicadas a tu ONG",
    icono="lista",
    orden=45,
)


@blueprint_ejecucion.get("/tareas")
@login_required
@requiere_permiso(EJECUCION_MARCAR_ACTIVIDAD)
def listar_tareas():
    """Panel de tareas asignadas para la ONG del usuario actual."""
    organizacion_id = getattr(current_user, "organizacion_id", None)
    if not organizacion_id:
        flash("Tu usuario no tiene una organización asignada.", "error")
        return redirect(url_for("inicio.hub"))

    tareas = servicios.sincronizar_tareas_para_ong(organizacion_id)
    formulario = FormularioFinalizarTarea()

    # Métricas para las tarjetas de estado
    total_tareas = len(tareas)
    tareas_en_progreso = sum(1 for t in tareas if t.estado == EstadoTareaEjecucion.en_progreso)
    tareas_pendientes = sum(1 for t in tareas if t.estado == EstadoTareaEjecucion.cierre_pendiente)
    tareas_finalizadas = sum(1 for t in tareas if t.estado == EstadoTareaEjecucion.finalizada)
    estados_finalizacion = {
        emergencia_id: servicios.obtener_estado_finalizacion_emergencia(emergencia_id)
        for emergencia_id in {t.emergencia_id for t in tareas}
    }

    return render_template(
        "ejecucion_cierre/panel_tareas.html",
        tareas=tareas,
        formulario=formulario,
        total_tareas=total_tareas,
        tareas_en_progreso=tareas_en_progreso,
        tareas_pendientes=tareas_pendientes,
        tareas_finalizadas=tareas_finalizadas,
        estados_finalizacion=estados_finalizacion,
    )


@blueprint_ejecucion.post("/tareas/<int:tarea_id>/finalizar")
@login_required
@requiere_permiso(EJECUCION_MARCAR_ACTIVIDAD)
def finalizar_tarea(tarea_id: int):
    """Registra localmente que la ONG terminó una tarea."""
    organizacion_id = getattr(current_user, "organizacion_id", None)
    if not organizacion_id:
        flash("Tu usuario no tiene una organización asignada.", "error")
        return redirect(url_for("inicio.hub"))

    formulario = FormularioFinalizarTarea()
    if not formulario.validate_on_submit():
        for errores in formulario.errors.values():
            for error in errores:
                flash(error, "error")
        return redirect(url_for("ejecucion.listar_tareas"))

    try:
        tarea = servicios.finalizar_tarea_ong(
            tarea_id=tarea_id,
            organizacion_id=organizacion_id,
            usuario_id=current_user.id,
            observaciones=formulario.observaciones.data,
        )
        estado_cierre = servicios.obtener_estado_finalizacion_emergencia(tarea.emergencia_id)
        if estado_cierre["todas_finalizadas"]:
            flash(
                "Todas las ONGs finalizaron sus actividades. El cierre queda listo para "
                "registrarse mediante la integración con Bonita y el Sistema Nacional.",
                "exito",
            )
        else:
            flash(
                "Se registró la finalización de esta actividad. La liberación espera a que "
                "todas las ONGs completen sus tareas.",
                "exito",
            )
    except ErrorDeAplicacion as error:
        flash(error.mensaje, "error")
    except Exception as error:  # noqa: BLE001
        flash(f"Ocurrió un error al procesar el cierre: {error}", "error")

    return redirect(url_for("ejecucion.listar_tareas"))
