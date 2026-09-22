# Contrato de autorización

Este documento es la fuente de verdad sobre identidad, sesión y control de accesos en
RescueSync. La decisión de fondo y sus alternativas están en
[ADR-009](../adr/ADR-009-autenticacion-y-rbac.md); acá está **cómo se usa**.

Si vas a escribir una pantalla nueva, lo único que necesitás de este documento es la
sección 3.

## 1. Los perfiles

| Rol | Organización que exige | Qué hace en el proceso |
|---|---|---|
| `operador_municipal` | Un municipio | Registra la emergencia y selecciona las ofertas a adjudicar |
| `coordinador_regional` | El centro coordinador regional | Revisa la emergencia, arma los lotes de necesidad, publica la convocatoria, registra la adjudicación y monitorea la ejecución |
| `representante_ong` | Una ONG | Gestiona el inventario, presenta y edita ofertas, marca sus actividades como finalizadas |
| `auditor` | Ninguna | Solo lectura sobre todo el proceso, más el dashboard de indicadores |
| `administrador` | Ninguna | Da de alta cuentas y organizaciones. **No participa del proceso** |

Los cuatro primeros son los que exige el punto 2 del enunciado. `administrador` es un
perfil operativo, no un actor del proceso: no tiene ni un solo permiso de `emergencias`,
`lotes`, `convocatorias`, `ofertas`, `adjudicaciones` ni `ejecucion`.

La coherencia entre el rol y el tipo de organización la hace cumplir
`usuarios_roles.servicios.verificar_coherencia_rol_organizacion()`. No es una restricción
de base porque cruza tres tablas.

## 2. Los permisos

Formato: **`recurso:accion`**, en minúsculas y sin tildes. El catálogo completo vive en
`backend/app/core/permisos.py` y es la fuente de verdad; la base se llena a partir de él
con `flask seed`.

| Recurso | Acciones |
|---|---|
| `usuarios` | `listar`, `crear`, `editar`, `cambiar_estado`, `restablecer_contrasena` |
| `organizaciones` | `listar`, `crear`, `editar`, `cambiar_estado` |
| `emergencias` | `crear`, `listar`, `ver`, `editar` |
| `lotes` | `crear`, `editar`, `listar` |
| `convocatorias` | `crear`, `publicar`, `cerrar`, `listar` |
| `ofertas` | `crear`, `editar`, `retirar`, `listar` |
| `inventario` | `ver`, `editar` |
| `adjudicaciones` | `seleccionar`, `registrar`, `listar` |
| `ejecucion` | `marcar_actividad`, `informar_finalizacion`, `monitorear` |
| `indicadores` | `ver`, `exportar` |

El catálogo cubre todo el proceso BPMN y no solo la épica de identidad, para que las
épicas siguientes declaren su permiso y no tengan que volver a tocar el RBAC.

### Matriz rol → permisos

| | operador_municipal | coordinador_regional | representante_ong | auditor | administrador |
|---|---|---|---|---|---|
| `usuarios:*` | | | | | ✔ |
| `organizaciones:*` | | | | | ✔ |
| `emergencias:crear` | ✔ | | | | |
| `emergencias:editar` | ✔ | | | | |
| `emergencias:listar` / `:ver` | ✔ | ✔ | | ✔ | |
| `lotes:crear` / `:editar` | | ✔ | | | |
| `lotes:listar` | ✔ | ✔ | | ✔ | |
| `convocatorias:crear` / `:publicar` / `:cerrar` | | ✔ | | | |
| `convocatorias:listar` | ✔ | ✔ | ✔ | ✔ | |
| `ofertas:crear` / `:editar` / `:retirar` | | | ✔ | | |
| `ofertas:listar` | ✔ | ✔ | ✔ | ✔ | |
| `inventario:ver` | | | ✔ | ✔ | |
| `inventario:editar` | | | ✔ | | |
| `adjudicaciones:seleccionar` | ✔ | | | | |
| `adjudicaciones:registrar` | | ✔ | | | |
| `adjudicaciones:listar` | ✔ | ✔ | | ✔ | |
| `ejecucion:marcar_actividad` / `:informar_finalizacion` | | | ✔ | | |
| `ejecucion:monitorear` | | ✔ | | | |
| `indicadores:ver` / `:exportar` | | | | ✔ | |

## 3. Cómo se protege una pantalla nueva

