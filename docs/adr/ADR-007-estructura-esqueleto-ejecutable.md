# ADR-007: Estructura del esqueleto ejecutable y cadena de build de frontend

- Estado: Propuesto
- Fecha: 2026-09-17
- Reemplaza a: —
- Reemplazado por: —

> Este ADR enmienda parcialmente al ADR-005 y completa al ADR-001. No los reemplaza:
> ver la sección **Relación con ADRs previos** al final y la regla de enmienda parcial
> en [`docs/adr/README.md`](./README.md).

## Contexto

La estructura de carpetas del proyecto quedó definida en `CONTRIBUTING.md` sección 3 y en el
mapa del repositorio del `README.md` **antes de que existiera una sola línea de código**: un
directorio `app/` en la raíz, con `app/core/`, `app/modulos/<modulo>/` y, dentro de cada
módulo, su propia subcarpeta `plantillas/`, más `app/plantillas/` y `app/estaticos/`
compartidos.

Al construir el esqueleto ejecutable aparecen dos cuestiones que esa estructura no resuelve.

La primera es de organización. Con las plantillas Jinja viviendo dentro de cada módulo de
dominio, el código Python y las vistas quedan entremezclados en el mismo árbol: abrir
`app/modulos/emergencias/` muestra a la vez lógica de negocio, acceso a datos, formularios y
HTML. El equipo prefiere poder trabajar sobre la presentación sin navegar el código, y a la
inversa.

La segunda es la cadena de build de Tailwind, que el propio ADR-001 dejó explícitamente sin
resolver:

> "Tailwind requiere Node.js para su cadena de build […]. Esta máquina de desarrollo no tiene
> Node instalado todavía; la resolución concreta de esa cadena de build (Node dockerizado o
> no, script de build, watch en desarrollo) queda a cargo de la épica del esqueleto
> ejecutable, que es la que crea `Dockerfile`, `docker-compose.yml` y los archivos de
> configuración de Node."

Ese material —`package.json`, el CSS fuente, la configuración de Tailwind, el `Dockerfile` de
Node— no tiene hoy ningún lugar asignado en el árbol, y no es código Python: meterlo dentro
de `app/` sería forzarlo.

Si no se decide nada, cada integrante ubicaría las plantillas y los archivos de Node donde le
parezca, que es exactamente el problema que los ADRs existen para evitar.

## Decisión

El repositorio se organiza en **dos carpetas hermanas en la raíz**: `backend/`, que contiene
únicamente código Python, y `frontend/`, que contiene únicamente presentación (plantillas
Jinja, estáticos y la cadena de build de Tailwind). El `docker-compose.yml` sigue en la raíz,
como exige el ADR-004.

El árbol interno de `backend/app/` es exactamente el que ya definía `CONTRIBUTING.md`, un
nivel más abajo, con una sola diferencia: **los módulos ya no tienen subcarpeta
`plantillas/`**. Todas las vistas viven en `frontend/plantillas/<modulo>/<accion>.html`.

```
backend/                          frontend/
└── app/                          ├── plantillas/
    ├── core/                     │   ├── base.html
    │   └── integraciones/        │   ├── parciales/
    └── modulos/<modulo>/         │   └── <modulo>/<accion>.html
        ├── rutas.py              ├── estaticos/css/app.css
        ├── servicios.py          ├── src/input.css
        ├── modelos.py            ├── package.json
        └── formularios.py        └── Dockerfile
```

Esto no obliga a configurar nada raro en Jinja: la convención de nombres de plantilla que
`CONTRIBUTING.md` ya fijaba (`modulo/accion.html`) mapea directamente a un único directorio
raíz de plantillas con una subcarpeta por módulo, de modo que
`render_template("emergencias/alta.html")` resuelve con el loader por defecto de Flask. La
aplicación apunta `template_folder` y `static_folder` a `frontend/`, y los estáticos se sirven
bajo la URL `/estaticos`.

Tailwind se compila en un **contenedor Node dedicado** (`node:22-alpine`), declarado como
servicio `tailwind` en el `docker-compose.yml`, que deja la salida en
`frontend/estaticos/css/app.css`. Nadie necesita instalar Node en su máquina. Ese CSS
compilado **no se versiona**: lo regenera el contenedor en cada arranque, y versionarlo solo
produciría conflictos de merge.

La recompilación automática **no** usa `tailwindcss --watch`, sino un bucle propio
(`frontend/observar.sh`) que compara marcas de tiempo cada dos segundos. El motivo se midió,
no se supuso: el modo `--watch` depende de notificaciones de inotify, y esos eventos no
atraviesan un bind mount de Windows ni de macOS. El resultado es el peor posible, porque no da
ningún síntoma: el proceso queda vivo, compila una vez al arrancar y después ignora todos los
cambios, de modo que uno guarda una plantilla, recarga el navegador y ve estilos viejos sin
entender por qué. La variable `CHOKIDAR_USEPOLLING`, que suele proponerse para esto, tampoco
aplica: Tailwind 4 no usa chokidar. Un bucle de `find -newer` cuesta una compilación de ~110 ms
cuando algo cambió de verdad, y funciona igual en los tres sistemas operativos.

