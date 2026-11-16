"""Fase 15: el catálogo por capacidad, los conjuntos de modelos y la migración de registros."""

import copy
import tomllib

import pytest

from imagehearth_mcp.engine import config
from imagehearth_mcp.provisioner import ProvisionError, manifest, quality, selection
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from imagehearth_mcp.provisioner.manifest import ModelSet, Pick
from tests.test_provisioner import machine  # noqa: F401
from tests.test_quality_model import old_record, put


@pytest.fixture
def catalog():
    return manifest.load()


def values():
    with config.data_path("models.toml").open("rb") as file:
        return copy.deepcopy(tomllib.load(file))


# Catálogo


def test_the_catalog_has_the_models_of_the_decision(catalog):
    assert catalog.models_with("fast") == ["sdxl-turbo", "z-image-turbo", "klein-4b"]
    assert catalog.models_with("high") == [
        "sdxl", "flux-dev", "flux-schnell", "chroma-hd", "qwen-image", "hidream-full",
    ]
    assert catalog.models_with("edit") == ["kontext", "klein-4b", "qwen-image-edit"]
    offered = {
        name: [option.precision for option in model.options]
        for name, model in catalog.catalog.items()
    }
    assert offered["z-image-turbo"] == ["bf16", "int8"]
    assert offered["klein-4b"] == ["bf16"]
    assert offered["chroma-hd"] == ["bf16", "fp8"]
    assert offered["qwen-image"] == ["bf16", "fp8", "q4_k_m", "q2_k"]
    assert offered["hidream-full"] == ["fp8", "q4_k_m"]
    assert offered["qwen-image-edit"] == ["fp8", "q4_k_m"]
    assert offered["flux-dev"] == ["fp8", "gguf"] and offered["sdxl"] == ["fp16"]


def test_every_weight_has_a_pinned_revision_size_hash_and_license(catalog):
    for name in (
        "z_image_turbo_bf16", "z_image_turbo_int8", "klein_4b", "chroma_hd_bf16",
        "chroma_hd_fp8", "qwen_image_bf16", "qwen_image_fp8", "qwen_image_q4_k_m",
        "qwen_image_q2_k", "hidream_full_fp8", "hidream_full_q4_k_m", "qwen_edit_2511_fp8",
        "qwen_edit_2511_q4_k_m", "hidream_llama",
    ):
        weight = catalog.models[name]
        assert len(weight.revision) == 40 and len(weight.sha256) == 64 and weight.bytes > 10**8
        assert weight.license in catalog.licenses


def test_licenses_of_the_new_models(catalog):
    assert catalog.licenses["llama-3-1"].commercial and "Llama" in catalog.licenses["llama-3-1"].name
    hidream = catalog.build_set(
        catalog.profiles["quality"],
        ModelSet(
            {"fast": (Pick("sdxl-turbo", "fp16"),), "high": (Pick("hidream-full", "fp8"),)}
        ),
    )
    keys = {entry.key for entry in catalog.licenses_for(hidream)}
    assert {"llama-3-1", "mit", "apache-2", "sai-community"} <= keys


def test_non_commercial_models_are_flagged(catalog):
    info = {item["name"]: item for item in catalog.describe_catalog("high", 24564)}
    assert not info["flux-dev"]["commercial_use"]
    assert info["qwen-image"]["commercial_use"] and info["chroma-hd"]["commercial_use"]
    edits = {item["name"]: item for item in catalog.describe_catalog("edit", 24564)}
    assert not edits["kontext"]["commercial_use"] and edits["klein-4b"]["commercial_use"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda v: v["catalog"]["klein-4b"].update(capabilities=["fast", "nope"]), "capabilities"),
        (lambda v: v["catalog"]["klein-4b"].update(capabilities=[]), "capabilities"),
        (lambda v: v["catalog"]["klein-4b"].update(license="unknown"), "unknown license"),
        (lambda v: v["catalog"]["klein-4b"]["options"][0].update(models=["nope"]), "nope"),
        (
            lambda v: v["catalog"]["z-image-turbo"]["options"][1].update(precision="BF16"),
            "precision is repeated",
        ),
        (
            lambda v: v["catalog"]["klein-4b"]["options"][0].update(workflow={"fast": "klein_4b"}),
            "workflow for exactly",
        ),
        (
            lambda v: v["catalog"]["klein-4b"]["options"][0]["loaders"].update(clip="nope"),
            "unknown loader weight",
        ),
        (lambda v: v["catalog"]["klein-4b"].update(options=[]), "no options"),
        (lambda v: v["recommended"]["fast"].update({"8": "nope:bf16"}), "doesn't have it"),
        (lambda v: v["recommended"]["fast"].update({"8": "klein-4b:fp4"}), "no such precision"),
        (lambda v: v["recommended"].update(extra={"8": "klein-4b"}), "unknown capability"),
        (lambda v: v["profiles"]["fast"].update(capabilities=["nope"]), "unknown capability"),
        (
            lambda v: v["profiles"]["mac-fast"].update(fixed={"fast": ["nope:fp16"]}),
            "unknown fixed model",
        ),
        (
            lambda v: next(m for m in v["models"] if m["name"] == "klein_4b").update(license="zzz"),
            "unknown license",
        ),
    ],
)
def test_the_catalog_rejects_what_is_wrong(change, message):
    broken = values()
    change(broken)

    with pytest.raises(ProvisionError, match=message):
        manifest.parse(broken)


