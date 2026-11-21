import pathlib
import core
from architect import agent


def test_architect_is_read_only():
    assert set(core.AGENTS["architect"]["tools"].split(",")) == {"Read", "Grep", "Glob"}


def test_qualify_writes_brief(tmp_path, monkeypatch):
    rfp = tmp_path / "rfp.md"
    rfp.write_text("Build a portal. Due 1 May.")
    seen = {}
    monkeypatch.setattr(agent, "HERE", tmp_path)
    (tmp_path / "qualify.md").write_text("TEMPLATE")
    monkeypatch.setattr(agent, "ask", lambda a, p: seen.update(agent=a, prompt=p) or "## Business problem")
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.qualify([str(rfp)])
    assert seen["agent"] == "architect" and "TEMPLATE" in seen["prompt"] and str(rfp) in seen["prompt"]
    assert (tmp_path / "briefs/opportunity-brief.md").read_text() == "## Business problem"
    assert str(tmp_path) in core.EXTRA_DIRS


def test_discover_includes_opportunity_brief(tmp_path, monkeypatch):
    notes = tmp_path / "notes.md"
    notes.write_text("x")
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/opportunity-brief.md").write_text("brief")
    (tmp_path / "discover.md").write_text("DISCOVER")
    seen = {}
    monkeypatch.setattr(agent, "HERE", tmp_path)
    monkeypatch.setattr(agent, "ask", lambda a, p: seen.update(prompt=p) or "| R-001 |")
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.discover([str(notes)])
    assert "DISCOVER" in seen["prompt"] and "opportunity-brief.md" in seen["prompt"]
    assert (tmp_path / "briefs/requirements.md").read_text() == "| R-001 |"


def _setup(tmp_path, monkeypatch, replies=None):
    (tmp_path / "qualify.md").write_text("T")
    (tmp_path / "discover.md").write_text("D")
    doc = tmp_path / "doc.md"
    doc.write_text("x")
    prompts = []
    monkeypatch.setattr(agent, "HERE", tmp_path)
    monkeypatch.setattr(agent, "ask", lambda a, p: prompts.append(p) or "out")
    return doc, prompts


def test_missing_source_file_exits(tmp_path, monkeypatch):
    import pytest
    _setup(tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        agent.qualify([str(tmp_path / "nope.pdf")])
    with pytest.raises(SystemExit):
        agent.discover([str(tmp_path / "nope.pdf")])


def test_rejection_reruns_with_feedback(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    answers = iter([False, True])
    monkeypatch.setattr(agent, "approve", lambda who: next(answers))
    monkeypatch.setattr("builtins.input", lambda _: "add budget risk")
    agent.qualify([str(doc)])
    assert len(prompts) == 2 and "add budget risk" in prompts[1] and "add budget risk" not in prompts[0]


def test_discover_without_brief_reads_only_given_docs(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.discover([str(doc)])
    assert "opportunity-brief.md" not in prompts[0] and str(doc) in prompts[0]


def test_real_templates_forbid_invention_and_demand_sources():
    real = pathlib.Path(agent.__file__).parent
    for t in ("qualify.md", "discover.md"):
        text = (real / t).read_text().lower()
        assert "never invent" in text and ("not stated" in text or "proposed" in text)
