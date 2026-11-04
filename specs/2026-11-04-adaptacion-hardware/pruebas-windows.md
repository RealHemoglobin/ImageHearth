# Pruebas en Windows de la fase 7

Todo en PowerShell, sin administrador. Anota la salida de cada paso (o copia el texto) y mándamela: al final hay una plantilla. Si un paso falla, no sigas con los que dependen de él: cuéntame el error tal cual.

Las dos partes son independientes:

- **Parte A, antes de fusionar:** Windows 11 con NVIDIA.
- **Parte B, para cerrar la fase:** la AMD de 16 GB, después de fusionar.

## 0. Preparación

Los cambios de Linux no están en `main`: estás en la rama `feature/adaptacion-hardware`, y los cambios sin commitear no llegan a otra máquina. Haz el commit y `push` de la rama antes de empezar, y en Windows:

```powershell
git clone https://github.com/RealHemoglobin/ImageHearth.git
cd ImageHearth
git checkout feature/adaptacion-hardware
git log -1 --oneline
```

Si ya tienes un clon, `git fetch` y `git checkout feature/adaptacion-hardware`. Apunta el hash que muestra `git log` y cuántos GB libres tienes en el disco donde irán los modelos (`Get-PSDrive C`): `setup` descarga hasta decenas de GB.

Anota también tu GPU y su memoria:

```powershell
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
```

## Parte A: Windows con NVIDIA

### A1. `scripts\check.ps1`

Instala `uv` si falta, pasa ruff y los tests, y prueba el paquete construido como rueda en un entorno limpio.

```powershell
scripts\check.ps1
```

Esperado: termina sin errores. Anota cuántos tests pasan (en Linux son 415) y si alguno falla o se salta. Un fallo de tests de `processes` o de `memory_servers` en Windows es justo lo que buscamos.

### A2. `install.ps1` con `PATH`

Esto instala la rama que tienes clonada (el script detecta que está en un clon). Pregunta antes de descargar y de conectar agentes; **lee las licencias**, yo no puedo aceptarlas por ti.

```powershell
.\install.ps1
```

Observa y anota:

1. Qué perfil propone `setup` según tu GPU y cuánto va a descargar.
2. Al final, si imprime algo sobre el `PATH` ("is not in your PATH. Running: uv tool update-shell") y si acaba con "Open a new PowerShell window…".

Cierra esa ventana, abre **una PowerShell nueva** y comprueba:

```powershell
Get-Command imagehearth-mcp
imagehearth-mcp doctor
```

Esperado: `Get-Command` encuentra `imagehearth-mcp.exe` sin que hagas nada a mano, y `doctor` muestra `[OK] path`. Si no lo encuentra, copia la salida de `doctor` y de:

```powershell
[Environment]::GetEnvironmentVariable("Path", "User") -split ";"
uv tool dir --bin
```

### A3. `doctor` con el comando fuera del `PATH`

Quita temporalmente la carpeta de herramientas del `PATH` de esta ventana y llama a `doctor` con la ruta completa:

```powershell
$bin = uv tool dir --bin
$env:Path = ($env:Path -split ";" | Where-Object { $_ -ne $bin }) -join ";"
& "$bin\imagehearth-mcp.exe" doctor
```

Esperado: `[WARN] path` con una orden para arreglarlo (`uv tool update-shell`). Cierra la ventana después para recuperar el `PATH`.

### A4. Actualizar con el instalador (instalación ya existente)

En una PowerShell nueva, dentro del clon:

```powershell
.\install.ps1
```

Esperado: no descarga de nuevo los modelos que ya están, te vuelve a preguntar la conexión de agentes y termina sin errores. Anota si repite alguna descarga.

### A5. `scripts\contract.ps1`

Necesita el ComfyUI que acaba de instalar `setup`. No usa la GPU ni descarga modelos.

```powershell
scripts\contract.ps1
```

Esperado: `OK: 20 node types used by the workflows exist.` (o más, si hay más nodos). Si falta algún nodo, copia la lista.

### A6. `llama-server` oficial: parar y volver sin abrir consola

Es lo único que no se puede comprobar sin un Windows. El script arranca su propio `llama-server` en el puerto 8099, usa el mismo código que el motor para pararlo y relanzarlo, y lo para al terminar. No toca ningún otro proceso.

Descarga el binario oficial de CPU (25 MB) y un modelo pequeño (490 MB). Es de la release `b12110`; si prefieres otra, usa la CPU x64 de https://github.com/ggml-org/llama.cpp/releases.

```powershell
$dir = "$env:TEMP\llama-test"
New-Item -ItemType Directory -Force $dir | Out-Null
Invoke-WebRequest https://github.com/ggml-org/llama.cpp/releases/download/b12110/llama-b12110-bin-win-cpu-x64.zip -OutFile "$dir\llama.zip"
Invoke-WebRequest https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf -OutFile "$dir\model.gguf"
(Get-FileHash "$dir\llama.zip" -Algorithm SHA256).Hash
Expand-Archive "$dir\llama.zip" "$dir\bin"
Get-ChildItem -Recurse "$dir\bin" -Filter llama-server.exe
```

