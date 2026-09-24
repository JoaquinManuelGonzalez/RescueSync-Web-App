"""Paginacion de los listados.

Todo listado del sistema se pagina en la base, no en la plantilla: la consulta trae solo la
pagina pedida y un conteo del total. Los servicios arman la consulta con sus filtros y llaman a
`paginar()`; la ruta lee `?pagina=` y `?por_pagina=` con `parametros_de_paginacion()`.

    pagina, por_pagina = parametros_de_paginacion()
    resultado = servicios.paginar_usuarios(..., pagina=pagina, por_pagina=por_pagina)

Un cliente JSON recibe los elementos y, aparte, `resultado.a_diccionario()`; la plantilla
recibe el objeto y lo dibuja con el macro `paginacion()` de `componentes/tablas.html`.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from flask import request, url_for
from sqlalchemy import Select, func, select

from app.core.interfaz.formularios import parametro_entero
from app.extensiones import db

POR_PAGINA_POR_DEFECTO = 20
POR_PAGINA_MAXIMO = 100


@dataclass(frozen=True)
class Pagina[T]:
    """Una pagina de resultados, con lo necesario para dibujar la navegacion."""

    elementos: list[T]
    numero: int
    por_pagina: int
    total: int

    @property
    def paginas(self) -> int:
        return max(1, math.ceil(self.total / self.por_pagina))

    @property
    def tiene_anterior(self) -> bool:
        return self.numero > 1

    @property
    def tiene_siguiente(self) -> bool:
        return self.numero < self.paginas

    @property
    def desde(self) -> int:
        """Posicion (desde 1) del primer elemento de la pagina; 0 si no hay ninguno."""
        return 0 if self.total == 0 else (self.numero - 1) * self.por_pagina + 1

    @property
    def hasta(self) -> int:
        return min(self.numero * self.por_pagina, self.total)

    def ventana(self, alrededor: int = 1) -> list[int | None]:
        """Numeros de pagina a mostrar: la primera, la ultima y las vecinas de la actual.

        `None` marca un salto ("…"). Con 10 paginas y la actual en 5: 1 … 4 5 6 … 10.
        """
        visibles = {1, self.paginas} | {
            numero
            for numero in range(self.numero - alrededor, self.numero + alrededor + 1)
            if 1 <= numero <= self.paginas
        }
        ventana: list[int | None] = []
        anterior = 0
        for numero in sorted(visibles):
            if numero - anterior > 1:
                ventana.append(None)
            ventana.append(numero)
            anterior = numero
        return ventana

    def mapear[U](self, funcion: Callable[[T], U]) -> Pagina[U]:
        """La misma pagina con cada elemento transformado (por ejemplo, a diccionario)."""
        return Pagina(
            [funcion(uno) for uno in self.elementos], self.numero, self.por_pagina, self.total
        )

    def a_diccionario(self) -> dict[str, Any]:
        """Metadatos para la respuesta JSON, sin los elementos."""
        return {
            "pagina": self.numero,
            "por_pagina": self.por_pagina,
            "total": self.total,
            "paginas": self.paginas,
        }


def paginar(consulta: Select, pagina: int, por_pagina: int) -> Pagina[Any]:
    """Ejecuta `consulta` trayendo solo la pagina pedida.

    Una pagina fuera de rango (por ejemplo, despues de filtrar) se lleva a la ultima que
    existe, en vez de mostrar un listado vacio con resultados que si existen.
    """
    total = db.session.execute(
        select(func.count()).select_from(consulta.order_by(None).subquery())
    ).scalar_one()
    paginas = max(1, math.ceil(total / por_pagina))
    numero = min(max(1, pagina), paginas)
    elementos = list(
        db.session.execute(consulta.limit(por_pagina).offset((numero - 1) * por_pagina)).scalars()
    )
    return Pagina(elementos, numero, por_pagina, total)


def parametros_de_paginacion() -> tuple[int, int]:
    """Lee `?pagina=` y `?por_pagina=` de la URL, con valores por defecto y tope."""
    pagina = parametro_entero("pagina") or 1
    por_pagina = parametro_entero("por_pagina") or POR_PAGINA_POR_DEFECTO
    return max(1, pagina), min(max(1, por_pagina), POR_PAGINA_MAXIMO)


def url_de_pagina(numero: int) -> str:
    """URL de la pantalla actual en otra pagina, conservando los filtros de la query string."""
    argumentos = request.args.to_dict()
    argumentos["pagina"] = str(numero)
    return url_for(str(request.endpoint), **(request.view_args or {}), **argumentos)
