# Validación: Fase 5

## Criterios de finalización

- El servidor arranca sin ComfyUI ni modelos, y cada herramienta explica qué falta y con qué comando se arregla.
- Un agente sin skill recibe las `instructions` y las descripciones por el protocolo MCP, y le bastan para generar y editar.
- En cada cliente disponible (Claude Code, Codex, opencode, Hermes, pi si admite MCP, y VS Code) se puede conectar, generar con `fast`, generar con `quality` y editar con Kontext, partiendo de una configuración vacía.
- Los clientes no disponibles aquí (Claude Desktop, Gemini CLI, Cursor, JetBrains) están contrastados con su documentación, marcados como sin probar y sin anunciarse como soportados.
- Un cliente sin soporte propio se conecta con `connect --print` y `docs/agents.md`.
- `connect` hace copia de seguridad, conserva las demás entradas y no duplica nada al repetirse.
- Con al menos un modelo local de lenguaje (opencode u Hermes) se genera y se edita una imagen sin ayuda, con el modelo cargado y devolviendo su memoria al terminar.
- `setup_start` rechaza continuar sin `profile` y `accept_licenses`, y rechaza perfiles experimentales. Una instalación iniciada sobrevive a la desconexión del agente.
- `memory_mode` funciona en sus tres modos, y `ollama_mode` sigue funcionando como alias.
- Si un servidor no permite descargar su modelo, se avisa antes de generar con un mensaje accionable.
- Hay progreso durante la generación y el plazo de cada cliente disponible está medido.
- Por defecto, la respuesta sigue teniendo la ruta en la primera línea y no incluye la imagen.
- La decisión sobre `generate_image` y `edit_image` está aplicada y respaldada por una medición.

## Validaciones automáticas

Desde la raíz del repositorio, en Linux:

```bash
scripts/check.sh
```

Ejecuta `uv sync --locked`, `ruff`, `pytest` y los tests contra el wheel instalado en un entorno aparte.

```bash
scripts/contract.sh
```

Prueba de contrato: ComfyUI en CPU y comprobación con `/object_info` de que existen todos los nodos que usan los workflows.

En Windows (PowerShell):

```powershell
scripts\check.ps1
```

```powershell
scripts\contract.ps1
```

Los tests simulan configuraciones de agentes, servidores de modelos y subprocesos, y no descargan nada. La puerta de calidad obligatoria de [tech-stack](../tech-stack.md) es `scripts/check.sh` más la prueba de contrato.

## Validaciones manuales

### Agentes y editores (partiendo de una configuración vacía)

Para cada uno: conectar, `fast`, `quality` y edición con Kontext.

- [x] Claude Code.
- [x] Codex.
- [x] opencode.
- [x] Hermes.
- [x] pi, o documentado que no está soportado.
- [ ] VS Code.
- [x] Configuración previa con otras entradas: se conserva y queda copia de seguridad, con copias de las configuraciones reales de Hermes y Codex.
- [x] Restaurar las configuraciones reales de esta máquina al terminar las pruebas: no se han tocado; se probó con HOME temporales y copias.

### `connect --print`

- [x] Un cliente sin descriptor propio se conecta: MCP Inspector lista las herramientas con el comando absoluto. No es un agente con modelo, y no se llamó a ninguna herramienta.

### Modelos locales pequeños (sin skill)

- [x] Confirmado qué servidor escucha en el puerto 11434 y anotado el modelo usado.
- [x] opencode: elige bien la herramienta, pasa parámetros válidos, relata el resultado, y genera y edita.
- [x] Hermes: lo mismo.
- [x] Modelo de lenguaje cargado al empezar y disponible de nuevo al terminar.
- [x] Medición con las 7 herramientas y con el conjunto reducido.
- [x] Tamaño mínimo que funciona, documentado.

### Memoria

- [x] `auto`, `off` y `manual` con Ollama u otro servidor real.
- [x] `manual` con memoria insuficiente: error accionable y sin tocar el modelo del usuario.
- [x] Matar el proceso a mitad de sesión con un modelo cargado: `recover_engine` lo restaura.
- [x] llama.cpp, LM Studio y vLLM: probados con el servidor real si se pueden ejecutar aquí. Si no, anotado como cubierto solo por tests simulados.
- [x] VRAM para tener un modelo de lenguaje y la generación a la vez, medida en la RTX 4090.

### Instalación desde el agente

- [ ] Con un agente real, en carpetas aisladas y con el perfil `fast`: pregunta antes, instala y genera.
- [x] Cerrar el agente a mitad: la instalación continúa y `setup_status` la refleja al volver.
- [ ] `llms-install.md`: un agente completa la instalación siguiéndolo.

### Generaciones largas

- [x] Plazo medido en cada cliente disponible con una herramienta de 330 s; `quality` en frío medido con opencode.
- [ ] Progreso visible en los clientes que lo muestran.
- [x] Imagen como contenido MCP en al menos un cliente con visión.

## Lista para fusionar

