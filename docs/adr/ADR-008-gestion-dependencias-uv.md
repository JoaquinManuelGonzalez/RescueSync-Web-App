# ADR-008: Gestión de dependencias de Python con uv

- Estado: Propuesto
- Fecha: 2026-09-17
- Reemplaza a: —
- Reemplazado por: —

> Este ADR enmienda parcialmente al ADR-002 y al ADR-005. No los reemplaza: ver la sección
> **Relación con ADRs previos** al final y la regla de enmienda parcial en
> [`docs/adr/README.md`](./README.md).

## Contexto

El ADR-002 fijó que "toda dependencia de Python del proyecto se declara con versión exacta en
`requirements.txt`" y el ADR-005 que el repositorio tiene "un único `requirements.txt` para
todas las dependencias Python". Ninguno de los dos discutió la herramienta de gestión: la
decisión era sobre *dónde* se declaran las dependencias y con *qué* precisión, no sobre cómo
se instalan.

Al construir el esqueleto ejecutable esa cuestión se vuelve concreta, y con dos exigencias que
un `requirements.txt` plano no cubre del todo:

- **Reproducibilidad real.** Un `requirements.txt` escrito a mano fija las dependencias
  directas, pero no el árbol transitivo. Dos integrantes que instalen con una semana de
  diferencia pueden terminar con versiones distintas de una dependencia indirecta, que es
  precisamente el tipo de diferencia que produce el "en mi máquina anda" que esta épica busca
  eliminar.
- **Tiempo de build.** La imagen de la aplicación se reconstruye cada vez que cambian las
  dependencias, en cinco máquinas distintas, durante cinco entregas.

Además, el ADR-002 anticipó un riesgo concreto: que Python 3.14 no tuviera wheel binario para
alguna dependencia. Resolver ese tipo de problema es mucho más rápido con un resolvedor que
permita verificar el árbol completo antes de construir la imagen.

## Decisión

Las dependencias de Python se gestionan con **uv**, en su formato nativo: se declaran en
`backend/pyproject.toml` y el árbol transitivo completo queda fijado en `backend/uv.lock`,
que se versiona. Se elimina `requirements.txt`.

`pyproject.toml` declara las dependencias directas con **versión exacta** (`==`), manteniendo
la exigencia del ADR-002, y separa las de desarrollo en un grupo `dev` que no se instala en la
imagen de producción. El `Dockerfile` instala con `uv sync --locked`, que falla si el lock no
está sincronizado con `pyproject.toml`, de modo que es imposible construir una imagen a partir
de un lock desactualizado.

El mismo `pyproject.toml` aloja la configuración de Ruff que ya fijaba `CONTRIBUTING.md`
sección 4, con lo cual la configuración de herramientas del backend queda en un solo archivo.

### Instalación en la máquina de cada integrante

uv se instala además **en el host**, y pasa a ser un requisito previo del proyecto junto con
Docker. Es lo que permite:

- crear `backend/.venv` con `uv sync --locked`, para que el editor resuelva imports y
  autocompletado y para correr Ruff y pytest con `uv run` sin levantar los contenedores;
- regenerar `uv.lock` con `uv add` / `uv lock` al cambiar una dependencia, sin depender de
  que el contenedor esté levantado ni de que su imagen esté actualizada.

No implica instalar Python a mano: uv descarga y administra el intérprete `3.14` que fija
`.python-version`. La versión de uv del host tiene que ser la misma que la de la imagen para
que el formato de `uv.lock` no varíe entre integrantes.

### Versión fijada

| Tecnología | Versión | Archivo del repositorio donde se fija |
|---|---|---|
| `uv` (imagen de Docker) | `0.12.13` | `backend/Dockerfile` (argumento `UV_VERSION`) |
| `uv` (máquina de cada integrante) | `0.12.13` | `README.md`, sección *Requisitos previos* |
| Intérprete de Python que instala uv | `3.14` | `.python-version` |
| Formato de lock | `backend/uv.lock` | `backend/uv.lock` |
| Declaración de dependencias | `backend/pyproject.toml` | `backend/pyproject.toml` |

### Alternativas consideradas

