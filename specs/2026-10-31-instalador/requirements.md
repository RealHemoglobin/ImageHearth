# Fase 3: Instalador

## Contexto

Cuarta fase del [roadmap](../roadmap.md). Su objetivo es que `imagehearth-mcp setup` lleve una máquina limpia a un sistema funcional, cumpliendo los criterios de la [misión](../mission.md): sin editar configuración a mano, sabiendo antes de descargar cuánto ocupa y qué licencias se aceptan, y sin borrar nunca lo que el usuario ya tenía.

Estado de partida, comprobado el 2026-10-31:

- El paquete se instala con `uv tool install ./`. `cli.py` usa `argparse`, solo tiene `--version` y, sin argumentos, sirve MCP por stdio.
- `engine/config.py` resuelve rutas con `platformdirs` y lee `config.toml`. ComfyUI se espera en `DATA_DIR/comfyui` o en `comfy_dir`.
- `platform/` ya ofrece procesos, bloqueos, rutas del venv y arranque desacoplado en Linux y Windows.
- El nodo `imagehearth_status` y los workflows están en `data/` como datos de paquete, pero el nodo se copia a mano.
- El [análisis](../analysis.md) contiene los seis modelos con repositorio, bytes y SHA-256 verificados. Faltan las revisiones fijadas.

## Alcance

- **Spike** (máximo 2 días): instalador propio frente a `comfy-cli` en Linux y Windows.
- **Detección:** sistema, arquitectura, GPU, driver, VRAM, RAM, disco, ComfyUI existente (incluido Desktop), Ollama, LM Studio, llama.cpp y vLLM.
- **Manifiesto `models.toml`:** repositorio, revisión fijada, ruta, tamaño, SHA-256, licencia y workflows que habilita cada modelo, y perfiles `fast`, `quality` y `full`.
- **ComfyUI gestionado:** versión fijada descargada sin Git, entorno con uv y Python gestionado, PyTorch adecuado y nodo instalado.
- **Modo adjunto:** usar un ComfyUI existente, instalar el nodo con permiso y configurar URL y rutas.
- **Modelos:** descarga reanudable, verificación SHA-256 y sin repetir lo que ya existe.
- **Consentimiento:** resumen de espacio, licencias y enlaces antes de descargar, y elección de perfil. En modo no interactivo se exige `--accept-licenses`.
- **Comprobaciones previas:** disco insuficiente, driver ausente, GPU sin soporte y puerto ocupado, cada una con un mensaje accionable.
- **`doctor`:** comprobación de cada capa, con salida legible y `--json`.
- **`update` y `uninstall`:** basados en un manifiesto de lo instalado.
- **Prueba de humo** final con una imagen pequeña.

## Fuera de alcance

- macOS, perfiles `mac-*`, GGUF y catálogo dinámico de workflows: fase 4.
- `connect`, herramientas `setup_status` y `setup_start`, y arranque del servidor con explicación de lo que falta: fase 5.
- `install.sh`, `install.ps1` y publicación en PyPI: fase 6.
- Instalar o gestionar Ollama, LM Studio, llama.cpp o vLLM: aquí solo se detectan.
- Buscar un origen más estable para FLUX Dev: fase 4.
- Soportar como probados los niveles 2 y 3 de la matriz de PyTorch. Se detectan y se avisa, sin anunciarlos.
- CI de cualquier tipo.

## Decisiones

| Tema | Decisión |
|---|---|
| Alcance de la rama | Fase 3 completa en una sola rama, `feature/instalador` |
| Spike | Primera tarea, con el resultado documentado en `tech-stack.md`. El plan parte del instalador propio salvo que el spike lo descarte |
| Orden | De abajo arriba: spike, detección, manifiesto, modelos, ComfyUI, comprobaciones previas, `setup`, `doctor`, `update` y `uninstall`, humo |
| CLI | Subcomandos con `argparse`, que es lo que ya usa `cli.py`, sin dependencia nueva. Sin subcomando se sigue sirviendo MCP por stdio |
| Módulo | `src/imagehearth_mcp/provisioner/`, según la arquitectura de [tech-stack](../tech-stack.md) |
| Descarga de modelos | `huggingface_hub` con revisión fijada y SHA-256 propio; admite `HF_TOKEN` |
| ComfyUI existente | Se detecta y se ofrece adjuntar. Los modelos se comparten con `extra_model_paths.yaml` |
| PyTorch | Nivel 1: `cu130` con Python 3.13. Los valores exactos se fijan en el manifiesto |
| Tamaños de perfil | `fast` 6,9 GB, `quality` 24,5 GB, `full` 36,5 GB, más 7,2 GB de ComfyUI y entorno en modo gestionado |
| Borrados | `uninstall` solo borra lo registrado en el manifiesto de instalación, y los modelos solo con confirmación |
| Verificación real | Máquinas limpias Ubuntu y Windows 11 con NVIDIA; es requisito para cerrar la fase y fusionar |

## Restricciones

- El servidor MCP sigue sin depender de PyTorch ni de ComfyUI para arrancar.
- `imagehearth-mcp` sin argumentos sigue sirviendo MCP por stdio, y `stdout` queda reservado al protocolo en ese modo.
- Las 7 herramientas conservan nombres, parámetros y resultados.
- Nunca se redistribuyen pesos: siempre se descargan desde su origen.
- Nada se descarga antes de mostrar el resumen y obtener la aceptación de las licencias.
- Nunca se modifica ni se borra un ComfyUI o unos modelos ajenos sin permiso explícito.
- La interfaz es en inglés; los documentos de `specs/` siguen en español.
- No hay `git commit` por parte del asistente: el usuario revisa y confirma los cambios.

## Entregables

- Paquete `provisioner/` con detección, manifiesto, descarga, instalación, comprobaciones previas y registro de lo instalado.
- `data/models.toml` con revisiones fijadas y hashes.
- Subcomandos `setup`, `doctor`, `update` y `uninstall`.
- Resultado del spike en `tech-stack.md`.
- Tests con hardware, red y procesos simulados, y evidencia real en Ubuntu y Windows 11.
- Ambos README y `THIRD_PARTY_NOTICES.md` actualizados.

## Supuestos abiertos

- **uv en ejecución:** se asume que `setup` encuentra `uv` en `PATH`, porque es el método de instalación y `install.sh` lo garantizará en la fase 6. Si falta, el error explica cómo instalarlo. El spike confirma este punto.
- **Origen de ComfyUI:** se asume el archivo de una versión publicada en GitHub. El spike fija la versión y el mecanismo.
- **Máquinas limpias:** se asume que las VM tienen paso de GPU o que se usan equipos limpios, como admite el roadmap.
- **Licencias:** el [análisis](../analysis.md) deja por confirmar el texto de Kontext y la licencia que prevalece en SDXL Turbo. Hay que resolverlo antes de redactar el consentimiento.
- **Fase 1:** el roadmap mantiene pendiente su última tarea, la migración de la instalación actual. Esta spec no la cambia.
