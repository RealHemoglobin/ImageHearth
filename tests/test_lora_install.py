"""Phase 13: installing, fixing the set of, and removing style LoRAs."""

import argparse
import json
import sys
import types

import pytest

from imagehearth_mcp import cli
from imagehearth_mcp.engine import config
from imagehearth_mcp.provisioner import (
    ProvisionError,
    agent_setup,
    doctor,
    maintenance,
    manifest,
    menu,
    models,
)
from imagehearth_mcp.provisioner import setup as setup_command
from imagehearth_mcp.provisioner.install_manifest import InstallManifest
from tests.test_move import installed  # noqa: F401
from tests.test_provisioner import fake_download, machine, press, setup_args, torch_ok  # noqa: F401
from tests.test_quality_model import idle  # noqa: F401

CATALOG = list(manifest.load().loras)


def sdxl(**kwargs):
    return setup_args(**{"profile": "quality", "quality_model": "sdxl", **kwargs})


def lora_file(box, name):
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    return models.resolve_dir(records, box.data / "comfyui") / manifest.load().loras[name].dest


def present(box):
    return {name for name in CATALOG if lora_file(box, name).exists()}


def owned_models():
    return {entry["path"] for entry in InstallManifest.load(config.INSTALL_MANIFEST).owned("model")}


DOWN = "\x1b[B"


def pick(names):
    """The keys that mark those LoRAs from the first row (arrows and Space), without Enter."""
    text, row = "", 0

    for index in sorted(CATALOG.index(name) for name in names):
        text += DOWN * (index - row) + " "
        row = index

    return text


# --loras


def test_the_option_is_known_to_the_parser():
    parsed = cli._build_parser().parse_args(["setup", "--loras", "a,b"])
    assert parsed.loras == "a,b"
    assert cli._build_parser().parse_args(["setup"]).loras is None


def test_a_list_installs_those_and_records_them_as_owned(machine):
    chosen = CATALOG[:2]
    assert setup_command.run(sdxl(loras=",".join(chosen))) == 0
    assert present(machine) == set(chosen)
    assert {lora_file(machine, name).as_posix() for name in chosen} <= owned_models()
    assert set(chosen) <= set(machine.downloads)
    assert not set(CATALOG[2:]) & set(machine.downloads)


def test_all_installs_every_lora(machine):
    assert setup_command.run(sdxl(loras="all")) == 0
    assert present(machine) == set(CATALOG)


def test_none_installs_no_lora(machine):
    assert setup_command.run(sdxl(loras="none")) == 0
    assert present(machine) == set()
    assert not set(CATALOG) & set(machine.downloads)


def test_without_the_option_no_lora_is_installed(machine):
    assert setup_command.run(sdxl()) == 0
    assert present(machine) == set()


def test_an_unknown_name_names_the_valid_ones_and_downloads_nothing(machine):
    with pytest.raises(ProvisionError) as caught:
        setup_command.run(sdxl(loras=f"{CATALOG[0]},ghibli"))

    assert "'ghibli'" in str(caught.value) and CATALOG[1] in str(caught.value)
    assert machine.downloads == [] and not config.INSTALL_MANIFEST.exists()


@pytest.mark.parametrize("model", ["flux-dev", "flux-schnell"])
def test_loras_with_flux_are_an_argument_error(machine, model):
    with pytest.raises(ProvisionError, match=r"only work with the SDXL 1\.0"):
        setup_command.run(setup_args(profile="quality", quality_model=model, loras="all"))

    assert machine.downloads == [] and not config.INSTALL_MANIFEST.exists()


def test_loras_with_a_profile_without_a_quality_model_are_an_error(machine):
    with pytest.raises(ProvisionError, match=r"only work with the SDXL 1\.0"):
        setup_command.run(setup_args(profile="fast", loras="all"))

    assert machine.downloads == []


