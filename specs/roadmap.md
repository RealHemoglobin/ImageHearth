# Roadmap hacia la distribución pública

Contexto: [misión](mission.md), [análisis del estado actual](analysis.md) y [stack y decisiones](tech-stack.md).

## Destino

```bash
# macOS o Linux
curl -LsSf https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.sh | sh
```

```powershell
# Windows
irm https://raw.githubusercontent.com/RealHemoglobin/ImageHearth/main/install.ps1 | iex
```

El comando instala uv y el paquete, detecta el hardware, propone un perfil, muestra licencias y espacio, instala ComfyUI y los modelos, conecta los agentes detectados y genera una imagen de prueba.

## Mapa

| Fase | Resultado | Tamaño | Depende de |
|---|---|---|---|
| 0. Preparación | Decisiones cerradas y verificación local | S | — |
| 1. Empaquetado | Se instala como paquete, aún en Linux | M | 0 |
| 2. Portabilidad | El servidor funciona en los tres sistemas; Ollama opcional | L | 1 |
| 3. Instalador | `setup` y `doctor` dejan un sistema funcionando | XL | 2 |
| 4. Perfiles y macOS | Modelos según hardware; macOS preparado sin probar | L | 3 |
| 5. Agentes | Conexión con un comando y generaciones largas fiables | M | 2 |
| 6. Beta pública | v0.1 en PyPI y en el registro MCP | M | 3, 5 |
| 7. Adaptación al hardware | La mejor calidad que cabe en cada equipo y modelos de lenguaje que se paran y vuelven | L | 4, 5, 6 |
| 8. Generación por lotes | Varias imágenes en una sola sesión de GPU | M | 5, 7 |
| 9. Elección del modelo de `quality` | FLUX.1 Dev, FLUX.1 Schnell o SDXL 1.0, intercambiables con `setup` | L | 3, 7 |
| 10. v1.0 | macOS experimental y matriz de pruebas completa | M | 6, 7, 8, 9 |

**macOS no bloquea ninguna fase:** no hay Mac disponible, así que se deja preparado sin probar y sin anunciarlo como soportado. Solo sube de nivel cuando se pruebe con hardware real. La fase 5 se puede hacer en paralelo a la 3.

---

## Fase 0: Preparación

**Objetivo:** cerrar lo que sería caro cambiar después.