def test_a_workflow_that_is_not_shipped_is_refused(monkeypatch, catalog):
    broken = values()
    broken["catalog"]["klein-4b"]["options"][0]["workflow"] = {"fast": "klein_4b", "edit": "ghost"}
    parsed = manifest.parse(broken)

    with pytest.raises(ProvisionError, match="workflow ghost"):
        manifest._check_workflow_files(parsed)


# Elección de precisión y recomendaciones


@pytest.mark.parametrize(
    ("vram", "fast", "high", "edit"),
    [
        (8192, "klein-4b:bf16", "chroma-hd:fp8", "klein-4b:bf16"),
        (16384, "z-image-turbo:bf16", "qwen-image:q4_k_m", "klein-4b:bf16"),
        (24564, "z-image-turbo:bf16", "qwen-image:fp8", "qwen-image-edit:fp8"),
        (32607, "z-image-turbo:bf16", "qwen-image:fp8", "qwen-image-edit:fp8"),
    ],
)
def test_recommendation_per_level(catalog, vram, fast, high, edit):
    assert str(catalog.recommended_pick("fast", vram)) == fast
    assert str(catalog.recommended_pick("high", vram)) == high
    assert str(catalog.recommended_pick("edit", vram)) == edit


def test_every_level_has_a_recommendation_with_commercial_use(catalog):
    for vram in (8192, 16384, 24564, 32607):
        for capability in ("fast", "high", "edit"):
            pick = catalog.recommended_pick(capability, vram)
            entry = catalog.catalog[pick.model]
            assert catalog.licenses[entry.license].commercial, (vram, capability, pick)


def test_precision_is_the_best_that_does_not_move_weights_to_ram(catalog):
    qwen = catalog.catalog["qwen-image"]
    chosen = {
        vram: catalog.recommended_precision(qwen, "high", vram).precision
        for vram in (8192, 16384, 24564, 32607)
    }
    # bf16 and fp8 spill at 8 and 16 GB; Q4_K_M and Q2_K don't. fp8 fits from 24 GB.
    assert chosen == {8192: "q4_k_m", 16384: "q4_k_m", 24564: "fp8", 32607: "fp8"}
    chroma = catalog.catalog["chroma-hd"]
    assert catalog.recommended_precision(chroma, "high", 8192).precision == "fp8"
    assert catalog.recommended_precision(chroma, "high", 24564).precision == "bf16"


def test_measures_come_from_the_phase_14_data(catalog):
    option = catalog.catalog["klein-4b"].option("bf16")
    assert option.measure("fast", 8).seconds == 1.5
    assert option.measure("edit", 24).seconds == 2.5
    qwen = catalog.catalog["qwen-image"].option("bf16")
    assert qwen.measure("high", 32).offload_mib > 0
    # No figure for a level: the nearest lower one.
    edit = catalog.catalog["qwen-image-edit"].option("fp8")
    assert edit.measure("edit", 32) == edit.measure("edit", 24)
    assert catalog.catalog["flux-dev"].option("fp8").measure("high", 24) is None


def test_picks_accept_any_spelling_of_the_precision(catalog):
    assert catalog.parse_pick("high", "qwen-image:Q4_K_M") == Pick("qwen-image", "q4_k_m")
    assert catalog.parse_pick("high", "qwen-image:q4-k-m") == Pick("qwen-image", "q4_k_m")
    assert catalog.parse_pick("high", "qwen-image", 24564) == Pick("qwen-image", "fp8")