def test_loras_with_an_installed_flux_are_an_error(machine):
    setup_command.run(setup_args(profile="quality", quality_model="flux-schnell"))

    with pytest.raises(ProvisionError, match=r"only work with the SDXL 1\.0"):
        setup_command.run(setup_args(profile="quality", loras="all"))


def test_the_option_fixes_the_set_on_an_existing_installation(machine):
    first, second, third = CATALOG[:3]
    setup_command.run(sdxl(loras=f"{first},{second}"))
    machine.downloads.clear()

    setup_command.run(sdxl(loras=f"{second},{third}"))
    assert present(machine) == {second, third}
    assert machine.downloads == [third]
    assert not lora_file(machine, first).as_posix() in owned_models()


def test_none_removes_every_lora(machine):
    setup_command.run(sdxl(loras="all"))
    setup_command.run(sdxl(loras="none"))
    assert present(machine) == set()


def test_without_the_option_an_existing_installation_keeps_its_loras(machine):
    setup_command.run(sdxl(loras="all"))
    machine.downloads.clear()
    setup_command.run(sdxl())
    assert present(machine) == set(CATALOG) and machine.downloads == []


def test_a_file_the_user_put_in_the_loras_folder_is_never_deleted(machine):
    setup_command.run(sdxl(loras="all"))
    mine = lora_file(machine, CATALOG[0]).parent / "mine.safetensors"
    mine.write_bytes(b"mine")
    setup_command.run(sdxl(loras="none"))
    assert mine.read_bytes() == b"mine"


