"""Documentation is generated from reviewed code and diagrams, never runtime."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/docs-build"))
spec = importlib.util.spec_from_file_location(
    "walkthrough_build", ROOT / "tools/docs-build/build.py"
)
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


def test_readable_walkthrough_matches_canonical_source():
    expanded, _ = docs.expand(docs.SOURCE.read_text(encoding="utf-8"))
    docs.check_readable(expanded)
    assert "<!-- snippet:" not in expanded
    assert "<!-- diagram:" not in expanded
    assert docs.PDF.is_file()


def test_changed_excerpt_stops_the_build(tmp_path, monkeypatch):
    monkeypatch.setattr(docs, "ROOT", tmp_path)
    path = tmp_path / "example.py"
    path.write_text("original = True\n", encoding="utf-8")
    digest, _ = docs.lines_hash(path, 1, 1)
    directive = f"<!-- snippet: example.py lines=1-1 sha={digest[:12]} lang=python -->"
    docs.expand(directive)
    path.write_text("changed = True\n", encoding="utf-8")
    with pytest.raises(docs.BuildError, match="changed"):
        docs.expand(directive)


def test_missing_link_stops_the_build():
    with pytest.raises(docs.BuildError, match="missing"):
        docs.expand("[missing](repo:src/not-a-real-file.py)")


def test_diagram_provenance_is_current():
    from render_diagrams import problems

    assert problems() == []


def test_changed_diagram_source_is_detected(tmp_path, monkeypatch):
    import render_diagrams as diagrams

    monkeypatch.setattr(diagrams, "DIAGRAMS", tmp_path)
    monkeypatch.setattr(diagrams, "CONFIG", tmp_path / "config.json")
    monkeypatch.setattr(diagrams, "MANIFEST", tmp_path / "manifest.json")
    diagrams.CONFIG.write_text("{}", encoding="utf-8")
    (tmp_path / "example.mmd").write_text("flowchart TB\nA-->B", encoding="utf-8")
    (tmp_path / "example.svg").write_text("<svg/>", encoding="utf-8")
    diagrams.MANIFEST.write_text('{"example.mmd": "stale"}', encoding="utf-8")
    assert any("changed" in problem for problem in diagrams.problems())
