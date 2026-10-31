# Validación: Fase 2

## Criterios de finalización

- Los tests pasan en Linux; en Windows se ejecuta `scripts/check.ps1` y se documenta el resultado.
- Una generación completa funciona sin Ollama, verificado con hardware real en Linux.
- ComfyUI ya no muestra `IMPORT FAILED` para el nodo `imagehearth_status`.
- Sin el nodo instalado, el motor genera, avisa y no entra en `recovery_required`.
- Nunca se mata ni reinicia una instancia de ComfyUI ajena.
- `git grep -nE "fcntl|/proc|SIGKILL|ADVERTENCIA" -- src tests` no devuelve nada injustificado.
- Una generación real y la recuperación tras matar el proceso a mitad de sesión funcionan en Windows con NVIDIA (no bloquea el merge: ver más abajo).
- macOS queda sin verificar y no se anuncia como soportado.

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

```bash
git grep -nE "fcntl|/proc|SIGKILL|ADVERTENCIA" -- src tests
```

```bash
git grep -n "imageengine_status" -- src tests README.md README.es.md
```

El último comando no debe devolver nada: el nodo pasa a `imagehearth_status`.

En Windows (PowerShell):

```powershell
scripts\check.ps1
```

```powershell
scripts\contract.ps1
```

No se exige cobertura mínima. La puerta de calidad obligatoria de [tech-stack](../tech-stack.md) es `scripts/check.sh` más la prueba de contrato.

## Validaciones manuales

### Linux con RTX 4090

- [x] `ollama_mode = "off"`: generación con `fast` y con `quality`, sin tocar Ollama; el estado no es `degraded`.
- [x] `ollama_mode = "auto"` con el servicio Ollama detenido: generación correcta, sin avisos de fallo y sin `degraded`.
- [x] `auto` con Ollama activo y un modelo cargado: se descarga para generar y se restaura al terminar.
- [x] Ollama cae con modelos cargados a mitad de sesión: se conserva la protección y el mensaje es claro.
- [x] ComfyUI arranca sin `IMPORT FAILED` con el nodo `imagehearth_status`, y el endpoint devuelve su versión.
- [x] Sin el nodo en `custom_nodes`: la generación funciona con `/system_stats`, hay un aviso y no aparece `recovery_required`.
- [x] Con un ComfyUI ajeno en el puerto: el motor avisa y no lo reinicia ni lo mata.
- [x] Matar ComfyUI a mitad de sesión: la recuperación reinicia solo la instancia registrada y la siguiente generación funciona.
- [x] Los logs son un archivo por proceso y la limpieza por antigüedad elimina los viejos.
- [x] Edición con Kontext tras la migración del nodo.

### Windows con NVIDIA (no bloquea el merge)

- [x] `scripts\check.ps1` en verde.
- [x] Generación real con ComfyUI instalado a mano.
- [x] Matar el proceso a mitad de sesión: la recuperación funciona.
- [x] Los logs se crean sin errores de renombrado y `os.replace` no falla por bloqueos transitorios.

Si no se hace antes de fusionar, se registra en la evidencia como pendiente y la fase 2 no se da por cerrada en el roadmap hasta completarlo.

### macOS

- [x] No se verifica en esta fase y no se anuncia como soportado: anotarlo en la evidencia.

## Lista para fusionar

- [x] `scripts/check.sh` en verde en local.
- [x] Prueba de contrato `/object_info` en verde en Linux.
- [ ] Las 7 herramientas conservan nombres, parámetros y resultados, revisado en el diff (solo cambia el texto de los mensajes).
- [x] Todos los mensajes, la skill y los tests están en inglés con `WARNING`.
- [x] README (ambos), `tech-stack.md` y `THIRD_PARTY_NOTICES.md` actualizados.
- [x] Instalación local migrada: paquete reinstalado y nodo antiguo sustituido.
- [x] Roadmap actualizado con las tareas de la fase 2 verificadas.
- [ ] Cambios revisados por el usuario, que realiza el commit.
- [x] Windows: resultado documentado en la evidencia (hecho o pendiente).

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` en Linux | Verde: ruff y 91 tests, también contra el wheel | 2026-10-31 |
| Prueba de contrato `/object_info` en Linux | Verde: 17 tipos de nodo | 2026-10-31 |
| Generación sin Ollama (`off` y servicio detenido) | Real en Linux con RTX 4090: `off` (`fast` y `quality`) y `auto` con Ollama detenido, sin avisos ni `degraded` | 2026-10-31 |
| Ollama con modelo cargado y restauración | Real (Ollama en Docker, vía API): se descarga antes de arrancar ComfyUI y se restaura al terminar. Corregido el orden de `generation_session()` (antes ComfyUI arrancaba con la VRAM ocupada) y añadido test de regresión. Ollama que cae a mitad de sesión: protección conservada y mensaje claro | 2026-10-31 |
| Nodo `imagehearth_status` sin `IMPORT FAILED` | Real: ComfyUI lo carga y `/imagehearth/status` devuelve `version: 1` | 2026-10-31 |
| Generación sin el nodo (alternativa `/system_stats`) | Real: genera, un aviso, estado `degraded` por el nodo y sin `recovery_required` | 2026-10-31 |
| Instancia ajena de ComfyUI intacta | Real: el motor avisa y no la reinicia ni la mata | 2026-10-31 |
| Recuperación tras matar el proceso en Linux | Real: `kill -9` a ComfyUI y la siguiente generación lo relanza y registra el nuevo PID | 2026-10-31 |
| Edición con Kontext tras la migración | Real: correcta | 2026-10-31 |
| `scripts\check.ps1` en Windows | Verde: ruff y 92 tests, también contra el wheel. `scripts/check.sh` en Linux repetido después: verde con 92 tests | 2026-10-31 |
| Generación real, recuperación y logs en Windows | Correctos, según confirma el usuario (RTX 4090 y ComfyUI instalado a mano) | 2026-10-31 |
| macOS | Sin verificar, no anunciado | |
