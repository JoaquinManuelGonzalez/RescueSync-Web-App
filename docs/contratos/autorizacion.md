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
`backend/app/core/acceso/permisos.py` y es la fuente de verdad; la base se llena a partir de él
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
| `organizacion_propia:ver` / `:editar` | ✔ | ✔ | ✔ | | |
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
from app.core.acceso.autorizacion import requiere_permiso
from app.core.acceso.permisos import EMERGENCIAS_CREAR


@blueprint_emergencias.post("/emergencias")
@requiere_permiso(EMERGENCIAS_CREAR)
def crear(): ...
```

El decorador va **debajo** del de la ruta. Hay tres:

| Decorador | Cuándo usarlo |
|---|---|
| `@requiere_permiso("recurso:accion")` | Lo habitual. Acepta varios permisos y los exige **todos** |
| `@requiere_autenticacion` | Para lo que cualquier usuario autenticado puede hacer con su propia cuenta |
| `@requiere_rol(NombreRol.AUDITOR)` | Excepcional: para lo que es intrínsecamente de un perfil y no de una acción. Acepta varios roles y exige **alguno** |

### Si la pantalla tiene una tarjeta en el hub

Si la pantalla tiene su tarjeta en el panel de inicio (`hub.html`), el módulo declara
su entrada **con el mismo permiso** junto a sus rutas, y `registrar_modulos()` la registra:

```python
from app.core.interfaz.navegacion import EntradaDeMenu

ENTRADA_DE_MENU = EntradaDeMenu(
    endpoint="emergencias.listar",
    titulo="Emergencias",
    permiso=EMERGENCIAS_LISTAR,
    descripcion="Registro y seguimiento de emergencias",
    icono="carpeta",
)
```

Aparece sola para los perfiles con el permiso y para ningún otro; `hub.html` no se
toca. Lo verifica `test_una_pantalla_nueva_aparece_en_el_menu_solo_declarando_su_entrada`.
Cómo se arma la plantilla de la pantalla está en [`interfaz.md`](./interfaz.md).

### Para agregar un permiso nuevo

1. Agregar la constante en `app/core/acceso/permisos.py`, en la sección de su recurso.
2. Sumarla a `CATALOGO_DE_PERMISOS` con su descripción legible.
3. Sumarla al `frozenset` de cada rol que deba tenerla en `PERMISOS_POR_ROL`.
4. `docker compose exec web flask seed`.

No hay que tocar ninguna ruta ni ningún decorador. El seeder crea el permiso que falta y
**resincroniza la matriz de cada rol**, así que agregar una acción no obliga a rehacer la
base.

### Regla de revisión

Una ruta sin decorador de autorización es un error de revisión, salvo que sea
deliberadamente pública y lo diga en su docstring. Hoy las únicas públicas son
`GET /sesion/ingreso`, `POST /sesion/ingreso`, `GET /health` y `GET /` (que solo redirige al
panel o al ingreso).

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
| Aviso de inactividad | Cada pantalla publica los minutos de sesión en `<body data-minutos-sesion>`; si queda abierta ese tiempo sin navegar, `interfaz.js` la recarga y el servidor muestra el aviso de sesión vencida. Es comodidad: la expiración real es la del servidor |

Todos los formularios llevan el campo oculto del macro `csrf()`, y toda pantalla publica el
token en `<meta name="csrf-token">` para un `fetch()` que lo mande en `X-CSRFToken`. La ruta
provisional `GET /sesion/token-csrf` que existía antes de la interfaz **se eliminó**: los tests
toman el token del `<meta>` (`tests/conftest.py::token_csrf_de`), igual que un navegador.

El endpoint que consume Bonita (integración 4) se eximirá con `@csrf.exempt`: se autentica
con `BONITA_CALLBACK_TOKEN`, no con sesión de usuario.

## 6. Contraseñas y bloqueo

- **Hash con sal**: `scrypt`, siempre a través de `app.core.acceso.seguridad.hashear_contrasena()`.
  Ninguna contraseña se hashea en otro lado ni se guarda en claro en ningún lugar.
- **Política**: toda contraseña nueva (alta, restablecimiento o cambio propio) tiene que
  tener al menos `CONTRASENA_LONGITUD_MINIMA` caracteres (8 por defecto), **una mayúscula,
  un número y un carácter especial** (cualquier cosa que no sea letra, número ni espacio).
  La regla está definida una sola vez, en `app/core/acceso/seguridad.py`, y se valida en el
  formulario (el error dice exactamente qué falta) y otra vez en el servicio, porque el
  seeder y la CLI no pasan por WTForms. `flask crear-administrador` genera claves que ya la
  cumplen. **No se exige al ingresar**: una clave vieja tiene que poder entrar a cambiarse.
- **Distinta de la actual**: en el cambio propio, la contraseña nueva no puede ser la misma
  que la actual. Sin esto, el cambio obligatorio se podría "cumplir" repitiendo la clave inicial.
- **En la interfaz**: los campos de contraseña tienen un botón para mostrarla u ocultarla, y
  los de contraseña nueva muestran los requisitos y los van marcando mientras se escribe.
- **Respuesta uniforme**: email inexistente y contraseña incorrecta devuelven el **mismo**
  mensaje y el mismo código. Además, cuando el email no existe se verifica igual contra un
  hash señuelo, para que los tiempos de respuesta no delaten qué cuentas están dadas de alta.
- **Cuenta desactivada**: si la contraseña es correcta, el aviso lo dice ("Tu cuenta está
  desactivada…", 403). Se informa recién después de validar la contraseña: a quien no la
  conoce le sale el mensaje genérico, así que no sirve para averiguar qué cuentas existen.
- **Bloqueo**: tras `LOGIN_MAX_INTENTOS` fallos consecutivos (5), la cuenta queda
  bloqueada `LOGIN_BLOQUEO_MINUTOS` (1, para poder mostrarlo en una demostración). El bloqueo se levanta solo al vencer, o el
  administrador lo levanta desde `POST /usuarios/<id>/desbloqueo`.
- **Cambio obligatorio**: las cuentas que crea el administrador nacen con
  `debe_cambiar_contrasena`. Mientras la marca esté puesta, lo único que la cuenta puede
  hacer es cambiar la contraseña, cerrar la sesión y ver quién es.

No hay recuperación de contraseña por correo: está fuera del alcance de la épica. Su
reemplazo es `POST /usuarios/<id>/contrasena`, que ejecuta el administrador.

## 7. Respuesta ante acceso no autorizado

A un cliente JSON le sale siempre el envelope único de [`errores.md`](./errores.md). Al
navegador, el mismo error traducido a una pantalla (ver `errores.md` sección 2.1):

| Situación | Código HTTP | `codigo` del envelope | En el navegador |
|---|---|---|---|
| Sin sesión, o sesión vencida por inactividad | 401 | `NO_AUTENTICADO` | Redirect al ingreso con el aviso y `?next=` a la pantalla pedida |
| Con sesión, sin el permiso exigido | 403 | `PERMISO_DENEGADO` | Página 403 con el id de correlación |
| Cuenta bloqueada por intentos fallidos | 403 | `PERMISO_DENEGADO` | La pantalla de ingreso, con el aviso de bloqueo y su duración |
| Cuenta desactivada (con la contraseña correcta) | 403 | `PERMISO_DENEGADO` | La pantalla de ingreso, con el aviso de cuenta desactivada |
| Credenciales incorrectas | 401 | `NO_AUTENTICADO` | La pantalla de ingreso, con el mensaje genérico y el email cargado |
| Con la contraseña pendiente de cambio | 409 | `CONFLICTO_DE_ESTADO` | Redirect a la pantalla de cambio de contraseña |

La distinción entre 401 y 403 importa: el 401 le dice al usuario que inicie sesión, el
403 que no insista con esa cuenta. El `?next=` solo acepta rutas de la propia aplicación
(`app.core.interfaz.vistas.destino_seguro`): un `//otro.sitio` o un `https://…` se descartan y el
ingreso lleva al panel.

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

