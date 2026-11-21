#!/usr/bin/env python3
"""Architect agent. Owns everything architect-related; sdlc.py just uses it for its design stage.

Usage: python architect/agent.py <step> FILE...      (FILEs: RFPs, notes, diagrams, inventories, standards)
Each step reads earlier steps' outputs from briefs/ automatically and writes its own there.
Steps: see STEPS below.
"""
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # so `import core` works when run as a script

import core  # noqa: E402
from core import approve, ask  # noqa: E402
from architect import baseline  # noqa: E402

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
    "options": ("options.md", "solution-options.md", "Tech lead and pursuit lead review the options and recommendation",
                ["opportunity-brief.md", "requirements.md", "current-state.md"]),
    "design": ("design.md", "target-architecture.md", "Tech lead signs off on the target architecture",
               ["opportunity-brief.md", "requirements.md", "current-state.md", "solution-options.md"]),
    "fit": ("fit.md", "enterprise-fit.md", "Security, compliance and enterprise architecture reviewers assess the fit",
            ["opportunity-brief.md", "requirements.md", "current-state.md", "solution-options.md",
             "target-architecture.md"]),
    "delivery": ("delivery.md", "delivery-approach.md", "Delivery lead and pursuit lead review the roadmap and responsibilities",
                 ["opportunity-brief.md", "requirements.md", "current-state.md", "solution-options.md",
                  "target-architecture.md", "enterprise-fit.md"]),
    "economics": ("economics.md", "rom-estimate.md", "Delivery lead, finance and pursuit lead validate the estimate",
                  ["opportunity-brief.md", "requirements.md", "current-state.md", "solution-options.md",
                   "target-architecture.md", "enterprise-fit.md", "delivery-approach.md"]),
    "proposal": ("proposal.md", "proposal-package.md", "Bid manager, delivery lead and pursuit lead review the proposal before release",
                 ["opportunity-brief.md", "requirements.md", "current-state.md", "solution-options.md",
                  "target-architecture.md", "enterprise-fit.md", "delivery-approach.md", "rom-estimate.md"]),
    "discuss": ("discuss.md", "discussion-pack.md", "Bid manager and pursuit lead approve the meeting pack",
                ["opportunity-brief.md", "requirements.md", "current-state.md", "solution-options.md",
                 "target-architecture.md", "enterprise-fit.md", "delivery-approach.md", "rom-estimate.md",
                 "proposal-package.md"]),
    "record": ("record.md", "opportunity-record.md", "Bid manager confirms the record of decisions and follow-ups",
               ["opportunity-brief.md", "requirements.md", "delivery-approach.md", "proposal-package.md",
                "discussion-pack.md"]),
    "handoff": ("handoff.md", "solution-baseline.md", "Delivery lead and bid manager approve the baseline for handoff",
                ["opportunity-brief.md", "requirements.md", "current-state.md", "solution-options.md",
                 "target-architecture.md", "enterprise-fit.md", "delivery-approach.md", "rom-estimate.md",
                 "proposal-package.md", "discussion-pack.md", "opportunity-record.md"]),
}

ACCUMULATE = {"record"}  # these steps build on their own previous output (a running log) instead of starting over


def must_cover(source, pattern, what):
    """Deterministic check factory: every ID matching `pattern` in briefs/<source> must appear in the step's output.
    Returns fn(briefs_dir, text) -> fix-up prompt, or '' when nothing is missing."""
    def check(briefs, text):
        src = briefs / source
        ids = sorted(set(re.findall(pattern, src.read_text()))) if src.exists() else []
        missing = [i for i in ids if i not in text]
        return (f"The {what} is missing {', '.join(missing)}. Add a row for each, saying how it is handled or "
                "its verdict/status, with the reason. Reply with the complete updated document, same sections."
                ) if missing else ""
    return check


untraced = must_cover("requirements.md", r"R-\d{3}", "requirement traceability table")  # design: every requirement
unassessed = must_cover("target-architecture.md", r"\b[KI]\d+\b", "fit assessment table")  # fit: every component/interface

unhandled = must_cover("enterprise-fit.md", r"\bE\d+\b", "exceptions and fit items table")  # delivery: every exception

unestimated = must_cover("delivery-approach.md", r"\bP\d+\b", "effort estimate table")  # economics: every phase

unanswered = must_cover("requirements.md", r"R-\d{3}", "response to RFP requirements table")  # proposal: every requirement

undiscussed = must_cover("delivery-approach.md", r"\bD\d+\b", "decisions we need table")  # discuss: every decision point
unlogged = must_cover("discussion-pack.md", r"\bD\d+\b", "decision log")  # record: an outcome for every decision point

