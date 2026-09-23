# Guía de contribución — RescueSync

Esta guía define cómo se escribe código, cómo se nombran ramas y commits, y cómo se revisan
y mergean los cambios en este repositorio. Es de lectura obligatoria antes del primer commit.
Su objetivo es que cinco personas trabajando en paralelo sobre módulos distintos no choquen
por supuestos distintos.

## Índice

1. Idioma del código
2. Nomenclatura por capa
3. Estructura de carpetas
4. Entorno local, formato y verificación (uv + Ruff)
5. Nomenclatura de ramas
6. Revisión obligatoria antes del merge
7. Commits y vínculo con el backlog
8. Flujo de trabajo de punta a punta
9. Guía de revisión

## 1. Idioma del código

Todo el código de RescueSync se escribe en español: nombres de paquetes, módulos, clases,
funciones, variables, tablas, columnas, rutas, mensajes de commit y comentarios.

Los identificadores (nombres de variables, funciones, clases, archivos, tablas, columnas,
ramas) se escriben **sin tildes ni `ñ`**, porque no todos los motores/herramientas los
toleran de forma consistente (por ejemplo `adjudicacion`, `anio`, en vez de `adjudicación`,
`año`). La ortografía completa (con tildes y `ñ`) se reserva para todo lo que no sea un
identificador: comentarios, docstrings, documentación (`.md`), mensajes de log legibles por
humanos y textos de la interfaz (labels, mensajes de error al usuario, etc.).


## 2. Nomenclatura por capa

| Elemento | Convención | Ejemplo |
|---|---|---|
| Paquetes / módulos | `snake_case` | `lotes_convocatorias` |
| Clases y modelos | `PascalCase` singular | `OfertaDeAyuda`, `LoteDeNecesidad` |
| Funciones y métodos | `snake_case`, empiezan con verbo | `registrar_oferta`, `obtener_emergencia_por_id` |
| Variables | `snake_case` | `ventana_de_carga` |
| Constantes | `MAYUSCULAS_CON_GUION_BAJO` | `ESTADOS_DE_OFERTA` |
| Blueprints / endpoints | `modulo.accion` | `ofertas.crear` |
| Rutas URL | minúsculas con guion medio | `/ofertas/nueva`, `/lotes-de-necesidad` |
| Plantillas Jinja | `modulo/accion.html` | `ofertas/crear.html` |
| Tablas | `snake_case` plural | `ofertas_de_ayuda` |
| Columnas | `snake_case` singular | `nivel_de_gravedad` |
| Clave primaria | siempre `id` | `id` |
| Clave foránea | `<tabla_en_singular>_id` | `emergencia_id` |
| Booleanos | prefijo `es_` / `tiene_` | `es_consorcio`, `tiene_adjudicacion` |
| Fechas | prefijo `fecha_` | `fecha_creacion`, `fecha_cierre` |
| Índices y restricciones | `ix_`/`uq_`/`fk_`/`ck_` + tabla + columnas | `ix_ofertas_de_ayuda_convocatoria_id` |
| Tests | `test_<unidad>.py` / `test_<caso>_<resultado>` | `test_registrar_oferta_fuera_de_ventana_falla` |


## 3. Estructura de carpetas

El repositorio se divide en dos carpetas: `backend/` es 100 % Python y `frontend/`
es 100 % presentación (ver [ADR-007](docs/adr/ADR-007-estructura-esqueleto-ejecutable.md)).

```
backend/
  pyproject.toml     dependencias (uv) y configuracion de Ruff
  uv.lock            arbol de dependencias fijado, se versiona
  migrations/        migraciones de Alembic (Flask-Migrate)
  tests/
  app/
    __init__.py      app factory: create_app()
    wsgi.py          objeto que levantan flask y gunicorn
    extensiones.py   db, migrate, login_manager
    cli.py           comandos `flask <comando>` (por ejemplo, seed)
    core/            configuracion, errores, logging, salud, semillas
      acceso/          identidad y RBAC: autorizacion, permisos, seguridad, sesion
      interfaz/        capa web compartida: vistas, formularios, navegacion, paginacion,
                        plantillas, inicio
      integraciones/   {bonita,api_nacional}  -> clientes HTTP compartidos
    modulos/
      usuarios_roles/    alta y gestion de usuarios, roles y permisos (RBAC)
      emergencias/       alta y ciclo de vida de una emergencia
      lotes_convocatorias/  lotes de necesidad y convocatorias asociadas a una emergencia
      ofertas/           carga y listado de ofertas de ayuda de las ONG
      adjudicacion/       logica de adjudicacion de ofertas a lotes/convocatorias
      ejecucion_cierre/   seguimiento de ejecucion y cierre del proyecto
      indicadores/        dashboard de metricas y reportes (solo lectura)
      <cada modulo>/
        rutas.py          blueprint Flask: define los endpoints HTTP
        servicios.py       logica de negocio del modulo (unico punto de entrada para otros modulos)
        modelos.py         modelos SQLAlchemy y consultas propias del modulo
        formularios.py     formularios WTForms (validacion de entrada)

frontend/
  plantillas/
    base.html        layout base
    parciales/       parciales compartidos (_nav.html, etc.)
    <modulo>/        plantillas del modulo, una por accion (modulo/accion.html)
  estaticos/
    css/app.css      CSS compilado por Tailwind. NO se versiona: lo genera el contenedor
    img/
  src/input.css      hoja de entrada de Tailwind (configuracion CSS-first, sin config.js)
  observar.sh        bucle que recompila el CSS cuando cambia una plantilla
  package.json       dependencias de Node, con version exacta
  Dockerfile         contenedor que compila Tailwind
```

