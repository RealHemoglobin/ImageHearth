# Plan: Fase 16

Orden decidido: primero la seguridad, porque puede cambiar código que tocan las demás tareas. Los commits los hace el usuario al final de cada bloque.

## 1. Revisión de seguridad

1. Revisar `install.sh` e `install.ps1`:
   - versión fijada;
   - origen de uv;
   - ejecución de lo descargado;
   - comillas y rutas con espacios.
2. Revisar las descargas (`provisioner/models.py`, `comfyui.py`):
   - SHA-256 obligatorio;
   - archivos `.part`;
   - extracción del `tar.gz` de ComfyUI frente a rutas con `..` o enlaces;
   - uso de `HF_TOKEN` sin escribirlo en logs.
3. Revisar la edición de la configuración de agentes (`connect.py`, `agent_setup.py`, `agent_scan.py`):
   - copias de seguridad;
   - escritura atómica;
   - solo entradas propias;
   - JSON y TOML inválidos;
   - permisos de los archivos.
4. Revisar la lectura de rutas locales:
   - `image_paths` de `create_image`;
   - `--install-dir` y `--move-to`;
   - rutas de `config.toml` y variables de entorno;
   - el servidor HTTP local de ComfyUI y el nodo `imagehearth_status`.
5. Escribir `docs/security-review.md`, con gravedad, archivo, escenario y estado de cada hallazgo.
6. Corregir los hallazgos altos y medios. Cada uno lleva su test.

## 2. Política de versiones y migraciones

1. Escribir `docs/versioning.md`:
   - semver;
   - qué fija cada versión;
   - qué cambios admite un parche, una versión menor y una mayor;
   - cómo migra `update`.
2. Centralizar `SCHEMA` (hoy repetido en `install_manifest.py`, `move.py` y `doctor.py`).
3. Añadir `imagehearth_version` al registro.
4. Crear el registro de migraciones (`provisioner/migrations.py`):
   - funciones `schema N -> N+1` aplicadas en orden;
   - copia `install.json.bak-<schema>` antes de guardar;
   - error claro si el esquema es mayor que el conocido.
5. `InstallManifest.load` migra en memoria. Solo `update` (y `setup`, si ya escribe) guardan el resultado. `doctor` informa si hace falta migrar.
6. `update` muestra, antes de actuar:
   - la versión de origen y la de destino;
   - la versión de ComfyUI fijada antes y después;
   - los modelos que cambian.
   Con `--yes` no pregunta.
7. Tests:
   - un registro de esquema 1 de cada fase (9, 13 y 15) carga sin cambios en los modelos;
   - migración simulada de 1 a 2;
   - esquema futuro rechazado;
   - copia de seguridad creada;
   - `update` sin descargas cuando nada cambia.

## 3. Prueba de contrato periódica

1. Separar de `scripts/contract.py` la parte que comprueba un ComfyUI ya extraído, para reutilizarla.
2. Crear `scripts/contract_latest.py`:
   - consulta la última versión de ComfyUI en la API de GitHub;
   - descarga y extrae en una carpeta temporal;
   - ejecuta la comprobación;
   - escribe el log en la carpeta de logs de ImageHearth con fecha y versión probada;
   - código de salida 0 si pasa y 1 si falla.
3. Crear los envoltorios `scripts/contract_latest.sh` y `scripts/contract_latest.ps1`.
4. Ampliar `docs/releasing.md` con:
   - cómo programarlo con el Programador de tareas de Windows (`schtasks`);
   - cómo programarlo con cron o un temporizador de systemd;
   - qué hacer si falla.
5. Ejecutarlo una vez en Windows y anotar el resultado en la evidencia.

## 4. Documentación y versión 1.0.0

1. `tech-stack.md`:
   - trabajos en segundo plano en la tabla de decisiones (sustituye la fila «Plazos de los clientes»);
   - fila de política de versiones;
   - nivel de cada plataforma según la matriz.
2. README en inglés y en español:
   - quitar las referencias a la beta;
   - matriz de soporte por niveles;
   - enlace a `docs/versioning.md`.
3. Subir la versión a `1.0.0` en `pyproject.toml`, `uv.lock`, `install.sh`, `install.ps1`, `server.json`, los README y `docs/`. Buscar `0.1.0b3` para que no quede ninguna.
4. Añadir la entrada de `CHANGELOG.md` para `1.0.0`.

## 5. Matriz de pruebas

1. Ejecutar en Windows 11 con NVIDIA:
   - `scripts\check.ps1`;
   - `scripts\contract.ps1`;
   - `scripts\contract_latest.ps1`.
2. En una máquina Windows 11 limpia con NVIDIA:
   - `irm ... install.ps1 | iex` desde la rama;
   - instalación sin intervención salvo licencias y perfil;
   - primera imagen con un agente;
   - `doctor --json`;
   - `uninstall`.
3. Actualizar de `0.1.0b3` a la rama con `update`: la migración se aplica, conserva modelos y conexiones, y la generación sigue funcionando.
4. Resolver el supuesto de Linux (ver `requirements.md`) antes de publicar.
5. Rellenar la tabla de criterios de la misión en `validation.md`.

## 6. Publicación

1. Fusionar `feature/v1` cuando se cumpla la puerta de `validation.md`.
2. Seguir `docs/releasing.md`:
   - `uv build`;
   - `uv publish`;
   - `gh release create v1.0.0`;
   - publicar `server.json` en el registro MCP.
3. Comprobar desde las URL públicas:
   - `install.ps1` en Windows;
   - `install.sh` en Linux, si se confirma el supuesto;
   - `uv tool install imagehearth-mcp==1.0.0`;
   - la entrada en el registro MCP.
4. Marcar la fase 16 como completada en el roadmap y actualizar «Siguiente paso».
