# Fase 5: Integración con agentes

## Contexto

Fase 5 del [roadmap](../roadmap.md), cuyo objetivo es funcionar igual en cualquier agente, tenga o no skills, y que un usuario con modelos locales pueda instalarlo con facilidad y compaginarlo con ellos en la misma GPU. El servidor MCP estándar por stdio es el producto: cada agente o editor es solo una forma de conectarlo, y el soporte de uno nuevo no debe exigir cambios en el motor.

Estado de partida, comprobado el 2026-10-31:

- `server.py` expone 7 herramientas con `FastMCP("imagehearth")`, sin `instructions`. Lo esencial está en `data/skill/SKILL.md`, que los agentes con modelos locales no cargan.
- `create_image` ya admite `mode` (`auto`, `generate`, `edit`), `quality`, `image_paths` y `workflow`, de modo que cubre a `generate_image` y `edit_image`.
- `cli.py` tiene `setup`, `doctor`, `update` y `uninstall`. No existe `connect`.
- `engine/memory.py` define `MemoryProvider` (`loaded`, `unload`, `restore`), con `OllamaProvider` y `DisabledProvider`. `get_provider` solo mira `ollama_mode` (`auto`, `off`).
- `provisioner/detect.py` ya detecta Ollama, LM Studio, llama.cpp y vLLM.
- Las herramientas devuelven una cadena con la ruta en la primera línea y, después, las líneas `WARNING`. No emiten progreso.
- No existe la carpeta `docs/`.
- En esta máquina están instalados opencode, Hermes, pi, Codex y VS Code, además de Claude Code. No están Gemini CLI ni Cursor. `pi` trae un comando `pi mcp`. Hermes apunta a un servidor local en el puerto 11434.

## Alcance

La fase 5 completa, en una sola spec y una sola rama:

- **Servidor:** `instructions` obligatorias, descripciones autosuficientes, arranque sin ComfyUI y herramientas que explican qué falta.
- **Herramientas:** `create_image` como vía principal y decisión medida sobre `generate_image` y `edit_image`.
- **Conexión:** `connect <agente>`, `connect --detect`, `connect --print <agente>` y `docs/agents.md`.
- **Agentes:** Claude Code, Claude Desktop, Codex, Gemini CLI, opencode, Hermes y pi si admite MCP.
- **Editores:** Cursor, VS Code, IntelliJ y otros JetBrains.
- **Instalación desde el agente:** `setup_status`, `setup_start` y `llms-install.md`.
- **Generaciones largas:** progreso con `ctx.report_progress`, medición del plazo de cada cliente e imagen opcional como contenido MCP.
- **Memoria:** `MemoryProvider` para llama.cpp, LM Studio y vLLM, y `memory_mode`.
- **Modelos pequeños:** pruebas con modelos locales de 7B a 14B y documentación del tamaño mínimo que funciona.

## Fuera de alcance

- Instalar Ollama, LM Studio, llama.cpp o vLLM para el usuario, según la [misión](../mission.md).
- Pendientes de la fase 4: mediciones en Windows, Mac, perfil GGUF para NVIDIA, origen de FLUX Dev y FLUX.1 Schnell.
- `install.sh`, `install.ps1`, PyPI, registro MCP y `.mcpb`: fase 6.
- Anunciar como soportado un agente o editor que no se haya probado de verdad.
- `start_image_job` y `get_job`, salvo que la medición demuestre que algún cliente corta las generaciones.

## Decisiones

