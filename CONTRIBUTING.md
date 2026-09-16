# Guía de contribución — RescueSync

Esta guía define cómo se escribe código, cómo se nombran ramas y commits, y cómo se revisan
y mergean los cambios en este repositorio. Es de lectura obligatoria antes del primer commit.
Su objetivo es que cinco personas trabajando en paralelo sobre módulos distintos no choquen
por supuestos distintos.

## Índice

1. Idioma del código
2. Nomenclatura por capa
3. Estructura de carpetas
4. Formato y verificación (Ruff)
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

Ejemplo:

```python
# Calcula la cantidad de dias habiles restantes hasta el cierre de la convocatoria.
def calcular_dias_habiles_restantes(convocatoria: Convocatoria) -> int:
    anio_actual = convocatoria.fecha_cierre.year
    ...
```

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

Más ejemplos de dominio para fijar el criterio, cubriendo las entidades reales de RescueSync
(emergencias, lotes de necesidad, convocatorias, ofertas de ayuda, adjudicación, consorcios):

- Modelos: `Emergencia`, `LoteDeNecesidad`, `Convocatoria`, `OfertaDeAyuda`, `Adjudicacion`,
  `Consorcio`, `UsuarioRol`.
- Servicios: `crear_emergencia`, `cerrar_convocatoria`, `listar_ofertas_de_convocatoria`,
  `adjudicar_lote`, `conformar_consorcio`.
- Tablas: `emergencias`, `lotes_de_necesidad`, `convocatorias`, `ofertas_de_ayuda`,
  `adjudicaciones`, `consorcios`, `usuarios_roles`.
- Columnas booleanas: `es_consorcio`, `es_activa`, `tiene_adjudicacion_vigente`.
- Columnas de fecha: `fecha_creacion`, `fecha_cierre`, `fecha_adjudicacion`,
  `fecha_vencimiento_ventana`.
- Endpoints: `emergencias.crear`, `emergencias.detalle`, `ofertas.crear`, `ofertas.listar`,
  `adjudicacion.confirmar`.
- Restricciones: `uq_ofertas_de_ayuda_convocatoria_id_ong_id`,
  `fk_ofertas_de_ayuda_convocatoria_id`, `ck_lotes_de_necesidad_cantidad_positiva`.

## 3. Estructura de carpetas

```
app/
  core/              configuracion, errores, logging, seguridad,
                      integraciones/{bonita,api_nacional}  -> clientes HTTP compartidos
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
      plantillas/         plantillas Jinja propias del modulo (modulo/accion.html)
  plantillas/          layout base y parciales compartidos por todos los modulos
  estaticos/           CSS compilado por Tailwind, imagenes y otros estaticos
```

Cada carpeta de `modulos/` reproduce siempre el mismo esqueleto interno
(`rutas.py`, `servicios.py`, `modelos.py`, `formularios.py`, `plantillas/`), lo que hace
predecible dónde buscar o agregar algo.

### ¿Dónde escribo una funcionalidad nueva?

- ¿Es una operación de negocio dentro de un módulo existente (por ejemplo, una nueva regla de
  adjudicación)? Va en `servicios.py` del módulo correspondiente, con su endpoint en `rutas.py`
  y, si aplica, su plantilla en `plantillas/`.
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

## 4. Formato y verificación (Ruff)

RescueSync usa **Ruff 0.16.7** como linter y formateador único.

Formatear el código antes de commitear:

```bash
ruff format .
```

Verificar sin modificar archivos (se usa antes de abrir un PR y en cualquier revisión):

```bash
ruff format --check .
ruff check .
```

Cuando `ruff check` encuentra un problema, la salida tiene el formato
`archivo:línea:columna: código mensaje`. Por ejemplo:

```
app/modulos/ofertas/servicios.py:42:1: F401 [*] `datetime` importado pero no usado
app/modulos/ofertas/rutas.py:15:80: E501 la linea supera los 100 caracteres
Found 2 errors.
[*] 1 error corregible automaticamente con `ruff check --fix`.
```

Configuración que la épica del esqueleto ejecutable debe volcar en `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B"]
```

> **Nota importante:** hasta que exista `pyproject.toml` en este repositorio (se crea en la
> épica del esqueleto ejecutable, junto con el `Dockerfile`, `docker-compose.yml` y
> `requirements.txt`), estos comandos están documentados pero **todavía no son ejecutables**
> en este repositorio: no hay archivo de configuración que `ruff` pueda leer ni código Python
> sobre el cual correr. Apenas exista, esta sección queda vigente sin cambios.

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

Estas reglas se hacen cumplir con un **Ruleset de GitHub** sobre `main`. Procedimiento paso a
paso para configurarlo (lo aplica Joaquín desde la web del repositorio):

