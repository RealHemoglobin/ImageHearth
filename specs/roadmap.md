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
| 4. Perfiles y macOS | Modelos según hardware; validación en Mac | L | 3 |
| 5. Agentes | Conexión con un comando y generaciones largas fiables | M | 2 |
| 6. Beta pública | v0.1 en PyPI y en el registro MCP | M | 3, 5 |
| 7. v1.0 | macOS soportado y matriz de pruebas completa | M | 4, 6 |

**Recomendación de orden:** publicar la beta sin esperar a macOS. La fase 4 tiene el mayor riesgo técnico y necesita hardware que hoy no está disponible. La fase 5 se puede hacer en paralelo a la 3.

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
- [ ] Ejecutar `scripts/check.sh` (con una versión para PowerShell) en las máquinas Windows y macOS, y añadir la prueba de contrato con `/object_info`. Hecho: `check.ps1`, `contract.sh` y `contract.ps1`, y verificado en Linux. Pendiente: ejecutarlos en Windows y macOS.

**Listo cuando:**
- Los tests pasan en los tres sistemas.
- Una generación completa funciona sin Ollama, verificado con hardware real en Linux.
- Una generación real funciona en Windows con NVIDIA y ComfyUI instalado a mano.
- Se ha probado matar el proceso a mitad de sesión en Windows y la recuperación funciona.
- ComfyUI ya no muestra `IMPORT FAILED`.

## Fase 3: Instalador

**Objetivo:** `imageengine-mcp setup` lleva una máquina limpia a un sistema funcional.

**Spike inicial (máximo 2 días):** comparar el instalador propio con `comfy-cli` en Linux y Windows, y validar la decisión de [tech-stack](tech-stack.md).

- [ ] **Detección:** sistema, arquitectura, GPU, driver, VRAM, RAM, disco, ComfyUI existente (incluido Desktop), Ollama, LM Studio, llama.cpp y vLLM.
- [ ] **Manifiesto** `models.toml`: repositorio, revisión fijada, ruta, tamaño, SHA-256, licencia y workflows que habilita. Partir de la tabla verificada del análisis.
- [ ] **ComfyUI:** descargar una versión fijada, crear el entorno con uv y Python gestionado, instalar el PyTorch adecuado e instalar el nodo.
- [ ] **Modo adjunto:** usar un ComfyUI existente, instalar el nodo con permiso y configurar URL y rutas.
- [ ] **Modelos:** descarga reanudable con verificación SHA-256, que no vuelva a descargar lo que ya existe.
- [ ] **Consentimiento:** mostrar espacio, licencias y enlaces antes de descargar. En modo no interactivo, exigir `--accept-licenses`.
- [ ] **Comprobaciones previas:** disco insuficiente, driver ausente, GPU sin soporte o puerto ocupado; cada una con un mensaje accionable.
- [ ] **`doctor`:** comprobar cada capa, con salida legible y `--json`.
- [ ] **`update` y `uninstall`:** registrar en un manifiesto qué se instaló; no borrar nunca nada ajeno ni, sin confirmación, los modelos.
- [ ] **Mostrar el resumen de lo que se va a descargar antes de hacerlo y permitir elegir el perfil**, para que quien ya usa modelos locales pueda empezar solo con `fast` y poco disco.
- [ ] Prueba de humo final con una imagen pequeña.

**Listo cuando:**
- Funciona en máquinas virtuales o equipos limpios: Ubuntu y Windows 11 con NVIDIA.
- Interrumpir la descarga y repetir el comando continúa donde se quedó.
- Un archivo corrupto se detecta y se vuelve a descargar.
- Con espacio insuficiente falla antes de descargar nada.
- `uninstall` deja intactos un ComfyUI y unos modelos preexistentes.

## Fase 4: Perfiles y macOS

**Objetivo:** el hardware decide qué se ofrece y nada se anuncia sin haberlo probado.

