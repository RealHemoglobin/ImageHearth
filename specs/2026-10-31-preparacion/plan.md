# Plan: Fase 0

Rama: `feature/preparacion`. Los pasos marcados como **manual** los hace el usuario.

## 1. Elegir el nombre (hecho)

Elegido **ImageHearth** el 2026-10-31 y anotado en `specs/roadmap.md` y en `requirements.md`.

## 2. Licencias

1. Añadir `LICENSE` con MIT en la raíz.
2. Añadir `extras/comfyui_custom_nodes/imageengine_status/LICENSE` con GPL-3.0.
3. Revisar en su origen las licencias de FLUX Dev, FLUX Kontext y SDXL Turbo, y las de las dependencias directas (`mcp`, `pillow`, `requests`).
4. Escribir `THIRD_PARTY_NOTICES.md`: componente, licencia, enlace, si admite uso comercial y fecha de revisión. Indicar que los pesos no se redistribuyen y que el documento no es asesoramiento legal.
5. Enlazar las licencias desde ambos README.

## 3. Entorno de desarrollo

1. Instalar `uv` si no está disponible.
2. Crear `pyproject.toml` sin empaquetar (`[tool.uv] package = false`), con las dependencias de `requirements.txt` y un grupo `dev` con `pytest` y `ruff`.
3. Configurar `pytest` (`testpaths`, `pythonpath = ["."]`) y `ruff`.
4. Comprobar que la carpeta `mcp/` no oculta la dependencia `mcp` al ejecutar `pytest` desde la raíz, incluido el test que lanza `mcp/server.py`. Si la oculta, resolverlo solo con configuración de pruebas: eliminar la carpeta es de la fase 1.
5. Generar `uv.lock` y ejecutar los tests en un entorno limpio con `uv sync`.
6. Decidir qué hacer con `requirements.txt`: mantenerlo mientras el README lo use para instalar y anotar su retirada en la fase 1.
7. Documentar en ambos README cómo preparar el entorno y lanzar los tests.

## 4. Lint

1. Ejecutar `uv run ruff check .` y revisar los avisos.
2. Corregir los que no cambien la lógica y excluir el resto de forma explícita, con motivo.
3. Volver a pasar los tests.

## 5. CI

1. Crear `.github/workflows/ci.yml`: se ejecuta en `push` a `main` y en `pull_request`, sobre `ubuntu-latest`, con `astral-sh/setup-uv` en versión fijada.
2. Pasos: `uv sync --locked`, `uv run ruff check .` y `uv run pytest`.
3. Comprobar en local esos mismos comandos.

## 6. Repositorio remoto

1. **Manual:** crear el repositorio privado `RealHemoglobin/ImageHearth`, vacío.
2. Sustituir `OWNER/ImageEngine` por `RealHemoglobin/ImageHearth` en `README.md` y `README.es.md`, y quitar la frase que pide sustituir `OWNER`.
3. Con confirmación del usuario, añadir el remoto y subir `main` y `feature/preparacion`.
4. Abrir el PR y comprobar que el CI pasa en la rama.

## 7. Cierre

1. Marcar las tareas de la fase 0 en `specs/roadmap.md` y actualizar la tabla de decisiones abiertas. Dejar el hardware Mac como pendiente para la fase 4.
2. Completar la evidencia en `validation.md`.
3. Con confirmación del usuario, fusionar en `main` y comprobar el CI en verde en `main`.

## Dependencias

- El paso 6 depende del paso 5.
- El paso 5 depende de los pasos 3 y 4.
- El paso 2 se puede hacer en paralelo.
