/*
 * Graficos del panel de auditoria, dibujados con Chart.js (estaticos/js/vendor/, ver ADR-010).
 *
 * Los arma el macro `tarjeta_grafico()` de plantillas/componentes/indicadores.html. Cada grafico
 * es un [data-grafico-contenedor] con su <canvas> (dentro de [data-grafico-lienzo], oculto), una
 * tabla con los mismos datos ([data-grafico-respaldo]) y su definicion en
 * <script type="application/json" data-grafico>. La definicion la arma el servidor
 * (app/modulos/indicadores/graficos.py) o la plantilla:
 *
 *   tipo           "barras" o "dona"
 *   etiquetas      texto de cada barra o porcion
 *
 *   Una sola serie:
 *   valores        numero de cada barra o porcion; null es "sin dato" (no es un cero)
 *   tonos          color de cada una (ver TONOS)
 *   unidad         [singular, plural], para tooltips y etiquetas: "3 emergencias"
 *   decimales      (opcional) decimales de los valores: 1 para "2,5"
 *   detalles       (opcional) una linea extra del tooltip por valor, o null
 *   textos         (opcional, barras) el valor ya escrito por el servidor, para el tooltip, en
 *                  lugar del numero con su unidad: "1 d 4 h 12 min 5 s"; null donde no hay valor
 *   textosCortos   (opcional, barras) idem, para la etiqueta sobre la barra: "1 d 4 h"
 *   unidadDelEje   (opcional, barras) abreviatura que acompaña a los numeros del eje: "12 h"
 *   porcentajes    (opcional, dona) el porcentaje de cada porcion, ya calculado por el servidor
 *   orientacion    (opcional, barras) "horizontal": para etiquetas largas (ONGs, rubros, etapas)
 *   mostrarValores (opcional, barras) escribe el valor al final de cada barra
 *   maximo         (opcional, barras) tope del eje de valores: 100 para porcentajes
 *   marcadores     (opcional, barras) {nombre, valores, textos}: una marca de referencia por barra
 *                  sobre el mismo eje (el plazo objetivo de cada gravedad); `textos` (opcional) es
 *                  lo que dice el tooltip de cada marca en lugar del numero
 *
 *   Las duraciones (app/modulos/indicadores/graficos.py::barras_de_duracion) llegan con los
 *   valores en la unidad del eje (minutos, horas o dias, segun el valor mas alto) y con
 *   `textos`, `textosCortos` y `unidadDelEje`: aca no se formatea ni se redondea un tiempo.
 *   sinDato        (opcional) texto que se escribe donde el valor es null ("Sin ocurrencias")
 *   enlaces        (opcional, barras) una URL por barra: tocarla sigue el enlace del filtro de la
 *                  seccion que lleva a esa URL (indicadores.js lo aplica sin recargar). El filtro
 *                  sigue a la vista: es el camino con teclado y sin JavaScript
 *
 *   Barras apiladas:
 *   series         [{nombre, valores, tono, unidad, decimales}], una por segmento
 *   apilado        true
 *
 * Nunca hay doble eje: dos medidas de escala distinta van en dos graficos (ADR-010).
 *
 * Los tonos son nombres, nunca colores: primario, exito, advertencia, info, neutro, tenue y
 * serie-1 a serie-8, la paleta categorica validada para daltonismo (el color sigue a la entidad).
 *
 * Responsive: los graficos horizontales toman la altura que necesitan sus barras, las etiquetas
 * largas se acortan (horizontal) o se parten en lineas (vertical) segun el ancho disponible, y la
 * tipografia baja un punto en pantallas angostas. Chart.js vuelve a dibujar al cambiar el tamaño.
 *
 * Al dibujar, el lienzo aparece y la tabla queda solo para lectores de pantalla. Sin JavaScript,
 * o si Chart.js no cargo, la tabla sigue a la vista.
 *
 * Expone `window.RescueSync.graficos` con `iniciar(raiz)`, `destruir(raiz)` (para volver a
 * dibujar cuando una pantalla reemplaza parte de la pagina, lo usa indicadores.js) e
 * `imagen(canvas, { titulo, descripcion, contexto })`, que devuelve el grafico como PNG (data
 * URL) para descargarlo.
 *
 * Imagen para informes: no se copia el lienzo de la pantalla, que depende del ancho de la
 * ventana y deja afuera lo que la pagina escribe en HTML (la cifra del centro de una dona, su
 * leyenda, el titulo). Se vuelve a dibujar el mismo grafico, con la misma definicion, en un
 * lienzo aparte de ancho fijo y al doble de resolucion, con el titulo, la descripcion y el
 * periodo como encabezado; las donas suman su leyenda con valores y la cifra del centro (que
 * llega en los data-centro-cifra / data-centro-texto del <canvas>). Las series que la persona
 * oculto en la leyenda tampoco salen. Si algo falla, se descarga el lienzo tal como se ve.
 */