## 9. La interfaz

Qué ve cada perfil sale de sus permisos, nunca de una lista de roles en una plantilla:

- **Tarjetas del panel de inicio (`hub.html`)**: `entradas_de_menu()`, global de Jinja, devuelve las
  entradas registradas (sección 3) filtradas por `puede(entrada.permiso)`, y el hub
  solo recorre esa lista. Un perfil sin pantallas todavía ve un mensaje que lo indica.
- **Botones y acciones dentro de una pantalla**: `puede()` y `tiene_rol()`, globales de Jinja:

```jinja
{% if puede('usuarios:crear') %}
  <a class="btn btn-primario" href="{{ url_for('usuarios.formulario_de_alta') }}">Nueva cuenta</a>
{% endif %}
```

Es **solo presentación**. La interfaz oculta lo que el servidor ya prohíbe: cada ruta
sigue protegida por su decorador, y borrar ese `{% if %}` no habilita nada. Hay tests que lo
verifican escribiendo la URL a mano y enviando un formulario armado sin permiso
(`tests/test_interfaz_autorizacion.py`).

| Pantalla | Ruta | Quién |
|---|---|---|
| Ingreso | `GET /sesion/ingreso` | Pública |
| Panel de inicio | `GET /inicio` | Cualquier sesión |
| Mi perfil (datos, perfil y permisos) | `GET /sesion/actual` | Cualquier sesión |
| Cambio de contraseña | `GET /sesion/contrasena` | Cualquier sesión |
| Cuentas: listado, alta, detalle, edición | `/usuarios`, `/usuarios/nuevo`, `/usuarios/<id>`, `/usuarios/<id>/edicion` | `usuarios:*` |
| Organizaciones: listado, alta, detalle, edición | `/organizaciones`, `/organizaciones/nueva`, `/organizaciones/<id>`, `/organizaciones/<id>/edicion` | `organizaciones:*` |
| Mi organización: datos, cobertura y miembros; edición de contacto y cobertura | `/organizaciones/mia`, `/organizaciones/mia/edicion` | `organizacion_propia:*` |

`organizacion_propia:*` es un recurso aparte de `organizaciones:*` a propósito: cada miembro ve y
actualiza solo la organización a la que pertenece (el id sale de la sesión, nunca de la URL) y
no puede listar las demás. Nombre, tipo, identificador y estado siguen siendo del administrador.

Dar de baja una organización corta el acceso de todas sus cuentas mientras dure la baja, sin
modificarlas: no pueden ingresar y una sesión ya abierta deja de valer en la siguiente solicitud
(`usuarios_roles.servicios.puede_operar`). Al reactivarla, vuelven a entrar.

Cómo se construye una pantalla (plantillas, componentes y estilos) está en
[`interfaz.md`](./interfaz.md).
