# Análisis del estado actual

Fecha: 2026-10-31. Rama analizada: `robustez` (`08221dd`).

## Conclusión

El núcleo es sólido: orquestación de sesiones, recuperación tras fallos, validaciones y 44 tests con servidores simulados. Es lo más valioso del proyecto y **no hay que reescribirlo**.

Lo que falta es todo lo que rodea al núcleo. Hoy funciona en una sola máquina configurada a mano: Linux, NVIDIA, ComfyUI en `~/AI/ComfyUI` y Ollama activo.

## Qué se ha comprobado

| Comprobación | Resultado |
|---|---|
| Tests en el venv de ComfyUI | 44 correctos |
| Tests en un venv limpio creado con `requirements.txt` | 44 correctos |
| Tests con el Python del sistema | 1 error, porque no tiene `mcp`: el proyecto no define su entorno |
| Servidor MCP por stdio en un venv limpio | Expone las 7 herramientas |
| Sesión de generación con Ollama apagado | **Falla** con `ConnectionError` |
| Hash SHA-256 de los 6 modelos locales frente a Hugging Face | Los 6 coinciden |
| Historial de git, buscando rutas personales y secretos | Sin hallazgos; el autor usa un email `noreply` |
| Log de ComfyUI | Marca el nodo como `IMPORT FAILED` en el arranque, aunque la ruta funciona |

Solo se ha ejecutado en Linux con una RTX 4090 de 24 GB y Python 3.14. Lo relativo a Windows y macOS sale de leer el código y la documentación: **todavía no se ha probado**.

## Bloqueos

### A. El paquete no se puede distribuir

| Problema | Dónde | Consecuencia |
|---|---|---|
| No hay `pyproject.toml` ni punto de entrada | raíz | No se puede instalar con `uvx` ni `pip` |
| La carpeta `mcp/` se llama igual que la dependencia `mcp` | `mcp/server.py:5` | Hoy funciona por el orden de `sys.path`; empaquetada, chocaría |
| El paquete `engine` tiene un nombre genérico | `engine/` | Riesgo de colisión en `site-packages` |
| Datos, logs, estado y salida viven junto al código | `engine/config.py:9-16` | Dentro de un paquete instalado, la ruta es inadecuada o no se puede escribir |
| Los workflows no son datos de paquete | `engine/config.py:10` | No se incluirían en la distribución |
| El MCP corre con el Python del venv de ComfyUI | configuración local del agente | Actualizar uno puede romper al otro |
| No hay `LICENSE` | raíz | Publicado así, nadie tiene permiso legal para usarlo |

### B. Código exclusivo de Linux

| Problema | Dónde | En otros sistemas |
|---|---|---|
| `import fcntl` | `engine/orchestrator.py:1`, `engine/log.py:2` | **Windows: el servidor no llega a arrancar** |
| Recorre `/proc` para buscar procesos | `engine/comfyui_manager.py:42` | Falla en Windows y macOS |
| `os.kill` con `SIGKILL` | `engine/comfyui_manager.py:166` | `SIGKILL` no existe en Windows |
| `venv/bin/python` | `engine/comfyui_manager.py:103` | En Windows es `Scripts\python.exe` |
| `start_new_session=True` | `engine/comfyui_manager.py:128` | Windows necesita `creationflags` |
| La rotación de logs compara inodos y renombra archivos abiertos | `engine/log.py:41-52` | Windows no permite renombrar un archivo abierto |
| `read_text()` sin `encoding` | `engine/workflow_runner.py:70`, `engine/kontext.py:109` | Windows puede usar otra codificación por defecto |
| `nvidia-smi` como única sonda de VRAM | `engine/comfyui_manager.py:62-78` | Sin datos en AMD, Intel y Apple |

### C. Dependencias que hoy son obligatorias y no deberían serlo

