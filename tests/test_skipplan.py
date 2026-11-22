"""The skip plan: rules suggest, a person confirms (name and reason), code writes a placeholder and the ledger records who skipped it and why."""
import json
import subprocess

import pytest

import skipplan
from architect import agent as A, baseline
from qa import agent as Q
from test_web import web, new, view, step, run, awaiting, app, wait  # noqa: F401

THIN = "A meeting assistant. " * 10
RICH = "Our current system is a legacy CRM. Budget is 50k, 2000 users. " * 80


def test_architect_rules_follow_the_size_and_content_of_the_input():
    thin = dict(src=THIN, meetings=0)
    assert "10 words" not in skipplan.suggest("architect", "assess", thin) and "only" in skipplan.suggest("architect", "assess", thin)
    assert all(skipplan.suggest("architect", s, thin) for s in ("assess", "economics", "discuss", "record"))
    rich = dict(src=RICH, meetings=1)
    assert not any(skipplan.suggest("architect", s, rich) for s in ("assess", "economics", "discuss", "record"))
    assert skipplan.suggest("architect", "assess", dict(src="legacy " + THIN, meetings=0)) == ""   # thin, but a current environment is described
    assert skipplan.suggest("architect", "economics", dict(src="budget 5k " + THIN, meetings=0)) == ""  # thin, but money is mentioned
    assert skipplan.suggest("architect", "record", dict(src=RICH, meetings=0)) and not skipplan.suggest("architect", "qualify", thin)


def test_coder_and_qa_rules():
    assert "python" in skipplan.suggest("coder", "detect", dict(stacks=["python"], gaps=[], unsupported=[]))
    for bad in (dict(stacks=["python", "node"], gaps=[], unsupported=[]), dict(stacks=["python"], gaps=[1], unsupported=[]), dict(stacks=["python"], gaps=[], unsupported=[1])):
        assert skipplan.suggest("coder", "detect", bad) == ""
    assert skipplan.suggest("qa", "nonfunctional", dict(scope="only functional rules")) and not skipplan.suggest("qa", "nonfunctional", dict(scope="must meet latency targets"))
    assert not skipplan.suggest("qa", "nonfunctional", dict(scope=None))      # no scope yet: no suggestion
    assert skipplan.suggest("qa", "explore", dict(changed=(2, 80), high=False))
    assert not skipplan.suggest("qa", "explore", dict(changed=(3, 10), high=False)) and not skipplan.suggest("qa", "explore", dict(changed=(1, 10), high=True))


def test_a_skipped_step_satisfies_the_ledger_but_an_edited_placeholder_does_not(tmp_path):
    out = tmp_path / "current-state.md"
    out.write_text(skipplan.placeholder("assess", "Priya N", "no environment given", "", "2026-11-22"))
    baseline.log_skip(tmp_path, "assess", out, "Priya N", "no environment given")
    step_ = {"assess": (None, "current-state.md", [A.ARCH], [])}
    assert baseline.problems(tmp_path, step_) == [] and baseline.skipped(tmp_path, "current-state.md")["reviewer"] == "SKIPPED by Priya N"
    out.write_text(out.read_text() + "tampered")
    assert baseline.skipped(tmp_path, "current-state.md") is None and "edited after it was approved" in baseline.problems(tmp_path, step_)[0]


def prepare(web, tmp_path, desc=THIN):
    pid = new(web, desc=desc * 2)
    b = tmp_path / "projects" / pid / "architect/briefs"
    for st, f, who in (("qualify", "opportunity-brief.md", [A.ACCOUNT]), ("discover", "requirements.md", [A.ACCOUNT, A.ARCH])):
        (b / f).write_text("x")
        for r in who:
            baseline.log_approval(b, st, b / f, r)
    return pid, b