| Tema | Decisión |
|---|---|
| Orden | Primero el servidor, porque los fragmentos de `connect` se apoyan en un servidor ya estable. Después conexión, plazos, memoria, instalación desde el agente y pruebas con modelos locales |
| `create_image` | Pasa a ser la vía principal y cubre generación y edición |
| `generate_image` y `edit_image` | Se mide con modelos pequeños cuánto cuesta mantenerlos. Solo se quedan como alias si se mide que cuestan poco; si no, se eliminan. El resultado y el motivo se anotan en la evidencia |
| Skill | Queda como complemento y se instala donde el agente la admita. El servidor debe bastar sin ella |
| Método de `connect` | CLI oficial del agente si existe. Si no, edición de su configuración con copia de seguridad previa |
| Comando configurado | Ruta absoluta del ejecutable instalado, como fija [tech-stack](../tech-stack.md) |
| `connect --print` | Imprime el fragmento sin tocar nada. Es la vía para cualquier cliente sin soporte propio |
| Nivel de soporte | **Probado:** conectado y generando de verdad en esta máquina. **Sin probar:** contrastado solo con su documentación, marcado así en `docs/agents.md` y sin anunciarse como soportado |
| pi | Se comprueba `pi mcp`. Si admite stdio, se trata como un agente más. Si no, se documenta que no está soportado o se valora un adaptador pequeño |
| Proveedores de memoria | Mejor esfuerzo: cada proveedor descarga si su API lo permite. Si no, se avisa con un mensaje accionable antes de generar, en lugar de fallar por falta de memoria |
| `memory_mode` | `auto`, `off` o `manual`, en `config.toml` y con variable de entorno. En `manual`, el motor no toca los modelos del usuario y solo comprueba la memoria libre antes de generar |
| `ollama_mode` | Lo sustituye `memory_mode`. Se sigue leyendo como alias de `auto` u `off`. Si están los dos, gana `memory_mode` |
| `setup_start` | Exige `profile` y `accept_licenses` explícitos, sin valores por defecto. Lanza un proceso desacoplado que sobrevive a la desconexión. Nunca instala perfiles experimentales |
| `setup_status` | Informa de qué está instalado, qué falta, tamaños, licencias y progreso de un `setup_start` en curso |
| Instrucciones de instalación | Obligan al agente a preguntar al usuario antes de `setup_start`, indicando tamaño y licencias |
| Imagen como contenido MCP | Solo ruta por defecto. Un parámetro opcional incluye la imagen, para no llenar el contexto de los modelos pequeños. La ruta sigue en la primera línea |
| Trabajos en segundo plano | Solo se añaden si la medición muestra que algún cliente corta una generación |

## Restricciones

- El servidor MCP sigue arrancando sin PyTorch ni ComfyUI, y sin importar `huggingface_hub` al arrancar.
- Soportar un agente nuevo no debe exigir cambios en `engine/`.
- `connect` nunca modifica una configuración sin copia de seguridad, conserva las demás entradas del usuario y se puede repetir sin duplicar nada.
- `connect` no copia secretos ni variables de entorno del usuario en la configuración del agente.
- `uninstall` y el registro de lo instalado siguen sin borrar nada ajeno. Si `connect` deja entradas, deben poder retirarse.
- La protección actual se conserva: no se restaura ningún modelo mientras ComfyUI pueda retener la memoria de la GPU, y nunca se reinicia ni se mata una instancia ajena.
- Mantener la ruta en la primera línea de la respuesta, de la que dependen los agentes actuales.
- La interfaz es en inglés; los documentos de `specs/` siguen en español. `docs/agents.md` y `llms-install.md` van en inglés.
- No hay `git commit` por parte del asistente: el usuario revisa y confirma los cambios.

## Entregables

- `server.py` con `instructions`, descripciones revisadas, `setup_status`, `setup_start`, progreso e imagen opcional.
- Módulo de conexión con un descriptor por cliente, y comando `connect` en `cli.py`.
- `docs/agents.md`, con el fragmento y el nivel de soporte de cada cliente, y `llms-install.md`.
- Proveedores de memoria para llama.cpp, LM Studio y vLLM, y `memory_mode` en `config.py`, `doctor` y `get_engine_status`.
- Tests simulados de todo lo anterior.
- Skill actualizada, ambos README y `tech-stack.md`, con la VRAM necesaria para tener un modelo de lenguaje y la generación a la vez.
- Roadmap con las tareas hechas marcadas cuando estén verificadas.

## Supuestos abiertos

- **Servidor en el puerto 11434:** se asume que es Ollama, porque es su puerto y Hermes lo usa. Hay que confirmarlo y ver qué modelos tiene antes de las pruebas. Tampoco se sabe qué escucha en el 8080.
- **llama.cpp, LM Studio y vLLM:** `llama-server`, `lms` y `vllm` no están en `PATH`. Si no se pueden ejecutar aquí, sus proveedores quedan cubiertos con tests simulados y marcados como sin probar con el servidor real. Qué permite descargar cada API se comprueba en su documentación al implementarlos.
- **Formatos de configuración:** ninguno se ha verificado todavía. Se contrasta cada uno con su documentación al implementarlo.
- **Plazo de los clientes:** se desconoce. Si alguno corta las generaciones, entran `start_image_job` y `get_job`, lo que ampliaría esta spec.