| Problema | Dónde | Consecuencia |
|---|---|---|
| **Ollama es obligatorio de hecho** | `engine/orchestrator.py:350`, `:46` | Quien no lo tenga no puede generar nada |
| Sin Ollama el estado es `degraded` | `engine/status.py:62` | Avisa de un problema que no debería existir |
| **Sin el nodo `imageengine_status`, el motor se bloquea** | `engine/comfyui_client.py:187-191` | `free_models` falla, ComfyUI se reinicia, vuelve a fallar y pasa a `recovery_required`. La siguiente sesión lo repite en `_reconcile` (`engine/orchestrator.py:287`) |
| El nodo devuelve `None` en `comfy_entrypoint` | `extras/.../imageengine_status/__init__.py:20` | La ruta se registra como efecto secundario y ComfyUI lo muestra como `IMPORT FAILED`: una actualización podría romperlo |
| Ruta fija de ComfyUI, sin variable de entorno | `engine/config.py:18` | Solo admite una ubicación |
| Puerto 8188 fijo | `engine/config.py:20`, `mcp/server.py:139` | Choca con otra instancia; ComfyUI Desktop usa su propia configuración |

### D. Modelos y hardware sin contemplar

| Problema | Dónde | Consecuencia |
|---|---|---|
| Ningún instalador ni manifiesto de modelos | — | El usuario debe descubrir archivos, carpetas y versiones |
| `list_workflows` no comprueba si existen los modelos | `engine/validation.py:41-46` | Ofrece workflows que fallarán |
| El mapa calidad → workflow está fijo | `engine/validation.py:59` | No se adapta al perfil instalado |
| **Los pesos fp8 no funcionan en Apple Silicon** | `workflows/flux_dev.json`, `workflows/flux_kontext_dev_basic.json` | MPS no tiene el tipo `Float8_e4m3fn`: FLUX y Kontext necesitan otros modelos en macOS |
| `build_workflow` depende de identificadores de nodo fijos | `engine/kontext.py:111-129` | Las variantes GGUF necesitan otro nodo cargador |

### E. Integración con agentes

| Problema | Dónde | Consecuencia |
|---|---|---|
| Las instrucciones viven solo en la skill | `skill/SKILL.md` | Los agentes sin skills no las reciben; `FastMCP` admite `instructions` y no se usa |
| Ruta personal en la skill | `skill/SKILL.md:231` | Es incorrecta para cualquier otro usuario |
| Sin notificaciones de progreso | `mcp/server.py` | Una generación larga puede superar el plazo del cliente |
| Solo devuelve una ruta | `engine/result.py` | Los agentes en otro contenedor no ven la imagen |
| Mensajes en español y prefijo `ADVERTENCIA` | `engine/result.py:12` y todo `engine/` | Público limitado; la skill depende de ese prefijo |

Claude Code aguanta bien las llamadas largas (limita a unos 30 min sin actividad por stdio). No se ha verificado el plazo de Cursor, VS Code ni Codex, y para Gemini CLI solo hay una fuente secundaria que indica 10 min. La fase 5 debe medirlo.

### F. Riesgos para quien lo instale

| Riesgo | Dónde | Medida |
|---|---|---|
| `restart()` mata cualquier ComfyUI lanzado desde esa carpeta | `engine/comfyui_manager.py:154-173` | Instancia propia registrada con PID; nunca reiniciar una ajena |
| `/free` descarga los modelos de una instancia que el usuario esté usando | `engine/comfyui_client.py:177` | Instancia gestionada por defecto y aviso en modo adjunto |
| Se borran archivos directamente en la carpeta de ComfyUI | `engine/comfyui_client.py:112`, `:124` | Conservar el límite a la subcarpeta `imageengine`; resolver las rutas desde la configuración |
| Descargas sin versión fijada | — | Fijar revisión y SHA-256 |

## Modelos actuales: origen verificado

Los hashes de los archivos instalados coinciden con estos repositorios. Ninguno exige aprobación previa a día de hoy.

