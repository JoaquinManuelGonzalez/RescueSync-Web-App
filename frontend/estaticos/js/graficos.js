/*
 * Graficos del panel de auditoria, dibujados con Chart.js (estaticos/js/vendor/, ver ADR-010).
 *
 * Los arma el macro `tarjeta_grafico()` de plantillas/componentes/indicadores.html. Cada grafico
 * es un [data-grafico-contenedor] con su <canvas> (dentro de [data-grafico-lienzo], oculto), una
 * tabla con los mismos datos ([data-grafico-respaldo]) y su definicion en
 * <script type="application/json" data-grafico>:
 *
 *   tipo         "barras" o "dona"
 *   etiquetas    texto de cada barra o porcion
 *   valores      numero de cada una
 *   tonos        color de cada una: primario, exito, advertencia, info, neutro o tenue
 *   unidad       [singular, plural], para los tooltips: "3 emergencias"
 *   detalles     (opcional) una linea extra del tooltip por valor, o null
 *   porcentajes  (opcional, dona) el porcentaje de cada porcion, ya calculado por el servidor
 *
 * Al dibujar, el lienzo aparece y la tabla queda solo para lectores de pantalla. Sin JavaScript,
 * o si Chart.js no cargo, la tabla sigue a la vista.
 *
 * Expone `window.RescueSync.graficos` con `iniciar(raiz)` y `destruir(raiz)`, para volver a
 * dibujar cuando una pantalla reemplaza parte de la pagina (lo usa indicadores.js).
 */
(() => {
  "use strict";

  const instancias = new Map(); // canvas -> Chart
  const numero = new Intl.NumberFormat("es-AR");
  const sinMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function variableCss(nombre, respaldo) {
    return getComputedStyle(document.documentElement).getPropertyValue(nombre).trim() || respaldo;
  }

  // Los colores de marca salen del tema de Tailwind (src/input.css). El resto son los de la
  // paleta de Tailwind en hexadecimal, que es lo que Chart.js sabe aclarar al pasar el mouse.
  function paleta() {
    return {
      primario: variableCss("--color-primario", "#a00d27"),
      exito: variableCss("--color-exito", "#2e9b5b"),
      advertencia: "#f59e0b",
      info: "#3b82f6",
      neutro: "#9ca3af",
      tenue: "#d1d5db",
    };
  }

  function conUnidad(valor, [singular, plural] = ["", ""]) {
    return `${numero.format(valor)} ${valor === 1 ? singular : plural}`.trim();
  }

  function opcionesComunes(definicion) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: sinMovimiento ? false : { duration: 700, easing: "easeOutQuart" },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#111827",
          padding: 10,
          cornerRadius: 8,
          displayColors: true,
          boxPadding: 4,
          callbacks: {
            afterLabel: (contexto) => definicion.detalles?.[contexto.dataIndex] || "",
          },
        },
      },
    };
  }

  function configuracionDeBarras(definicion, colores) {
    const opciones = opcionesComunes(definicion);
    opciones.plugins.tooltip.callbacks.label = (contexto) => conUnidad(contexto.parsed.y, definicion.unidad);
    opciones.scales = {
      x: { grid: { display: false }, border: { display: false } },
      y: {
        beginAtZero: true,
        border: { display: false },
        grid: { color: "#f3f4f6" },
        ticks: { precision: 0, callback: (valor) => numero.format(valor) },
      },
    };
    return {
      type: "bar",
      data: {
        labels: definicion.etiquetas,
        datasets: [
          {
            data: definicion.valores,
            backgroundColor: colores,
            hoverBackgroundColor: colores,
            borderRadius: 6,
            maxBarThickness: 56,
          },
        ],
      },
      options: opciones,
    };
  }

  function configuracionDeDona(definicion, colores) {
    const opciones = opcionesComunes(definicion);
    opciones.cutout = "72%";
    opciones.plugins.tooltip.callbacks.label = (contexto) => {
      const porcentaje = definicion.porcentajes?.[contexto.dataIndex];
      const cantidad = conUnidad(contexto.parsed, definicion.unidad);
      return porcentaje === undefined ? cantidad : `${cantidad} (${porcentaje} %)`;
    };
    return {
      type: "doughnut",
      data: {
        labels: definicion.etiquetas,
        datasets: [
          {
            data: definicion.valores,
            backgroundColor: colores,
            hoverBackgroundColor: colores,
            borderColor: variableCss("--color-superficie", "#ffffff"),
            borderWidth: 3,
            hoverOffset: 6,
          },
        ],
      },
      options: opciones,
    };
  }

  const CONFIGURACIONES = { barras: configuracionDeBarras, dona: configuracionDeDona };

  function dibujar(contenedor) {
    const fuente = contenedor.querySelector("script[data-grafico]");
    const lienzo = contenedor.querySelector("[data-grafico-lienzo]");
    const canvas = lienzo?.querySelector("canvas");
    if (!fuente || !canvas || instancias.has(canvas)) return;

    const definicion = JSON.parse(fuente.textContent);
    const configurar = CONFIGURACIONES[definicion.tipo];
    if (!configurar) return;

    const colores = paleta();
    const coloresDelGrafico = definicion.tonos.map((tono) => colores[tono] || colores.primario);

    // El lienzo tiene que estar visible antes de crear el grafico, para que tome su tamaño.
    lienzo.hidden = false;
    instancias.set(canvas, new window.Chart(canvas, configurar(definicion, coloresDelGrafico)));
    contenedor.querySelector("[data-grafico-respaldo]")?.classList.add("sr-only");
  }

  function iniciar(raiz = document) {
    if (!window.Chart) return;
    const estilo = getComputedStyle(document.body);
    window.Chart.defaults.font.family = estilo.fontFamily;
    window.Chart.defaults.color = "#6b7280";
    raiz.querySelectorAll("[data-grafico-contenedor]").forEach(dibujar);
  }

  function destruir(raiz = document) {
    raiz.querySelectorAll("[data-grafico-contenedor] canvas").forEach((canvas) => {
      instancias.get(canvas)?.destroy();
      instancias.delete(canvas);
    });
  }

  window.RescueSync = window.RescueSync || {};
  window.RescueSync.graficos = { iniciar, destruir };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => iniciar());
  } else {
    iniciar();
  }
})();