- [x] Decidir nombre, licencia y dueño del repositorio (ver [decisiones abiertas](#decisiones-abiertas)).
- [x] Añadir `LICENSE` y `THIRD_PARTY_NOTICES.md`.
- [x] Revisar las licencias de FLUX y SDXL Turbo.
- [x] Conseguir acceso a hardware Windows con NVIDIA. El Mac con Apple Silicon sigue pendiente para la fase 4.
- [x] Fusionar `robustez` en `main`: sus commits ya estaban en `main`.
- [x] ~~Crear CI en Linux~~ Descartado: no se usan GitHub Actions. La verificación es local con `scripts/check.sh` (lint, tests y tests contra el wheel instalado).
- [x] Definir el entorno de desarrollo, de forma que los tests no dependan del venv de ComfyUI.

**Listo cuando:** `scripts/check.sh` pasa en `main` y no hay decisiones abiertas que bloqueen la fase 1.

## Fase 1: Empaquetado

**Objetivo:** convertir el repositorio en un paquete instalable, sin cambiar su comportamiento.

- [x] Pasar a `src/imageengine_mcp/` y eliminar la carpeta `mcp/`, que choca con la dependencia.
- [x] Ampliar `pyproject.toml` con el comando `imageengine-mcp` y retirar `requirements.txt`, que se mantiene mientras el README lo use para instalar.
- [x] Incluir workflows, skill y nodo personalizado como datos de paquete, leídos con `importlib.resources`.
- [x] Reescribir `config.py`: `platformdirs`, `config.toml` y variables de entorno para ruta de ComfyUI, puerto, salida y Ollama.
- [x] Sacar del código `sys.path.insert` y los `__main__` por módulo; la CLI los sustituye.
- [ ] Migrar la instalación actual: mantener `~/AI/ComfyUI` por configuración y actualizar `~/.claude.json`, `~/.codex/config.toml` y el enlace de la skill.

**Listo cuando:**
- `uv tool install ./` en un usuario limpio de Linux expone las 7 herramientas.
- Todos los tests pasan contra el paquete instalado, no contra el código fuente.
- La instalación actual sigue generando imágenes.
- Los datos del usuario no se escriben dentro de `site-packages`.

## Fase 2: Portabilidad del núcleo

**Objetivo:** eliminar cada bloqueo de las secciones B y C del [análisis](analysis.md).

- [x] Crear `platform/`: procesos con `psutil`, bloqueos con `filelock`, rutas del venv y arranque desacoplado por sistema.
- [x] Sustituir la rotación compartida de logs.
- [x] Declarar `encoding="utf-8"` en toda lectura y escritura de texto.
- [x] Reintentar `os.replace` ante bloqueos transitorios en Windows.
- [x] Abstraer la memoria de GPU: `/system_stats` y después `nvidia-smi`.
- [x] **Hacer Ollama opcional:** `auto` u `off`. Si no responde en `auto`, no hay nada que descargar ni restaurar, y el estado no pasa a `degraded`.
- [x] **Diseñar la liberación de memoria como interfaz de proveedores** (`MemoryProvider`: listar lo cargado, descargar y restaurar), con Ollama como primera implementación. Es la base para la fase 5; no se implementan otros servidores aquí.
- [x] Distinguir "Ollama no está" de "Ollama falló con modelos cargados": en el segundo caso se conserva la protección actual.
- [x] **Corregir el nodo:** devolver un `ComfyExtension` válido o registrar la ruta con otro mecanismo, y añadir una versión al endpoint.
- [x] **Si falta el nodo:** usar como alternativa la memoria libre de `/system_stats`, avisar y no entrar en bucle de `recovery_required`.
- [x] Registrar con PID la instancia gestionada y no reiniciar ni matar nunca una ajena.
- [x] Traducir mensajes a inglés y renombrar `ADVERTENCIA` a `WARNING`, junto con la skill.
- [x] Ejecutar `scripts/check.sh` (con una versión para PowerShell) en las máquinas Windows y macOS, y añadir la prueba de contrato con `/object_info`. Hecho: `check.ps1`, `contract.sh` y `contract.ps1`, y verificado en Linux. Windows verificado (`check.ps1` en verde). macOS sin verificar y no anunciado como soportado.

**Listo cuando:**
- Los tests pasan en los tres sistemas.
- Una generación completa funciona sin Ollama, verificado con hardware real en Linux.
- Una generación real funciona en Windows con NVIDIA y ComfyUI instalado a mano.
- Se ha probado matar el proceso a mitad de sesión en Windows y la recuperación funciona.
- ComfyUI ya no muestra `IMPORT FAILED`.

## Fase 3: Instalador

**Objetivo:** `imageengine-mcp setup` lleva una máquina limpia a un sistema funcional.

**Spike inicial (máximo 2 días):** comparar el instalador propio con `comfy-cli` en Linux y Windows, y validar la decisión de [tech-stack](tech-stack.md).

- [x] **Detección:** sistema, arquitectura, GPU, driver, VRAM, RAM, disco, ComfyUI existente (incluido Desktop), Ollama, LM Studio, llama.cpp y vLLM.
- [x] **Manifiesto** `models.toml`: repositorio, revisión fijada, ruta, tamaño, SHA-256, licencia y workflows que habilita. Partir de la tabla verificada del análisis.
- [x] **ComfyUI:** descargar una versión fijada, crear el entorno con uv y Python gestionado, instalar el PyTorch adecuado e instalar el nodo.
- [x] **Modo adjunto:** usar un ComfyUI existente, instalar el nodo con permiso y configurar URL y rutas.
- [x] **Modelos:** descarga reanudable con verificación SHA-256, que no vuelva a descargar lo que ya existe.
- [x] **Consentimiento:** mostrar espacio, licencias y enlaces antes de descargar. En modo no interactivo, exigir `--accept-licenses`.
- [x] **Comprobaciones previas:** disco insuficiente, driver ausente, GPU sin soporte o puerto ocupado; cada una con un mensaje accionable.
- [x] **`doctor`:** comprobar cada capa, con salida legible y `--json`.
- [x] **`update` y `uninstall`:** registrar en un manifiesto qué se instaló; no borrar nunca nada ajeno ni, sin confirmación, los modelos.
- [x] **Mostrar el resumen de lo que se va a descargar antes de hacerlo y permitir elegir el perfil**, para que quien ya usa modelos locales pueda empezar solo con `fast` y poco disco.
- [x] Prueba de humo final con una imagen pequeña.

**Listo cuando:**
- Funciona en máquinas virtuales o equipos limpios: Ubuntu y Windows 11 con NVIDIA.
- Interrumpir la descarga y repetir el comando continúa donde se quedó.
- Un archivo corrupto se detecta y se vuelve a descargar.
- Con espacio insuficiente falla antes de descargar nada.
- `uninstall` deja intactos un ComfyUI y unos modelos preexistentes.

**Estado:** completada por decisión del usuario el 2026-10-31. Las pruebas en máquinas limpias no constan en la [evidencia](2026-10-31-instalador/validation.md#evidencia), que recoge lo pendiente.

## Fase 4: Perfiles y macOS

**Objetivo:** el hardware decide qué se ofrece y nada se anuncia sin haberlo probado.

- [x] Hacer dinámico el catálogo: `list_workflows`, `quality` y los errores se basan en lo instalado. Un error dice qué perfil instalar.
- [x] Separar en `build_workflow` el cargador de modelo de los identificadores de nodo fijos.
- [ ] Medir VRAM y tiempo reales por perfil y documentarlos. Hecho en Linux con la RTX 4090; falta Windows.
- [x] Elegir cuantización y codificador T5 para Mac, sin medir.
- [x] Crear workflows y manifiesto para Mac, con hashes fijados, y dejar `setup` y `doctor` preparados tras `--experimental`.
- [x] Sin Mac: ejecutar los workflows GGUF en NVIDIA y cubrir lo propio de macOS con tests simulados.
- [ ] **Cuando haya un Mac (no bloquea):** comprobar que ComfyUI, `ComfyUI-GGUF`, FLUX y Kontext funcionan en MPS.
- [ ] Añadir perfil GGUF para NVIDIA con poca VRAM si las mediciones lo justifican.
- [ ] Buscar un origen más estable para FLUX Dev.
- [ ] Evaluar FLUX.1 Schnell como opción Apache-2.0 para uso comercial; su repositorio oficial exige aprobación automática. Pasa a la [fase 9](#fase-9-elección-del-modelo-de-quality).

**Listo cuando:**
- macOS queda preparado tras `--experimental`, documentado como sin probar y sin anunciarse como soportado.
- La tabla de requisitos del README contiene mediciones reales de Linux y Windows.

**Plan B:** si un informe real descarta Kontext en Mac, se ofrece generación en macOS y se marca la edición como no disponible.

## Fase 5: Integración con agentes

**Objetivo:** funcionar igual en cualquier agente, tenga o no skills, y que un usuario con modelos locales pueda instalarlo con facilidad y compaginarlo con ellos en la misma GPU.

**Principio:** el servidor MCP estándar por stdio es el producto. Cada agente o editor es solo una forma de conectarlo, y el soporte de uno nuevo no debe exigir cambios en el motor.

- [x] `connect <agente>` y `connect --detect`, usando la CLI oficial si existe o editando su configuración con copia de seguridad.
- [x] **`connect --print <agente>`:** imprime el fragmento de configuración (JSON, TOML o YAML) sin tocar nada, para cualquier cliente que no esté soportado, y una página `docs/agents.md` con el fragmento de cada uno.
- [ ] Soporte inicial de agentes: Claude Code, Claude Desktop, Codex, Gemini CLI, **opencode y Hermes**. Verificar cada formato contra su documentación y probarlo con un modelo local real.
- [ ] Soporte inicial de editores: Cursor, VS Code e **IntelliJ y otros JetBrains**. Verificar cada configuración contra su documentación.
- [x] **pi:** comprobar si admite MCP. Si no, valorar un adaptador pequeño (extensión o llamada a la CLI) o documentar que no está soportado.
- [x] **Pasar lo esencial de la skill a `FastMCP(instructions=...)`, de forma obligatoria:** los agentes con modelos locales no cargan skills. Las descripciones de cada herramienta deben bastar por sí solas. Dejar la skill como complemento e instalarla donde el agente la admita.
- [x] **Probar con modelos locales pequeños** (por ejemplo 7B–14B con Ollama o llama.cpp) en opencode y Hermes: elegir la herramienta correcta, pasar parámetros válidos y relatar el resultado. Documentar el tamaño mínimo que funciona.
- [x] Hacer que el servidor arranque sin ComfyUI y que cada herramienta explique qué falta.
- [x] Añadir `setup_status` y `setup_start`. El segundo exige perfil y aceptación explícita, lanza un proceso que sobrevive a la desconexión e informa de su progreso. Las instrucciones obligan al agente a preguntar antes, porque descarga decenas de GB.
- [ ] Publicar `llms-install.md` para pedirle la instalación al agente.
- [x] Emitir progreso con `ctx.report_progress` durante la generación.
- [x] **Medir el plazo real de cada cliente.** Solo si alguno corta las generaciones, añadir `start_image_job` y `get_job`.
- [x] Devolver la ruta y, de forma opcional, la imagen como contenido MCP, manteniendo la ruta en la primera línea.
- [x] **Reducir las herramientas expuestas:** `create_image` cubre a `generate_image` y `edit_image`. Menos herramientas y parámetros más simples ayudan a los modelos pequeños. Mantener los nombres antiguos como alias solo si se mide que cuestan poco.
- [ ] **Compaginar con modelos locales en la misma GPU:** implementar `MemoryProvider` para llama.cpp (`llama-server`), LM Studio y vLLM, además de Ollama. Si el servidor no permite descargar el modelo, avisar con un mensaje accionable en lugar de fallar por falta de memoria. Documentar la VRAM necesaria para tener un modelo de lenguaje y la generación a la vez.
- [x] Opción `memory_mode` en `config.toml`: `auto`, `off` o `manual`. En `manual`, el motor no toca los modelos del usuario y solo comprueba la memoria libre antes de generar.

**Estado (2026-10-31):** pendientes sin marcar: Claude Desktop, Gemini CLI y los editores no se han probado con un cliente real; `llms-install.md` está escrito, pero ningún agente lo ha seguido; los proveedores de llama.cpp, LM Studio y vLLM solo tienen tests simulados. Ver la [evidencia](2026-10-31-integracion-agentes/validation.md#evidencia).

**Listo cuando:**
- En cada agente y editor soportado se puede conectar, generar con `fast`, generar con `quality` y editar con Kontext, partiendo de una configuración vacía.
- Con al menos un modelo local de lenguaje (opencode u Hermes) se genera y se edita una imagen sin ayuda, con el modelo de lenguaje cargado y devolviendo su memoria al terminar.
- Un cliente sin soporte propio se conecta con `connect --print` y la documentación.

## Fase 6: Beta pública

**Objetivo:** cualquiera con Linux o Windows y NVIDIA puede instalarlo.

- [ ] `install.sh` e `install.ps1`, breves y legibles: instalar uv, instalar la herramienta con versión fijada y lanzar `setup`.
- [ ] Publicar desde la máquina del mantenedor, sin GitHub Actions: `uv publish` a PyPI con un token y `gh release create` para la GitHub Release.
- [ ] Publicar en el registro oficial de MCP con `server.json`.
- [x] ~~Añadir `.mcpb` para Claude Desktop~~ No se crea: Claude Desktop sigue con `connect` y consta como sin probar.
- [x] Reescribir el README: la instalación de un comando pasa a ser la principal y se quita el aviso de desarrollo.
- [x] Añadir guía de problemas frecuentes, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md` y plantillas de incidencias que pidan la salida de `doctor --json`.
- [ ] Reunir entre 5 y 10 probadores externos en hardware distinto.

**Estado (2026-11-01):** rama lista para fusionar. Los scripts, la guía de publicación y `server.json` están escritos, sin marcar hasta publicar. `install.ps1` se ha ejecutado en Windows 11 con NVIDIA desde un clon, con `check.ps1` en verde y generación `fast` y `quality` con Claude Code; faltan la máquina limpia, `contract.ps1` y las mediciones de Windows. La publicación sigue bloqueada por lo pendiente en la [validación](2026-10-31-beta-publica/validation.md#antes-de-publicar-pendientes-de-fases-anteriores).

**Listo cuando:** al menos 3 personas externas instalan y generan sin ayuda, y los fallos de instalación se pueden diagnosticar con `doctor --json`.

## Fase 7: Adaptación al hardware

**Objetivo:** cada equipo obtiene la mejor calidad que cabe en su hardware, aunque vaya más lento, y los modelos de lenguaje del usuario se apartan y vuelven sin intervención.

**Contexto (2026-11-04):** en una AMD de 16 GB en Windows, FLUX Dev fp8 (12 GB de modelo y 5 GB de T5) va muy justo. Con un `llama-server` de un solo modelo, el motor solo avisa y genera compartiendo la GPU, porque su API no permite descargarlo.

### Instalación

- [ ] **`imagehearth-mcp` queda en el PATH tras instalar** en Linux, Windows y macOS. Los instaladores ejecutan `uv tool update-shell` (con aviso) en lugar de solo sugerirlo, y comprueban en un shell nuevo que el comando se encuentra. Cubrir zsh, bash, fish y PowerShell, y `uv` instalado por el instalador oficial, por el gestor del sistema o ya presente.
- [x] `doctor` comprueba que el comando está en el PATH y, si no, da la orden exacta para arreglarlo.

### Memoria de ComfyUI

- [ ] **Descarga parcial a RAM:** medir cómo carga ComfyUI FLUX en 16 GB y menos (`NORMAL_VRAM` ya carga por partes) y ajustar los argumentos de arranque según el hardware: `--reserve-vram`, `--lowvram` o `--novram`, y el comportamiento en ROCm Windows.
- [x] Opción `comfy_args` en `config.toml` para añadir argumentos propios, y que `doctor` muestre los que se usan.
- [x] Revisar las comprobaciones de memoria del motor (`min_vram_mib` y `_check_free_memory`) para que no rechacen un modelo que cabe con descarga parcial; usar la RAM libre como segundo límite.
- [x] Reproducir una tarjeta de 16 GB en la RTX 4090 con `--reserve-vram` y medir tiempo y memoria de cada variante.

### Variantes de `quality` según el hardware

- [ ] **Escalera de variantes** elegida por VRAM y RAM, tanto en `setup` como al generar:
  - 20 GB o más: FLUX Dev fp8 (actual).
  - De 12 a 20 GB: FLUX Dev GGUF Q5 con T5 GGUF (los workflows ya existen para Mac) y descarga parcial si hace falta.
  - De 8 a 12 GB: **SDXL 1.0 afinado con LoRAs** de detalle, sin T5.
- [x] Elegir el checkpoint SDXL y las LoRAs por licencia (preferir OpenRAIL++ o similar, que permiten uso comercial), calidad y origen estable en Hugging Face, con revisión y SHA-256 fijados en `models.toml`.
- [x] Crear el workflow `sdxl_quality` (checkpoint, LoRAs, más pasos y resolución nativa de 1024) e incluirlo en `VARIANTS["high"]`.
- [ ] Perfiles nuevos o variantes de `quality`/`full` para NVIDIA y AMD con poca VRAM, con `min_vram_mib` medido.
- [ ] Comparar la calidad de las tres variantes con los mismos prompts y documentarla en el README.

### Modelos de lenguaje que se paran y vuelven

- [ ] **llama.cpp de un solo modelo:** si la API no permite descargar, localizar el proceso `llama-server` que escucha en el puerto, guardar su línea de comandos, directorio y entorno, pararlo y rearrancarlo igual al terminar. Funciona en Linux, Windows y macOS con `psutil` y `spawn`.
- [x] Solo se para un proceso del mismo usuario e identificado como `llama-server`; si no se puede reproducir su arranque (servicio del sistema, contenedor, otro usuario), se avisa como ahora.
- [x] Guardar la línea de arranque en el estado de sesión, para que `recover_engine` lo rearranque tras una caída del motor.
- [ ] Probar con un `llama-server` real y un modelo pequeño en Linux; Windows con el binario oficial; macOS sin probar.
- [x] Valorar el mismo enfoque para LM Studio sin API de descarga y para vLLM sin modo de reposo.

**Spike de llama.cpp (2026-11-04, Linux, build b12101 Vulkan, Qwen2.5-0.5B Q4_K_M):**
- Un solo modelo: el proveedor actual devuelve `unloadable: False` y el motor solo avisa; ese es el fallo observado.
- Prototipo con `psutil`: localizar `llama-server` del mismo usuario por el puerto en escucha, guardar `exe()`, `cmdline()`, `cwd()` y `environ()`, `terminate()` y relanzar con `spawn.detached_options()`. Libera la VRAM al instante y vuelve en 0,5 s con la misma línea, directorio, modelo y `n_ctx`, y responde.
- Usar `exe()` y no `cmdline()[0]`, que puede ser relativo (`./llama-server`). La salida del relanzado va a un log propio, porque la terminal original ya no existe.
- Modo router (`--models-dir`): el proveedor actual descarga y restaura correctamente contra un servidor real, no solo en tests simulados.
- Riesgos por cubrir: en macOS `environ()` puede dar `AccessDenied` (usar el entorno propio y avisar); un servicio de systemd o un contenedor no se debe relanzar desde aquí; en Windows, ocultar la consola al relanzar.
- El puerto 8080 por defecto estaba ocupado por otro programa (SearXNG): la identificación por `/props` lo descartó correctamente.

**Listo cuando:**
- Tras `install.sh` o `install.ps1`, `imagehearth-mcp` funciona en una terminal nueva sin pasos manuales.
- En una tarjeta de 16 GB (real o simulada) `quality` genera sin quedarse sin memoria, aunque tarde más.
- En una de 8 GB `quality` genera con la variante SDXL.
- Con un `llama-server` de un solo modelo cargado, una generación lo para, genera y lo deja respondiendo con el mismo modelo y los mismos parámetros.

## Fase 8: Generación por lotes

**Objetivo:** que un agente con una lista de imágenes por hacer las pida todas de una vez y el motor las genere en una sola sesión de GPU: descarga los modelos de lenguaje una vez, genera todas las imágenes seguidas en ComfyUI y libera la memoria y restaura los modelos al final.

Hoy cada `create_image` es una sesión completa: descargar el modelo de lenguaje, arrancar ComfyUI, cargar los pesos, generar, liberar ComfyUI y restaurar el modelo. Con diez imágenes se repite diez veces, y con un modelo local el agente además recarga su propio modelo entre una petición y la siguiente. `generation_session` ya agrupa todo ese ciclo, así que el lote cabe dentro de una sola sesión.

### Herramienta

- [ ] Herramienta nueva `create_images` con `items`: una lista de peticiones con los mismos campos que `create_image` (`prompt`, `quality`, `width`, `height`, `negative_prompt`, `image_paths`, `workflow`, `mode`). Solo `prompt` es obligatorio en cada una.
- [ ] Valores comunes opcionales al nivel del lote (`quality`, `width`, `height`, `negative_prompt`) que cada elemento puede sobrescribir, para que el agente no repita lo mismo en cada prompt.
- [ ] **Lote homogéneo:** un lote es solo de generaciones o solo de ediciones con Kontext, nunca mezclado, para no cargar en ComfyUI modelos distintos dentro de la misma sesión. El tipo se deduce de los elementos (con o sin `image_paths`, o `mode`) y un lote mezclado se rechaza entero indicando qué elementos no encajan.
- [ ] Validar el lote completo antes de tocar la GPU: tipo homogéneo, prompts, tamaños, rutas de referencia y workflows instalados. Si algo no es válido, se rechaza el lote entero sin descargar nada y el error dice qué elemento falla.
- [ ] Máximo de 20 elementos por lote por defecto, para no retener el motor demasiado tiempo frente a otros clientes. Se guarda en la configuración y `imagehearth-mcp setup` permite cambiarlo con una opción (`--batch-limit N`, junto a `--port`); `doctor` muestra el valor en uso.
- [ ] `create_image` no cambia: sigue siendo la herramienta para una sola imagen y la que usan los modelos pequeños.

### Motor

- [ ] Un único `generation_session` para todo el lote: descarga y restauración de los modelos de lenguaje una sola vez, y ComfyUI arrancado una sola vez.
- [ ] VRAM necesaria del lote = la del workflow más exigente que contenga; la comprobación de memoria libre se hace una vez al principio.
- [ ] En los lotes de generación, agrupar internamente por workflow (SDXL Turbo, FLUX Dev, SDXL afinado) para que ComfyUI no cambie de pesos más de lo necesario, conservando el orden original en la respuesta. Los lotes de edición usan siempre Kontext.
- [ ] Generar las imágenes una tras otra dentro de la sesión, reutilizando `run_workflow` y el camino de Kontext; cada una con su semilla aleatoria y su propio plazo, como ahora.
- [ ] Un fallo en una imagen no aborta el lote: se registra el error de ese elemento y se sigue con el siguiente. Solo se aborta si el motor queda inutilizable (ComfyUI caído, `RecoveryRequired`).
- [ ] Cancelar detiene el lote tras la imagen en curso; las ya generadas se conservan y se devuelven, y la limpieza de la sesión se ejecuta igual.
- [ ] El estado de sesión registra el lote en curso para que `recover_engine` funcione igual que con una sola imagen.

### Respuesta y progreso

- [ ] Una línea por elemento, en el orden pedido: `1: /ruta/imagen.png` o `1: ERROR: motivo`. Las advertencias generales del lote van al final con el prefijo `WARNING:` de siempre.
- [ ] El progreso dice en qué imagen va (`Generating image 3 of 10 (45s)`), para que el cliente mantenga viva la petición y el usuario vea el avance.
- [ ] `include_image` en el lote queda fuera o limitado a miniaturas, porque varias imágenes completas llenan el contexto del agente.

### Agentes y documentación

- [ ] Actualizar las instrucciones del servidor MCP y la skill `imagehearth`: si el agente ya sabe que va a crear varias imágenes independientes, que use `create_images` en lugar de llamar varias veces a `create_image`.
- [ ] Dejar claro que cada elemento es independiente: un elemento no puede editar el resultado de otro del mismo lote. Las cadenas de ediciones siguen siendo llamadas sucesivas.
- [ ] Dejar claro que generaciones y ediciones van en lotes separados: si el agente necesita ambas, hace dos llamadas a `create_images`.
- [ ] Sección en el README con un ejemplo y el ahorro medido.

### Pruebas

- [ ] Pruebas simuladas: con N elementos, la descarga y la restauración de los modelos de lenguaje y el arranque de ComfyUI ocurren una sola vez; un fallo intermedio no impide los siguientes; la cancelación conserva las imágenes ya hechas y restaura los modelos; un lote mezclado o por encima del límite se rechaza sin tocar la GPU; el límite configurado en `setup` se respeta.
- [ ] Prueba real etiquetada: lote de cuatro imágenes `fast` y dos `high` con un modelo de Ollama cargado, comparando el tiempo con seis llamadas a `create_image`.
- [ ] Prueba real etiquetada: lote de tres ediciones con Kontext, comparando el tiempo con tres llamadas sueltas.
- [ ] Probar con un agente real (Claude Code y un modelo local de la fase 5) que elige `create_images` cuando tiene una lista y `create_image` cuando tiene una sola.

**Decisiones cerradas el 2026-11-05:**

- **Herramienta aparte:** `create_images`, nueva. `create_image` mantiene su firma simple para los modelos pequeños.
- **Ediciones con Kontext:** se permiten desde la primera versión, pero un lote es solo de generaciones o solo de ediciones, nunca ambas, para no cargar modelos distintos en la misma sesión.
- **Límite del lote:** 20 elementos por defecto, configurable con `imagehearth-mcp setup`.

**Listo cuando:**

- Un agente pide diez imágenes en una llamada y el modelo de lenguaje se descarga y se restaura una sola vez.
- Un lote de generaciones y otro de ediciones tardan claramente menos que las mismas imágenes en llamadas separadas, y la diferencia está medida en el README.
- Un lote que mezcla generaciones y ediciones, o que supera el límite, se rechaza antes de tocar la GPU con un error que lo explica.
- Cambiar el límite con `imagehearth-mcp setup` se refleja en `create_images` y en `doctor`.
- Si una imagen del lote falla, el resto se genera y la respuesta indica cuál falló y por qué.
- Cancelar a mitad deja la GPU libre, el modelo de lenguaje restaurado y las imágenes hechas en disco.

## Fase 9: Elección del modelo de `quality`

**Objetivo:** al instalar `quality` o `full`, el usuario elige el modelo de generación de calidad entre FLUX.1 Dev, FLUX.1 Schnell y SDXL 1.0. Después puede cambiarlo con `imagehearth-mcp setup`, que borra el anterior, para comparar resultados entre modelos o para quedarse con uno de licencia comercial.

**Contexto:** FLUX.1 Dev y FLUX.1 Kontext Dev tienen licencia no comercial. FLUX.1 Schnell es Apache-2.0 y SDXL 1.0 es OpenRAIL++, ambas con uso comercial. `fast` sigue con SDXL Turbo y la edición sigue con Kontext; solo cambia el modelo de `quality`. Solo hay un modelo de `quality` instalado a la vez.

| Capacidad | Modelo | Elección |
|---|---|---|
| `fast` | SDXL Turbo | Fijo |
| `quality` | FLUX.1 Dev, FLUX.1 Schnell o SDXL 1.0 | Uno, elegido en `setup` |
| Edición (`full`) | FLUX.1 Kontext Dev | Fijo |

### Catálogo y manifiesto

- [ ] Separar el **perfil** (qué capacidades: `fast`, `quality`, `full`) del **modelo de `quality`** (`flux-dev`, `flux-schnell` o `sdxl`). El perfil sigue diciendo qué se instala; el modelo de `quality` decide qué pesos de generación de calidad lo componen.
- [ ] Añadir FLUX.1 Schnell a `models.toml` con repositorio, revisión, SHA-256, tamaño y licencia `apache-2`. Reutiliza T5, CLIP-L y el VAE de FLUX. El repositorio oficial exige aprobación automática: documentar `HF_TOKEN` o elegir un origen alternativo estable (por ejemplo la versión fp8 reempaquetada para ComfyUI).
- [ ] Añadir SDXL 1.0 a `models.toml` (`stabilityai/stable-diffusion-xl-base-1.0`, `openrail-pp`), con revisión y SHA-256 fijados. Se usa con la misma LoRA de detalle que ya instala la fase 7 y sustituye a RealVisXL en `quality-sdxl`.
- [ ] **Refiner de SDXL:** comparar base con LoRA frente a base con LoRA y refiner (`stabilityai/stable-diffusion-xl-refiner-1.0`, `openrail-pp`) usando los mismos prompts y semillas. Si el refiner mejora la calidad, se incluye en el workflow y en el manifiesto; si no, se queda solo el modelo base.
- [ ] **FLUX.1 Schnell con poca VRAM:** medir durante la implementación si fp8 genera bien con 12 GB y descarga parcial a RAM. Solo se añade una variante GGUF si las mediciones lo piden.
- [ ] Combinar la elección con la escalera de variantes de la [fase 7](#fase-7-adaptación-al-hardware): el usuario elige la familia y el hardware decide la precisión (fp8 o GGUF) cuando exista.
- [ ] **El hardware recomienda y el usuario decide:** se ofrecen siempre los tres modelos. Si el elegido pide más VRAM o RAM de la que hay, se permite instalarlo igualmente con una advertencia que da el mínimo medido y la memoria detectada.
- [ ] En `full`, Kontext sigue necesitando T5, CLIP-L y el VAE de FLUX aunque el modelo de `quality` sea SDXL: el manifiesto los incluye por Kontext y no por el modelo de `quality`.
- [ ] Registrar el modelo de `quality` elegido en el manifiesto de instalación.

### Workflows

- [ ] Workflow `flux_schnell`: 4 pasos, sin CFG ni guía, con los parámetros recomendados del modelo.
- [ ] Workflow `sdxl_base`: resolución nativa de 1024, pasos y CFG propios de SDXL base.
- [ ] Incluirlos en `VARIANTS["high"]`; el catálogo usa el que esté instalado, como ahora.
- [ ] `list_workflows`, `get_engine_status` y `doctor` muestran qué modelo de `quality` está activo y su licencia.
- [ ] Guardar en los metadatos del PNG el modelo y el workflow que generaron cada imagen, para poder comparar después.

### Instalación

- [ ] Al elegir `quality` o `full` en `setup` interactivo, preguntar el modelo de `quality` mostrando de cada opción el tamaño de descarga, la VRAM mínima, la licencia y si permite uso comercial. Se marca como recomendada la que mejor encaja con el hardware, sea cual sea su licencia, y las que no caben se muestran con su advertencia en lugar de ocultarse.
- [ ] Modo no interactivo: `--quality-model {flux-dev,flux-schnell,sdxl}`. Si falta, se usa la recomendación según el hardware y se indica en la salida. Si el modelo pedido no cabe en el hardware, se instala igual y se emite la advertencia.
- [ ] `setup_status` lista los modelos de `quality` con tamaño, licencia, uso comercial, cuál se recomienda y si cabe en el hardware. `setup_start` acepta `quality_model` opcional y devuelve la advertencia de hardware si la hay. Las instrucciones del servidor obligan al agente a decir al usuario qué modelo, licencia y advertencias tiene la instalación antes de llamarlo, y a dejarle elegir a él.
- [ ] El consentimiento de licencias muestra solo las de lo que se va a descargar: con Schnell o SDXL no aparece la licencia no comercial de FLUX Dev salvo que se instale Kontext.

### Cambio de modelo

- [ ] `imagehearth-mcp setup` sobre una instalación existente muestra el modelo de `quality` actual y permite cambiarlo por otro, de forma interactiva o con `--quality-model`.
- [ ] Antes de cambiar, mostrar qué se descarga, qué se borra y el espacio que se libera, y pedir confirmación (o `--yes` en modo no interactivo).
- [ ] Descargar y verificar primero el modelo nuevo y borrar el anterior solo después: si la descarga se interrumpe o falla, la instalación sigue funcionando con el modelo anterior y repetir el comando continúa donde se quedó.
- [ ] Borrar solo archivos que ImageHearth instaló (según el manifiesto de instalación) y que ningún otro componente instalado use: T5, CLIP-L y el VAE se conservan si los necesita Kontext o el modelo nuevo. Los modelos preexistentes o del modo adjunto no se borran nunca.
- [ ] Comprobar el espacio libre teniendo en cuenta que durante el cambio conviven ambos modelos.
- [ ] Rechazar el cambio mientras haya una generación en curso, y reiniciar el ComfyUI gestionado si estaba en marcha para que no siga con los pesos anteriores en memoria.
- [ ] Las imágenes ya generadas no se tocan.

### Documentación

- [ ] Tabla en el README con los tres modelos de `quality`: licencia, uso comercial, tamaño, VRAM y tiempo medidos.
- [ ] Comparativa con los mismos prompts y semillas en los tres modelos, documentada en el README. Sustituye a la comparación de variantes pendiente de la fase 7.
- [ ] Explicar cómo cambiar de modelo y que, en `full`, la edición con Kontext sigue siendo no comercial.
- [ ] Los errores de "no instalado" y la skill `imagehearth` mencionan `--quality-model` cuando proceda.

### Pruebas

- [ ] Pruebas simuladas: la elección se registra en el manifiesto; el catálogo usa el workflow del modelo instalado; el cambio descarga antes de borrar; un fallo a mitad deja el modelo anterior funcionando; los archivos compartidos con Kontext se conservan; los modelos preexistentes no se borran; el cambio se rechaza con una generación en curso.
- [ ] Prueba real etiquetada: generar el mismo prompt con la misma semilla con cada uno de los tres modelos en la RTX 4090, cambiando con `setup` entre uno y otro.
- [ ] Prueba real etiquetada: ciclo `flux-dev` → `flux-schnell` → `sdxl` → `flux-dev` en un perfil `full`, comprobando tras cada cambio que la edición con Kontext sigue funcionando y que el disco usado vuelve al de partida.

### Decisiones cerradas el 2026-11-05

- **SDXL 1.0:** SDXL 1.0 base con la misma LoRA de detalle de la fase 7, en lugar de RealVisXL. El usuario lo elige; ya no lo decide la escalera de hardware.
- **Refiner de SDXL:** se incluye si mejora la calidad, según la comparación con los mismos prompts y semillas.
- **Recomendación:** según el hardware, pero la última palabra es del usuario. Se muestra siempre si cada modelo permite uso comercial, y un modelo que no cabe se puede instalar con advertencia.
- **Schnell con poca VRAM:** debería ir bien con 12 GB o más; se mide durante la implementación y solo se añade GGUF si hace falta.

**Listo cuando:**

- Instalar `quality` o `full` permite elegir entre FLUX.1 Dev, FLUX.1 Schnell y SDXL 1.0, mostrando licencia y tamaño antes de descargar, tanto en la CLI como desde un agente con `setup_start`.
- `imagehearth-mcp setup` cambia el modelo de `quality`, libera el espacio del anterior y, en `full`, la edición con Kontext sigue funcionando.
- Un cambio interrumpido deja el sistema generando con el modelo anterior.
- Una instalación `quality` con Schnell o SDXL no incluye ningún componente con licencia no comercial de FLUX.
- El README contiene la comparativa de los tres modelos con los mismos prompts.

## Fase 10: v1.0

**Objetivo:** cumplir todos los criterios de la [misión](mission.md).

- [ ] Mantener macOS como nivel 3 experimental; pasa a nivel 2 solo si se ha probado con hardware real, sin que eso retenga la versión.
- [ ] Probar la matriz completa de niveles 1 y 2 antes de publicar.
- [ ] Definir la política de versiones: la versión de ImageEngine fija ComfyUI y modelos, y `update` migra entre ellas.
- [ ] Ejecutar periódicamente, con una tarea programada local, la prueba de contrato contra el último ComfyUI, para detectar roturas antes de actualizar la versión fijada.
- [ ] Revisión de seguridad: scripts de instalación, descargas, edición de configuración de agentes y lectura de rutas locales.

**Listo cuando:** se cumplen los cinco criterios de éxito de la misión.

## Después de la v1

Por valorar según la demanda, sin compromiso: workflows personalizados, LoRAs elegidas por el usuario, upscaling, otros modelos, conexión a un ComfyUI en otra máquina y más agentes y editores según se pida.

---

## Riesgos

| Riesgo | Impacto | Medida |
|---|---|---|
| Sin hardware Mac para probar | Medio | macOS preparado tras `--experimental`, sin anunciar soporte, y a la espera de informes reales |
| Kontext o GGUF no funcionan bien en MPS | Medio | Solo afecta a macOS experimental; plan B de la fase 4 |
| Los repositorios de modelos desaparecen o pasan a exigir aprobación | Alto | Manifiesto actualizable, `HF_TOKEN`, errores claros y orígenes alternativos |
| Una actualización de ComfyUI rompe algo | Medio | Versión fijada y prueba de contrato periódica en local |
| Mantener la matriz de PyTorch | Medio | Limitar el nivel 1 a NVIDIA y fijar versiones |
| Malentendidos sobre licencias no comerciales | Medio | Consentimiento explícito y aviso en README e instalador |
| Instaladores `curl \| sh` y descargas grandes generan desconfianza | Medio | Scripts cortos, alternativa manual con `uv tool install` y resumen antes de actuar |
| Los modelos locales pequeños usan mal las herramientas | Alto | Instrucciones en el servidor, menos herramientas y pruebas con modelos locales reales en la fase 5 |
| Un modelo local y la generación compiten por la VRAM | Alto | `MemoryProvider` para varios servidores, modo `manual` y documentación de requisitos |
| Cada agente cambia su formato de configuración | Medio | `connect --print`, documentación por agente y revisión antes de cada versión |
| Bloqueo de la GPU por las pruebas | Bajo | Separar pruebas simuladas y pruebas reales etiquetadas |

## Decisiones abiertas

Ninguna. Las de la fase 9 se cerraron el 2026-11-05 y constan en la [propia fase](#decisiones-cerradas-el-2026-11-05).

**Cerradas el 2026-10-31:**

- **Hardware Mac:** no hay ni se espera. macOS se prepara sin probar y no bloquea ninguna fase.
- **Nombre público:** ImageHearth. `imageengine` está ocupado en PyPI e ImageEngine es también una marca de un CDN de imágenes. El paquete y el comando pasan a `imagehearth_mcp` e `imagehearth-mcp` en la fase 1.
- **Licencia:** MIT para el proyecto y GPL-3.0 para la carpeta del nodo, que importa código de ComfyUI.
- **Dueño en GitHub:** cuenta personal `RealHemoglobin`, con el repositorio `RealHemoglobin/ImageHearth`.

## Siguiente paso

Cerrar la fase 0 y preparar la fase 1 con la skill `feature-spec`, que lee estos documentos y genera la especificación en `specs/`.
