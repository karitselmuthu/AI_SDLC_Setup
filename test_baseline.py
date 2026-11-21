import json
import os
import stat

import pytest

from architect import baseline

STEPS = {  # name: (template, file, reviewer, prior files), mirrors agent.STEPS in miniature
    "a": ("a.md", "a.md", "r", []),
    "b": ("b.md", "b.md", "r", ["a.md"]),
}


def _make(tmp_path, content="x"):
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    for f in ("a.md", "b.md"):
        (briefs / f).write_text(content)
    return briefs


def test_log_then_latest_last_approval_wins_and_orders_by_position(tmp_path):
    briefs = _make(tmp_path)
    baseline.log_approval(briefs, "a", briefs / "a.md", "lead")
    baseline.log_approval(briefs, "b", briefs / "b.md", "lead")
    (briefs / "a.md").write_text("changed")
    baseline.log_approval(briefs, "a", briefs / "a.md", "lead")
    ap = baseline.latest(briefs)
    assert ap["a.md"]["n"] == 2 and ap["b.md"]["n"] == 1
    assert ap["a.md"]["sha256"] == baseline.sha256(briefs / "a.md")


def test_latest_on_empty_ledger_is_empty(tmp_path):
    assert baseline.latest(tmp_path) == {}


def test_clean_set_has_no_problems(tmp_path):
    briefs = _make(tmp_path)
    for s, (_, f, _, _) in STEPS.items():
        baseline.log_approval(briefs, s, briefs / f, "lead")
    assert baseline.problems(briefs, STEPS) == []


def test_problem_not_produced(tmp_path):
    briefs = _make(tmp_path)
    (briefs / "b.md").unlink()
    baseline.log_approval(briefs, "a", briefs / "a.md", "lead")
    assert any("b.md: not produced" in p for p in baseline.problems(briefs, STEPS))


def test_problem_not_approved(tmp_path):
    briefs = _make(tmp_path)
    baseline.log_approval(briefs, "a", briefs / "a.md", "lead")
    assert baseline.problems(briefs, STEPS) == ["b.md: not approved (run `b` and approve it)"]


def test_problem_edited_after_approval(tmp_path):
    briefs = _make(tmp_path)
    for s, (_, f, _, _) in STEPS.items():
        baseline.log_approval(briefs, s, briefs / f, "lead")
    (briefs / "b.md").write_text("sneaky edit")
    assert baseline.problems(briefs, STEPS) == ["b.md: edited after it was approved (re-run `b`)"]


def test_problem_stale_when_an_input_was_reapproved_later(tmp_path):
    briefs = _make(tmp_path)
    baseline.log_approval(briefs, "a", briefs / "a.md", "lead")
    baseline.log_approval(briefs, "b", briefs / "b.md", "lead")
    (briefs / "a.md").write_text("new version of a")
    baseline.log_approval(briefs, "a", briefs / "a.md", "lead")  # a re-approved after b was approved
    assert baseline.problems(briefs, STEPS) == ["b.md: stale, a.md was re-approved after it (re-run `b`)"]


def test_rerunning_the_dependent_clears_staleness(tmp_path):
    briefs = _make(tmp_path)
    baseline.log_approval(briefs, "a", briefs / "a.md", "lead")
    baseline.log_approval(briefs, "b", briefs / "b.md", "lead")
    (briefs / "a.md").write_text("v2")
    baseline.log_approval(briefs, "a", briefs / "a.md", "lead")
    baseline.log_approval(briefs, "b", briefs / "b.md", "lead")
    assert baseline.problems(briefs, STEPS) == []


def test_version_numbers_and_previous_doc(tmp_path):
    base = tmp_path / "baseline"
    assert baseline.next_version(base) == 1
    (base / "v1").mkdir(parents=True)
    (base / "v2").mkdir()
    (base / "notes").mkdir()
    assert baseline.next_version(base) == 3
    assert baseline.previous_doc(base, 3, "doc.md") is None
    (base / "v2" / "doc.md").write_text("x")
    assert baseline.previous_doc(base, 3, "doc.md") == base / "v2" / "doc.md"


def _approved(tmp_path):
    briefs = _make(tmp_path)
    (briefs / "handoff.md").write_text("the handoff document")
    for s, f in [("a", "a.md"), ("b", "b.md"), ("handoff", "handoff.md")]:
        baseline.log_approval(briefs, s, briefs / f, f"{s}-lead")
    return briefs


def test_package_copies_artifacts_and_writes_manifest(tmp_path):
    briefs = _approved(tmp_path)
    src = tmp_path / "rfp.md"
    src.write_text("client doc")
    dest = baseline.package(briefs, tmp_path / "baseline", STEPS, "handoff.md", 1, [src, tmp_path / "missing.pdf"])
    assert dest.name == "v1"
    assert sorted(p.name for p in dest.iterdir()) == ["a.md", "b.md", "handoff.md", "manifest.json"]
    m = json.loads((dest / "manifest.json").read_text())
    assert m["version"] == 1 and m["previous_version"] is None and m["created_at"].endswith("+00:00")
    assert [a["file"] for a in m["artifacts"]] == ["a.md", "b.md", "handoff.md"]
    assert m["artifacts"][0]["approved_by"] == "a-lead"
    assert all(a["sha256"] == baseline.sha256(dest / a["file"]) for a in m["artifacts"])
    assert [s["path"] for s in m["source_documents"]] == [str(src)]  # the missing source is skipped


def test_package_makes_files_read_only(tmp_path):
    dest = baseline.package(_approved(tmp_path), tmp_path / "baseline", STEPS, "handoff.md", 1, [])
    for f in dest.iterdir():
        assert not os.stat(f).st_mode & stat.S_IWUSR


def test_package_never_overwrites_a_version(tmp_path):
    briefs = _approved(tmp_path)
    baseline.package(briefs, tmp_path / "baseline", STEPS, "handoff.md", 1, [])
    with pytest.raises(FileExistsError):
        baseline.package(briefs, tmp_path / "baseline", STEPS, "handoff.md", 1, [])


def test_second_version_links_to_the_first(tmp_path):
    briefs = _approved(tmp_path)
    baseline.package(briefs, tmp_path / "baseline", STEPS, "handoff.md", 1, [])
    dest = baseline.package(briefs, tmp_path / "baseline", STEPS, "handoff.md", 2, [])
    assert json.loads((dest / "manifest.json").read_text())["previous_version"] == 1