Cada carpeta de `modulos/` reproduce siempre el mismo esqueleto interno
(`rutas.py`, `servicios.py`, `modelos.py`, `formularios.py`), lo que hace predecible dónde
buscar o agregar algo.

**Las plantillas no van dentro del módulo.** Un módulo es código Python; sus vistas viven en
`frontend/plantillas/<modulo>/`. La convención de nombres no cambia: una plantilla se sigue
llamando `modulo/accion.html` y se sigue invocando con
`render_template("emergencias/alta.html")`. Un archivo `.html` dentro de `backend/` es un
error de revisión.

### ¿Dónde escribo una funcionalidad nueva?

- ¿Es una operación de negocio dentro de un módulo existente (por ejemplo, una nueva regla de
  adjudicación)? Va en `servicios.py` del módulo correspondiente, con su endpoint en `rutas.py`
  y, si aplica, su plantilla en `frontend/plantillas/<modulo>/`.
- ¿Es una entidad de dominio nueva (una tabla nueva)? El modelo va en `modelos.py` del módulo
  dueño de esa entidad, nunca en otro módulo.
- ¿Necesito datos de otro módulo? Se piden a través de la capa `servicios` de ese módulo, nunca
  importando sus modelos ni haciendo consultas directas a sus tablas.
- ¿Es transversal a toda la aplicación (configuración, manejo de errores, logging, seguridad,
  o un cliente HTTP hacia Bonita o la API Nacional)? Va en `core/`.
- ¿Es una métrica, un gráfico o un reporte del dashboard? Va en `modulos/indicadores/`. El
  dashboard es un módulo más de esta aplicación, no un proyecto aparte: lee a través de los
  servicios de los otros módulos y nunca consulta sus tablas por su cuenta.
- ¿Necesita llamar a Bonita o a la API Nacional? Siempre a través de los clientes de
  `core/integraciones/`, nunca con una llamada HTTP directa desde el módulo.

## 4. Entorno local, formato y verificación (uv + Ruff)

### Entorno local con uv

