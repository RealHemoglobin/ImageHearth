# Validación: Fase 1

## Criterios de finalización

- `uv tool install ./` en un usuario limpio de Linux expone las 7 herramientas.
- Todos los tests pasan contra el paquete instalado, no contra el código fuente.
- La instalación actual sigue generando imágenes.
- Los datos del usuario no se escriben dentro de `site-packages`.
- `mcp/`, `engine/`, `workflows/`, `skill/`, `extras/` y `requirements.txt` ya no existen en la raíz.

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

```bash
uv build --wheel
```

```bash
git grep -in imageengine -- ':!specs'
```

El último comando solo puede devolver el nodo `imageengine_status` y su ruta, los identificadores internos de `kontext.py` y referencias justificadas en la documentación.

El CI ejecuta los tres primeros comandos y, en otro trabajo, los tests contra el wheel instalado en un entorno aparte. Ese trabajo falla si `imagehearth_mcp.__file__` no está en `site-packages`. Todo se ejecuta en `ubuntu-latest`, sin GPU ni ComfyUI.

No se exige cobertura mínima. `tech-stack.md` no define ninguna otra puerta de calidad obligatoria para esta fase.

## Validaciones manuales

### Usuario temporal de Linux

- [ ] Crear un usuario sin configuración previa ni acceso al repositorio. El wheel se copia a una ruta que pueda leer.
- [ ] `uv tool install` del wheel termina sin errores y `imagehearth-mcp --version` funciona.
- [ ] Un cliente MCP por stdio lista las 7 herramientas, sin ComfyUI configurado.
- [ ] `ensure_comfyui` o una generación da un error que indica la ruta buscada y cómo configurarla.
- [ ] Los archivos creados están en las carpetas de `platformdirs` de ese usuario, y nada nuevo aparece dentro del entorno de la herramienta.
- [ ] Eliminar el usuario temporal y su carpeta.

### Configuración

- [ ] Una variable de entorno tiene prioridad sobre `config.toml`, y `config.toml` sobre el valor por defecto.
- [ ] Un `config.toml` no válido da un error que nombra el archivo.

### Instalación migrada, con RTX 4090

- [ ] Existen copias de `~/.claude.json` y `~/.codex/config.toml` con sus permisos originales.
- [ ] Claude Code y Codex listan las 7 herramientas bajo `imagehearth`, lanzadas con la ruta absoluta del ejecutable.
- [ ] La skill `imagehearth` carga desde el paquete instalado y ya no existe el enlace antiguo.
- [ ] Generación real con `fast` y con `quality`, y edición con Kontext. Las imágenes quedan en `~/Pictures/ImageHearth/`.
- [ ] El modelo de Ollama se restaura al terminar.
- [ ] `output/`, `logs/` y `state/` del repositorio y la subcarpeta `imageengine` de ComfyUI siguen intactos.
- [ ] Los pasos de reversión del plan se han revisado y siguen siendo aplicables.

## Lista para fusionar

- [ ] `uv sync --locked`, `ruff`, `pytest` y `uv build --wheel` en verde en local.
- [ ] El wheel contiene workflows, skill, nodo y ambas licencias, y no contiene tests ni `specs/`.
- [ ] Los trabajos del CI en verde en el PR, incluido el del wheel instalado.
- [ ] Las herramientas conservan nombres, parámetros y resultados, revisado en el diff.
- [ ] Ambos README coinciden entre sí y describen la instalación con `uv tool install ./`.
- [ ] `tech-stack.md` y `THIRD_PARTY_NOTICES.md` están actualizados.
- [ ] Roadmap actualizado: tareas de la fase 1 marcadas.
- [ ] CI en verde en `main` después de fusionar.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| Tests y `ruff` en local | Pendiente de implementación | |
| Contenido del wheel | Pendiente de implementación | |
| Ejecución del CI en el PR | Pendiente de implementación | |
| Usuario temporal de Linux | Pendiente de implementación | |
| Migración de agentes y skill | Pendiente de implementación | |
| Generación real con `fast`, `quality` y Kontext | Pendiente de implementación | |
| Ejecución del CI en `main` | Pendiente de implementación | |