def all_of(*checks):
    """Combine checks: one fix-up prompt listing everything that is missing."""
    return lambda briefs, text: "\n".join(filter(None, (c(briefs, text) for c in checks)))


unindexed = must_cover("requirements.md", r"R-\d{3}", "traceability index")  # handoff: every requirement
unfollowed = must_cover("opportunity-record.md", r"\bF\d+\b", "client commitments and follow-ups table")  # every follow-up

CHECKS = {"design": untraced, "fit": unassessed, "delivery": unhandled, "economics": unestimated,
          "proposal": unanswered, "discuss": undiscussed, "record": unlogged,
          "handoff": all_of(unindexed, unfollowed)}  # step -> fn(briefs_dir, output_text) -> fix-up prompt or ''


def run_step(name, files):
    """Template + earlier outputs + source docs -> markdown in briefs/, looped until a human approves."""
    template, out_name, reviewer, prior = STEPS[name]
    briefs = HERE / "briefs"
    extra, others = "", {k: v for k, v in STEPS.items() if k != "handoff"}
    if name == "handoff":  # only approved, unedited, consistent artifacts can be baselined
        bad = baseline.problems(briefs, others)
        if bad:
            sys.exit("Cannot hand off yet. Fix these first:\n  " + "\n  ".join(bad))
        version = baseline.next_version(HERE / "baseline")
        extra = f"\n\nThis baseline will be published as version v{version}."
    docs = [briefs / p for p in prior if (briefs / p).exists()] + [pathlib.Path(f).resolve() for f in files]
    if name in ACCUMULATE and (briefs / out_name).exists():
        docs.insert(0, briefs / out_name)  # previous version: carry its decisions and follow-ups forward
    if name == "handoff" and (old := baseline.previous_doc(HERE / "baseline", version, out_name)):
        docs.insert(0, old)  # previous baseline, for the "what changed" section
        extra += f" The previous baseline is {old.name} in {old.parent.name}."
    if not docs:
        sys.exit(f"{name}: nothing to read. Pass source files, or run the earlier steps first.")
    missing = [str(d) for d in docs if not d.is_file()]
    if missing:
        sys.exit(f"not found: {missing}")
    core.EXTRA_DIRS.extend({str(d.parent) for d in docs})
    out = briefs / out_name
    out.parent.mkdir(exist_ok=True)
    note = ""
    while True:
        text = ask("architect", (HERE / template).read_text() + extra
                   + "\n\nSource documents (open each with the Read tool):\n" + "\n".join(map(str, docs)) + note)
        gap = CHECKS.get(name, lambda *_: "")(briefs, text)
        if gap:  # one automatic repair pass; the human reviewer still sees whatever comes out
            text = ask("architect", gap)
        out.write_text(text)
        if approve(reviewer):
            baseline.log_approval(briefs, name, out, reviewer)  # the ledger step 11 relies on
            break
        note = "\n\nHuman feedback: " + input("feedback> ")
    print("wrote:", out)
    if name == "handoff":
        print("baseline:", baseline.package(briefs, HERE / "baseline", others, out_name, version,
                                            [pathlib.Path(f).resolve() for f in files]))


def qualify(files): run_step("qualify", files)    # 1. opportunity brief
def discover(files): run_step("discover", files)  # 2. requirements
def assess(files): run_step("assess", files)      # 3. current-state view
def options(files): run_step("options", files)    # 4. solution options + recommendation
def design(files): run_step("design", files)      # 5. target architecture + traceability
def fit(files): run_step("fit", files)            # 6. enterprise fit: standards, exceptions, compliance questions
def delivery(files): run_step("delivery", files)  # 7. phases, dependencies, migration, roles, risks
def economics(files): run_step("economics", files)  # 8. ROM: effort ranges, cost drivers, savings, validation needs
def proposal(files): run_step("proposal", files)    # 9. proposal package, claims evidenced or marked [CONFIRM]
def discuss(files): run_step("discuss", files)      # 10a. meeting pack: flow, questions, walkthrough, objections
def record(files): run_step("record", files)        # 10b. decisions, changes and follow-ups after the meeting
def handoff(files): run_step("handoff", files)      # 11. versioned solution baseline for the delivery team


if __name__ == "__main__":
    cmd, *files = sys.argv[1:] or [""]
    if cmd not in STEPS:
        sys.exit(__doc__ + "Steps: " + ", ".join(STEPS))
    run_step(cmd, files)
