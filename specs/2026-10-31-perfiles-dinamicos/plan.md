# Plan: Fase 4

Rama: `feature/perfiles-dinamicos`. Sin commits del asistente: los cambios se dejan en el árbol de trabajo para revisión.

## 1. Catálogo de lo instalado

1. Sacar a una función compartida la resolución de la carpeta de modelos que hoy está en `provisioner/doctor.py`, y usarla también desde `doctor`.
2. Crear `engine/catalog.py`: a partir de `provisioner.manifest` y de `models.inspect`, indicar qué workflows están instalados y cuál es el perfil mínimo de cada uno. Se evalúa en cada llamada, sin caché.
3. Comprobar que importar `server` no carga `huggingface_hub`. Si `provisioner/models.py` lo importa al inicio, diferir esa importación.
4. Tests con `tmp_path`: carpeta vacía y cada perfil completo, modelo con tamaño incorrecto, modelo compartido entre FLUX Dev y Kontext, y sin `install.json`.

## 2. Integración en el motor

1. `validation.available_workflows()`: devolver solo lo instalado, sin los internos, y añadir la función que construye el error con el perfil y el comando de `setup`.
2. `resolve_workflow`: distinguir un nombre inexistente de un workflow conocido sin instalar. El segundo caso da el error accionable, también para `quality`.
3. `kontext.generate`: comprobar Kontext antes de subir referencias y de abrir la sesión.
4. `run_workflow`: comprobar el workflow antes de abrir la sesión, porque `generate_image` y `create_image` lo alcanzan por la misma vía.
5. `server.py`: actualizar las descripciones de `generate_image`, `create_image`, `edit_image` y `list_workflows` para indicar que dependen de lo instalado. Revisar también la skill de `data/` si menciona modelos siempre disponibles.
6. Tests: con solo `fast`, `quality=high` y `edit_image` fallan con el perfil correcto y sin abrir sesión ni tocar Ollama; `list_workflows` conserva su forma; instalar más modelos se nota sin reiniciar.

## 3. Separación del cargador de modelo

1. Antes de tocar nada, añadir un test que guarde como referencia el resultado actual de `build_workflow` con una y con varias referencias.
2. Añadir funciones que localicen un nodo por `class_type`, con rol cuando haya varios del mismo tipo (por ejemplo, `CLIPTextEncode` positivo), admitiendo los cargadores estándar y los GGUF. Fallar con un error claro si falta o hay ambigüedad.
3. Sustituir `required_nodes` y los identificadores fijos por esas funciones, incluida la lista de nodos antiguos que se eliminan.
4. Aislar el cargador en una función que devuelva la referencia al modelo, al codificador y al VAE, y enlazar con ella los nodos añadidos.
5. Comprobar que el resultado es equivalente a la referencia del punto 1.
6. Ejecutar `scripts/contract.sh` y una edición real con Kontext.

## 4. Script de medición

1. Crear `scripts/measure_profiles.py`: medir `sdxl_turbo`, `flux_dev` y `flux_kontext_dev_basic` a 1024x1024, con una referencia en Kontext.
2. Pico de VRAM muestreando `nvidia-smi` en paralelo y restando la memoria en uso antes de empezar. Tiempo con carga en frío y media de 3 generaciones en caliente. Registrar también RAM máxima.
3. Salida JSON con GPU, driver, sistema, versión de ComfyUI y resultados. Debe funcionar en Linux y en Windows, sin modelos de lenguaje cargados.
4. Avisar y omitir lo que no esté instalado, usando el catálogo de la tarea 1.

## 5. Mediciones y documentación

1. Ejecutar el script en la RTX 4090 con Linux y en el equipo NVIDIA con Windows.
2. Ambos README: tabla de requisitos con los valores medidos y el equipo, indicando que los mínimos para otras GPU son orientativos.
3. `tech-stack.md`: actualizar la tabla de perfiles con las mediciones. Revisar `min_vram_mib` de `models.toml` solo si los datos contradicen el valor actual.
4. Documentar en los README que el catálogo depende del perfil y cómo ampliarlo con `setup`.

## 6. Manifiesto para macOS

1. Confirmar los repositorios GGUF y sus licencias. Fijar revisión, tamaño y SHA-256 con los metadatos de Hugging Face, sin depender de un Mac.
2. Añadir a `models.toml` los modelos `Q5_K_M`, `pytorch.metal` y los perfiles `mac-fast`, `mac-quality` y `mac-full`, con un campo de plataforma en cada perfil y `install_bytes` propio para Mac.
3. Fijar `ComfyUI-GGUF` por commit y SHA-256, con su licencia. Instalarlo con el registro de lo instalado, de forma que `update` y `uninstall` lo gestionen, e instalar su dependencia `gguf` en el entorno.
4. Tests: los perfiles existentes no cambian, los de Mac validan formato y tamaños, y cada plataforma solo ve los suyos.

## 7. Workflows GGUF

1. Crear `flux_dev_gguf.json` y `flux_kontext_dev_gguf.json`, con `UnetLoaderGGUF` y `DualCLIPLoaderGGUF` en lugar de los cargadores actuales.
2. Catálogo: `quality=high` y la edición resuelven a la variante del perfil instalado. Las variantes de otra plataforma no se ofrecen.
3. Ampliar `scripts/contract.py` para instalar `ComfyUI-GGUF` y comprobar también estos workflows con `/object_info`.
4. Ejecutar ambos workflows en la RTX 4090 con los archivos GGUF reales.

## 8. `setup`, `doctor` y motor en macOS

1. `detect.py`: pasar `metal` a nivel 3 y detectar Apple Silicon y memoria unificada. Mac con Intel sigue sin soporte, con mensaje claro.
2. `setup`: exigir `--experimental` en macOS y mostrar que no se ha probado, antes de descargar nada. Proponer perfil según la memoria unificada.
3. `preflight.py` y `doctor`: usar memoria unificada, no exigir driver NVIDIA ni llamar a `nvidia-smi`, y añadir `ComfyUI-GGUF` como capa en Mac. `doctor` indica que la plataforma está sin probar.
4. Revisar rutas, arranque desacoplado y procesos de `platform/` por si dan por hecho Linux, y `gpu.py` para que caiga en `/system_stats`.
5. Tests con `darwin` simulado: rechazo sin `--experimental`, flujo completo con subprocesos simulados, `doctor --json`, y actualizar los casos actuales de `test_provisioner.py`.

## 9. Validación y cierre

1. Ejecutar la matriz de [validation.md](validation.md) y rellenar la evidencia.
2. Comprobar el supuesto sobre `extra_model_paths.yaml` con la instalación de desarrollo.
3. Documentar macOS en ambos README y en `tech-stack.md` como preparado y sin probar, pidiendo informes de quien lo use. Actualizar `THIRD_PARTY_NOTICES.md`.
4. Marcar en el roadmap las tareas hechas (el usuario revisa antes).
