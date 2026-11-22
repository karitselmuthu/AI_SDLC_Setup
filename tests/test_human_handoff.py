"""Coding agent step 9, human handoff. No model is involved in this step, so the tests check the package against the real
records and git: what it contains, that it is built from the approved chain only, that it never claims approval, and that a
reviewer's decision can only be recorded by a person at a terminal."""
import json

import pytest

import core
from architect import baseline
from coder import agent, handoff

import test_handoff as TH
from test_handoff import repo  # noqa: F401  (the fixture: a work repository on the step 5 branch)

COVERAGE = ("## Stack coverage (from the code; a check is only PASS or FAIL if it was run)\n\n### Detected stack\n| Stack | Area | Evidence | Convention files |\n|---|---|---|---|\n"
            "| Python | Backend services | app.py | pytest.ini |\n\n### Checks selected (2), run (1), not run (1)\n| Stack | Kind | Command | Outcome |\n|---|---|---|---|\n"
            "| Python | unit or component tests | `pytest -q` | PASS (exit 0) |\n| Python | lint or static analysis | `ruff check .` | Not run: `ruff` is not installed here |\n\n"
            "### Gaps (an expected kind of check the repository has no way to run)\n| Stack | Kind | Reason |\n|---|---|---|\n| Python | build or compile | no build or compile is configured or detectable for this stack |\n\n"
            "### Unsupported technologies\n- Elixir (1 files): no adapter for this language\n\n")
TESTS = TH.TESTS.replace("## Results before", COVERAGE + "## Results before", 1)


def chain(tmp_path, monkeypatch, repo, tests=TESTS, pr_reply=TH.PR_GOOD, review=None, plan=TH.PLAN):
    """Run the real steps 7 and 8 with a fake model on top of an approved chain of earlier outputs."""
    def model(prompt):
        if "REVIEW THE CHANGE" in prompt:
            return (review or TH.review_reply)(prompt)
        return pr_reply
    TH._env(tmp_path, monkeypatch, model, tests=tests, signed=(), plan=plan)
    b = tmp_path / "briefs"
    (b / "repository-inspection.md").write_text("## Status\nDraft\n")
    (b / "stack-profile.md").write_text("## Status\nDraft\n")
    for step, f in (("understand", "implementation-plan.md"), ("inspect", "repository-inspection.md"), ("detect", "stack-profile.md"),
                    ("plan", "change-plan.md"), ("implement", "implementation-report.md"), ("tests", "test-report.md")):
        for role in agent.STEPS[step][2]:
            baseline.log_approval(b, step, b / f, role)
    agent.review([], str(repo))
    agent.pr([], str(repo))
    return b


