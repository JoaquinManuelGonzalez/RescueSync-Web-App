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
 *   decimales      (opcional) decimales de los valores: 1 para "5,0 días"
 *   detalles       (opcional) una linea extra del tooltip por valor, o null
 *   porcentajes    (opcional, dona) el porcentaje de cada porcion, ya calculado por el servidor
 *   orientacion    (opcional, barras) "horizontal": para etiquetas largas (ONGs, rubros, etapas)
 *   mostrarValores (opcional, barras) escribe el valor al final de cada barra
 *   maximo         (opcional, barras) tope del eje de valores: 100 para porcentajes
 *   marcadores     (opcional, barras) {nombre, valores}: una marca de referencia por barra sobre el
 *                  mismo eje (el plazo objetivo de cada gravedad)
 *   sinDato        (opcional) texto que se escribe donde el valor es null ("Sin ocurrencias")
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
 * `imagen(canvas)`, que devuelve el grafico como PNG (data URL) para descargarlo.
 */
(() => {
  "use strict";

  const instancias = new Map(); // canvas -> Chart
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

  function ejeDeValores({ decimales = 0, maximo, porcentaje = false } = {}) {
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
        callback: (valor) => `${formato(Number.isInteger(valor) ? 0 : decimales || 1).format(valor)}${porcentaje ? " %" : ""}`,
      },
    };
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
              ctx.textAlign = "center";
              ctx.textBaseline = "bottom";
              ctx.fillText(definicion.sinDato, posicion, chartArea.bottom - 8);
            }
            return;
          }
          if (!definicion.mostrarValores) return;
          ctx.fillStyle = TINTA;
          ctx.font = `600 ${tamano}px ${familia}`;
          const texto = valorCorto(valor, definicion.unidad, definicion.decimales || 0);
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
            const marca = grafico.data.datasets.length > 1 ? grafico.getDatasetMeta(1).data[indice] : null;
            const tope = marca && !marca.skip ? Math.min(elemento.y, marca.y - 3) : elemento.y;
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

  function configuracionDeBarras(definicion, colores) {
    if (definicion.series) return configuracionDeApiladas(definicion, colores);

    const horizontal = definicion.orientacion === "horizontal";
    const decimales = definicion.decimales || 0;
    const coloresDelGrafico = definicion.tonos.map((tono) => colores[tono] || colores.primario);
    const opciones = opcionesComunes(definicion);
    opciones.indexAxis = horizontal ? "y" : "x";
    opciones.plugins.tooltip.callbacks.label = (contexto) => {
      const valor = horizontal ? contexto.parsed.x : contexto.parsed.y;
      if (contexto.datasetIndex === 1) return `${definicion.marcadores.nombre}: ${conUnidad(valor, definicion.unidad)}`;
      return conUnidad(valor, definicion.unidad, decimales);
    };

    const valores = ejeDeValores({ decimales, maximo: definicion.maximo, porcentaje: definicion.unidad?.[1] === "%" });
    // Con un tope fijo (100 %) la barra llena llega al borde: se deja lugar para su etiqueta.
    if (definicion.maximo && definicion.mostrarValores) {
      opciones.layout.padding = horizontal ? { top: 4, right: 44 } : { top: 22, right: 8 };
    }
    opciones.scales = horizontal
      ? { y: ejeDeEtiquetas(definicion, true), x: valores }
      : { x: ejeDeEtiquetas(definicion, false), y: valores };

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
            borderWidth: 3,
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
    instancias.set(canvas, new window.Chart(canvas, configurar(definicion, paleta())));
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
      instancias.get(canvas)?.destroy();
      instancias.delete(canvas);
    });
  }

  function imagen(canvas) {
    return instancias.get(canvas)?.toBase64Image("image/png", 1) ?? null;
  }

  // Al cruzar el ancho de un telefono, la tipografia cambia: se vuelve a dibujar todo.
  let eraAngosto = window.innerWidth < 640;
  window.addEventListener("resize", () => {
    const angosto = window.innerWidth < 640;
    if (angosto === eraAngosto || !window.Chart) return;
    eraAngosto = angosto;
    aplicarTipografia();
    instancias.forEach((grafico) => grafico.update("none"));
  });

  window.RescueSync = window.RescueSync || {};
  window.RescueSync.graficos = { iniciar, destruir, imagen };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => iniciar());
  } else {
    iniciar();
  }
})();