1. Ir a **Settings → Rules → Rulesets → New branch ruleset**.
2. Ponerle un nombre descriptivo, por ejemplo `Proteccion de main`.
3. **Enforcement status:** `Active`.
4. **Target branches:** incluir `main` (usar la opción "Include default branch").
5. Activar **Require a pull request before merging**, con:
   - **Required approvals:** `1`.
   - **Dismiss stale pull request approvals when new commits are pushed:** activado.
6. Activar **Block force pushes**.
7. Activar **Restrict deletions**.
8. Guardar el ruleset.

> En cuenta GitHub Free, los Rulesets están disponibles tanto en repositorios públicos como
> privados, así que esto no depende de pasar el repo a público. Se recomienda adjuntar una
> captura de pantalla del ruleset activo (la lista de reglas tildadas) como evidencia para la
> cátedra.

## 7. Commits y vínculo con el backlog

Se usa **Conventional Commits en español**, incluyendo siempre el identificador de la HU que
el commit resuelve.

Formato:

```
<tipo>(<alcance>): <descripcion en minuscula> (HU-XX)
```

Ejemplo: `feat(ofertas): agrega formulario de carga de ofertas (HU-07)`

Cuando el asunto queda largo y no entra la referencia a la HU, se agrega al pie del mensaje:

```
feat(adjudicacion): implementa regla de desempate por antiguedad de la ONG

Refs: HU-15
```

| Mensaje | Válido / Inválido | Motivo |
|---|---|---|
| `feat(ofertas): agrega formulario de carga de ofertas (HU-07)` | Válido | tipo, alcance, descripción en minúscula, HU referenciada |
| `fix(emergencias): corrige calculo de ventana de convocatoria (HU-09)` | Válido | corrige un defecto, referencia clara |
| `docs(contributing): documenta flujo de ramas y commits (HU-01)` | Válido | cambio documental con HU |
| `Agrego formulario de ofertas` | Inválido | sin tipo, sin alcance, sin HU, empieza en mayúscula |
| `feat: cambios varios` | Inválido | no describe qué cambia ni referencia una HU |
| `fix(ofertas): FIX BUG (HU-07)` | Inválido | descripción no está en minúscula ni es descriptiva |

## 8. Flujo de trabajo de punta a punta

```bash
# 1. Actualizar main y crear la rama de la HU
git checkout main
git pull origin main
git checkout -b feat/HU-07-formulario-ofertas

# 2. Trabajar y commitear con Conventional Commits
git add app/modulos/ofertas/
git commit -m "feat(ofertas): agrega formulario de carga de ofertas (HU-07)"

# 3. Verificar formato y linter antes de subir (cuando exista pyproject.toml)
ruff format --check .
ruff check .

# 4. Subir la rama y abrir el Pull Request
git push -u origin feat/HU-07-formulario-ofertas
# El PR se abre desde la web de GitHub: el link aparece en la salida del push.
# Si tenes instalada la CLI de GitHub, equivale a:
# gh pr create --base main --title "feat(ofertas): formulario de carga de ofertas (HU-07)" \
#   --body "Resuelve HU-07. Ver checklist en la plantilla de PR."

# 5. Atender comentarios de revisión con commits adicionales en la misma rama
git commit -m "fix(ofertas): ajusta validacion de cantidad segun revision (HU-07)"
git push

# 6. Una vez aprobado, mergear por squash desde GitHub y borrar la rama
git checkout main
git pull origin main
git branch -d feat/HU-07-formulario-ofertas
```

## 9. Guía de revisión

Qué mirar al revisar un PR de un compañero:
- Que resuelve la HU que dice resolver y nada más (alcance acotado).
- Que respeta la nomenclatura de la sección 2 y la estructura de carpetas de la sección 3.
- Que no rompe la regla de dependencia entre módulos (un módulo no importa modelos ni hace
  consultas directas a las tablas de otro módulo, ni llama a Bonita/API Nacional fuera de
  `core/integraciones/`).
- Que los commits siguen Conventional Commits y referencian la HU.
- Que no se commitean secretos, archivos `.env` ni credenciales.
- Que la documentación relacionada (README, ADR, docs de contratos) queda actualizada si el
  cambio la afecta.

Plazo de respuesta: cada integrante se compromete a dar una primera revisión dentro de las
**24 horas** de abierto el PR (o de la última actualización pedida), para no bloquear al resto
del equipo dado el calendario de entregas.

Cómo resolver desacuerdos: se discute primero en los comentarios del PR con argumentos
técnicos concretos; si no hay acuerdo en un intercambio razonable, se lleva el punto a una
reunión breve del equipo (o al canal de chat del grupo) y decide por mayoría simple, dejando
constancia de la decisión en el propio PR antes de mergear.
