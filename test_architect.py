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
    monkeypatch.setattr(agent, "PROMPTS", tmp_path)
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
    monkeypatch.setattr(agent, "PROMPTS", tmp_path)
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
    monkeypatch.setattr(agent, "PROMPTS", tmp_path)
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
    real = agent.PROMPTS
    for t in ("qualify.md", "discover.md"):
        text = (real / t).read_text().lower()
        assert "never invent" in text and ("not stated" in text or "proposed" in text)


def test_every_step_has_template_and_ordered_inputs():
    """Guards the 11-step table: templates exist, and each step only reads outputs earlier steps produce."""
    produced = set()
    for name, (template, out, reviewer, prior) in agent.STEPS.items():
        assert (agent.PROMPTS / template).is_file(), name
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
    text = (agent.PROMPTS / "assess.md").read_text()
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
    text = (agent.PROMPTS / "options.md").read_text().lower()
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
    text = (agent.PROMPTS / "design.md").read_text().lower()
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
    text = " ".join((agent.PROMPTS / "fit.md").read_text().lower().split())  # ignore line wraps
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
    text = " ".join((agent.PROMPTS / "delivery.md").read_text().lower().split())
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
    text = " ".join((agent.PROMPTS / "economics.md").read_text().lower().split())
    for needed in ("rom, not a quote", "confirmed =", "calculated =", "estimate =", "not stated =",
                   "never invent prices, rates, volumes or headcounts", "do not convert between currencies",
                   "expired, indicative, or not a quote is not confirmed", "high >= likely >= low",
                   "savings are never counted in the totals", "one row for every phase",
                   "licensing and subscription", "cloud and service usage factors", "potential savings",
                   "confidence", "exclusions", "validation needs", "sensitivity"):
        assert needed in text, needed


def test_sample_commercial_inputs_contain_the_traps():
    s = (agent.PROMPTS / "samples/commercial-inputs.md").read_text()
    assert "valid until 31 August 2026" in s and "GBP" in s and "USD" in s and "not a quote" in s


def test_proposal_repairs_when_a_requirement_has_no_response(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "proposal.md").write_text("PROP")
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/requirements.md").write_text("R-001 R-002 R-003")
    replies = iter(["R-001 R-003 answered", "R-001 R-002 R-003 answered"])
    monkeypatch.setattr(agent, "ask", lambda a, p: prompts.append(p) or next(replies))
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.proposal([str(doc)])
    assert len(prompts) == 2 and "R-002" in prompts[1] and "response to RFP requirements" in prompts[1]
    assert (tmp_path / "briefs/proposal-package.md").read_text() == "R-001 R-002 R-003 answered"


def test_proposal_feeds_in_the_rom_and_bidder_documents(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "proposal.md").write_text("PROP")
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/rom-estimate.md").write_text("x")
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.proposal([str(doc)])
    assert "rom-estimate.md" in prompts[0] and str(doc) in prompts[0]


def test_proposal_template_enforces_evidence_honesty_and_no_leaks():
    text = " ".join((agent.PROMPTS / "proposal.md").read_text().lower().split())
    for needed in ("[confirm", "evidenced", "never invent credentials", "do not claim a certification",
                   "reference whose approval is pending", "unsupported superlatives",
                   "must never be answered \"full\"", "internal rate card", "[confirm: pricing approval]",
                   "rom estimates are internal", "reviewer summary (internal, remove before sending)",
                   "one row for every requirement id", "evidence register", "evaluation criteria",
                   "executive summary", "solution narrative", "differentiators", "mermaid"):
        assert needed in text, needed


def test_proposal_reviewer_summary_comes_first():
    text = (agent.PROMPTS / "proposal.md").read_text()
    assert text.index("## Reviewer summary") < text.index("## 1. Executive summary") < text.index("## Evidence register")


def test_bidder_profile_sample_contains_the_traps():
    s = (agent.PROMPTS / "samples/bidder-profile.md").read_text()
    assert "SOC 2 Type II: not held" in s and "approval pending" in s and "no supporting evidence" in s


def test_discuss_repairs_when_a_decision_point_is_missing(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "discuss.md").write_text("DISC")
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/delivery-approach.md").write_text("D1 D2 D3")
    replies = iter(["D1 D3 covered", "D1 D2 D3 covered"])
    monkeypatch.setattr(agent, "ask", lambda a, p: prompts.append(p) or next(replies))
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.discuss([str(doc)])
    assert len(prompts) == 2 and "D2" in prompts[1] and "decisions we need" in prompts[1]
    assert (tmp_path / "briefs/discussion-pack.md").read_text() == "D1 D2 D3 covered"