(() => {
  "use strict";

  const instancias = new Map(); // canvas -> { grafico: Chart, definicion }
  const sinMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const formatos = new Map();

  const TINTA = "#374151";
  const TINTA_SECUNDARIA = "#6b7280";
  const TINTA_TENUE = "#9ca3af";
  const GRILLA = "#f3f4f6";
  const ANGOSTO = 480; // px de ancho del lienzo por debajo de los cuales se compacta

  function variableCss(nombre, respaldo) {
    return getComputedStyle(document.documentElement).getPropertyValue(nombre).trim() || respaldo;
  }

  // Los colores de marca salen del tema de Tailwind (src/input.css). La paleta categorica
  // (serie-1 a serie-8) esta validada para daltonismo en este orden: no se reordena.
  function paleta() {
    const primario = variableCss("--color-primario", "#a00d27");
    return {
      primario,
      exito: variableCss("--color-exito", "#2e9b5b"),
      advertencia: "#f59e0b",
      info: "#3b82f6",
      neutro: "#9ca3af",
      tenue: "#d1d5db",
      "serie-1": primario,
      "serie-2": "#1baf7a",
      "serie-3": "#6250d6",
      "serie-4": "#eb6834",
      "serie-5": "#2a78d6",
      "serie-6": "#eda100",
      "serie-7": "#008300",
      "serie-8": "#e87ba4",
    };
  }

  function formato(decimales = 0) {
    if (!formatos.has(decimales)) {
      formatos.set(
        decimales,
        new Intl.NumberFormat("es-AR", { minimumFractionDigits: decimales, maximumFractionDigits: decimales }),
      );
    }
    return formatos.get(decimales);
  }

  function conUnidad(valor, [singular, plural] = ["", ""], decimales = 0) {
    if (valor === null || valor === undefined) return "—";
    const texto = formato(decimales).format(valor);
    const unidad = valor === 1 ? singular : plural;
    return unidad === "%" ? `${texto} %` : `${texto} ${unidad}`.trim();
  }

  // Valor corto para escribir sobre la barra: sin la unidad, salvo el porcentaje.
  function valorCorto(valor, unidad, decimales) {
    const texto = formato(decimales).format(valor);
    return unidad?.[1] === "%" ? `${texto} %` : texto;
  }

  const esAngosto = (grafico) => grafico.width < ANGOSTO;

  function acortar(texto, maximo) {
    return texto.length <= maximo ? texto : `${texto.slice(0, maximo - 1).trimEnd()}…`;
  }

  // Parte una etiqueta en lineas de hasta `ancho` caracteres, sin cortar palabras.
  function partir(texto, ancho) {
    const lineas = [];
    let actual = "";
    for (const palabra of texto.split(" ")) {
      if (actual && `${actual} ${palabra}`.length > ancho) {
        lineas.push(actual);
        actual = palabra;
      } else {
        actual = actual ? `${actual} ${palabra}` : palabra;
      }
    }
    if (actual) lineas.push(actual);
    return lineas;
  }

  function opcionesComunes(definicion) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: sinMovimiento ? false : { duration: 700, easing: "easeOutQuart" },
      layout: { padding: { top: 4, right: 8 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#111827",
          padding: 10,
          cornerRadius: 8,
          displayColors: true,
          boxPadding: 4,
          usePointStyle: true,
          callbacks: {
            // El titulo del tooltip siempre muestra la etiqueta completa, aunque el eje la acorte.
            title: (items) => items[0]?.label ?? "",
            afterLabel: (contexto) => definicion.detalles?.[contexto.dataIndex] || "",
          },
        },
      },
    };
  }

  // `sufijo` acompaña a cada numero del eje: " %" o la unidad de una duracion (" h").
  function ejeDeValores({ decimales = 0, maximo, sufijo = "" } = {}) {
    return {
      beginAtZero: true,
      max: maximo ?? undefined,
      // Aire sobre la barra mas alta para que entre su etiqueta de valor.
      grace: maximo ? 0 : "12%",
      border: { display: false },
      grid: { color: GRILLA },
      ticks: {
        precision: decimales ? undefined : 0,
        maxTicksLimit: 6,
        // Con decimales la escala puede ir de a 0,5: sin ellos, 2,5 se leeria como "3".
        callback: (valor) => `${formato(Number.isInteger(valor) ? 0 : decimales || 1).format(valor)}${sufijo}`,
      },
    };
  }

  // La marca de referencia de una barra (ver `marcadores`), o null si el grafico no tiene.
  function marcaDe(grafico, indice) {
    const marca = grafico.data.datasets.length > 1 ? grafico.getDatasetMeta(1).data[indice] : null;
    return marca && !marca.skip ? marca : null;
  }

  // Escribe el valor al final de cada barra y `sinDato` donde no hay valor.
  function pluginDeEtiquetas(definicion, horizontal) {
    return {
      id: "etiquetasDeValor",
      afterDatasetsDraw(grafico) {
        const { ctx, chartArea, scales } = grafico;
        const barras = grafico.getDatasetMeta(0);
        const tamano = esAngosto(grafico) ? 11 : 12;
        const familia = window.Chart.defaults.font.family;
        ctx.save();
        definicion.valores.forEach((valor, indice) => {
          const elemento = barras.data[indice];
          if (!elemento) return;
          if (valor === null || valor === undefined) {
            if (!definicion.sinDato) return;
            ctx.fillStyle = TINTA_TENUE;
            ctx.font = `italic ${tamano}px ${familia}`;
            const posicion = (horizontal ? scales.y : scales.x).getPixelForValue(indice);
            if (horizontal) {
              ctx.textAlign = "left";
              ctx.textBaseline = "middle";
              ctx.fillText(definicion.sinDato, chartArea.left + 8, posicion);
            } else {
              // Sobre la base del eje, salvo que la marca de referencia caiga en ese renglon: ahi
              // va encima de la marca, para que no la tache.
              const base = chartArea.bottom - 8;
              const marca = marcaDe(grafico, indice);
              const tapado = marca && marca.y > base - tamano - 4;
              ctx.textAlign = "center";
              ctx.textBaseline = "bottom";
              ctx.fillText(definicion.sinDato, posicion, tapado ? marca.y - 7 : base);
            }
            return;
          }
          if (!definicion.mostrarValores) return;
          ctx.fillStyle = TINTA;
          ctx.font = `600 ${tamano}px ${familia}`;
          const texto = definicion.textosCortos?.[indice] ?? valorCorto(valor, definicion.unidad, definicion.decimales || 0);
          if (horizontal) {
            const ancho = ctx.measureText(texto).width;
            // Si no entra a la derecha de la barra, va adentro, en blanco.
            const afuera = elemento.x + 6 + ancho <= chartArea.right;
            ctx.fillStyle = afuera ? TINTA : "#ffffff";
            ctx.textAlign = afuera ? "left" : "right";
            ctx.textBaseline = "middle";
            ctx.fillText(texto, afuera ? elemento.x + 6 : elemento.x - 6, elemento.y);
          } else {
            // Por encima de la barra y, si hay una marca de referencia mas arriba, de la marca.
            const marca = marcaDe(grafico, indice);
            const tope = marca ? Math.min(elemento.y, marca.y - 3) : elemento.y;
            ctx.textAlign = "center";
            ctx.textBaseline = "bottom";
            ctx.fillText(texto, elemento.x, tope - 4);
          }
        });
        ctx.restore();
      },
    };
  }

  // Fondo blanco en el lienzo: la imagen descargada no queda transparente.
  const pluginDeFondo = {
    id: "fondo",
    beforeDraw(grafico) {
      const { ctx, width, height } = grafico;
      ctx.save();
      ctx.globalCompositeOperation = "destination-over";
      ctx.fillStyle = variableCss("--color-superficie", "#ffffff");
      ctx.fillRect(0, 0, width, height);
      ctx.restore();
    },
  };

  function ejeDeEtiquetas(definicion, horizontal) {
    return {
      grid: { display: false },
      border: { display: false },
      ticks: {
        autoSkip: horizontal ? false : true,
        maxRotation: 0,
        callback(_valor, indice) {
          const etiqueta = definicion.etiquetas[indice] ?? "";
          const ancho = this.chart.width;
          if (horizontal) {
            return acortar(etiqueta, ancho < ANGOSTO ? 16 : ancho < 768 ? 26 : ancho < 1024 ? 36 : 52);
          }
          const porCategoria = ancho / Math.max(definicion.etiquetas.length, 1);
          return partir(etiqueta, Math.max(8, Math.floor(porCategoria / 7)));
        },
      },
    };
  }

  // --- Una sola serie ---------------------------------------------------------------

  // Tocar una barra hace lo mismo que elegir su opcion en el filtro de la seccion: se busca ese
  // enlace y se lo activa, asi indicadores.js reemplaza solo las regiones que cambian.
  function seguirEnlace(url) {
    const enlace = [...document.querySelectorAll("[data-filtro-de-seccion] a[href]")].find(
      (candidato) => candidato.getAttribute("href") === url,
    );
    if (enlace) enlace.click();
    else window.location.assign(url);
  }

  function barrasConEnlaces(opciones, enlaces) {
    opciones.onClick = (_evento, elementos) => {
      const url = enlaces[elementos[0]?.index];
      if (url) seguirEnlace(url);
    };
    opciones.onHover = (evento, elementos) => {
      const lienzo = evento.native?.target;
      if (lienzo) lienzo.style.cursor = elementos.length ? "pointer" : "default";
    };
  }

  function configuracionDeBarras(definicion, colores) {
    if (definicion.series) return configuracionDeApiladas(definicion, colores);

    const horizontal = definicion.orientacion === "horizontal";
    const decimales = definicion.decimales || 0;
    const coloresDelGrafico = definicion.tonos.map((tono) => colores[tono] || colores.primario);
    const opciones = opcionesComunes(definicion);
    opciones.indexAxis = horizontal ? "y" : "x";
    opciones.plugins.tooltip.callbacks.label = (contexto) => {
      const indice = contexto.dataIndex;
      const valor = horizontal ? contexto.parsed.x : contexto.parsed.y;
      if (contexto.datasetIndex === 1) {
        const { nombre, textos } = definicion.marcadores;
        return `${nombre}: ${textos?.[indice] ?? conUnidad(valor, definicion.unidad)}`;
      }
      return definicion.textos?.[indice] ?? conUnidad(valor, definicion.unidad, decimales);
    };

    const sufijo = definicion.unidad?.[1] === "%" ? " %" : definicion.unidadDelEje ? ` ${definicion.unidadDelEje}` : "";
    const valores = ejeDeValores({ decimales, maximo: definicion.maximo, sufijo });
    // Con un tope fijo (100 %) la barra llena llega al borde: se deja lugar para su etiqueta.
    if (definicion.maximo && definicion.mostrarValores) {
      opciones.layout.padding = horizontal ? { top: 4, right: 44 } : { top: 22, right: 8 };
    }
    opciones.scales = horizontal
      ? { y: ejeDeEtiquetas(definicion, true), x: valores }
      : { x: ejeDeEtiquetas(definicion, false), y: valores };
    if (definicion.enlaces) barrasConEnlaces(opciones, definicion.enlaces);

    const datasets = [
      {
        data: definicion.valores,
        backgroundColor: coloresDelGrafico,
        hoverBackgroundColor: coloresDelGrafico,
        borderRadius: 4,
        borderSkipped: "start",
        maxBarThickness: horizontal ? 24 : 56,
        categoryPercentage: horizontal ? 0.7 : 0.8,
        order: 1,
      },
    ];
    if (definicion.marcadores) {
      // La marca de referencia: una raya horizontal sobre cada barra, sin linea que las una.
      datasets.push({
        type: "line",
        label: definicion.marcadores.nombre,
        data: definicion.marcadores.valores,
        showLine: false,
        pointStyle: "line",
        pointRadius: 18,
        pointHoverRadius: 20,
        pointBorderWidth: 3,
        pointBorderColor: TINTA,
        pointBackgroundColor: TINTA,
        order: 0, // menor orden: se dibuja encima de las barras
      });
      opciones.plugins.legend = leyenda([{ text: definicion.marcadores.nombre, pointStyle: "line", strokeStyle: TINTA, lineWidth: 3 }]);
    }

    return {
      type: "bar",
      data: { labels: definicion.etiquetas, datasets },
      options: opciones,
      plugins: [pluginDeEtiquetas(definicion, horizontal), pluginDeFondo],
    };
  }

  function leyenda(etiquetasFijas) {
    return {
      display: true,
      position: "bottom",
      labels: {
        usePointStyle: true,
        pointStyle: "circle",
        boxWidth: 8,
        boxHeight: 8,
        padding: 14,
        color: "#4b5563",
        ...(etiquetasFijas ? { generateLabels: () => etiquetasFijas.map((e) => ({ fillStyle: e.strokeStyle, ...e })) } : {}),
        // En el orden de las series.
        sort: (a, b) => (a.datasetIndex ?? 0) - (b.datasetIndex ?? 0),
      },
    };
  }

  function configuracionDeDona(definicion, colores) {
    const coloresDelGrafico = definicion.tonos.map((tono) => colores[tono] || colores.primario);
    // El borde separa porciones: con una sola porcion con valor, el de la porcion en 0 quedaria
    // como una muesca blanca en el anillo.
    const conValor = definicion.valores.filter((valor) => valor > 0).length;
    const opciones = opcionesComunes(definicion);
    opciones.cutout = "72%";
    opciones.layout = { padding: 4 };
    opciones.plugins.tooltip.callbacks.title = () => "";
    opciones.plugins.tooltip.callbacks.label = (contexto) => {
      const porcentaje = definicion.porcentajes?.[contexto.dataIndex];
      const cantidad = conUnidad(contexto.parsed, definicion.unidad);
      const texto = porcentaje === undefined ? cantidad : `${cantidad} (${porcentaje} %)`;
      return `${definicion.etiquetas[contexto.dataIndex]}: ${texto}`;
    };
    return {
      type: "doughnut",
      data: {
        labels: definicion.etiquetas,
        datasets: [
          {
            data: definicion.valores,
            backgroundColor: coloresDelGrafico,
            hoverBackgroundColor: coloresDelGrafico,
            borderColor: variableCss("--color-superficie", "#ffffff"),
            borderWidth: conValor > 1 ? 3 : 0,
            hoverOffset: 6,
          },
        ],
      },
      options: opciones,
      plugins: [pluginDeFondo],
    };
  }

  // --- Barras apiladas --------------------------------------------------------------

  // En una barra apilada solo se redondea el extremo del ultimo segmento con valor.
  function radioDelSegmento(datasets) {
    return (contexto) => {
      const indice = contexto.dataIndex;
      let ultimo = -1;
      datasets.forEach((dataset, posicion) => {
        if (dataset.data[indice]) ultimo = posicion;
      });
      return contexto.datasetIndex === ultimo ? { topLeft: 4, topRight: 4 } : 0;
    };
  }

  function configuracionDeApiladas(definicion, colores) {
    const superficie = variableCss("--color-superficie", "#ffffff");
    const datasets = definicion.series.map((serie) => {
      const color = colores[serie.tono] || colores.primario;
      return {
        label: serie.nombre,
        data: serie.valores,
        backgroundColor: color,
        hoverBackgroundColor: color,
        borderColor: superficie,
        borderWidth: { top: 2 },
        borderSkipped: "start",
        maxBarThickness: 56,
        categoryPercentage: 0.7,
      };
    });
    datasets.forEach((dataset) => {
      dataset.borderRadius = radioDelSegmento(datasets);
    });

    const opciones = opcionesComunes(definicion);
    opciones.interaction = { mode: "index", intersect: false };
    opciones.plugins.legend = leyenda();
    opciones.plugins.tooltip.itemSort = (a, b) => b.datasetIndex - a.datasetIndex;
    opciones.plugins.tooltip.filter = (item) => Boolean(item.raw);
    opciones.plugins.tooltip.callbacks.label = (contexto) => {
      const serie = definicion.series[contexto.datasetIndex];
      return `${serie.nombre}: ${conUnidad(contexto.raw, serie.unidad, serie.decimales || 0)}`;
    };
    opciones.plugins.tooltip.callbacks.footer = (items) => {
      const total = items.reduce((suma, item) => suma + (item.raw || 0), 0);
      return `Total: ${conUnidad(total, definicion.series[0]?.unidad)}`;
    };
    opciones.scales = {
      x: { ...ejeDeEtiquetas(definicion, false), stacked: true },
      y: { ...ejeDeValores(), stacked: true, grace: 0 },
    };

    return {
      type: "bar",
      data: { labels: definicion.etiquetas, datasets },
      options: opciones,
      plugins: [pluginDeFondo],
    };
  }

  const CONFIGURACIONES = { barras: configuracionDeBarras, dona: configuracionDeDona };

  // Un grafico horizontal mide lo que necesitan sus barras: ni barras aplastadas con muchas
  // categorias ni barras gigantes con dos. Uno con leyenda de varias series gana altura en el
  // telefono, donde la leyenda ocupa varios renglones y le quitaria espacio al trazado.
  function ajustarAltura(lienzo, definicion) {
    if (definicion.orientacion === "horizontal") {
      const barras = definicion.etiquetas.length;
      const conLeyenda = definicion.marcadores ? 32 : 0;
      lienzo.style.height = `${Math.max(160, barras * 40 + 48 + conLeyenda)}px`;
    } else if (definicion.series && lienzo.clientWidth < ANGOSTO) {
      lienzo.style.height = `${280 + Math.ceil(definicion.series.length / 3) * 22}px`;
    }
  }

  function dibujar(contenedor) {
    const fuente = contenedor.querySelector("script[data-grafico]");
    const lienzo = contenedor.querySelector("[data-grafico-lienzo]");
    const canvas = lienzo?.querySelector("canvas");
    if (!fuente || !canvas || instancias.has(canvas)) return;

    const definicion = JSON.parse(fuente.textContent);
    const configurar = CONFIGURACIONES[definicion.tipo];
    if (!configurar) return;

    // El lienzo tiene que estar visible antes de crear el grafico, para que tome su tamaño.
    lienzo.hidden = false;
    ajustarAltura(lienzo, definicion);
    const grafico = new window.Chart(canvas, configurar(definicion, paleta()));
    instancias.set(canvas, { grafico, definicion });
    contenedor.querySelector("[data-grafico-respaldo]")?.classList.add("sr-only");
  }

  function aplicarTipografia() {
    const estilo = getComputedStyle(document.body);
    window.Chart.defaults.font.family = estilo.fontFamily;
    window.Chart.defaults.font.size = window.innerWidth < 640 ? 11 : 12;
    window.Chart.defaults.color = TINTA_SECUNDARIA;
  }

  function iniciar(raiz = document) {
    if (!window.Chart) return;
    aplicarTipografia();
    raiz.querySelectorAll("[data-grafico-contenedor]").forEach(dibujar);
  }

  function destruir(raiz = document) {
    raiz.querySelectorAll("[data-grafico-contenedor] canvas").forEach((canvas) => {
      instancias.get(canvas)?.grafico.destroy();
      instancias.delete(canvas);
    });
  }

  // --- Imagen para informes -----------------------------------------------------------

  // Medidas en px de CSS. La imagen se dibuja al doble (`escala`) para que se lea nitida
  // impresa o proyectada, y con ancho fijo para que no dependa de la ventana: en un telefono las
  // etiquetas no salen recortadas.
  const IMAGEN = {
    ancho: 1200,
    anchoDona: 880,
    escala: 2,
    margen: 32,
    letra: 13,
    letraTitulo: 20,
    letraSubtitulo: 14,
    renglonSubtitulo: 1.45,
  };

  // Parte un texto en renglones que entren en `ancho` px con esa fuente, sin cortar palabras.
  function renglones(texto, ancho, fuente) {
    const ctx = document.createElement("canvas").getContext("2d");
    ctx.font = fuente;
    const lineas = [];
    let actual = "";
    for (const palabra of texto.split(/\s+/).filter(Boolean)) {
      const candidata = actual ? `${actual} ${palabra}` : palabra;
      if (actual && ctx.measureText(candidata).width > ancho) {
        lineas.push(actual);
        actual = palabra;
      } else {
        actual = candidata;
      }
    }
    if (actual) lineas.push(actual);
    return lineas;
  }

  // Alto del trazado (ejes, barras, leyenda), sin el encabezado.
  function altoDelTrazado(definicion) {
    if (definicion.tipo === "dona") return 460;
    if (definicion.orientacion === "horizontal") {
      const conLeyenda = definicion.marcadores ? 36 : 0;
      return Math.max(220, definicion.etiquetas.length * 44 + 64 + conLeyenda);
    }
    return definicion.series ? 500 : 460;
  }

  // La cifra del hueco de la dona, que en pantalla es HTML encima del lienzo.
  function pluginDeCentro(cifra, texto) {
    return {
      id: "centro",
      afterDatasetsDraw(grafico) {
        const arco = grafico.getDatasetMeta(0).data[0];
        if (!arco || !cifra) return;
        const { x, y, innerRadius } = arco;
        const familia = window.Chart.defaults.font.family;
        const tamanoCifra = Math.round(innerRadius * 0.42);
        const tamanoTexto = Math.max(IMAGEN.letra, Math.round(innerRadius * 0.12));
        const base = texto ? y + tamanoCifra * 0.2 : y + tamanoCifra * 0.35;
        const { ctx } = grafico;
        ctx.save();
        ctx.textAlign = "center";
        ctx.textBaseline = "alphabetic";
        ctx.fillStyle = TINTA;
        ctx.font = `700 ${tamanoCifra}px ${familia}`;
        ctx.fillText(cifra, x, base);
        if (texto) {
          ctx.textBaseline = "top";
          ctx.fillStyle = TINTA_SECUNDARIA;
          ctx.font = `${tamanoTexto}px ${familia}`;
          ctx.fillText(texto, x, base + tamanoTexto * 0.6);
        }
        ctx.restore();
      },
    };
  }

  // La leyenda de la dona con sus valores, como la que la pagina escribe en HTML:
  // "Cobertura total: 4 (80 %)".
  function leyendaDeDona(definicion, colores) {
    return {
      display: true,
      position: "bottom",
      labels: {
        usePointStyle: true,
        boxWidth: 10,
        boxHeight: 10,
        padding: 18,
        color: TINTA,
        font: { size: IMAGEN.letraSubtitulo },
        generateLabels: () =>
          definicion.etiquetas.map((etiqueta, indice) => {
            const valor = formato(definicion.decimales || 0).format(definicion.valores[indice] ?? 0);
            const porcentaje = definicion.porcentajes?.[indice];
            return {
              text: porcentaje === undefined ? `${etiqueta}: ${valor}` : `${etiqueta}: ${valor} (${porcentaje} %)`,
              fillStyle: colores[indice],
              strokeStyle: colores[indice],
              lineWidth: 0,
              pointStyle: "circle",
              hidden: false,
              index: indice,
            };
          }),
      },
    };
  }

  function rellenoDe(opciones) {
    const relleno = opciones.layout?.padding ?? 0;
    const lado = (nombre) => (typeof relleno === "number" ? relleno : relleno[nombre] ?? 0);
    return {
      top: lado("top") + 8,
      right: lado("right") + IMAGEN.margen,
      bottom: lado("bottom") + IMAGEN.margen,
      left: lado("left") + IMAGEN.margen,
    };
  }

  function configuracionParaInforme({ grafico, definicion }, { titulo, descripcion, contexto }, centro) {
    const config = CONFIGURACIONES[definicion.tipo](definicion, paleta());
    const opciones = config.options;
    const dona = definicion.tipo === "dona";
    const ancho = dona ? IMAGEN.anchoDona : IMAGEN.ancho;
    const familia = window.Chart.defaults.font.family;

    const subtitulo = [
      ...(descripcion ? renglones(descripcion, ancho - 2 * IMAGEN.margen, `${IMAGEN.letraSubtitulo}px ${familia}`) : []),
      ...(contexto ? [contexto] : []),
    ];
    const altoDelTitulo = titulo ? IMAGEN.letraTitulo * 1.2 + IMAGEN.margen - 8 + 6 : 0;
    const altoDelSubtitulo = subtitulo.length
      ? subtitulo.length * IMAGEN.letraSubtitulo * IMAGEN.renglonSubtitulo + 24
      : 0;
    const alto = Math.ceil(altoDelTitulo + altoDelSubtitulo + altoDelTrazado(definicion) + IMAGEN.margen + 8);

    Object.assign(opciones, {
      responsive: false,
      maintainAspectRatio: false,
      animation: false,
      events: [],
      devicePixelRatio: IMAGEN.escala,
    });
    opciones.layout = { padding: rellenoDe(opciones) };
    opciones.plugins.tooltip = { enabled: false };
    opciones.plugins.title = {
      display: Boolean(titulo),
      text: titulo,
      align: "start",
      color: TINTA,
      font: { size: IMAGEN.letraTitulo, weight: "600" },
      padding: { top: IMAGEN.margen - 8, bottom: 6 },
    };
    opciones.plugins.subtitle = {
      display: subtitulo.length > 0,
      text: subtitulo,
      align: "start",
      color: TINTA_SECUNDARIA,
      font: { size: IMAGEN.letraSubtitulo, lineHeight: IMAGEN.renglonSubtitulo },
      padding: { bottom: 24 },
    };
    // Letra fija: en pantalla baja un punto en los telefonos, la imagen no.
    Object.values(opciones.scales || {}).forEach((escala) => {
      escala.ticks = { ...escala.ticks, font: { size: IMAGEN.letra } };
    });
    if (opciones.plugins.legend?.display) {
      opciones.plugins.legend.labels = { ...opciones.plugins.legend.labels, font: { size: IMAGEN.letra } };
    }

    if (dona) {
      opciones.plugins.legend = leyendaDeDona(definicion, config.data.datasets[0].backgroundColor);
      config.plugins.push(pluginDeCentro(centro.cifra, centro.texto));
    }
    // Lo exportado es lo que se ve: las series ocultas desde la leyenda no salen.
    config.data.datasets.forEach((dataset, indice) => {
      if (!grafico.isDatasetVisible(indice)) dataset.hidden = true;
    });

    return { config, ancho, alto };
  }

  function imagen(canvas, metadatos = {}) {
    const registro = instancias.get(canvas);
    if (!registro) return null;
    let copia = null;
    try {
      const { config, ancho, alto } = configuracionParaInforme(registro, metadatos, {
        cifra: canvas.dataset.centroCifra,
        texto: canvas.dataset.centroTexto,
      });
      // Con `responsive: false` Chart.js dibuja en el acto, aunque el lienzo no este en la pagina.
      const lienzo = document.createElement("canvas");
      lienzo.width = ancho;
      lienzo.height = alto;
      copia = new window.Chart(lienzo, config);
      return copia.toBase64Image("image/png", 1);
    } catch (error) {
      // Mejor la imagen de la pantalla que ninguna.
      console.error("No se pudo armar la imagen para el informe", error);
      return registro.grafico.toBase64Image("image/png", 1);
    } finally {
      copia?.destroy();
    }
  }

  // Al cruzar el ancho de un telefono, la tipografia cambia: se vuelve a dibujar todo.
  let eraAngosto = window.innerWidth < 640;
  window.addEventListener("resize", () => {
    const angosto = window.innerWidth < 640;
    if (angosto === eraAngosto || !window.Chart) return;
    eraAngosto = angosto;
    aplicarTipografia();
    instancias.forEach(({ grafico }) => grafico.update("none"));
  });

  window.RescueSync = window.RescueSync || {};
  window.RescueSync.graficos = { iniciar, destruir, imagen };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => iniciar());
  } else {
    iniciar();
  }
})();