def fail_if_model_called(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the handoff step must not call a model")
    monkeypatch.setattr(agent, "ask", boom)
    monkeypatch.setattr(core, "ask", boom)


def package(tmp_path):
    return (tmp_path / "briefs/handoff-package.md").read_text()


def test_the_package_has_everything_the_reviewer_needs_and_comes_from_the_records(tmp_path, monkeypatch, repo):
    chain(tmp_path, monkeypatch, repo)
    fail_if_model_called(monkeypatch)
    agent.run_handoff(repo, decide=False)
    p = package(tmp_path)
    assert p.startswith("# Human handoff: List the agent steps\n")
    # the ticket
    assert "## 1. Ticket\n**TICKET-142** (https://tracker.example/TICKET-142)" in p
    # the implementation plan, with its planned changes
    assert "## 2. Implementation plan" in p and "| C1 | first |" in p and "| C2 | second |" in p and "| S1 | x | AC1, AC2 |" in p
    # changed files from git
    files = p.split("## 3. Changed files (from git)")[1].split("## 4.")[0]
    assert "| `src/app.py` | production | 1 | 1 |" in files and "| `src/out.py` | production | 1 | 0 |" in files and "| `tests/test_app.py` | test | 1 | 0 |" in files
    # acceptance criteria mapping
    assert "| AC1 | C1 | `src/app.py` | t | Met |" in p and "**Criteria not fully met:**\nNone recorded." in p
    # tests run and results
    t = p.split("## 5. Tests run and results")[1].split("## 6.")[0]
    assert "**All 1 local checks passed.**" in t and "| `pytest -q` | PASS (exit 0) | 1.2 |" in t and "not independent QA sign-off" in t
    # checks not run, with the reason
    c = p.split("## 6. Checks not run and coverage gaps")[1].split("## 7.")[0]
    assert "- lint or static analysis `ruff check .`: Not run: `ruff` is not installed here" in c
    assert "- Python, build or compile: no build or compile is configured" in c and "- Elixir (1 files): no adapter for this language" in c
    assert "CI, independent QA" in c  # what no agent check covers is said, never claimed
    # known risks
    r = p.split("## 7. Known risks and open items")[1].split("## 8.")[0]
    assert "Low." in r and "Self-review only; nothing was run." in r and "Q1: is 4 the right limit? Priya." in r and "None. Searched for stored data." in r


def test_the_package_never_claims_approval_and_says_who_decides(tmp_path, monkeypatch, repo):
    chain(tmp_path, monkeypatch, repo)
    agent.run_handoff(repo, decide=False)
    p = package(tmp_path)
    assert "**The reviewer makes the merge decision.**" in p and "this package is not an approval" in p
    assert "has not approved, merged, committed, pushed or opened anything" in p
    assert "Did not: commit, push, open the pull request, merge, approve" in p
    assert "It is **not** an independent review" in p
    assert "Approved by the tech lead and the ticket owner before any code was written" in p  # what is true of the plan, not of the change
    assert not any(w in p for w in ("Status: Approved", "ready to merge", "LGTM"))


def test_the_integrity_table_lists_every_approved_document_with_its_hash_and_approvers(tmp_path, monkeypatch, repo):
    b = chain(tmp_path, monkeypatch, repo)
    agent.run_handoff(repo, decide=False)
    ledger = baseline.latest(b)
    p = package(tmp_path)
    integ = p.split("## 8. Evidence and integrity")[1].split("## 9.")[0]
    for f in ("implementation-plan.md", "repository-inspection.md", "stack-profile.md", "change-plan.md", "implementation-report.md", "test-report.md", "review-report.md", "pull-request.md"):
        assert f"| `{f}` | `{ledger[f]['sha256'][:12]}` |" in integ
    assert "| `implementation-plan.md` |" in integ and "Tech lead, Ticket owner" in integ
    assert f"SHA-256 `{handoff.sha((b / 'change.diff').read_text())[:12]}`" in p


def test_a_missing_ticket_reference_is_called_out_not_invented(tmp_path, monkeypatch, repo):
    plain = TH.PLAN.replace("TICKET-142 (https://tracker.example/TICKET-142): ", "")
    chain(tmp_path, monkeypatch, repo, plan=plain)
    agent.run_handoff(repo, decide=False)
    assert "The ticket reference is NOT STATED in the ticket documents. Add it before merging." in package(tmp_path)


# ---------------------------------------------------------------- gates ---------------------------------------------

def test_every_earlier_output_must_be_approved_unedited_and_current(tmp_path, monkeypatch, repo):
    b = chain(tmp_path, monkeypatch, repo)
    (b / "stack-profile.md").write_text("## Status\nEdited later\n")  # an EARLY document, not the last one
    with pytest.raises(SystemExit) as e:
        agent.run_handoff(repo, decide=False)
    assert "stack-profile.md: edited after it was approved" in str(e.value) and not (b / "handoff-package.md").exists()


def test_no_pull_request_description_means_no_handoff(tmp_path, monkeypatch, repo):
    TH._env(tmp_path, monkeypatch, "x", signed=("implement", "tests"))
    with pytest.raises(SystemExit) as e:
        agent.run_handoff(repo, decide=False)
    assert "pull-request.md: not produced" in str(e.value)


def test_a_change_made_after_the_review_is_refused_so_the_reviewer_sees_what_will_be_merged(tmp_path, monkeypatch, repo):
    b = chain(tmp_path, monkeypatch, repo)
    (repo / "src/app.py").write_text("x = 3\n")  # someone edited the code after the review and the PR text were written
    with pytest.raises(SystemExit) as e:
        agent.run_handoff(repo, decide=False)
    assert "the working tree changed since the review" in str(e.value) and not (b / "handoff-package.md").exists()


def test_the_repository_must_be_on_the_implementation_branch(tmp_path, monkeypatch, repo):
    chain(tmp_path, monkeypatch, repo)
    TH._git(repo, "stash", "-u", "-q")
    TH._git(repo, "checkout", "-q", "-")
    with pytest.raises(SystemExit) as e:
        agent.run_handoff(repo, decide=False)
    assert "Check that branch out first" in str(e.value)


# ---------------------------------------------------------------- what is open ---------------------------------------

def test_a_secret_failing_checks_and_unmet_criteria_make_the_package_say_not_ready(tmp_path, monkeypatch, repo):
    (repo / "src/app.py").write_text('x = 2\nkey = "AKIAABCDEFGHIJKLMNOP"\n')
    bad_tests = TESTS.replace("**All 1 local checks passed.**", "**1 of 1 local checks FAILED after 3 fix attempt(s).**").replace("| `pytest -q` | PASS (exit 0) | 1.2 |", "| `pytest -q` | FAIL (exit 1) | 1.2 |")
    pr = TH.PR_GOOD.replace("| AC2 | C2 | `src/out.py` | t | Met |", "| AC2 | C2 | `src/out.py` | t | Partly met |")
    chain(tmp_path, monkeypatch, repo, tests=bad_tests, pr_reply=pr)
    agent.run_handoff(repo, decide=False)
    p = package(tmp_path)
    assert "**Not ready to merge: 1 open blocker(s), 1 failing check(s)" in p
    assert "Open blockers: 1. Should-fix items: 1. Failing checks: 1." in p and "Criteria not fully met: 1." in p
    assert "**Criteria not fully met:**\n- AC2: Partly met" in p
    assert "AKIAABCDEFGHIJKLMNOP" not in p  # the secret is masked everywhere


def test_issues_reads_the_open_items_from_the_reports(tmp_path):
    review = ("## Blockers\n- D1, found by the code scan: Secret, `a.py`: x\n\n## Scanner findings from code (plain text)\n| ID | Severity | Kind | Where | Evidence | Why |\n|---|---|---|---|---|---|\n"
              "| D1 | Should fix | Unsafe default | `a.py`:3 | shell=True | shell=True. |\n| D2 | Check | Leftover | `b.py`:1 | print | x |\n\n"
              "## Findings\n| ID | sev | where | what | why | fix |\n|---|---|---|---|---|---|\n| F1 | Should fix | `c.py:1` | thing | y | z |\n| F2 | Nit | `c.py:2` | n | y | z |\n")
    i = handoff.issues(review, TESTS.replace("PASS (exit 0) | 1.2", "COULD NOT RUN, probable environment failure: x (exit 127) | 1.2"), TH.PR_GOOD)
    assert len(i["blockers"]) == 1 and len(i["should_fix"]) == 2 and i["should_fix"][0].startswith("D1") and i["should_fix"][1].startswith("F1")
    assert len(i["env"]) == 1 and i["failing"] == [] and i["not_run"][0].startswith("lint or static analysis `ruff check .`")
    assert i["gaps"] and i["unsupported"] == ["Elixir (1 files): no adapter for this language"] and i["unmet"] == []
    assert any("no check was run" in w for w in handoff.needs_reason(dict(i, checks_ran=False)))


# ---------------------------------------------------------------- the reviewer's decision -----------------------------

def decide_with(monkeypatch, answers, tty=True):
    it = iter(answers)
    monkeypatch.setattr(handoff, "is_tty", lambda: tty)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))


