"""Shared plumbing for all agents: run one agent via the `claude` CLI with its own role,
tool limits and session, plus the human-approval prompt. Each agent registers itself in AGENTS."""
import subprocess
import uuid

RO = "Read,Grep,Glob"
DENY = ["Read(.env*)", "Edit(.env*)", "Write(.env*)", "Edit(.github/**)", "Write(.github/**)",
        "Bash(git push:*)", "Bash(rm -rf:*)"]  # applies to every agent
BUDGET = "2"  # USD cap per agent call

# name -> dict(role=system prompt, tools=..., allow=[...], mode=...); filled in by each agent's module
AGENTS = {}
TEST_CMD = "pytest -q"  # substituted into "{test}" allow-rules; set by the CLI
EXTRA_DIRS = []  # extra readable folders (e.g. source docs for the architect)
sessions = {}  # agent -> session id; each agent keeps its own conversation


def ask(agent, prompt):  # ponytail: shells out to claude CLI; swap for SDK if you need more control
    cfg = AGENTS[agent]
    new = agent not in sessions
    sid = sessions.setdefault(agent, str(uuid.uuid4()))
    cmd = ["claude", "-p", prompt, "--permission-mode", cfg.get("mode", "default"),
           "--tools", cfg["tools"], "--disallowedTools", *DENY, "--max-budget-usd", BUDGET,
           *(["--allowedTools", *[a.format(test=TEST_CMD) for a in cfg["allow"]]] if "allow" in cfg else []),
           *[x for d in EXTRA_DIRS for x in ("--add-dir", d)],
           *(["--session-id", sid, "--append-system-prompt", cfg["role"]] if new else ["--resume", sid])]
    return subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout


def approve(who):
    return input(f"[{who}] approve? [y/N] ").strip().lower() == "y"


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.strip()
