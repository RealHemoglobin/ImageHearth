"""Fase 15: el parámetro `model`, los workflows de los modelos nuevos y su descubrimiento."""

import json
import re
from pathlib import Path
from unittest import mock

import pytest
from PIL import Image

from imagehearth_mcp.engine import batch, catalog, config, loras, workflow_runner
from imagehearth_mcp.engine.image_router import create_image, plan_request
from imagehearth_mcp.provisioner import manifest, models
from imagehearth_mcp.server import list_workflows
from tests.harness import EngineTestCase

CATALOG = manifest.load()


def installed_as(option_model, capability, precision):
    """The InstalledModel a catalog option would be, with its loader files."""
    entry = CATALOG.catalog[option_model]
    option = entry.option(precision)
    license = CATALOG.licenses[entry.license]
    return catalog.InstalledModel(
        entry.name,
        entry.title,
        capability,
        option.precision,
        option.workflow(capability),
        True,
        license.name,
        license.commercial,
        loaders={role: Path(CATALOG.models[w].dest).name for role, w in option.loaders.items()},
        max_references=entry.max_references,
    )


NEW_GENERATION = [
    (entry.name, capability, option.precision)
    for entry in CATALOG.catalog.values()
    for capability in entry.capabilities
    if capability in ("fast", "high")
    for option in entry.options
    if entry.name not in catalog.LEGACY_MODELS
]
NEW_EDITING = [
    (entry.name, "edit", option.precision)
    for entry in CATALOG.catalog.values()
    if "edit" in entry.capabilities and entry.name not in catalog.LEGACY_MODELS
    for option in entry.options
]


def references_exist(workflow):
    for node_id, node in workflow.items():
        for value in node["inputs"].values():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                assert value[0] in workflow, (node_id, value)


def no_markers_left(workflow):
    assert not re.search(r"%[A-Z0-9]+%", json.dumps(workflow))


# Plantillas con marcadores


@pytest.mark.parametrize(("model", "capability", "precision"), NEW_GENERATION)
def test_generation_workflow_is_complete(model, capability, precision, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "COMFY_SUBFOLDER", "tests")
    item = installed_as(model, capability, precision)
    workflow = json.loads((config.WORKFLOWS_DIR / f"{item.workflow}.json").read_text("utf-8"))
    filled = workflow_runner.prepare_workflow(
        workflow, "a red fox", "blur", 1000, 700, "tests/abc", item
    )

    no_markers_left(filled)
    references_exist(filled)
    texts = [n["inputs"]["text"] for n in filled.values() if n["class_type"] == "CLIPTextEncode"]
    assert "a red fox" in texts
    files = {
        value
        for node in filled.values()
        for key, value in node["inputs"].items()
        if key in ("unet_name", "vae_name") or key.startswith("clip_name")
    }
    assert set(item.loaders.values()) == files
    save = next(n for n in filled.values() if n["class_type"] == "SaveImage")
    assert save["inputs"]["filename_prefix"] == "tests/abc"
    sizes = [
        (n["inputs"]["width"], n["inputs"]["height"])
        for n in filled.values()
        if "width" in n["inputs"] and "batch_size" in n["inputs"]
    ]
    assert sizes == [(992, 704)]
    seeds = [
        n["inputs"].get("seed", n["inputs"].get("noise_seed"))
        for n in filled.values()
        if "seed" in n["inputs"] or "noise_seed" in n["inputs"]
    ]
    assert len(seeds) == 1 and isinstance(seeds[0], int)