def decisions(tmp_path):
    f = tmp_path / "briefs/handoff-decisions.log"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def test_a_decision_cannot_be_made_by_a_script_or_a_piped_answer(tmp_path, monkeypatch, repo, capsys):
    chain(tmp_path, monkeypatch, repo)
    decide_with(monkeypatch, ["approve", "Priya", "fine"], tty=False)  # no person at a terminal
    agent.run_handoff(repo)
    assert decisions(tmp_path) == [] and "must be answered by a person at a terminal" in capsys.readouterr().out
    assert not any(r["step"] == "handoff" for r in map(json.loads, (tmp_path / "briefs/approvals.log").read_text().splitlines()))


def test_a_reviewer_who_approves_is_recorded_with_name_hash_and_that_nothing_was_merged_by_the_agent(tmp_path, monkeypatch, repo):
    b = chain(tmp_path, monkeypatch, repo)
    decide_with(monkeypatch, ["approve", "Priya N", "reviewed the diff and the criteria"])
    head = TH._git(repo, "rev-parse", "HEAD")
    agent.run_handoff(repo)
    d = decisions(tmp_path)
    assert len(d) == 1 and d[0]["decision"] == "approve" and d[0]["reviewer"] == "Priya N" and d[0]["merged_by_agent"] is False
    assert d[0]["package_sha256"] == handoff.sha(package(tmp_path)) and d[0]["reason"].startswith("reviewed the diff")
    assert d[0]["role"] == handoff.REVIEWER and d[0]["known_issues_at_decision"] == ["1 selected checks not run"]
    last = [json.loads(l) for l in (b / "approvals.log").read_text().splitlines()][-1]
    assert last["step"] == "handoff" and last["file"] == "handoff-package.md" and last["sha256"] == d[0]["package_sha256"]
    assert TH._git(repo, "rev-parse", "HEAD") == head  # no commit, no push, no merge


