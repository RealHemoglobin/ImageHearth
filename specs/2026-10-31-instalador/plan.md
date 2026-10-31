# Plan: Fase 3

Rama: `feature/instalador`. Sin commits del asistente: los cambios se dejan en el árbol de trabajo para revisión.

## 1. Spike: instalador propio o `comfy-cli` (máximo 2 días)

1. Instalar ComfyUI con `comfy-cli` sin preguntas en Linux y Windows, comprobando los flags de ruta y de GPU.
2. Prototipar la vía propia: archivo de una versión fijada, entorno con uv y Python 3.13, PyTorch `cu130`.
3. Confirmar los supuestos sobre `uv` en `PATH` y el origen de ComfyUI.
4. Documentar la decisión, y la versión fijada de ComfyUI, en `tech-stack.md`. Si se descarta el instalador propio, ajustar las tareas 5 y 7 antes de seguir.

## 2. Estructura y dependencias

1. Crear `src/imagehearth_mcp/provisioner/` y añadir `huggingface_hub` a `pyproject.toml`, regenerando `uv.lock`.
2. Convertir `cli.py` a subcomandos `setup`, `doctor`, `update` y `uninstall`, que importen el provisioner solo al usarse. Mantener el servidor MCP sin subcomando, y `--version`.
3. Tests: sin argumentos sigue sirviendo MCP y `--version` no carga el servidor ni el provisioner.

## 3. Detección

1. `provisioner/detect.py`: sistema, arquitectura, GPU, driver, VRAM, RAM y disco, con un resultado tipado y serializable.
2. ComfyUI existente, incluido Desktop, por rutas conocidas y por el puerto.
3. Ollama, LM Studio, llama.cpp y vLLM, solo lectura.
4. Clasificar la plataforma con los niveles de la matriz de PyTorch de [tech-stack](../tech-stack.md).
5. Tests con salidas simuladas de `nvidia-smi`, sin GPU y con cada sistema.

## 4. Manifiesto de modelos

1. Crear `data/models.toml` partiendo de la tabla del [análisis](../analysis.md) y fijar la revisión de cada repositorio.
2. Definir perfiles: `fast` (SDXL Turbo), `quality` (`fast` + FLUX Dev, T5, CLIP-L y VAE) y `full` (`quality` + Kontext).
3. Resolver las dudas de licencias del análisis y registrar nombre y enlace de cada una.
4. Cargador con validación. Tests: los tamaños suman lo documentado, cada workflow tiene sus modelos y los hashes tienen formato válido.

## 5. Descarga de modelos

1. `provisioner/models.py`: descarga con `huggingface_hub`, revisión fijada y `HF_TOKEN` si existe.
2. Saltar un archivo presente si coincide su SHA-256. Volver a descargar uno corrupto, solo si está en una ruta propia del instalador.
3. Tests con descargador simulado: interrupción y reanudación, archivo corrupto, archivo presente y repositorio con acceso restringido.

## 6. Registro de lo instalado

1. `provisioner/install_manifest.py`: registrar con escritura atómica cada carpeta, archivo y cambio de configuración, indicando si es propio o preexistente.
2. Tests: se conserva lo ya registrado al repetir la instalación y nunca se marca como propio algo preexistente.

## 7. ComfyUI gestionado y modo adjunto

1. Gestionado: descargar la versión fijada, crear el entorno con uv y Python gestionado, instalar el PyTorch del manifiesto e instalar el nodo desde `data/`.
2. Adjunto: pedir permiso, instalar el nodo en `custom_nodes`, escribir `comfy_dir` y puerto en `config.toml` y generar `extra_model_paths.yaml` si hace falta.
3. Tests con subprocesos simulados y `tmp_path`. Repetir la instalación no debe duplicar ni romper nada.

## 8. Comprobaciones previas y `setup`

1. `provisioner/preflight.py`: disco insuficiente según el perfil, driver ausente, GPU sin soporte y puerto ocupado, con mensajes accionables en inglés. Se ejecuta antes de descargar nada.
2. Subcomando `setup`, con `--profile`, `--accept-licenses`, modo adjunto o gestionado y modo no interactivo.
3. Flujo: detectar, proponer perfil, mostrar espacio, licencias y enlaces, pedir aceptación, comprobaciones previas, ComfyUI, modelos, prueba de humo.
4. Tests: no interactivo sin `--accept-licenses` falla sin descargar, y se puede empezar solo con `fast`.

## 9. Prueba de humo

1. Generar una imagen pequeña con `fast` usando el motor existente, y comprobar que el archivo existe y es válido.
2. Si falla, indicar la capa afectada y remitir a `doctor`.

## 10. `doctor`

1. Comprobar cada capa: paquete, configuración, ComfyUI, entorno y PyTorch, nodo y versión, modelos por perfil, GPU, puerto y Ollama opcional.
2. Salida legible con cómo arreglar cada fallo, y `--json` estable. Código de salida distinto de cero si hay fallos.
3. Modo rápido de modelos por tamaño, y hash completo solo con una opción explícita.
4. Tests de cada capa y del formato JSON.

## 11. `update` y `uninstall`

1. `update`: aplicar la versión fijada de ComfyUI y los modelos del manifiesto actual, sin tocar un ComfyUI adjunto salvo el nodo.
2. `uninstall`: mostrar qué se borra, borrar solo lo registrado como propio y pedir confirmación aparte para los modelos. Retirar el nodo de un ComfyUI adjunto si lo instaló el propio setup.
3. Tests: ComfyUI y modelos preexistentes quedan intactos, y sin registro no se borra nada.

## 12. Documentación

1. Ambos README: instalación con `setup`, opciones, modo adjunto y `doctor`. La instalación de un comando sigue reservada para la fase 6.
2. `tech-stack.md`: resultado del spike y valores fijados. `THIRD_PARTY_NOTICES.md` si cambian las dependencias.
3. Marcar las tareas de la fase 3 en el roadmap cuando estén verificadas (el usuario revisa antes).

## 13. Validación

1. Ejecutar la matriz de [validation.md](validation.md): automática en Linux y Windows, y manual en máquinas limpias Ubuntu y Windows 11 con NVIDIA.
2. Rellenar la tabla de evidencia.
