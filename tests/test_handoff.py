"""Coding agent steps 7 (review the change) and 8 (prepare the pull request). The model is faked; the repository is
a real temporary git repo, so the diff, the scan, the verdict and the assembled PR text are all checked for real."""
import re
import subprocess

import pytest

from architect import baseline
from coder import agent

REAL = agent.PROMPTS
BRANCH = "coder/20260101-000000"
PLAN = ("## Status\nDraft\n## Ticket summary\nTICKET-142 (https://tracker.example/TICKET-142): list the steps.\n"
        "## Acceptance criteria\n| AC1 | a |\n| AC2 | b |\n## Implementation plan\n| S1 | x | AC1, AC2 |\n")
CHANGE_PLAN = ("## Change set\n| ID | change | files | what | AC | size |\n|---|---|---|---|---|---|\n"
               "| C1 | first | `src/app.py` | x | AC1 | S |\n| C2 | second | new: `src/out.py` | y | AC2 | S |\n")
IMPL = ("## Status\nDraft. The work is on branch `" + BRANCH + "` (from `main`).\n## Changes\n| Change | Result | Files | The change |\n"
        "|---|---|---|---|\n| C1 | Done | `src/app.py` | first |\n| C2 | Done | `src/out.py` | second |\n"
        "## Diff summary\nNew files: `src/out.py`\n")
TESTS = ("## Status\nDraft. **This is development verification, not independent QA sign-off.** Branch.\n\n"
         "**All 1 local checks passed.**\n## Local checks run\n- `pytest -q`\n## Results before the test changes (baseline)\n"
         "| Check | Result | Seconds |\n|---|---|---|\n| `pytest -q` | PASS (exit 0) | 1.0 |\n## Results after the test changes\n"
         "| Check | Result | Seconds |\n|---|---|---|\n| `pytest -q` | PASS (exit 0) | 1.2 |\n"
         "## Test files changed (from git)\n| `tests/test_app.py` | updated | 3 | 0 |\n")
REVIEW_TAIL = ("## Consistency with the approved design\n| C | matches | evidence | deviation |\n|---|---|---|---|\n"
               "| C1 | Yes | `src/app.py:1` | None |\n| C2 | Yes | `src/out.py:1` | None |\n"
               "## Acceptance criteria check\n| AC | implemented | tested | status |\n|---|---|---|---|\n"
               "| AC1 | `src/app.py` | `tests/test_app.py` | Met |\n| AC2 | `src/out.py` | `tests/test_app.py` | Met |\n"
               "## Limitations\nSelf-review only; nothing was run.\n## Remaining questions\nQ1: is 4 the right limit? Priya.\n")
PR_GOOD = ("## Title\nList the agent steps\n## Problem\nReviewers cannot see the steps.\n## Implementation summary\nAdded a formatter.\n"
           "## Acceptance criteria mapping\n| AC | changes | files | test | status |\n|---|---|---|---|---|\n"
           "| AC1 | C1 | `src/app.py` | t | Met |\n| AC2 | C2 | `src/out.py` | t | Met |\n"
           "## Risks\nLow.\n## Migration and compatibility notes\nNone. Searched for stored data.\n")


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def review_reply(prompt, findings="None found", disposition="Intended"):
    ids = re.findall(r"(?m)^(D\d+) \[", prompt)
    rows = "".join(f"| {i} | {disposition} | reason |\n" for i in ids)
    return (f"## Findings\n{findings}\n## Scanner findings\n| D | disposition | reason |\n|---|---|---|\n{rows}" + REVIEW_TAIL)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "tests").mkdir()
    (r / "src/app.py").write_text("x = 1\n")
    (r / "tests/test_app.py").write_text("def test_x():\n    assert 1 == 1\n")
    (r / "README.md").write_text("hello\n")
    _git(r, "init", "-q")
    _git(r, "add", ".")
    _git(r, "commit", "-qm", "init")
    _git(r, "checkout", "-q", "-b", BRANCH)
    (r / "src/app.py").write_text("x = 2\n")
    (r / "src/out.py").write_text("new = True\n")
    (r / "tests/test_app.py").write_text("def test_x():\n    assert 1 == 1\n    assert 2 == 2\n")
    return r


