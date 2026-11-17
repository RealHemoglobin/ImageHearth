"""`scripts/contract_latest.py`: la última versión de ComfyUI, con la API simulada."""

import importlib.util
import io
import sys
import tarfile
from pathlib import Path

import pytest
import requests

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load(name):
    sys.path.insert(0, str(SCRIPTS))

    try:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS))


@pytest.fixture(scope="module")
def latest():
    return load("contract_latest")


def comfy_archive(tag):
    buffer = io.BytesIO()

    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        data = b"print('comfy')"
        info = tarfile.TarInfo(f"ComfyUI-{tag.lstrip('v')}/main.py")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    return buffer.getvalue()


class Response:
    def __init__(self, payload=None, body=b"", status=200):
        self.payload = payload
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status} error")

    def json(self):
        return self.payload

    def iter_content(self, size):
        yield self.body


class Github:
    """La API y los archivos de GitHub, sin red."""

    def __init__(self, tag="v9.9.9", api_status=200, payload=None):
        self.tag = tag
        self.api_status = api_status
        self.payload = {"tag_name": tag} if payload is None else payload
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)

        if url.endswith("/releases/latest"):
            return Response(self.payload, status=self.api_status)

        return Response(body=comfy_archive(self.tag))


def run(latest, tmp_path, github, verify):
    return latest.run(session=github, log_dir=tmp_path / "logs", verify=verify, now=lambda: 1_800_000_000)


def test_latest_tag_is_read_from_the_release_api(latest):
    github = Github("v0.50.1")
    assert latest.latest_tag(github) == "v0.50.1"
    assert github.urls == [latest.RELEASE_API]


@pytest.mark.parametrize("github", [Github(api_status=403), Github(payload={}), Github(tag="v1/../x")])
def test_unusable_release_answers_are_errors(latest, github):
    with pytest.raises(latest.LatestError):
        latest.latest_tag(github)


def test_passing_run_logs_the_tested_version_and_exits_0(latest, tmp_path):
    github = Github("v9.9.9")
    seen = {}

    def verify(source, folder, log_file=None):
        seen["source"] = Path(source)
        seen["log_file"] = log_file
        assert (Path(source) / "main.py").exists()
        return []

    code, log = run(latest, tmp_path, github, verify)

    assert code == 0
    assert "v9.9.9" in log.name
    text = log.read_text(encoding="utf-8")
    assert "Latest ComfyUI release: v9.9.9" in text
    assert "Pinned by ImageHearth:" in text
    assert "Result: PASS (ComfyUI v9.9.9)" in text
    assert "Archive SHA-256:" in text
    assert latest.ARCHIVE_URL.format(tag="v9.9.9") in github.urls
    assert log.parent == tmp_path / "logs"
    assert seen["log_file"].parent == tmp_path / "logs"
    # La carpeta temporal desaparece al terminar.
    assert not seen["source"].exists()


def test_broken_contract_exits_1_and_lists_the_problems(latest, tmp_path):
    code, log = run(
        latest, tmp_path, Github(), lambda source, folder, log_file=None: ["MISSING FooNode (used by a.json)"]
    )

    assert code == 1
    text = log.read_text(encoding="utf-8")
    assert "MISSING FooNode" in text
    assert "Result: FAIL (ComfyUI v9.9.9)" in text


def test_comfyui_that_does_not_start_exits_1(latest, tmp_path):
    def verify(source, folder, log_file=None):
        raise latest.contract.ContractError("ComfyUI exited at startup (code 1).")

    code, log = run(latest, tmp_path, Github(), verify)

    assert code == 1
    assert "FAIL: ComfyUI exited at startup" in log.read_text(encoding="utf-8")


def test_github_down_exits_1_and_still_leaves_a_log(latest, tmp_path):
    def never(*args, **kwargs):
        raise AssertionError("nothing to verify without a version")

    code, log = run(latest, tmp_path, Github(api_status=503), never)

    assert code == 1
    text = log.read_text(encoding="utf-8")
    assert "Can't read the latest ComfyUI release" in text
    assert "unknown" in log.name


def test_download_failure_exits_1(latest, tmp_path):
    class Broken(Github):
        def get(self, url, **kwargs):
            if url.endswith(".tar.gz"):
                return Response(status=404)

            return super().get(url, **kwargs)

    code, log = run(latest, tmp_path, Broken(), lambda *a, **k: [])

    assert code == 1
    assert "Can't download or unpack ComfyUI v9.9.9" in log.read_text(encoding="utf-8")


def test_an_archive_that_tries_to_escape_is_rejected(latest, tmp_path):
    class Evil(Github):
        def get(self, url, **kwargs):
            if url.endswith(".tar.gz"):
                buffer = io.BytesIO()

                with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
                    info = tarfile.TarInfo("ComfyUI-1/../../escape.py")
                    info.size = 1
                    tar.addfile(info, io.BytesIO(b"x"))

                return Response(body=buffer.getvalue())

            return super().get(url, **kwargs)

    code, log = run(latest, tmp_path, Evil(), lambda *a, **k: [])

    assert code == 1
    assert not (tmp_path / "escape.py").exists()
    assert "FAIL" in log.read_text(encoding="utf-8")


def test_the_shared_check_reports_missing_nodes_and_inputs():
    contract = load("contract")
    available = {name: {"input": {"required": {}, "optional": {}}} for name in contract.workflow_nodes()}
    problems = contract.compare(available)
    assert problems and all(p.startswith("UNKNOWN INPUT") for p in problems)

    del available["KSampler"]
    assert contract.compare(available) == [
        f"MISSING KSampler (used by {', '.join(sorted(contract.workflow_nodes()['KSampler']))})"
    ]
    assert contract.report([]) == 0
    assert contract.report(["MISSING X"]) == 1


def test_wrappers_exist_and_call_the_script():
    assert "contract_latest.py" in (SCRIPTS / "contract_latest.sh").read_text(encoding="utf-8")
    assert "contract_latest.py" in (SCRIPTS / "contract_latest.ps1").read_text(encoding="utf-8")
