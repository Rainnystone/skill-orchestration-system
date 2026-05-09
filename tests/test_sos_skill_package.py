from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / ".agents" / "skills" / "sos"
SKILL_MD = SKILL_ROOT / "SKILL.md"
REFERENCES = SKILL_ROOT / "references"
SCRIPTS = SKILL_ROOT / "scripts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_sos_skill_package_has_agent_skill_shape():
    assert SKILL_MD.is_file()
    assert REFERENCES.is_dir()
    assert SCRIPTS.is_dir()
    for name in (
        "workflows.md",
        "safety-model.md",
        "execution-modes.md",
        "codex.md",
        "claude-code-future.md",
    ):
        assert (REFERENCES / name).is_file()
    assert (SCRIPTS / "sos_doctor.py").is_file()


def test_sos_skill_frontmatter_is_portable_and_codex_first():
    text = _read(SKILL_MD)
    assert text.startswith("---\n")
    assert "\nname: sos\n" in text
    assert "\ndescription:" in text
    assert "Codex" in text
    assert "global installation" in text
    assert len(text.splitlines()) <= 90


def test_sos_skill_uses_progressive_disclosure_references():
    text = _read(SKILL_MD)
    for reference in (
        "references/execution-modes.md",
        "references/workflows.md",
        "references/safety-model.md",
        "references/codex.md",
        "references/claude-code-future.md",
    ):
        assert reference in text
    assert "Do not load every reference up front" in text
    assert "Do not paste the full CLI reference" in text


def test_sos_skill_does_not_keep_obsolete_readme_rewrite_deferral():
    text = _read(SKILL_MD)
    assert "README rewrite is deferred" not in text
    assert "ask the human for the README style" not in text


def test_readmes_explain_how_to_use_sos_after_installation():
    english = _read(REPO_ROOT / "README.md")
    chinese = _read(REPO_ROOT / "README_CN.md")

    for text in (english, chinese):
        assert "Use the sos skill" in text
        assert "sos_doctor.py" in text
        assert "python -m sos" in text
        assert "sos-haruhi" in text
        assert "sos-<pack>" in text
        assert "pack activate" in text
        assert "pack activate PACK_ID --runtime-root RUNTIME_ROOT --sync=clean-auto" in text

    assert "## How To Use SOS" in english
    assert "Codex Skill Path" in english
    assert "CLI Path" in english

    first_run = english.split("### Codex Skill Path", 1)[1].split("### CLI Path", 1)[0]
    assert "Use sos-haruhi" not in first_run


def test_codex_reference_has_current_readme_policy():
    text = _read(REFERENCES / "codex.md")
    assert "README rewrite is deferred" not in text
    assert "Keep `README.md` and `README_CN.md` aligned" in text


def test_sos_skill_references_do_not_defer_completed_readme_work():
    for path in sorted(REFERENCES.glob("*.md")):
        text = _read(path)
        assert "README rewrite is deferred" not in text, path


def test_claude_code_reference_is_future_only():
    text = _read(REFERENCES / "claude-code-future.md")
    assert "not implemented in this phase" in text
    assert "settings, commands, or installer" in text.lower()
    assert "Do not claim Claude Code support is complete" in text
    assert "separate approved implementation packet" in text


def test_public_skill_files_do_not_contain_private_local_paths():
    forbidden = (
        "F:" + "\\",
        "C:" + "\\Users",
        "Users" + "\\Administrator",
        "vibe" + " coding",
    )
    for path in sorted(SKILL_ROOT.rglob("*")):
        if path.suffix not in {".md", ".py"}:
            continue
        text = _read(path)
        for needle in forbidden:
            assert needle not in text, f"{needle!r} leaked into {path}"


def test_public_skill_markdown_avoids_shell_chaining():
    for path in sorted(SKILL_ROOT.rglob("*.md")):
        text = _read(path)
        assert " && " not in text


def test_workflows_resolve_invocation_before_commands():
    text = _read(REFERENCES / "workflows.md")
    assert "Resolve Invocation First" in text
    assert "repo-local" in text
    assert "scripts/sos_doctor.py" in text
    assert "append the workflow arguments" in text


def test_workflows_do_not_require_global_sos_examples():
    text = _read(REFERENCES / "workflows.md")
    assert "do not prove that a global `sos` executable exists" in text
    assert "```text\nsos " not in text


def test_activation_requires_safety_model_and_human_approval():
    text = _read(REFERENCES / "workflows.md")
    activation = text.split("## Activate A Pack", 1)[1].split("##", 1)[0]
    assert "safety-model.md" in activation
    assert "explicit human approval" in activation
    assert "status" in activation
    assert "backup list" in activation
    assert "pack activate" in activation


def test_workflows_include_pack_inspection_changes_and_skill_selection():
    text = _read(REFERENCES / "workflows.md")
    assert "Inspect Packs" in text
    assert "pack list --runtime-root RUNTIME_ROOT" in text
    assert "pack show PACK_ID --runtime-root RUNTIME_ROOT" in text
    assert "Detect New Or Changed Skills" in text
    assert "changes --root SKILLS_ROOT --runtime-root RUNTIME_ROOT --codex-config CODEX_CONFIG" in text
    assert "Select A Skill Inside A Pack" in text
    assert "exactly against manifest `skills.name`" in text
