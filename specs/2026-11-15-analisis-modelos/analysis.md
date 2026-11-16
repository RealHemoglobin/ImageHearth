# Análisis de modelos de generación (fase 14)

Estado: **lista corta aprobada el 2026-11-15** (tarea 2 del [plan](plan.md)); Qwen-Image 2.1 queda descartado como referencia no comercial por decisión del usuario. Mediciones terminadas el 2026-11-16 (sección 6); decisión del usuario del 2026-11-16 en la sección 9. Datos de candidatos tomados el 2026-11-15 de las fichas y de la API de Hugging Face (tamaños en GB decimales); donde algo no consta en la ficha se dice. ComfyUI fijado: **0.43.0**, posterior a la incorporación nativa de todos los modelos de la lista corta, así que no hace falta versión mínima ni nodos personalizados (salvo GGUF, que ya usa `ComfyUI-GGUF` del catálogo).

## 1. Candidatos revisados

### Generación

| Modelo | Licencia | Descarga | Pesos (GB) | Codificador de texto / VAE | Nativo | Veredicto |
|---|---|---|---|---|---|---|
| **Z-Image-Turbo** (Tongyi-MAI) | Apache-2.0 | libre | bf16 12,31 · int8_convrot 6,20 · nvfp4 4,51 | Qwen3-4B 8,04 (fp8 mixto 5,63) · VAE `ae` 0,34 | sí | **Lista corta** |
| **FLUX.2 Klein 4B** (BFL) | Apache-2.0 | libre | bf16 7,75 | Qwen3-4B 8,04 (el mismo que Z-Image) · VAE FLUX.2 0,34 | sí | **Lista corta** (también edita) |
| **Chroma1-HD** (lodestones) | Apache-2.0 | libre | bf16 17,80 · fp8 escalado 9,19 | T5-XXL idéntico al de FLUX.1 · VAE de FLUX.1 | sí | **Lista corta** |
| **Qwen-Image** | Apache-2.0 | libre | bf16 40,86 · fp8 20,43 · GGUF Q4_K_M 13,07 · Q2_K 7,06 | Qwen2.5-VL-7B 16,58 (fp8 9,38) · VAE 0,25 | sí | **Lista corta** (texto en la imagen) |
| **HiDream-I1 Full** | MIT | libre (el codificador Llama 3.1 exige su propia licencia) | fp16 34,21 · fp8 17,11 · GGUF Q4_K_M 11,48 | CLIP-L + CLIP-G + T5 fp8 5,16 + Llama 3.1 8B fp8 9,08 · VAE `ae` = el de FLUX.1 | sí | **Lista corta** |
| Z-Image (base) | Apache-2.0 | libre | bf16 12,31 | como Turbo | sí | Descartado: misma familia que Turbo, 28–50 pasos; no aporta un nivel nuevo |
| HiDream-I1 Dev / Fast | MIT | libre | 34,21 (bf16) | como Full | sí | Descartado: destilados de Full; se mide solo Full |
| Chroma1-Base / Flash | Apache-2.0 | libre | 17,80 | como HD | sí | Descartado: HD es la versión final; Flash es una variante rápida del mismo modelo |
| Qwen-Image 2.1 y 2.1 Turbo | **Qwen Research License (solo investigación/evaluación; uso comercial requiere licencia aparte de Alibaba)** | libre | bf16 14,23 · int8 7,26 | Qwen3-VL-8B 17,53 · VAE 0,68 | sí (0.37/0.40) | Descartado por licencia: hay alternativa comercial en todos los niveles. Genera y edita en un solo modelo con 2K, así que se puede medir como referencia no comercial si lo pides |
| FLUX.2 dev | FLUX Non-Commercial v2.1 (uso comercial con licencia de BFL) | token + aceptar | bf16 64,45 · fp8 mixto 35,46 | Mistral-Small-3.2-24B 48,02 (fp8 18,03) | sí | Descartado: no comercial, 100+ GB entre pesos y codificador |
| FLUX.2 Klein 9B (y 9b-kv) | FLUX Non-Commercial | token + aceptar | bf16 18,16 | Qwen3-8B 16,38 | sí | Descartado: no comercial; el 4B es Apache-2.0 |
| SD3.5 Medium / Large / Large Turbo | Stability Community (gratis por debajo de 1 M$ de ingresos anuales; por encima, licencia Enterprise) | token + aceptar | 5,11 / 16,46 / 16,46 (+ codificadores 15–25) | CLIP-L, CLIP-G, T5 propios | sí | Descartado: condición de ingresos, descarga con aceptación, calidad inferior a los nuevos |
| HunyuanImage 2.1 | Tencent Community: **excluye UE, Reino Unido y Corea del Sur**, prohíbe usar las salidas para mejorar otros modelos | libre | 34,85 (fp8 17,90) + refinador | Qwen2.5-VL + byT5 | sí | Descartado: territorio excluido, 2K, mínimo 24 GB declarado |
| Lumina-Image 2.0 | Apache-2.0 | libre | 5,22 (bf16, repack) | Gemma-2 2B 5,23 · VAE `ae` | sí | Descartado: más antiguo y por debajo de Z-Image Turbo en el nivel de 8 GB |
| Sana / Sana 1.5 / Sprint | Apache-2.0 (con términos de Gemma) | libre | 2,4–18,9 | Gemma-2 + DC-AE | no se encontró soporte nativo | Descartado: sin soporte verificado en ComfyUI |
| PixArt-Σ | OpenRAIL++ | libre | 2,44 + T5 19,05 | T5 propio | no se encontró soporte nativo | Descartado: ídem, y calidad por debajo de SDXL |