def test_a_catalog_file_that_was_there_before_is_not_owned_and_stays(machine):
    setup_command.run(sdxl())
    path = lora_file(machine, CATALOG[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(CATALOG[0].encode())
    setup_command.run(sdxl(loras="none"))
    assert path.exists()


def test_the_summary_lists_what_is_added_and_what_is_deleted(machine, capsys):
    first, second = CATALOG[:2]
    setup_command.run(sdxl(loras=first))
    capsys.readouterr()
    setup_command.run(sdxl(loras=second))
    output = capsys.readouterr().out
    assert "(LoRA)" in output and f"LoRAs after this: {second}" in output
    assert f"To delete: {lora_file(machine, first).name}" in output


def test_the_licenses_of_the_new_loras_are_shown_before_downloading(machine, monkeypatch, capsys):
    with pytest.raises(ProvisionError, match="--accept-licenses"):
        setup_command.run(sdxl(loras="pixel-art", accept_licenses=False))

    output = capsys.readouterr().out
    assert "(LoRA)" in output and machine.downloads == []


# Interactive step


def interactive(**kwargs):
    return sdxl(
        **{
            "profile": None,
            "quality_model": None,
            "fast_models": "sdxl-turbo",
            "accept_licenses": False,
            "non_interactive": False,
            **kwargs,
        }
    )


DOWN = "\x1b[B"
# The quality models step: SDXL 1.0 is the first option and the recommended Qwen-Image the
# fifth. Mark one, unmark the other, Enter.
SDXL = " " + DOWN * 4 + " " + "\r"
# FLUX Dev is the second one; its precision menu then takes Enter (the recommended fp8).
FLUX_DEV = DOWN + " " + DOWN * 3 + " " + "\r" + "\r"


def test_the_step_appears_with_sdxl_and_nothing_is_marked_on_a_new_install(
    machine, monkeypatch, capsys
):
    # folder, profile quality, model sdxl, Enter (none marked), accept.
    press(monkeypatch, "12" + SDXL + "\r1")
    assert setup_command.run(interactive()) == 0
    output = capsys.readouterr().out
    assert "Step 4 of 5" in output and "Style LoRAs for SDXL 1.0" in output
    section = output.split("Style LoRAs for SDXL 1.0")[1].split("Selected:")[0]
    assert "[x]" not in section and "[ ] " in section
    assert present(machine) == set()


def test_the_step_shows_category_size_and_license(machine, monkeypatch, capsys):
    press(monkeypatch, "12" + SDXL + "\r1")
    setup_command.run(interactive())
    output = capsys.readouterr().out
    lora = manifest.load().loras[CATALOG[0]]
    assert lora.category in output and lora.description in output
    assert manifest.load().licenses[lora.license].name in output


def test_numbers_choose_the_loras(machine, monkeypatch):
    chosen = CATALOG[:3:2]
    press(monkeypatch, f"12{SDXL}{pick(chosen)}\r1")
    assert setup_command.run(interactive()) == 0
    assert present(machine) == set(chosen)


def test_zero_goes_back_to_the_model(machine, monkeypatch, capsys):
    # ... at the LoRAs step, 0 goes back to the model (default sdxl), then on again.
    press(monkeypatch, "12" + SDXL + "0" + "\r\r\r")
    assert setup_command.run(interactive()) == 0
    output = capsys.readouterr().out
    assert output.count("Step 3 of 5") == 2 and output.count("Step 4 of 5") == 2


def test_choosing_flux_removes_the_step(machine, monkeypatch, capsys):
    # folder, profile quality, model flux-dev, accept.
    press(monkeypatch, "12" + FLUX_DEV + "1")
    assert setup_command.run(interactive()) == 0
    output = capsys.readouterr().out
    assert "Style LoRAs" not in output and "Step 5 of 5" in output


def test_the_model_argument_keeps_the_step_in_the_count(machine, monkeypatch, capsys):
    press(monkeypatch, "12\r1")
    assert setup_command.run(interactive(quality_model="sdxl")) == 0
    assert "Step 3 of 4" in capsys.readouterr().out


def test_the_loras_argument_hides_the_step(machine, monkeypatch, capsys):
    press(monkeypatch, "12" + SDXL + "1")
    assert setup_command.run(interactive(loras="none")) == 0
    assert "Style LoRAs" not in capsys.readouterr().out


def test_an_answer_is_dropped_when_the_model_is_changed_afterwards(machine, monkeypatch):
    # sdxl with a LoRA, back (review, then the LoRAs step) to the model, flux-dev, accept.
    press(monkeypatch, f"12{SDXL}{pick(CATALOG[:1])}\r" "0" "0" " " + DOWN + " " + "\r" + "\r" + "1")
    assert setup_command.run(interactive()) == 0
    assert present(machine) == set()


def test_existing_loras_come_marked_and_enter_keeps_them(machine, monkeypatch, capsys):
    kept = CATALOG[:2]
    setup_command.run(sdxl(loras=",".join(kept)))
    machine.downloads.clear()
    capsys.readouterr()
    # profile and model are asked again; the LoRAs step shows the installed ones marked.
    press(monkeypatch, "2" "\r" "\r" "1")
    assert setup_command.run(interactive(accept_licenses=True)) == 0
    output = capsys.readouterr().out
    assert f"Selected: {', '.join(kept)}" in output
    assert present(machine) == set(kept) and machine.downloads == []


def test_choosing_none_in_the_step_removes_the_installed_ones(machine, monkeypatch):
    setup_command.run(sdxl(loras=CATALOG[0]))
    press(monkeypatch, "2" "\r" " " "\r" "1")
    assert setup_command.run(interactive()) == 0
    assert present(machine) == set()


def test_nothing_is_written_before_the_confirmation(machine, monkeypatch):
    press(monkeypatch, f"12{SDXL}{pick(CATALOG[:1])}\r" "\x03")

    with pytest.raises(KeyboardInterrupt):
        setup_command.run(interactive())

    assert machine.downloads == [] and not config.INSTALL_MANIFEST.exists()


def test_exiting_from_the_review_writes_nothing(machine, monkeypatch):
    press(monkeypatch, f"12{SDXL}{pick(CATALOG[:1])}\r" "0" "0" "0" "0" "0")
    assert setup_command.run(interactive()) == 0
    assert machine.downloads == [] and not config.INSTALL_MANIFEST.exists()


def test_deleting_loras_in_the_step_asks_for_the_final_confirmation(machine, monkeypatch, capsys):
    setup_command.run(sdxl(loras=CATALOG[0]))
    capsys.readouterr()
    press(monkeypatch, "2" "\r" " " "\r" "1")
    assert setup_command.run(interactive(accept_licenses=True)) == 0
    assert "To delete:" in capsys.readouterr().out


# Changing the quality model


def test_changing_from_sdxl_to_flux_deletes_the_loras_and_says_so(machine, capsys):
    setup_command.run(sdxl(loras="all"))
    capsys.readouterr()
    setup_command.run(setup_args(profile="quality", quality_model="flux-schnell", yes=True))
    output = capsys.readouterr().out
    assert present(machine) == set()
    assert "(LoRA)" in output and "To delete afterwards" in output
    assert not any(lora_file(machine, name).as_posix() in owned_models() for name in CATALOG)


def test_changing_to_flux_keeps_a_file_that_is_not_ours(machine):
    setup_command.run(sdxl(loras="all"))
    mine = lora_file(machine, CATALOG[0]).parent / "mine.safetensors"
    mine.write_bytes(b"mine")
    setup_command.run(setup_args(profile="quality", quality_model="flux-schnell", yes=True))
    assert mine.read_bytes() == b"mine"


def test_changing_to_flux_without_loras_has_nothing_to_delete(machine, capsys):
    setup_command.run(sdxl())
    capsys.readouterr()
    setup_command.run(setup_args(profile="quality", quality_model="flux-schnell", yes=True))
    assert "(LoRA)" not in capsys.readouterr().out


# uninstall, doctor


def test_uninstall_removes_the_loras_and_keeps_foreign_files(machine):
    setup_command.run(sdxl(loras="all"))
    mine = lora_file(machine, CATALOG[0]).parent / "mine.safetensors"
    mine.write_bytes(b"mine")
    args = argparse.Namespace(yes=True, remove_models=True, keep_models=False)
    assert maintenance.uninstall(args) == 0
    assert present(machine) == set()
    assert mine.read_bytes() == b"mine"


def test_uninstall_can_keep_the_models_and_their_loras(machine):
    setup_command.run(sdxl(loras=CATALOG[0]))
    args = argparse.Namespace(yes=True, remove_models=False, keep_models=True)
    assert maintenance.uninstall(args) == 0
    assert present(machine) == {CATALOG[0]}


def records_and_catalog(machine):
    records = InstallManifest.load(config.INSTALL_MANIFEST)
    return records, manifest.load()


def test_doctor_lists_the_installed_loras(machine):
    chosen = CATALOG[:2]
    setup_command.run(sdxl(loras=",".join(chosen)))
    records, catalog = records_and_catalog(machine)
    check = doctor.check_models(config, records, catalog, False, "linux")
    assert check.status == doctor.OK
    assert check.details["loras"] == chosen
    assert all(name in check.message for name in chosen)


def test_doctor_warns_when_a_registered_lora_is_missing(machine):
    setup_command.run(sdxl(loras="all"))
    lora_file(machine, CATALOG[1]).unlink()
    records, catalog = records_and_catalog(machine)
    check = doctor.check_models(config, records, catalog, False, "linux")
    assert check.status == doctor.WARN
    assert CATALOG[1] in check.details["lora_problems"]
    assert CATALOG[1] not in check.details["loras"]
    assert f"--loras {','.join([*check.details['loras'], CATALOG[1]])}" in check.fix


def test_doctor_warns_when_a_lora_does_not_match(machine):
    setup_command.run(sdxl(loras=CATALOG[0]))
    lora_file(machine, CATALOG[0]).write_bytes(b"corrupt but another size")
    records, catalog = records_and_catalog(machine)
    check = doctor.check_models(config, records, catalog, False, "linux")
    assert check.status == doctor.WARN and CATALOG[0] in check.details["lora_problems"]


def test_doctor_with_hashes_finds_a_lora_of_the_right_size_and_wrong_content(machine):
    setup_command.run(sdxl(loras=CATALOG[0]))
    path = lora_file(machine, CATALOG[0])
    path.write_bytes(b"x" * path.stat().st_size)
    records, catalog = records_and_catalog(machine)
    assert doctor.check_models(config, records, catalog, False, "linux").status == doctor.OK
    assert doctor.check_models(config, records, catalog, True, "linux").status == doctor.WARN


def test_doctor_json_has_the_loras_in_the_details(machine):
    setup_command.run(sdxl(loras=CATALOG[0]))
    records, catalog = records_and_catalog(machine)
    check = doctor.check_models(config, records, catalog, False, "linux")
    data = doctor.to_json([check])
    assert data["checks"][0]["details"]["loras"] == [CATALOG[0]]
    json.dumps(data)


def test_doctor_without_loras_reports_an_empty_list(machine):
    setup_command.run(sdxl())
    records, catalog = records_and_catalog(machine)
    check = doctor.check_models(config, records, catalog, False, "linux")
    assert check.status == doctor.OK and check.details["loras"] == []


def test_doctor_does_not_complain_about_a_lora_that_was_never_installed(machine):
    setup_command.run(sdxl())
    records, catalog = records_and_catalog(machine)
    check = doctor.check_models(config, records, catalog, False, "linux")
    assert "lora_problems" not in check.details


# The menu


def keys(text):
    chars = iter(text)
    return lambda: next(chars)


OPTIONS = [menu.Option(name, name) for name in "abc"]


def test_choose_many_with_marks_enter_keeps_them(capsys):
    assert menu.choose_many("Pick", OPTIONS, reader=keys("\r"), default=["b"]) == ["b"]
    output = capsys.readouterr().out
    assert "[ ] a" in output and "[x] b" in output


def test_choose_many_unmarking_everything_chooses_nothing():
    assert menu.choose_many("Pick", OPTIONS, reader=keys(DOWN + " \r"), default=["b"]) == []


def test_choose_many_keys_replace_the_marks():
    answer = menu.choose_many("Pick", OPTIONS, reader=keys(" " + DOWN + " " + DOWN + " \r"), default=["b"])
    assert answer == ["a", "c"]


def test_choose_many_line_mode_none_chooses_nothing(monkeypatch):
    monkeypatch.setattr(sys, "stdin", types.SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr("builtins.input", lambda prompt="": "none")
    assert menu.choose_many("Pick", OPTIONS, default=["b"]) == []


def test_choose_many_without_marks_is_unchanged():
    assert menu.choose_many("Pick", OPTIONS, reader=keys("\r")) == ["a", "b", "c"]


# setup_status and setup_start


@pytest.fixture
def paths(tmp_path, monkeypatch):
    for name, value in {
        "DATA_DIR": tmp_path,
        "COMFY_DIR": tmp_path / "comfyui",
        "INSTALL_MANIFEST": tmp_path / "install.json",
        "SETUP_LOCK": tmp_path / "setup.lock",
        "SETUP_JOB_LOCK": tmp_path / "job.lock",
        "SETUP_JOB_FILE": tmp_path / "state" / "job.json",
        "SETUP_JOB_LOG": tmp_path / "logs" / "job.log",
        "CONFIG_FILE": tmp_path / "config.toml",
    }.items():
        monkeypatch.setattr(config, name, value)

    return tmp_path


class FakeProcess:
    pid = 4242


@pytest.fixture
def spawned(paths, monkeypatch):
    calls = []

    def spawn(profile, existing, quality_model="", install_dir="", loras=""):
        calls.append({"profile": profile, "quality_model": quality_model, "loras": loras})
        return FakeProcess()

    monkeypatch.setattr(agent_setup, "_spawn", spawn)
    monkeypatch.setattr(agent_setup.processes, "create_time", lambda pid: 1.0)
    return calls


def test_status_lists_the_catalog_with_size_license_and_what_is_installed(paths):
    result = agent_setup.status()["loras"]
    assert result["only_with"] == "sdxl"
    names = [entry["name"] for entry in result["available"]]
    assert names == CATALOG

    entry = result["available"][0]
    lora = manifest.load().loras[CATALOG[0]]
    assert entry["description"] == lora.description and entry["category"] == lora.category
    assert entry["download_mb"] == round(lora.bytes / 1e6)
    assert entry["license"]["name"] and entry["commercial_use"] is True
    assert not any(item["installed"] for item in result["available"])


def test_status_marks_the_installed_ones(machine):
    setup_command.run(sdxl(loras=CATALOG[1]))
    installed = {
        item["name"] for item in agent_setup.status()["loras"]["available"] if item["installed"]
    }
    assert installed == {CATALOG[1]}


def test_start_with_a_list(spawned):
    result = agent_setup.start("quality", True, quality_model="sdxl", loras=CATALOG[:2])
    assert result["loras"] == CATALOG[:2]
    assert spawned[0]["loras"] == ",".join(CATALOG[:2])


def test_start_with_all(spawned):
    result = agent_setup.start("quality", True, quality_model="sdxl", loras=["all"])
    assert result["loras"] == CATALOG and spawned[0]["loras"] == ",".join(CATALOG)


@pytest.mark.parametrize("empty", [None, []])
def test_start_without_loras_changes_nothing(spawned, empty):
    result = agent_setup.start("quality", True, quality_model="sdxl", loras=empty)
    assert "loras" not in result and spawned[0]["loras"] == ""


def test_start_with_an_unknown_name(spawned):
    with pytest.raises(ValueError, match=r"Unknown LoRA.*ghibli.*Choose from"):
        agent_setup.start("quality", True, quality_model="sdxl", loras=["ghibli"])

    assert spawned == []


@pytest.mark.parametrize("model", ["flux-dev", "flux-schnell"])
def test_start_with_flux(spawned, model):
    with pytest.raises(ValueError, match="only work with the sdxl"):
        agent_setup.start("quality", True, quality_model=model, loras=["all"])

    assert spawned == []


def test_start_with_a_profile_without_a_quality_model(spawned):
    with pytest.raises(ValueError, match="only work with the sdxl"):
        agent_setup.start("fast", True, loras=["all"])


def test_start_with_a_malformed_list(spawned):
    for value in ("anime", [1], ["all", "anime"]):
        with pytest.raises(ValueError):
            agent_setup.start("quality", True, quality_model="sdxl", loras=value)


def test_the_installer_process_receives_the_loras():
    parsed = agent_setup._args("quality", "", "sdxl", "", "anime,detail")
    assert parsed.loras == "anime,detail" and parsed.quality_models == "sdxl"
    assert agent_setup._args("quality", "", "sdxl").loras is None


def test_the_tool_has_the_parameter_and_the_instructions_mention_the_question():
    import inspect

    from imagehearth_mcp import server

    assert "loras" in inspect.signature(server.setup_start).parameters
    assert "loras" in inspect.signature(server.create_image).parameters
    assert "style LoRAs" in server.INSTRUCTIONS and "loras" in server.INSTRUCTIONS


# update --move-to


def test_move_carries_the_installed_loras(installed, tmp_path, monkeypatch):
    from tests.test_move import other_disk, update

    chosen = CATALOG[:2]
    assert setup_command.run(sdxl(loras=",".join(chosen))) == 0
    other_disk(monkeypatch)
    target = tmp_path / "disk2"
    assert update(target) == 0
    folder = target / "comfyui" / "models"

    for name in chosen:
        assert (folder / manifest.load().loras[name].dest).exists()

    records = InstallManifest.load(config.INSTALL_MANIFEST)
    assert records.is_owned(folder / manifest.load().loras[chosen[0]].dest)
    assert not (installed.data / "comfyui").exists()
