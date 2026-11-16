"""Phase 13: style LoRAs for SDXL 1.0 (catalog, requests, workflow, metadata, discovery)."""

import copy
import dataclasses
import json
import tomllib
from importlib import resources

import pytest
from PIL import Image

from imagehearth_mcp.engine import catalog as engine_catalog
from imagehearth_mcp.engine import config, gpu, workflow_runner
from imagehearth_mcp.engine import loras as engine_loras
from imagehearth_mcp.engine.image_router import plan_request
from imagehearth_mcp.provisioner import ProvisionError, manifest
from imagehearth_mcp.server import list_workflows
from tests.test_catalog import install, models_dir, tiny  # noqa: F401
from tests.test_quality_model import png_with_comfy_text


def raw():
    source = resources.files("imagehearth_mcp") / "data" / "models.toml"

    with source.open("rb") as file:
        return tomllib.load(file)


def put(tiny, *names):
    """Make those catalog LoRAs present (their files have the size the catalog says)."""
    for name in names:
        lora = tiny.loras[name]
        path = models_dir() / lora.dest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * lora.bytes)


@pytest.fixture
def sdxl(tiny, monkeypatch):
    """SDXL 1.0 installed as the quality model, no LoRAs yet."""
    install(models_dir(), tiny, "quality", "sdxl")
    monkeypatch.setattr(gpu, "total_mib", lambda: 24564)
    return tiny


# Catalog


def test_the_catalog_has_between_6_and_10_commercial_sdxl_loras():
    catalog = manifest.load()
    assert 6 <= len(catalog.loras) <= 10

    for lora in catalog.loras.values():
        assert lora.base == "sdxl" and lora.dest.startswith("loras/")
        assert catalog.licenses[lora.license].commercial
        assert 0 <= lora.weight <= 2 and lora.description and lora.category
        assert len(lora.sha256) == 64 and len(lora.revision) == 40

    assert len({lora.dest for lora in catalog.loras.values()}) == len(catalog.loras)


def test_the_catalog_covers_the_main_styles():
    categories = {lora.category for lora in manifest.load().loras.values()}
    assert {"anime", "pixel-art", "illustration", "photo"} <= categories


def mutate(change):
    values = raw()
    change(values["loras"])
    return values


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda loras: loras.append(copy.deepcopy(loras[0])), "duplicated LoRA"),
        (lambda loras: loras[0].update(dest="checkpoints/x.safetensors"), "under loras/"),
        (lambda loras: loras[0].update(dest="loras/../x.safetensors"), "under loras/"),
        (lambda loras: loras[0].update(dest="/loras/x.safetensors"), "under loras/"),
        (lambda loras: loras[0].update(weight=2.5), "weight"),
        (lambda loras: loras[0].update(weight=-0.1), "weight"),
        (lambda loras: loras[0].update(base="flux"), "base must be sdxl"),
        (lambda loras: loras[0].update(name="Pixel Art"), "lowercase words"),
        (lambda loras: loras[0].pop("category"), "category"),
        (lambda loras: loras[0].pop("trigger_words"), "trigger_words"),
        (lambda loras: loras[0].update(trigger_words="anime-pop"), "trigger_words"),
        (lambda loras: loras[0].update(sha256="abc"), "sha256"),
        (lambda loras: loras[0].update(revision="main"), "revision"),
        (lambda loras: loras[0].update(license="nope"), "unknown license"),
        (lambda loras: loras[0].update(license="flux-dev-non-commercial"), "commercial"),
        (lambda loras: loras[0].update(dest="loras/sd_xl_offset_example-lora_1.0.safetensors"), "already used"),
    ],
)
def test_invalid_catalogs_are_rejected(change, message):
    with pytest.raises(ProvisionError, match=message):
        manifest.parse(mutate(change))


def test_a_catalog_without_loras_is_valid():
    values = raw()
    del values["loras"]
    assert manifest.parse(values).loras == {}


# Installed LoRAs


def test_no_loras_installed(sdxl):
    assert engine_loras.installed() == {}
    assert engine_loras.describe_installed() == []


def test_installed_loras_follow_the_files(sdxl):
    put(sdxl, "anime-pop", "pixel-art")
    assert set(engine_loras.installed()) == {"anime-pop", "pixel-art"}

    (models_dir() / sdxl.loras["anime-pop"].dest).write_bytes(b"wrong size!!!!")
    assert set(engine_loras.installed()) == {"pixel-art"}


