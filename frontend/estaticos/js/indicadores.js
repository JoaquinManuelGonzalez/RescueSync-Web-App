/*
 * Filtros del panel de auditoria. Lo incluye plantillas/indicadores/base.html.
 *
 * 1. Filtro de periodo: adelanta en el navegador la regla que valida el servidor
 *    (app/modulos/indicadores/formularios.py), para avisar sin recargar la pagina.
 *
 *      form[data-filtro-periodo]   el formulario; `data-mensaje-invertido` trae el texto del error
 *      input[name="desde"] / input[name="hasta"]  las dos fechas, en formato ISO (aaaa-mm-dd)
 *
 * 2. Filtros de una seccion (como la gravedad o el orden del ranking): un enlace dentro de
 *    [data-filtro-de-seccion] trae la misma pantalla con el filtro aplicado y reemplaza solo las
 *    regiones [data-panel-actualizable="nombre"], sin recargar. Los graficos se vuelven a dibujar
 *    con graficos.js y la URL cambia, asi se puede compartir. Si algo falla, se sigue el enlace.
 *
 * 3. Regiones de carga diferida: [data-carga-diferida="url"] se completa con el fragmento HTML
 *    de esa URL apenas se muestra la pantalla (lo usa la seccion "Proceso", que consulta Bonita).
 *    El boton [data-reintentar] de un aviso de error vuelve a pedir la region en la que esta.
 *
 * 4. Menu de exportacion (details[data-exportar-menu]): se cierra al hacer clic afuera, al
 *    elegir una descarga o con Escape. La opcion [data-exportar-imagen="id del canvas"] (oculta
 *    sin JavaScript) descarga el grafico como PNG con el nombre de `data-nombre-archivo`. La
 *    imagen la arma graficos.js con `data-titulo`, `data-descripcion` y `data-contexto` (el
 *    periodo) como encabezado.
 *
 * 5. Pestañas: en pantallas angostas la barra se desplaza de costado; al cargar, la pestaña
 *    activa queda a la vista.
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
        habilitarImagenes(nueva);
        cargarRegionesDiferidas(nueva);
      });
      document.title = pagina.title;
      history.replaceState(null, "", url);
      // El enlace elegido ya no existe: el foco pasa a su reemplazo (el que lleva a la misma URL)
      // o, si no esta, al que quedo marcado.
      const enlaces = [...document.querySelectorAll("[data-filtro-de-seccion] a[href]")];
      (enlaces.find((candidato) => candidato.href === url) ||
        document.querySelector("[data-filtro-de-seccion] [aria-current]"))?.focus();
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

  // --- Regiones de carga diferida ---------------------------------------------------

  function avisoDeFalla(region) {
    const mensaje = region.dataset.mensajeError || "No se pudieron obtener los datos.";
    const aviso = document.createElement("div");
    aviso.className = "tarjeta seccion-error";
    aviso.setAttribute("role", "alert");
    const texto = document.createElement("p");
    texto.className = "seccion-error-mensaje flex-1";
    texto.textContent = mensaje;
    const boton = document.createElement("a");
    boton.className = "btn btn-secundario";
    boton.href = window.location.href;
    boton.dataset.reintentar = "";
    boton.textContent = "Reintentar";
    aviso.append(texto, boton);
    return aviso;
  }

  async function cargarRegion(region) {
    const url = region.dataset.cargaDiferida;
    if (!url || region.getAttribute("aria-busy") === "true") return;
    const graficos = window.RescueSync?.graficos;
    region.setAttribute("aria-busy", "true");
    try {
      const respuesta = await fetch(url, { headers: { Accept: "text/html" }, credentials: "same-origin" });
      // Una redireccion es la sesion vencida: se navega para que el servidor la resuelva.
      if (respuesta.redirected) {
        window.location.assign(respuesta.url);
        return;
      }
      if (!respuesta.ok) throw new Error(`Respuesta inesperada: ${respuesta.status}`);
      const html = await respuesta.text();
      graficos?.destruir(region);
      region.innerHTML = html;
      graficos?.iniciar(region);
      habilitarImagenes(region);
    } catch (error) {
      graficos?.destruir(region);
      region.replaceChildren(avisoDeFalla(region));
    } finally {
      region.removeAttribute("aria-busy");
    }
  }

  function cargarRegionesDiferidas(raiz = document) {
    const regiones = raiz.matches?.("[data-carga-diferida]")
      ? [raiz]
      : [...raiz.querySelectorAll("[data-carga-diferida]")];
    regiones.forEach(cargarRegion);
  }

  document.addEventListener("click", (evento) => {
    const boton = evento.target.closest?.("[data-reintentar]");
    const region = boton?.closest("[data-carga-diferida]");
    if (!region || evento.button !== 0 || evento.metaKey || evento.ctrlKey) return;
    evento.preventDefault();
    cargarRegion(region);
  });

  // --- Menu de exportacion ------------------------------------------------------------

  document.addEventListener("click", (evento) => {
    document.querySelectorAll("details[data-exportar-menu][open]").forEach((menu) => {
      const descarga = evento.target.closest?.(".exportar-opcion");
      if (!menu.contains(evento.target) || (descarga && menu.contains(descarga))) {
        menu.removeAttribute("open");
      }
    });
  });

  document.addEventListener("keydown", (evento) => {
    if (evento.key !== "Escape") return;
    document.querySelectorAll("details[data-exportar-menu][open]").forEach((menu) => {
      menu.removeAttribute("open");
      menu.querySelector("summary")?.focus();
    });
  });

  // --- Descarga del grafico como imagen ------------------------------------------------

  function habilitarImagenes(raiz = document) {
    if (!window.RescueSync?.graficos?.imagen) return;
    raiz.querySelectorAll("[data-opcion-imagen]").forEach((opcion) => {
      opcion.hidden = false;
    });
  }

  document.addEventListener("click", (evento) => {
    const boton = evento.target.closest?.("[data-exportar-imagen]");
    if (!boton) return;
    const canvas = document.getElementById(boton.dataset.exportarImagen);
    const { titulo, descripcion, contexto } = boton.dataset;
    const datos = canvas && window.RescueSync?.graficos?.imagen(canvas, { titulo, descripcion, contexto });
    boton.closest("details")?.removeAttribute("open");
    if (!datos) return;
    const enlace = document.createElement("a");
    enlace.href = datos;
    enlace.download = boton.dataset.nombreArchivo || "grafico.png";
    document.body.append(enlace);
    enlace.click();
    enlace.remove();
  });

  // --- Pestañas -------------------------------------------------------------------------

  // Sin mover la pagina: solo la barra de pestañas se desplaza hasta centrar la activa.
  function mostrarPestanaActiva() {
    const barra = document.querySelector(".panel-pestanas");
    const activa = barra?.querySelector("[aria-current='page']");
    if (!barra || !activa || barra.scrollWidth <= barra.clientWidth) return;
    const desplazamiento = activa.getBoundingClientRect().left - barra.getBoundingClientRect().left;
    barra.scrollLeft += desplazamiento - (barra.clientWidth - activa.offsetWidth) / 2;
  }

  function iniciar() {
    document.querySelectorAll("form[data-filtro-periodo]").forEach(inicializar);
    mostrarPestanaActiva();
    cargarRegionesDiferidas();
    // graficos.js carga despues (defer, mas abajo en la pagina): se espera a que termine.
    window.addEventListener("load", () => habilitarImagenes());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
