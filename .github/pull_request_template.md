## HU que resuelve

<!-- Ejemplo: HU-07 — Carga de ofertas de ayuda -->

## Qué cambia y por qué

<!-- Descripcion breve del cambio y la motivacion / problema que resuelve. -->

## Cómo probarlo

<!-- Pasos concretos para que quien revisa pueda verificar el cambio localmente. -->

1.
2.
3.

## Checklist

- [ ] Desde `backend/`: `uv run ruff format --check .`, `uv run ruff check .` y
      `uv run pytest` pasan sin errores.
- [ ] Si se agregó una migración, se probó `flask db upgrade` y `downgrade` contra PostgreSQL. Si
      transforma datos, se probó con una copia de una base con datos.
- [ ] Las tablas y foráneas nuevas usan UUID (`Uuid`, `default=nuevo_id`), las rutas con ids
      `<uuid:...>` y los formularios `CampoId` (`docs/adr/ADR-011-claves-uuid.md`).
- [ ] Si cambia lo que la web intercambia con Bonita (contratos de tareas, ofertas consolidadas,
      `POST /ofertas/evaluaciones`), se coordinó con el proceso de Bonita y, si llega a la API del
      Sistema Nacional, con su repositorio. Un cambio incompatible lleva `BREAKING CHANGE:` en el
      commit y se mergea el mismo día que sus contrapartes.
- [ ] Se respeta la convención de nombres de `CONTRIBUTING.md` (paquetes, clases, funciones,
      tablas, columnas, rutas, ramas).
- [ ] Los commits siguen Conventional Commits y referencian la HU (`(HU-XX)` o `Refs: HU-XX`).
- [ ] La documentación relacionada (README, ADR, contratos) está actualizada si el cambio la
      afecta.
- [ ] No se commitean secretos, archivos `.env` ni credenciales.