# The request


def test_normalize_names_and_objects():
    assert engine_loras.normalize(None) == []
    assert engine_loras.normalize("anime-pop") == [("anime-pop", None)]
    assert engine_loras.normalize(["anime-pop", {"name": "pixel-art", "weight": 0.5}]) == [
        ("anime-pop", None),
        ("pixel-art", 0.5),
    ]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (["a", "b", "c", "d"], "At most 3"),
        (["a", "a"], "repeated"),
        ([{"name": "a", "weight": 2.5}], "from 0 to 2"),
        ([{"name": "a", "weight": -1}], "from 0 to 2"),
        ([{"name": "a", "weight": "high"}], "from 0 to 2"),
        ([{"name": "a", "weight": True}], "from 0 to 2"),
        ([{"weight": 1}], "needs a name"),
        ([{"name": "a", "strength": 1}], "unknown field"),
        ([3], "must be a name"),
        (5, "must be a list"),
    ],
)
def test_normalize_rejects(value, message):
    with pytest.raises(ValueError, match=message):
        engine_loras.normalize(value)


def test_plan_without_loras_is_unchanged(sdxl):
    request = plan_request("a fox", quality="high")
    assert request.loras == () and request.workflow == "sdxl_base"


def test_plan_resolves_names_with_the_recommended_weight(sdxl):
    put(sdxl, "pixel-art", "anime-pop")
    request = plan_request("a fox", quality="high", loras=["pixel-art"])
    assert [(item.name, item.weight) for item in request.loras] == [
        ("pixel-art", sdxl.loras["pixel-art"].weight)
    ]


def test_plan_accepts_objects_with_a_weight(sdxl):
    put(sdxl, "pixel-art", "anime-pop")
    request = plan_request(
        "a fox", quality="high", loras=["anime-pop", {"name": "pixel-art", "weight": 0.6}]
    )
    assert [(item.name, item.weight) for item in request.loras] == [
        ("anime-pop", sdxl.loras["anime-pop"].weight),
        ("pixel-art", 0.6),
    ]


def test_not_installed_lora_says_how_to_install_it(sdxl):
    put(sdxl, "anime-pop")

    with pytest.raises(ValueError) as caught:
        plan_request("a fox", quality="high", loras=["pixel-art"])

    message = str(caught.value)
    assert "not installed" in message and "Installed LoRAs: anime-pop" in message
    assert "imagehearth-mcp setup --loras anime-pop,pixel-art" in message


def test_unknown_lora_lists_the_installed_ones(sdxl):
    put(sdxl, "anime-pop")

    with pytest.raises(ValueError, match=r"Unknown LoRA 'ghibli'.*Installed LoRAs: anime-pop"):
        plan_request("a fox", quality="high", loras=["ghibli"])


def test_unknown_lora_with_none_installed(sdxl):
    with pytest.raises(ValueError, match="Installed LoRAs: none"):
        plan_request("a fox", quality="high", loras=["ghibli"])


@pytest.mark.parametrize(
    ("loras", "message"),
    [
        (["a", "b", "c", "d"], "At most 3"),
        (["anime-pop", "anime-pop"], "repeated"),
        ([{"name": "anime-pop", "weight": 3}], "from 0 to 2"),
    ],
)
def test_plan_rejects_bad_requests(sdxl, loras, message):
    put(sdxl, "anime-pop")

    with pytest.raises(ValueError, match=message):
        plan_request("a fox", quality="high", loras=loras)


def test_loras_need_high_quality(sdxl):
    put(sdxl, "anime-pop")

    with pytest.raises(ValueError, match='quality="high"'):
        plan_request("a fox", quality="fast", loras=["anime-pop"])


def test_loras_are_not_for_editing(sdxl, tmp_path):
    put(sdxl, "anime-pop")
    reference = tmp_path / "ref.png"
    Image.new("RGB", (8, 8)).save(reference)

    with pytest.raises(ValueError, match="not when editing"):
        plan_request("a fox", quality="high", image_paths=[str(reference)], loras=["anime-pop"])