- [ ] Hacer dinámico el catálogo: `list_workflows`, `quality` y los errores se basan en lo instalado. Un error dice qué perfil instalar.
- [ ] Separar en `build_workflow` el cargador de modelo de los identificadores de nodo fijos.
- [ ] Medir VRAM y tiempo reales por perfil y documentarlos.
- [ ] **Spike en Mac (bloqueante):** comprobar que ComfyUI, `ComfyUI-GGUF`, FLUX y Kontext funcionan en MPS. Elegir cuantización y codificador T5.
- [ ] Crear workflows y manifiesto para Mac, con hashes fijados.
- [ ] Añadir perfil GGUF para NVIDIA con poca VRAM si las mediciones lo justifican.
- [ ] Buscar un origen más estable para FLUX Dev.
- [ ] Evaluar FLUX.1 Schnell como opción Apache-2.0 para uso comercial; su repositorio oficial exige aprobación automática.

**Listo cuando:**
- Un Mac real completa las tres capacidades, o se documenta y se oculta la que no funcione.
- La tabla de requisitos del README contiene mediciones reales.

**Plan B:** si Kontext no es viable en Mac, la v1 ofrece generación en macOS y marca la edición como no disponible.

## Fase 5: Integración con agentes

**Objetivo:** funcionar igual en cualquier agente, tenga o no skills, y que un usuario con modelos locales pueda instalarlo con facilidad y compaginarlo con ellos en la misma GPU.

**Principio:** el servidor MCP estándar por stdio es el producto. Cada agente o editor es solo una forma de conectarlo, y el soporte de uno nuevo no debe exigir cambios en el motor.

- [ ] `connect <agente>` y `connect --detect`, usando la CLI oficial si existe o editando su configuración con copia de seguridad.
- [ ] **`connect --print <agente>`:** imprime el fragmento de configuración (JSON, TOML o YAML) sin tocar nada, para cualquier cliente que no esté soportado, y una página `docs/agents.md` con el fragmento de cada uno.
- [ ] Soporte inicial de agentes: Claude Code, Claude Desktop, Codex, Gemini CLI, **opencode y Hermes**. Verificar cada formato contra su documentación y probarlo con un modelo local real.
- [ ] Soporte inicial de editores: Cursor, VS Code e **IntelliJ y otros JetBrains**. Verificar cada configuración contra su documentación.
- [ ] **pi:** comprobar si admite MCP. Si no, valorar un adaptador pequeño (extensión o llamada a la CLI) o documentar que no está soportado.
- [ ] **Pasar lo esencial de la skill a `FastMCP(instructions=...)`, de forma obligatoria:** los agentes con modelos locales no cargan skills. Las descripciones de cada herramienta deben bastar por sí solas. Dejar la skill como complemento e instalarla donde el agente la admita.
- [ ] **Probar con modelos locales pequeños** (por ejemplo 7B–14B con Ollama o llama.cpp) en opencode y Hermes: elegir la herramienta correcta, pasar parámetros válidos y relatar el resultado. Documentar el tamaño mínimo que funciona.
- [ ] Hacer que el servidor arranque sin ComfyUI y que cada herramienta explique qué falta.
- [ ] Añadir `setup_status` y `setup_start`. El segundo exige perfil y aceptación explícita, lanza un proceso que sobrevive a la desconexión e informa de su progreso. Las instrucciones obligan al agente a preguntar antes, porque descarga decenas de GB.
- [ ] Publicar `llms-install.md` para pedirle la instalación al agente.
- [ ] Emitir progreso con `ctx.report_progress` durante la generación.
- [ ] **Medir el plazo real de cada cliente.** Solo si alguno corta las generaciones, añadir `start_image_job` y `get_job`.
- [ ] Devolver la ruta y, de forma opcional, la imagen como contenido MCP, manteniendo la ruta en la primera línea.
- [ ] **Reducir las herramientas expuestas:** `create_image` cubre a `generate_image` y `edit_image`. Menos herramientas y parámetros más simples ayudan a los modelos pequeños. Mantener los nombres antiguos como alias solo si se mide que cuestan poco.
- [ ] **Compaginar con modelos locales en la misma GPU:** implementar `MemoryProvider` para llama.cpp (`llama-server`), LM Studio y vLLM, además de Ollama. Si el servidor no permite descargar el modelo, avisar con un mensaje accionable en lugar de fallar por falta de memoria. Documentar la VRAM necesaria para tener un modelo de lenguaje y la generación a la vez.
- [ ] Opción `memory_mode` en `config.toml`: `auto`, `off` o `manual`. En `manual`, el motor no toca los modelos del usuario y solo comprueba la memoria libre antes de generar.