def test_approving_with_known_open_items_needs_a_written_reason(tmp_path, monkeypatch, repo, capsys):
    chain(tmp_path, monkeypatch, repo)
    decide_with(monkeypatch, ["approve", "Priya", ""])
    agent.run_handoff(repo)
    assert decisions(tmp_path) == [] and "A reason is required here" in capsys.readouterr().out


def test_changes_and_reject_need_a_reason_and_later_or_nonsense_records_nothing(tmp_path, monkeypatch, repo, capsys):
    chain(tmp_path, monkeypatch, repo)
    for answers in (["later"], ["maybe"], [""], ["changes", "Priya", ""], ["reject", "", "x"]):
        decide_with(monkeypatch, answers)
        agent.run_handoff(repo)
    assert decisions(tmp_path) == []
    decide_with(monkeypatch, ["changes", "Priya", "AC2 has no failure test"])
    agent.run_handoff(repo)
    decide_with(monkeypatch, ["reject", "Sam", "wrong approach"])
    agent.run_handoff(repo)
    assert [(x["decision"], x["reviewer"]) for x in decisions(tmp_path)] == [("changes", "Priya"), ("reject", "Sam")]
    assert not any(r["step"] == "handoff" for r in map(json.loads, (tmp_path / "briefs/approvals.log").read_text().splitlines()))  # only approve is an approval


def test_end_of_input_is_no_decision(tmp_path, monkeypatch, repo):
    chain(tmp_path, monkeypatch, repo)
    monkeypatch.setattr(handoff, "is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(EOFError()))
    agent.run_handoff(repo)
    assert decisions(tmp_path) == []


def test_no_decision_flag_writes_the_package_and_asks_nothing(tmp_path, monkeypatch, repo, capsys):
    chain(tmp_path, monkeypatch, repo)
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("must not ask"))
    agent.run_handoff(repo, decide=False)
    assert "Nothing was approved" in capsys.readouterr().out and decisions(tmp_path) == []


# ---------------------------------------------------------------- re-runs and safety ---------------------------------

def test_a_rerun_with_nothing_changed_is_identical_and_a_changed_one_keeps_the_old_package(tmp_path, monkeypatch, repo):
    b = chain(tmp_path, monkeypatch, repo)
    agent.run_handoff(repo, decide=False)
    first = package(tmp_path)
    agent.run_handoff(repo, decide=False)
    assert package(tmp_path) == first and not (b / "history").exists() or not list((b / "history").glob("handoff-package.*"))
    baseline.log_approval(b, "pr", b / "pull-request.md", agent.TECH)  # an approval renews the hash list only
    (b / "pull-request.md").write_text((b / "pull-request.md").read_text())
    agent.run_handoff(repo, decide=False)
    assert package(tmp_path) == first


