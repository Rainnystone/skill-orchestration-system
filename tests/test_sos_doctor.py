import os
import json
import subprocess
import sys
from importlib import util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCTOR_PATH = REPO_ROOT / ".agents" / "skills" / "sos" / "scripts" / "sos_doctor.py"


spec = util.spec_from_file_location("sos_doctor", DOCTOR_PATH)
sos_doctor = util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(sos_doctor)

detect = sos_doctor.detect
find_repo_root = sos_doctor.find_repo_root

REQUIRED_RESULT_KEYS = {
    "mode",
    "message",
    "cwd",
    "repo_root",
    "installed_cli",
    "command",
    "env_updates",
    "python",
    "platform",
}


def _write_repo(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        '[project]\nname = "skill-orchestration-system"\n',
        encoding="utf-8",
    )
    (root / "src" / "sos").mkdir(parents=True)


def _assert_output_contract(result: dict[str, object]) -> None:
    assert REQUIRED_RESULT_KEYS <= result.keys()
    assert isinstance(result["mode"], str)
    assert isinstance(result["message"], str)
    assert isinstance(result["cwd"], str)
    assert result["repo_root"] is None or isinstance(result["repo_root"], str)
    assert result["installed_cli"] is None or isinstance(result["installed_cli"], str)
    assert isinstance(result["command"], list)
    assert all(isinstance(item, str) for item in result["command"])
    assert isinstance(result["env_updates"], dict)
    assert all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in result["env_updates"].items()
    )
    assert isinstance(result["python"], str)
    assert isinstance(result["platform"], str)


def test_detect_returns_advisory_mode_without_backend(tmp_path):
    result = detect(cwd=tmp_path, cli_finder=lambda _: None)

    _assert_output_contract(result)
    assert result["mode"] == "advisory"
    assert result["repo_root"] is None
    assert result["installed_cli"] is None
    assert result["command"] == []
    assert result["env_updates"] == {}
    assert result["cwd"] == str(tmp_path.resolve())


def test_detect_finds_repo_local_mode_from_nested_directory(tmp_path):
    repo = tmp_path / "skill-orchestration-system"
    nested = repo / "docs" / "plans"
    nested.mkdir(parents=True)
    _write_repo(repo)

    result = detect(cwd=nested, cli_finder=lambda _: None)

    _assert_output_contract(result)
    assert result["mode"] == "repo-local"
    assert result["repo_root"] == str(repo.resolve())
    assert result["installed_cli"] is None
    assert result["command"] == [sys.executable, "-m", "sos", "--version"]
    assert result["env_updates"] == {"PYTHONPATH": str((repo / "src").resolve())}
    assert find_repo_root(nested) == repo.resolve()


def test_detect_finds_installed_cli_when_no_repo_local_backend(tmp_path):
    result = detect(cwd=tmp_path, cli_finder=lambda _: "/usr/local/bin/sos")

    _assert_output_contract(result)
    assert result["mode"] == "installed-cli"
    assert result["repo_root"] is None
    assert result["installed_cli"] == "/usr/local/bin/sos"
    assert result["command"] == ["sos", "--version"]
    assert result["env_updates"] == {}


def test_cli_prints_json_output_for_repo_local_mode(tmp_path):
    repo = tmp_path / "skill-orchestration-system"
    nested = repo / "nested"
    nested.mkdir(parents=True)
    _write_repo(repo)

    completed = subprocess.run(
        [sys.executable, str(DOCTOR_PATH), "--cwd", str(nested)],
        check=True,
        capture_output=True,
        text=True,
    )

    result = json.loads(completed.stdout)
    _assert_output_contract(result)
    assert result["mode"] == "repo-local"
    assert result["repo_root"] == str(repo.resolve())
    assert result["command"] == [sys.executable, "-m", "sos", "--version"]


def test_rejects_pyproject_without_src_sos(tmp_path):
    root = tmp_path / "not-sos"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "skill-orchestration-system"\n',
        encoding="utf-8",
    )

    result = detect(cwd=nested, cli_finder=lambda _: None)

    assert find_repo_root(nested) is None
    assert result["mode"] == "advisory"
    assert result["repo_root"] is None
    assert result["command"] == []


def test_find_repo_root_accepts_project_name_with_inline_comment(tmp_path):
    repo = tmp_path / "skill-orchestration-system"
    nested = repo / "nested"
    nested.mkdir(parents=True)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "skill-orchestration-system" # inline comment\n',
        encoding="utf-8",
    )
    (repo / "src" / "sos").mkdir(parents=True)

    assert find_repo_root(nested) == repo.resolve()


def test_main_no_path_lookup_stays_advisory_without_repo(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sos_doctor.shutil, "which", lambda _: "/usr/local/bin/sos")

    exit_code = sos_doctor.main(["--cwd", str(tmp_path), "--no-path-lookup"])

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    _assert_output_contract(result)
    assert result["mode"] == "advisory"
    assert result["installed_cli"] is None
    assert result["command"] == []


def test_detect_prepends_repo_src_to_existing_pythonpath(tmp_path, monkeypatch):
    repo = tmp_path / "skill-orchestration-system"
    nested = repo / "docs"
    nested.mkdir(parents=True)
    _write_repo(repo)
    monkeypatch.setenv("PYTHONPATH", "existing/path")

    result = detect(cwd=nested, cli_finder=lambda _: None)

    assert result["env_updates"]["PYTHONPATH"] == (
        f"{(repo / 'src').resolve()}{os.pathsep}existing/path"
    )
