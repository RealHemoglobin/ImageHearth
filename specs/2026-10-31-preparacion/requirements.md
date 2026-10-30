# Fase 0: Preparación

## Contexto

Primera fase del [roadmap](../roadmap.md). Su objetivo es cerrar lo que sería caro cambiar después y dejar un CI base antes de empaquetar el proyecto en la fase 1.

Estado de partida, comprobado el 2026-10-31:

- `main` es la única rama y no hay ningún remoto configurado.
- `robustez` ya no existe y sus commits están en `main`.
- No hay `LICENSE`, `THIRD_PARTY_NOTICES.md`, `pyproject.toml` ni workflows de GitHub Actions.
- Los tests usan un ComfyUI simulado (`tests/harness.py`), sin GPU ni ComfyUI real.
- `uv` y `ruff` no están instalados en esta máquina; `gh` sí.

## Alcance

- Añadir las licencias y `THIRD_PARTY_NOTICES.md`.
- Definir un entorno de desarrollo independiente del venv de ComfyUI.
- Crear el CI en Linux con `pytest` y `ruff`.
- Crear el repositorio privado en GitHub y dejar el CI en verde en `main`.
- Sustituir `OWNER` y el nombre del repositorio en ambos README.
- Registrar el hardware de prueba disponible y lo que falta.

## Fuera de alcance

- Mover código a `src/`, eliminar `mcp/` o renombrar el paquete y sus módulos: es la fase 1.
- Empaquetar el proyecto o exponer el comando de la CLI: es la fase 1.
- CI en Windows y macOS: es la fase 2.
- Prueba de contrato con `/object_info`: es la fase 2.
- Publicar en PyPI o hacer público el repositorio: es la fase 6.
- Umbral de cobertura de tests.

## Decisiones

| Tema | Decisión |
|---|---|
| Nombre público | **ImageHearth**, elegido el 2026-10-31 para evitar el conflicto con `imageengine` en PyPI y con la marca del CDN. Ese día `imagehearth` e `imagehearth-mcp` estaban libres en PyPI y no había repositorios en GitHub con ese nombre. No se han consultado registros oficiales de marcas |
| Licencia del proyecto | MIT |
| Licencia del nodo | GPL-3.0 para `extras/comfyui_custom_nodes/imageengine_status/`, que importa código de ComfyUI |
| Dueño en GitHub | Cuenta personal `RealHemoglobin` |
| Creación del repositorio | La hace el usuario, una vez elegido el nombre |
| Visibilidad | Privado hasta la beta de la fase 6 |
| Entorno de desarrollo | `pyproject.toml` mínimo con grupo `dev` y `uv.lock`, sin empaquetar. La fase 1 lo amplía |
| Licencias de modelos | Síntesis con enlaces para FLUX Dev, Kontext y SDXL Turbo, sin revisión legal externa |
| Puerta de calidad | `pytest` y `ruff` limpios en `ubuntu` |
| Tarea `robustez` | Se da por cumplida: no hay nada que fusionar |

## Hardware de prueba

| Plataforma | Estado |
|---|---|
| Linux con NVIDIA | Disponible |
| Windows con NVIDIA | Disponible |
| Mac con Apple Silicon | **No disponible.** Riesgo abierto para la fase 4 |

La falta de un Mac no bloquea esta fase ni la fase 1, porque el roadmap recomienda publicar la beta sin esperar a macOS. Sin un Mac no se anuncia soporte para macOS.

## Restricciones

- No cambiar el comportamiento del motor ni del servidor MCP. Las correcciones de `ruff` no deben alterar la lógica; lo que no se pueda corregir así se excluye de forma explícita en la configuración.
- El CI no puede necesitar GPU, ComfyUI ni modelos.
- `THIRD_PARTY_NOTICES.md` indica la fecha de revisión y deja claro que no es asesoramiento legal.

## Entregables

- `LICENSE` (MIT) en la raíz y licencia GPL-3.0 en la carpeta del nodo.
- `THIRD_PARTY_NOTICES.md`.
- `pyproject.toml` y `uv.lock`.
- `.github/workflows/ci.yml`.
- `README.md` y `README.es.md` actualizados.
- Repositorio privado `RealHemoglobin/ImageHearth` con el CI en verde en `main`.
- Roadmap con las tareas de la fase 0 marcadas y la tabla de decisiones abiertas actualizada.

## Supuestos

- `requires-python = ">=3.13"` y CI con Python 3.13, en línea con la matriz de `tech-stack.md`. Se ajusta si las dependencias o los tests lo exigen.
- El nombre interno del paquete y del comando (`imageengine_mcp`, `imageengine-mcp` en el roadmap) pasa a `imagehearth_mcp` e `imagehearth-mcp` en la fase 1. Hasta entonces el código conserva el nombre actual.
- Antes de hacer público el repositorio en la fase 6 habrá que revisar su historial en busca de datos personales.