def test_record_repairs_when_a_decision_point_has_no_outcome(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "record.md").write_text("REC")
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/discussion-pack.md").write_text("D1 D2")
    replies = iter(["D1 decided", "D1 decided, D2 deferred"])
    monkeypatch.setattr(agent, "ask", lambda a, p: prompts.append(p) or next(replies))
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.record([str(doc)])
    assert len(prompts) == 2 and "D2" in prompts[1] and "decision log" in prompts[1]
    assert (tmp_path / "briefs/opportunity-record.md").read_text() == "D1 decided, D2 deferred"


def test_record_carries_forward_its_previous_version(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "record.md").write_text("REC")
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/opportunity-record.md").write_text("meeting 1: M1 decided")
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.record([str(doc)])
    assert "opportunity-record.md" in prompts[0]  # previous record is read first, so decisions accumulate


def test_other_steps_do_not_read_their_previous_output(tmp_path, monkeypatch):
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "briefs").mkdir()
    (tmp_path / "briefs/opportunity-brief.md").write_text("old")
    monkeypatch.setattr(agent, "approve", lambda who: True)
    agent.qualify([str(doc)])
    assert "opportunity-brief.md" not in prompts[0]


def test_discuss_template_labels_sections_and_blocks_leaks():
    text = " ".join((agent.PROMPTS / "discuss.md").read_text().lower().split())
    for needed in ("[client-shareable]", "[internal]", "internal rate card", "rom figures", "pending references",
                   "never invent", "[confirm", "bluffing", "never promise what the analysis says cannot be met",
                   "presentation flow", "discovery questions", "architecture walkthrough", "option comparison",
                   "anticipated objections", "one row for every decision point", "capture plan",
                   "pre-meeting checklist", "sensitive topics"):
        assert needed in text, needed


def test_record_template_distinguishes_firmness_and_never_rewrites_briefs():
    text = " ".join((agent.PROMPTS / "record.md").read_text().lower().split())
    for needed in ("explicit", "implied", "verbal-unconfirmed", "never treated as confirmed",
                   "do not silently rewrite the earlier briefs", "re-run", "one row for every decision point",
                   "follow-ups", "owner", "decision history", "impact on earlier artifacts",
                   "carry forward every decision", "never invent"):
        assert needed in text, needed


def test_meeting_notes_sample_contains_the_traps():
    s = (agent.PROMPTS / "samples/client-meeting-notes.md").read_text()
    assert "Not confirmed by Finance" in s and "No date given" in s and "nobody in the room knew" in s
    assert "stretch goal" in s and "No decision" in s


def test_every_section_in_the_discuss_template_is_labelled():
    import re
    text = (agent.PROMPTS / "discuss.md").read_text()
    headings = re.findall(r"(?m)^## (.+)$", text)
    assert len(headings) == 11
    assert [h for h in headings if "[CLIENT-SHAREABLE]" not in h and "[INTERNAL]" not in h] == []


def test_approving_a_step_writes_the_ledger_and_a_rejection_does_not(tmp_path, monkeypatch):
    import json
    doc, _ = _setup(tmp_path, monkeypatch)
    answers = iter([False, True])
    monkeypatch.setattr(agent, "approve", lambda who: next(answers))
    monkeypatch.setattr("builtins.input", lambda _: "tighten it")
    agent.qualify([str(doc)])
    lines = (tmp_path / "briefs/approvals.log").read_text().splitlines()
    assert len(lines) == 1  # two drafts, one approval
    rec = json.loads(lines[0])
    assert rec["step"] == "qualify" and rec["file"] == "opportunity-brief.md" and len(rec["sha256"]) == 64


def _approved_pipeline(tmp_path, monkeypatch):
    """Every step's output exists and is approved, in order, as after a clean run of steps 1-10."""
    from architect import baseline
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "handoff.md").write_text("HANDOFF")
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    for step, (_, out, _, _) in agent.STEPS.items():
        if step != "handoff":
            (briefs / out).write_text("R-001 F1 content")
            baseline.log_approval(briefs, step, briefs / out, "reviewer")
    monkeypatch.setattr(agent, "approve", lambda who: True)
    return doc, prompts


def test_handoff_refuses_when_nothing_is_approved(tmp_path, monkeypatch):
    import pytest
    doc, prompts = _setup(tmp_path, monkeypatch)
    (tmp_path / "handoff.md").write_text("HANDOFF")
    with pytest.raises(SystemExit) as e:
        agent.handoff([])
    assert "Cannot hand off yet" in str(e.value) and "not produced" in str(e.value)
    assert prompts == []  # the model is never called on unapproved material


