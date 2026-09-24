"""Capa web compartida por todas las pantallas.

- `vistas.py`: responder HTML al navegador y JSON al resto, redirects con mensaje y
  `@plantilla_ante_error` para volver a mostrar un formulario con sus errores.
- `formularios.py`: arma un formulario WTForms desde un POST HTML o desde JSON.
- `navegacion.py`: entradas de menu declaradas por cada modulo y filtradas por permiso.
- `paginacion.py`: paginacion de listados en la base.
- `plantillas.py`: filtros y globales de Jinja.
- `inicio.py`: `/` y el panel de inicio (`/inicio`).

Ver docs/contratos/interfaz.md.
"""