@pytest.mark.parametrize(("model", "capability", "precision"), NEW_EDITING)
def test_editing_workflow_is_complete(model, capability, precision):
    from imagehearth_mcp.engine import kontext

    item = installed_as(model, capability, precision)
    filled = kontext.build_marker_workflow(
        ["run/reference_1.png"], "make it night", "tests/abc", item, item.workflow
    )
    no_markers_left(filled)
    references_exist(filled)
    load = next(n for n in filled.values() if n["class_type"] == "LoadImage")
    assert load["inputs"]["image"] == "run/reference_1.png"
    prompts = [
        n["inputs"].get("text", n["inputs"].get("prompt"))
        for n in filled.values()
        if n["class_type"] in ("CLIPTextEncode", "TextEncodeQwenImageEditPlus")
    ]
    assert "make it night" in prompts
    files = {
        value
        for node in filled.values()
        for key, value in node["inputs"].items()
        if key in ("unet_name", "vae_name") or key.startswith("clip_name")
    }
    assert set(item.loaders.values()) == files
    assert next(n for n in filled.values() if n["class_type"] == "SaveImage")["inputs"][
        "filename_prefix"
    ] == "tests/abc"

    with pytest.raises(ValueError, match="one image at a time"):
        kontext.build_marker_workflow(["a", "b"], "x", "p", item, item.workflow)


def test_negative_prompt_reaches_the_models_that_use_it():
    for model, capability, precision in (
        ("chroma-hd", "high", "fp8"),
        ("qwen-image", "high", "fp8"),
        ("hidream-full", "high", "fp8"),
    ):
        item = installed_as(model, capability, precision)
        workflow = json.loads((config.WORKFLOWS_DIR / f"{item.workflow}.json").read_text("utf-8"))
        assert workflow_runner.negative_prompt_applies(workflow), model
        filled = workflow_runner.prepare_workflow(workflow, "fox", "no blur", 512, 512, "p", item)
        texts = [n["inputs"]["text"] for n in filled.values() if n["class_type"] == "CLIPTextEncode"]
        assert sorted(texts) == ["fox", "no blur"], model

    for model, capability, precision in (("klein-4b", "fast", "bf16"), ("z-image-turbo", "fast", "int8")):
        item = installed_as(model, capability, precision)
        workflow = json.loads((config.WORKFLOWS_DIR / f"{item.workflow}.json").read_text("utf-8"))
        assert not workflow_runner.negative_prompt_applies(workflow), model


def test_a_template_with_an_unknown_marker_is_refused():
    with pytest.raises(ValueError, match="%MYSTERY%"):
        workflow_runner.fill_markers({"1": {"inputs": {"a": "%MYSTERY%"}}}, {})


def test_loader_files_are_the_names_of_the_installed_weights():
    item = installed_as("hidream-full", "high", "q4_k_m")
    assert item.loaders == {
        "unet": "hidream-i1-full-Q4_K_M.gguf",
        "clip1": "clip_l_hidream.safetensors",
        "clip2": "clip_g_hidream.safetensors",
        "clip3": "t5xxl_fp8_e4m3fn_scaled.safetensors",
        "clip4": "llama_3.1_8b_instruct_fp8_scaled.safetensors",
        "vae": "ae.safetensors",
    }
    assert workflow_runner.loader_values(item)["CLIP4"] == item.loaders["clip4"]


# Elección con `model`


class ChoiceCase(EngineTestCase):
    def make_reference(self, name="foto.png"):
        path = self.tmp / name
        Image.new("RGB", (64, 64), "blue").save(path)
        return str(path)

    def missing(self, *weights):
        """Everything is installed except these weights."""
        self.models_present.side_effect = lambda items, folder, extra=None: [
            models.ModelState(
                item,
                Path(folder) / item.dest,
                models.MISSING if item.name in weights else models.PRESENT,
            )
            for item in items
        ]

    def assert_untouched(self):
        self.assertEqual(self.comfy.workflows, [])
        self.assertEqual(self.comfy.events, [])
        self.assertEqual(self.ollama.events, [])

    def last(self):
        return self.comfy.workflows[-1]

    def classes(self, workflow):
        return {node["class_type"] for node in workflow.values()}


