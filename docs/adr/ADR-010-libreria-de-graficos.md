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

## Actualización: tipos agregados para el resto de la épica

Para las secciones de recursos, red de ONGs, tiempos y proceso, `graficos.js` suma, siempre detrás
del mismo contrato JSON (documentado en su encabezado):

- **Barras apiladas** (`series` + `apilado`): recursos movilizados por mes y rubro, con leyenda
  que permite ocultar un rubro y un tooltip que suma el total del mes.
- **Barras horizontales** (`orientacion: "horizontal"`): para etiquetas largas (ranking de ONGs,
  rubros, etapas del proceso). Toman la altura que necesitan sus barras.
- **Valores sobre las barras** (`mostrarValores`): el gráfico se lee sin pasar el mouse ni abrir
  la tabla.
- **Marcas de referencia** (`marcadores`): una raya por barra sobre el mismo eje (el plazo
  objetivo de cada gravedad junto al tiempo medio de resolución).
- **Sin dato** (`sinDato`): un valor `null` no dibuja barra y escribe el texto indicado
  ("Sin ocurrencias"), para que no se lea como un cero.
- **Imagen PNG**: el menú de exportación de cada gráfico descarga una imagen para informes, con
  fondo blanco (ver "Actualización: imagen PNG para informes").

Las definiciones se arman del lado del servidor (`app/modulos/indicadores/graficos.py`), no en las
plantillas: así se verifican en pytest sin navegador.

**Paleta categórica.** Los rubros usan los tonos `serie-1` a `serie-8`, en un orden fijo validado
para daltonismo (peor par adyacente: ΔE 16,2 con protanopía o deuteranopía y 30,3 con visión
normal). El color sigue a la entidad: un rubro conserva su color con cualquier filtro y en todos los
gráficos; las gravedades usan los mismos colores que sus puntos en los filtros. Tres tonos
(amarillo, aqua y rosa) tienen menos de 3:1 de contraste sobre blanco; por eso todo gráfico lleva su
tabla de respaldo, su leyenda o sus valores escritos.

**Sin doble eje.** Dos HUs pedían un segundo eje (demanda por rubro con la tasa de inhabilitación,
y resolución en término con el porcentaje y los días). Un doble eje invita a comparar alturas que
no son comparables, así que, con el acuerdo del equipo, cada medida va en su propio gráfico, uno al
lado del otro y con las categorías en el mismo orden. Es una regla para todo gráfico nuevo del panel.

**Responsive.** Las etiquetas largas se acortan (horizontal; el tooltip muestra la completa) o se
parten en líneas (vertical) según el ancho del lienzo, la tipografía baja un punto por debajo de
640 px y los gráficos con leyenda ganan altura en el teléfono.

## Actualización: duraciones con precisión de segundos

Los tiempos del panel (tiempos de respuesta, etapas del proceso, resolución en término y tiempo
medio de ejecución del ranking de ONGs) se informaban en días con un decimal. Ese redondeo es de
2,4 horas: una emergencia resuelta en 15 minutos se mostraba como "0,0 días". Ahora:

- **Cálculo.** Las duraciones son `timedelta`, exactas hasta que se promedian; el promedio se
  redondea al segundo, mitad hacia arriba (`app/modulos/indicadores/tiempos.py`).
- **Texto.** Una duración se escribe con días, horas, minutos y segundos, omitiendo los que valen
  cero: "1 d 4 h 12 min 5 s", "15 min 32 s", "2 d 5 min". Así aparece en las cifras destacadas,
  las tablas, los tooltips y las tarjetas. Entre el número y su unidad va un espacio duro, para
  que un renglón nunca separe "59" de "min". Sobre las barras, donde no entra la completa, va
  abreviada a las dos unidades mayores y redondeada a la segunda ("1 d 4 h").
- **Eje.** `barras_de_duracion()` (en `graficos.py`) dibuja los valores en la mayor unidad en la
  que el más alto (contando las marcas de referencia) llega a 2: hasta 1 h 59 min se lee en
  minutos y hasta 47 h en horas, en vez de "1,9 d". Los números del eje llevan la abreviatura
  ("12 h").
- **Contrato de `graficos.js`.** Suma `textos` (el tooltip de cada barra), `textosCortos` (la
  etiqueta sobre la barra), `unidadDelEje` y `marcadores.textos`, todos opcionales. El texto lo
  arma el servidor: el navegador no formatea ni redondea un tiempo, así que no hay un segundo
  formateador que pueda dar otro resultado, y los tests lo verifican sin navegador.
- **Exportación.** Una duración ocupa dos columnas: los segundos exactos (`*_segundos`, entero,
  para calcular en una planilla) y el texto, con espacios comunes. Reemplazan a las columnas
  `*_dias`. Los plazos objetivo siguen en días (`plazo_objetivo_dias`), porque se definen así.

## Actualización: imagen PNG para informes

La opción PNG copiaba el lienzo tal como se ve en pantalla (`toBase64Image()`). En las donas, la
cifra del centro y la leyenda con valores son HTML encima del lienzo, así que la imagen salía solo
con el anillo. Además, ninguna imagen decía qué mostraba ni de qué período era, la resolución
dependía de la pantalla y en el teléfono las etiquetas salían recortadas. Ahora:

- **Se vuelve a dibujar.** `graficos.js::imagen(canvas, { titulo, descripcion, contexto })` arma
  el mismo gráfico, con la misma definición y la misma configuración, en un lienzo aparte de
  ancho fijo (1200 px; 880 las donas) y al doble de resolución, sin animación ni eventos. Con
  `responsive: false`, Chart.js dibuja en el acto aunque el lienzo no esté en la página. El
  resultado no depende de la ventana: en un teléfono la imagen sale igual que en el escritorio.
- **Encabezado.** Título, descripción de la tarjeta (en renglones según el ancho) y período, con
  los plugins `title` y `subtitle` de Chart.js. Llegan en los `data-titulo`, `data-descripcion`
  y `data-contexto` del botón PNG; el período (`exportacion(...).contexto`) lo escribe el
  servidor igual que el resumen de la pantalla. Las descripciones de los gráficos con filtro
  propio lo nombran ("con gravedad alta", "de alimentos"), así la imagen lo dice, y no llevan
  indicaciones de uso, que van en notas debajo del gráfico.
- **Donas.** Suman su leyenda con valores ("Cobertura total: 4 (80 %)", el mismo texto que la
  leyenda HTML) y la cifra del centro, que viaja en los `data-centro-cifra` y
  `data-centro-texto` del `<canvas>`.
- **Lo que se ve.** Las series ocultas desde la leyenda tampoco salen en la imagen.
- **Respaldo.** Si algo falla al armarla, se descarga el lienzo de la pantalla como antes.

También: una dona con una sola porción con valor se dibuja sin borde entre porciones, porque el
borde de la porción en 0 quedaba como una muesca blanca en el anillo.
