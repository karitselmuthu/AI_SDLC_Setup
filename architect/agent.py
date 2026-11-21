#!/usr/bin/env python3
"""Architect agent. Owns everything architect-related; sdlc.py just uses it for its design stage.

Usage: python architect/agent.py qualify  rfp.pdf notes.md ...   -> briefs/opportunity-brief.md
       python architect/agent.py discover rfp.pdf notes.md ...   -> briefs/requirements.md
         (discover also reads briefs/opportunity-brief.md if qualify has run)
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # so `import core` works when run as a script

import core  # noqa: E402
from core import approve, ask  # noqa: E402

core.AGENTS["architect"] = dict(
    role="You are the Architect Agent. Draft the spec, map dependencies, qualify opportunities, "
         "discover requirements. Never write code.",
    tools=core.RO,  # read-only: no edit, write or shell
)


def _task(template, files, out_name, reviewer):
    """Prompt template + source docs -> markdown in briefs/, looped until a human approves."""
    docs = [pathlib.Path(f).resolve() for f in files]
    missing = [str(d) for d in docs if not d.is_file()]
    if missing:
        sys.exit(f"not found: {missing}")
    core.EXTRA_DIRS.extend({str(d.parent) for d in docs})
    out = HERE / "briefs" / out_name
    out.parent.mkdir(exist_ok=True)
    note = ""
    while True:
        text = ask("architect", (HERE / template).read_text()
                   + "\n\nSource documents (open each with the Read tool):\n" + "\n".join(map(str, docs)) + note)
        out.write_text(text)
        if approve(reviewer):
            break
        note = "\n\nHuman feedback: " + input("feedback> ")
    print("wrote:", out)


def qualify(files):
    """Step 1: RFP / questionnaire / notes / account brief -> opportunity brief."""
    _task("qualify.md", files, "opportunity-brief.md", "Pursuit lead reviews the opportunity brief")


def discover(files):
    """Step 2: documents (+ the opportunity brief, if any) -> prioritized, traceable requirements."""
    brief = HERE / "briefs" / "opportunity-brief.md"
    _task("discover.md", ([str(brief)] if brief.exists() else []) + list(files), "requirements.md",
          "Product owner approves the requirements")


if __name__ == "__main__":
    steps = {"qualify": qualify, "discover": discover}
    cmd, *files = sys.argv[1:] or [""]
    if cmd not in steps or not files:
        sys.exit(__doc__)
    steps[cmd](files)