Las dependencias de Python se gestionan con **uv 0.12.13**
([ADR-008](docs/adr/ADR-008-gestion-dependencias-uv.md)): se declaran con versión exacta en
`backend/pyproject.toml` y el árbol transitivo completo queda fijado en `backend/uv.lock`, que
se versiona. uv tiene que estar instalado en tu máquina; el README explica cómo, en
[Requisitos previos](README.md#requisitos-previos).

Después de clonar, y cada vez que alguien cambie las dependencias en `main`:

```bash
cd backend
uv sync --locked
```

Eso crea `backend/.venv` con las mismas versiones que instala la imagen de Docker, incluidas
Ruff y pytest. `--locked` hace que falle si el lock no está sincronizado con `pyproject.toml`,
en lugar de regenerarlo por su cuenta. `backend/.venv` está en `.gitignore` y no se commitea.

Reglas al tocar dependencias:

- Se agregan con `uv add "paquete==1.2.3"` desde `backend/`, **siempre con versión exacta**,
  nunca con un rango.
- Las que solo sirven para desarrollar (linters, tests) van con `uv add --dev`, para que no
  entren en la imagen de producción.
- `uv.lock` **no se edita a mano**. Ante un conflicto de merge se regenera con `uv lock`.
- `pyproject.toml` y `uv.lock` se commitean **juntos**, en el mismo commit, y la dependencia
  nueva se agrega a la tabla de stack tecnológico del README en el mismo PR.
- Después de cambiar dependencias hay que reconstruir la imagen:
  `docker compose build web && docker compose up -d web`.

### Formato y verificación (Ruff)

RescueSync usa **Ruff 0.16.7** como linter y formateador único. Los comandos se corren desde
`backend/`, con `uv run`, que usa el Ruff del entorno del proyecto y no uno instalado suelto.

Formatear el código antes de commitear:

```bash
uv run ruff format .
```

Verificar sin modificar archivos (se usa antes de abrir un PR y en cualquier revisión):

```bash
uv run ruff format --check .
uv run ruff check .
```

Cuando `ruff check` encuentra un problema, la salida tiene el formato
`archivo:línea:columna: código mensaje`. Por ejemplo:

```
app/modulos/ofertas/servicios.py:42:1: F401 [*] `datetime` importado pero no usado
app/modulos/ofertas/rutas.py:15:80: E501 la linea supera los 100 caracteres
Found 2 errors.
[*] 1 error corregible automaticamente con `ruff check --fix`.
```

La configuración vive en `backend/pyproject.toml` y es esta:

```toml
[tool.ruff]
line-length = 100
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B"]
```

A eso se le sumaron dos excepciones acotadas, cada una con su motivo comentado en el archivo:

- `migrations/*` ignora `F401`, `E501`, `N999`, `I001` y `UP035`, porque esos archivos los
  genera Alembic con su propia plantilla y su nombre empieza con un número.
- `app/core/errores.py` ignora `N818`, que exige que las excepciones terminen en `Error`. El
  código del proyecto está en español y la palabra va adelante: `ErrorDeAplicacion`, no
  `AplicacionError`.

Los mismos comandos se pueden correr dentro del contenedor, si preferís no usar el entorno
local o si querés verificar exactamente lo que ve la imagen. Es equivalente: las dos rutas
instalan el mismo `uv.lock`.

```bash
docker compose exec web ruff format .
docker compose exec web ruff format --check .
docker compose exec web ruff check .
```

## 5. Nomenclatura de ramas

Patrón: `<tipo>/HU-<id>-<descripcion-en-kebab>`

Tipos permitidos: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

Ejemplo: `feat/HU-03-alta-emergencia`

Reglas:
- La rama nace siempre de `main` actualizada (`git pull origin main` antes de crearla).
- Es corta: vive lo que dura la HU, se borra apenas se mergea el PR.
- `main` está reservada a código entregable: **no se hace push directo**, todo cambio entra
  por Pull Request.

| Ejemplo | Válido / Inválido | Motivo |
|---|---|---|
| `feat/HU-03-alta-emergencia` | Válido | tipo correcto, HU identificada, descripción en kebab-case |
| `fix/HU-12-error-calculo-ventana` | Válido | corrige un defecto de la HU-12 |
| `docs/HU-01-contributing` | Válido | cambio documental referenciado a su HU |
| `nueva-funcionalidad` | Inválido | sin tipo ni número de HU |
| `feat/emergencias` | Inválido | falta el identificador de HU |
| `feat/HU-03_Alta_Emergencia` | Inválido | usa `_` y mayúsculas en vez de kebab-case |
| `joaquin/pruebas` | Inválido | nombre personal, no describe la HU ni el tipo de cambio |

## 6. Revisión obligatoria antes del merge

Reglas del equipo:
- Mínimo **1 aprobación** de otro integrante (no vale la propia).
- Prohibido auto-aprobarse el PR.
- El merge se hace siempre por **squash** (un commit limpio por PR en el historial de `main`).
- La rama debe estar al día con `main` antes de mergear (rebase o merge de `main` en la rama
  si quedó desactualizada).


## 7. Commits y vínculo con el backlog

Se usa **Conventional Commits en español**, incluyendo siempre el identificador de la HU que
el commit resuelve.

Formato:

```
<tipo>(<alcance>): <descripcion en minuscula> (HU-XX)
```

## 8. Flujo de trabajo de punta a punta

```bash
# 1. Actualizar main y crear la rama de la HU
git checkout main
git pull origin main
git checkout -b feat/HU-07-formulario-ofertas

# 2. Sincronizar el entorno local por si cambiaron las dependencias en main
cd backend && uv sync --locked && cd ..

# 3. Trabajar y commitear con Conventional Commits
git add backend/app/modulos/ofertas/
git commit -m "feat(ofertas): agrega formulario de carga de ofertas (HU-07)"

# 4. Verificar formato, linter y tests antes de subir
cd backend
uv run ruff format --check .
uv run ruff check .
uv run pytest
cd ..

# 5. Subir la rama y abrir el Pull Request
git push -u origin feat/HU-07-formulario-ofertas
# El PR se abre desde la web de GitHub: el link aparece en la salida del push.
# Si tenes instalada la CLI de GitHub, equivale a:
# gh pr create --base main --title "feat(ofertas): formulario de carga de ofertas (HU-07)" \
#   --body "Resuelve HU-07. Ver checklist en la plantilla de PR."

# 6. Atender comentarios de revisión con commits adicionales en la misma rama
git commit -m "fix(ofertas): ajusta validacion de cantidad segun revision (HU-07)"
git push

# 7. Una vez aprobado, mergear por squash desde GitHub y borrar la rama
git checkout main
git pull origin main
git branch -d feat/HU-07-formulario-ofertas
```
