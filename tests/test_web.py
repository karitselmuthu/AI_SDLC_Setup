"""The web page (web/app.py). The agents are replaced by a small fake process that prints the same `approve? [y/N]` prompts and writes
the same ledger entries, so these tests cover the page itself: projects, status from the ledger, answering prompts, the reviewer decision
and, above all, the security rules (only localhost, a token on every change, no path tricks)."""
import http.client
import json
import os
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from architect import agent as A, baseline
from coder import agent as C
import test_handoff as TH
from web import app

ROOT = app.ROOT
FAKE = textwrap.dedent('''
    import os, pathlib, sys
    sys.path.insert(0, os.environ["FAKE_ROOT"])
    from architect import baseline
    step, which = sys.argv[1], sys.argv[2]
    if os.environ.get("FAKE_FAIL"):
        print("Cannot do this yet: something is wrong", flush=True); sys.exit(1)
    mod = __import__(which + ".agent", fromlist=["STEPS"])
    _, file, roles, _ = mod.STEPS[step]
    roles = roles if isinstance(roles, list) else [roles]
    briefs = pathlib.Path(os.environ["SDLC_WORKSPACE"]) / which / "briefs"
    n = 0
    while True:
        n += 1
        (briefs / file).write_text(f"## Status\\nDraft number {n} of {step}\\n")
        print("wrote:", briefs / file, flush=True)
        for r in roles:
            if input(f"[{r}] approve? [y/N] ").strip().lower() != "y":
                print("feedback:", input("feedback> "), flush=True); break
            baseline.log_approval(briefs, step, briefs / file, r)
        else:
            break
''')


