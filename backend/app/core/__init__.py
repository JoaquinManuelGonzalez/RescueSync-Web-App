"""Modulo transversal: lo que usan todos los modulos de dominio.

No depende de ningun modulo de dominio. Todos los modulos dependen de el.

    core/
    ├── configuracion.py   variables de entorno y validacion fail-fast
    ├── errores.py         envelope unico de error y manejadores globales
    ├── logging.py         logging JSON e id de correlacion
    ├── salud.py           GET /health
    ├── semillas.py        registro de seeders (`flask seed`)
    ├── acceso/            identidad, sesion y control de accesos (RBAC)
    ├── interfaz/          capa web compartida: respuesta HTML/JSON, formularios, menu,
    │                      paginacion, filtros de Jinja y panel de inicio
    └── integraciones/     clientes HTTP hacia Bonita y la API Nacional

Los subpaquetes no reexportan nada en su `__init__`: se importa siempre el modulo concreto
(`from app.core.acceso.autorizacion import requiere_permiso`), asi no se crean ciclos de
importacion entre `errores`, `acceso` e `interfaz`.
"""
