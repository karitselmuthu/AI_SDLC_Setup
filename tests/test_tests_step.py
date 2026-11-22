"""Coding agent step 6 (developer tests). The model is faked; its test edits are made by the test against a real
temporary git repo, and the local checks are real shell commands, so scope, the fix loop and recording are checked."""
import re
import subprocess

import pytest

import core
from architect import baseline
from coder import agent

REAL = agent.PROMPTS
PLAN = "## Status\nDraft\n## Acceptance criteria\n| AC1 | a |\n| AC2 | b |\n## Implementation plan\n| S1 | x | AC1, AC2 |\n"
GOOD = ("## Test matrix\n| AC | normal | boundary | failure | notes |\n|---|---|---|---|---|\n"
        "| AC1 | test_ok | test_empty | test_bad | - |\n| AC2 | test_ok2 | N/A: no range | test_bad2 | - |\n"
        "## Test changes\nadded\n## Fixtures and determinism\ntmp_path\n## Gaps and suspected defects\nNone\n")


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A repo already on the implement branch: src/app.py modified and src/out.py created, both uncommitted."""
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "tests").mkdir()
    (r / "src/app.py").write_text("x = 1\n")
    (r / "tests/test_app.py").write_text("def test_x():\n    assert 1 == 1\n    assert 2 == 2\n")
    _git(r, "init", "-q")
    _git(r, "add", ".")
    _git(r, "commit", "-qm", "init")
    _git(r, "checkout", "-q", "-b", "coder/20260101-000000")
    (r / "src/app.py").write_text("x = 2\n")
    (r / "src/out.py").write_text("new = True\n")
    return r


def _env(tmp_path, monkeypatch, repo, edits=None, replies=None, approve=None, signed=True, stack=None):
    for f in REAL.glob("*.md"):
        (tmp_path / f.name).write_text(f.read_text())
    monkeypatch.setattr(agent, "HERE", tmp_path)
    monkeypatch.setattr(agent, "PROMPTS", tmp_path)
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    (briefs / "implementation-plan.md").write_text(PLAN)
    (briefs / "implementation-report.md").write_text(
        "## Status\nDraft. The work is on branch `coder/20260101-000000` (from `main`).\n## Changes\n"
        "| C1 | Done | `src/app.py` | x |\n## Diff summary\n```\nsrc/app.py | 1 +\n```\nNew files: `src/out.py`\n")
    if stack:
        (briefs / "stack-profile.md").write_text("## Build, run and test commands\n| Purpose | Command | Where |\n|---|---|---|\n" + stack)
    if signed:
        baseline.log_approval(briefs, "implement", briefs / "implementation-report.md", agent.TECH)
    calls, asked = [], []

    def fake(who, prompt):
        key = ("fix" if "FAILED after your test changes" in prompt else "feedback" if "Human feedback" in prompt
               else "repair" if "Test matrix has no complete row" in prompt or "claims QA" in prompt or "claim" in prompt[:80]
               else "write")
        calls.append((who, key, prompt, list(core.AGENTS["coder-test"]["allow"])))
        n = sum(1 for c in calls if c[1] == key)
        for k in (f"{key}{n}", key):
            if edits and k in edits:
                edits[k]()
                break
        r = (replies or {}).get(f"{key}{n}", (replies or {}).get(key, GOOD))
        return r
    monkeypatch.setattr(agent, "ask", fake)
    monkeypatch.setattr(agent, "approve", approve or (lambda who: asked.append(who) or True))
    return calls, asked


def _report(tmp_path):
    return (tmp_path / "briefs/test-report.md").read_text()


def _write(repo, rel, text):
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text)


def test_the_test_agent_has_no_shell_and_says_this_is_not_qa():
    cfg = core.AGENTS["coder-test"]
    assert "Bash" not in cfg["tools"] and cfg["mode"] == "default"
    assert "not independent QA sign-off" in cfg["role"] and "only test files" in cfg["role"]


def test_prompt_demands_normal_boundary_failure_determinism_and_no_weakening():
    u = " ".join((REAL / "tests.md").read_text().split())
    for part in ("not independent QA sign-off", "ONLY test files and test fixtures", "must NOT change production code",
                 "normal behaviour, boundary behaviour", "failure behaviour", "Deterministic fixtures only",
                 "no real clock or sleeping", "NEVER weaken, delete, skip or xfail", "Production defect suspected",
                 "never claim that a test passes or fails yourself", "ONE ROW FOR EVERY acceptance criterion",
                 "Do not leave a cell empty"):
        assert part in u


def test_is_test_path_and_the_allow_rules_cover_tests_and_never_production_code(repo):
    for yes in ("tests/test_x.py", "pkg/tests/helper.py", "src/test_a.py", "web/app.spec.ts", "web/a.test.js", "conftest.py",
                "tests/fixtures/data.json", "lib/mod_test.py"):
        assert agent.is_test_path(yes), yes
    for no in ("src/app.py", "docs/guide.md", "contest.py", "src/protest/a.py", "README.md", "latest.py"):
        assert not agent.is_test_path(no), no
    rules = agent.test_allow_rules(repo)
    assert rules[:3] == ["Read", "Grep", "Glob"] and f"Edit(//{str(repo.resolve())[1:]}/tests/**)" in rules
    assert not any("src" in r and "tests" not in r for r in rules[3:])


def test_check_commands_come_from_the_stack_profile_and_skip_unsafe_ones():
    import tempfile, pathlib
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "stack-profile.md").write_text(
        "## Build, run and test commands\n| Purpose | Command | Where |\n|---|---|---|\n"
        "| Run tests | `pytest -q` | pytest.ini |\n| Lint | `ruff check .` | x |\n| Type check | `mypy src` | x |\n"
        "| Install | `pip install -r requirements.txt` | x |\n| Install deps | `yarn install --frozen-lockfile` | x |\n"
        "| Deploy | `make deploy` | x |\n| Test in docker | `docker run app test` | x |\n"
        "| Test and clean | `pytest && rm -rf build` | x |\n| Lint, piped | `ruff check . | tee out` | x |\n"
        "| Build, lint, format | Not stated. | none |\n| Run the app | `python app.py` | x |\n| Test again | `pytest -q` | x |\n")
    assert agent.check_commands(d) == ["pytest -q", "ruff check .", "mypy src"]
    assert agent.check_commands(tmp := pathlib.Path(tempfile.mkdtemp())) == [] and tmp.exists()


def test_refuses_without_an_approved_report_on_the_right_branch(tmp_path, monkeypatch, repo):
    calls, _ = _env(tmp_path, monkeypatch, repo, signed=False)
    with pytest.raises(SystemExit) as e:
        agent.tests([], str(repo))
    assert "implementation-report.md: not approved" in str(e.value)
    baseline.log_approval(tmp_path / "briefs", "implement", tmp_path / "briefs/implementation-report.md", agent.TECH)
    _git(repo, "stash", "-u", "-q")
    _git(repo, "checkout", "-q", "-")
    with pytest.raises(SystemExit) as e:
        agent.tests([], str(repo))
    assert "is on" in str(e.value) and "Check that branch out first" in str(e.value)
    with pytest.raises(SystemExit):
        agent.tests([], None)
    assert calls == []


def test_the_system_runs_the_approved_checks_before_and_after_and_records_real_results(tmp_path, monkeypatch, repo):
    calls, asked = _env(tmp_path, monkeypatch, repo, edits={"write": lambda: _write(repo, "tests/test_new.py", "def test_n():\n    assert True is True\n")})
    agent.tests([], str(repo), ["test -f tests/test_new.py"])
    rep = _report(tmp_path)
    base, after = rep.split("## Results before")[1].split("## Results after")
    assert "FAIL (exit 1)" in base  # the file did not exist yet
    assert "PASS (exit 0)" in after and "All 1 local checks passed" in rep
    assert "not independent QA sign-off" in rep and "| `tests/test_new.py` | new |" in rep
    assert asked[0].startswith("Tech lead approves running these local checks") and asked[1] == agent.TECH


def test_failing_checks_go_back_to_the_model_for_a_test_fix_and_the_loop_ends(tmp_path, monkeypatch, repo):
    calls, _ = _env(tmp_path, monkeypatch, repo, edits={"fix": lambda: _write(repo, "tests/test_new.py", "def test_n(): pass\n")})
    agent.tests([], str(repo), ["test -f tests/test_new.py"])
    keys = [c[1] for c in calls]
    assert keys == ["write", "fix"]
    fix = calls[1][2]
    assert "$ test -f tests/test_new.py  (exit 1; " in fix and "Fix the TESTS only" in fix and "Production defect suspected" in fix
    assert "All 1 local checks passed after" not in _report(tmp_path) and "Run 1:" in _report(tmp_path) and "Run 2:" in _report(tmp_path)


def test_the_fix_loop_is_capped_and_a_human_still_decides(tmp_path, monkeypatch, repo):
    calls, asked = _env(tmp_path, monkeypatch, repo)
    agent.tests([], str(repo), ["false"])
    assert [c[1] for c in calls].count("fix") == agent.MAX_FIX
    rep = _report(tmp_path)
    assert "1 of 1 local checks FAILED" in rep and "Failures that were already there before" in rep
    assert asked[-1] == agent.TECH  # a failing result is shown to the tech lead, never hidden or auto-approved


def test_new_failures_are_told_apart_from_old_ones(tmp_path, monkeypatch, repo):
    calls, _ = _env(tmp_path, monkeypatch, repo, edits={"write": lambda: _write(repo, "tests/test_flag.py", "x = 1\n")})
    agent.tests([], str(repo), ["test ! -f tests/test_flag.py"])  # passes before, fails after the model adds the file
    rep = _report(tmp_path)
    assert "New failures (passed before the test changes): `test ! -f tests/test_flag.py`" in rep
    assert "passed before your changes" in calls[1][2]


def test_declining_to_run_the_checks_is_recorded_and_nothing_is_run(tmp_path, monkeypatch, repo):
    answers = iter([False, True])
    calls, _ = _env(tmp_path, monkeypatch, repo, approve=lambda who: next(answers),
                    edits={"write": lambda: _write(repo, "tests/test_new.py", "x = 1\n")})
    agent.tests([], str(repo), ["touch SHOULD_NOT_EXIST"])
    assert not (repo / "SHOULD_NOT_EXIST").exists() and "Local checks were NOT run (not approved)" in _report(tmp_path)


def test_no_commands_at_all_is_reported_not_invented(tmp_path, monkeypatch, repo):
    _env(tmp_path, monkeypatch, repo)
    agent.tests([], str(repo))
    assert "no applicable commands were found" in _report(tmp_path)


def test_a_timeout_is_a_recorded_result_not_a_crash():
    import tempfile
    r = agent.run_checks(tempfile.mkdtemp(), ["sleep 5"], timeout=1)[0]
    assert r["rc"] == "timeout" and "stopped after 1 seconds" in r["tail"]


def test_edits_outside_test_files_are_reverted_including_files_the_implement_step_created(tmp_path, monkeypatch, repo):
    def sneaky():
        _write(repo, "tests/test_ok.py", "def test_ok(): pass\n")
        (repo / "src/app.py").write_text("x = HACKED\n")  # production code edited by the model
        (repo / "src/out.py").write_text("new = HACKED\n")  # a file the implement step created
    _env(tmp_path, monkeypatch, repo, edits={"write": sneaky})
    agent.tests([], str(repo))
    assert (repo / "src/app.py").read_text() == "x = 2\n" and (repo / "src/out.py").read_text() == "new = True\n"
    assert (repo / "tests/test_ok.py").exists()
    rep = _report(tmp_path)
    assert "`src/app.py`" in rep.split("## Edits outside test files, reverted")[1] and "`src/out.py`" in rep.split("## Edits outside")[1]


def test_weakened_removed_and_skipped_tests_are_flagged_for_the_reviewer(tmp_path, monkeypatch, repo):
    def weaken():
        _write(repo, "tests/test_app.py", "import pytest\n@pytest.mark.skip\ndef test_y():\n    pass\n")
    _env(tmp_path, monkeypatch, repo, edits={"write": weaken})
    agent.tests([], str(repo))
    flags = _report(tmp_path).split("## Review flags")[1].split("## Edits")[0]
    assert "assertion lines were removed" in flags and "test definition(s) were removed: def test_x" in flags
    assert "skip or xfail was added" in flags
    assert agent.review_flags("+def test_new():\n+    assert 1 == 2\n") == []


def test_a_matrix_without_boundary_or_failure_cases_is_sent_back_once(tmp_path, monkeypatch, repo):
    thin = GOOD.replace("| test_empty |", "|  |")
    calls, _ = _env(tmp_path, monkeypatch, repo, replies={"write": thin, "repair": GOOD})
    agent.tests([], str(repo))
    assert [c[1] for c in calls] == ["write", "repair"] and "no complete row for AC1" in calls[1][2]
    assert agent.untested(tmp_path / "briefs", GOOD) == ""


def test_a_claim_of_qa_sign_off_is_removed(tmp_path, monkeypatch, repo):
    calls, _ = _env(tmp_path, monkeypatch, repo, replies={"write": GOOD + "\nQA sign-off complete.", "repair": GOOD})
    agent.tests([], str(repo))
    assert "claims QA sign-off" in calls[1][2] and "QA sign-off complete" not in _report(tmp_path)
    assert agent.claims_qa("independently tested by the team") != "" and agent.claims_qa("unit tests added") == ""


def test_the_tech_lead_can_send_the_tests_back_and_checks_are_rerun(tmp_path, monkeypatch, repo):
    answers = iter([True, False, True])  # run checks? yes. approve report? no. approve revision? yes.
    asked = []
    calls, _ = _env(tmp_path, monkeypatch, repo, approve=lambda who: asked.append(who) or next(answers),
                    edits={"write": lambda: _write(repo, "tests/test_new.py", "x = 1\n")})
    monkeypatch.setattr("builtins.input", lambda _: "also test the empty input")
    agent.tests([], str(repo), ["test -f tests/test_new.py"])
    assert [c[1] for c in calls] == ["write", "feedback"] and "also test the empty input" in calls[1][2]
    assert "Run 2:" in _report(tmp_path) or "Run 1:" in _report(tmp_path)


def test_nothing_is_committed_and_the_branch_does_not_change(tmp_path, monkeypatch, repo):
    head, branch = _git(repo, "rev-parse", "HEAD"), _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    _env(tmp_path, monkeypatch, repo, edits={"write": lambda: _write(repo, "tests/test_new.py", "x = 1\n")})
    agent.tests([], str(repo))
    assert _git(repo, "rev-parse", "HEAD") == head and _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == branch


def test_the_tool_scope_given_to_the_model_is_test_paths_only(tmp_path, monkeypatch, repo):
    calls, _ = _env(tmp_path, monkeypatch, repo)
    agent.tests([], str(repo))
    allow = calls[0][3]
    assert all(a in ("Read", "Grep", "Glob") or a.startswith("Edit(//") for a in allow)
    assert any(a.endswith("/tests/**)") for a in allow) and not any("/src" in a for a in allow)
