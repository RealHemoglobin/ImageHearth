# Plan: Fase 5

Rama: `feature/integracion-agentes`. Sin commits del asistente: los cambios se dejan en el árbol de trabajo para revisión.

## 1. Arranque sin ComfyUI

1. Comprobar qué falla hoy al arrancar el servidor sin ComfyUI, sin modelos y sin `config.toml`, y qué devuelve cada herramienta.
2. Hacer que cada herramienta explique qué falta y con qué comando se arregla, reutilizando el catálogo y `doctor`.
3. Tests: servidor sin instalación, sin ComfyUI y sin modelos, comprobando que importar `server` no carga `huggingface_hub` ni PyTorch.

## 2. Instrucciones y descripciones

1. Pasar lo esencial de la skill a `FastMCP(instructions=...)`: qué herramienta usar, cómo relatar la ruta y los `WARNING`, y qué hacer ante `recovery_required`.
2. Reescribir las descripciones para que cada herramienta se entienda por sí sola.
3. Dejar la skill como complemento, sin contradecir las instrucciones.
4. Test que compruebe que las `instructions` y las descripciones llegan por el protocolo MCP.

## 3. Reducción de herramientas

1. Confirmar con tests que `create_image` cubre todos los casos de `generate_image` y `edit_image`.
2. Dejar `create_image` como vía principal en instrucciones y descripciones.
3. La decisión sobre los nombres antiguos se toma en la tarea 11, con las mediciones. Hasta entonces se mantienen.

## 4. Comando `connect`

1. Crear un módulo con un descriptor por cliente: detección, ruta de configuración por sistema, formato y CLI oficial si existe. Verificar cada formato contra su documentación.
2. Implementar `connect --print <agente>`, que imprime el fragmento en JSON, TOML o YAML sin tocar nada.
3. Implementar `connect <agente>`: CLI oficial o edición con copia de seguridad, conservando el resto del archivo, sin duplicar entradas y usando la ruta absoluta del ejecutable.
4. Implementar `connect --detect`: lista los clientes encontrados y ofrece conectarlos, con confirmación.
5. Instalar la skill donde el agente la admita.
6. Añadir la retirada de entradas y registrar lo conectado, para que `uninstall` pueda deshacerlo sin tocar nada ajeno.
7. Comprobar `pi mcp` y decidir su caso según [requirements.md](requirements.md).
8. Tests con `tmp_path` por cliente: configuración vacía, con otras entradas, ya conectada y corrupta, copia de seguridad, repetición y rutas por sistema.

## 5. Documentación de agentes

1. Crear `docs/agents.md` con fragmento, método y nivel de soporte de cada cliente, en inglés.
2. Crear `llms-install.md`: los pasos para que un agente haga la instalación, preguntando antes al usuario.
3. Test que compare los fragmentos de `docs/agents.md` con la salida de `connect --print`.

## 6. Progreso, imagen y plazos

1. Emitir `ctx.report_progress` durante la generación, desde el hilo de trabajo hacia el bucle de eventos. Sin `Context` disponible, debe seguir funcionando igual.
2. Añadir a `create_image` el parámetro opcional que incluye la imagen como contenido MCP, con la ruta en la primera línea y sin cambios por defecto.
3. Medir el plazo real de cada cliente disponible con una generación lenta (`quality=high`, en frío), con y sin progreso, y anotarlo en la evidencia.
4. Solo si algún cliente corta: añadir `start_image_job` y `get_job`, avisando antes de que amplía el alcance.
5. Tests: progreso emitido, cancelación que limpia la sesión y las dos formas de respuesta.

## 7. Modo de memoria

1. Añadir `memory_mode` a `config.py`, con variable de entorno y `ollama_mode` como alias. Si están los dos, gana `memory_mode`.
2. Cambiar `get_provider` para que dependa de `memory_mode`. `auto` combina los proveedores detectados.
3. Implementar `manual`: no tocar modelos y comprobar la memoria libre antes de generar, con un error accionable si no basta.
4. Reflejar el modo en `doctor`, `get_engine_status`, la skill y las instrucciones.
5. Tests de precedencia y de cada modo. Los casos actuales de `ollama_mode` deben seguir pasando.

## 8. Proveedores de memoria

1. Comprobar en su documentación qué permite cada API: listar, descargar y restaurar.
2. Implementar los proveedores de llama.cpp (`llama-server`), LM Studio y vLLM. Donde no se pueda descargar, avisar antes de generar con un mensaje accionable.
3. Mantener en todos la distinción entre "no está" y "falló con modelos cargados", que conserva la protección actual.
4. Revisar que el registro de sesión y `recover_engine` funcionan con varios proveedores y con modelos pendientes de cada uno.
5. Tests con servidores HTTP simulados, incluidas la caída a mitad de sesión y la recuperación.
6. Probar con servidores reales los que estén disponibles.
7. Medir y documentar la VRAM necesaria para tener un modelo de lenguaje y la generación a la vez.

## 9. Instalación desde el agente

1. Añadir `setup_status`: lo instalado, lo que falta, perfiles posibles para el hardware, tamaños, licencias y progreso.
2. Añadir `setup_start`: exige `profile` y `accept_licenses`, rechaza perfiles experimentales y lanza `setup` con `platform/spawn.py`, de modo que sobreviva a la desconexión.
3. Guardar el progreso en un archivo de estado, con bloqueo para impedir dos instalaciones a la vez.
4. Añadir a las instrucciones la obligación de preguntar antes, indicando tamaño y licencias.
5. Tests con subprocesos simulados: sin aceptación, perfil inválido o experimental, ejecución doble, desconexión del servidor y fallo a mitad.

## 10. Pruebas con agentes reales

1. Conectar y probar cada cliente disponible partiendo de una configuración vacía: Claude Code, Codex, opencode, Hermes, pi y VS Code.
2. En cada uno: conectar, generar con `fast`, generar con `quality` y editar con Kontext.
3. Marcar el resto (Claude Desktop, Gemini CLI, Cursor, JetBrains) como sin probar en `docs/agents.md`.

## 11. Pruebas con modelos locales pequeños

1. Confirmar el servidor del puerto 11434 y preparar al menos un modelo de 7B a 14B.
2. Con opencode y Hermes, sin skill: elegir la herramienta correcta, pasar parámetros válidos, relatar el resultado y generar y editar con el modelo cargado, que debe recuperar su memoria al terminar.
3. Repetir con las 7 herramientas y con el conjunto reducido, midiendo aciertos, y decidir si `generate_image` y `edit_image` se quedan como alias. Aplicar la decisión.
4. Ajustar instrucciones y descripciones según lo observado, y documentar el tamaño mínimo que funciona.

## 12. Validación y cierre

1. Ejecutar la matriz de [validation.md](validation.md) y rellenar la evidencia.
2. Actualizar ambos README, `tech-stack.md`, `THIRD_PARTY_NOTICES.md` si procede y la skill.
3. Marcar en el roadmap las tareas hechas (el usuario revisa antes).
