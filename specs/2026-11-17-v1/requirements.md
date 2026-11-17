# Fase 16: v1.0

## Contexto

Fase 16 del [roadmap](../roadmap.md). Objetivo: cumplir los cinco criterios de éxito de la [misión](../mission.md) y publicar ImageHearth 1.0.0. Depende de las fases 6 a 13 y 15, todas completadas. La fase 6 se marcó como completada el 2026-11-17 por decisión del usuario: la publicación, el registro MCP, las pruebas en máquina limpia y los probadores externos ya estaban hechos, aunque no constaban.

Estado de partida, comprobado el 2026-11-17:

- La versión es `0.1.0b3` en `pyproject.toml`, los instaladores, `server.json` y la documentación. Hay etiquetas `v0.1.0b1` a `v0.1.0b3`.
- ComfyUI está fijado en `v0.43.0` (`[comfyui]` de `data/models.toml`, archivo `tar.gz` con SHA-256).
- `install.json` (`provisioner/install_manifest.py`) y los registros de `move.py` y `doctor.py` llevan `schema = 1`. Un esquema distinto se rechaza con «Unknown install record format» y no hay migraciones.
- `imagehearth-mcp update` (`provisioner/maintenance.py`, `update(args)`) aplica el ComfyUI fijado y el manifiesto de modelos actual. No sabe de qué versión viene.
- `scripts/contract.py` (con `contract.sh` y `contract.ps1`) comprueba los nodos y entradas de los workflows contra el ComfyUI **fijado**, en CPU, sin descargar modelos.
- El commit `003a2b9` añadió trabajos en segundo plano: `create_image` espera hasta 40 s (`IMAGEHEARTH_JOB_WAIT_SECONDS`) y devuelve el resultado o `RUNNING: image job <id>`. Además hay `get_image_job` y `cancel_image_job`. `tech-stack.md` aún dice que `start_image_job` y `get_job` están descartados.

## Alcance

1. **Revisión de seguridad** de los scripts de instalación, las descargas, la edición de la configuración de los agentes y la lectura de rutas locales. Informe en `docs/security-review.md` y corrección de los hallazgos altos y medios.
2. **Política de versiones** documentada, y **migraciones versionadas** en `update`.
3. **Prueba de contrato periódica** contra el último ComfyUI publicado: un script y una guía para programarlo.
4. **Matriz de pruebas** con el hardware disponible: NVIDIA en Windows.
5. **Documentación**: `tech-stack.md` (trabajos en segundo plano y política de versiones), README en inglés y español, `CHANGELOG.md` y la guía de publicación.
6. **Versión 1.0.0** en todos los sitios donde hoy aparece `0.1.0b3`, y **publicación** en PyPI, en la GitHub Release y en el registro MCP.

## Fuera de alcance

- Probar con hardware real AMD, Intel Arc, NVIDIA serie 10 o anterior y macOS: siguen en nivel 3.
- Pendientes de la fase 5: Claude Desktop, Gemini CLI y los editores con un cliente real; llama.cpp, LM Studio y vLLM con servidores reales. Siguen documentados como sin probar.
- Subir la versión fijada de ComfyUI desde `v0.43.0`, salvo que la revisión de seguridad o la matriz de pruebas lo exijan.
- Un candidato `1.0.0rc1`: se publica `1.0.0` directamente.
- Un comando que registre la tarea programada en el sistema.
- Corregir los hallazgos de seguridad bajos: se documentan en el informe.
- Las funciones de «Después de la v1» del roadmap.

## Decisiones

