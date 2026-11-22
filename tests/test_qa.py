"""The QA agent (qa/agent.py): ten steps, the model replaced by canned replies. What matters: facts come from code, QA edits test files only,
nothing is approved by the model, and the recommendation is never a release decision."""
import pathlib
import subprocess

import pytest

import core
from coder import agent as C
from qa import agent as Q

TICKET = "# T-1\nAC1: add returns the sum.\nAC2: add rejects non-numbers.\n"
TABLE = lambda h, rows: "| " + " | ".join(h) + " |\n|" + "---|" * len(h) + "\n" + "\n".join("| " + " | ".join(r) + " |" for r in rows) + "\n"
DOCS = {
    "STEP 1": "## Status\nDraft.\n## Requirements-to-test map\n" + TABLE(["AC", "Criterion", "Testable?"], [["AC1", "sum", "yes"], ["AC2", "reject", "yes"]])
              + "## Open questions\nNone.\n## In scope\nadd\n## Out of scope\nUI\n",
    "STEP 2": "## Status\nDraft.\n## Risk assessment\n" + TABLE(["Risk", "AC", "Priority"], [["wrong sum", "AC1", "High"], ["bad input", "AC2", "Medium"]]),
    "STEP 3": "## Status\nDraft.\n## Test approach\n" + TABLE(["AC", "Level"], [["AC1", "unit"], ["AC2", "unit"]]) + "## Coverage gaps\nNone.\n",
    "STEP 4": "## Status\nDraft.\n## Test cases\n" + TABLE(["ID", "AC", "Kind", "Preconditions", "Steps", "Expected", "Data"],
              [["TC1", "AC1", "positive", "-", "add(1,2)", "3", "1,2"], ["TC2", "AC1", "boundary", "-", "add(0,0)", "0", "0,0"],
               ["TC3", "AC2", "positive", "-", "add(1,2)", "ok", "1,2"], ["TC4", "AC2", "negative", "-", "add('a',1)", "TypeError", "a,1"]])
              + "## Test data\nInvented numbers only.\n",
    "STEP 5": "## Status\nDraft.\n## Test case to automated test\n" + TABLE(["TC", "Test"], [[f"TC{i}", f"tests/test_qa.py::t{i}"] for i in (1, 2, 3, 4)]),
    "STEP 7": "## Status\nDraft.\n## Exploratory findings\n" + TABLE(["ID", "Finding"], [["E1", "see `src/app.py`"]]) + "## Regression assessment\n" + TABLE(["Area", "Gap"], [["`src/app.py`", "none"]]),
    "STEP 8": "## Status\nDraft.\n## Non-functional quality\n" + TABLE(["Dimension", "Threshold", "Status"],
              [[d, "Not stated", "Gap" if d == "Performance" else "Not applicable"] for d in Q.DIMENSIONS]),
    "STEP 9": "## Status\nDraft.\n## Failing checks\n" + TABLE(["X", "Class"], [["X1", "product defect"]]) + "## Defects\n"
              + TABLE(["ID", "Title", "Severity", "Status"], [["DEF1", "bad sum", "High", "Open"]]) + "## Re-test\nNo fix provided yet\n",
}


