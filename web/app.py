#!/usr/bin/env python3
"""Web page for the Architect, Coder, Review and QA agents (local, standard library only).

  python web/app.py [--port 8765] [--no-open]

A person enters the project information once, then follows four tracks (Architect 12 steps, Coder 9, Review 9, QA 10), and approves or sends
back each draft in the browser. The page does NOT replace the agents or their guardrails: every step still runs as the same CLI process
(`architect/agent.py`, `coder/agent.py`, `review/agent.py`, `qa/agent.py`) in a per-project workspace (SDLC_WORKSPACE), and the page only answers the `approve? [y/N]` prompt
when a person clicks. Status comes from the approvals ledger (the same check the agents use), never from what a model says.

Safety: it listens on 127.0.0.1 only, checks the Host and Origin headers, and needs a random token (embedded in the page) on every change,
so another web page in your browser cannot approve anything. Nothing here is a login: anyone who can use this computer's browser session
can approve. Documents are served only from a fixed list of file names inside the project.
"""
import base64
import hmac
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from architect import agent as architect_agent, baseline  # noqa: E402
from coder import agent as coder_agent, handoff  # noqa: E402
from qa import agent as qa_agent  # noqa: E402
from release import agent as release_agent  # noqa: E402
from sre import agent as sre_agent  # noqa: E402
from review import agent as review_agent  # noqa: E402
import skipplan  # noqa: E402
from coder import adapters  # noqa: E402

PROJECTS = pathlib.Path(os.environ.get("SDLC_PROJECTS") or ROOT / "projects")
MODS = {"architect": architect_agent, "coder": coder_agent, "review": review_agent, "qa": qa_agent, "release": release_agent, "sre": sre_agent}
NEVER_AUTO = {("release", "promote"), ("sre", "remediate")}  # "Run all" never starts a production change; a person starts it, then authorizes the exact commands
ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,70}$")
UPLOAD_EXT = {".md", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".csv", ".json", ".jsonl", ".log", ".yaml", ".yml", ".html"}
DOC_KINDS = ("meeting", "release", "sre", "evidence", "incident", "allowlist", "policy", "recovery")
MAX_UPLOAD = 5_000_000
MAX_BODY = 12_000_000
TOKEN = secrets.token_urlsafe(24)
LOCK = threading.RLock()

LABELS = {
    "architect": {"qualify": "Qualify the opportunity", "discover": "Discover requirements", "assess": "Assess the current environment",
                  "options": "Solution options", "design": "Target architecture", "fit": "Enterprise fit (security, compliance)",
                  "delivery": "Delivery approach", "economics": "Rough-order-of-magnitude estimate", "proposal": "Proposal package",
                  "discuss": "Client discussion pack", "record": "Record the client meeting", "handoff": "Solution baseline handoff"},
    "coder": {"understand": "Understand the work", "inspect": "Inspect the repository", "detect": "Detect the technology stack",
              "plan": "Plan the change", "implement": "Implement the change", "tests": "Developer tests and local checks",
              "review": "Review the change", "pr": "Prepare the pull request", "handoff": "Human handoff to the reviewer"},
    "review": {"context": "Establish review context", "correctness": "Correctness and design fit", "interfaces": "Interfaces and compatibility",
               "security": "Security and privacy", "reliability": "Reliability and performance", "accessibility": "Accessibility and usability",
               "cost": "Cost and compliance implications", "verify": "Verify the findings", "report": "Findings and scorecard"},
    "qa": {"scope": "Review requirements and scope", "risk": "Assess quality risk", "coverage": "Select test coverage", "design": "Design scenarios and data",
           "automate": "Create automated tests", "execute": "Execute and analyze tests", "explore": "Exploratory and regression testing",
           "nonfunctional": "Non-functional quality", "defects": "Report and track defects", "recommend": "Quality recommendation"},
    "release": {"request": "Receive the release request", "readiness": "Check release readiness", "plan": "Prepare the release plan", "provenance": "Verify artifact and provenance",
                "config": "Validate target configuration", "promote": "Execute authorized promotion", "monitor": "Monitor rollout health", "rollback": "Roll back or recover",
                "close": "Close the release"},
    "sre": {"context": "Service: establish context", "health": "Service: observe health", "risks": "Service: detect risks", "triage": "Incident: triage",
            "recommend": "Incident: recommend actions", "remediate": "Incident: authorized remediation", "updates": "Incident: updates", "recovery": "Incident: recovery and closure",
            "review": "Incident: learn and improve"}}