@pytest.mark.parametrize("model", ["flux-schnell", "flux-dev"])
def test_loras_are_refused_with_flux(tiny, monkeypatch, model):
    install(models_dir(), tiny, "quality", model)
    put(tiny, "anime-pop")
    monkeypatch.setattr(gpu, "total_mib", lambda: 24564)
    title = {"flux-schnell": "FLUX Schnell", "flux-dev": "FLUX Dev"}[model]

    with pytest.raises(ValueError, match=f"SDXL 1.0 quality model.*{title}"):
        plan_request("a fox", quality="high", loras=["anime-pop"])


def test_loras_are_refused_with_realvisxl(sdxl):
    put(sdxl, "anime-pop")

    for name in ("realvisxl", "sdxl_offset_lora"):
        path = models_dir() / sdxl.models[name].dest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())

    with pytest.raises(ValueError, match="RealVisXL"):
        plan_request("a fox", quality="high", workflow="sdxl_quality", loras=["anime-pop"])


def test_loras_are_refused_with_another_workflow(sdxl):
    put(sdxl, "anime-pop")

    with pytest.raises(ValueError, match=r"only work with the SDXL 1\.0"):
        plan_request("a fox", quality="high", workflow="sdxl_turbo", loras=["anime-pop"])


# The workflow


def template():
    path = config.WORKFLOWS_DIR / "sdxl_base.json"
    return json.loads(path.read_text(encoding="utf-8"))


def selected(sdxl, *pairs):
    return [engine_loras.Selected(sdxl.loras[name], weight) for name, weight in pairs]


def test_no_loras_leaves_the_workflow_identical():
    assert workflow_runner.apply_loras(template(), []) == template()


def test_one_lora_is_chained_after_the_detail_lora(sdxl):
    workflow = workflow_runner.apply_loras(template(), selected(sdxl, ("anime-pop", 1.5)))
    node = workflow["100"]
    assert node["class_type"] == "LoraLoader"
    assert node["inputs"] == {
        "lora_name": sdxl.loras["anime-pop"].lora_name,
        "strength_model": 1.5,
        "strength_clip": 1.5,
        "model": ["2", 0],
        "clip": ["2", 1],
    }
    assert workflow["3"]["inputs"]["clip"] == ["100", 1]
    assert workflow["4"]["inputs"]["clip"] == ["100", 1]
    assert workflow["6"]["inputs"]["model"] == ["100", 0]
    # The fixed detail LoRA keeps reading the checkpoint.
    assert workflow["2"]["inputs"]["model"] == ["1", 0]


def test_three_loras_form_a_chain(sdxl):
    workflow = workflow_runner.apply_loras(
        template(), selected(sdxl, ("anime-pop", 1), ("pixel-art", 0.5), ("crayon", 2))
    )
    assert workflow["100"]["inputs"]["model"] == ["2", 0]
    assert workflow["101"]["inputs"]["model"] == ["100", 0]
    assert workflow["101"]["inputs"]["clip"] == ["100", 1]
    assert workflow["102"]["inputs"]["model"] == ["101", 0]
    assert workflow["102"]["inputs"]["strength_clip"] == 2
    assert workflow["3"]["inputs"]["clip"] == ["102", 1]
    assert workflow["6"]["inputs"]["model"] == ["102", 0]


def test_a_workflow_without_the_detail_lora_cannot_take_loras(sdxl):
    turbo = json.loads((config.WORKFLOWS_DIR / "sdxl_turbo.json").read_text(encoding="utf-8"))

    with pytest.raises(ValueError, match="can't take LoRAs"):
        workflow_runner.apply_loras(turbo, selected(sdxl, ("anime-pop", 1)))


# Activation words and style


def test_trigger_words_are_added_when_missing(sdxl):
    chosen = selected(sdxl, ("pixel-art", 1))
    assert engine_loras.with_trigger_words("a fox", chosen) == "pixel art, a fox"


def test_trigger_words_present_are_not_repeated(sdxl):
    chosen = selected(sdxl, ("pixel-art", 1))
    assert engine_loras.with_trigger_words("a PIXEL ART fox", chosen) == "a PIXEL ART fox"


def test_a_lora_without_trigger_words_adds_nothing(sdxl):
    chosen = selected(sdxl, ("crayon", 1))
    assert engine_loras.with_trigger_words("a fox", chosen) == "a fox"