def test_unknown_models_and_precisions_list_the_valid_ones(catalog):
    with pytest.raises(ProvisionError, match=r"Unknown model 'nope'.*klein-4b"):
        catalog.parse_pick("fast", "nope")

    with pytest.raises(ProvisionError, match=r"doesn't have the high capability.*chroma-hd"):
        catalog.parse_pick("high", "klein-4b")

    with pytest.raises(ProvisionError, match=r"no fp4 precision.*bf16, int8"):
        catalog.parse_pick("fast", "z-image-turbo:fp4")

    with pytest.raises(ProvisionError, match="listed twice"):
        catalog.parse_picks("fast", ["klein-4b", "klein-4b:bf16"])


# Conjuntos y componentes compartidos


def build(catalog, profile, **picks):
    return catalog.build_set(
        catalog.profiles[profile],
        ModelSet({cap: tuple(Pick(*p.split(":")) for p in texts) for cap, texts in picks.items()}),
    )


def test_a_set_has_every_weight_once(catalog):
    profile = build(
        catalog, "full", fast=["klein-4b:bf16", "z-image-turbo:int8"],
        high=["chroma-hd:fp8", "flux-dev:fp8"], edit=["klein-4b:bf16"],
    )
    names = [model.name for model in profile.models]
    assert len(names) == len(set(names))
    # Klein in `fast` and in editing: its weights once. The Z-Image int8 encoder and Klein's
    # share nothing but are not repeated; T5 and the VAE are shared by Chroma and FLUX.
    assert names.count("klein_4b") == 1 and names.count("flux2_vae") == 1
    assert {"t5xxl", "flux_vae", "clip_l", "qwen3_4b", "qwen3_4b_fp8"} <= set(names)
    assert profile.bytes == sum(model.bytes for model in profile.models)


def test_the_encoder_is_shared_by_z_image_bf16_and_klein(catalog):
    profile = build(catalog, "fast", fast=["klein-4b:bf16", "z-image-turbo:bf16"])
    assert [m.name for m in profile.models].count("qwen3_4b") == 1


def test_a_set_needs_the_capabilities_of_its_profile(catalog):
    with pytest.raises(ProvisionError, match="needs at least one high model"):
        build(catalog, "quality", fast=["klein-4b:bf16"])

    with pytest.raises(ProvisionError, match="has no edit models"):
        build(catalog, "quality", fast=["klein-4b:bf16"], high=["sdxl:fp16"], edit=["klein-4b:bf16"])


def test_the_set_decides_the_nodes(catalog):
    assert not build(catalog, "quality", fast=["sdxl-turbo:fp16"], high=["flux-dev:fp8"]).nodes
    gguf = build(catalog, "quality", fast=["sdxl-turbo:fp16"], high=["qwen-image:q4_k_m"])
    assert [node.folder for node in gguf.nodes] == ["ComfyUI-GGUF"]


def test_the_default_comes_from_the_set(catalog):
    chosen = ModelSet(
        {"fast": (Pick("klein-4b", "bf16"), Pick("sdxl-turbo", "fp16"))}, {"fast": "sdxl-turbo"}
    )
    assert chosen.default("fast").model == "sdxl-turbo"
    assert ModelSet({"fast": chosen.of("fast")}).default("fast").model == "klein-4b"
    assert chosen.default("high") is None


def test_a_profile_below_the_models_gets_the_profile_that_has_them(catalog):
    wanted = ModelSet({"fast": (Pick("klein-4b", "bf16"),), "edit": (Pick("klein-4b", "bf16"),)})
    assert selection.profile_for(catalog, catalog.profiles["fast"], wanted).name == "full"


# Migración de registros de las fases 9 a 13


def models_dir(box):
    return box.data / "comfyui" / "models"


def migrated(box, catalog, profile, *files, **fields):
    for name in files:
        put(box, name)

    records = old_record(box, profile, **fields)
    return selection.installed_set(catalog, records, models_dir(box))


def test_a_phase_9_record_with_flux_dev(machine, catalog):
    installed = migrated(
        machine, catalog, "quality", "sdxl_turbo", "flux_dev",
        quality_model="flux-dev", precision="fp8",
    )
    assert installed.picks == {
        "fast": (Pick("sdxl-turbo", "fp16"),),
        "high": (Pick("flux-dev", "fp8"),),
    }
    assert installed.default("high").model == "flux-dev"