### Edición

| Modelo | Licencia | Descarga | Pesos (GB) | Notas | Veredicto |
|---|---|---|---|---|---|
| **Qwen-Image-Edit-2511** | Apache-2.0 | libre | bf16 40,86 · fp8 mixto 20,53 · GGUF Q4_K_M 12,84 (unsloth) | mismo codificador y VAE que Qwen-Image; multi-imagen, consistencia de personas | **Lista corta** |
| **FLUX.2 Klein 4B** | Apache-2.0 | libre | 7,75 | la misma checkpoint edita (una o varias referencias) | **Lista corta** (ya en generación) |
| FLUX.1 Kontext Dev | FLUX.1 [dev] No Comercial | token | ya en el catálogo (`flux_kontext`) | referencia | Referencia, no candidato |
| Qwen-Image-Edit / 2509 | Apache-2.0 | libre | 40,86 / 20,43 fp8 | anteriores a 2511 | Descartado: 2511 los sustituye |
| HiDream-E1-1 | MIT | libre | bf16 34,21 | edición por instrucción, exige aceptar la licencia de Llama | Descartado: más pesado y menos capaz que Qwen-Edit; sin multi-referencia declarada |
| OmniGen2 | Apache-2.0 | libre | transformer 15,87 (F32) + mllm 15,02 | ~17 GB declarados, nativo desde 2025-07 | Descartado: peso en F32 y calidad inferior a Qwen-Edit y Klein |
| Step1X-Edit | Apache-2.0 | libre | 24,86 | sin soporte nativo encontrado | Descartado |
| Qwen-Image 2.1 (edición) | investigación | libre | ver arriba | | Descartado por licencia |

### Sin revisar en profundidad

El registro de cambios de ComfyUI lista modelos de 2026 con soporte nativo cuya licencia **no he verificado en su repositorio**: ERNIE-Image, LongCat-Image, Krea2 (RAW y Turbo), Boogu-Image, Ideogram 4 (pesos abiertos), HiDream-O1-Image, Ming Image 0.1, MOSS-Image, Ovis-Image, Kandinsky 5, JoyImageEdit, FLUX.3 Image Klein (licencia `flux-kommunity-license`, descarga con aceptación). Las fuentes secundarias citan ERNIE-Image, Boogu-Image y LongCat-Image como Apache/MIT. Quedan fuera de la lista corta por falta de verificación, no por calidad; dímelo si quieres que revise alguno antes de aprobar.

## 2. Lista corta propuesta

**Generación (5)** y **edición (2)**, todas con licencia comercial y sin token ni aceptación de condiciones (salvo que el codificador Llama de HiDream pida aceptar la licencia de Meta, a confirmar):

| Nivel | Generación | Edición |
|---|---|---|
| 8 GB | Z-Image-Turbo (int8 / fp8 + descarga), FLUX.2 Klein 4B, Qwen-Image GGUF Q2_K (con descarga) | Klein 4B |
| 16 GB | Z-Image-Turbo bf16, Chroma1-HD fp8, Klein 4B, HiDream GGUF Q4_K_M | Klein 4B, Qwen-Edit GGUF Q4_K_M |
| 24 GB | Qwen-Image fp8, HiDream fp8, Chroma bf16 | Qwen-Edit fp8 |
| 32+ GB | Qwen-Image bf16, HiDream fp16 | Qwen-Edit bf16 |