def _env(tmp_path, monkeypatch, reply, approve=None, tests=TESTS, impl=IMPL, signed=("implement", "tests"), plan=PLAN):
    for f in REAL.glob("*.md"):
        (tmp_path / f.name).write_text(f.read_text())
    monkeypatch.setattr(agent, "HERE", tmp_path)
    monkeypatch.setattr(agent, "PROMPTS", tmp_path)
    b = tmp_path / "briefs"
    b.mkdir()
    for name, text in (("implementation-plan.md", plan), ("change-plan.md", CHANGE_PLAN), ("implementation-report.md", impl),
                       ("test-report.md", tests)):
        (b / name).write_text(text)
    for step, f in (("implement", "implementation-report.md"), ("tests", "test-report.md")):
        if step in signed:
            baseline.log_approval(b, step, b / f, agent.TECH)
    calls, asked = [], []

    def fake(who, prompt):
        calls.append((who, prompt))
        return reply(prompt) if callable(reply) else reply
    monkeypatch.setattr(agent, "ask", fake)
    monkeypatch.setattr(agent, "approve", approve or (lambda who: asked.append(who) or True))
    return calls, asked


def _rep(tmp_path, name="review-report.md"):
    return (tmp_path / "briefs" / name).read_text()


# ---------------------------------------------------------------- step 7: review ------------------------------------

def test_review_prompt_covers_every_review_duty_and_never_claims_independence():
    u = " ".join((REAL / "review.md").read_text().split())
    for part in ("accidental edits", "secrets", "unsafe defaults", "missing or weak error handling",
                 "differs from the approved ticket", "You may only read", "not an independent review",
                 "You must answer every one of them", "never \"Intended\"", "ONE ROW FOR EVERY finding D",
                 "ONE ROW FOR EVERY change C", "ONE ROW FOR EVERY acceptance criterion AC", "## Limitations",
                 "## Remaining questions", "Never claim to have run anything"):
        assert part in u


def test_review_needs_approved_reports_and_the_right_branch_and_never_calls_the_model_otherwise(tmp_path, monkeypatch, repo):
    calls, _ = _env(tmp_path, monkeypatch, review_reply, signed=("implement",))  # the test report was never approved
    with pytest.raises(SystemExit) as e:
        agent.review([], str(repo))
    assert "test-report.md: not approved" in str(e.value)
    baseline.log_approval(tmp_path / "briefs", "tests", tmp_path / "briefs/test-report.md", agent.TECH)
    _git(repo, "stash", "-u", "-q")
    _git(repo, "checkout", "-q", "-")
    with pytest.raises(SystemExit) as e:
        agent.review([], str(repo))
    assert "Check that branch out first" in str(e.value)
    with pytest.raises(SystemExit):
        agent.review([], None)
    assert calls == []


def test_a_clean_change_is_ready_for_human_review_but_the_report_says_it_is_only_a_self_review(tmp_path, monkeypatch, repo):
    calls, asked = _env(tmp_path, monkeypatch, review_reply)
    head = _git(repo, "rev-parse", "HEAD")
    agent.review([], str(repo))
    rep = _rep(tmp_path)
    assert "**No blockers found. Ready for human review.**" in rep and "not an independent review and not an approval" in rep
    diff = (tmp_path / "briefs/change.diff").read_text()
    assert "+++ b/src/out.py" in diff and "+new = True" in diff and "+x = 2" in diff  # new files are in the diff too
    assert {c[0] for c in calls} == {"coder"} and asked == [agent.TECH]  # the read-only agent, one human approval
    assert _git(repo, "rev-parse", "HEAD") == head and _git(repo, "status", "--short").count("\n") == 2  # nothing was edited


def test_a_secret_blocks_the_review_whatever_the_model_says_and_is_never_printed_in_full(tmp_path, monkeypatch, repo):
    secret = "AKIAABCDEFGHIJKLMNOP"
    (repo / "src/app.py").write_text(f'x = 2\nkey = "{secret}"\n')
    _env(tmp_path, monkeypatch, lambda p: review_reply(p, disposition="False positive"))
    agent.review([], str(repo))
    rep = _rep(tmp_path)
    assert "**Not ready for human review: 1 blocker(s).**" in rep and "found by the code scan: Secret" in rep
    assert secret not in rep and secret not in (tmp_path / "briefs/review-report.md").read_text()
    assert "AKIA" in rep  # a few characters stay so a human can find it


