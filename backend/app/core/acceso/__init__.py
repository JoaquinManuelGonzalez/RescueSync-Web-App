"""Identidad, sesion y control de accesos (RBAC).

- `permisos.py`: el vocabulario. Catalogo de roles y permisos y la matriz rol -> permisos.
- `autorizacion.py`: el mecanismo. Decoradores `@requiere_permiso`, `@requiere_autenticacion`,
  `@requiere_rol` y las funciones `puede()` / `tiene_rol()` para las plantillas.
- `sesion.py`: ciclo de vida de la sesion (apertura, cierre, inactividad, cambio obligatorio
  de contrasena).
- `seguridad.py`: hash de contrasenas, politica de contrasenas y formato de email.

Ver docs/contratos/autorizacion.md.
"""