@pytest.fixture
def qa(tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "HERE", tmp_path / "qa")
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src/app.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "tests/test_app.py").write_text("def test_x():\n    pass\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@x.invalid", "commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(repo), *c], check=True, capture_output=True)
    t = tmp_path / "ticket.md"
    t.write_text(TICKET)
    calls = []

    def ask(agent, prompt):
        calls.append((agent, prompt))
        for k, v in DOCS.items():
            if prompt.startswith("RULES") and f"{k}:" in prompt:
                if k == "STEP 5":
                    (repo / "tests/test_qa.py").write_text("def t1():\n    pass\n")
                    (repo / "src/app.py").write_text("def add(a, b):\n    return 0\n")  # a QA edit to application code
                return v
        return DOCS.get(next((k for k in DOCS if k in prompt), ""), "## Status\nDraft.\n")
    monkeypatch.setattr(Q, "ask", ask)
    monkeypatch.setattr(C, "approve", lambda who: True)
    monkeypatch.setattr(Q, "approve", lambda who: True)
    return dict(repo=repo, ticket=t, calls=calls, briefs=tmp_path / "qa/briefs")


def test_the_ten_steps_form_one_chain_and_only_two_need_no_model():
    assert list(Q.STEPS) == ["scope", "risk", "coverage", "design", "automate", "execute", "explore", "nonfunctional", "defects", "recommend"]
    assert [s for s, v in Q.STEPS.items() if v[0] == "-"] == ["execute", "recommend"]
    assert all((Q.PROMPTS / v[0]).exists() for v in Q.STEPS.values() if v[0] != "-")


def test_a_step_waits_for_the_approved_step_before_it(qa):
    with pytest.raises(SystemExit, match="Cannot risk yet"):
        Q.run_step("risk", [])


def test_scope_must_map_every_acceptance_criterion_and_repairs_once(qa, monkeypatch):
    replies = iter(["## Requirements-to-test map\n| AC1 | x |\n## Open questions\n.\n## In scope\n.\n## Out of scope\n.\n", DOCS["STEP 1"]])
    monkeypatch.setattr(Q, "ask", lambda a, p: next(replies))
    Q.run_step("scope", [str(qa["ticket"])])
    assert "AC2" in (qa["briefs"] / "test-scope.md").read_text()


def test_design_needs_a_negative_or_boundary_case_for_every_criterion(qa):
    Q.run_step("scope", [str(qa["ticket"])])
    only_positive = DOCS["STEP 4"].replace("boundary", "positive").replace("negative", "positive")
    assert "no negative, boundary or failure case" in Q.check_design(qa["briefs"], only_positive, None)
    assert Q.check_design(qa["briefs"], DOCS["STEP 4"], None) == ""


def test_the_whole_chain_with_a_failing_check_gives_not_ready_and_no_release_decision(qa):
    r, t = str(qa["repo"]), str(qa["ticket"])
    Q.run_step("scope", [t], r)
    for s in ("risk", "coverage", "design"):
        Q.run_step(s, [], r)
    Q.run_automate(r)
    rep = (qa["briefs"] / "automation-report.md").read_text()
    assert "`tests/test_qa.py`" in rep and "Application edits reverted" in rep and "src/app.py" in rep.split("## Application edits reverted")[1].split("##")[0]
    assert (qa["repo"] / "src/app.py").read_text() == "def add(a, b):\n    return a + b\n"  # the application edit was undone
    Q.run_execute(r, ["python3 -c 'import sys; sys.exit(0)'", "python3 -c 'import sys; sys.exit(1)'"])
    ex = (qa["briefs"] / "execution-report.md").read_text()
    assert "Passed: 1. Failed: 1." in ex and "| X1 `python3" in ex and "FAIL" in ex
    for s in ("explore", "nonfunctional", "defects"):
        Q.run_step(s, [], r)
    Q.run_recommend()
    rec = (qa["briefs"] / "qa-recommendation.md").read_text()
    assert "Not ready for the release decision" in rec and "1 check(s) failed" in rec and "DEF1" in rec
    assert "a person does" in rec and not Q.RELEASE_CLAIM.search(rec)
    assert "Non-functional gap: Performance" in rec


def test_defects_must_classify_every_failing_check(qa):
    (qa["briefs"]).mkdir(parents=True)
    (qa["briefs"] / "execution-report.md").write_text("## Results\n| X1 `a` | FAIL |\n| X2 `b` | FAIL |\n")
    assert "missing: X1, X2" in Q.check_defects(qa["briefs"], "## Defects\n## Failing checks\nnone\n## Re-test\n.\n", None)


def test_every_defect_needs_a_severity_and_nonfunctional_dimension_a_status():
    assert "Give a severity" in Q.check_defects(pathlib.Path("/nonexistent"), "## Defects\n| ID | T |\n|---|---|\n| DEF1 | x |\n## Failing checks\n.\n## Re-test\n.\n", None)
    assert "missing: Accessibility, Security" in Q.check_nonfunctional(None, "## Non-functional quality\n| Performance | Not stated | - | Gap |\n", None)


def test_a_model_claiming_release_is_sent_back(qa, monkeypatch):
    replies = iter([DOCS["STEP 1"] + "\nApproved for release.\n", DOCS["STEP 1"]])
    seen = []
    monkeypatch.setattr(Q, "ask", lambda a, p: (seen.append(p), next(replies))[1])
    Q.run_step("scope", [str(qa["ticket"])])
    assert any("release" in p.lower() and "only a person" in p for p in seen)
    assert "Approved for release" not in (qa["briefs"] / "test-scope.md").read_text()


def test_the_recommendation_is_ready_only_with_a_pass_and_no_open_high_defects(tmp_path):
    b = tmp_path
    (b / "execution-report.md").write_text("## Results\nPassed: 3. Failed: 0. Blocked: 0. Not run: 0.\n")
    (b / "defect-report.md").write_text("## Defects\n| ID | Title | Severity | Status |\n|---|---|---|---|\n| DEF1 | x | High | Closed |\n")
    assert "Ready for the designated human release decision" in Q.recommendation(b)
    (b / "defect-report.md").write_text("## Defects\n| ID | Title | Severity | Status |\n|---|---|---|---|\n| DEF1 | x | High | Open |\n")
    assert "Not ready" in Q.recommendation(b)
    (b / "execution-report.md").write_text("## Results\nPassed: 0. Failed: 0. Blocked: 1. Not run: 2.\n")
    (b / "defect-report.md").write_text("## Defects\n")
    assert "no passing evidence" in Q.recommendation(b)