| Archivo | Repositorio y ruta | Bytes | SHA-256 |
|---|---|---|---|
| `checkpoints/sd_xl_turbo_1.0_fp16.safetensors` | `stabilityai/sdxl-turbo` | 6938081905 | `e869ac7d6942cb327d68d5ed83a40447aadf20e0c3358d98b2cc9e270db0da26` |
| `diffusion_models/flux_dev_fp8_scaled_diffusion_model.safetensors` | `comfyanonymous/flux_dev_scaled_fp8_test` | 11901607560 | `358fff9355c962532593898b10436f13e6f9bfb0389f36df03c6e55fe7c9cbfe` |
| `diffusion_models/flux1-dev-kontext_fp8_scaled.safetensors` | `Comfy-Org/flux1-kontext-dev_ComfyUI`, `split_files/diffusion_models/` | 11904640136 | `630ba795ec64283b4230ea23cf79406c2c68b7c578229ed139f30043eadb30a2` |
| `text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors` | `comfyanonymous/flux_text_encoders` | 5157348688 | `a498f0485dc9536735258018417c3fd7758dc3bccc0a645feaa472b34955557a` |
| `text_encoders/clip_l.safetensors` | `comfyanonymous/flux_text_encoders` | 246144152 | `660c6f5b1abae9dc498ac2d21e1347d2abdb0cf6c0c0c8576cd796491d9a6cdd` |
| `vae/ae.safetensors` | `Comfy-Org/Lumina_Image_2.0_Repackaged`, `split_files/vae/` | 335304388 | `afc8e28272cd15db3919bacdb6918ce9c1ed22e96cb12c4d5ed0fba823529e38` |

`checkpoints/sd_xl_base_1.0.safetensors` también está instalado, pero ningún workflow lo usa.

El repositorio del FLUX Dev tiene "test" en el nombre, así que es el origen más frágil. Hay que buscarle un sustituto o una alternativa antes de la v1.

Espacio medido en esta máquina:

| Componente | Tamaño |
|---|---|
| SDXL Turbo | 6,9 GB |
| FLUX Dev con codificadores y VAE | 17,6 GB |
| Kontext (reutiliza codificadores y VAE) | 11,9 GB |
| **Todos los modelos** | **36,5 GB** |
| ComfyUI | 0,2 GB |
| Entorno Python con PyTorch CUDA | 7 GB |

## Licencias

No es asesoramiento legal, y hay que revisarlo antes de publicar.

| Componente | Licencia | Implicación |
|---|---|---|
| FLUX.1 Dev y Kontext Dev | `flux-1-dev-non-commercial-license` | El modelo es de uso no comercial. El texto de Kontext está tras acceso restringido y no se ha podido leer aquí; revisar qué permite sobre las imágenes generadas |
| SDXL Turbo | Stability AI Community License | Su `LICENSE.md` permite uso comercial por debajo de 1 M USD de ingresos anuales, con registro. Los metadatos de Hugging Face siguen indicando `sai-nc-community`: confirmar cuál prevalece |
| ComfyUI | GPL-3.0 | ImageEngine se comunica por HTTP, pero el nodo personalizado importa módulos de ComfyUI y puede tener que ser GPL |

Consecuencias: el instalador debe enseñar y hacer aceptar cada licencia, y el proyecto nunca debe alojar los pesos.

## Fuentes

- [Instalación de ComfyUI: versiones de Python, PyTorch y builds portables](https://github.com/Comfy-Org/ComfyUI#manual-install-windows-linux)
- [comfy-cli](https://docs.comfy.org/comfy-cli/getting-started)
- [PR de ComfyUI sobre float8 en MPS](https://github.com/Comfy-Org/ComfyUI/pull/12406) y [discusión sobre fp8 en Apple Silicon](https://huggingface.co/Kijai/flux-fp8/discussions/14)
- [FLUX.1 Dev GGUF](https://huggingface.co/city96/FLUX.1-dev-gguf) y [FLUX.1 Kontext Dev GGUF](https://huggingface.co/QuantStack/FLUX.1-Kontext-dev-GGUF)
- [MCP en Claude Code: comandos, ámbitos y plazos](https://code.claude.com/docs/en/mcp)
- [Registro oficial de MCP](https://modelcontextprotocol.info/tools/registry/)
- [Licencia de SDXL Turbo](https://huggingface.co/stabilityai/sdxl-turbo/blob/main/LICENSE.md)
