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

- [x] Crear un usuario sin configuración previa ni acceso al repositorio. El wheel se copia a una ruta que pueda leer.
- [x] `uv tool install` del wheel termina sin errores y `imagehearth-mcp --version` funciona.
- [x] Un cliente MCP por stdio lista las 7 herramientas, sin ComfyUI configurado.
- [x] `ensure_comfyui` o una generación da un error que indica la ruta buscada y cómo configurarla.
- [x] Los archivos creados están en las carpetas de `platformdirs` de ese usuario, y nada nuevo aparece dentro del entorno de la herramienta.
- [x] Eliminar el usuario temporal y su carpeta.

### Configuración

- [x] Una variable de entorno tiene prioridad sobre `config.toml`, y `config.toml` sobre el valor por defecto.
- [x] Un `config.toml` no válido da un error que nombra el archivo.

### Instalación migrada, con RTX 4090

- [x] Existen copias de `~/.claude.json` y `~/.codex/config.toml` con sus permisos originales.
- [ ] Claude Code y Codex listan las 7 herramientas bajo `imagehearth`, lanzadas con la ruta absoluta del ejecutable.
- [x] La skill `imagehearth` carga desde el paquete instalado y ya no existe el enlace antiguo.
- [x] Generación real con `fast` y con `quality`, y edición con Kontext. Las imágenes quedan en `~/Pictures/ImageHearth/`.
- [ ] El modelo de Ollama se restaura al terminar.
- [x] `output/`, `logs/` y `state/` del repositorio y la subcarpeta `imageengine` de ComfyUI siguen intactos.
- [x] Los pasos de reversión del plan se han revisado y siguen siendo aplicables.

## Lista para fusionar

- [x] `uv sync --locked`, `ruff`, `pytest` y `uv build --wheel` en verde en local.
- [x] El wheel contiene workflows, skill, nodo y ambas licencias, y no contiene tests ni `specs/`.
- [ ] Los trabajos del CI en verde en el PR, incluido el del wheel instalado.
- [x] Las herramientas conservan nombres, parámetros y resultados, revisado en el diff.
- [x] Ambos README coinciden entre sí y describen la instalación con `uv tool install ./`.
- [x] `tech-stack.md` y `THIRD_PARTY_NOTICES.md` están actualizados.
- [x] Roadmap actualizado: tareas de la fase 1 marcadas.
- [ ] CI en verde en `main` después de fusionar.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| Tests y `ruff` en local | 56 tests y `ruff` en verde; `uv lock --check` correcto | 2026-10-31 |
| Contenido del wheel | Contiene workflows, skill, nodo y ambas licencias; 0 entradas de `tests/` o `specs/` | 2026-10-31 |
| Ejecución del CI en el PR | Pendiente de implementación | |
| Usuario temporal de Linux | Simulado con un `HOME` vacío y repetido por el usuario con un usuario real de Linux: todo correcto, usuario eliminado | 2026-10-31 |
| Migración de agentes y skill | Copias `*.bak-20261031-010019` de `~/.claude.json` y `~/.codex/config.toml` (permisos 600 en la de Claude); entradas `imagehearth` con `~/.local/bin/imagehearth-mcp`; enlace `~/.claude/skills/imagehearth` al paquete instalado. Falta reiniciar los agentes y listar las herramientas en cada uno | 2026-10-31 |
| Generación real con `fast`, `quality` y Kontext | Las tres OK con el comando instalado por stdio; imágenes en `~/Pictures/ImageHearth/`; sin sesión pendiente. No se comprobó la restauración de Ollama | 2026-10-31 |
| Ejecución del CI en `main` | Pendiente de implementación | |
