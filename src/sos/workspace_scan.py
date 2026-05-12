from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


_NOISY_TOP_DIRS = frozenset(
    {".git", ".sos", ".agents", ".venv", "__pycache__", "node_modules"}
)
_DOC_EXTENSIONS = frozenset({".md", ".markdown", ".docx", ".pdf", ".txt"})
_WEB_EXTENSIONS = frozenset({".html", ".htm", ".css", ".js", ".jsx", ".ts", ".tsx"})
_PYTHON_EXTENSIONS = frozenset({".py"})
_DATA_EXTENSIONS = frozenset({".csv", ".json", ".sql", ".xlsx", ".tsv"})
_DESIGN_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".fig", ".sketch", ".xd", ".psd"}
)
_KIND_ORDER = ("docs", "browser", "python", "data", "design")


@dataclass(frozen=True)
class WorkspaceSignal:
    root: Path
    root_name: str
    top_dirs: tuple[str, ...]
    top_files: tuple[str, ...]
    extensions: tuple[str, ...]
    markers: tuple[str, ...]
    kinds: tuple[str, ...]


def scan_workspace(root: str | Path, max_entries: int = 80) -> WorkspaceSignal:
    workspace_root = Path(root).expanduser()
    if not workspace_root.is_dir():
        raise ValueError(f"workspace root is not a directory: {workspace_root}")

    top_dirs: list[str] = []
    top_files: list[str] = []
    extensions: set[str] = set()
    markers: set[str] = set()
    kinds: set[str] = set()

    entries = sorted(workspace_root.iterdir(), key=lambda entry: entry.name.lower())
    for entry in entries[: max(0, max_entries)]:
        name = entry.name
        lower_name = name.lower()
        if entry.is_dir():
            if name in _NOISY_TOP_DIRS:
                continue
            top_dirs.append(name)
            if lower_name == "docs":
                markers.add("docs_dir")
                kinds.add("docs")
            continue

        if not entry.is_file():
            continue

        top_files.append(name)
        suffix = entry.suffix.lower()
        if suffix:
            extensions.add(suffix)
        _collect_file_signals(lower_name, suffix, markers, kinds)

    ordered_kinds = [kind for kind in _KIND_ORDER if kind in kinds]
    if len(ordered_kinds) > 1:
        ordered_kinds.append("mixed")

    return WorkspaceSignal(
        root=workspace_root,
        root_name=workspace_root.name,
        top_dirs=tuple(top_dirs),
        top_files=tuple(top_files),
        extensions=tuple(sorted(extensions)),
        markers=tuple(sorted(markers)),
        kinds=tuple(ordered_kinds),
    )


def _collect_file_signals(
    lower_name: str,
    suffix: str,
    markers: set[str],
    kinds: set[str],
) -> None:
    if lower_name.startswith("readme"):
        markers.add("readme")
        kinds.add("docs")
    if lower_name == "pyproject.toml":
        markers.add("pyproject")
        kinds.add("python")
    if lower_name == "requirements.txt":
        markers.add("requirements")
        kinds.add("python")
    if lower_name == "package.json":
        markers.add("package_json")
        kinds.add("browser")

    if suffix in _DOC_EXTENSIONS:
        kinds.add("docs")
    if suffix in _WEB_EXTENSIONS:
        kinds.add("browser")
    if suffix in _PYTHON_EXTENSIONS:
        kinds.add("python")
    if suffix in _DATA_EXTENSIONS:
        kinds.add("data")
    if suffix in _DESIGN_EXTENSIONS:
        kinds.add("design")
