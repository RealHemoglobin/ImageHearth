# Plan: Fase 9

Rama: `feature/eleccion-modelo-quality`. Sin commits del asistente: los cambios se dejan en el árbol de trabajo para revisión. Los pasos marcados como **mantenedor** no los ejecuta el asistente.

Orden: catálogo primero, porque todo lo demás depende de separar perfil y modelo de `quality`. Después workflows y su detección, la instalación nueva, la migración, el cambio de modelo (el paso con más riesgo), la superficie para agentes y, al final, documentación y pruebas reales.

## 1. Modelos nuevos en el catálogo

1. Localizar el repositorio público con FLUX.1 Schnell fp8 para ComfyUI; fijar revisión, `filename`, `dest`, `bytes`, `sha256` y licencia `apache-2` en `models.toml`. Si no hay un origen estable sin token, parar y preguntar.
2. Añadir el checkpoint de SDXL 1.0 base (`stabilityai/stable-diffusion-xl-base-1.0`, `openrail-pp`) con revisión y SHA-256 fijados. La LoRA `sdxl_offset_lora` ya está.
3. Preparar la entrada del refiner (`stabilityai/stable-diffusion-xl-refiner-1.0`, `openrail-pp`) sin añadirla a ningún perfil hasta la tarea 3.
4. Comprobar que la licencia `apache-2` y `openrail-pp` existentes cubren ambos modelos.

## 2. Perfil y modelo de `quality` separados

1. `models.toml`: describir los modelos de `quality` (`flux-dev`, `flux-schnell`, `sdxl`) con sus pesos, su VRAM mínima medida y sus variantes por precisión (`flux-dev`: fp8 y GGUF). Los componentes compartidos (T5, CLIP-L, VAE de FLUX) se declaran como dependencias del modelo que los usa, no del perfil.
2. Kontext declara sus propias dependencias (T5, CLIP-L, VAE), para que `full` con `sdxl` las incluya por Kontext.
3. Retirar RealVisXL y el perfil `quality-sdxl`; `quality-gguf` y `full-gguf` pasan a ser variantes de `flux-dev`.
4. `provisioner/manifest.py`: `Manifest.resolve(profile, quality_model, vram_mib)` devuelve la lista de modelos, nodos y licencias de la combinación; `licenses_for` solo incluye las licencias de lo que se descarga.
5. Recomendación: función que, según la VRAM, devuelve `flux-dev` (20 GB o más), `flux-schnell` (12 a 20 GB) o `sdxl` (menos de 12 GB), y otra que dice si un modelo cabe y con qué mínimo.
6. Mantener intactos los perfiles `fast` y `mac-*`.
7. Tests en `tests/test_provisioner.py` y `tests/test_hardware_adaptation.py`: combinaciones perfil-modelo, `full` con `sdxl` incluye T5/CLIP-L/VAE, `quality` con Schnell o SDXL sin licencia no comercial, recomendación por tramos, modelo que no cabe con advertencia.

## 3. Workflows

1. `data/workflows/flux_schnell.json`: 4 pasos, sin CFG ni guía, sampler y scheduler recomendados para Schnell, prefijo `imagehearth/flux_schnell`.
2. `data/workflows/sdxl_base.json`: 1024 nativo, pasos y CFG de SDXL base, con la LoRA de detalle.
3. **Refiner:** generar los mismos prompts y semillas con base+LoRA y con base+LoRA+refiner en la RTX 4090. Si mejora, añadir el refiner al workflow y al modelo `sdxl` en `models.toml`; si no, retirar la entrada preparada en la tarea 1.3. Guardar la comparación en la carpeta de la spec y anotar la decisión en la evidencia.
4. `engine/catalog.py`: `VARIANTS["high"]` con `flux_dev`, `flux_dev_gguf`, `flux_schnell`, `sdxl_base` y `sdxl_quality` (este solo para instalaciones migradas con RealVisXL). El catálogo usa el instalado, como ahora.
5. `catalog.minimum_vram_mib` y `required_vram_mib` con los valores de los nuevos workflows.
6. `scripts/contract.py`: incluir los dos workflows nuevos en la prueba de contrato con `/object_info`.
7. Tests en `tests/test_catalog.py`: el catálogo elige el workflow del modelo instalado y no ofrece los que no están.

## 4. Modelo activo visible y metadatos

1. `install_manifest.py`: guardar `quality_model` en el registro de instalación y leerlo con un valor deducido para registros antiguos (tarea 6).
2. `list_workflows`, `get_engine_status` (`engine/status.py`) y `doctor` (también `--json`): modelo de `quality` activo, licencia y si permite uso comercial.
3. Metadatos del PNG: escribir modelo de `quality` y workflow como texto del PNG al guardar la imagen. Si ComfyUI ya escribe el prompt, añadir las claves propias sin quitar las suyas.
4. Tests: registro con `quality_model`, salida de `doctor` y `get_engine_status`, metadatos presentes en un PNG generado por el arnés.

## 5. Instalación nueva

1. `cli.py`: `setup --quality-model {flux-dev,flux-schnell,sdxl}` con su ayuda.
2. `provisioner/setup.py` interactivo: tras elegir `quality` o `full`, preguntar el modelo mostrando de cada uno tamaño de descarga, VRAM mínima, licencia y uso comercial; marcar la recomendada; las que no caben aparecen con su advertencia.
3. No interactivo: sin `--quality-model`, usar la recomendación e indicarlo en la salida; con un modelo que no cabe, instalar y emitir la advertencia.
4. `show_summary` y `require_acceptance`: resumen y licencias de la combinación elegida.
5. `run_preflight`: espacio y requisitos de la combinación.
6. Tests: pregunta interactiva simulada, `--quality-model`, recomendación por defecto anunciada, advertencia de hardware, licencias mostradas por combinación.