Comprueba que el hash del zip coincide con el que publica GitHub en la página de la release (campo "digest" del asset). Luego, **mirando la pantalla mientras corre**:

```powershell
uv run python scripts\check_llama_restart.py --server "$dir\bin\llama-server.exe" --model "$dir\model.gguf"
```

Esperado: todas las líneas `[OK]` y `RESULTADO: todo bien`. Anota además:

- Si en algún momento (al parar o al relanzar) aparece una **ventana de consola** nueva. No debería.
- El tiempo que tarda en volver ("vuelve a responder (X s)").
- Cualquier línea `[FALLA]`, con su texto.

Si falla en "se puede reproducir el arranque", el mensaje dice por qué (otro usuario, servicio, no se puede leer el entorno): cópialo. Al terminar, `Remove-Item -Recurse $dir` libera el espacio.

### A7. Mediciones de Windows

Cierra ComfyUI y cualquier modelo de lenguaje (Ollama, LM Studio…): el script se niega a medir con otros procesos usando más de 4 GB de GPU. Mide solo lo que tengas instalado.

```powershell
uv run python scripts\measure_profiles.py --output "$env:TEMP\medidas-nativas.json"
```

Si tu tarjeta tiene 24 GB, simula 16 GB y 8 GB con `--reserve-vram` (en una tarjeta menor, salta estas dos y dímelo):

```powershell
uv run python scripts\measure_profiles.py --workflow flux_dev --comfy-arg=--reserve-vram=8 --output "$env:TEMP\medidas-16gb.json"
uv run python scripts\measure_profiles.py --workflow sdxl_quality --comfy-arg=--reserve-vram=16 --output "$env:TEMP\medidas-8gb.json"
```

Cuando acaben, manda los JSON (están en `%TEMP%`). Los números de la 4090 en Linux, para comparar, son: FLUX fp8 ≈ 16,2 GB de VRAM propia y 11,1 s en caliente; SDXL ≈ 6,4 GB y 4,8 s.

### A8. Una generación real

Desde tu agente, pide una imagen con `quality` y comprueba que sale. Si tienes un `llama-server` o un Ollama con modelo cargado mientras generas, anota si el aviso dice que se paró y volvió, o solo que compartió la GPU.

## Parte B: AMD de 16 GB (después de fusionar)

Mismos pasos de A0 a A2 (usa `main` tras la fusión). Ten a mano el nombre exacto de la tarjeta (`Get-CimInstance Win32_VideoController | Select Name, AdapterRAM, DriverVersion`) y la versión del driver de AMD.

1. **`setup` propone la variante GGUF.** Ejecuta `imagehearth-mcp setup --profile quality` y, antes de aceptar nada, anota qué variante dice que va a instalar, el tamaño y las licencias. Debería proponer FLUX GGUF Q5 (la franja de 12 a 20 GB) y mostrar su licencia. Si lo ves distinto, o con una VRAM que no coincide con la tuya, cópialo.
2. **`doctor` muestra los argumentos de ComfyUI.** Ejecuta `imagehearth-mcp doctor` y copia la línea del check `gpu`, con `comfy_args`. Esperado en 16 GB: `--reserve-vram 1.0` (en Windows). Anota si ComfyUI arranca con ROCm.
3. **`quality` genera sin quedarse sin memoria**, aunque tarde más. Pide una imagen 1024×1024 desde el agente y anota el tiempo y si ve el aviso de memoria baja.
4. **`llama-server` de un solo modelo:** repite A6 en la AMD (el script ya hace el ciclo de parar y volver). Después, con un `llama-server` tuyo cargado, pide una imagen y comprueba que el aviso dice que se paró y volvió, y que sigue respondiendo con el mismo modelo.
5. Si ves un error de memoria o un cuelgue, ejecuta `imagehearth-mcp doctor --json` y mándamelo (incluye rutas locales con tu usuario; cámbialo si quieres).

## Qué mandarme

Copia esto y rellénalo (un "no sé" vale):

```text
Rama/commit: 
GPU y VRAM: 
Windows (versión): 

A1 check.ps1: OK / falla — tests: __ pasan, __ fallan
A2 install.ps1: perfil propuesto: ___; PATH en PowerShell nueva: sí / no
A3 doctor sin PATH: WARN con la orden: sí / no
A4 actualizar con el instalador: sin re-descargas: sí / no
A5 contract.ps1: OK / falla
A6 llama-server: RESULTADO ___; ventana de consola: sí / no; vuelve en __ s
A7 mediciones (VRAM propia / s en caliente): fp8 __ / __, GGUF __ / __, SDXL __ / __; simulado 16 GB: __; 8 GB: __
A8 generación con quality: OK / falla

Parte B (AMD): variante propuesta: ___; comfy_args: ___; quality genera: sí / no, __ s; llama-server: ___
```
