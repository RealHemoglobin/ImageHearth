# Validación: Fase 0

## Criterios de finalización

- El CI está en verde en `main` del repositorio privado `RealHemoglobin/ImageHearth`.
- No quedan decisiones abiertas que bloqueen la fase 1.
- Los tests pasan en un entorno creado con `uv sync`, sin usar el venv de ComfyUI.
- No cambia el comportamiento del motor ni del servidor MCP.

## Validaciones automáticas

Desde la raíz del repositorio:

```bash
uv sync --locked
```

```bash
uv run ruff check .
```

```bash
uv run pytest
```

El workflow `.github/workflows/ci.yml` ejecuta esos mismos comandos en `ubuntu-latest`, sin GPU ni ComfyUI.

No se exige cobertura mínima. `tech-stack.md` no define ninguna otra puerta de calidad obligatoria para esta fase.

## Validaciones manuales

- [ ] `LICENSE` contiene MIT y la carpeta del nodo contiene GPL-3.0.
- [ ] `THIRD_PARTY_NOTICES.md` cubre FLUX Dev, Kontext y SDXL Turbo con enlace, uso comercial y fecha de revisión.
- [ ] Cada enlace de `THIRD_PARTY_NOTICES.md` abre la licencia de origen.
- [ ] Ningún README contiene `OWNER`, y la URL de clonado funciona con el repositorio real.
- [ ] El repositorio es privado.
- [ ] Una generación real con `fast` sigue funcionando en Linux con NVIDIA, en la instalación actual.
- [ ] El CI falla si se rompe un test a propósito en una rama de prueba.

## Lista para fusionar

- [ ] `uv sync --locked`, `ruff` y `pytest` en verde en local.
- [ ] CI en verde en el PR.
- [ ] Los cambios de `ruff` no alteran la lógica, revisado en el diff.
- [ ] Ambos README están actualizados y coinciden entre sí.
- [ ] Roadmap actualizado: tareas de la fase 0 marcadas y decisiones abiertas al día.
- [ ] El riesgo del hardware Mac sigue registrado para la fase 4.
- [ ] CI en verde en `main` después de fusionar.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| Nombre elegido y disponibilidad | ImageHearth; libre en PyPI (`imagehearth`, `imagehearth-mcp`) y sin repositorios en GitHub | 2026-10-31 |
| Tests y `ruff` en local | Pendiente de implementación | |
| Ejecución del CI en el PR | Pendiente de implementación | |
| Ejecución del CI en `main` | Pendiente de implementación | |
| Generación real con `fast` | Pendiente de implementación | |