### Tamaño de descarga

| Conjunto | GB |
|---|---|
| Z-Image-Turbo: bf16 12,31 + int8 6,20 + Qwen3-4B 8,04 + VAE 0,34 | 26,9 |
| FLUX.2 Klein 4B: 7,75 + VAE FLUX.2 0,34 (codificador compartido) | 8,1 |
| Chroma1-HD: bf16 17,80 + fp8 9,19 (T5 y VAE ya instalados) | 27,0 |
| Qwen-Image: bf16 40,86 + fp8 20,43 + Q4_K_M 13,07 + Q2_K 7,06 + codificador fp8 9,38 + VAE 0,25 | 91,1 |
| Qwen-Image-Edit-2511: bf16 40,86 + fp8 20,53 + Q4_K_M 12,84 | 74,2 |
| HiDream-I1 Full: fp16 34,21 + fp8 17,11 + Q4_K_M 11,48 + codificadores 15,88 | 78,7 |
| **Total** | **≈ 306** |

Hay **83 GB libres** en `/home`. La descarga es a una carpeta temporal fuera del repositorio y se borra cada precisión al terminar de medirla; el pico simultáneo es ~55 GB (Qwen-Image bf16 con su codificador), así que cabe, pero se descargan unos 306 GB en total a lo largo de las mediciones.

## 3. Pendiente

- ~~Aprobación de la lista corta, de los tamaños y del espacio (tarea 2).~~ Hecha. Aprobada tal cual el 2026-11-15, con los tamaños y el espacio libre (83 GB) expuestos.
- Confirmar `int8_convrot` y `nvfp4` como precisiones soportadas por ComfyUI 0.43.0 (las fichas no lo dicen); si no, se miden fp8 o GGUF.
- Secciones 5 a 9 rellenadas el 2026-11-16; decisión del usuario anotada el 2026-11-16 (tarea 8).

## 4. Herramienta y entorno de medición

- `scripts/measure_models.py` con el registro `scripts/measure_models/registry.json` (repositorio, ruta, carpeta de cada peso; tamaño, SHA-256 y revisión se leen de Hugging Face al descargar y quedan en cada JSON) y un workflow por modelo en `scripts/measure_models/`. Se desvía del plan en dos cosas: el workflow es uno por modelo (y `-gguf` si cambia el cargador), no uno por precisión, porque el fichero de pesos va en un marcador `%UNET%`; y los pesos GGUF van en `diffusion_models`.
- Entorno: ComfyUI 0.43.0 propio en `/home/paco/measure-models/comfyui` (sha256 del catálogo, PyTorch 2.14.1+cu130, `ComfyUI-GGUF` en el commit del catálogo); pesos en `/mnt/NuevoVol/HF_Cache/measure`; imágenes PNG en `/mnt/NuevoVol/HF_Cache/measure/images`. Nada de esto está en el repositorio ni toca la instalación del usuario.
- ComfyUI 0.43.0 usa VRAM dinámica y no avisa de la carga parcial a RAM. La descarga se deduce de los MB "Staged" del log frente al pico de VRAM medido (hay descarga si el pico es menos del 90 % del mayor modelo preparado). Es una heurística: en 32+ GB, la estimación sin descarga es VRAM medida + MB descargados y se marca como estimada.
- Con prompt y semilla idénticos ComfyUI reutiliza la caché del grafo y los tiempos salen falsos (0,3 s); por eso calentamiento y medidas usan semillas distintas (`1234+1000`, `1234+2000+n`) y las imágenes de la comparativa usan `1234`.
- Probado de punta a punta con Klein 4B (generación en 8 GB y edición en 24 GB): descarga con SHA-256, arranque, medidas e imágenes correctas. Los demás workflows (Z-Image, Chroma, Qwen, HiDream, Qwen-Edit y GGUF), escritos a partir de las plantillas oficiales, funcionaron a la primera.
- Comfy-Org/Qwen3-4B: el `qwen_3_4b.safetensors` de Z-Image y el de Klein se tratan como el mismo fichero (se descarga una vez); la medición lo verifica por SHA-256 contra cada repositorio.

## 5. Criterios y parámetros