SOURCE_STEPS = {"qualify", "discover", "assess", "options", "fit", "economics", "proposal"}  # architect steps that read the source documents
READABLE = {"architect": {v[1] for v in architect_agent.STEPS.values()},
            "coder": {v[1] for v in coder_agent.STEPS.values()} | {"change.diff", "handoff-decisions.log"},
            "review": {v[1] for v in review_agent.STEPS.values()} | {"change.diff", "review-areas.md"},
            "qa": {v[1] for v in qa_agent.STEPS.values()},
            "release": {v[1] for v in release_agent.STEPS.values()},
            "sre": {v[1] for v in sre_agent.STEPS.values()} | {"review-facts.md"}}


# ------------------------------------------------------------------------------------------------ projects

def pdir(pid):
    if not ID.match(pid or ""):
        raise KeyError("no such project")
    d = PROJECTS / pid
    if not (d / "project.json").exists():
        raise KeyError("no such project")
    return d


def load(pid):
    return json.loads((pdir(pid) / "project.json").read_text())


def save(pid, data):
    with LOCK:
        (pdir(pid) / "project.json").write_text(json.dumps(data, indent=1))


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9._-]", "_", pathlib.Path(name or "").name)[:80]


def create(data):
    name, desc = (data.get("name") or "").strip(), (data.get("description") or "").strip()
    if not 1 <= len(name) <= 80:
        raise ValueError("Give the project a name (up to 80 characters).")
    if len(desc) < 10:
        raise ValueError("Describe the project in at least a sentence: what it does, for whom, any constraints you know.")
    pid = (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "project") + "-" + secrets.token_hex(2)
    d = PROJECTS / pid
    for sub in ("inputs", "architect/briefs", "architect/baseline", "coder/briefs", "qa/briefs"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    (d / "inputs/project-brief.md").write_text(
        f"# Project description (supplied by the user)\n\nSource: entered on the web page by the user. Nothing else is known about the client, "
        f"the industry, the environment, the budget or the timeline unless a document says so. Anything not stated here is not known.\n\n## {name}\n\n{desc}\n")
    p = dict(id=pid, name=name, description=desc, created=datetime.now(timezone.utc).isoformat(timespec="seconds"), repo="", ticket=False,
             checks=[], note="", docs=[dict(name="project-brief.md", kind="source")])
    (d / "project.json").write_text(json.dumps(p, indent=1))
    return p


def add_doc(pid, data):
    p, d = load(pid), pdir(pid)
    name = safe_name(data.get("name"))
    if pathlib.Path(name).suffix.lower() not in UPLOAD_EXT:
        raise ValueError(f"Files of type '{pathlib.Path(name).suffix or 'none'}' are not accepted. Use: {', '.join(sorted(UPLOAD_EXT))}.")
    if name in ("project-brief.md", "ticket.md", "project.json"):
        raise ValueError("That file name is reserved. Rename the file.")
    raw = base64.b64decode(data["b64"], validate=True) if data.get("b64") else (data.get("text") or "").encode()
    if not raw:
        raise ValueError("The file is empty.")
    if len(raw) > MAX_UPLOAD:
        raise ValueError("The file is larger than 5 MB.")
    kind = data.get("kind") if data.get("kind") in DOC_KINDS else "source"
    (d / "inputs" / name).write_bytes(raw)
    p["docs"] = [x for x in p["docs"] if x["name"] != name] + [dict(name=name, kind=kind)]
    save(pid, p)
    return p


def settings(pid, data):
    p = load(pid)
    if "repo" in data:
        repo = (data["repo"] or "").strip()
        if repo:
            r = pathlib.Path(repo).expanduser()
            if not r.is_dir() or subprocess.run(["git", "-C", str(r), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True,
                                                stdin=subprocess.DEVNULL).stdout.strip() != "true":
                raise ValueError("The repository path must be an existing folder that is a git repository.")
            repo = str(r.resolve())
        p["repo"] = repo
    if "ticket_text" in data:
        text = (data["ticket_text"] or "").strip()
        if text:
            (pdir(pid) / "inputs/ticket.md").write_text(text + "\n")
        p["ticket"] = bool(text) or p["ticket"]
    if "actions" in data:
        p["actions"] = [c.strip()[:200] for c in data["actions"] if isinstance(c, str) and c.strip()][:5]
    if "checks" in data:
        p["checks"] = [c.strip()[:200] for c in data["checks"] if isinstance(c, str) and c.strip()][:10]
    save(pid, p)
    return p


# ------------------------------------------------------------------------------------------------ status

def classify(problems):
    """The ledger's own verdict for one step, as (code, text)."""
    text = " | ".join(problems)
    if not problems:
        return "approved", "Approved"
    if "not produced" in text:
        return "todo", "Not started"
    if "not approved" in text:
        return "draft", "Draft written, waiting for approval"
    if "awaiting sign-off" in text:
        return "partial", "Waiting for: " + ", ".join(m.split(" (")[0] for m in re.findall(r"awaiting sign-off from ([^(]*\([^)]*\))", text))
    if "edited after" in text:
        return "edited", "Edited after it was approved: run it again"
    return "stale", "Out of date: an earlier step was approved again"


# The pipeline as drawn in SDLC_AI.png: agent, SDLC stage, what the agent does and the human checkpoint. QA comes before Review; Release needs both.
PIPELINE = [("triage", "Triage Agent", "Plan", "Scores issue readiness", "Product owner approves scope"),
            ("architect", "Architect Agent", "Design", "Drafts the spec", "Tech lead signs off on design"),
            ("coder", "Coding Agent", "Build", "Writes code, opens the PR", "Auto retry: loops until all checks pass (bounded here, then a person decides)"),
            ("qa", "QA Agent", "Test", "Writes and runs tests", "Auto retry: failing checks are rerun to expose flaky ones"),
            ("review", "Review Agent", "Review", "First-pass PR review", "Engineer approves the PR"),
            ("release", "Release Agent", "Deploy", "Rolls out behind flags", "Release manager approves the production release"),
            ("sre", "SRE Agent", "Operate", "Watches SLOs, triages incidents", "On-call engineer owns incidents")]


def pipeline():
    def roles(agent):
        mod = MODS.get(agent)
        names = []
        for v in (mod.STEPS.values() if mod else []):
            for r in (v[2] if isinstance(v[2], list) else [v[2]]):
                n = r.split(" (")[0]
                if n not in names:
                    names.append(n)
        return names
    return [dict(agent=a, name=n, stage=st, does=d, checkpoint=c, built=a in MODS, signers=roles(a)) for a, n, st, d, c in PIPELINE]


def briefs_of(pid, agent, step=None):
    """Where a step's files are. The SRE service record is shared; each SRE incident has its own folder, and the selected one is used. None: no incident yet."""
    d = pdir(pid) / agent
    if agent != "sre":
        return d / "briefs"
    if step in sre_agent.SERVICE_STEPS:
        return d / "service" / "briefs"
    inc = load(pid).get("incident")
    return d / "incidents" / inc / "briefs" if inc and (d / "incidents" / inc / "incident.json").exists() else None


def sre_incidents(pid):
    root = pdir(pid) / "sre" / "incidents"
    return [json.loads((f).read_text()) | {"id": f.parent.name} for f in sorted(root.glob("INC-*/incident.json"))] if root.exists() else []


def steps_status(pid, agent):
    mod, out = MODS[agent], []
    for name, (_, file, reviewers, prior) in mod.STEPS.items():
        roles = reviewers if isinstance(reviewers, list) else [reviewers]
        briefs = briefs_of(pid, agent, name)
        if briefs is None:
            out.append(dict(name=name, label=LABELS[agent][name], file=file, status="todo", text="Open an incident first", ready=False, produced=False,
                            roles=[dict(role=r, approved=False) for r in roles], skippable=False, suggest=""))
            continue
        code, text = classify(baseline.problems(briefs, {name: mod.STEPS[name]}))
        ready = not baseline.problems(briefs, {s: v for s, v in mod.STEPS.items() if v[1] in prior})
        sha = baseline.latest(briefs).get(file, {}).get("sha256")
        signed = baseline.signed_roles(briefs, file, sha) if sha and (briefs / file).exists() and baseline.sha256(briefs / file) == sha else []
        sk = baseline.skipped(briefs, file) if code == "approved" else None
        if sk:
            code, text = "skipped", f"Skipped by {sk['reviewer'][len('SKIPPED by '):]}: {sk['reason']}"
        skippable = name in skipplan.SKIPPABLE.get(agent, []) and code in ("todo", "draft", "partial", "edited", "stale")
        out.append(dict(name=name, label=LABELS[agent][name], file=file, status=code, text=text, ready=ready, produced=(briefs / file).exists(),
                        roles=[dict(role=r, approved=r in signed) for r in roles], skippable=skippable,
                        suggest=suggestion(pid, agent, name) if skippable and ready and code == "todo" else ""))
    return out


_SUG = {}  # (pid, agent, step) -> (time, reason): the rules read files and scan a repository, so do not repeat that on every poll


def context(pid, agent):
    p, d = load(pid), pdir(pid)
    rd = lambda f: (f.read_text() if f.exists() else "")
    ctx = dict(src="\n".join(rd(d / "inputs" / x["name"]) for x in p["docs"] if x["kind"] == "source"),
               meetings=sum(x["kind"] == "meeting" for x in p["docs"]))
    if agent == "coder" and p["repo"] and pathlib.Path(p["repo"]).is_dir():
        pl = adapters.plan(p["repo"])
        ctx.update(stacks=[x["name"] for x in pl["stacks"]], gaps=pl["gaps"], unsupported=pl["unsupported"])
    if agent == "review" and p["repo"] and pathlib.Path(p["repo"]).is_dir():
        from coder import diffscan
        diff = review_agent.change_diff(p["repo"])
        files = review_agent.changed_files(diff)
        src = [f for f in files if not qa_agent.C.is_test_path(f)]
        ctx.update(diff=diff, ui=any(review_agent.UI_FILES.search(f) for f in files), interface=any(diffscan.is_interface(f) or f.rsplit("/", 1)[-1] in
                   ("package.json", "requirements.txt", "pyproject.toml", "go.mod", "pom.xml") for f in files), all_new=bool(src) and all(review_agent.is_new_file(diff, f) for f in src),
                   costly=any(re.search(r"(?i)(dockerfile|\.tf$|terraform|cloudformation|serverless|\.ya?ml$|requirements|package\.json|pom\.xml|go\.mod|pyproject)", f) for f in files),
                   compliance=bool(re.search(r"(?i)gdpr|hipaa|pci|soc ?2|iso ?27001|compliance|retention|audit", ctx["src"] + rd(d / "inputs" / "ticket.md"))))
    if agent == "qa":
        qb = d / "qa" / "briefs"
        ctx["scope"] = rd(qb / "test-scope.md") + rd(qb / "risk-plan.md") if (qb / "test-scope.md").exists() else None
        ctx["high"] = bool(re.search(r"\bHigh\b", rd(qb / "risk-plan.md")))
        if p["repo"] and pathlib.Path(p["repo"]).is_dir():
            r = p["repo"]
            files = set(qa_agent.C.git(r, "diff", "--name-only", "HEAD")[1].splitlines()) | qa_agent.C.untracked(r)
            lines = sum(len((pathlib.Path(r) / f).read_text(errors="ignore").splitlines()) for f in files if (pathlib.Path(r) / f).is_file())
            ctx["changed"] = (len(files), lines)
    return ctx


def suggestion(pid, agent, step):
    key, now = (pid, agent, step), time.time()
    if key in _SUG and now - _SUG[key][0] < 20:
        return _SUG[key][1]
    try:
        reason = skipplan.suggest(agent, step, context(pid, agent))
    except Exception:  # a suggestion must never break the page
        reason = ""
    _SUG[key] = (now, reason)
    return reason


def skip(pid, data):
    """A person confirms that a step is not needed. Code writes the placeholder and pins it in the ledger; no model runs."""
    agent, step = data.get("agent"), data.get("step")
    name, reason = (data.get("name") or "").strip(), (data.get("reason") or "").strip()
    if step not in skipplan.SKIPPABLE.get(agent, []):
        raise ValueError("This step cannot be skipped.")
    if len(name) < 2 or len(reason) < 8:
        raise ValueError("Give your name and a reason (a sentence) for skipping this step.")
    if MANAGER.active(pid):
        raise ValueError("A step is running for this project. Answer it or stop it first.")
    st = next(x for x in steps_status(pid, agent) if x["name"] == step)
    if not st["ready"]:
        raise ValueError("An earlier step must be approved first.")
    mod, briefs = MODS[agent], pdir(pid) / agent / "briefs"
    out = briefs / mod.STEPS[step][1]
    briefs.mkdir(parents=True, exist_ok=True)
    if out.exists():  # whatever was there is kept
        (briefs / "history").mkdir(exist_ok=True)
        shutil.copy2(out, briefs / "history" / f"{out.stem}.{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.md")
    rule = st["suggest"] or skipplan.suggest(agent, step, context(pid, agent))
    out.write_text(skipplan.placeholder(step, name, reason, rule, datetime.now(timezone.utc).strftime("%Y-%m-%d")))
    baseline.log_skip(briefs, step, out, name, reason)
    _SUG.clear()
    return {"skipped": step}


def next_step(pid, agent):
    for s in steps_status(pid, agent):
        if s["status"] not in ("approved", "skipped"):
            return s["name"] if s["ready"] else None
    return None


def step_args(p, agent, step):
    d = pdir(p["id"]) / "inputs"
    src = [str(d / x["name"]) for x in p["docs"] if x["kind"] == "source"]
    notes = [str(d / x["name"]) for x in p["docs"] if x["kind"] == "meeting"]
    if agent == "architect":
        if step in SOURCE_STEPS:
            return src
        if step == "record":
            if not notes:
                raise ValueError("Add the client meeting notes first (use 'Add meeting notes'). If there was no meeting, add a note that says so.")
            return notes
        return src + notes if step == "handoff" else []
    if agent == "sre":
        args = sre_args(p, d, step)
        if step not in sre_agent.SERVICE_STEPS:
            if not p.get("incident"):
                raise ValueError("Open an incident first (the SRE card has an Open incident button).")
            args += ["--incident", p["incident"]]
        return args
    return step_args_rest(p, agent, step, d, src, notes)


def sre_args(p, d, step):
    of = lambda kind: [str(d / x["name"]) for x in p["docs"] if x["kind"] == kind]
    if step == "context":
        if not of("sre"):
            raise ValueError("Add the service catalog entry first (under Documents, add it as 'SRE service document'; add runbooks, SLOs and alert rules the same way).")
        return of("sre")
    if step in ("health", "recovery"):
        ev = of("evidence" if step == "health" else "recovery")
        if not any(f.endswith(".csv") for f in ev):
            raise ValueError("Add a metrics snapshot first (a .csv with time,metric,value) as " + ("'SRE evidence'." if step == "health" else "'SRE recovery evidence' (a newer snapshot taken after the action)."))
        return [a for f in ev for a in ((("--metrics" if f.endswith(".csv") else "--events" if f.endswith(".jsonl") else "--logs"), f))]
    if step == "triage":
        if not of("incident"):
            raise ValueError("Add the incident note first (under Documents, add it as 'SRE incident note').")
        return of("incident")
    if step == "remediate":
        acts = [a for a in p.get("actions", []) if a]
        pol, al = of("policy"), of("allowlist")
        if not acts:
            return []  # read-only: nothing is requested, so nothing is changed
        if not (pol and al and p["repo"]):
            raise ValueError("To authorize an action, add a policy and an allowlist (as 'SRE policy' and 'SRE allowlist') and set the repository folder: the action's command runs there.")
        return ["--policy", pol[0], "--allowlist", al[0], "--repo", p["repo"], *[a for x in acts for a in ("--action", x)]]
    return []


def step_args_rest(p, agent, step, d, src, notes):
    if agent == "release":
        if step in ("request",):
            asks = [str(d / x["name"]) for x in p["docs"] if x["kind"] == "release"]
            if not asks:
                raise ValueError("Add the release request first (under Documents, add it as 'Release request').")
            more = [str(pdir(p["id"]) / a / "briefs" / f) for a, f in (("coder", "pull-request.md"), ("qa", "qa-recommendation.md"), ("review", "review-report.md")) if (pdir(p["id"]) / a / "briefs" / f).exists()]
            return asks + more
        if step in ("provenance", "config", "promote", "monitor", "rollback"):
            if not p["repo"]:
                raise ValueError("Set the repository folder first (under 'Coder setup'): the release commands run there.")
            return ["--repo", p["repo"]]
        return ["--repo", p["repo"]] if p["repo"] and step in ("readiness", "plan") else []  # the repository is evidence for which release targets apply
    if agent in ("qa", "review") and step in ("recommend", "report"):
        return []
    if not p["repo"]:
        raise ValueError("Set the repository the coder should work in (under 'Coder setup').")
    repo = ["--repo", p["repo"]]
    if agent == "review":
        if step != "context":
            return repo
        if not p["ticket"]:
            raise ValueError("Paste the approved ticket first (under 'Coder setup').")
        cb, ab = pdir(p["id"]) / "coder" / "briefs", pdir(p["id"]) / "architect" / "briefs"  # the change's design and pull request, when they exist
        more = [str(b / f) for b, f in ((cb, "pull-request.md"), (cb, "change-plan.md"), (ab, "solution-baseline.md")) if (b / f).exists()]
        return [str(d / "ticket.md"), *more, *repo]
    if agent == "qa":
        if step == "scope":
            if not p["ticket"]:
                raise ValueError("Paste the approved ticket first (under 'Coder setup').")
            cb = pdir(p["id"]) / "coder" / "briefs"  # the change details the QA agent reviews, when the Coder has produced them
            return [str(d / "ticket.md"), *[str(cb / f) for f in ("pull-request.md", "change-plan.md") if (cb / f).exists()], *repo]
        return repo + ([a for c in p["checks"] for a in ("--check", c)] if step == "execute" else [])
    if step == "understand":
        if not p["ticket"]:
            raise ValueError("Paste the approved ticket first (under 'Coder setup').")
        # the ticket cites the architect's requirement IDs, so the approved-or-not baseline and requirements are supplied as design input
        arch = [str(pdir(p["id"]) / "architect" / "briefs" / f) for f in ("solution-baseline.md", "requirements.md")
                if (pdir(p["id"]) / "architect" / "briefs" / f).exists()]
        return [str(d / "ticket.md"), *[x for x in src if not x.endswith("project-brief.md")], *arch, *repo]
    if step == "tests":
        return repo + [a for c in p["checks"] for a in ("--check", c)]
    if step == "handoff":
        return repo + ["--no-decision"]  # the decision is made by a person on the page, never by the process
    return repo


def build_cmd(agent, step, args):
    return [sys.executable, "-u", str(ROOT / agent / "agent.py"), step, *args]


# ------------------------------------------------------------------------------------------------ runs

APPROVE = re.compile(r"\[([^\n]*)\] approve\? \[y/N\] $")


class Run:
    """One agent step running as a child process. It stops at each `approve? [y/N]` prompt until a person answers on the page."""

    def __init__(self, pid, agent, step, args, auto=False):
        self.pid, self.agent, self.step, self.auto = pid, agent, step, auto
        self.state, self.pending, self.log, self.rc, self.buf = "running", None, [], None, ""
        self.started = time.time()
        env = dict(os.environ, SDLC_WORKSPACE=str(pdir(pid)), PYTHONUNBUFFERED="1")
        self.proc = subprocess.Popen(build_cmd(agent, step, args), cwd=str(pdir(pid)), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, bufsize=0)
        threading.Thread(target=self._read, daemon=True).start()

    def _lines(self, text):
        for line in text.splitlines():
            if line.strip():
                self.log.append(line[:600])
        del self.log[:-400]

    def _read(self):
        fd = self.proc.stdout.fileno()
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            with LOCK:
                self.buf += chunk.decode(errors="replace")
                *done, self.buf = self.buf.split("\n")
                self._lines("\n".join(done))
                if (m := APPROVE.search(self.buf)):
                    self.pending, self.state = dict(role=m.group(1)), "awaiting"
        self.rc = self.proc.wait()
        with LOCK:
            self._lines(self.buf)
            self.buf, self.pending = "", None
            if self.state != "stopped":
                self.state = "done" if self.rc == 0 else "failed"
        MANAGER.finished(self)

    def respond(self, answer, feedback=""):
        with LOCK:
            if not self.pending:
                raise ValueError("Nothing is waiting for an answer.")
            self.log.append(f"[you] {'approved' if answer == 'y' else 'sent back'}: {self.pending['role']}"
                            + (f" ({' '.join(feedback.split())[:200]})" if answer == "n" else ""))
            self.pending, self.buf, self.state = None, "", "running"
            self.proc.stdin.write((answer + "\n").encode())
            if answer == "n":
                self.proc.stdin.write((" ".join(feedback.split()) or "Please revise.").encode() + b"\n")
            self.proc.stdin.flush()

    def stop(self):
        with LOCK:
            self.state, self.pending = "stopped", None
        self.proc.terminate()

    def info(self):
        with LOCK:
            return dict(agent=self.agent, step=self.step, state=self.state, pending=self.pending, rc=self.rc, auto=self.auto, log=self.log[-80:])


class Manager:
    def __init__(self):
        self.runs = {}

    def current(self, pid):
        return self.runs.get(pid)

    def active(self, pid):
        r = self.runs.get(pid)
        return r if r and r.state in ("running", "awaiting") else None

    def start(self, pid, agent, step, auto=False):
        with LOCK:
            if self.active(pid):
                raise ValueError("A step is already running for this project. Answer it or stop it first.")
            if agent not in MODS or step not in MODS[agent].STEPS:
                raise ValueError("Unknown step.")
            s = next(x for x in steps_status(pid, agent) if x["name"] == step)
            if not s["ready"]:
                raise ValueError("An earlier step must be approved first.")
            self.runs[pid] = Run(pid, agent, step, step_args(load(pid), agent, step), auto)
            return self.runs[pid]

    def finished(self, run):
        if run.auto and run.state == "done" and (step := next_step(run.pid, run.agent)):
            if (run.agent, step) in NEVER_AUTO:
                with LOCK:
                    run.log.append(f"[auto] paused before {step}: a promotion is never started automatically. Start it from the page, then authorize the commands.")
                return
            if why := next(x["suggest"] for x in steps_status(run.pid, run.agent) if x["name"] == step):
                with LOCK:
                    run.log.append(f"[auto] paused before {step}: it may not be needed ({why}) Skip it or run it from the page.")
                return
            try:
                self.start(run.pid, run.agent, step, auto=True)
            except ValueError as e:
                with LOCK:
                    run.log.append(f"[auto] stopped: {e}")


MANAGER = Manager()


def project_view(pid):
    p, run = load(pid), MANAGER.current(pid)
    r = run.info() if run else None
    tracks = {}
    for agent in MODS:
        st = steps_status(pid, agent)
        for s in st:
            if r and r["agent"] == agent and r["step"] == s["name"] and r["state"] in ("running", "awaiting"):
                s["status"], s["text"] = ("needs_you", "Needs you: " + r["pending"]["role"]) if r["pending"] else ("running", "Running")
        tracks[agent] = dict(steps=st, approved=sum(s["status"] == "approved" for s in st), skipped=sum(s["status"] == "skipped" for s in st),
                             total=len(st), next=next_step(pid, agent))
    hand = None
    cb = pdir(pid) / "coder" / "briefs"
    if (cb / "handoff-package.md").exists():
        try:
            iss = handoff.issues((cb / "review-report.md").read_text(), (cb / "test-report.md").read_text(), (cb / "pull-request.md").read_text())
        except OSError:
            iss = None
        dec = [json.loads(x) for x in (cb / "handoff-decisions.log").read_text().splitlines()] if (cb / "handoff-decisions.log").exists() else []
        hand = dict(ready=iss is not None, counts=handoff.counts_line(iss) if iss else "", needs_reason=handoff.needs_reason(iss) if iss else [],
                    decisions=dec[-3:])
    return dict(project=p, tracks=tracks, run=r, handoff=hand, incidents=sre_incidents(pid), pipeline=pipeline())


def incident_action(pid, data):
    """Open an incident, select one or bring the latest service record into it. All by the SRE agent's own command, so the page and the command line cannot disagree."""
    if MANAGER.active(pid):
        raise ValueError("A step is running. Answer it or stop it first.")
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "sre" / "agent.py"), "incident", *a], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                    env=dict(os.environ, SDLC_WORKSPACE=str(pdir(pid))), cwd=str(pdir(pid)))
    p = load(pid)
    if data.get("select"):
        if data["select"] not in [i["id"] for i in sre_incidents(pid)]:
            raise ValueError("No such incident.")
        p["incident"] = data["select"]
        save(pid, p)
        return dict(incident=p["incident"], message="")
    if data.get("pin"):
        if not p.get("incident"):
            raise ValueError("Select an incident first.")
        r = run("pin", "--incident", p["incident"])
        if r.returncode:
            raise ValueError((r.stdout + r.stderr).strip()[-400:])
        return dict(incident=p["incident"], message=r.stdout.strip())
    title = (data.get("title") or "").strip()[:120]
    r = run("open", title)
    if r.returncode:
        raise ValueError((r.stdout + r.stderr).strip()[-500:])
    m = re.search(r"opened (INC-\d+-\d+)", r.stdout)
    p["incident"] = m.group(1)
    save(pid, p)
    return dict(incident=p["incident"], message=r.stdout.strip())