- [ ] `scripts/check.sh` en verde en Linux y `scripts\check.ps1` en verde en Windows.
- [x] Prueba de contrato `/object_info` en verde.
- [ ] Validaciones manuales completadas.
- [x] Ningún documento anuncia como soportado un cliente sin probar.
- [x] Ambos README, `tech-stack.md` y la skill actualizados.
- [x] `docs/agents.md` y `llms-install.md` creados.
- [x] Roadmap actualizado con las tareas hechas.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` en Linux | Verde: 361 tests, también contra el wheel | 2026-10-31 |
| `scripts\\check.ps1` en Windows | **Pendiente:** no hay Windows en esta máquina | |
| Prueba de contrato `/object_info` | Verde: 19 tipos de nodo | 2026-10-31 |
| Claude Code | `connect` con su CLI real en HOME vacío (`claude mcp list`: conectado). `fast`, `quality` y Kontext con `claude -p`, modelo haiku | 2026-10-31 |
| Codex | `connect` en HOME vacío. Las tres tareas con `codex exec --oss` y `qwen3.5:9b`. Con el modelo de su configuración real (`gpt-5.6-sol`) falla antes de llamar a nada: la cuenta no lo admite | 2026-10-31 |
| opencode | `connect` en HOME vacío (`opencode mcp list`: conectado). Las tres tareas con `qwen3.5:9b` | 2026-10-31 |
| Hermes | `connect` en HOME vacío (`hermes mcp test`: conectado). Las tres tareas con `qwen3.5:9b` | 2026-10-31 |
| pi | Admite stdio con `pi mcp`. Con exposición `codemode`, 9B no encontró la herramienta (una tarea falló y otra editó con otro método). Con `exposure: direct`, que fija `connect`, las tres tareas bien | 2026-10-31 |
| VS Code | Solo `connect`. **No se ha generado:** su chat no se puede manejar sin interfaz. Queda como sin probar | 2026-10-31 |
| Claude Desktop, Gemini CLI, Cursor, JetBrains | Sin probar; contrastados con su documentación | 2026-10-31 |
| Modelo local y tamaño mínimo | Servidor del 11434: Ollama 0.40.13. `qwen3.5:9b` funciona en opencode, Hermes, pi y Codex, y vuelve a memoria al terminar. Es el menor probado. `qwen3:4b` no se pudo probar: su descarga desde Ollama falla ahora mismo | 2026-10-31 |
| Coste de los alias y decisión tomada | opencode con 9B, 5 peticiones x 3, sin skill. Con alias: 14/15 aciertos, 35,3 mil tokens de entrada por petición con una llamada. Sin alias: 15/15, 34,5 mil. Nadie eligió los alias; la diferencia de aciertos es 1 caso, no significativa. **Decisión: se eliminan**, porque cuestan unos 750 tokens por petición y no aportan nada | 2026-10-31 |
| Plazo de cada cliente | Herramienta de 330 s, sin y con progreso. Claude Code: completa/completa. pi: corta a 60 s/completa. opencode: corta/completa. Codex: 300 s/300 s, y completa con `tool_timeout_sec`. Hermes: 300 s/sin resultado en 600 s, y completa con `timeout`. **Decisión:** ninguna generación real se cortó (máximo 106 s por tarea), así que no se añaden `start_image_job` ni `get_job`; `connect` fija 1800 s en Codex y Hermes. Disco frío (caché de los modelos de FLUX vaciada, comprobado con `fincore`): 18,4 s frente a 14,4 s con caché, en NVMe; con opencode y 9B, 49 s en total y sin corte | 2026-10-31 |
| `memory_mode` con servidor real | Ollama. `auto`: descarga y restaura. `off`: genera sin tocarlo (pico 24,0 GB). `manual`: genera con memoria suficiente y, sin ella, error sin tocar el modelo. SIGKILL a mitad: `recovery_required`, y `recover_engine` restaura el modelo | 2026-10-31 |
| llama.cpp, LM Studio y vLLM | Solo tests simulados: no están instalados. El modo router de llama.cpp no consta en la parte leída de su documentación y se ha implementado de memoria: hay que comprobarlo con un servidor real. El puerto por defecto de llama.cpp también (la documentación consultada dice 9931 y el código usa 8080) | 2026-10-31 |
| VRAM con modelo de lenguaje y generación | `qwen3.5:9b`: 14,3 GB con contexto por defecto, 5,9 GB con `num_ctx` 8192. Con 5,9 GB y SDXL Turbo, pico de 19,2 GB de GPU, unos 3 GB del escritorio. Con FLUX, `manual` lo rechaza (14,3 GB libres, pide 16), pero en `off` funciona: 14-16 s, pico de 24,0 GB, y el modelo sigue cargado y responde. El umbral de 16 GB de `manual` es orientativo y aquí resulta conservador | 2026-10-31 |
| `setup_start` y desconexión | opencode con 9B, HOME aislado, adjuntando el ComfyUI existente, sin descargas. Sin consentimiento: muestra opciones y pregunta, sin lanzar nada. Con consentimiento: lanza; se mata al agente; termina `finished` con imagen de prueba, y `setup_status` lo refleja. Instalación gestionada con descarga real, llamando a `setup_start` directamente, sin agente, en carpetas aisladas: segunda llamada rechazada; SIGKILL con 2,2 GB descargados, estado `interrupted`; al relanzar continúa desde ahí y termina con imagen de prueba en 123 s. `doctor` en verde y `uninstall` funciona. Tras `uninstall` quedan carpetas en `comfyui/models`, sin revisar | 2026-10-31 |
| Imagen como contenido MCP | Claude Code con haiku describe la imagen recibida, con la ruta en la primera línea del resultado | 2026-10-31 |