class Generating(ChoiceCase):
    def test_without_model_the_default_is_what_it_was(self):
        create_image("a cat")
        self.assertIn("CheckpointLoaderSimple", self.classes(self.last()))
        create_image("a cat", quality="high")
        self.assertEqual(
            next(n for n in self.last().values() if n["class_type"] == "UNETLoader")["inputs"][
                "unet_name"
            ],
            "flux_dev_fp8_scaled_diffusion_model.safetensors",
        )

    def test_model_chooses_among_the_installed_ones(self):
        path = create_image("a cat", model="klein-4b")
        loaders = {n["class_type"]: n["inputs"] for n in self.last().values()}
        self.assertEqual(loaders["UNETLoader"]["unet_name"], "flux-2-klein-4b.safetensors")
        self.assertEqual(loaders["CLIPLoader"]["clip_name"], "qwen_3_4b.safetensors")
        self.assertEqual(loaders["VAELoader"]["vae_name"], "flux2-vae.safetensors")
        self.assertEqual(loaders["CLIPTextEncode"]["text"], "a cat")
        self.assertTrue(Path(path.splitlines()[0]).is_file())

    def test_high_quality_model(self):
        create_image("a cat", quality="high", model="chroma-hd")
        self.assertIn("T5TokenizerOptions", self.classes(self.last()))

    def test_the_image_says_which_model_made_it(self):
        path = create_image("a cat", model="z-image-turbo").splitlines()[0]
        self.assertEqual(Image.open(path).text["ImageHearth-Model"].split(":")[0], "z-image-turbo")
        self.assertEqual(Image.open(path).text["ImageHearth-Workflow"], "z_image_turbo")
        path = create_image("a cat", quality="high", model="sdxl").splitlines()[0]
        text = Image.open(path).text
        self.assertEqual(text["ImageHearth-Model"], "sdxl:fp16")
        self.assertEqual(text["ImageHearth-Quality-Model"], "sdxl")

    def test_unknown_model_names_the_installed_ones(self):
        with self.assertRaisesRegex(ValueError, "Unknown model 'nope'.*Installed fast models"):
            create_image("a cat", model="nope")

        self.assert_untouched()

    def test_a_model_without_the_capability_is_refused(self):
        with self.assertRaisesRegex(ValueError, "FLUX.1 Kontext Dev.*editing model.*fast model"):
            create_image("a cat", model="kontext")

        with self.assertRaisesRegex(ValueError, "Z-Image-Turbo.*fast model.*high-quality"):
            create_image("a cat", quality="high", model="z-image-turbo")

        self.assert_untouched()

    def test_a_model_that_is_not_installed_says_how_to_install_it(self):
        self.missing("chroma_hd_fp8", "chroma_hd_bf16")

        with self.assertRaisesRegex(
            ValueError,
            r"Chroma1-HD \(chroma-hd\) is not installed.*--quality-models chroma-hd",
        ):
            create_image("a cat", quality="high", model="chroma-hd")

        self.assert_untouched()

    def test_model_and_workflow_cannot_be_combined(self):
        with self.assertRaisesRegex(ValueError, "model and workflow can't be combined"):
            create_image("a cat", model="klein-4b", workflow="sdxl_turbo")

        self.assert_untouched()

    def test_loras_need_sdxl(self):
        with self.assertRaisesRegex(ValueError, "LoRAs only work with the SDXL 1.0.*Chroma1-HD"):
            plan_request("a cat", quality="high", model="chroma-hd", loras=["pixel-art"])

        with self.assertRaisesRegex(ValueError, "SDXL 1.0 quality model.*FLUX Dev"):
            plan_request("a cat", quality="high", model="flux-dev", loras=["pixel-art"])

    def test_the_default_of_a_capability_comes_from_the_record(self):
        from imagehearth_mcp.provisioner.install_manifest import InstallManifest

        records = InstallManifest(config.INSTALL_MANIFEST)
        records.mode, records.comfy_dir, records.profile = "managed", str(self.comfy_dir), "full"
        records.models = {
            "fast": [
                {"model": "sdxl-turbo", "precision": "fp16"},
                {"model": "klein-4b", "precision": "bf16"},
            ],
            "high": [{"model": "qwen-image", "precision": "fp8"}],
            "edit": [{"model": "kontext", "precision": "fp8"}],
        }
        records.defaults = {"fast": "klein-4b", "high": "qwen-image", "edit": "kontext"}
        records.save()
        create_image("a cat")
        self.assertIn("EmptyFlux2LatentImage", self.classes(self.last()))
        create_image("a cat", model="sdxl-turbo")
        self.assertIn("CheckpointLoaderSimple", self.classes(self.last()))
        create_image("a cat", quality="high")
        self.assertIn("ModelSamplingAuraFlow", self.classes(self.last()))
        self.assertEqual(
            next(n for n in self.last().values() if n["class_type"] == "UNETLoader")["inputs"][
                "unet_name"
            ],
            "qwen_image_fp8_e4m3fn.safetensors",
        )

    def test_the_recorded_precision_wins_over_the_gpu(self):
        from imagehearth_mcp.provisioner.install_manifest import InstallManifest

        records = InstallManifest(config.INSTALL_MANIFEST)
        records.mode, records.comfy_dir, records.profile = "managed", str(self.comfy_dir), "quality"
        records.models = {
            "fast": [{"model": "sdxl-turbo", "precision": "fp16"}],
            "high": [{"model": "qwen-image", "precision": "q4_k_m"}],
        }
        records.save()
        create_image("a cat", quality="high", model="qwen-image")
        self.assertIn("UnetLoaderGGUF", self.classes(self.last()))