def test_nothing_is_committed_pushed_or_changed_in_the_repository(tmp_path, monkeypatch, repo):
    chain(tmp_path, monkeypatch, repo)
    before = (TH._git(repo, "rev-parse", "HEAD"), TH._git(repo, "status", "--short"), TH._git(repo, "branch", "--show-current"))
    fail_if_model_called(monkeypatch)
    agent.run_handoff(repo, decide=False)
    assert (TH._git(repo, "rev-parse", "HEAD"), TH._git(repo, "status", "--short"), TH._git(repo, "branch", "--show-current")) == before


def test_the_step_is_registered_with_a_reviewer_role_and_depends_on_the_pull_request(tmp_path):
    template, out, reviewers, prior = agent.STEPS["handoff"]
    assert out == "handoff-package.md" and prior == ["pull-request.md"] and reviewers == [handoff.REVIEWER]
    assert "makes the merge decision" in handoff.REVIEWER and "handoff" in agent.NEEDS_REPO
    assert "[--no-decision]" in agent.__doc__ and "calls no model" in agent.__doc__


# ---------------------------------------------------------------- found by a real run: a hollow model reply -----------

def test_a_model_that_returns_nothing_usable_stops_every_step_and_writes_no_document(tmp_path, monkeypatch, repo):
    for junk in ("", "   \n", "You've hit your usage limit. It resets at 5pm.", "I cannot help with that."):
        tmp = tmp_path / f"t{abs(hash(junk))}"
        tmp.mkdir()
        TH._env(tmp, monkeypatch, lambda p, j=junk: j, signed=("implement", "tests"))
        for step, out in (("review", "review-report.md"), ("tests", "test-report.md")):
            before = (tmp / "briefs" / out).exists()
            with pytest.raises(SystemExit) as e:
                getattr(agent, step)([], str(repo))
            assert "returned no usable document" in str(e.value) and (tmp / "briefs" / out).exists() == before


def test_the_pr_step_does_not_write_a_hollow_description_when_the_model_fails(tmp_path, monkeypatch, repo):
    TH._pr_env(tmp_path, monkeypatch, repo, reply="Claude usage limit reached.")
    with pytest.raises(SystemExit) as e:
        agent.pr([], str(repo))
    assert "returned no usable document" in str(e.value) and "usage limit reached" in str(e.value)
    assert not (tmp_path / "briefs/pull-request.md").exists()


def test_the_understand_inspect_and_other_read_steps_also_refuse_an_empty_reply(tmp_path, monkeypatch):
    import test_coder as TC
    ticket, prompts = TC._env(tmp_path, monkeypatch, reply="")
    with pytest.raises(SystemExit) as e:
        agent.understand([str(ticket)])
    assert "returned no usable document" in str(e.value) and not (tmp_path / "briefs/implementation-plan.md").exists()


def test_the_handoff_refuses_a_hollow_pull_request_description_instead_of_reporting_none(tmp_path, monkeypatch, repo):
    b = chain(tmp_path, monkeypatch, repo)
    hollow = (b / "pull-request.md").read_text().replace("## Problem\nReviewers cannot see the steps.", "## Problem\n").replace("# List the agent steps", "# (no title)", 1)
    (b / "pull-request.md").write_text(hollow)
    for role in agent.STEPS["pr"][2]:
        baseline.log_approval(b, "pr", b / "pull-request.md", role)  # even if a person approved it, the handoff will not build on it
    with pytest.raises(SystemExit) as e:
        agent.run_handoff(repo, decide=False)
    assert "pull-request.md is incomplete (no title; empty section: Problem" in str(e.value) and not (b / "handoff-package.md").exists()
    full = (tmp_path / "briefs/pull-request.md").read_text().replace("| AC2 |", "| ACX |")
    assert "no row for AC2 in the acceptance criteria mapping" in agent.pr_incomplete(b, full)