def test_handoff_refuses_when_an_artifact_was_edited_after_approval(tmp_path, monkeypatch):
    import pytest
    doc, prompts = _approved_pipeline(tmp_path, monkeypatch)
    (tmp_path / "briefs/requirements.md").write_text("R-001 edited behind the reviewer's back")
    with pytest.raises(SystemExit) as e:
        agent.handoff([])
    assert "requirements.md: edited after it was approved" in str(e.value) and prompts == []


def test_handoff_refuses_when_an_earlier_step_was_rerun_and_approved_later(tmp_path, monkeypatch):
    import pytest
    from architect import baseline
    doc, prompts = _approved_pipeline(tmp_path, monkeypatch)
    (tmp_path / "briefs/requirements.md").write_text("R-001 revised after the meeting")
    baseline.log_approval(tmp_path / "briefs", "discover", tmp_path / "briefs/requirements.md", "reviewer")
    with pytest.raises(SystemExit) as e:
        agent.handoff([])
    msg = str(e.value)
    assert "current-state.md: stale, requirements.md was re-approved" in msg and "re-run `assess`" in msg


def test_handoff_publishes_v1_then_v2_with_the_previous_baseline_fed_in(tmp_path, monkeypatch):
    import json
    doc, prompts = _approved_pipeline(tmp_path, monkeypatch)
    monkeypatch.setattr(agent, "ask", lambda a, p: prompts.append(p) or "baseline text covering R-001 and F1")
    agent.handoff([str(doc)])
    v1 = tmp_path / "baseline/v1"
    assert (v1 / "solution-baseline.md").read_text() == "baseline text covering R-001 and F1"
    assert json.loads((v1 / "manifest.json").read_text())["version"] == 1
    assert "version v1" in prompts[0] and "previous baseline" not in prompts[0]
    # the handoff itself was approved, so the second run is consistent and publishes v2
    agent.handoff([str(doc)])
    assert (tmp_path / "baseline/v2/manifest.json").exists()
    assert "version v2" in prompts[1] and "previous baseline is solution-baseline.md in v1" in prompts[1]
    assert str(tmp_path / "baseline/v1/solution-baseline.md") in prompts[1]


def test_handoff_repairs_a_missing_requirement_or_follow_up(tmp_path, monkeypatch):
    doc, prompts = _approved_pipeline(tmp_path, monkeypatch)
    (tmp_path / "briefs/requirements.md").write_text("R-001 R-002")
    (tmp_path / "briefs/opportunity-record.md").write_text("F1 F2")
    from architect import baseline
    for step, f in (("discover", "requirements.md"), ("record", "opportunity-record.md")):
        baseline.log_approval(tmp_path / "briefs", step, tmp_path / "briefs" / f, "reviewer")
    # re-approve the dependants in order so the set is consistent again
    for step, (_, out, _, _) in agent.STEPS.items():
        if step not in ("handoff", "qualify", "discover", "record"):
            baseline.log_approval(tmp_path / "briefs", step, tmp_path / "briefs" / out, "reviewer")
    baseline.log_approval(tmp_path / "briefs", "record", tmp_path / "briefs/opportunity-record.md", "reviewer")
    replies = iter(["covers R-001 and F1 only", "covers R-001 R-002 F1 F2"])
    monkeypatch.setattr(agent, "ask", lambda a, p: prompts.append(p) or next(replies))
    agent.handoff([])
    assert len(prompts) == 2 and "R-002" in prompts[1] and "F2" in prompts[1]
    assert (tmp_path / "baseline/v1/solution-baseline.md").read_text() == "covers R-001 R-002 F1 F2"


def test_handoff_template_enforces_firm_vs_soft_and_known_deltas():
    text = " ".join((agent.PROMPTS / "handoff.md").read_text().lower().split())
    for needed in ("never invent or change a requirement", "keep ids unchanged", "explicit in the opportunity record",
                   "verbal-unconfirmed", "known deltas", "does not build from outdated content",
                   "estimates stay estimates", "internal-only commercial material", "baseline identity",
                   "reading guide", "requirements baseline", "architecture baseline", "assumptions register",
                   "dependencies", "risks", "client commitments and follow-ups", "validation checklist",
                   "change control", "traceability index", "one row for every requirement id",
                   "one row for every follow-up id", "what changed since the previous version"):
        assert needed in text, needed


def test_handoff_row_reads_every_other_output_and_is_the_last_step():
    names = list(agent.STEPS)
    assert names[-1] == "handoff"
    others = {o for k, (_, o, _, _) in agent.STEPS.items() if k != "handoff"}
    assert set(agent.STEPS["handoff"][3]) == others
