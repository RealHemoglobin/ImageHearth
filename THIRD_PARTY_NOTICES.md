# Third-party notices

Last reviewed: 2026-11-06. This is a summary, **not legal advice**: the linked licenses are what applies. No external legal review has been done.

**ImageHearth does not redistribute model weights.** You download them from their publishers and accept their terms yourself.

## Models

| Component | License | Commercial use | Reviewed |
|---|---|---|---|
| FLUX.1 Dev | [FLUX [dev] Non-Commercial License v2.0](https://bfl.ai/legal/non-commercial-license-terms) | **No** for the model, without a separate license from Black Forest Labs. See the note on outputs | 2026-10-31 |
| FLUX.1 Dev and Kontext Dev in GGUF, `mac-*` profiles only | Same as the models they derive from, as declared by `city96/FLUX.1-dev-gguf` and `QuantStack/FLUX.1-Kontext-dev-GGUF` | Same as FLUX.1 Dev | 2026-10-31 |
| T5-XXL in GGUF, `mac-*` profiles only | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0), as declared by `city96/t5-v1_1-xxl-encoder-gguf` | Yes | 2026-10-31 |
| FLUX.1 Kontext Dev | [FLUX [dev] Non-Commercial License v2.0](https://bfl.ai/legal/non-commercial-license-terms), which names this model | Same as FLUX.1 Dev | 2026-10-31 |
| T5-XXL, CLIP-L and the FLUX VAE | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0), as declared by `comfyanonymous/flux_text_encoders` and `Comfy-Org/Lumina-Image-2` | Yes | 2026-10-31 |
| FLUX.1 Schnell (fp8, `flux-schnell` quality model) | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0), as released by Black Forest Labs and declared by the repackaged `Kijai/flux-fp8` | Yes | 2026-11-06 |
| SDXL 1.0 base (`sdxl` quality model) | [CreativeML Open RAIL++-M](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md), as declared by `stabilityai/stable-diffusion-xl-base-1.0` | **Yes**, with use restrictions that must be passed on | 2026-11-06 |
| RealVisXL V5.0 (fine-tuned SDXL, no longer offered; only for installations made before SDXL 1.0 was added) | [CreativeML Open RAIL++-M](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md), as declared by `SG161222/RealVisXL_V5.0` | **Yes**, with use restrictions that must be passed on | 2026-11-04 |
| SDXL offset LoRA (`sd_xl_offset_example-lora_1.0`, from the SDXL 1.0 base repository) | [CreativeML Open RAIL++-M](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md), as declared by `stabilityai/stable-diffusion-xl-base-1.0` | **Yes**, with the same restrictions | 2026-11-04 |
| SDXL Turbo | [Stability AI Community License](https://huggingface.co/stabilityai/sdxl-turbo/blob/main/LICENSE.md) (updated 2024-07-05) | **Yes, with limits:** requires registering with Stability AI, and an enterprise license above USD 1M in annual revenue | 2026-10-31 |

Notes:

- **FLUX outputs.** The license disclaims ownership of outputs and mentions commercial use of them, but it also restricts commercial or production use of data produced by the model, and the text does not reconcile the two. Treat commercial use of FLUX images as unresolved and check with Black Forest Labs. Outputs also can't be used to train competing models, and the license sets conditions on content filtering and AI-generation disclosure.
- **FLUX repackaged weights.** `imagehearth-mcp setup` downloads the fp8 files from `comfyanonymous/flux_dev_scaled_fp8_test` and `Comfy-Org/Flux-1-Kontext-Dev`, which are repackaged versions under the same license. The original Hugging Face repositories require logging in to read their copy of the license, so the link above points to the publisher's page.
- **Quality models and licenses.** The licenses `setup` asks you to accept are only those of what it downloads: with `flux-schnell` or `sdxl` in the `quality` profile no FLUX [dev] file is downloaded. The `full` profile adds FLUX.1 Kontext Dev for editing, which stays non-commercial whatever the quality model is.
- **FLUX.1 Schnell weights.** `imagehearth-mcp setup` downloads the fp8 diffusion model from `Kijai/flux-fp8`, a public repackaging of the Apache-2.0 release, so no Hugging Face token is needed.
- **SDXL Turbo metadata.** The Hugging Face metadata still says `sai-nc-community`, while the linked `LICENSE.md` is the Community License and allows limited commercial use. This summary follows `LICENSE.md`, the text the metadata itself links to.

## Software

| Component | License | How it's used | Commercial use | Reviewed |
|---|---|---|---|---|
| [ComfyUI](https://github.com/Comfy-Org/ComfyUI) | [GPL-3.0](https://github.com/Comfy-Org/ComfyUI/blob/master/LICENSE) | Separate program, reached over local HTTP. Not distributed here | Yes | 2026-10-31 |
| [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) | [Apache-2.0](https://github.com/city96/ComfyUI-GGUF/blob/main/LICENSE) | ComfyUI node downloaded by setup for the `mac-*` profiles, with its `gguf`, `sentencepiece` and `protobuf` dependencies. Not distributed here | Yes | 2026-10-31 |
| [huggingface_hub](https://github.com/huggingface/huggingface_hub) | [Apache-2.0](https://github.com/huggingface/huggingface_hub/blob/main/LICENSE) | Direct dependency | Yes | 2026-10-31 |
| [mcp](https://github.com/modelcontextprotocol/python-sdk) | [MIT](https://github.com/modelcontextprotocol/python-sdk/blob/main/LICENSE) | Direct dependency | Yes | 2026-10-31 |
| [Pillow](https://github.com/python-pillow/Pillow) | [MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE) | Direct dependency | Yes | 2026-10-31 |
| [PyYAML](https://github.com/yaml/pyyaml) | [MIT](https://github.com/yaml/pyyaml/blob/main/LICENSE) | Direct dependency | Yes | 2026-10-31 |
| [Requests](https://github.com/psf/requests) | [Apache-2.0](https://github.com/psf/requests/blob/main/LICENSE) | Direct dependency | Yes | 2026-10-31 |

## This project

- Everything is under the [MIT license](LICENSE), except as stated below.
- [`src/imagehearth_mcp/data/imagehearth_status/`](src/imagehearth_mcp/data/imagehearth_status/LICENSE) is under GPL-3.0 because it imports ComfyUI code.
