from pathlib import Path

from sos.fingerprint import fingerprint_dir


def test_fingerprint_changes_when_nested_file_changes(tmp_path: Path):
    skill = tmp_path / "demo-skill"
    scripts = skill / "scripts"
    scripts.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
    tool = scripts / "tool.py"
    tool.write_text("print('first')\n", encoding="utf-8")

    first = fingerprint_dir(skill)
    tool.write_text("print('second')\n", encoding="utf-8")
    second = fingerprint_dir(skill)

    assert first != second


def test_fingerprint_distinguishes_file_content_from_next_path_frame(tmp_path: Path):
    def frame(path: str) -> bytes:
        encoded_path = path.encode("utf-8")
        return len(encoded_path).to_bytes(8, "big") + encoded_path

    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()

    (one / "a").write_bytes(b"X" + frame("b") + b"Y")
    (two / "a").write_bytes(b"X")
    (two / "b").write_bytes(b"Y")

    assert fingerprint_dir(one) != fingerprint_dir(two)
