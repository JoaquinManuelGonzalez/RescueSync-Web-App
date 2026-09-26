"""Cliente de la API Nacional.

Andamiaje: lo implementa la epica de integraciones (Entrega 3) siguiendo la politica de
app/core/integraciones/cliente_http.py.

Las organizaciones no se verifican desde aca: se cargan en RescueSync despues de que el Sistema
Nacional las verifico, y nacen `verificada`. Si la integracion llegara a informar otro resultado,
lo guarda con `app.modulos.organizaciones.servicios.registrar_resultado_de_verificacion()`.

Las funciones de este modulo reciben datos primitivos y no modelos a proposito: `core` no importa
modulos de dominio (regla de dependencias de docs/arquitectura/componentes.md), y asi una llamada
se puede diferir a una tarea en segundo plano sin arrastrar una sesion de SQLAlchemy.
"""

from __future__ import annotations
