/*
 * Filas repetibles de la zona de cobertura de una organizacion.
 *
 * Lo incluye el macro `campos_de_zonas` de plantillas/organizaciones/componentes.html. El
 * formulario funciona igual sin JavaScript (se envia la fila que ya viene en la pantalla); esto
 * solo agrega y quita filas.
 *
 *   [data-zonas-de-cobertura]   contenedor
 *   [data-zonas-filas]          donde viven las filas
 *   template[data-zonas-plantilla]  fila modelo, con "__indice__" en nombres e ids
 *   [data-zona-agregar] / [data-zona-quitar]  botones
 *   [data-cobertura-nacional]   casilla "Opera en todo el país"; oculta [data-zonas-detalle]
 *
 * Los indices no se renumeran al quitar una fila: WTForms acepta indices salteados
 * (zonas-0-..., zonas-3-...), asi que alcanza con usar siempre uno que no este en uso.
 */
(() => {
  "use strict";

  const PATRON_INDICE = /^zonas-(\d+)-/;

  function mayorIndiceEnUso(filas) {
    let mayor = -1;
    filas.querySelectorAll("[name]").forEach((control) => {
      const coincidencia = PATRON_INDICE.exec(control.name);
      if (coincidencia) {
        mayor = Math.max(mayor, Number(coincidencia[1]));
      }
    });
    return mayor;
  }

  function inicializar(contenedor) {
    const filas = contenedor.querySelector("[data-zonas-filas]");
    const plantilla = contenedor.querySelector("template[data-zonas-plantilla]");
    if (!filas || !plantilla) {
      return;
    }
    let siguiente = mayorIndiceEnUso(filas) + 1;

    // "Opera en todo el país" reemplaza a las zonas: mientras este marcada, las filas se ocultan.
    // No se borran, asi desmarcarla por error no hace perder lo que ya estaba cargado.
    const nacional = contenedor.querySelector("[data-cobertura-nacional]");
    const detalle = contenedor.querySelector("[data-zonas-detalle]");
    if (nacional && detalle) {
      const sincronizar = () => {
        detalle.hidden = nacional.checked;
      };
      nacional.addEventListener("change", sincronizar);
      sincronizar();
    }

    function agregarFila() {
      const html = plantilla.innerHTML.replaceAll("__indice__", String(siguiente));
      siguiente += 1;
      filas.insertAdjacentHTML("beforeend", html);
      const nueva = filas.lastElementChild;
      const primerControl = nueva && nueva.querySelector("select, input");
      if (primerControl) {
        primerControl.focus();
      }
    }

    contenedor.addEventListener("click", (evento) => {
      if (evento.target.closest("[data-zona-agregar]")) {
        agregarFila();
        return;
      }
      const quitar = evento.target.closest("[data-zona-quitar]");
      if (!quitar) {
        return;
      }
      quitar.closest("[data-zona-fila]").remove();
      // Siempre queda al menos una fila, aunque sea vacia, para poder volver a cargar.
      if (!filas.querySelector("[data-zona-fila]")) {
        agregarFila();
      }
    });
  }

  function iniciar() {
    document.querySelectorAll("[data-zonas-de-cobertura]").forEach(inicializar);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