def test_two_loras_add_each_their_words_once(sdxl):
    chosen = selected(sdxl, ("anime-pop", 1), ("photorealism", 1))
    prompt = engine_loras.with_trigger_words("a fox", chosen)
    assert prompt.startswith("daiton style, PhotoRealism") and prompt.endswith("a fox")


def prepared(sdxl, prompt, *pairs, style="auto"):
    return workflow_runner.prepare_generation(
        "sdxl_base.json", prompt, "", 1024, 1024, style, selected(sdxl, *pairs)
    )


def text_of(item):
    return next(
        node["inputs"]["text"]
        for node in item.workflow.values()
        if node["class_type"] == "CLIPTextEncode" and node["inputs"]["text"]
    )


def test_auto_style_adds_no_photo_cues_with_a_lora_of_another_medium(sdxl):
    text = text_of(prepared(sdxl, "a quiet harbor", ("pixel-art", 1)))
    assert text == "pixel art, a quiet harbor"
    assert "photograph" not in text


def test_auto_style_keeps_photo_cues_with_a_photo_lora(sdxl):
    text = text_of(prepared(sdxl, "a quiet harbor", ("photorealism", 1)))
    assert text.startswith("PhotoRealism, a quiet harbor") and "RAW photo" in text


def test_photo_style_still_adds_cues_with_any_lora(sdxl):
    text = text_of(prepared(sdxl, "a quiet harbor", ("pixel-art", 1), style="photo"))
    assert "RAW photo" in text and text.startswith("pixel art")


def test_without_loras_the_prompt_is_unchanged(sdxl):
    assert "pixel" not in text_of(prepared(sdxl, "a quiet harbor"))


def test_prepared_workflow_carries_the_chain(sdxl):
    item = prepared(sdxl, "a fox", ("anime-pop", 1), ("pixel-art", 0.5))
    assert [loader.name for loader in item.loras] == ["anime-pop", "pixel-art"]
    assert item.workflow["101"]["inputs"]["lora_name"] == sdxl.loras["pixel-art"].lora_name


# PNG metadata


def test_png_lists_the_loras_with_their_weights(tmp_path, sdxl):
    path = tmp_path / "image.png"
    path.write_bytes(png_with_comfy_text())
    workflow_runner.stamp_png(
        path, "sdxl_base", selected(sdxl, ("anime-pop", 1.5), ("pixel-art", 0.6))
    )

    with Image.open(path) as image:
        image.load()
        assert image.text["ImageHearth-LoRAs"] == "anime-pop:1.5,pixel-art:0.6"
        assert image.text["ImageHearth-Quality-Model"] == "sdxl"


def test_png_without_loras_has_no_lora_text(tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(png_with_comfy_text())
    workflow_runner.stamp_png(path, "sdxl_base")

    with Image.open(path) as image:
        image.load()
        assert "ImageHearth-LoRAs" not in image.text


# Discovery


def items():
    return {item["model"]: item for item in list_workflows()}


def test_list_workflows_shows_the_installed_loras(sdxl):
    put(sdxl, "anime-pop")
    active = items()["sdxl"]
    assert active["default"]
    assert active["loras"] == [
        {
            "name": "anime-pop",
            "description": sdxl.loras["anime-pop"].description,
            "category": "anime",
            "trigger_words": ["daiton style"],
            "weight": sdxl.loras["anime-pop"].weight,
        }
    ]


def test_list_workflows_with_no_loras_has_an_empty_list(sdxl):
    assert items()["sdxl"]["loras"] == []


def test_list_workflows_with_flux_has_no_loras_field(tiny, monkeypatch):
    install(models_dir(), tiny, "quality", "flux-schnell")
    put(tiny, "anime-pop")
    monkeypatch.setattr(gpu, "total_mib", lambda: 24564)
    assert all("loras" not in item for item in list_workflows())


def test_only_the_sdxl_item_has_loras(sdxl):
    assert "loras" not in items()["sdxl-turbo"]


def test_engine_catalog_still_installed(sdxl):
    assert engine_catalog.entries()["sdxl_base"].installed


def test_dataclass_is_frozen(sdxl):
    with pytest.raises(dataclasses.FrozenInstanceError):
        sdxl.loras["anime-pop"].weight = 1