| Alternativa | A favor | En contra | Motivo del descarte |
|---|---|---|---|
| `requirements.txt` plano con `pip` | Es literalmente lo que decían el ADR-002 y el ADR-005; cero herramientas nuevas | No fija el árbol transitivo; builds de Docker notablemente más lentos | La reproducibilidad del árbol completo es el objetivo central de esta épica |
| `uv` como instalador, con `requirements.in` + `requirements.txt` compilado | Cumple los ADR-002 y ADR-005 al pie de la letra sin enmendarlos; el equipo sigue leyendo un `requirements.txt` normal | Dos archivos para lo mismo; formato de segunda clase para uv; los grupos de dependencias hay que emularlos con archivos separados | Conserva la letra de los ADRs a costa de un flujo más engorroso que el nativo |
| `pip-tools` | Lock con hashes y `requirements.txt` real | Más lento que uv y un paso manual extra para agregar cualquier librería | uv hace lo mismo más rápido y con mejor ergonomía |
| `Poetry` | Muy difundido y con buen manejo de entornos | El más lento de los cuatro en builds de Docker y el más pesado de configurar | No aporta nada que uv no dé más barato |

## Consecuencias

### Positivas

- El árbol transitivo queda fijado: todos instalan exactamente lo mismo.
- `uv sync --locked` falla si alguien tocó `pyproject.toml` sin regenerar el lock, así que el
  desvío se detecta en el build y no en tiempo de ejecución.
- Los grupos de dependencias son nativos: la imagen de producción no arrastra Ruff ni pytest.
- Builds de Docker sensiblemente más rápidos, con la capa de dependencias cacheada aparte del
  código fuente.
- La configuración de Ruff vive junto a las dependencias, en un único `pyproject.toml`.

### Negativas

- Es una herramienta nueva para el equipo, con su propia curva de aprendizaje.
- Deja de ser cierto que lo único que hace falta instalar es Docker: se suma uv a los requisitos
  previos del README. Es un instalador de un comando y no arrastra Python al host, pero es un
  paso más de puesta en marcha y una versión más que mantener alineada entre host e imagen.
- `uv.lock` es un archivo grande y generado: hay que resolver sus conflictos de merge
  regenerándolo, nunca editándolo a mano.
- Queda una dependencia más del ecosistema (`ghcr.io/astral-sh/uv`) en el `Dockerfile`.

### Qué nos obliga a hacer

- Cada integrante instala uv `0.12.13` en su máquina y corre `uv sync --locked` desde
  `backend/` al clonar el repositorio y cada vez que cambien las dependencias en `main`.
- Toda dependencia nueva se agrega con `uv add "paquete==X.Y.Z"` desde `backend/`, es decir a
  `backend/pyproject.toml` **con versión exacta** (`==`), nunca con un rango, y en el mismo PR
  se regenera y se versiona `backend/uv.lock`.
- Las dependencias que solo sirven para desarrollar (linters, tests) van al grupo `dev`, nunca
  a `[project].dependencies`.
- Nunca se edita `uv.lock` a mano. Ante un conflicto de merge se regenera con `uv lock`.
- Toda dependencia nueva se suma además a la tabla de stack tecnológico del `README.md`, en el
  mismo PR.
- No se agrega `watchdog` al grupo `dev`: Werkzeug lo prefiere si es importable y su reloader
  por inotify no recibe eventos a través de los bind mounts de Windows, con lo que rompería la
  recarga en caliente para parte del equipo.

## Relación con ADRs previos

Este ADR **no reemplaza** a ningún ADR: enmienda una cláusula puntual de cada uno y deja el
resto vigente.

- **ADR-002 (framework de backend), enmendado parcialmente.** La cláusula "toda dependencia de
  Python del proyecto se declara con versión exacta en `requirements.txt`" pasa a leerse "...
  con versión exacta en `backend/pyproject.toml`, con el árbol transitivo fijado en
  `backend/uv.lock`". **La exigencia de versión exacta no se relaja: se mantiene y se
  refuerza.** Todo lo demás del ADR-002 —Python 3.14, Flask 3.1.3, la coincidencia entre
  `.python-version` y el `Dockerfile`, los clientes HTTP en `core/integraciones/`— sigue
  vigente sin cambios.
- **ADR-005 (estilo arquitectónico), enmendado parcialmente.** La cláusula "un único
  `requirements.txt` para todas las dependencias Python" pasa a leerse "un único
  `backend/pyproject.toml`". El espíritu se conserva: **un solo lugar donde se declaran las
  dependencias de todo el monolito**, no uno por módulo. El resto del ADR-005 no cambia.