def test_an_unplanned_file_a_missed_change_and_bad_test_results_are_blockers(tmp_path, monkeypatch, repo):
    (repo / "README.md").write_text("rewritten\n")  # tracked, in no change of the plan, not a test
    (repo / "scratch.txt").write_text("x\n")  # untracked, in no report
    bad_impl = IMPL.replace("| C2 | Done |", "| C2 | Blocked |")
    bad_tests = TESTS.replace("**All 1 local checks passed.**", "**1 of 1 local checks FAILED after 3 fix attempt(s).**\n"
                              "- New failures (passed before the test changes): `pytest -q`")
    _env(tmp_path, monkeypatch, review_reply, impl=bad_impl, tests=bad_tests)
    agent.review([], str(repo))
    rep = _rep(tmp_path)
    assert "Changed, but not in any change of the approved plan" in rep and "`README.md`" in rep
    assert "Change C2 of the approved plan is 'Blocked'" in rep and "Checks that passed before the test changes fail now" in rep
    assert "An untracked file is present that no report mentions" in rep and "`scratch.txt`" in rep
    assert "Not ready for human review: 3 blocker(s)" in rep  # the untracked file is only a Check


def test_failing_or_unrun_checks_are_should_fix_not_blockers(tmp_path, monkeypatch, repo):
    _env(tmp_path, monkeypatch, review_reply, tests=TESTS.replace("**All 1 local checks passed.**", "**Local checks were NOT run (not approved).**"))
    agent.review([], str(repo))
    assert "No blockers found" in _rep(tmp_path) and "The local checks were not run, so nothing was verified" in _rep(tmp_path)


def test_every_scanner_finding_change_and_criterion_must_be_answered_once_repair(tmp_path, monkeypatch, repo):
    (repo / "src/app.py").write_text("x = 2\nprint(x)\n")
    replies = iter([None, None])

    def reply(prompt):
        if "The review is missing rows" in prompt:
            return review_reply(prompts[0])
        return "## Findings\nNone found\n## Scanner findings\n| D | disposition | reason |\n|---|---|---|\n## Limitations\nx\n"
    prompts = []
    calls, _ = _env(tmp_path, monkeypatch, lambda p: (prompts.append(p), reply(p))[1])
    agent.review([], str(repo))
    gap = calls[1][1]
    assert len(calls) == 2 and "Scanner findings: D1" in gap and "C1, C2" in gap and "AC1, AC2" in gap
    assert "| C1 | Yes |" in _rep(tmp_path)


def test_a_blocker_the_model_finds_counts_toward_the_verdict(tmp_path, monkeypatch, repo):
    finding = "| F1 | Blocker | `src/app.py:1` | wrong limit | breaks callers | fix it |"
    _env(tmp_path, monkeypatch, lambda p: review_reply(p, findings="| ID | severity | where | what | why | fix |\n|---|---|---|---|---|---|\n" + finding))
    agent.review([], str(repo))
    assert "Not ready for human review: 1 blocker(s)" in _rep(tmp_path) and "F1 `src/app.py:1`, found by the model review" in _rep(tmp_path)


def test_a_review_that_claims_approval_is_sent_back_and_the_tech_lead_can_ask_for_a_rework(tmp_path, monkeypatch, repo):
    answers = iter([False, True])
    asked = []
    replies = iter([review_reply("") + "\nStatus: Approved", review_reply(""), review_reply("")])
    calls, _ = _env(tmp_path, monkeypatch, lambda p: next(replies), approve=lambda who: asked.append(who) or next(answers))
    monkeypatch.setattr("builtins.input", lambda _: "look harder at error handling")
    agent.review([], str(repo))
    assert "approved or final" in calls[1][1] and "look harder at error handling" in calls[2][1]
    assert "Status: Approved" not in _rep(tmp_path) and asked == [agent.TECH, agent.TECH]


# ---------------------------------------------------------------- step 8: pull request ------------------------------

def _pr_env(tmp_path, monkeypatch, repo, reply=PR_GOOD, approve=None, plan=PLAN):
    calls, asked = _env(tmp_path, monkeypatch, reply, approve=approve, plan=plan)
    b = tmp_path / "briefs"
    (b / "review-report.md").write_text("## Status\nDraft. **Self-review by the system.**\n\n**No blockers found. Ready for human review.**\n"
                                        "## Limitations\nSelf-review only.\n## Remaining questions\nQ1: is 4 right? Priya.\n")
    baseline.log_approval(b, "review", b / "review-report.md", agent.TECH)
    return calls, asked