Se declara el permiso. Eso es todo:

```python
from app.core.autorizacion import requiere_permiso
from app.core.permisos import EMERGENCIAS_CREAR

@blueprint_emergencias.post("/emergencias")
@requiere_permiso(EMERGENCIAS_CREAR)
def crear():
    ...
```

El decorador va **debajo** del de la ruta. Hay tres:

| Decorador | Cuándo usarlo |
|---|---|
| `@requiere_permiso("recurso:accion")` | Lo habitual. Acepta varios permisos y los exige **todos** |
| `@requiere_autenticacion` | Para lo que cualquier usuario autenticado puede hacer con su propia cuenta |
| `@requiere_rol(NombreRol.AUDITOR)` | Excepcional: para lo que es intrínsecamente de un perfil y no de una acción. Acepta varios roles y exige **alguno** |

### Para agregar un permiso nuevo

1. Agregar la constante en `app/core/permisos.py`, en la sección de su recurso.
2. Sumarla a `CATALOGO_DE_PERMISOS` con su descripción legible.
3. Sumarla al `frozenset` de cada rol que deba tenerla en `PERMISOS_POR_ROL`.
4. `docker compose exec web flask seed`.

No hay que tocar ninguna ruta ni ningún decorador. El seeder crea el permiso que falta y
**resincroniza la matriz de cada rol**, así que agregar una acción no obliga a rehacer la
base.

### Regla de revisión

Una ruta sin decorador de autorización es un error de revisión, salvo que sea
deliberadamente pública y lo diga en su docstring. Hoy las únicas públicas son
`POST /sesion/ingreso`, `GET /sesion/token-csrf`, `GET /health` y `GET /`.

## 4. Alcance por organización

Los decoradores contestan **qué acción** puede ejecutar un rol. No contestan **sobre qué
filas**. Un operador municipal tiene `emergencias:editar`, pero solo sobre las
emergencias de su propio municipio.

Eso se verifica en la capa de servicios, antes de devolver o modificar cualquier fila que
tenga dueño:

```python
from app.modulos.usuarios_roles.servicios import verificar_alcance_de_organizacion

def editar_emergencia(usuario, emergencia_id, ...):
    emergencia = _obtener(emergencia_id)
    verificar_alcance_de_organizacion(usuario, emergencia.municipio_id)
    ...
```

`coordinador_regional`, `auditor` y `administrador` no tienen límite de organización: el
coordinador porque orquesta el proceso completo, el auditor porque lo audita, y el
administrador porque da de alta cuentas de cualquiera.

Olvidarse de esta verificación es el otro error clásico del RBAC, además de verificar
solo en el front: deja a cada municipio viendo las emergencias de los demás aunque la
matriz de permisos esté impecable.

## 5. Sesión

| Aspecto | Cómo está resuelto |
|---|---|
| Mecanismo | Cookie de sesión firmada de Flask + Flask-Login. No hay JWT en la aplicación web (el JWT del enunciado es el de la API Nacional) |
| Expiración | Por **inactividad**, a los `SESION_MINUTOS_INACTIVIDAD` minutos (30 por defecto) |
| Dónde se verifica | En el servidor. Flask usa `PERMANENT_SESSION_LIFETIME` como `max_age` al deserializar la cookie: una cookie vencida se rechaza aunque el cliente la siga mandando |
| Deslizante | Sí: `SESSION_REFRESH_EACH_REQUEST` la reemite en cada respuesta |
| Cookie | `HttpOnly`, `SameSite=Lax`, y `Secure` en todo entorno que no sea `local` |
| "Recordarme" | Deshabilitado: sobrevive al cierre del navegador y volvería decorativa la expiración |
| Rotación | Al iniciar y al cerrar sesión se descarta todo el contenido previo de la sesión |
| CSRF | `CSRFProtect` en toda la aplicación. El token viaja en el campo oculto del formulario o en la cabecera `X-CSRFToken` |

Mientras no existan las plantillas, `GET /sesion/token-csrf` entrega un token para poder
ejercitar los POST con `curl` y desde los tests. **Es provisional**: cuando llegue la
interfaz, el token viaja en el campo oculto que renderiza `{{ csrf_token() }}` y esa ruta
se elimina.

El endpoint que consume Bonita (integración 4) se eximirá con `@csrf.exempt`: se autentica
con `BONITA_CALLBACK_TOKEN`, no con sesión de usuario.