def test_the_page_suggests_then_a_person_skips_and_the_chain_moves_on(web, tmp_path):
    pid, b = prepare(web, tmp_path)
    s = step(view(web, pid), "architect", "assess")
    assert s["skippable"] and s["ready"] and "only" in s["suggest"] and not step(view(web, pid), "architect", "qualify")["skippable"]
    url = f"/api/projects/{pid}/skip"
    assert web("POST", url, dict(agent="architect", step="assess", name="P", reason="no environment given"), token=False)[0] == 403
    for bad in (dict(agent="architect", step="qualify", name="Priya", reason="not allowed to skip this"), dict(agent="architect", step="assess", name="", reason="long enough reason"),
                dict(agent="architect", step="assess", name="Priya", reason="short")):
        assert web("POST", url, bad)[0] == 400
    assert web("POST", url, dict(agent="architect", step="economics", name="Priya", reason="skipping early"))[0] == 400  # earlier step not approved
    assert web("POST", url, dict(agent="architect", step="assess", name="Priya N", reason="no current environment was given"))[1] == {"skipped": "assess"}
    v = view(web, pid)
    s = step(v, "architect", "assess")
    assert s["status"] == "skipped" and s["text"].startswith("Skipped by Priya N: no current environment") and v["tracks"]["architect"]["skipped"] == 1
    assert v["tracks"]["architect"]["next"] == "options" and "Skipped by: Priya N" in (b / "current-state.md").read_text()
    rec = json.loads((b / "approvals.log").read_text().splitlines()[-1])
    assert rec["skipped"] and rec["step"] == "assess" and rec["reviewer"] == "SKIPPED by Priya N"


def test_a_rich_input_gets_no_suggestion_and_a_skipped_step_can_be_run_again(web, tmp_path):
    pid, b = prepare(web, tmp_path, desc=RICH)
    s = step(view(web, pid), "architect", "assess")
    assert s["skippable"] and s["suggest"] == ""                      # still allowed by the person, but not suggested
    web("POST", f"/api/projects/{pid}/skip", dict(agent="architect", step="assess", name="Priya N", reason="the client said skip the assessment"))
    assert step(view(web, pid), "architect", "assess")["status"] == "skipped"
    assert run(web, pid, step_="assess")[0] == 200                      # running it replaces the placeholder with a real draft
    awaiting(web, pid)
    assert step(view(web, pid), "architect", "assess")["status"] == "needs_you"
    assert "Skipped." not in (b / "current-state.md").read_text()


def test_run_all_pauses_before_a_step_that_may_not_be_needed(web, tmp_path, monkeypatch):
    pid, b = prepare(web, tmp_path)
    (b / "current-state.md").write_text("x")  # pretend assess is done by the fake agent below: approve it, then 'options' follows
    baseline.log_approval(b, "assess", b / "current-state.md", A.ARCH)
    run(web, pid, auto=False, step_="options")
    awaiting(web, pid)
    web("POST", f"/api/projects/{pid}/respond", dict(answer="y"))
    awaiting(web, pid)
    web("POST", f"/api/projects/{pid}/respond", dict(answer="y"))
    wait(lambda: view(web, pid)["run"]["state"] == "done")
    # an auto run would now continue to design, fit, delivery; 'economics' is the first with a suggestion
    assert step(view(web, pid), "architect", "economics")["status"] == "todo"


def test_the_qa_recommendation_says_what_was_skipped(tmp_path):
    (tmp_path / "execution-report.md").write_text("## Results\nPassed: 3. Failed: 0. Flaky: 0. Blocked: 0. Not run: 0.\n")
    (tmp_path / "defect-report.md").write_text("## Defects\n")
    (tmp_path / "nonfunctional-report.md").write_text(skipplan.placeholder("nonfunctional", "Priya N", "no NFR was stated", "rule", "2026-11-22"))
    rec = Q.recommendation(tmp_path)
    assert "nonfunctional-report.md was SKIPPED (not assessed)" in rec and "Priya N" in rec and "no NFR was stated" in rec and "No non-functional gap recorded" not in rec
