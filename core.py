"""Shared plumbing for all agents: run one agent via the `claude` CLI with its own role,
tool limits and session, plus the human-approval prompt. Each agent registers itself in AGENTS."""
import pathlib
import re
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


# Prompt-injection pre-scan of the supplied source documents. It cannot stop a model from being fooled (the rules and
# the read-only tools do that), it makes sure a human is told. PDFs and images cannot be scanned here, only by the model.
INJECTION = re.compile(
    r"(?i)\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|these|your)\b.{0,30}"
    r"\b(instruction|rule|prompt|guideline)s?\b|\byou are now\b|\bsystem prompt\b"
    r"|\b(mark|set|treat|record|declare)\b.{0,40}\b(approved|final|signed.off)\b"
    r"|\b(skip|bypass|waive)\b.{0,20}\b(review|approval|sign.?off)\b|\bdo not (flag|mention|report|tell)\b"
    r"|\breveal\b.{0,30}\b(prompt|instruction|rate card)\b|\bauto.?approve\b")
# only the system may say a document is approved; a model claiming it is a defect, whatever a source document said
APPROVED = re.compile(r"(?im)\bstatus\b\W{0,6}(approved|final|signed.off|released)\b|\bexternally approved\b"
                      r"|\bfinal version\b|\bapproved for (release|client|external)")


def flagged(files):
    """Instruction-like lines in the supplied source documents: 'file:line: text'."""
    out = []
    for f in files:
        try:
            lines = pathlib.Path(f).read_text().splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        out += [f"{pathlib.Path(f).name}:{n}: {line.strip()[:160]}" for n, line in enumerate(lines, 1)
                if INJECTION.search(line)]
    return out


def false_approval(briefs, text):
    return ("The document says it is approved or final. Only the system records approval; every document you write is "
            "a Draft pending review by the named reviewers. Replace that wording and reply with the complete updated "
            "document, same sections.") if APPROVED.search(text) else ""