def test_pr_prompt_asks_for_the_explaining_parts_only_and_forbids_secrets_and_approval_claims():
    u = " ".join((REAL / "pr.md").read_text().split())
    for part in ("Another program adds the parts that must come from the record", "Never say that it, the change or the tests are approved",
                 "not independent QA sign-off", "ONE ROW FOR EVERY acceptance criterion", "Never include a secret",
                 "at most 72 characters", "Migration and compatibility notes", "Write \"None\" only with what was searched"):
        assert part in u


def test_pr_needs_an_approved_review_that_is_not_stale(tmp_path, monkeypatch, repo):
    calls, _ = _env(tmp_path, monkeypatch, PR_GOOD)
    with pytest.raises(SystemExit) as e:
        agent.pr([], str(repo))
    assert "review-report.md: not produced (run `review`)" in str(e.value)
    (tmp_path / "briefs/review-report.md").write_text("R")
    baseline.log_approval(tmp_path / "briefs", "review", tmp_path / "briefs/review-report.md", agent.TECH)
    baseline.log_approval(tmp_path / "briefs", "implement", tmp_path / "briefs/implementation-report.md", agent.TECH)  # re-approved later
    with pytest.raises(SystemExit) as e:
        agent.pr([], str(repo))
    assert "review-report.md: stale, implementation-report.md was re-approved after it" in str(e.value) and calls == []


def test_the_pr_body_is_assembled_from_the_record_not_from_the_model(tmp_path, monkeypatch, repo):
    greedy = PR_GOOD + "## Tests run\nEverything passed, QA verified!\n## Files changed\nonly README\n"
    calls, asked = _pr_env(tmp_path, monkeypatch, repo, reply=greedy)
    head = _git(repo, "rev-parse", "HEAD")
    agent.pr([], str(repo))
    body = (tmp_path / "briefs/pull-request.md").read_text()
    assert body.startswith("# List the agent steps\n")
    assert "**Ticket:** TICKET-142 (https://tracker.example/TICKET-142)" in body and f"`{BRANCH}`" in body
    files = body.split("## Files changed (from git)")[1].split("## Tests run")[0]
    assert "| `src/app.py` | production | 1 | 1 |" in files and "| `src/out.py` | production | 1 | 0 |" in files
    assert "| `tests/test_app.py` | test | 1 | 0 |" in files and "README" not in files  # from git, whatever the model wrote
    tests = body.split("## Tests run (from the recorded check runs)")[1].split("## Review outcome")[0]
    assert "**All 1 local checks passed.**" in tests and "| `pytest -q` | PASS (exit 0) | 1.2 |" in tests
    assert "not independent QA sign-off" in tests and "QA verified" not in body
    rv = body.split("## Review outcome")[1].split("## Risks")[0]
    assert "No blockers found. Ready for human review." in rv and "Self-review only." in rv and "Priya" in rv
    prov = body.split("## Source documents and approvals")[1].split("## Reviewer checklist")[0]
    assert re.search(r"\| `change-plan.md` \|", prov) is None  # never approved in this fixture, so never claimed
    assert re.search(r"\| `implementation-report.md` \| `[0-9a-f]{12}` \| Tech lead \|", prov)
    assert "git push -u origin " + BRANCH in body and 'gh pr create --title "List the agent steps"' in body
    assert "NOT run by the system" in body and _git(repo, "rev-parse", "HEAD") == head  # nothing pushed, nothing committed
    assert asked == [agent.TECH, agent.OWNER]


def test_a_missing_ticket_link_is_called_out_not_invented(tmp_path, monkeypatch, repo):
    _pr_env(tmp_path, monkeypatch, repo, plan="## Status\nDraft\n## Ticket summary\nno reference here\n## Acceptance criteria\n| AC1 | a |\n| AC2 | b |\n")
    agent.pr([], str(repo))
    assert "NOT STATED in the ticket documents. Add the ticket link before opening this PR." in (tmp_path / "briefs/pull-request.md").read_text()


