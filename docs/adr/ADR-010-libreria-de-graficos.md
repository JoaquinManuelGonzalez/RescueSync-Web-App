# ADR-010: Librería de gráficos del panel de auditoría

- Estado: Propuesto
- Fecha: 2026-11-02
- Reemplaza a: —
- Reemplazado por: —

## Contexto

La épica "Panel de auditor" pide un panel para el perfil Auditor/Directivo con **gráficos
interactivos** y exportación de datos, combinando métricas propias con datos de Bonita. La
primera historia que dibuja gráficos ("Estado de las emergencias y cobertura total vs. parcial")
necesita un gráfico de barras y uno de torta; las siguientes de la épica van a sumar más tipos
(tiempos por etapa, series en el tiempo).

ADR-001 fija Jinja2 + Tailwind CSS y deja la interactividad del navegador a JavaScript vanilla,
sin runtime de componentes. El proyecto no tenía ninguna librería de gráficos, y `layout.html` no
carga nada desde dominios externos: todo lo sirve Flask desde `frontend/estaticos/`. La cadena de
Node existe solo para compilar Tailwind dentro de su contenedor; Flask no ve su `node_modules`.

Sin una decisión común, cada integrante que sume una sección del panel podría elegir otra
librería, o dibujar a mano, y el panel terminaría con estilos y comportamientos distintos.

## Decisión

Se usa **Chart.js 4.4.9**, en su build UMD, **copiado al repositorio** en
`frontend/estaticos/js/vendor/chart-4.4.9.umd.js` (con la licencia MIT en su encabezado). No se
carga desde un CDN.

Ningún template llama a Chart.js directamente. Todo pasa por `frontend/estaticos/js/graficos.js`,
que lee una definición declarativa en `<script type="application/json" data-grafico>` (la arma el
macro `tarjeta_grafico()` de `plantillas/componentes/indicadores.html`) y aplica los colores, la
tipografía, los tooltips en castellano y el respeto a `prefers-reduced-motion` del sitio. Cada
gráfico lleva al lado una tabla con los mismos datos: la leen los lectores de pantalla y es lo
que se ve sin JavaScript.

Chart.js cubre lo que pide la épica (barras, tortas, líneas, tooltips, leyendas, animación,
exportar el lienzo a PNG) con unos 200 KB minificados, una API declarativa simple y licencia MIT.
Copiarlo al repositorio mantiene la regla de no depender de dominios externos, funciona sin
conexión en desarrollo y fija la versión exacta en el control de versiones.

### Versión fijada

| Tecnología | Versión | Archivo del repositorio donde se fija |
|---|---|---|
| Chart.js | `4.4.9` | `frontend/estaticos/js/vendor/chart-4.4.9.umd.js` (el número va en el nombre del archivo) |

### Alternativas consideradas

| Alternativa | A favor | En contra | Motivo del descarte |
|---|---|---|---|
| SVG propio generado con macros Jinja | Sin dependencias; funciona sin JavaScript; fácil de testear en pytest | Cada tipo de gráfico (ejes, escalas, tooltips, accesibilidad) se construye y mantiene a mano | El costo crece con cada gráfico nuevo de la épica |
| Apache ECharts | Muy completo: zoom, drill-down, exportación integrada | Cerca de 1 MB minificado; API más compleja | Desproporcionado para lo que pide la épica |
| Chart.js desde un CDN | No suma archivos al repositorio | Depende de un dominio externo en cada carga; la versión queda fuera del repositorio | Rompe la regla de servir todo desde `estaticos/` |
| Chart.js como dependencia npm, copiado en el build | La versión queda en `package.json` | Flask no ve el `node_modules` del contenedor de Tailwind; habría que copiar el archivo en cada arranque | Agrega un paso de build por un único archivo estático |

## Consecuencias

### Positivas

- Todas las secciones del panel comparten el mismo aspecto y el mismo comportamiento.
- Las plantillas solo declaran datos: cambiar de librería en el futuro toca `graficos.js`, no
  cada pantalla.
- Los tests de backend verifican los gráficos leyendo la definición JSON que se embebe en la
  página, sin navegador.

### Negativas

- El repositorio guarda un archivo minificado de terceros (unos 200 KB).
- Las actualizaciones de Chart.js son manuales.

### Qué nos obliga a hacer

- Todo gráfico nuevo se dibuja con `tarjeta_grafico()` + `graficos.js`. Si necesita un tipo que
  `graficos.js` no soporta, se agrega ahí y se documenta en el encabezado del archivo.
- Para actualizar Chart.js: bajar el tarball oficial de npm (`chart.js-<versión>.tgz`), verificar
  su `shasum` contra el del registro, copiar `package/dist/chart.umd.js` como
  `vendor/chart-<versión>.umd.js`, borrar el anterior, actualizar la referencia en las plantillas
  y esta tabla.
- Ninguna plantilla carga scripts desde dominios externos.