@pytest.fixture
def web(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "PROJECTS", tmp_path / "projects")
    script = tmp_path / "fake_agent.py"
    script.write_text(FAKE)
    monkeypatch.setattr(app, "build_cmd", lambda agent, step, args: [sys.executable, "-u", str(script), step, agent])
    monkeypatch.setenv("FAKE_ROOT", str(ROOT))
    monkeypatch.setattr(app, "MANAGER", app.Manager())
    srv = app.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    def call(method, path, body=None, token=True, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        h = {"Content-Type": "application/json", **(headers or {})}
        if token:
            h["X-Token"] = app.TOKEN
        c.request(method, path, json.dumps(body) if body is not None else None, h)
        r = c.getresponse()
        raw = r.read().decode()
        try:
            return r.status, json.loads(raw)
        except ValueError:
            return r.status, raw
    yield call
    for r in list(app.MANAGER.runs.values()):
        if r.state in ("running", "awaiting"):
            r.stop()
    srv.shutdown()


def wait(pred, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError("timed out waiting")


def new(web, name="Smart Meeting Assistant", desc="Joins meetings, transcribes them and tracks action items."):
    st, p = web("POST", "/api/projects", dict(name=name, description=desc))
    assert st == 200, p
    return p["id"]


def view(web, pid):
    return web("GET", f"/api/projects/{pid}")[1]


def step(v, agent, name):
    return next(s for s in v["tracks"][agent]["steps"] if s["name"] == name)


def run(web, pid, agent="architect", step_="next", auto=False):
    return web("POST", f"/api/projects/{pid}/run", dict(agent=agent, step=step_, auto=auto))


def awaiting(web, pid):
    return wait(lambda: (lambda v: v if v["run"] and v["run"]["pending"] else None)(view(web, pid)))


# ---------------------------------------------------------------- projects -------------------------------------------

def test_a_project_keeps_the_users_words_and_nothing_else_and_gets_its_own_workspace(web, tmp_path):
    pid = new(web, desc="Joins meetings. Any industry.")
    d = tmp_path / "projects" / pid
    brief = (d / "inputs/project-brief.md").read_text()
    assert "Joins meetings. Any industry." in brief and "Anything not stated here is not known" in brief
    for sub in ("architect/briefs", "architect/baseline", "coder/briefs"):
        assert (d / sub).is_dir()
    v = view(web, pid)
    assert v["project"]["name"] == "Smart Meeting Assistant" and [x["name"] for x in v["project"]["docs"]] == ["project-brief.md"]
    assert web("GET", "/api/projects")[1][0]["id"] == pid


def test_a_project_needs_a_name_and_a_real_description(web):
    assert web("POST", "/api/projects", dict(name="", description="long enough description here"))[0] == 400
    st, e = web("POST", "/api/projects", dict(name="x", description="short"))
    assert st == 400 and "Describe the project" in e["error"]


def test_documents_are_checked_named_safely_and_limited(web, tmp_path):
    pid = new(web)
    ok = web("POST", f"/api/projects/{pid}/docs", dict(name="../../evil/rfp.md", text="# RFP", kind="source"))
    assert ok[0] == 200 and "rfp.md" in [d["name"] for d in ok[1]["docs"]]
    assert (tmp_path / "projects" / pid / "inputs/rfp.md").exists() and not (tmp_path / "evil").exists()
    assert web("POST", f"/api/projects/{pid}/docs", dict(name="x.exe", text="x"))[0] == 400
    assert web("POST", f"/api/projects/{pid}/docs", dict(name="project-brief.md", text="overwrite"))[0] == 400
    assert web("POST", f"/api/projects/{pid}/docs", dict(name="a.md", text=""))[0] == 400
    assert web("POST", f"/api/projects/{pid}/docs", dict(name="big.txt", text="x" * (app.MAX_UPLOAD + 1)))[0] == 400
    n = web("POST", f"/api/projects/{pid}/docs", dict(name="notes.md", text="met", kind="meeting"))[1]
    assert {"name": "notes.md", "kind": "meeting"} in n["docs"]


def test_coder_setup_validates_the_repository_and_stores_the_ticket(web, tmp_path):
    pid = new(web)
    assert web("POST", f"/api/projects/{pid}/settings", dict(repo=str(tmp_path / "nope")))[0] == 400
    plain = tmp_path / "plain"
    plain.mkdir()
    assert web("POST", f"/api/projects/{pid}/settings", dict(repo=str(plain)))[0] == 400  # a folder, but not a git repository
    subprocess.run(["git", "init", "-q", str(plain)], check=True)
    st, p = web("POST", f"/api/projects/{pid}/settings", dict(repo=str(plain), ticket_text="Approved. Add --list.", checks=["pytest -q", " ", "ruff check ."]))
    assert st == 200 and p["repo"] == str(plain.resolve()) and p["ticket"] is True and p["checks"] == ["pytest -q", "ruff check ."]
    assert (tmp_path / "projects" / pid / "inputs/ticket.md").read_text().startswith("Approved.")


def test_new_and_existing_projects_are_told_apart_and_the_notes_follow(web):
    pid = new(web)
    notes = {x["agent"]: x["note"] for x in view(web, pid)["pipeline"]}
    assert "Optional" in notes["triage"] and "after the first release" in notes["sre"] and notes["architect"] == ""
    st, p = web("POST", "/api/projects", dict(name="Old", description="A live system with a backlog.", kind="existing"))
    assert st == 200 and {x["agent"]: x["note"] for x in view(web, p["id"])["pipeline"]}["triage"] == ""
    assert web("POST", "/api/projects", dict(name="X", description="A real description here.", kind="weird"))[0] == 400


def test_an_empty_repository_is_made_for_a_new_project(web, tmp_path):
    pid = new(web)
    st, p = web("POST", f"/api/projects/{pid}/settings", dict(create_repo=True))
    assert st == 200 and p["repo"] == str((tmp_path / "projects" / pid / "repo").resolve())
    assert subprocess.run(["git", "-C", p["repo"], "log", "--oneline"], capture_output=True, text=True).stdout.strip().endswith("Start the project")
    assert web("POST", f"/api/projects/{pid}/settings", dict(create_repo=True))[0] == 400  # never replaces a repository that is set


def test_the_first_ticket_comes_only_from_an_approved_baseline_and_names_its_approver(web, tmp_path, monkeypatch):
    pid = new(web)
    assert web("POST", f"/api/projects/{pid}/settings", dict(draft_ticket=True, approved_by="Asha"))[0] == 400  # handoff not approved
    briefs = tmp_path / "projects" / pid / "architect/briefs"
    (briefs / "requirements.md").write_text("| R-001 | Take in PDFs | Technical | Preferred | C1 | brief | Proposed: every PDF is taken in |\n| Q1 | not a requirement |\n")
    real = app.steps_status
    monkeypatch.setattr(app, "steps_status", lambda pid_, agent: [dict(x, status="approved") for x in real(pid_, agent)] if agent == "architect" else real(pid_, agent))
    assert web("POST", f"/api/projects/{pid}/settings", dict(draft_ticket=True))[0] == 400  # no approver named
    st, p = web("POST", f"/api/projects/{pid}/settings", dict(draft_ticket=True, approved_by="Asha"))
    ticket = (tmp_path / "projects" / pid / "inputs/ticket.md").read_text()
    assert st == 200 and p["ticket"] is True and "Approved by Asha" in ticket and "R-001: Take in PDFs. Acceptance: Proposed: every PDF is taken in" in ticket and "Q1" not in ticket


def fake_github(monkeypatch, issues=None, clone_rc=0):
    real, seen = subprocess.run, []

    def run(cmd, *a, **k):
        seen.append(cmd)
        if cmd[:2] == ["git", "clone"]:
            if clone_rc == 0:
                real(["git", "init", "-q", cmd[-1]], check=True)
            return subprocess.CompletedProcess(cmd, clone_rc, "", "fatal: repository not found" if clone_rc else "")
        if cmd[0] == "gh":
            return subprocess.CompletedProcess(cmd, 0, json.dumps(issues or []), "")
        return real(cmd, *a, **k)
    monkeypatch.setattr(app.subprocess, "run", run)
    return seen


def test_a_github_repository_is_copied_and_its_issues_are_fetched(web, tmp_path, monkeypatch):
    seen = fake_github(monkeypatch, issues=[dict(number=7, title="Crash on empty file", body="It crashes.", author=dict(login="sam"))])
    pid = new(web)
    for bad in ("http://github.com/a/b", "https://github.com/a", "https://evil.com/a/b", "https://github.com/a/b; rm -rf x", "git@github.com:a/b.git"):
        assert web("POST", f"/api/projects/{pid}/settings", dict(clone_url=bad))[0] == 400
    assert not any(c[:2] == ["git", "clone"] for c in seen)  # a bad address never reaches git
    assert web("POST", f"/api/projects/{pid}/settings", dict(github_issues=True))[0] == 400  # nothing copied yet
    st, p = web("POST", f"/api/projects/{pid}/settings", dict(clone_url="https://github.com/karitselmuthu/Enterprise_LLM_Transfomer", github_issues=True))
    assert st == 200 and p["github"] == "karitselmuthu/Enterprise_LLM_Transfomer" and p["repo"] == str((tmp_path / "projects" / pid / "repo").resolve())
    assert next(c for c in seen if c[:2] == ["git", "clone"])[3] == "--"
    rows = json.loads((tmp_path / "projects" / pid / "inputs/github-issues.json").read_text())
    assert rows == [dict(id="GH-7", title="Crash on empty file", description="It crashes.", requester="sam")] and dict(name="github-issues.json", kind="issues") in p["docs"]
    assert web("POST", f"/api/projects/{pid}/settings", dict(clone_url="https://github.com/a/b"))[0] == 400  # never replaces a repository


def test_a_copy_is_kept_even_when_the_next_action_in_the_same_request_fails(web, tmp_path, monkeypatch):
    fake_github(monkeypatch, issues=[])  # the copy works, the issue fetch finds nothing and is refused
    pid = new(web)
    assert web("POST", f"/api/projects/{pid}/settings", dict(clone_url="https://github.com/a/b", github_issues=True))[0] == 400
    assert view(web, pid)["project"]["repo"].endswith("/repo")


def test_a_failed_copy_leaves_nothing_behind(web, tmp_path, monkeypatch):
    fake_github(monkeypatch, clone_rc=128)
    pid = new(web)
    st, p = web("POST", f"/api/projects/{pid}/settings", dict(clone_url="https://github.com/a/b"))
    assert st == 400 and "repository not found" in p["error"] and not (tmp_path / "projects" / pid / "repo").exists() and view(web, pid)["project"]["repo"] == ""


README = """# App\n\n## Quick start\nrun it\n\n## Scope\n\nThis is a lab. The decoder is sequential.\n\n### Detail\nOnly simulations.\n\n## Known limitations\n- no GPU\n\n## Empty scope\n## License\nMIT\n"""


def test_readme_sections_that_state_scope_become_triage_items_word_for_word(web, tmp_path):
    pid = new(web)
    assert web("POST", f"/api/projects/{pid}/settings", dict(readme_scope=True))[0] == 400  # no repository yet
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert web("POST", f"/api/projects/{pid}/settings", dict(repo=str(repo)))[0] == 200
    st, p = web("POST", f"/api/projects/{pid}/settings", dict(readme_scope=True))
    assert st == 400 and "no Scope" in p["error"]  # no README at all
    (repo / "README.md").write_text(README)
    st, p = web("POST", f"/api/projects/{pid}/settings", dict(readme_scope=True))
    rows = json.loads((tmp_path / "projects" / pid / "inputs/readme-scope.json").read_text())
    assert st == 200 and dict(name="readme-scope.json", kind="issues") in p["docs"]
    assert [r["id"] for r in rows] == ["README-1", "README-2"]  # the empty section and the others are left out
    assert rows[0]["description"] == "This is a lab. The decoder is sequential.\n\n### Detail\nOnly simulations." and rows[1]["description"] == "- no GPU"
    assert "Scope" in rows[0]["title"] and rows[0]["requester"] == "README.md"


# ---------------------------------------------------------------- security -------------------------------------------

def test_only_localhost_hosts_are_served(web):
    assert web("GET", "/api/projects", headers={"Host": "evil.example"})[0] == 403  # DNS rebinding
    assert web("GET", "/api/projects", headers={"Host": "localhost"})[0] == 200


def test_every_change_needs_the_token_and_a_same_origin_request(web):
    pid = new(web)
    assert web("POST", "/api/projects", dict(name="n", description="long enough description"), token=False)[0] == 403
    assert web("POST", "/api/projects", dict(name="n", description="long enough description"), headers={"X-Token": "wrong"}, token=False)[0] == 403
    st, e = web("POST", f"/api/projects/{pid}/respond", dict(answer="y"), headers={"Origin": "http://evil.example"})
    assert st == 403 and "Cross-site" in e["error"]  # another web page in the browser cannot approve anything
    assert web("POST", f"/api/projects/{pid}/stop", {})[0] == 200


def test_paths_are_never_taken_from_the_request(web):
    pid = new(web)
    for bad in ("../x", "..%2f..%2fetc", "A%20B", "x" * 200, ".hidden"):
        assert web("GET", f"/api/projects/{bad}")[0] == 404
    for q in ("agent=architect&file=../../project.json", "agent=architect&file=project.json", "agent=../x&file=requirements.md",
              "agent=architect&file=/etc/passwd", "agent=coder&file=approvals.log"):
        assert web("GET", f"/api/projects/{pid}/doc?{q}")[0] == 404
    assert web("GET", f"/api/projects/{pid}/doc?agent=architect&file=requirements.md")[0] == 200  # a listed output, not yet written -> empty


def test_the_page_is_served_with_the_token_and_safe_headers(web):
    st, html = web("GET", "/", token=False)
    assert st == 200 and app.TOKEN in html and "__TOKEN__" not in html and "AI SDLC Tracker" in html


# ---------------------------------------------------------------- status from the ledger -----------------------------

def test_status_is_read_from_the_approvals_ledger_not_from_what_anything_says(web, tmp_path):
    pid = new(web)
    briefs = tmp_path / "projects" / pid / "architect/briefs"
    v = view(web, pid)
    assert [s["status"] for s in v["tracks"]["architect"]["steps"]][:2] == ["todo", "todo"] and v["tracks"]["architect"]["next"] == "qualify"
    assert step(v, "architect", "qualify")["ready"] and not step(v, "architect", "discover")["ready"] and len(v["tracks"]["architect"]["steps"]) == 12
    assert len(v["tracks"]["coder"]["steps"]) == 9 and v["tracks"]["coder"]["steps"][-1]["name"] == "handoff"
    (briefs / "opportunity-brief.md").write_text("draft")
    assert step(view(web, pid), "architect", "qualify")["status"] == "draft"
    baseline.log_approval(briefs, "qualify", briefs / "opportunity-brief.md", A.ACCOUNT)
    v = view(web, pid)
    assert step(v, "architect", "qualify")["status"] == "approved" and step(v, "architect", "discover")["ready"] and v["tracks"]["architect"]["next"] == "discover"
    (briefs / "requirements.md").write_text("draft")
    baseline.log_approval(briefs, "discover", briefs / "requirements.md", A.ACCOUNT)  # discover needs two roles
    s = step(view(web, pid), "architect", "discover")
    assert s["status"] == "partial" and s["text"].startswith("Waiting for: Lead solution architect")
    assert [r["approved"] for r in s["roles"]] == [True, False]
    (briefs / "opportunity-brief.md").write_text("edited after approval")
    assert step(view(web, pid), "architect", "qualify")["status"] == "edited"


# ---------------------------------------------------------------- running steps and answering -------------------------

def test_a_step_waits_for_the_person_and_only_their_click_records_the_approval(web, tmp_path):
    pid = new(web)
    assert run(web, pid)[1] == {"started": "qualify"}
    v = awaiting(web, pid)
    assert v["run"]["pending"] == {"role": A.ACCOUNT} and step(v, "architect", "qualify")["status"] == "needs_you"
    time.sleep(0.3)
    assert step(view(web, pid), "architect", "qualify")["status"] == "needs_you"  # it does not approve itself while we wait
    assert not (tmp_path / "projects" / pid / "architect/briefs/approvals.log").exists()  # nothing approved yet
    st, _ = web("POST", f"/api/projects/{pid}/respond", dict(answer="y"))
    assert st == 200
    v = wait(lambda: (lambda v: v if v["run"]["state"] == "done" else None)(view(web, pid)))
    assert step(v, "architect", "qualify")["status"] == "approved" and v["tracks"]["architect"]["next"] == "discover"
    assert any("[you] approved:" in l for l in v["run"]["log"])


def test_sending_a_draft_back_needs_feedback_and_the_agent_redoes_the_step(web, tmp_path):
    pid = new(web)
    run(web, pid)
    awaiting(web, pid)
    st, e = web("POST", f"/api/projects/{pid}/respond", dict(answer="n", feedback="  "))
    assert st == 400 and "Say what should change" in e["error"]
    assert web("POST", f"/api/projects/{pid}/respond", dict(answer="n", feedback="add the risks"))[0] == 200
    v = wait(lambda: (lambda v: v if v["run"]["pending"] and any("Draft number 2" in l or "feedback: add the risks" in l for l in v["run"]["log"]) else None)(view(web, pid)))
    assert (tmp_path / "projects" / pid / "architect/briefs/opportunity-brief.md").read_text().count("Draft number 2") == 1
    assert step(v, "architect", "qualify")["status"] == "needs_you"


def test_each_role_is_asked_separately_and_the_status_shows_who_is_still_needed(web):
    pid = new(web)
    for _ in range(2):  # qualify, then discover (two roles)
        run(web, pid)
        awaiting(web, pid)
        web("POST", f"/api/projects/{pid}/respond", dict(answer="y"))
        wait(lambda: view(web, pid)["run"]["state"] in ("done", "awaiting") and (view(web, pid)["run"]["pending"] or view(web, pid)["run"]["state"] == "done"))
        if view(web, pid)["run"]["pending"]:
            assert view(web, pid)["run"]["pending"]["role"] == A.ARCH and step(view(web, pid), "architect", "discover")["roles"][0]["approved"]
            web("POST", f"/api/projects/{pid}/respond", dict(answer="y"))
            wait(lambda: view(web, pid)["run"]["state"] == "done")
    assert step(view(web, pid), "architect", "discover")["status"] == "approved"


def test_run_all_goes_step_by_step_and_pauses_for_every_approval(web):
    pid = new(web, desc="Our current legacy system has a budget of 50k and 2000 users. " * 60)  # a rich input: no step is suggested for skipping
    run(web, pid, auto=True)
    answered = 0
    while answered < 3:
        v = awaiting(web, pid)
        web("POST", f"/api/projects/{pid}/respond", dict(answer="y"))
        answered += 1
        time.sleep(0.2)
    assert view(web, pid)["tracks"]["architect"]["approved"] >= 2  # it moved on to the next step by itself, but only after each approval
    web("POST", f"/api/projects/{pid}/stop", {})
    assert wait(lambda: view(web, pid)["run"]["state"] == "stopped")


def test_one_run_at_a_time_and_steps_wait_for_their_predecessors(web):
    pid = new(web)
    st, e = run(web, pid, step_="discover")
    assert st == 400 and "earlier step must be approved first" in e["error"]
    assert run(web, pid)[0] == 200
    awaiting(web, pid)
    st, e = run(web, pid)
    assert st == 400 and "already running" in e["error"]
    assert run(web, pid, step_="nonsense")[0] == 400 and run(web, pid, agent="x")[0] == 400


def test_stop_ends_the_step_and_leaves_the_draft_unapproved(web):
    pid = new(web)
    run(web, pid)
    awaiting(web, pid)
    web("POST", f"/api/projects/{pid}/stop", {})
    v = wait(lambda: (lambda v: v if v["run"]["state"] == "stopped" else None)(view(web, pid)))
    assert step(v, "architect", "qualify")["status"] == "draft" and v["run"]["pending"] is None
    assert web("POST", f"/api/projects/{pid}/respond", dict(answer="y"))[0] == 400  # nothing left to approve


def test_a_failing_step_shows_the_error_and_is_not_approved(web, monkeypatch):
    monkeypatch.setenv("FAKE_FAIL", "1")
    pid = new(web)
    run(web, pid)
    v = wait(lambda: (lambda v: v if v["run"]["state"] == "failed" else None)(view(web, pid)))
    assert v["run"]["rc"] == 1 and any("Cannot do this yet" in l for l in v["run"]["log"]) and step(v, "architect", "qualify")["status"] == "todo"


def test_the_real_coder_process_gets_the_workspace_and_reports_its_own_refusal_without_any_model_call(web, tmp_path, monkeypatch):
    # the coder refuses before any model is called when an earlier output is not approved, so this runs the REAL agent safely and offline
    monkeypatch.setattr(app, "build_cmd", lambda agent, step, args: [sys.executable, "-u", str(ROOT / agent / "agent.py"), step, *args])
    pid = new(web)
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    d = tmp_path / "projects" / pid
    r = app.Run(pid, "coder", "inspect", ["--repo", str(repo)])
    wait(lambda: r.state in ("done", "failed"), timeout=30)
    assert r.state == "failed" and any("implementation-plan.md: not produced" in l for l in r.log)
    assert (d / "coder/briefs").is_dir() and not (d / "coder/briefs/repository-inspection.md").exists()


def test_the_workspace_setting_moves_the_agents_outputs_and_defaults_to_the_code_folder(tmp_path):
    code = "import sys; sys.path.insert(0, %r); from %s import agent; print(agent.HERE)"
    for which in ("architect", "coder"):
        env = {k: v for k, v in os.environ.items() if k != "SDLC_WORKSPACE"}
        assert subprocess.run([sys.executable, "-c", code % (str(ROOT), which)], capture_output=True, text=True, env=env).stdout.strip() == str(ROOT / which)
        env["SDLC_WORKSPACE"] = str(tmp_path)
        assert subprocess.run([sys.executable, "-c", code % (str(ROOT), which)], capture_output=True, text=True, env=env).stdout.strip() == str(tmp_path / which)


# ---------------------------------------------------------------- what each step is given ----------------------------

def test_each_step_gets_the_right_files_and_the_coder_never_decides_the_handoff(web, tmp_path):
    pid = new(web)
    web("POST", f"/api/projects/{pid}/docs", dict(name="rfp.md", text="rfp"))
    web("POST", f"/api/projects/{pid}/docs", dict(name="meet.md", text="notes", kind="meeting"))
    p = app.load(pid)
    ins = tmp_path / "projects" / pid / "inputs"
    assert app.step_args(p, "architect", "qualify") == [str(ins / "project-brief.md"), str(ins / "rfp.md")]
    assert app.step_args(p, "architect", "design") == [] and app.step_args(p, "architect", "record") == [str(ins / "meet.md")]
    assert app.step_args(p, "architect", "handoff") == [str(ins / "project-brief.md"), str(ins / "rfp.md"), str(ins / "meet.md")]
    with pytest.raises(ValueError, match="Set the repository"):
        app.step_args(p, "coder", "inspect")
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    p = app.settings(pid, dict(repo=str(repo), checks=["pytest -q"]))
    with pytest.raises(ValueError, match="Paste the approved ticket"):
        app.step_args(p, "coder", "understand")
    p = app.settings(pid, dict(ticket_text="Approved ticket"))
    assert app.step_args(p, "coder", "understand")[0] == str(ins / "ticket.md") and "--repo" in app.step_args(p, "coder", "understand")
    assert app.step_args(p, "coder", "tests") == ["--repo", str(repo.resolve()), "--check", "pytest -q"]
    assert app.step_args(p, "coder", "handoff") == ["--repo", str(repo.resolve()), "--no-decision"]  # the process never decides; a person does
    noted = app.load(pid)
    noted["docs"] = [d for d in noted["docs"] if d["kind"] != "meeting"]
    with pytest.raises(ValueError, match="meeting notes"):
        app.step_args(noted, "architect", "record")


# ---------------------------------------------------------------- the reviewer decision ------------------------------

def handoff_ready(web, tmp_path):
    pid = new(web)
    cb = tmp_path / "projects" / pid / "coder/briefs"
    (cb / "review-report.md").write_text("## Blockers\nNone.\n\n## Scanner findings from code (x)\n| ID | Severity | Kind | Where | Evidence | Why |\n|---|---|---|---|---|---|\n")
    (cb / "test-report.md").write_text(TH.TESTS)
    (cb / "pull-request.md").write_text(TH.PR_GOOD)
    (cb / "handoff-package.md").write_text("# Human handoff: x\n\nBranch `coder/2026` (starting commit `abc123def456`), repository /r.\n")
    return pid, cb


def test_the_reviewer_decision_is_made_by_a_person_on_the_page_with_the_same_rules_as_the_terminal(web, tmp_path):
    pid, cb = handoff_ready(web, tmp_path)
    v = view(web, pid)
    assert v["handoff"]["ready"] and v["handoff"]["counts"].startswith("Open blockers: 0.")
    url = f"/api/projects/{pid}/handoff-decision"
    assert web("POST", url, dict(decision="approve", name="", reason="ok"))[0] == 400  # a name is needed
    assert web("POST", url, dict(decision="maybe", name="Priya", reason="ok"))[0] == 400
    assert web("POST", url, dict(decision="changes", name="Priya", reason=""))[0] == 400
    st, e = web("POST", url, dict(decision="reject", name="Priya", reason=" "))
    assert st == 400 and not (cb / "handoff-decisions.log").exists()
    st, rec = web("POST", url, dict(decision="changes", name="Priya N", reason="AC2 has no failure test"))
    assert st == 200 and rec["decision"] == "changes" and rec["merged_by_agent"] is False and rec["reviewer"] == "Priya N"
    assert not (cb / "approvals.log").exists()  # only an approval is an approval
    st, rec = web("POST", url, dict(decision="approve", name="Priya N", reason="reviewed the diff"))
    assert st == 200 and rec["package_sha256"]
    last = json.loads((cb / "approvals.log").read_text().splitlines()[-1])
    assert last["step"] == "handoff" and last["file"] == "handoff-package.md" and "makes the merge decision" in last["reviewer"]
    assert [d["decision"] for d in view(web, pid)["handoff"]["decisions"]] == ["changes", "approve"]


def test_no_decision_can_be_recorded_before_a_package_exists_or_without_the_token(web, tmp_path):
    pid = new(web)
    st, e = web("POST", f"/api/projects/{pid}/handoff-decision", dict(decision="approve", name="P", reason="x"))
    assert st == 400 and "no handoff package" in e["error"]
    pid, cb = handoff_ready(web, tmp_path)
    assert web("POST", f"/api/projects/{pid}/handoff-decision", dict(decision="approve", name="P", reason="x"), token=False)[0] == 403
    assert not (cb / "handoff-decisions.log").exists()


# ---------------------------------------------------------------- the page itself (found by looking at it) -------------

def page_script():
    import re
    return re.search(r"<script>(.*)</script>", (ROOT / "web" / "index.html").read_text(), re.S).group(1)


def test_the_page_script_is_valid_javascript_and_flattens_nested_lists(tmp_path):
    js = page_script()
    assert "kids.flat(Infinity)" in js and "kids.flat()" not in js  # a one-level flatten printed '[object HTMLElement]' in the Approvals line
    import shutil
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    f = tmp_path / "page.js"
    f.write_text(js)
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_the_page_opens_the_latest_project_and_can_be_linked_to(web):
    assert "location.hash" in page_script() and "items[0]" in page_script()


def test_a_project_can_carry_a_note_that_the_page_shows(web, tmp_path):
    pid = new(web)
    p = app.load(pid)
    assert p["note"] == ""
    p["note"] = "Approvals here were scripted by the assistant."
    app.save(pid, p)
    assert view(web, pid)["project"]["note"].startswith("Approvals here were scripted")
    assert "p.note" in (ROOT / "web" / "index.html").read_text()


def test_the_coders_first_step_is_given_the_architects_baseline_and_requirements_when_they_exist(web, tmp_path):
    pid = new(web)
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    p = app.settings(pid, dict(repo=str(repo), ticket_text="Approved ticket citing R-003"))
    d = tmp_path / "projects" / pid
    before = app.step_args(p, "coder", "understand")
    assert before == [str(d / "inputs/ticket.md"), "--repo", str(repo.resolve())]  # nothing from the architect yet, nothing invented
    for f in ("solution-baseline.md", "requirements.md", "delivery-approach.md"):
        (d / "architect/briefs" / f).write_text("x")
    after = app.step_args(p, "coder", "understand")
    arch = d / "architect/briefs"
    assert after == [str(d / "inputs/ticket.md"), str(arch / "solution-baseline.md"), str(arch / "requirements.md"), "--repo", str(repo.resolve())]
    assert app.step_args(p, "coder", "inspect") == ["--repo", str(repo.resolve())]  # only the first step gets them


def test_the_qa_track_has_ten_steps_runs_from_the_page_and_is_given_the_ticket_and_the_change(web, tmp_path):
    pid = new(web)
    v = view(web, pid)
    assert len(v["tracks"]["qa"]["steps"]) == 10 and v["tracks"]["qa"]["next"] == "scope"
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    p = app.settings(pid, dict(repo=str(repo), ticket_text="AC1: x", checks=["pytest -q"]))
    d = tmp_path / "projects" / pid
    (d / "coder/briefs/pull-request.md").write_text("pr")
    assert app.step_args(p, "qa", "scope") == [str(d / "inputs/ticket.md"), str(d / "coder/briefs/pull-request.md"), "--repo", str(repo.resolve())]
    assert app.step_args(p, "qa", "execute") == ["--repo", str(repo.resolve()), "--check", "pytest -q"]
    assert app.step_args(p, "qa", "recommend") == [] and app.step_args(p, "qa", "design") == ["--repo", str(repo.resolve())]
    assert run(web, pid, agent="qa")[1] == {"started": "scope"}
    awaiting(web, pid)
    web("POST", f"/api/projects/{pid}/respond", dict(answer="y"))
    assert "Developer" in wait(lambda: (lambda v: v["run"]["pending"]["role"] if v["run"]["pending"] and "Developer" in v["run"]["pending"]["role"] else None)(view(web, pid)))


def test_run_all_pauses_before_a_step_that_may_not_be_needed(web):
    pid = new(web)  # a thin input: 'assess' is suggested for skipping
    run(web, pid, auto=True)
    for _ in range(2 + 1):  # qualify (1 role), discover (2 roles)
        awaiting(web, pid)
        web("POST", f"/api/projects/{pid}/respond", dict(answer="y"))
        time.sleep(0.3)
    v = wait(lambda: (lambda v: v if v["run"]["state"] == "done" and any("[auto] paused before assess" in l for l in v["run"]["log"]) else None)(view(web, pid)))
    assert step(v, "architect", "assess")["status"] == "todo" and step(v, "architect", "assess")["suggest"]


def test_the_review_track_has_nine_steps_gets_its_inputs_and_suggests_skips_from_the_change(web, tmp_path):
    pid = new(web)
    v = view(web, pid)
    assert len(v["tracks"]["review"]["steps"]) == 10 and v["tracks"]["review"]["next"] == "context"
    repo = tmp_path / "r"
    (repo / "pkg").mkdir(parents=True)
    for c in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=t@x.invalid", "commit", "-q", "--allow-empty", "-m", "i"]):
        subprocess.run(["git", "-C", str(repo), *c], check=True, capture_output=True)
    (repo / "pkg/new_module.py").write_text("def f():\n    return 1\n")
    p = app.settings(pid, dict(repo=str(repo), ticket_text="AC1: f returns 1"))
    d = tmp_path / "projects" / pid
    (d / "coder/briefs/pull-request.md").write_text("pr")
    assert app.step_args(p, "review", "context") == [str(d / "inputs/ticket.md"), str(d / "coder/briefs/pull-request.md"), "--repo", str(repo.resolve())]
    assert app.step_args(p, "review", "security") == ["--repo", str(repo.resolve())] and app.step_args(p, "review", "report") == []
    ctx = app.context(pid, "review")
    assert ctx["ui"] is False and ctx["all_new"] is True and ctx["interface"] is False
    assert "No user-facing files" in app.suggestion(pid, "review", "accessibility") and "new" in app.suggestion(pid, "review", "interfaces")
    assert app.suggestion(pid, "review", "correctness") == ""
    assert run(web, pid, agent="review")[1] == {"started": "context"}


def test_the_release_track_has_nine_steps_takes_the_release_request_and_commands_need_a_repository(web, tmp_path):
    pid = new(web)
    v = view(web, pid)
    assert len(v["tracks"]["release"]["steps"]) == 9 and v["tracks"]["release"]["next"] == "request"
    assert not any(s["skippable"] for s in v["tracks"]["release"]["steps"])  # a release step is never skipped
    p = app.load(pid)
    with pytest.raises(ValueError, match="release request"):
        app.step_args(p, "release", "request")
    n = web("POST", f"/api/projects/{pid}/docs", dict(name="release-request.md", text="Version: 1.0", kind="release"))[1]
    assert {"name": "release-request.md", "kind": "release"} in n["docs"]
    d = tmp_path / "projects" / pid
    (d / "qa/briefs/qa-recommendation.md").write_text("q")
    p = app.load(pid)
    assert app.step_args(p, "release", "request") == [str(d / "inputs/release-request.md"), str(d / "qa/briefs/qa-recommendation.md")]
    assert app.step_args(p, "release", "readiness") == [] and app.step_args(p, "release", "plan") == [] and app.step_args(p, "release", "close") == []
    for s in ("provenance", "config", "promote", "monitor", "rollback"):
        with pytest.raises(ValueError, match="repository"):
            app.step_args(p, "release", s)  # the release commands must never run in the tool's own folder
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    p = app.settings(pid, dict(repo=str(repo)))
    assert app.step_args(p, "release", "promote") == ["--repo", str(repo.resolve())]


def test_run_all_never_starts_a_promotion(web, monkeypatch):
    pid = new(web)
    run_obj = type("R", (), dict(auto=True, state="done", pid=pid, agent="release", log=[]))()
    monkeypatch.setattr(app, "next_step", lambda p, a: "promote")
    started = []
    monkeypatch.setattr(app.MANAGER, "start", lambda *a, **k: started.append(a))
    app.MANAGER.finished(run_obj)
    assert not started and "never started automatically" in run_obj.log[0]


def test_the_sre_track_has_nine_steps_takes_its_documents_and_never_changes_production_by_default(web, tmp_path):
    pid = new(web)
    v = view(web, pid)
    assert len(v["tracks"]["sre"]["steps"]) == 9 and v["tracks"]["sre"]["next"] == "context" and not any(s["skippable"] for s in v["tracks"]["sre"]["steps"])
    p = app.load(pid)
    for step, word in (("context", "service catalog"), ("health", "metrics snapshot"), ("triage", "incident note"), ("recovery", "metrics snapshot")):
        with pytest.raises(ValueError, match=word):
            app.step_args(p, "sre", step)
    for name, text, kind in (("catalog.md", "Owner: x", "sre"), ("m.csv", "time,metric,value\n", "evidence"), ("e.jsonl", "{}\n", "evidence"), ("l.log", "2026-11-24T09:00:00Z x\n", "evidence"),
                             ("note.md", "checkout failing", "incident"), ("after.csv", "time,metric,value\n", "recovery"), ("p.json", "{}", "policy"), ("a.json", "{}", "allowlist")):
        assert web("POST", f"/api/projects/{pid}/docs", dict(name=name, text=text, kind=kind))[0] == 200
    d, p = tmp_path / "projects" / pid / "inputs", app.load(pid)
    assert app.step_args(p, "sre", "context") == [str(d / "catalog.md")]
    with pytest.raises(ValueError, match="Open an incident"):
        app.step_args(p, "sre", "triage")
    p["incident"] = "INC-20261124-01"
    assert app.step_args(p, "sre", "triage") == [str(d / "note.md"), "--incident", "INC-20261124-01"]
    assert app.step_args(p, "sre", "health") == ["--metrics", str(d / "m.csv"), "--events", str(d / "e.jsonl"), "--logs", str(d / "l.log")]
    assert app.step_args(p, "sre", "recovery") == ["--metrics", str(d / "after.csv"), "--incident", "INC-20261124-01"]
    assert app.step_args(p, "sre", "risks") == [] and app.step_args(p, "sre", "remediate") == ["--incident", "INC-20261124-01"]  # no action requested: read-only
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    p = app.settings(pid, dict(repo=str(repo), actions=["Restart worker pool", ""]))
    assert p["actions"] == ["Restart worker pool"]
    p["incident"] = "INC-20261124-01"
    assert app.step_args(p, "sre", "remediate") == ["--policy", str(d / "p.json"), "--allowlist", str(d / "a.json"), "--repo", str(repo.resolve()), "--action", "Restart worker pool", "--incident", "INC-20261124-01"]
    p["docs"] = [x for x in p["docs"] if x["kind"] != "allowlist"]
    with pytest.raises(ValueError, match="allowlist"):
        app.step_args(p, "sre", "remediate")  # an action is requested but the allowlist is missing: refuse, never improvise


def test_run_all_never_starts_a_production_change_for_the_sre_agent(web, monkeypatch):
    pid = new(web)
    run_obj = type("R", (), dict(auto=True, state="done", pid=pid, agent="sre", log=[]))()
    monkeypatch.setattr(app, "next_step", lambda p, a: "remediate")
    started = []
    monkeypatch.setattr(app.MANAGER, "start", lambda *a, **k: started.append(a))
    app.MANAGER.finished(run_obj)
    assert not started and "never started automatically" in run_obj.log[0]


def test_sre_incident_steps_follow_the_selected_incident_and_the_service_steps_do_not(web, tmp_path):
    pid = new(web)
    v = view(web, pid)
    st = {x["name"]: x for x in v["tracks"]["sre"]["steps"]}
    assert v["incidents"] == [] and st["triage"]["text"] == "Open an incident first" and not st["triage"]["ready"] and st["context"]["text"] != "Open an incident first"
    code, body = web("POST", f"/api/projects/{pid}/incident", dict(title="Checkout errors"))
    assert code == 400 and "service record" in str(body)  # the service record is not approved yet, so an incident cannot be opened
    assert web("POST", f"/api/projects/{pid}/incident", dict(select="INC-1"))[0] == 400
    inc = tmp_path / "projects" / pid / "sre" / "incidents" / "INC-20261124-01"
    (inc / "briefs").mkdir(parents=True)
    (inc / "incident.json").write_text(json.dumps(dict(id="INC-20261124-01", title="Checkout errors", status="open")))
    (inc / "briefs" / "incident-triage.md").write_text("## Status\nDraft.\n")
    assert web("POST", f"/api/projects/{pid}/incident", dict(select="INC-20261124-01"))[0] == 200
    v = view(web, pid)
    st = {x["name"]: x for x in v["tracks"]["sre"]["steps"]}
    assert v["incidents"][0]["title"] == "Checkout errors" and v["project"]["incident"] == "INC-20261124-01" and st["triage"]["produced"] and st["triage"]["text"] != "Open an incident first"
    assert web("GET", f"/api/projects/{pid}/doc?agent=sre&file=incident-triage.md")[1]["text"].startswith("## Status")
    assert web("GET", f"/api/projects/{pid}/doc?agent=sre&file=service-context.md")[1]["text"] == ""  # service files are read from the service folder


def test_the_page_follows_the_pipeline_in_the_image_with_stages_and_human_checkpoints(web):
    v = view(web, new(web))
    pl = v["pipeline"]
    assert [s["agent"] for s in pl] == ["triage", "architect", "coder", "qa", "review", "release", "sre"]  # QA before Review, as drawn
    assert [s["stage"] for s in pl] == ["Plan", "Design", "Build", "Test", "Review", "Deploy", "Operate"]
    assert all(s["built"] for s in pl) and all(s["agent"] in v["tracks"] for s in pl if s["built"])
    by = {s["agent"]: s for s in pl}
    assert "Product owner" in by["triage"]["checkpoint"] and "Release manager" in by["release"]["checkpoint"] and "On-call engineer" in by["sre"]["checkpoint"]
    assert "On-call engineer" in by["sre"]["signers"] and "Release Manager" in by["release"]["signers"]


def test_the_triage_track_takes_issues_and_feeds_in_the_selected_incidents_sre_follow_ups(web, tmp_path):
    pid = new(web)
    v = view(web, pid)
    assert [s["name"] for s in v["tracks"]["triage"]["steps"]] == ["import", "readiness", "prioritize", "scope"] and v["tracks"]["triage"]["next"] == "import"
    p = app.load(pid)
    with pytest.raises(ValueError, match="Add the issues first"):
        app.step_args(p, "triage", "import")
    assert web("POST", f"/api/projects/{pid}/docs", dict(name="issues.csv", text="id,title\nA-1,x\n", kind="issues"))[0] == 200
    d = tmp_path / "projects" / pid
    p = app.load(pid)
    assert app.step_args(p, "triage", "import") == [str(d / "inputs" / "issues.csv")] and app.step_args(p, "triage", "readiness") == []
    rev = d / "sre" / "incidents" / "INC-20261124-01" / "briefs"
    rev.mkdir(parents=True)
    (rev / "incident-review.md").write_text("## Follow-up actions\n")
    p["incident"] = "INC-20261124-01"
    assert app.step_args(p, "triage", "import")[-2:] == ["--sre-review", str(rev / "incident-review.md")]


def test_usage_is_summed_per_agent_and_step_from_the_projects_usage_log(web, tmp_path):
    pid = new(web)
    assert view(web, pid)["usage"] == dict(agents={}, total=dict(calls=0, tokens_in=0, tokens_out=0, usd=0.0))
    rows = [dict(agent="sre", step="sre:triage", input=4, cache_write=100, cache_read=50, output=20, usd=0.1, secs=10.0),
            dict(agent="sre", step="sre:triage", input=1, cache_write=0, cache_read=9, output=5, usd=0.05, secs=2.5),
            dict(agent="triage", step="triage:prioritize", input=2, cache_write=3, cache_read=5, output=7, usd=0.02, secs=1.0)]
    (tmp_path / "projects" / pid / "usage.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    u = view(web, pid)["usage"]
    assert u["agents"]["sre"]["calls"] == 2 and u["agents"]["sre"]["tokens_in"] == 164 and u["agents"]["sre"]["tokens_out"] == 25 and u["agents"]["sre"]["usd"] == 0.15
    assert u["agents"]["sre"]["steps"]["sre:triage"]["calls"] == 2 and list(u["agents"]["triage"]["steps"]) == ["triage:prioritize"]
    assert u["total"] == dict(calls=3, tokens_in=174, tokens_out=32, usd=0.17)


def test_the_review_track_has_a_disposition_step_that_needs_the_tech_leads_file(web):
    pid = new(web)
    v = view(web, pid)
    assert [s["name"] for s in v["tracks"]["review"]["steps"]][-1] == "disposition"
    p = app.load(pid)
    with pytest.raises(ValueError, match="Add the tech lead's decisions first"):
        app.step_args(p, "review", "disposition")
    assert web("POST", f"/api/projects/{pid}/docs", dict(name="d.json", text="[]", kind="waiver"))[0] == 200
    p = app.load(pid)
    assert app.step_args(p, "review", "disposition")[0] == "--dispositions"


def test_disposition_needs_no_file_when_the_report_routes_nothing(web, tmp_path):
    pid = new(web)
    rb = tmp_path / "projects" / pid / "review" / "briefs"
    rb.mkdir(parents=True, exist_ok=True)
    (rb / "review-report.md").write_text("## Routed for human disposition (Critical and High findings still standing)\nNone. No Critical or High finding is standing.\n## Review coverage\n")
    assert app.step_args(app.load(pid), "review", "disposition") == []
    (rb / "review-report.md").write_text("## Routed for human disposition (x)\n- **C1** (High, Confirmed, S): b | i | src/a.py:1\n## Review coverage\n")
    with pytest.raises(ValueError, match="Add the tech lead's decisions first"):
        app.step_args(app.load(pid), "review", "disposition")


def test_the_release_plan_gets_the_aws_profile_when_one_is_added(web, tmp_path):
    pid = new(web)
    p = app.load(pid)
    assert app.step_args(p, "release", "plan") == []
    assert web("POST", f"/api/projects/{pid}/docs", dict(name="aws.json", text="{}", kind="aws"))[0] == 200
    d = tmp_path / "projects" / pid / "inputs"
    assert app.step_args(app.load(pid), "release", "plan") == ["--aws-profile", str(d / "aws.json")]


def report_with(tmp_path, pid, body):
    rb = tmp_path / "projects" / pid / "review" / "briefs"
    rb.mkdir(parents=True, exist_ok=True)
    (rb / "review-report.md").write_text("## Routed for human disposition (Critical and High findings still standing)\n" + body + "\n## Review coverage\n")


ROUTED = "- **C1** (High, Confirmed, S): the check is skipped | impact | src/app.py:2\n- **Scanner** (Critical) `src/new.py:1`: secret, key in code\n"
WHY = "The check is skipped only behind a flag that stays off until the fix ships next sprint, and an alert fires on any use of it."


def test_the_decision_form_lists_the_routed_findings_and_saves_only_decisions_the_review_rules_accept(web, tmp_path):
    pid = new(web)
    assert view(web, pid)["routed"] == []
    assert web("POST", f"/api/projects/{pid}/dispositions", dict(entries=[]))[0] == 400  # nothing is routed yet
    report_with(tmp_path, pid, ROUTED)
    v = view(web, pid)
    assert [(x["id"], x["severity"]) for x in v["routed"]] == [("C1", "High"), ("Scanner src/new.py:1", "Critical")] and "the check is skipped" in v["routed"][0]["text"] and "secret, key in code" in v["routed"][1]["text"]
    soon = (__import__("datetime").date.today() + __import__("datetime").timedelta(days=5)).isoformat()
    code, body = web("POST", f"/api/projects/{pid}/dispositions", dict(entries=[dict(finding="C1", decision="waive", reason="too short", expires=soon)]))
    assert code == 400 and "at least 12 words" in str(body)
    code, body = web("POST", f"/api/projects/{pid}/dispositions", dict(entries=[dict(finding="C1", decision="fix", reason="The wrong result appears only for input that the caller already guards against and tests.")]))
    assert code == 400 and "does not mention anything from this finding" in str(body)
    code, body = web("POST", f"/api/projects/{pid}/dispositions", dict(entries=[dict(finding="ZZ", decision="fix", reason=WHY)]))
    assert code == 400 and "not a routed finding" in str(body)
    code, body = web("POST", f"/api/projects/{pid}/dispositions", dict(entries=[dict(finding="C1", decision="waive", reason=WHY, expires=soon), dict(finding="Scanner src/new.py:1", decision="", reason="")]))
    assert code == 200 and body == dict(saved=1, undecided=["Scanner src/new.py:1"])
    v = view(web, pid)
    assert v["dispositions"][0]["finding"] == "C1" and any(d["kind"] == "waiver" and d["name"] == "dispositions.json" for d in v["project"]["docs"])
    assert app.step_args(app.load(pid), "review", "disposition") == ["--dispositions", str(tmp_path / "projects" / pid / "inputs" / "dispositions.json")]


def test_the_form_file_is_exactly_what_the_disposition_step_reads(web, tmp_path):
    pid = new(web)
    report_with(tmp_path, pid, ROUTED)
    soon = (__import__("datetime").date.today() + __import__("datetime").timedelta(days=5)).isoformat()
    web("POST", f"/api/projects/{pid}/dispositions", dict(entries=[dict(finding="C1", decision="waive", reason=WHY, expires=soon)]))
    saved = json.loads((tmp_path / "projects" / pid / "inputs" / "dispositions.json").read_text())
    assert saved == [dict(finding="C1", decision="waive", reason=WHY, expires=soon)] and app.review_agent.check_entry(saved[0], "High") == ""


def test_the_page_gets_the_waivers_with_their_days_left(web, tmp_path):
    pid = new(web)
    assert view(web, pid)["waivers"] == []
    rb = tmp_path / "projects" / pid / "review" / "briefs"
    rb.mkdir(parents=True, exist_ok=True)
    (rb / "review-report.md").write_text("r")
    soon = (__import__("datetime").date.today() + __import__("datetime").timedelta(days=2)).isoformat()
    (rb / "dispositions.json").write_text(json.dumps(dict(report_sha256="x", entries=[dict(finding="C1", severity="High", decision="waive", reason="r", expires=soon, second_approval=False)])))
    w = view(web, pid)["waivers"]
    assert w[0]["finding"] == "C1" and w[0]["days_left"] == 2 and w[0]["state"] == "expiring" and w[0]["counts"] is False  # not approved, and the report hash differs