def test_pr_gaps_are_repaired_once_title_criteria_migration_secrets_and_claims(tmp_path):
    b = tmp_path
    (b / "implementation-plan.md").write_text(PLAN)
    assert agent.pr_gaps(b, PR_GOOD) == ""
    long_title = PR_GOOD.replace("List the agent steps", "x" * 80)
    assert "at most 72" in agent.pr_gaps(b, long_title)
    assert "no row for AC2" in agent.pr_gaps(b, PR_GOOD.replace("| AC2 | C2 | `src/out.py` | t | Met |\n", ""))
    assert "Migration and compatibility notes are empty" in agent.pr_gaps(b, PR_GOOD.replace("None. Searched for stored data.", ""))
    assert "looks like a secret" in agent.pr_gaps(b, PR_GOOD + "key AKIAABCDEFGHIJKLMNOP")
    assert "looks like a secret" in agent.pr_gaps(b, PR_GOOD.replace("Low.", 'password = "hunter2hunter2"'))


def test_a_pr_text_that_claims_qa_or_approval_is_sent_back(tmp_path, monkeypatch, repo):
    replies = iter([PR_GOOD.replace("Low.", "Low. QA sign-off complete. Status: Approved."), PR_GOOD])
    calls, _ = _pr_env(tmp_path, monkeypatch, repo, reply=lambda p: next(replies))
    agent.pr([], str(repo))
    assert len(calls) == 2 and "claims QA sign-off" in calls[1][1] and "approved or final" in calls[1][1]
    assert "QA sign-off complete" not in (tmp_path / "briefs/pull-request.md").read_text()


def test_the_tech_lead_and_ticket_owner_sign_separately_and_can_send_it_back(tmp_path, monkeypatch, repo):
    answers, asked = iter([True, False, True, True]), []
    calls, _ = _pr_env(tmp_path, monkeypatch, repo, approve=lambda who: asked.append(who) or next(answers))
    monkeypatch.setattr("builtins.input", lambda _: "explain the rollback")
    agent.pr([], str(repo))
    assert asked == [agent.TECH, agent.OWNER, agent.TECH, agent.OWNER] and "explain the rollback" in calls[1][1]


def test_the_verdict_line_counts_should_fix_items_from_the_scan_and_the_model(tmp_path, monkeypatch, repo):
    (repo / "src/app.py").write_text("x = 2\nrequests.get(u, verify=False)\n")  # scan: one Should fix
    row = "| F1 | Should fix | `src/app.py:1` | w | y | z |\n| F2 | Nit | `src/app.py:1` | w | y | z |"
    _env(tmp_path, monkeypatch, lambda p: review_reply(p, findings="| ID | sev | where | what | why | fix |\n|---|---|---|---|---|---|\n" + row))
    agent.review([], str(repo))
    assert "**No blockers found. Ready for human review. 2 should-fix item(s) for the reviewer to read first.**" in _rep(tmp_path)


def test_the_pr_carries_the_stack_coverage_and_gaps_from_the_test_report_so_a_reviewer_sees_what_did_not_run(tmp_path, monkeypatch, repo):
    cov = ("## Stack coverage (from the code; a check is only PASS or FAIL if it was run)\n\n### Detected stack\n| Stack | Area |\n|---|---|\n| Fake | Backend |\n\n"
           "### Checks selected (2), run (1), not run (1)\n| Stack | Kind | Command | Outcome |\n|---|---|---|---|\n| Fake | lint | `x` | Not run: `x` is not installed here |\n\n"
           "### Unsupported technologies\n- Lua (2 files): no adapter\n\n")
    _pr_env(tmp_path, monkeypatch, repo)
    t = tmp_path / "briefs/test-report.md"
    t.write_text(TESTS.replace("## Results before", cov + "## Results before", 1))
    baseline.log_approval(tmp_path / "briefs", "tests", t, agent.TECH)
    baseline.log_approval(tmp_path / "briefs", "review", tmp_path / "briefs/review-report.md", agent.TECH)
    agent.pr([], str(repo))
    body = (tmp_path / "briefs/pull-request.md").read_text()
    assert "### Stack coverage (from the code; a check is only PASS or FAIL if it was run)" in body
    assert "| Fake | lint | `x` | Not run: `x` is not installed here |" in body and "#### Unsupported technologies" in body
    assert body.index("Stack coverage") < body.index("## Review outcome")
