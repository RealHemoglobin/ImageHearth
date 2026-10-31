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

- [ ] Claude Code.
- [ ] Codex.
- [ ] opencode.
- [ ] Hermes.
- [ ] pi, o documentado que no está soportado.
- [ ] VS Code.
- [ ] Configuración previa con otras entradas: se conserva y queda copia de seguridad, en al menos un cliente real.
- [ ] Restaurar las configuraciones reales de esta máquina al terminar las pruebas.

### `connect --print`

- [ ] Un cliente sin descriptor propio se conecta siguiendo solo `docs/agents.md`.

### Modelos locales pequeños (sin skill)

- [ ] Confirmado qué servidor escucha en el puerto 11434 y anotado el modelo usado.
- [ ] opencode: elige bien la herramienta, pasa parámetros válidos, relata el resultado, y genera y edita.
- [ ] Hermes: lo mismo.
- [ ] Modelo de lenguaje cargado al empezar y disponible de nuevo al terminar.
- [ ] Medición con las 7 herramientas y con el conjunto reducido.
- [ ] Tamaño mínimo que funciona, documentado.

### Memoria

- [ ] `auto`, `off` y `manual` con Ollama u otro servidor real.
- [ ] `manual` con memoria insuficiente: error accionable y sin tocar el modelo del usuario.
- [ ] Matar el proceso a mitad de sesión con un modelo cargado: `recover_engine` lo restaura.
- [ ] llama.cpp, LM Studio y vLLM: probados con el servidor real si se pueden ejecutar aquí. Si no, anotado como cubierto solo por tests simulados.
- [ ] VRAM para tener un modelo de lenguaje y la generación a la vez, medida en la RTX 4090.

### Instalación desde el agente

- [ ] Con un agente real, en carpetas aisladas y con el perfil `fast`: pregunta antes, instala y genera.
- [ ] Cerrar el agente a mitad: la instalación continúa y `setup_status` la refleja al volver.
- [ ] `llms-install.md`: un agente completa la instalación siguiéndolo.

### Generaciones largas

- [ ] Plazo medido en cada cliente disponible, con `quality` en frío.
- [ ] Progreso visible en los clientes que lo muestran.
- [ ] Imagen como contenido MCP en al menos un cliente con visión.

## Lista para fusionar

- [ ] `scripts/check.sh` en verde en Linux y `scripts\check.ps1` en verde en Windows.
- [ ] Prueba de contrato `/object_info` en verde.
- [ ] Validaciones manuales completadas.
- [ ] Ningún documento anuncia como soportado un cliente sin probar.
- [ ] Ambos README, `tech-stack.md` y la skill actualizados.
- [ ] `docs/agents.md` y `llms-install.md` creados.
- [ ] Roadmap actualizado con las tareas hechas.
- [ ] Cambios revisados por el usuario, que realiza el commit.

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` en Linux | | |
| `scripts\check.ps1` en Windows | | |
| Prueba de contrato `/object_info` | | |
| Claude Code | | |
| Codex | | |
| opencode | | |
| Hermes | | |
| pi | | |
| VS Code | | |
| Claude Desktop, Gemini CLI, Cursor, JetBrains | Sin probar | |
| Modelo local y tamaño mínimo | | |
| Coste de los alias y decisión tomada | | |
| Plazo de cada cliente | | |
| `memory_mode` con servidor real | | |
| llama.cpp, LM Studio y vLLM | | |
| VRAM con modelo de lenguaje y generación | | |
| `setup_start` y desconexión | | |