- **Criterios:** licencia comercial sin token ni aceptación; memoria (peso en disco y pico de VRAM/RAM por nivel); calidad en la comparativa; velocidad (segundos por imagen con el modelo ya cargado); integración (nodos nativos de ComfyUI o `ComfyUI-GGUF`); capacidades (texto en la imagen, edición).
- **Parámetros:** 1024×1024, semilla 1234, un workflow por modelo tomado de las plantillas oficiales de ComfyUI (pasos, CFG y muestreador de cada una), prompt negativo constante donde el modelo lo usa. Los parámetros exactos están en `scripts/measure_models/*.json`. Edición: imagen de entrada `specs/2026-11-06-eleccion-modelo-quality/comparison/flux_dev-1.png`.
- **Equipo:** RTX 4090 24 GB, 60 GB de RAM, controlador 580.178.04, ComfyUI 0.43.0. Línea base de VRAM del escritorio ~2,3–2,7 GB, que se resta del pico.
- **Niveles:** 8, 16 y 24 GB se simulan con `--reserve-vram` (24 − nivel). **32+ GB** es la tarjeta entera: no existe una tarjeta de 32 GB en el equipo, así que ese nivel solo difiere de 24 GB cuando hay descarga (Qwen-Image bf16, marcada como estimada).

## 6. Mediciones

Cada celda: **segundos por imagen con el modelo cargado** (mediana de 3 ejecuciones) · **pico de VRAM sobre la línea base (GB)** · descarga a RAM si la hay. Los pesos en disco incluyen codificador de texto y VAE. Las 54 mediciones terminaron en `ok`. Datos completos en `measurements/*.json` y `.log`.

| Modelo | Precisión | Pesos en disco (GB) | 8 GB | 16 GB | 24 GB | 32+ GB | RAM pico (GB) |
|---|---|---|---|---|---|---|---|
| Z-Image-Turbo | bf16 | 19.3 | 4.1 s · 5.2 · descarga 3.7 | 3.6 s · 13.5 | 3.6 s · 18.0 | 3.6 s · 18.0 | 21 |
| Z-Image-Turbo | int8 | 11.3 | 2.0 s · 5.2 | 2.0 s · 11.4 | 2.0 s · 11.5 | 2.0 s · 11.4 | 14 |
| FLUX.2 Klein 4B | bf16 | 15.0 | 1.5 s · 5.3 | 1.3 s · 12.9 | 1.3 s · 13.0 | 1.3 s · 13.0 | 18 |
| Chroma1-HD | bf16 | 21.7 | 37.5 s · 5.1 · descarga 8.8 | 27.4 s · 13.2 | 25.9 s · 18.1 | 25.9 s · 18.1 | 24 |
| Chroma1-HD | fp8 | 13.7 | 19.3 s · 5.3 | 17.7 s · 13.5 | 17.7 s · 13.5 | 17.7 s · 13.5 | 16 |
| Qwen-Image | bf16 | 47.0 | 53.6 s · 5.6 · descarga 30.1 | 40.7 s · 13.7 · descarga 22.1 | 33.2 s · 18.8 · descarga 16.9 | 33.6 s · 18.8 · descarga 16.9 (estimado) | 48 |
| Qwen-Image | fp8 | 28.0 | 30.8 s · 5.3 · descarga 11.0 | 26.2 s · 13.6 · descarga 2.7 | 24.3 s · 18.0 | 24.3 s · 18.1 | 29 |
| Qwen-Image | q2k | 15.6 | 44.3 s · 4.8 | 35.7 s · 10.0 | 35.8 s · 12.4 | 35.8 s · 12.8 | 15 |
| Qwen-Image | q4km | 21.1 | 60.3 s · 4.7 | 39.9 s · 10.4 | 38.3 s · 16.4 | 37.3 s · 16.2 | 21 |
| HiDream-I1 Full | fp8 | 31.0 | 73.1 s · 5.5 · descarga 7.9 | 68.4 s · 13.6 | 67.7 s · 17.5 | 64.4 s · 18.4 | 33 |
| HiDream-I1 Full | q4km | 25.8 | 95.7 s · 5.4 · descarga 5.9 | 76.7 s · 11.4 | 77.8 s · 17.9 | 78.5 s · 17.5 | 26 |
| Klein 4B (edición) | bf16 | 15.0 | 2.5 s · 5.4 | 2.5 s · 13.4 | 2.5 s · 13.6 | 2.5 s · 13.6 | 18 |
| Qwen-Image-Edit-2511 | fp8 | 28.1 | 120.8 s · 5.8 · descarga 10.6 | 112.5 s · 13.6 · descarga 2.6 | 112.9 s · 17.8 | — | 30 |
| Qwen-Image-Edit-2511 | q4km | 20.9 | 173.0 s · 6.0 | 140.0 s · 10.4 | 137.2 s · 15.7 | — | 26 |

