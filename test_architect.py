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


def test_every_step_has_template_and_ordered_inputs():
    """Guards the 11-step table: templates exist, and each step only reads outputs earlier steps produce."""
    produced = set()
    for name, (template, out, reviewer, prior) in agent.STEPS.items():
        assert (pathlib.Path(agent.__file__).parent / template).is_file(), name
        assert set(prior) <= produced, f"{name} reads an output no earlier step makes"
        assert out not in produced and reviewer
        produced.add(out)


def test_assess_feeds_in_earlier_briefs_and_env_docs(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "assess.md").write_text("A")
    (tmp_path / "briefs").mkdir()
    for f in ("opportunity-brief.md", "requirements.md"):
        (tmp_path / "briefs" / f).write_text("x")
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.assess([str(doc)])
    p = prompts[0]
    assert "opportunity-brief.md" in p and "requirements.md" in p and str(doc) in p
    assert (tmp_path / "briefs/current-state.md").read_text() == "out"


def test_assess_template_covers_the_step_3_outputs():
    text = (pathlib.Path(agent.__file__).parent / "assess.md").read_text()
    for needed in ("Current systems", "Interfaces", "Data flows", "Hosting", "Identity", "pain points",
                   "Dependencies", "Gaps", "client confirmation", "mermaid", "never invent"):
        assert needed.lower() in text.lower(), needed


def test_options_feeds_in_all_three_earlier_briefs(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "options.md").write_text("O")
    (tmp_path / "briefs").mkdir()
    for f in ("opportunity-brief.md", "requirements.md", "current-state.md"):
        (tmp_path / "briefs" / f).write_text("x")
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.options([str(doc)])
    assert all(f in prompts[0] for f in ("opportunity-brief.md", "requirements.md", "current-state.md"))
    assert (tmp_path / "briefs/solution-options.md").read_text() == "out"


def test_options_template_enforces_comparison_and_honesty():
    text = (pathlib.Path(agent.__file__).parent / "options.md").read_text().lower()
    for needed in ("fit", "risk", "cost drivers", "complexity", "time to deliver", "recommendation",
                   "assumptions register", "trade-offs", "never invent", "do not invent prices",
                   "not met", "change freeze", "what would change the recommendation"):
        assert needed in text, needed


def test_untraced_finds_requirement_ids_missing_from_design(tmp_path):
    (tmp_path / "requirements.md").write_text("| R-001 | a |\n| R-002 | b |\n| R-003 | c |")
    assert agent.untraced(tmp_path, "R-001 and R-003 mapped") .count("R-002") == 1
    assert agent.untraced(tmp_path, "R-001 R-002 R-003") == ""
    assert agent.untraced(tmp_path / "nowhere", "anything") == ""  # no requirements file -> nothing to check


def test_design_repairs_missing_traceability_once(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "design.md").write_text("DES")
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/requirements.md").write_text("R-001 R-002")
    replies = iter(["covers R-001 only", "covers R-001 and R-002"])
    monkeypatch.setattr(agent, "ask", lambda a, p: prompts.append(p) or next(replies))
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.design([str(doc)])
    assert len(prompts) == 2 and "R-002" in prompts[1]
    assert (tmp_path / "briefs/target-architecture.md").read_text() == "covers R-001 and R-002"