def handoff_decision(pid, data):
    cb = pdir(pid) / "coder" / "briefs"
    pkg_path = cb / "handoff-package.md"
    if not pkg_path.exists():
        raise ValueError("There is no handoff package yet. Run the Coder's handoff step first.")
    iss = handoff.issues((cb / "review-report.md").read_text(), (cb / "test-report.md").read_text(), (cb / "pull-request.md").read_text())
    d, name, reason = (data.get("decision") or "").strip(), (data.get("name") or "").strip(), (data.get("reason") or "").strip()
    if err := handoff.record_problem(d, name, reason, iss):
        raise ValueError(err + ".")
    pkg = pkg_path.read_text()
    m = re.search(r"Branch `([^`]+)` \(starting commit `([0-9a-f]+)`\)", pkg)
    rec = handoff.record(cb, pkg_path, m.group(1) if m else "", m.group(2) if m else "", iss, d, name, reason)
    if d == "approve":
        baseline.log_approval(cb, "handoff", pkg_path, handoff.REVIEWER)
    return rec


# ------------------------------------------------------------------------------------------------ http

class Handler(BaseHTTPRequestHandler):
    server_version = "sdlc-web"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else (json.dumps(body) if ctype == "application/json" else body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:")
        self.end_headers()
        self.wfile.write(data)

    def _guard(self, post):
        host = self.headers.get("Host", "")
        if host.rsplit(":", 1)[0] not in ("127.0.0.1", "localhost"):
            self._send(403, {"error": "Only 127.0.0.1 and localhost are allowed."})
            return False
        if post:
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{host}":
                self._send(403, {"error": "Cross-site request refused."})
                return False
            if not hmac.compare_digest(self.headers.get("X-Token", ""), TOKEN):
                self._send(403, {"error": "Missing or wrong token. Reload the page."})
                return False
        return True

    def do_GET(self):
        if not self._guard(False):
            return
        u = urlparse(self.path)
        try:
            if u.path == "/":
                html = (ROOT / "web" / "index.html").read_text().replace("__TOKEN__", TOKEN)
                return self._send(200, html, "text/html")
            if u.path == "/api/projects":
                items = []
                for f in sorted(PROJECTS.glob("*/project.json"), key=lambda x: x.stat().st_mtime, reverse=True):
                    p = json.loads(f.read_text())
                    items.append(dict(id=p["id"], name=p["name"], created=p["created"]))
                return self._send(200, items)
            m = re.fullmatch(r"/api/projects/([^/]+)", u.path)
            if m:
                return self._send(200, project_view(m.group(1)))
            m = re.fullmatch(r"/api/projects/([^/]+)/doc", u.path)
            if m:
                q = parse_qs(u.query)
                agent, file = (q.get("agent") or [""])[0], (q.get("file") or [""])[0]
                if agent not in READABLE or file not in READABLE[agent]:
                    return self._send(404, {"error": "No such document."})
                base = briefs_of(m.group(1), agent, next((n for n, v in MODS[agent].STEPS.items() if v[1] == file), None))
                if base is None:
                    return self._send(200, dict(file=file, text=""))
                f = base / file
                return self._send(200, dict(file=file, text=f.read_text(errors="replace") if f.exists() else ""))
            self._send(404, {"error": "Not found."})
        except KeyError as e:
            self._send(404, {"error": str(e).strip("'\"")})

    def do_POST(self):
        if not self._guard(True):
            return
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._send(413, {"error": "Too large."})
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
            u = urlparse(self.path).path
            if u == "/api/projects":
                return self._send(200, create(data))
            m = re.fullmatch(r"/api/projects/([^/]+)/(docs|settings|run|respond|stop|handoff-decision|skip|incident)", u)
            if not m:
                return self._send(404, {"error": "Not found."})
            pid, act = m.groups()
            pdir(pid)
            if act == "docs":
                return self._send(200, add_doc(pid, data))
            if act == "settings":
                return self._send(200, settings(pid, data))
            if act == "skip":
                return self._send(200, skip(pid, data))
            if act == "incident":
                return self._send(200, incident_action(pid, data))
            if act == "run":
                agent = data.get("agent")
                step = data.get("step") if data.get("step") not in (None, "next") else (next_step(pid, agent) if agent in MODS else None)
                if not step:
                    return self._send(400, {"error": "Nothing to run: every step is approved, or the next one is waiting on an earlier step."})
                MANAGER.start(pid, agent, step, bool(data.get("auto")))
                return self._send(200, {"started": step})
            run = MANAGER.current(pid)
            if act == "respond":
                if data.get("answer") not in ("y", "n") or not run:
                    raise ValueError("Nothing is waiting for an answer.")
                if data["answer"] == "n" and not (data.get("feedback") or "").strip():
                    raise ValueError("Say what should change when you send a draft back.")
                run.respond(data["answer"], data.get("feedback") or "")
                return self._send(200, {"ok": True})
            if act == "stop":
                if MANAGER.active(pid):
                    run.auto = False
                    run.stop()
                return self._send(200, {"ok": True})
            return self._send(200, handoff_decision(pid, data))
        except KeyError as e:
            self._send(404, {"error": str(e).strip("'\"")})
        except (ValueError, OSError, json.JSONDecodeError) as e:
            self._send(400, {"error": str(e)})


def make_server(port=8765):
    PROJECTS.mkdir(parents=True, exist_ok=True)
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    args = sys.argv[1:]
    port = int(args[args.index("--port") + 1]) if "--port" in args else 8765
    srv = make_server(port)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"AI SDLC web page: {url}\nProjects are stored in {PROJECTS}\nPress Ctrl+C to stop. Runs that are waiting for you stay at their prompt until you answer.")
    if "--no-open" not in args:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:  # noqa: BLE001  (opening a browser is a convenience)
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        for r in list(MANAGER.runs.values()):
            if r.state in ("running", "awaiting"):
                r.stop()
