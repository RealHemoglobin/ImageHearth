# Plan: Fase 6

Rama: `feature/beta-publica`. Sin commits del asistente: los cambios se dejan en el árbol de trabajo para revisión. Los pasos marcados como **mantenedor** no los ejecuta el asistente.

## 1. Metadatos del paquete

1. Subir la versión a `0.1.0b1` y completar en `pyproject.toml` autores, palabras clave, clasificadores y URL.
2. Revisar el contenido del wheel y del sdist: datos de paquete presentes, licencias incluidas, y ni modelos, ni `specs/`, ni archivos locales como `engine.lock`, `state/` o `logs/`.
3. Comprobar los enlaces del README tal como se verán en PyPI, donde las rutas relativas no funcionan.
4. Tests: contenido del paquete y `--version` coherente con `pyproject.toml`.

## 2. Revisión para hacer público el repositorio

1. Revisar árbol e historial en busca de secretos, tokens, rutas personales y datos privados.
2. Revisar qué archivos versionados no deben publicarse, incluidos los binarios o `engine.lock` si estuvieran en el historial.
3. Anotar el resultado en la evidencia. Si aparece algo, parar y decidir con el mantenedor.

## 3. Scripts de instalación

1. Escribir `install.sh`, en POSIX `sh`: comprobar sistema, instalar uv si falta con su instalador oficial, instalar la versión fijada, ejecutar `setup` y `connect --detect` leyendo de `/dev/tty`.
2. Escribir `install.ps1` con el mismo flujo, sin `sudo` ni elevación.
3. Tratar cada fallo con un mensaje accionable: sin red, sin terminal, sistema no soportado o macOS (`--experimental`). Si ya está instalado, no debe romper nada.
4. Mantenerlos breves y envolver el cuerpo en una función, para que una descarga cortada no ejecute un script a medias.
5. Tests: versión fijada igual a `pyproject.toml`, ninguna aparición de `sudo` ni de `--accept-licenses`, y `sh -n` sobre `install.sh`.

## 4. Registro MCP

1. Contrastar con la documentación actual del registro el esquema de `server.json`, el espacio de nombres y la verificación de propiedad.
2. Crear `server.json` con el paquete de PyPI y el transporte stdio, y añadir al README la marca de propiedad si hace falta.
3. Test: validar `server.json` contra el esquema disponible, sin red, y que su versión coincida con `pyproject.toml`.

## 5. Documentación pública

1. Reescribir `README.md`: instalación de un comando como principal, alternativa manual, sin aviso de desarrollo y con los niveles de soporte reales. Trasladar lo mismo a `README.es.md`.
2. Crear `docs/troubleshooting.md` a partir de los mensajes reales de `doctor` y de las comprobaciones previas.
3. Crear `CHANGELOG.md` con la skill `maintain-changelog`, `CONTRIBUTING.md` con `scripts/check.sh` como puerta de calidad, y `SECURITY.md` con la vía de aviso privada.
4. Crear `.github/ISSUE_TEMPLATE/`: fallo de instalación y fallo general, con `doctor --json` como campo obligatorio, y petición.
5. Actualizar `llms-install.md` y `docs/agents.md` a la instalación desde PyPI.

## 6. Guía de publicación

1. Escribir `docs/releasing.md`: comprobaciones previas, `uv build`, ensayo en TestPyPI, `uv publish`, `gh release create` con la etiqueta `v0.1.0b1`, `mcp-publisher publish` y comprobación final.
2. Incluir el orden correcto: hacer público el repositorio antes de anunciar los scripts, y publicar en PyPI antes que en el registro MCP.
3. Incluir qué hacer si falla a mitad: una versión subida a PyPI no se puede reutilizar, solo retirar y subir otra.

## 7. Material para probadores

1. Escribir `docs/beta-testing.md`: a quién se busca (hardware distinto), qué probar y cómo informar con `doctor --json`.
2. Preparar la tabla de resultados en [validation.md](validation.md).

## 8. Validación local y fusión

1. Ejecutar `scripts/check.sh` y `scripts/contract.sh`.
2. Probar `install.sh` en un HOME aislado con un wheel local, sustituyendo solo el origen del paquete.
3. Rellenar la evidencia y dejar la rama lista.
4. **Mantenedor:** revisar, hacer commit y fusionar en `main`.

## 9. Pendientes previos a publicar

Bloquean la tarea 10. El asistente ayuda donde tenga acceso y anota el resultado.

1. **Mantenedor:** ejecutar `scripts\check.ps1` y `scripts\contract.ps1` en Windows, y una generación real con NVIDIA.
2. **Mantenedor:** ejecutar `scripts/measure_profiles.py` en Windows. Después, trasladar las cifras al README y a `tech-stack.md`.
3. **Mantenedor:** probar en máquinas limpias Ubuntu y Windows 11 con NVIDIA: instalación, descarga interrumpida, archivo corrupto, espacio insuficiente y `uninstall` con un ComfyUI previo.
4. Hacer que un agente real complete la instalación siguiendo `llms-install.md`, en carpetas aisladas y con el perfil `fast`.
5. Corregir lo que aparezca. Si cambia el paquete, volver a la tarea 8.

## 10. Publicación

Todos los pasos son del **mantenedor**, siguiendo `docs/releasing.md`.

1. Ensayo en TestPyPI e instalación desde allí en Linux y Windows.
2. Hacer público el repositorio.
3. Publicar `0.1.0b1` en PyPI y crear la GitHub Release.
4. Publicar en el registro MCP.
5. Ejecutar los comandos de instalación de un comando en Linux y Windows desde sus URL públicas.

## 11. Probadores y cierre

1. **Mantenedor:** reunir entre 5 y 10 probadores externos en hardware distinto.
2. Anotar sus resultados, corregir lo que aparezca y sacar nuevas betas si hace falta.
3. Con al menos 3 instalaciones sin ayuda, marcar la fase en el roadmap (el usuario revisa antes).