def test_other_steps_have_no_repair_pass(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/requirements.md").write_text("R-001 R-002")
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.qualify([str(doc)])
    assert len(prompts) == 1


def test_design_template_covers_step_5_outputs():
    text = (pathlib.Path(agent.__file__).parent / "design.md").read_text().lower()
    for needed in ("components", "boundaries", "interfaces", "data flows", "identity", "security controls",
                   "resilience", "observability", "deployment model", "requirement traceability",
                   "one row for every requirement", "mermaid", "never invent", "proposed",
                   "do not name a specific vendor", "key design decisions"):
        assert needed in text, needed


def test_must_cover_factory_is_generic(tmp_path):
    (tmp_path / "x.md").write_text("K1 K2 I1")
    check = agent.must_cover("x.md", r"\b[KI]\d+\b", "table")
    assert "K2" in check(tmp_path, "K1 I1") and "K1" not in check(tmp_path, "K1 I1")
    assert check(tmp_path, "K1 K2 I1") == ""


def test_fit_repairs_when_a_component_is_not_assessed(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "fit.md").write_text("FIT")
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/target-architecture.md").write_text("K1 K2 I1")
    replies = iter(["K1 and I1 only", "K1 K2 I1 all assessed"])
    monkeypatch.setattr(agent, "ask", lambda a, p: prompts.append(p) or next(replies))
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.fit([str(doc)])
    assert len(prompts) == 2 and "K2" in prompts[1] and "fit assessment" in prompts[1]
    assert (tmp_path / "briefs/enterprise-fit.md").read_text() == "K1 K2 I1 all assessed"


def test_fit_feeds_in_the_design_and_client_standards(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "fit.md").write_text("FIT")
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/target-architecture.md").write_text("K1")
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.fit([str(doc)])
    assert "target-architecture.md" in prompts[0] and str(doc) in prompts[0]


def test_fit_template_covers_step_6_outputs():
    text = " ".join((pathlib.Path(agent.__file__).parent / "fit.md").read_text().lower().split())  # ignore line wraps
    for needed in ("approved platforms", "security policy", "data residency", "regulatory", "accessibility",
                   "existing contracts", "exceptions", "compliance questions", "risks", "items for human review",
                   "one row for every design component", "commonly expected, not stated by client",
                   "do not give legal conclusions", "never round up", "never invent"):
        assert needed in text, needed


def test_delivery_repairs_when_an_exception_is_unhandled(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "delivery.md").write_text("DEL")
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/enterprise-fit.md").write_text("E1 E2 E3")
    replies = iter(["E1 and E3 handled", "E1 E2 E3 handled"])
    monkeypatch.setattr(agent, "ask", lambda a, p: prompts.append(p) or next(replies))
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.delivery([str(doc)])
    assert len(prompts) == 2 and "E2" in prompts[1] and "exceptions and fit items" in prompts[1]
    assert (tmp_path / "briefs/delivery-approach.md").read_text() == "E1 E2 E3 handled"


def test_delivery_feeds_in_the_fit_assessment(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "delivery.md").write_text("DEL")
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/enterprise-fit.md").write_text("E1")
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.delivery([str(doc)])
    assert "enterprise-fit.md" in prompts[0]


def test_every_checked_step_exists_in_steps():
    assert set(agent.CHECKS) <= set(agent.STEPS)


def test_delivery_template_covers_step_7_outputs():
    text = " ".join((pathlib.Path(agent.__file__).parent / "delivery.md").read_text().lower().split())
    for needed in ("phases", "roadmap", "dependency map", "migration and transition approach", "prerequisites",
                   "client responsibilities", "decision points", "likely delivery roles",
                   "responsibility assumptions", "delivery risks", "one row for every exception",
                   "do not invent dates, prices or headcounts", "t0", "estimate", "proposed", "never invent",
                   "no phasing can meet a deadline", "notice periods"):
        assert needed in text, needed


def test_step_with_no_files_and_no_earlier_briefs_exits(tmp_path, monkeypatch):
    import pytest
    _setup(tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as e:
        agent.run_step("qualify", [])
    assert "nothing to read" in str(e.value)


def test_later_step_runs_from_earlier_briefs_alone(tmp_path, monkeypatch):
    _, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "delivery.md").write_text("DEL")
    (tmp_path / "briefs").mkdir()
    for f in agent.STEPS["delivery"][3]:
        (tmp_path / "briefs" / f).write_text("E1")
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.run_step("delivery", [])  # no source files given
    assert "enterprise-fit.md" in prompts[0]


def test_economics_repairs_when_a_phase_has_no_estimate(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "economics.md").write_text("ECO")
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/delivery-approach.md").write_text("P0 P1 P2")
    replies = iter(["P0 and P2 estimated", "P0 P1 P2 estimated"])
    monkeypatch.setattr(agent, "ask", lambda a, p: prompts.append(p) or next(replies))
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.economics([str(doc)])
    assert len(prompts) == 2 and "P1" in prompts[1] and "effort estimate table" in prompts[1]
    assert (tmp_path / "briefs/rom-estimate.md").read_text() == "P0 P1 P2 estimated"


def test_economics_feeds_in_the_delivery_approach_and_commercial_docs(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "economics.md").write_text("ECO")
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/delivery-approach.md").write_text("P0")
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.economics([str(doc)])
    assert "delivery-approach.md" in prompts[0] and str(doc) in prompts[0]


def test_economics_template_separates_confirmed_from_estimates():
    text = " ".join((pathlib.Path(agent.__file__).parent / "economics.md").read_text().lower().split())
    for needed in ("rom, not a quote", "confirmed =", "calculated =", "estimate =", "not stated =",
                   "never invent prices, rates, volumes or headcounts", "do not convert between currencies",
                   "expired, indicative, or not a quote is not confirmed", "high >= likely >= low",
                   "savings are never counted in the totals", "one row for every phase",
                   "licensing and subscription", "cloud and service usage factors", "potential savings",
                   "confidence", "exclusions", "validation needs", "sensitivity"):
        assert needed in text, needed


def test_sample_commercial_inputs_contain_the_traps():
    s = (pathlib.Path(agent.__file__).parent / "samples/commercial-inputs.md").read_text()
    assert "valid until 31 August 2026" in s and "GBP" in s and "USD" in s and "not a quote" in s
