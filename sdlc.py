#!/usr/bin/env python3
"""AI-driven SDLC: one agent per stage (own role + own session), human gates,
auto-retry on tests, feedback loop.

Usage: python sdlc.py "issue text" [--test "pytest -q"]
       python sdlc.py --review /path/to/repo [--test "pytest -q"]   # review + fix any repo, on a new branch
Needs the `claude` CLI. Stage outputs land in .sdlc/ and are the hand-off between agents.
"""
import os
import pathlib
import subprocess
import sys
import uuid

OUT = pathlib.Path(".sdlc")

RO = "Read,Grep,Glob"
DENY = ["Read(.env*)", "Edit(.env*)", "Write(.env*)", "Edit(.github/**)", "Write(.github/**)",
        "Bash(git push:*)", "Bash(rm -rf:*)"]  # applies to every agent
BUDGET = "2"  # USD cap per agent call

# agent -> role (system prompt) + enforced limits: tools available, extra allow-rules, permission mode
AGENTS = {
    "triage": dict(role="You are the Triage Agent. Score issue readiness, list acceptance criteria, prioritize.",
                   tools=RO),
    "architect": dict(role="You are the Architect Agent. Draft the spec and map dependencies. Never write code.",
                      tools=RO),
    "coding": dict(role="You are the Coding Agent. Write code and keep the diff focused.",
                   tools=RO + ",Edit,Write,Bash", mode="acceptEdits"),
    "qa": dict(role="You are the QA Agent. Write and run tests. Do not change non-test code.",
               tools=RO + ",Edit,Write,Bash",  # default mode: only the allow-rules below pass, rest is denied
               allow=["Edit(test_*.py)", "Write(test_*.py)", "Edit(tests/**)", "Write(tests/**)", "Bash({test})"]),
    "review": dict(role="You are the Review Agent. First-pass PR review: security scan + scorecard. Read-only.",
                   tools=RO + ",Bash", allow=["Bash(git diff:*)", "Bash(git log:*)", "Bash(git status:*)"]),
    "release": dict(role="You are the Release Agent. Plan flag-based rollout and auto-rollback. Never deploy.",
                    tools=RO),
    "sre": dict(role="You are the SRE Agent. Define SLOs to watch, write a runbook, list follow-up issues one per line.",
                tools=RO),
}

# (stage, agent, task, human checkpoint or None)
STAGES = [
    ("plan", "triage", "Assess this issue.", "Product owner approves scope"),
    ("design", "architect", "Write the spec for the plan.", "Tech lead signs off on design"),
    ("build", "coding", "Implement the spec in this repo.", None),
    ("test", "qa", "Write tests for the spec's acceptance criteria.", None),  # + auto-retry loop
    ("review", "review", "Review `git diff`.", "Engineer approves the PR"),
    ("deploy", "release", "Write the rollout plan.", "Release manager approves prod release"),
    ("operate", "sre", "Write SLOs, runbook, follow-ups.", "On-call engineer owns incidents"),
]

TEST_CMD = "pytest -q"  # set by main
sessions = {}  # agent -> session id; each agent keeps its own conversation


def ask(agent, prompt):  # ponytail: shells out to claude CLI; swap for SDK if you need more control
    cfg = AGENTS[agent]
    new = agent not in sessions
    sid = sessions.setdefault(agent, str(uuid.uuid4()))
    cmd = ["claude", "-p", prompt, "--permission-mode", cfg.get("mode", "default"),
           "--tools", cfg["tools"], "--disallowedTools", *DENY, "--max-budget-usd", BUDGET,
           *(["--allowedTools", *[a.format(test=TEST_CMD) for a in cfg["allow"]]] if "allow" in cfg else []),
           *(["--session-id", sid, "--append-system-prompt", cfg["role"]] if new else ["--resume", sid])]
    return subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout


def approve(who):
    return input(f"[{who}] approve? [y/N] ").strip().lower() == "y"


def test_loop(cmd, max_tries=5):
    """Run tests; the coding agent fixes failures until green."""
    for _ in range(max_tries):
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if r.returncode == 0:
            return True
        ask("coding", f"Tests failed. Fix the code.\n$ {cmd}\n{r.stdout}{r.stderr}")
    return False


def run(issue, test_cmd):
    OUT.mkdir(exist_ok=True)
    fb = OUT / "feedback.md"  # SRE output from last run feeds triage: the feedback loop
    handoff = issue + (f"\n\nFollow-ups from last run:\n{fb.read_text()}" if fb.exists() else "")
    for stage, agent, task, human in STAGES:
        note = ""
        while True:
            if stage == "review":  # make new files show up in `git diff`
                sh("git add -N . ':!.sdlc' ':!__pycache__'")
            if stage == "test":
                task += f" Run them with exactly this command (other commands are blocked): {test_cmd}"
            out = ask(agent, f"{task}\n\nInput from previous stage:\n{handoff}\n{note}")
            (OUT / f"{stage}.md").write_text(out)
            if stage == "test" and not test_loop(test_cmd):
                sys.exit("tests still failing after retries; fix manually")
            if not human or approve(human):
                break
            note = "Human feedback: " + input("feedback> ")
        handoff = out
    fb.write_text(out)  # last stage = operate


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.strip()


def review_fix(repo, test_cmd=None, rounds=3):
    """Any repo: review -> human OK -> fix -> tests -> re-review, on a new branch (easy to discard)."""
    global OUT
    os.chdir(repo)
    if sh("git status --porcelain"):
        sys.exit("repo has uncommitted changes; commit or stash first")
    OUT = pathlib.Path(sh("git rev-parse --git-dir")) / "sdlc"  # inside .git: never committed
    OUT.mkdir(exist_ok=True)
    sh(f"git checkout -b sdlc-fixes-{uuid.uuid4().hex[:6]}")
    for i in range(1, rounds + 1):
        found = ask("review", "Review this whole repo for bugs and security issues. For each: file:line, problem, "
                              "concrete fix. If there is nothing worth fixing, reply exactly NO ISSUES.")
        (OUT / f"review-{i}.md").write_text(found)
        if "NO ISSUES" in found or not approve("Engineer approves fixes"):
            break
        ask("coding", f"Fix these review findings with minimal diffs:\n{found}")
        if test_cmd and not test_loop(test_cmd):
            sys.exit("tests failing after fixes; inspect the branch or `git checkout -` to discard")
        sh(f"git add -A && git commit -qm 'sdlc: review fixes round {i}'")
    print("branch:", sh("git branch --show-current"), "| reviews in", OUT)


if __name__ == "__main__":
    a = sys.argv[1:]
    opt = lambda f: a[a.index(f) + 1] if f in a else None
    if "--review" in a:
        review_fix(opt("--review"), opt("--test"))
    else:
        TEST_CMD = opt("--test") or TEST_CMD
        run(a[0], TEST_CMD)
