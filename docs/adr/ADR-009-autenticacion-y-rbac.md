# ADR-009: Autenticación por sesión y control de accesos basado en roles

- Estado: Propuesto
- Fecha: 2026-09-21
- Reemplaza a: —
- Reemplazado por: —

## Contexto

El punto 2 del enunciado exige que la aplicación web "diferencie estrictamente al
menos 4 perfiles con interfaces y permisos propios": Operador Municipal, Centro
Coordinador Regional, Representante de ONG y Auditor/Directivo. Hasta la HU-54-55 el
repositorio tenía el modelo de datos (`usuarios`, `roles`, `permisos` y sus tablas
asociativas) pero nadie podía autenticarse: el `user_loader` de Flask-Login era un
stub que devolvía `None`, no había rutas de sesión ni verificación de permisos.

Hay cuatro fuerzas en juego.

**Primera: dónde se verifican los permisos.** Verificarlos solo en la interfaz es el
error clásico que cualquier evaluador detecta, y el propio enunciado lo señala. Un
menú que oculta un botón no impide que alguien escriba la URL a mano.

**Segunda: el momento.** Identidad y permisos son transversales a todas las pantallas
que faltan (alta de emergencia, generación de lotes, carga de ofertas, adjudicación,
cierre). Si cada pantalla resuelve su propia autorización, el criterio se fragmenta
entre cinco personas trabajando en paralelo y deja de ser auditable.

**Tercera: el enunciado menciona JWT.** Lo menciona para el **Sistema Nacional**
(punto 3, Entrega 3), que es un componente distinto, desplegado aparte y consumido por
HTTP. No dice nada sobre cómo la aplicación web local autentica a sus usuarios.
Confundir las dos cosas y montar JWT propio en la app web es un malentendido fácil y
caro.

**Cuarta: quién da de alta las cuentas.** No hay forma, dentro del sistema, de
verificar que quien se registra pertenece de verdad al municipio o a la ONG que dice
representar, ni de impedir que se autoasigne el perfil de Centro Coordinador Regional.

## Decisión

Se decide: **autenticación por sesión de servidor con Flask-Login sobre la cookie
firmada de Flask, y autorización por permisos granulares declarados en cada ruta**, con
las cuentas dadas de alta exclusivamente por un rol `administrador`.

El razonamiento, punto por punto:

**Sesión y no JWT propio.** La aplicación web es un monolito renderizado en el servidor
(ADR-001 y ADR-005): el navegador manda formularios HTML y recibe HTML. En ese escenario
la cookie de sesión firmada es el mecanismo nativo, ya viene resuelta por Flask y
Flask-Login, ambos ya declarados en `pyproject.toml`, y permite revocar un acceso en el
acto desactivando la cuenta. Un JWT propio agregaría emisión, expiración, rotación y
revocación —que es justamente lo que un JWT no resuelve bien— sin ningún beneficio: no
hay cliente JavaScript separado ni otro servicio que tenga que validar nuestros tokens.
El JWT del enunciado corresponde a la API Nacional, que es un componente aparte.

**Permisos granulares y no un campo `rol` con opciones.** El decorador de cada ruta
declara un permiso (`emergencias:crear`), no un rol. El vínculo rol → permiso vive en
una tabla y se declara en un catálogo único, `app/core/acceso/permisos.py`. Así, agregar una
pantalla nueva no requiere código de autorización propio: solo declarar el permiso. Y
cambiar qué puede hacer un perfil es editar la matriz y volver a correr `flask seed`, sin
tocar una sola ruta. Es lo que la épica pide confirmar, y hay un test que lo verifica de
forma literal (`test_una_pantalla_nueva_solo_declara_su_permiso`).

**El catálogo vive en `core` y no en `usuarios_roles`.** Lo necesitan todos los módulos,
incluido `organizaciones`, que está *antes* que `usuarios_roles` en la cadena de
dependencias (sin una organización cargada no se puede crear un operador municipal).
Declarar un permiso desde `organizaciones` habría sido una dependencia hacia adelante,
prohibida por la regla 3 de `docs/arquitectura/componentes.md`. El mecanismo que hace
cumplir los permisos (`core/acceso/autorizacion.py`) queda separado del vocabulario
(`core/acceso/permisos.py`): el decorador recibe strings y no conoce el catálogo.

**Registro administrado y no autoservicio.** Todas las cuentas las crea un usuario con
rol `administrador` desde `/usuarios`. Es la lectura estricta del mínimo privilegio que
la propia épica exige: un formulario público que ofrezca los cuatro perfiles permite que
cualquiera se declare Centro Coordinador Regional.

**Un quinto rol, `administrador`, fuera de los cuatro del enunciado.** No participa del
proceso BPMN: sus permisos son exclusivamente `usuarios:*` y `organizaciones:*`, y no
tiene ninguno de `emergencias`, `lotes`, `convocatorias`, `ofertas`, `adjudicaciones` ni
`ejecucion`. El mínimo privilegio se le aplica también a él. Los cuatro perfiles que
evalúa la cátedra siguen siendo exactamente los del enunciado; `administrador` es una
función operativa, no un actor del proceso.

### Versión fijada