| Tema | Decisión |
|---|---|
| Rama y carpeta | `feature/v1` y `specs/2026-11-17-v1/` |
| Fase 6 | Completada por decisión del usuario el 2026-11-17. Sus pendientes no entran aquí |
| Versión | `1.0.0` directa, sin candidato. La fase termina cuando se publica y se comprueba desde las URL públicas |
| Hardware de la matriz | NVIDIA en Windows 11, la única máquina real disponible para esta fase. AMD, Intel, NVIDIA antigua y macOS siguen en nivel 3 |
| Política de versiones | Semver. Cada versión de ImageHearth fija la versión de ComfyUI, las revisiones y SHA-256 de los modelos y los nodos personalizados. Un cambio de esquema de `install.json` o de la versión fijada de ComfyUI solo llega en una versión menor o mayor, nunca en un parche. Se documenta en `docs/versioning.md` y se resume en `tech-stack.md` |
| Migraciones | `install.json` guarda también la versión de ImageHearth que lo escribió. `update` aplica en orden migraciones numeradas por esquema (`schema` N a N+1), que son funciones puras del registro, prueba cada una y guarda copia del registro anterior. Si el esquema es más nuevo que el que entiende el paquete, falla sin cambiar nada y dice que hay que actualizar ImageHearth. El esquema 1 actual sigue cargando sin descargas ni borrados. `update` muestra de qué versión viene y a cuál va, y qué cambia en ComfyUI y en los modelos, antes de actuar |
| Contrato periódico | `scripts/contract_latest.py`, con `contract_latest.sh` y `contract_latest.ps1`: consulta la última versión publicada de ComfyUI en GitHub, la descarga en una carpeta temporal y ejecuta la misma comprobación que `contract.py`. Escribe un log con fecha y sale con un código distinto de 0 si falla. Guía en `docs/releasing.md` para programarlo con el Programador de tareas de Windows y con cron o un temporizador de systemd en Linux. No registra la tarea solo |
| Seguridad | La revisión la hace el asistente. El informe recoge cada hallazgo con gravedad, archivo, escenario y estado. Se corrigen los altos y medios en esta fase, cada uno con su test; los bajos quedan documentados |
| Trabajos en segundo plano | `tech-stack.md` pasa a reflejar el diseño actual (espera de 40 s, `RUNNING: image job <id>`, `get_image_job`, `cancel_image_job`). Se retira `start_image_job` y `get_job` de la columna de descartados |
| Commits | Los hace el usuario tras revisar los cambios, como en fases anteriores |
| Evidencia | Tabla por criterio de la misión en `validation.md`, con quién lo prueba, la máquina, la fecha y el resultado |

## Restricciones

- La [misión](../mission.md) y el [stack](../tech-stack.md) mandan: el servidor MCP sigue sin depender de PyTorch, sin GitHub Actions y con publicación desde la máquina del mantenedor (`uv publish`, `gh release create`).
- Criterio 5 de la misión: solo se anuncia como soportada una combinación probada con hardware real.
- Ninguna migración descarga ni borra modelos por sí sola. Lo que cambie en los modelos pasa por el mecanismo actual: descargar antes de borrar.
- Ningún test toca el `HOME` real ni descarga nada. La prueba periódica es la única que descarga, y solo en una carpeta temporal.
- `uninstall` sigue sin borrar nada que el usuario ya tenía.

## Entregables

- `docs/security-review.md` y las correcciones de los hallazgos altos y medios, con tests.
- `docs/versioning.md`, el esquema de `install.json` con su versión y el registro de migraciones en `provisioner/`, y `update` con el resumen de origen y destino.
- `scripts/contract_latest.py`, `.sh` y `.ps1`, y su guía en `docs/releasing.md`.
- `tech-stack.md`, los README, `CHANGELOG.md`, `server.json`, `install.sh`, `install.ps1` y `pyproject.toml` en `1.0.0`.
- La evidencia de la matriz y de los criterios de la misión en `validation.md`.
- 1.0.0 publicada en PyPI, en la GitHub Release y en el registro MCP. El roadmap marca la fase 16 como completada.

## Supuestos abiertos

- **Linux con NVIDIA:** está en nivel 1, pero en esta fase solo hay hardware de Windows. Por el criterio 5, antes de publicar hay que confirmar una de estas dos opciones:
  - una prueba real de 1.0.0 en Linux (la RTX 4090 de fases anteriores);
  - o que el README anuncie Linux según las pruebas de la beta.