class Editing(ChoiceCase):
    def test_default_editing_is_kontext(self):
        create_image("make it night", image_paths=[self.make_reference()])
        self.assertIn("FluxGuidance", self.classes(self.last()))

    def test_klein_edits_with_its_template(self):
        path = create_image(
            "make it night", image_paths=[self.make_reference()], model="klein-4b"
        )
        workflow = self.last()
        no_markers_left(workflow)
        references_exist(workflow)
        load = next(n for n in workflow.values() if n["class_type"] == "LoadImage")
        self.assertRegex(load["inputs"]["image"], r"reference_1\.png$")
        prompt = next(n for n in workflow.values() if n["class_type"] == "CLIPTextEncode")
        self.assertEqual(prompt["inputs"]["text"], "make it night")
        text = Image.open(path.splitlines()[0]).text
        self.assertEqual(text["ImageHearth-Model"], "klein-4b:bf16")
        self.assertEqual(text["ImageHearth-Workflow"], "klein_4b_edit")

    def test_qwen_edit_uses_its_gguf_when_that_is_the_installed_precision(self):
        self.missing("qwen_edit_2511_fp8")
        create_image(
            "make it night", image_paths=[self.make_reference()], model="qwen-image-edit"
        )
        self.assertIn("UnetLoaderGGUF", self.classes(self.last()))
        self.assertIn("TextEncodeQwenImageEditPlus", self.classes(self.last()))

    def test_these_models_edit_one_image(self):
        references = [self.make_reference("a.png"), self.make_reference("b.png")]

        with self.assertRaisesRegex(ValueError, "FLUX.2 Klein 4B takes at most 1 reference image"):
            create_image("make it night", image_paths=references, model="klein-4b")

        self.assert_untouched()
        create_image("make it night", image_paths=references)
        self.assertEqual(len(self.comfy.workflows), 1)

    def test_size_and_negative_prompt_are_ignored_with_a_warning(self):
        result = create_image(
            "make it night",
            image_paths=[self.make_reference()],
            model="klein-4b",
            width=512,
            height=512,
            negative_prompt="blur",
        )
        self.assertIn("WARNING: FLUX.2 Klein 4B ignores negative_prompt.", result)
        self.assertIn("keeps the size of the reference", result)

    def test_a_generation_model_cannot_edit(self):
        with self.assertRaisesRegex(ValueError, "Z-Image-Turbo.*needs a editing one"):
            create_image(
                "make it night", image_paths=[self.make_reference()], model="z-image-turbo"
            )

        self.assert_untouched()