## 6. Migración de instalaciones anteriores

1. Deducir `quality_model` cuando falta en el registro: `flux-dev` si hay FLUX Dev fp8 o GGUF, `sdxl` si hay RealVisXL.
2. Con RealVisXL, `sdxl_quality` sigue disponible en el catálogo hasta el siguiente `setup`.
3. `setup` sobre una instalación con RealVisXL propone pasar a SDXL 1.0 y borrar RealVisXL si ImageHearth lo instaló; si es preexistente, no se borra.
4. `doctor` señala la instalación migrable con el comando que la actualiza.
5. Tests: registro antiguo con FLUX Dev, con FLUX Dev GGUF y con RealVisXL; RealVisXL preexistente que no se borra.

## 7. Cambio de modelo

1. `setup` sobre una instalación existente muestra el modelo actual y permite elegir otro (interactivo o `--quality-model`).
2. Plan del cambio: archivos a descargar, archivos a borrar (propios según el registro y no usados por ningún componente instalado tras el cambio) y espacio liberado. Pedir confirmación o `--yes`.
3. Comprobar espacio libre con ambos modelos conviviendo.
4. Rechazar el cambio si hay una generación en curso (bloqueo del motor / estado de sesión).
5. Descargar y verificar con `ensure_models`; actualizar `quality_model` en el registro solo cuando el nuevo está verificado; borrar después. Repetir el comando tras un fallo continúa la descarga y no borra nada antes.
6. Reiniciar el ComfyUI gestionado si estaba en marcha.
7. Reutilizar el borrado de `provisioner/maintenance.py` (`_remove`, `forget`) en lugar de duplicarlo.
8. Tests: descarga antes de borrar; fallo a mitad deja el anterior funcionando y el registro sin cambiar; T5/CLIP-L/VAE conservados con Kontext o con el modelo nuevo; preexistentes y modo adjunto intactos; rechazo con generación en curso; reinicio de ComfyUI gestionado; espacio insuficiente detectado antes de descargar.

## 8. Agentes

1. `setup_status`: lista de modelos de `quality` con tamaño, licencia, uso comercial, recomendación, si caben y cuál está instalado.
2. `setup_start(profile, accept_licenses, existing_comfyui, quality_model="")`: sin valor usa la recomendación; devuelve la advertencia de hardware y el modelo usado. Sobre una instalación existente, cambia el modelo con las mismas reglas que la tarea 7.
3. `FastMCP(instructions=...)`: antes de `setup_start` el agente dice al usuario perfil, modelo de `quality`, tamaño, licencias y advertencias, y le deja elegir el modelo.
4. Mensajes de "no instalado" que mencionan `--quality-model` cuando proceda.
5. Tests en `tests/test_requests.py` o equivalentes: campos de `setup_status`, `quality_model` en `setup_start`, advertencia devuelta.

## 9. Documentación

1. `README.md` y `README.es.md`: tabla de los tres modelos (licencia, uso comercial, tamaño, VRAM y tiempo medidos), cómo elegir y cambiar el modelo, y que la edición con Kontext en `full` sigue siendo no comercial.
2. Comparativa con los mismos prompts y semillas en los tres modelos (tarea 10), que sustituye a la comparación de variantes pendiente de la fase 7.
3. `data/skill/SKILL.md`: quitar RealVisXL, describir los tres modelos y `--quality-model`.
4. `docs/troubleshooting.md`: cambio interrumpido, modelo que no cabe, espacio durante el cambio.
5. `tech-stack.md`: decisión de perfil más modelo de `quality` y tabla de perfiles actualizada.
6. `THIRD_PARTY_NOTICES.md`: licencias de Schnell, SDXL 1.0 y refiner si se incluye.

## 10. Pruebas reales (RTX 4090 en Linux)

1. Ampliar `scripts/measure_profiles.py` (o un script nuevo) para generar el mismo prompt con la misma semilla con cada modelo y registrar tiempo, pico de VRAM y ruta.
2. Prueba real: los mismos prompts y semillas con `flux-dev`, `flux-schnell` y `sdxl`, cambiando con `setup` entre uno y otro. Montar la comparativa para el README.
3. Prueba real: ciclo `flux-dev` → `flux-schnell` → `sdxl` → `flux-dev` en `full`, comprobando tras cada cambio que la edición con Kontext funciona y que el disco usado vuelve al de partida.
4. Prueba real: interrumpir un cambio durante la descarga y comprobar que se sigue generando con el modelo anterior; repetir el comando y que termine.
5. Medir Schnell fp8 limitando la VRAM a 12 GB (o en la tarjeta más pequeña disponible) para fijar el umbral de la recomendación; si no va, añadir GGUF y repetir.
6. Comprobar que una instalación `quality` con Schnell o SDXL no tiene archivos con licencia no comercial de FLUX.
7. **Mantenedor:** instalar desde Claude Code con `setup_start` y comprobar que el agente presenta modelo, licencia y advertencias y deja elegir.
8. Trasladar cifras e imágenes al README y a la evidencia.

## 11. Validación local y fusión

1. Ejecutar `scripts/check.sh` y `scripts/contract.sh`.
2. Rellenar la evidencia en [validation.md](validation.md) y marcar en el roadmap lo verificado.
3. **Mantenedor:** revisar, hacer commit y fusionar en `main`.
4. Marcar la fase como completada en el roadmap cuando la lista de cierre esté completa.