**Listo cuando:**
- En cada agente y editor soportado se puede conectar, generar con `fast`, generar con `quality` y editar con Kontext, partiendo de una configuración vacía.
- Con al menos un modelo local de lenguaje (opencode u Hermes) se genera y se edita una imagen sin ayuda, con el modelo de lenguaje cargado y devolviendo su memoria al terminar.
- Un cliente sin soporte propio se conecta con `connect --print` y la documentación.

## Fase 6: Beta pública

**Objetivo:** cualquiera con Linux o Windows y NVIDIA puede instalarlo.

- [ ] `install.sh` e `install.ps1`, breves y legibles: instalar uv, instalar la herramienta con versión fijada y lanzar `setup`.
- [ ] Publicar desde la máquina del mantenedor, sin GitHub Actions: `uv publish` a PyPI con un token y `gh release create` para la GitHub Release.
- [ ] Publicar en el registro oficial de MCP con `server.json`.
- [ ] Añadir `.mcpb` para Claude Desktop solo si `connect` no es suficiente.
- [ ] Reescribir el README: la instalación de un comando pasa a ser la principal y se quita el aviso de desarrollo.
- [ ] Añadir guía de problemas frecuentes, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md` y plantillas de incidencias que pidan la salida de `doctor --json`.
- [ ] Reunir entre 5 y 10 probadores externos en hardware distinto.

**Listo cuando:** al menos 3 personas externas instalan y generan sin ayuda, y los fallos de instalación se pueden diagnosticar con `doctor --json`.

## Fase 7: v1.0

**Objetivo:** cumplir todos los criterios de la [misión](mission.md).

- [ ] Integrar macOS como nivel 2.
- [ ] Probar la matriz completa de niveles 1 y 2 antes de publicar.
- [ ] Definir la política de versiones: la versión de ImageEngine fija ComfyUI y modelos, y `update` migra entre ellas.
- [ ] Ejecutar periódicamente, con una tarea programada local, la prueba de contrato contra el último ComfyUI, para detectar roturas antes de actualizar la versión fijada.
- [ ] Revisión de seguridad: scripts de instalación, descargas, edición de configuración de agentes y lectura de rutas locales.

**Listo cuando:** se cumplen los cinco criterios de éxito de la misión.

## Después de la v1

Por valorar según la demanda, sin compromiso: workflows personalizados, LoRAs, upscaling, otros modelos, conexión a un ComfyUI en otra máquina y más agentes y editores según se pida.

---

## Riesgos

| Riesgo | Impacto | Medida |
|---|---|---|
| Sin hardware Mac o Windows para probar | **Alto** | Conseguirlo en la fase 0; sin él, no anunciar soporte |
| Kontext no funciona bien en MPS | Alto | Spike temprano y plan B |
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

| Decisión | Recomendación | Bloquea |
|---|---|---|
| Hardware de prueba | Linux y Windows con NVIDIA ya disponibles. Falta un Mac con 32 GB o más | Fase 4 |

**Cerradas el 2026-10-31:**

- **Nombre público:** ImageHearth. `imageengine` está ocupado en PyPI e ImageEngine es también una marca de un CDN de imágenes. El paquete y el comando pasan a `imagehearth_mcp` e `imagehearth-mcp` en la fase 1.
- **Licencia:** MIT para el proyecto y GPL-3.0 para la carpeta del nodo, que importa código de ComfyUI.
- **Dueño en GitHub:** cuenta personal `RealHemoglobin`, con el repositorio `RealHemoglobin/ImageHearth`.

## Siguiente paso

Cerrar la fase 0 y preparar la fase 1 con la skill `feature-spec`, que lee estos documentos y genera la especificación en `specs/`.