def test_a_gguf_record_keeps_the_precision_and_kontext(machine, catalog):
    installed = migrated(
        machine, catalog, "full-gguf", "sdxl_turbo", "flux_dev_gguf", "flux_kontext_gguf"
    )
    assert installed.of("high") == (Pick("flux-dev", "gguf"),)
    assert installed.of("edit") == (Pick("kontext", "gguf"),)


def test_a_record_before_phase_9_is_deduced_from_the_files(machine, catalog):
    installed = migrated(machine, catalog, "quality", "sdxl_turbo", "flux_dev")
    assert installed.of("high") == (Pick("flux-dev", "fp8"),)


def test_a_fast_record_has_only_fast(machine, catalog):
    installed = migrated(machine, catalog, "fast", "sdxl_turbo")
    assert installed.picks == {"fast": (Pick("sdxl-turbo", "fp16"),)}


def test_a_phase_13_record_with_sdxl(machine, catalog):
    installed = migrated(
        machine, catalog, "quality", "sdxl_turbo", "sdxl_base", "sdxl_offset_lora",
        quality_model="sdxl", precision="fp16",
    )
    assert installed.of("high") == (Pick("sdxl", "fp16"),)


def test_realvisxl_is_read_as_the_legacy_sdxl(machine, catalog):
    installed = migrated(machine, catalog, "quality-sdxl", "sdxl_turbo", "realvisxl")
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert installed.of("high") == (Pick("sdxl", "fp16"),)
    assert selection.is_legacy(catalog, records, models_dir(machine))
    resolved = quality.resolve_installed(catalog, records, models_dir(machine))
    assert "realvisxl" in {m.name for m in resolved.models}
    assert "sdxl_base" not in {m.name for m in resolved.models}


def install_old(box, catalog, profile, quality_model):
    """What an installation of before phase 15 left on disk, and its record."""
    old = catalog.resolve(catalog.profiles[profile], quality_model, 24564)

    for weight in old.models:
        put(box, weight.name)

    records = old_record(
        box, profile, quality_model=quality_model, precision=old.precision,
        edit_precision=old.edit_precision,
    )
    return old, records


def test_migrating_changes_nothing_on_disk(machine, catalog):
    _, records = install_old(machine, catalog, "full", "flux-dev")
    before = sorted(p for p in models_dir(machine).rglob("*") if p.is_file())
    found = selection.installed_set(catalog, records, models_dir(machine))
    change = selection.plan_set_change(
        catalog, records, models_dir(machine), found, found,
        quality.resolve_installed(catalog, records, models_dir(machine)),
    )
    assert not change.download and not change.delete and not change.changes_models
    assert before == sorted(p for p in models_dir(machine).rglob("*") if p.is_file())


@pytest.mark.parametrize(
    ("profile", "quality_model"),
    [("fast", None), ("quality", "flux-dev"), ("quality", "flux-schnell"), ("full", "sdxl"), ("full", "flux-dev")],
)
def test_the_migrated_set_resolves_to_what_the_old_code_installed(machine, catalog, profile, quality_model):
    old, records = install_old(machine, catalog, profile, quality_model)
    new = quality.resolve_installed(catalog, records, models_dir(machine))
    assert {m.name for m in new.models} == {m.name for m in old.models}
    assert new.quality_model == old.quality_model and new.precision == old.precision


def test_a_record_with_models_wins_over_the_deduction(machine, catalog):
    records = old_record(machine, "quality", quality_model="flux-dev")
    records.models = {
        "fast": [{"model": "klein-4b", "precision": "bf16"}],
        "high": [{"model": "chroma-hd", "precision": "fp8"}, {"model": "ghost", "precision": "x"}],
    }
    records.defaults = {"fast": "klein-4b", "high": "chroma-hd"}
    records.save()
    loaded = InstallManifest.load(config.INSTALL_MANIFEST)
    found = selection.installed_set(catalog, loaded, models_dir(machine))
    # What the catalog no longer knows is ignored.
    assert found.picks == {
        "fast": (Pick("klein-4b", "bf16"),),
        "high": (Pick("chroma-hd", "fp8"),),
    }
    assert found.defaults == {"fast": "klein-4b", "high": "chroma-hd"}
