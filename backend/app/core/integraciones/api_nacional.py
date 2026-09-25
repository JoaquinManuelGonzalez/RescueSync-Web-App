"""Cliente de la API Nacional.

Andamiaje: lo implementa la epica de integraciones (Entrega 3) siguiendo la politica de
app/core/integraciones/cliente_http.py.

Puntos de extension ya enganchados
----------------------------------
- `solicitar_verificacion_de_organizacion`: la llama `organizaciones.servicios` cada vez que se
  da de alta una ONG (o una organizacion pasa a ser ONG). Hoy no hace nada. La Entrega 3 la
  implementa consultando al Sistema Nacional y guarda el resultado con
  `app.modulos.organizaciones.servicios.registrar_resultado_de_verificacion()`.

  Recibe datos primitivos y no el modelo a proposito: `core` no importa modulos de dominio (regla
  de dependencias de docs/arquitectura/componentes.md), y asi la llamada se puede diferir a una
  tarea en segundo plano sin arrastrar una sesion de SQLAlchemy.
"""

from __future__ import annotations


def solicitar_verificacion_de_organizacion(
    *,
    organizacion_id: int,
    identificador_nacional: str | None,
    tipo: str,
) -> None:
    """Pide al Sistema Nacional que valide una organizacion. Sin efecto hasta la Entrega 3.

    No debe lanzar excepciones hacia quien la llama: el alta de la organizacion no puede fallar
    porque el servicio externo no responda. La organizacion queda `sin_verificar` hasta que
    llegue el resultado.
    """
    return None