Tailwind 4 se configura desde el propio CSS (`@import`, `@source`, `@theme`), así que **no hay
`tailwind.config.js`**.

### Versión fijada

| Tecnología | Versión | Archivo del repositorio donde se fija |
|---|---|---|
| `Node.js` | `22` (LTS), imagen `node:22-alpine` | `frontend/.nvmrc`, `frontend/Dockerfile` |
| `tailwindcss` | `4.3.3` | `frontend/package.json`, `frontend/package-lock.json` |
| `@tailwindcss/cli` | `4.3.3` | `frontend/package.json`, `frontend/package-lock.json` |

### Alternativas consideradas

| Alternativa | A favor | En contra | Motivo del descarte |
|---|---|---|---|
| `app/` en la raíz con plantillas dentro de cada módulo (lo que decía CONTRIBUTING) | Cero cambios a documentos ya aprobados; cada módulo es dueño de todo lo suyo | Mezcla lógica y presentación en el mismo árbol; deja sin lugar a `package.json` y al resto de la cadena de Node | Es justamente el problema que motiva este ADR |
| `frontend/` solo con la cadena de Tailwind, plantillas dentro de los módulos | Separa lo que hoy no tiene lugar sin tocar la regla de plantillas por módulo | La mezcla de lógica y vistas se mantiene; el contenedor de Node tiene que escribir dentro de `backend/`, cruzando las dos carpetas | Resuelve media cuestión: la de Node, no la de organización |
| SPA separada (React/Vite) consumiendo una API JSON | Separación total entre front y back | Contradice el ADR-001 (Jinja2), agrega CORS, autenticación por token y un servicio pesado más al compose | El ADR-001 ya decidió Jinja2 y no hay motivo para reabrirlo |
| Tailwind por CDN, sin contenedor de Node | Sin build step ni servicio extra; arranque más rápido | No apto para producción, sin purge ni `@theme` propio, sin versión fijada | El proyecto llega a producción en la Entrega 5; empezar con algo descartable es trabajo duplicado |
| `node_modules` dentro de `frontend/` | Es la ubicación convencional | El bind mount de `frontend/` la taparía; obliga a parchear con un volumen anónimo | Se instala en `/node_modules` del contenedor, que además es donde el resolver de Tailwind lo encuentra al subir desde `frontend/src` |

## Consecuencias

### Positivas

- `backend/` es 100 % Python y `frontend/` 100 % presentación: se puede trabajar en uno sin
  navegar el otro.
- El contenedor de Node solo monta `frontend/` y no toca el backend para nada.
- Nadie instala Node, ni Python, ni PostgreSQL en su máquina: alcanza con Docker.
- La cadena de build queda con versión fijada y `package-lock.json` versionado, así que
  compila igual en todas las máquinas.

### Negativas

- Hay que actualizar `CONTRIBUTING.md` sección 3 y el mapa del `README.md`, que ya estaban
  mergeados.
- Un módulo deja de ser autocontenido: su código está en `backend/app/modulos/<modulo>/` y sus
  vistas en `frontend/plantillas/<modulo>/`. Son dos lugares en vez de uno.
- Un servicio más en el `docker-compose.yml`.

### Qué nos obliga a hacer

- Todo código Python va bajo `backend/`; toda plantilla Jinja y todo estático, bajo
  `frontend/`. Un `.html` dentro de `backend/` es un error de revisión.
- Las plantillas se nombran `frontend/plantillas/<modulo>/<accion>.html`, manteniendo la
  convención de `CONTRIBUTING.md`.
- Ninguna dependencia de Node se agrega sin versión exacta y sin actualizar
  `package-lock.json` en el mismo PR.
- `frontend/estaticos/css/app.css` nunca se commitea: está en `.gitignore`.
- Si alguna vez se escriben clases de Tailwind dentro de archivos `.py`, hay que agregar una
  directiva `@source` a `frontend/src/input.css` apuntando a ellos, o esas clases no se
  compilan.

## Relación con ADRs previos

Este ADR **no reemplaza** a ningún ADR: enmienda cláusulas puntuales y deja el resto vigente.

- **ADR-005 (estilo arquitectónico), enmendado parcialmente.** Donde dice "una carpeta por
  módulo dentro de `app/modulos/`", ahora se lee `backend/app/modulos/`. La decisión de fondo
  —monolito modular, un único repositorio, la cadena acíclica de dependencias entre módulos y
  la regla de que nadie importa los modelos de otro módulo— **no cambia**. Lo que sí cambia es
  que las plantillas dejan de vivir dentro del módulo.
- **ADR-002 (framework de backend), enmendado parcialmente.** Los clientes HTTP siguen yendo
  en `core/integraciones/`, ahora bajo `backend/app/core/integraciones/`.
- **ADR-001 (framework de frontend), completado.** Este ADR resuelve la cadena de build que el
  ADR-001 delegó explícitamente a la épica del esqueleto ejecutable. No modifica nada de lo
  que el ADR-001 decidió: Jinja2 y Tailwind siguen siendo la elección.
- **ADR-004 (motor de base de datos), respetado sin cambios.** El `docker-compose.yml` sigue en
  la raíz del repositorio, el servicio se sigue llamando `db`, y Bonita y la API Nacional
  siguen fuera de ese compose.
