/*
 * Filtros del panel de auditoria. Lo incluye plantillas/indicadores/base.html.
 *
 * 1. Filtro de periodo: adelanta en el navegador la regla que valida el servidor
 *    (app/modulos/indicadores/formularios.py), para avisar sin recargar la pagina.
 *
 *      form[data-filtro-periodo]   el formulario; `data-mensaje-invertido` trae el texto del error
 *      input[name="desde"] / input[name="hasta"]  las dos fechas, en formato ISO (aaaa-mm-dd)
 *
 * 2. Filtros de una seccion (como la gravedad): un enlace dentro de [data-filtro-de-seccion]
 *    trae la misma pantalla con el filtro aplicado y reemplaza solo las regiones
 *    [data-panel-actualizable="nombre"], sin recargar. Los graficos se vuelven a dibujar con
 *    graficos.js y la URL cambia, asi se puede compartir. Si algo falla, se sigue el enlace.
 *
 * Sin JavaScript todo funciona igual: los errores los muestra el servidor y los enlaces recargan.
 */
(() => {
  "use strict";

  function camposDe(formulario) {
    return {
      desde: formulario.querySelector('input[name="desde"]'),
      hasta: formulario.querySelector('input[name="hasta"]'),
    };
  }

  // Las fechas ISO se comparan bien como texto.
  function estaInvertido({ desde, hasta }) {
    return Boolean(desde.value && hasta.value && desde.value > hasta.value);
  }

  // Los ids son los mismos que usa el macro `campo()`, asi el error del navegador reemplaza al
  // del servidor en vez de sumarse.
  function idDeError(control) {
    return `${control.id}-error`;
  }

  function describir(control, id, describe) {
    const ids = new Set((control.getAttribute("aria-describedby") || "").split(" ").filter(Boolean));
    if (describe) ids.add(id);
    else ids.delete(id);
    if (ids.size) control.setAttribute("aria-describedby", [...ids].join(" "));
    else control.removeAttribute("aria-describedby");
  }

  function mostrarError(control, mensaje) {
    const id = idDeError(control);
    let contenedor = document.getElementById(id);
    if (!contenedor) {
      contenedor = document.createElement("div");
      contenedor.id = id;
      control.closest(".campo")?.append(contenedor);
    }

    const parrafo = document.createElement("p");
    parrafo.className = "campo-error";
    parrafo.setAttribute("role", "alert");
    parrafo.textContent = mensaje;
    contenedor.replaceChildren(parrafo);

    control.classList.add("campo-control-invalido");
    control.setAttribute("aria-invalid", "true");
    describir(control, id, true);
  }

  function limpiarError(control) {
    const id = idDeError(control);
    document.getElementById(id)?.remove();
    control.classList.remove("campo-control-invalido");
    control.removeAttribute("aria-invalid");
    describir(control, id, false);
  }

  // Los calendarios del navegador ya no ofrecen un "desde" posterior al "hasta" ni al reves.
  // El tope de "hasta" (hoy) lo pone el servidor y no se toca.
  function sincronizarLimites({ desde, hasta }) {
    hasta.min = desde.value || "";
    desde.max = hasta.value || hasta.max;
  }

  function inicializar(formulario) {
    const campos = camposDe(formulario);
    if (!campos.desde || !campos.hasta) return;
    const mensajeInvertido = formulario.dataset.mensajeInvertido;

    sincronizarLimites(campos);
    [campos.desde, campos.hasta].forEach((control) => {
      control.addEventListener("change", () => {
        limpiarError(control);
        // El error de periodo invertido se muestra en "desde", pero se corrige desde cualquiera
        // de las dos fechas.
        const errorDeDesde = document.getElementById(idDeError(campos.desde));
        if (errorDeDesde?.textContent.trim() === mensajeInvertido && !estaInvertido(campos)) {
          limpiarError(campos.desde);
        }
        sincronizarLimites(campos);
      });
    });
  }

  // Se escucha en captura sobre `document` para correr antes que el `submit` de interfaz.js
  // (form[data-envio-con-carga]): si el periodo es invalido, el envio se cancela antes de que
  // el boton quede deshabilitado con su spinner.
  document.addEventListener(
    "submit",
    (evento) => {
      const formulario = evento.target;
      if (!(formulario instanceof HTMLFormElement) || !formulario.matches("[data-filtro-periodo]")) {
        return;
      }

      const campos = camposDe(formulario);
      if (campos.desde && campos.hasta && estaInvertido(campos)) {
        evento.preventDefault();
        mostrarError(campos.desde, formulario.dataset.mensajeInvertido);
        campos.desde.focus();
      }
    },
    true,
  );

  // --- Filtros de seccion sin recargar ---------------------------------------------

  let solicitudEnCurso = null;

  function regionesDe(raiz) {
    return new Map(
      [...raiz.querySelectorAll("[data-panel-actualizable]")].map((region) => [
        region.dataset.panelActualizable,
        region,
      ]),
    );
  }

  async function aplicarFiltroDeSeccion(enlace) {
    const url = enlace.href;
    const actuales = regionesDe(document);
    solicitudEnCurso?.abort();
    solicitudEnCurso = new AbortController();
    actuales.forEach((region) => region.setAttribute("aria-busy", "true"));

    try {
      const respuesta = await fetch(url, {
        headers: { Accept: "text/html" },
        credentials: "same-origin",
        signal: solicitudEnCurso.signal,
      });
      // Un 400 trae la pantalla con el error del filtro: se muestra igual. Una redireccion (la
      // sesion vencio) o cualquier otro error se resuelve navegando.
      if (respuesta.redirected || (!respuesta.ok && respuesta.status !== 400)) {
        throw new Error(`Respuesta inesperada: ${respuesta.status}`);
      }
      const pagina = new DOMParser().parseFromString(await respuesta.text(), "text/html");
      const nuevas = regionesDe(pagina);
      if ([...actuales.keys()].some((nombre) => !nuevas.has(nombre))) {
        throw new Error("La pantalla nueva no tiene las mismas regiones.");
      }

      const graficos = window.RescueSync?.graficos;
      actuales.forEach((region, nombre) => {
        graficos?.destruir(region);
        const nueva = document.importNode(nuevas.get(nombre), true);
        region.replaceWith(nueva);
        graficos?.iniciar(nueva);
      });
      document.title = pagina.title;
      history.replaceState(null, "", url);
      // El enlace elegido ya no existe: el foco pasa a su reemplazo, el que quedo marcado.
      document.querySelector("[data-filtro-de-seccion] [aria-current]")?.focus();
    } catch (error) {
      if (error.name === "AbortError") return;
      window.location.assign(url);
    } finally {
      actuales.forEach((region) => region.removeAttribute("aria-busy"));
    }
  }

  document.addEventListener("click", (evento) => {
    const enlace = evento.target.closest?.("[data-filtro-de-seccion] a[href]");
    // Con una tecla modificadora la persona quiere abrir el enlace en otra pestaña.
    if (
      !enlace ||
      evento.defaultPrevented ||
      evento.button !== 0 ||
      evento.metaKey ||
      evento.ctrlKey ||
      evento.shiftKey ||
      evento.altKey
    ) {
      return;
    }
    evento.preventDefault();
    if (enlace.hasAttribute("aria-current")) return;
    aplicarFiltroDeSeccion(enlace);
  });

  function iniciar() {
    document.querySelectorAll("form[data-filtro-periodo]").forEach(inicializar);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