Notas y límites:

- **En 8 GB el pico de VRAM es el tope del nivel**, no una necesidad: ahí ComfyUI carga lo que cabe y reparte el resto. La detección de descarga es una heurística (ver sección 4) y puede no avisar en 8 GB con GGUF (Qwen q2k/q4km, HiDream q4km, Qwen-Edit q4km); los tiempos sí son reales.
- **Qwen-Image bf16 en 32+ GB** no se pudo medir de verdad: estimación de 38,1 GB de VRAM sin descarga, así que ni en 32 GB cabe entero. El tiempo de la fila es el de 24 GB.
- **No medido, por decisión del 2026-11-16** para acortar la tanda tras 46 mediciones sin fallos: HiDream fp16, Qwen-Edit bf16 y Qwen-Edit en 32+ GB. En 32+ GB los modelos que caben en 24 GB tienen el mismo resultado.
- El tiempo en frío (primera ejecución) está en cada JSON; en los bf16 grandes está dominado por la lectura del disco y no es comparable.
- **Windows con 16 GB no se ha medido** (opcional para quien mantiene el proyecto): los datos de 16 GB son una simulación en Linux.

## 7. Comparativa de calidad

Imágenes JPG (512 px, <100 KB) y rejillas en [`comparison/`](comparison/). Modelos en su precisión más alta medida sin descarga a 24 GB (HiDream fp8; Qwen-Image bf16 con descarga). SDXL, FLUX.1 Schnell y FLUX.1 Dev son las imágenes de la fase 9 (mismos prompts 1–3 y semilla; no se regeneraron para los prompts 4 y 5).

- Prompts 1–3: [`grid-prompt1.jpg`](comparison/grid-prompt1.jpg), [`grid-prompt2.jpg`](comparison/grid-prompt2.jpg), [`grid-prompt3.jpg`](comparison/grid-prompt3.jpg).
- Prompts 4–5: [`grid-prompt4.jpg`](comparison/grid-prompt4.jpg), [`grid-prompt5.jpg`](comparison/grid-prompt5.jpg) (sin referencias).
- Cuantizaciones de Qwen-Image: [`grid-cuantizaciones-qwen.jpg`](comparison/grid-cuantizaciones-qwen.jpg).
- Edición: [`grid-edicion1.jpg`](comparison/grid-edicion1.jpg) (cielo estrellado) y [`grid-edicion2.jpg`](comparison/grid-edicion2.jpg) (cartel OPEN).
- **Kontext no se midió como referencia de edición** (habría que descargar sus pesos para una referencia no comercial): se sacrificó para acortar la tanda.

### Notas de calidad (juicio visual mío, una semilla por prompt: orientativo)

| Prompt | Observaciones |
|---|---|
| 1 faro | Todos componen bien. Qwen-Image y Z-Image tienen aspecto más fotográfico y limpio; HiDream es el más saturado; Klein y Chroma, intermedios. Sin diferencia clara respecto a FLUX.1 Dev. |
| 2 retrato | Caras convincentes en todos, sin manos. Z-Image y Qwen-Image, piel más natural; HiDream con más contraste y textura; Klein y Chroma, algo más suaves. A la altura de FLUX.1. |
| 3 cartel "OPEN" | Texto legible en Z-Image, Qwen-Image, HiDream, FLUX.1 Dev y Schnell. **Klein escribe "OPPEN"** y Chroma lo hace pequeño y torcido; SDXL no lo pone. En Qwen-Image la cabaña sale pequeña. |
| 4 composición | **Ninguno cumple todo** (3 astronautas, un robot, taza azul a la izquierda, perro durmiendo). Qwen-Image es el más cercano en escena y detalle (dos astronautas y robot, taza y perro); HiDream pone tres astronautas y no se ve robot; Klein y Chroma dibujan personas sin traje. |
| 5 acuarela | Chroma y HiDream son los que más parecen acuarela; Z-Image añade mucha textura; Qwen-Image se queda en ilustración digital limpia. |
| Cuantización Qwen-Image | bf16, fp8 y Q4_K_M son casi indistinguibles; **Q2_K pierde detalle y suaviza el cielo**, pero mantiene la composición y los objetos. |
| Edición: cielo | Klein cambia el cielo pero deja el reflejo naranja en el mar (cambio parcial); Qwen-Edit reilumina toda la escena (mar verdoso) y cambia más de lo pedido. |
| Edición: cartel | Ambos añaden un cartel legible con OPEN y respetan el resto; el de Qwen-Edit es más grande y claro, el de Klein, pequeño. |

