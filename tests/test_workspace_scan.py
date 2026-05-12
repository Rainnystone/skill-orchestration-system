from pathlib import Path

import pytest

from sos.workspace_scan import scan_workspace


def test_scan_workspace_detects_docs_shallow_only(tmp_path: Path) -> None:
    workspace = tmp_path / "docs-workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Project\n", encoding="utf-8")
    (workspace / "brief.docx").write_bytes(b"docx")
    (workspace / "docs").mkdir()
    nested = workspace / "nested"
    nested.mkdir()
    (nested / "ignore.md").write_text("nested", encoding="utf-8")
    (workspace / ".git").mkdir()

    signal = scan_workspace(workspace)

    assert signal.root == workspace
    assert signal.root_name == "docs-workspace"
    assert signal.top_dirs == ("docs", "nested")
    assert set(signal.top_files) == {"README.md", "brief.docx"}
    assert "ignore.md" not in signal.top_files
    assert ".md" in signal.extensions
    assert ".docx" in signal.extensions
    assert "docs" in signal.kinds


def test_scan_workspace_detects_mixed_python_and_data(tmp_path: Path) -> None:
    workspace = tmp_path / "analysis"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (workspace / "dataset.csv").write_text("value\n1\n", encoding="utf-8")

    signal = scan_workspace(workspace)

    assert signal.top_files == ("dataset.csv", "pyproject.toml")
    assert ".csv" in signal.extensions
    assert ".toml" in signal.extensions
    assert "python" in signal.kinds
    assert "data" in signal.kinds
    assert "mixed" in signal.kinds


def test_scan_workspace_rejects_missing_root(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    with pytest.raises(ValueError, match="workspace root"):
        scan_workspace(missing)


def test_scan_workspace_rejects_existing_file_root(tmp_path: Path) -> None:
    file_root = tmp_path / "workspace.txt"
    file_root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ValueError, match="workspace root"):
        scan_workspace(file_root)