| Tecnología | Versión | Archivo del repositorio donde se fija |
|---|---|---|
| `Flask-Login` | `0.6.3` | `backend/pyproject.toml` |
| `Flask-WTF` (protección CSRF) | `1.3.0` | `backend/pyproject.toml` |
| `Werkzeug` (hash `scrypt`) | transitiva de `Flask==3.1.3` | `backend/uv.lock` |

Esta decisión no agrega ninguna dependencia: las tres ya estaban declaradas por los
ADR-002 y ADR-007, y esta épica se limita a usarlas.

### Alternativas consideradas

| Alternativa | A favor | En contra | Motivo del descarte |
|---|---|---|---|
| JWT propio en la aplicación web | Consistente con la API Nacional, sin estado de sesión en el servidor | Hay que resolver emisión, expiración, rotación y revocación a mano; revocar un token antes de su vencimiento exige una lista de revocación, es decir, estado de servidor, que es justo lo que el JWT venía a evitar; guardarlo en el navegador obliga a elegir entre `localStorage` (expuesto a XSS) y una cookie, que es la sesión de nuevo | No hay cliente JavaScript separado ni otro servicio que valide nuestros tokens. El JWT del enunciado es el de la API Nacional, otro componente |
| Campo `rol` en `usuarios` con opciones fijas, y verificación por rol en cada ruta | Más simple de leer, una sola columna, sin tablas asociativas | Cada pantalla nueva tiene que enumerar los roles que la pueden usar, y cambiar los permisos de un perfil obliga a revisar todas las rutas; un usuario no puede tener dos perfiles | Contradice la hipótesis de beneficio de la épica: el objetivo es que agregar una pantalla no requiera tocar la autorización |
| Autorregistro con el rol elegido en el formulario | Cumple literalmente el "registro de usuarios" del alcance, más rápido de demostrar | Cualquiera puede autoasignarse el perfil de Centro Coordinador Regional; no hay forma de verificar la pertenencia a un municipio o una ONG | Contradice el mínimo privilegio que la misma épica define como criterio |
| Sin quinto rol: cuentas privilegiadas solo por CLI y semillas | No agrega perfiles fuera del enunciado | El alta de cuentas queda fuera de la aplicación web, y toda corrección durante una demostración exige entrar al contenedor | Se prefirió el panel; `flask crear-administrador` queda igual, pero solo para el arranque en frío |

## Consecuencias

### Positivas

- La verificación de permisos vive del lado del servidor por construcción: cada ruta
  levanta `NoAutenticado` o `PermisoDenegado`, y la respuesta sale con el envelope único
  del contrato de errores (ADR-006), con su código y su id de correlación.
- Agregar una pantalla cuesta una línea de decorador. Cambiar qué puede hacer un perfil
  cuesta editar la matriz y volver a correr `flask seed`.
- La interfaz, cuando exista, solo tiene que **ocultar** lo que el servidor ya
  **prohíbe**: `puede()` y `tiene_rol()` están registradas como globales de Jinja, y
  borrar un `{% if %}` de una plantilla no habilita nada.
- Desactivar una cuenta la deja afuera en la siguiente solicitud, sin esperar a que
  venza ningún token.

### Negativas

- La sesión vive en una cookie firmada, no cifrada: su contenido es legible por el
  cliente aunque no sea alterable. Por eso en la sesión no se guarda nada más que el id
  del usuario y la marca de actividad.
- Escalar a varias instancias del backend exige que todas compartan `SECRET_KEY`. Hoy el
  despliegue es un único contenedor (ADR-005), así que no es un problema; si alguna vez
  hay más de uno, hay que revisarlo.
- El catálogo de permisos y la base pueden desincronizarse si alguien agrega un permiso y
  no vuelve a correr `flask seed`. Se mitiga con un test que compara la matriz declarada
  contra lo que quedó en la base.
- `administrador` es un perfil más del que hay que hablar en la defensa, porque no está
  en el enunciado.

### Qué nos obliga a hacer

- **Toda ruta nueva declara su permiso** con `@requiere_permiso(...)`. Una ruta sin
  decorador es un error de revisión, salvo que sea deliberadamente pública y lo diga en
  su docstring.
- **Todo permiso nuevo se agrega a `app/core/acceso/permisos.py`**, con su descripción y su
  lugar en la matriz de roles. No se escriben códigos de permiso sueltos en las rutas.
- **El alcance por organización se verifica en la capa de servicios**, con
  `usuarios_roles.servicios.verificar_alcance_de_organizacion()`. El decorador decide qué
  acción puede ejecutar un rol; no decide sobre qué filas.
- **Ninguna contraseña se hashea fuera de `app/core/acceso/seguridad.py`**, y ninguna se
  registra en los logs.
- **El endpoint que consume Bonita (integración 4) se exime de CSRF** con
  `@csrf.exempt`: se autentica con `BONITA_CALLBACK_TOKEN` y no con sesión de usuario.

---

Recordatorio de uso: una vez que un ADR pasa a `Aceptado` es inmutable.
Si la decisión cambia más adelante, no se edita este documento: se escribe
un ADR nuevo y en este solo se actualiza el campo `Estado` (a
`Reemplazado por ADR-XXX`) y el campo `Reemplazado por`. El detalle completo
del procedimiento está en `docs/adr/README.md`.
