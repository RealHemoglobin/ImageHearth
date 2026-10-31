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

- [ ] `ollama_mode = "off"`: generación con `fast` y con `quality`, sin tocar Ollama; el estado no es `degraded`.
- [ ] `ollama_mode = "auto"` con el servicio Ollama detenido: generación correcta, sin avisos de fallo y sin `degraded`.
- [ ] `auto` con Ollama activo y un modelo cargado: se descarga para generar y se restaura al terminar.
- [ ] Ollama cae con modelos cargados a mitad de sesión: se conserva la protección y el mensaje es claro.
- [ ] ComfyUI arranca sin `IMPORT FAILED` con el nodo `imagehearth_status`, y el endpoint devuelve su versión.
- [ ] Sin el nodo en `custom_nodes`: la generación funciona con `/system_stats`, hay un aviso y no aparece `recovery_required`.
- [ ] Con un ComfyUI ajeno en el puerto: el motor avisa y no lo reinicia ni lo mata.
- [ ] Matar ComfyUI a mitad de sesión: la recuperación reinicia solo la instancia registrada y la siguiente generación funciona.
- [ ] Los logs son un archivo por proceso y la limpieza por antigüedad elimina los viejos.
- [ ] Edición con Kontext tras la migración del nodo.

### Windows con NVIDIA (no bloquea el merge)

- [ ] `scripts\check.ps1` en verde.
- [ ] Generación real con ComfyUI instalado a mano.
- [ ] Matar el proceso a mitad de sesión: la recuperación funciona.
- [ ] Los logs se crean sin errores de renombrado y `os.replace` no falla por bloqueos transitorios.

Si no se hace antes de fusionar, se registra en la evidencia como pendiente y la fase 2 no se da por cerrada en el roadmap hasta completarlo.

### macOS

- [ ] No se verifica en esta fase y no se anuncia como soportado: anotarlo en la evidencia.

## Lista para fusionar

- [ ] `scripts/check.sh` en verde en local.
- [ ] Prueba de contrato `/object_info` en verde en Linux.
- [ ] Las 7 herramientas conservan nombres, parámetros y resultados, revisado en el diff (solo cambia el texto de los mensajes).
- [ ] Todos los mensajes, la skill y los tests están en inglés con `WARNING`.
- [ ] README (ambos), `tech-stack.md` y `THIRD_PARTY_NOTICES.md` actualizados.
- [ ] Instalación local migrada: paquete reinstalado y nodo antiguo sustituido.
- [ ] Roadmap actualizado con las tareas de la fase 2 verificadas.
- [ ] Cambios revisados por el usuario, que realiza el commit.
- [ ] Windows: resultado documentado en la evidencia (hecho o pendiente).

## Evidencia

| Comprobación | Resultado | Fecha |
|---|---|---|
| `scripts/check.sh` en Linux | | |
| Prueba de contrato `/object_info` en Linux | | |
| Generación sin Ollama (`off` y servicio detenido) | | |
| Ollama con modelo cargado y restauración | | |
| Nodo `imagehearth_status` sin `IMPORT FAILED` | | |
| Generación sin el nodo (alternativa `/system_stats`) | | |
| Instancia ajena de ComfyUI intacta | | |
| Recuperación tras matar el proceso en Linux | | |
| `scripts\check.ps1` en Windows | | |
| Generación real y recuperación en Windows | | |
| macOS | Sin verificar, no anunciado | |