## 8. Tabla final por nivel (propuesta)

Tiempos de la sección 6. «Edición» y «alternativa comercial» son las opciones de la lista corta (todas con licencia comercial).

| Nivel | Recomendada (generación) | Otras opciones | Edición |
|---|---|---|---|
| 8 GB | **FLUX.2 Klein 4B** bf16 (1,5 s, 7,75 GB de pesos) | Z-Image-Turbo int8 (2,0 s); Qwen-Image Q2_K (44 s, con pérdida de detalle; el texto en la imagen no se ha probado en Q2_K) | Klein 4B (2,5 s) |
| 16 GB | **Z-Image-Turbo** bf16 (3,6 s) | Chroma1-HD fp8 (17,7 s); Qwen-Image Q4_K_M (40 s); HiDream Q4_K_M (77 s) | Qwen-Edit Q4_K_M (140 s, sin descarga) o Klein 4B |
| 24 GB | **Qwen-Image fp8** (24 s) | Chroma1-HD bf16 (26 s); HiDream fp8 (68 s) | Qwen-Edit fp8 (113 s) |
| 32+ GB | **Qwen-Image fp8** (24 s): bf16 solo aporta calidad marginal (casi igual) a 33 s, con ~38 GB para no descargar | HiDream fp8 | Qwen-Edit fp8 |

Qwen-Edit tarda de 2 a 3 minutos por imagen en cualquier nivel: su valor es la calidad de la edición, no la velocidad. Klein 4B es el único que edita en segundos.

## 9. Decisión para la fase 15

**Decisión del usuario, 2026-11-16:** se integran **todas** las opciones de la lista corta. La elección final es de quien instala: ImageHearth muestra las mediciones (tamaño, tiempos, VRAM, licencia) y recomienda según el hardware, sin esconder ninguna.

| Modelo | Precisiones ofrecidas (medidas) | Avisos para quien elige |
|---|---|---|
| Z-Image-Turbo | int8, bf16 | Muy rápido (2–4 s); nivel de 8 GB con int8 |
| FLUX.2 Klein 4B | bf16 (genera y edita) | El más rápido (1,5 s; edición 2,5 s). Escribió «OPPEN» en el prompt del cartel |
| Chroma1-HD | fp8, bf16 | 18–26 s; bf16 en 8 GB va con descarga a RAM (37 s) |
| Qwen-Image | Q2_K, Q4_K_M, fp8, bf16 | 24–60 s; bf16 pesa 47 GB y con 24 GB descarga 17 GB; Q2_K pierde detalle |
| HiDream-I1 Full | Q4_K_M, fp8 | El más lento (64–96 s) y 26–31 GB de descarga; mostrar y confirmar la licencia de Llama 3.1 |
| Qwen-Image-Edit-2511 | Q4_K_M, fp8 | 2–3 min por imagen; edita más de lo pedido (reilumina la escena) |

- No medidos, y por tanto no ofrecidos hasta medirlos: HiDream fp16, Qwen-Edit bf16, Qwen-Edit en 32+ GB, Kontext como referencia, Windows 16 GB.
- Descartados por licencia: FLUX.2 dev, Klein 9B, Qwen-Image 2.1, SD3.5, HunyuanImage 2.1 (sección 1).
- Por modelo en la fase 15: entrada en `models.toml`, workflow con el cargador correcto, `ComfyUI-GGUF` (ya en el catálogo) y textos de `setup` por nivel.

## Fuentes

Fichas y API en Hugging Face de cada repositorio citado (`Qwen/*`, `Comfy-Org/*`, `Tongyi-MAI/*`, `black-forest-labs/*`, `HiDream-ai/*`, `lodestones/*`, `stabilityai/*`, `tencent/HunyuanImage-2.1`, `Alpha-VLLM/Lumina-Image-2.0`, `OmniGen2/OmniGen2`, `stepfun-ai/Step1X-Edit`, GGUF de `city96`, `unsloth` y `QuantStack`) y el [registro de cambios de ComfyUI](https://docs.comfy.org/changelog). Los hashes y revisiones exactas se fijarán al descargar.
