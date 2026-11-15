# Selección de LoRAs para SDXL 1.0

Fecha: 2026-11-15. Hardware: RTX 4090 (24 GB), ComfyUI 0.43.0, `sdxl_base` con la LoRA de detalle fija a 0,5, 30 pasos, 1024x1024, semilla 1234, `style: "auto"`. Script: `scripts/measure_loras.py`. Imágenes y mediciones en [comparison/](comparison/) (hoja de contacto por LoRA y `measurements.json`); las imágenes completas se guardaron fuera del repositorio.

## Método

1. **Búsqueda** en Hugging Face (`filter=lora` + base `stabilityai/stable-diffusion-xl-base-1.0`, ordenado por descargas, y búsquedas por estilo: fotorrealismo, ilustración, anime, pixel art, acuarela, detalle, 3D, dibujo, línea).
2. **Filtro de licencia y origen**, antes de descargar nada: solo OpenRAIL++, CreativeML OpenRAIL-M, Apache-2.0 o MIT declaradas en el repositorio, sin acceso restringido ni token, de autor identificable. Se descartan los espejos masivos de Civitai (`Muapi/*`, `John6666/*`), las licencias `other`/sin licencia y las que dicen «solo investigación».
3. **Medición.** Tres prompts (`a red fox sitting in a snowy forest at dawn`, `a lighthouse on a rocky coast at sunset`, `a portrait of a young woman reading a book in a cafe`), la misma semilla y cuatro imágenes por prompt:
   1. sin LoRA;
   2. **el mismo texto, sin LoRA** (con las palabras de activación): separa lo que hace la LoRA de lo que hacen sus palabras;
   3. con la LoRA a su peso recomendado;
   4. con la LoRA a la mitad de ese peso.
4. **Criterio.** Se queda una LoRA solo si cambia la imagen de forma visible *respecto al mismo texto sin LoRA*. Se mide como la diferencia media de píxeles (0 a 255, en gris y a 128x128) entre la columna 2 y la columna 3; menos de 20 en media es que casi todo el efecto lo hacen las palabras de activación, y 0 es que ComfyUI no ha cargado la LoRA.

Resultado: se probaron **18** candidatas con licencia válida y se eligen **10**.

## Elegidas

Diferencia media respecto al mismo texto sin LoRA, al peso recomendado y a la mitad. Todas generan sin errores a 1024x1024 en la misma sesión (lote de 10 imágenes con una LoRA distinta cada una, a través del motor, con `ImageHearth-LoRAs` correcto en cada PNG).

| Nombre | Categoría | Origen (revisión fija en `models.toml`) | Licencia | Tamaño | Peso | Palabras | Dif. peso / mitad |
|---|---|---|---|---|---|---|---|
| `pixel-art` | pixel-art | `nerijs/pixel-art-xl` | CreativeML OpenRAIL-M | 171 MB | 1,0 | `pixel art` | 44,8 / 26,6 |
| `anime-pop` | anime | `alvdansen/popartanime` (`…-000012`) | CreativeML OpenRAIL-M | 228 MB | 1,0 | `daiton style` | 88,3 / 43,5 |
| `photorealism` | photo | `prithivMLmods/Canopus-Realism-LoRA` | CreativeML OpenRAIL-M | 456 MB | 1,0 | `PhotoRealism` | 27,9 / 21,3 |
| `papercut` | illustration | `TheLastBen/Papercut_SDXL` | CreativeML OpenRAIL-M | 341 MB | 1,0 | `papercut` | 65,6 / 49,6 |
| `flat-illustration` | illustration | `ramel2/emotional-flat-illustration-sdxl-lora` | CreativeML OpenRAIL-M | 457 MB | 1,0 | `minimal flat illustration` | 49,0 / 27,4 |
| `lineart` | illustration | `artificialguybr/LineAniRedmond-LinearMangaSDXL-V2` | CreativeML OpenRAIL-M | 171 MB | 1,0 | `LineAniAF`, `lineart` | 29,5 / 21,2 |
| `pencil-art` | illustration | `prithivMLmods/Canopus-Pencil-Art-LoRA` | Apache-2.0 | 456 MB | 1,0 | `Pencil Art` | 42,6 / 27,8 |
| `crayon` | illustration | `ostris/crayon_style_lora_sdxl` | Apache-2.0 | 48 MB | 1,0 | — | 71,8 / 37,0 |
| `3d-render` | 3d | `goofyai/3d_render_style_xl` | Apache-2.0 | 85 MB | 0,85 | `3d render` | 22,0 / 14,2 |
| `clay-animation` | 3d | `artificialguybr/ClayAnimationRedmond` | CreativeML OpenRAIL-M | 171 MB | 1,0 | `Clay Animation` | 42,5 / 27,7 |

