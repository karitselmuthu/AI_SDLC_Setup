#!/usr/bin/env python3
"""Architect agent. Owns everything architect-related; sdlc.py just uses it for its design stage.

Usage: python architect/agent.py <step> FILE...      (FILEs: RFPs, notes, diagrams, inventories, standards)
Each step reads earlier steps' outputs from briefs/ automatically and writes its own there.
Steps: see STEPS below.
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # so `import core` works when run as a script

import core  # noqa: E402
from core import approve, ask  # noqa: E402

core.AGENTS["architect"] = dict(
    role="You are the Architect Agent. Draft the spec, map dependencies, qualify opportunities, "
         "discover requirements, assess environments. Never write code.",
    tools=core.RO,  # read-only: no edit, write or shell. Read also opens PDFs and images (diagrams).
)

# step -> (prompt template, output file in briefs/, human reviewer, earlier outputs to feed in). Add a row per step.
STEPS = {
    "qualify": ("qualify.md", "opportunity-brief.md", "Pursuit lead reviews the opportunity brief", []),
    "discover": ("discover.md", "requirements.md", "Product owner approves the requirements",
                 ["opportunity-brief.md"]),
    "assess": ("assess.md", "current-state.md", "Tech lead confirms the current-state view",
               ["opportunity-brief.md", "requirements.md"]),
}


def run_step(name, files):
    """Template + earlier outputs + source docs -> markdown in briefs/, looped until a human approves."""
    template, out_name, reviewer, prior = STEPS[name]
    briefs = HERE / "briefs"
    docs = [briefs / p for p in prior if (briefs / p).exists()] + [pathlib.Path(f).resolve() for f in files]
    missing = [str(d) for d in docs if not d.is_file()]
    if missing:
        sys.exit(f"not found: {missing}")
    core.EXTRA_DIRS.extend({str(d.parent) for d in docs})
    out = briefs / out_name
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


def qualify(files): run_step("qualify", files)    # 1. opportunity brief
def discover(files): run_step("discover", files)  # 2. requirements
def assess(files): run_step("assess", files)      # 3. current-state view


if __name__ == "__main__":
    cmd, *files = sys.argv[1:] or [""]
    if cmd not in STEPS or not files:
        sys.exit(__doc__ + "Steps: " + ", ".join(STEPS))
    run_step(cmd, files)