## 6. Contraseñas y bloqueo

- **Hash con sal**: `scrypt`, siempre a través de `app.core.seguridad.hashear_contrasena()`.
  Ninguna contraseña se hashea en otro lado ni se guarda en claro en ningún lugar.
- **Longitud mínima**: `CONTRASENA_LONGITUD_MINIMA` (10 por defecto). Se valida en el
  formulario y otra vez en el servicio, porque el seeder y la CLI no pasan por WTForms.
- **Respuesta uniforme**: email inexistente, contraseña incorrecta y cuenta desactivada
  devuelven el **mismo** mensaje y el mismo código. Además, cuando el email no existe se
  verifica igual contra un hash señuelo, para que los tiempos de respuesta no delaten qué
  cuentas están dadas de alta.
- **Bloqueo**: tras `LOGIN_MAX_INTENTOS` fallos consecutivos (5), la cuenta queda
  bloqueada `LOGIN_BLOQUEO_MINUTOS` (15). El bloqueo se levanta solo al vencer, o el
  administrador lo levanta desde `POST /usuarios/<id>/desbloqueo`.
- **Cambio obligatorio**: las cuentas que crea el administrador nacen con
  `debe_cambiar_contrasena`. Mientras la marca esté puesta, lo único que la cuenta puede
  hacer es cambiar la contraseña, cerrar la sesión y ver quién es.

No hay recuperación de contraseña por correo: está fuera del alcance de la épica. Su
reemplazo es `POST /usuarios/<id>/contrasena`, que ejecuta el administrador.

## 7. Respuesta ante acceso no autorizado

Sale siempre con el envelope único de [`errores.md`](./errores.md), nunca con un redirect:

| Situación | Código HTTP | `codigo` del envelope |
|---|---|---|
| Sin sesión, o sesión vencida por inactividad | 401 | `NO_AUTENTICADO` |
| Con sesión, sin el permiso exigido | 403 | `PERMISO_DENEGADO` |
| Cuenta bloqueada por intentos fallidos | 403 | `PERMISO_DENEGADO` |
| Con la contraseña pendiente de cambio | 409 | `CONFLICTO_DE_ESTADO` |

La distinción entre 401 y 403 importa: el 401 le dice al usuario que inicie sesión, el
403 que no insista con esa cuenta.

## 8. Eventos de log

Con el formato de [`logging.md`](./logging.md), una línea JSON por evento. **Nunca llevan
el email ni la contraseña**: el identificador interno alcanza para reconstruir quién fue.

| Evento | Nivel | Cuándo |
|---|---|---|
| `login_exitoso` | INFO | Ingreso correcto |
| `login_fallido` | WARN | Con el campo `motivo`: `email_inexistente`, `contrasena_incorrecta`, `cuenta_bloqueada` o `cuenta_inactiva` |
| `cuenta_bloqueada` | WARN | Se agotaron los intentos |
| `cuenta_desbloqueada` | INFO | El administrador levantó el bloqueo |
| `acceso_denegado` | WARN | Con `motivo` (`sin_sesion`, `sin_permiso`, `sin_rol`) y `exigido` (el permiso o rol que faltaba) |
| `sesion_expirada` | INFO | Venció por inactividad |
| `usuario_creado`, `usuario_cambio_de_estado` | INFO | Alta y baja lógica de cuentas |
| `contrasena_cambiada`, `contrasena_restablecida` | INFO | Cambio propio y restablecimiento por el administrador |

Esto **no** es la auditoría avanzada que la épica deja fuera de alcance: es el contrato de
logging ya vigente, aplicado a los eventos de acceso. No hay tabla de auditoría.

## 9. La interfaz, cuando exista

`puede()` y `tiene_rol()` están registradas como globales de Jinja:

```jinja
{% if puede('emergencias:crear') %}
  <a href="{{ url_for('emergencias.crear') }}">Nueva emergencia</a>
{% endif %}
```

Es **solo presentación**. La interfaz oculta lo que el servidor ya prohíbe: cada ruta
sigue protegida por su decorador, y borrar ese `{% if %}` no habilita nada.

`GET /sesion/actual` devuelve el usuario, su organización, sus roles y sus permisos
efectivos: con eso la plantilla arma el menú sin repetir una lista de roles.