Total del catálogo: 2,6 GB. Los pesos recomendados salen de los README de cada autor (0,7–1,0) y se comprobaron en las hojas: a 1,0 el estilo es claro y a la mitad se nota menos, sin romper la imagen.

Notas:

- **`photorealism`** es el efecto más sutil de los elegidos: mejora luz, piel y profundidad, no cambia de medio. Es la única candidata válida de fotorrealismo.
- **`3d-render`** y **`lineart`** quedan en el límite del criterio; se mantienen porque el cambio es claro en las tres imágenes (acabado de animación 3D y línea limpia sin relleno).
- **`anime-pop`** es un anime ilustrado de colores planos, no un anime «clásico»: la descripción del catálogo lo dice.
- El prompt de las hojas es con `style: "auto"`: con una LoRA de otro medio no se añaden pistas fotográficas (comprobado: la columna 2 y la 3 comparten texto).

## Descartadas, con motivo

| Candidata | Licencia | Motivo |
|---|---|---|
| `ostris/watercolor_style_lora_sdxl` | Apache-2.0 | **Funciona pero empeora el resultado:** con SDXL 1.0 a peso 1,0 da una ilustración vectorial plana, y a 0,5 una pintura oscura; el prompt «watercolor painting» sin LoRA produce una acuarela mejor (diferencia 68,5 / 78,0, a favor del control). No hay otra candidata de acuarela válida |
| `ntc-ai/SDXL-LoRA-slider.anime`, `.oil-painting`, `.extremely-detailed`, `.cinematic-lighting`, `.Product-Photo` | MIT | Son *sliders* de rango 1: con peso 2 (el máximo que admite ImageHearth) cambian la composición un poco (diferencia 7,9 / 6,8 / 9,6 / 12,5 / 13,8) pero casi todo el estilo lo hacen las palabras de activación. No justifican la descarga. **No hay candidata válida de «detalle»** |
| `Twinber/sdxl-oldbook-illustrations-lora` | OpenRAIL++ | **ComfyUI no la carga** (formato PEFT de diffusers): el resultado es idéntico con la LoRA a cualquier peso y sin ella (diferencia 0,0). El grabado que se ve es solo del texto |
| `strkyyy/anime-cel-shaded` | OpenRAIL++ | Mismo problema de formato: diferencia 0,0 |
| `alpgures/amateur-phone-photo-realism-sdxl-lora` | OpenRAIL++ | Marcada `not-for-all-audiences`, entrenada con fotos de hombres adultos: no es un estilo general |
| `ostris/photorealistic-slider-sdxl-lora`, `ostris/ikea-instructions-lora-sdxl` | `other` | Licencia no incluida en la lista permitida |
| `alvdansen/BandW-Manga` | CreativeML OpenRAIL-M | El autor la publica «solo para investigación; para uso comercial, contactar» |
| `Shoaibism/sdxl-product-photography-lora` | Apache-2.0 | Entrenada con 20 imágenes de zapatillas, palabra `PRDCT`: solo sirve para ese objeto |
| `op74185/watercolor-illustration` | OpenRAIL++ | Necesita los embeddings de inversión textual `<s0><s1>` (`instance_prompt`), que ComfyUI no aplica con un `LoraLoader` |
| `Muapi/*`, `John6666/*` | OpenRAIL++/`other` | Espejos de modelos de Civitai: origen y licencia originales no comprobables |
| `artificialguybr/StudioGhibliRedmond` y las que nombran marcas | CreativeML OpenRAIL-M | Se evita nombrar propiedad intelectual de terceros en el catálogo |

## Cobertura

| Categoría pedida | Resultado |
|---|---|
| Fotorrealismo | `photorealism` (sutil) |
| Ilustración | `papercut`, `flat-illustration`, `lineart`, `pencil-art`, `crayon` |
| Anime | `anime-pop` |
| Pixel art | `pixel-art` |
| Acuarela | **Sin candidata válida** (ver el descarte de `watercolor_style_lora_sdxl`) |
| Detalle | **Sin candidata válida** (los *sliders* de MIT no superan el control) |
| Otras | 3D: `3d-render`, `clay-animation` |

Para acuarela y detalle el agente debe usar el prompt (`style: "none"` o describir el medio); no se rellenan con una LoRA dudosa.

## Lo aprendido para futuras selecciones

- Una LoRA de diffusers/PEFT puede no cargarse en ComfyUI sin avisar: **medir siempre contra el mismo texto sin LoRA** y descartar las de diferencia 0.
- SDXL ya hace muchos estilos solo con el texto; una LoRA solo aporta si supera al control.
- Los *sliders* de `ntc-ai` están pensados para pesos de hasta ±3; con el tope de 2 de ImageHearth no sirven.