class Batches(ChoiceCase):
    def test_common_and_own_model(self):
        result = batch.run(
            ["a", {"prompt": "b", "model": "klein-4b"}, {"prompt": "c", "model": "sdxl-turbo"}],
            model="z-image-turbo",
        )
        names = [
            next(n for n in w.values() if n["class_type"] in ("UNETLoader", "CheckpointLoaderSimple"))[
                "inputs"
            ]
            for w in self.comfy.workflows
        ]
        self.assertEqual(len(result.outcomes), 3)
        by_prompt = {
            next(n for n in w.values() if n["class_type"] == "CLIPTextEncode" and n["inputs"]["text"])[
                "inputs"
            ]["text"]: w
            for w in self.comfy.workflows
        }
        self.assertIn("EmptyFlux2LatentImage", self.classes_of(by_prompt["b"]))
        self.assertIn("CheckpointLoaderSimple", self.classes_of(by_prompt["c"]))
        self.assertIn("ModelSamplingAuraFlow", self.classes_of(by_prompt["a"]))
        self.assertEqual(len(names), 3)

    def classes_of(self, workflow):
        return {n["class_type"] for n in workflow.values()}

    def test_one_bad_model_rejects_the_whole_list_before_the_gpu(self):
        with (
            mock.patch.object(batch, "generation_session", side_effect=AssertionError("GPU")),
            self.assertRaisesRegex(ValueError, "Item 2: Unknown model 'nope'"),
        ):
            batch.run(["a", {"prompt": "b", "model": "nope"}, "c"])

        self.assert_untouched()

    def test_a_model_of_another_capability_is_item_specific(self):
        with (
            mock.patch.object(batch, "generation_session", side_effect=AssertionError("GPU")),
            self.assertRaisesRegex(ValueError, "Item 1: .*Kontext.*editing model"),
        ):
            batch.run([{"prompt": "a", "model": "kontext"}, "b"])

    def assert_untouched(self):
        self.assertEqual(self.comfy.workflows, [])
        self.assertEqual(self.ollama.events, [])


class Discovery(ChoiceCase):
    def test_one_item_per_installed_model_with_one_default_per_capability(self):
        items = list_workflows()
        self.assertEqual(
            [item["model"] for item in items if item["capability"] == "fast"],
            ["sdxl-turbo", "z-image-turbo", "klein-4b"],
        )
        self.assertEqual(
            [item["model"] for item in items if item["capability"] == "edit"],
            ["kontext", "klein-4b", "qwen-image-edit"],
        )

        for capability in ("fast", "high", "edit"):
            defaults = [i["model"] for i in items if i["capability"] == capability and i["default"]]
            self.assertEqual(len(defaults), 1, capability)

        sdxl = next(i for i in items if i["model"] == "sdxl")
        self.assertEqual(sdxl["loras"], loras.describe_installed())
        self.assertFalse(any("loras" in i for i in items if i["model"] != "sdxl"))
        klein = next(i for i in items if i["model"] == "klein-4b" and i["capability"] == "fast")
        self.assertEqual(klein["precision"], "bf16")
        self.assertEqual(klein["license"], "Apache-2.0")
        self.assertTrue(klein["commercial_use"])
        self.assertEqual(klein["seconds"], 1.3)

    def test_a_missing_weight_hides_the_model(self):
        self.missing("hidream_llama")
        items = list_workflows()
        self.assertNotIn("hidream-full", [i["model"] for i in items])

    def test_a_non_commercial_model_says_so(self):
        items = {(i["model"], i["capability"]): i for i in list_workflows()}
        self.assertFalse(items[("flux-dev", "high")]["commercial_use"])
        self.assertFalse(items[("kontext", "edit")]["commercial_use"])
        self.assertTrue(items[("hidream-full", "high")]["commercial_use"])
