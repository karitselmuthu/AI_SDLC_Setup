"""Human handoff (coding agent, step 9). Plain code, no model call: the package a reviewer needs is assembled ONLY from the
approved records and from git, so nothing in it can be embellished. The agent prepares the evidence; the reviewer makes the
merge decision. The agent never approves, merges, pushes or opens the pull request, and a reviewer's decision can only be
recorded by a person answering at a terminal.

issues(review, tests, pr)  -> dict of what a reviewer must look at (blockers, should-fix, failing, not run, criteria not met)
build(...)                 -> the handoff package as markdown
record(...)                -> append the reviewer's decision to handoff-decisions.log
"""
import hashlib
import json
import pathlib
import re
import sys
from datetime import datetime, timezone

REVIEWER = "Reviewer (a senior developer or designated reviewer, who makes the merge decision)"
DECISIONS = {"approve": "approves merging", "changes": "requests changes", "reject": "rejects the change", "later": "has not decided"}


def section(text, title):
    m = re.search(rf"(?ms)^## {re.escape(title)}[^\n]*\n(.*?)(?=^## |\Z)", text)
    return m.group(1).strip() if m else ""


def sub(text, title):
    """A '### title' subsection (to the next heading of the same or higher level)."""
    m = re.search(rf"(?ms)^### {re.escape(title)}[^\n]*\n(.*?)(?=^###? |\Z)", text)
    return m.group(1).strip() if m else ""


def rows(text):
    """Table rows as cell lists, without the header and separator lines."""
    out = []
    for line in text.splitlines():
        if line.startswith("|") and not re.match(r"^\|\s*:?-{2,}", line):
            out.append([c.strip() for c in line.strip().strip("|").split("|")])
    return out[1:] if out else []


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def issues(review, tests, pr):
    """What a reviewer must look at, taken from the approved reports."""
    blockers = [l.strip("- ").strip() for l in section(review, "Blockers").splitlines() if l.strip() and l.strip() != "None."]
    scan = [r for r in rows(section(review, "Scanner findings from code")) if len(r) > 5]
    model = [r for r in rows(section(review, "Findings")) if len(r) > 3 and re.fullmatch(r"F\d+", r[0])]
    should = [f"{r[0]} {r[2]} {r[3]}: {r[5]}" for r in scan if r[1] == "Should fix"] + [f"{r[0]} {r[2]}: {r[3]}" for r in model if r[1] == "Should fix"]
    after = re.split(r"(?m)^Run \d+:\n", section(tests, "Results after the test changes"))[-1]
    results = [r for r in rows(after) if len(r) >= 2]
    failing = [f"{r[0]}: {r[1]}" for r in results if r[1].startswith("FAIL")]
    env = [f"{r[0]}: {r[1]}" for r in results if r[1].startswith("COULD NOT RUN")]
    cov = section(tests, "Stack coverage")
    not_run = [f"{r[1]} {r[2]}: {r[3]}" for r in rows(sub(cov, "Checks selected")) if len(r) > 3 and r[3].startswith("Not run")]
    gaps = [f"{r[0]}, {r[1]}: {r[2]}" for r in rows(sub(cov, "Gaps")) if len(r) > 2]
    unsupported = [l[2:].strip() for l in sub(cov, "Unsupported technologies").splitlines() if l.startswith("- ")]
    unmet = [f"{r[0]}: {r[-1]}" for r in rows(section(pr, "Acceptance criteria mapping")) if r and re.match(r"AC\d+", r[0]) and not r[-1].lower().startswith("met")]
    ran = bool(results)
    return dict(blockers=blockers, should_fix=should, failing=failing, env=env, not_run=not_run, gaps=gaps, unsupported=unsupported,
                unmet=unmet, checks_ran=ran)


def counts_line(i):
    return (f"Open blockers: {len(i['blockers'])}. Should-fix items: {len(i['should_fix'])}. Failing checks: {len(i['failing'])}. "
            f"Checks that could not run (environment): {len(i['env'])}. Selected checks not run: {len(i['not_run'])}. "
            f"Coverage gaps: {len(i['gaps'])}. Unsupported technologies: {len(i['unsupported'])}. Criteria not fully met: {len(i['unmet'])}.")


def needs_reason(i):
    """Why an approval needs the reviewer's written reason: something known is wrong or unverified."""
    why = []
    for key, label in (("blockers", "open blocker(s)"), ("failing", "failing check(s)"), ("unmet", "criteria not fully met"),
                       ("env", "checks that could not run"), ("not_run", "selected checks not run")):
        if i[key]:
            why.append(f"{len(i[key])} {label}")
    if not i["checks_ran"]:
        why.append("no check was run")
    return why


def bullets(items, none="None."):
    return "\n".join(f"- {x}" for x in items) if items else none


def build(ctx):
    """ctx: title, ticket_id, ticket_url, branch, head, repo, plan, change_plan, tests, review, pr, files (list of (path, kind, added, removed)),
    diff_sha, docs (list of (file, sha12, approvers))."""
    i = issues(ctx["review"], ctx["tests"], ctx["pr"])
    blocked = bool(i["blockers"] or i["failing"])
    verdict = ("**Not ready to merge: " + ", ".join(needs_reason(i)[:3]) + ".**" if blocked else
               "**No open blockers or failing checks are recorded.**" + (" Read the items under 'Checks not run' and 'Known risks' before deciding." if needs_reason(i) or i["should_fix"] else ""))
    ticket = ("**" + ctx["ticket_id"] + "**" + (f" ({ctx['ticket_url']})" if ctx["ticket_url"] else "") if ctx["ticket_id"] else
              "**The ticket reference is NOT STATED in the ticket documents. Add it before merging.**")
    ac = section(ctx["pr"], "Acceptance criteria mapping")
    files = "\n".join(f"| `{p}` | {k} | {a} | {r} |" for p, k, a, r in ctx["files"]) or "| none | | | |"
    results = re.split(r"(?m)^Run \d+:\n", section(ctx["tests"], "Results after the test changes"))[-1].strip()
    tstatus = re.findall(r"\*\*([^*]+)\*\*", section(ctx["tests"], "Status"))
    verdict_t = next((b for b in tstatus if "development verification" not in b), "Not stated.")
    rflags = section(ctx["tests"], "Review flags")
    cov = section(ctx["tests"], "Stack coverage")
    docs = "\n".join(f"| `{f}` | `{h}` | {a} |" for f, h, a in ctx["docs"])
    chg = section(ctx["change_plan"], "Change set")
    parts = [
        f"# Human handoff: {ctx['title']}",
        "## Status\nPrepared for the reviewer. **The reviewer makes the merge decision.** The agent has not approved, merged, committed, pushed or "
        "opened anything, and this package is not an approval.\n\n" + verdict + "\n\n" + counts_line(i)
        + f"\n\nBranch `{ctx['branch']}` (starting commit `{ctx['head'][:12]}`), repository {ctx['repo']}. The changes are uncommitted in the working tree.",
        "## 1. Ticket\n" + ticket + "\n\n" + (section(ctx["plan"], "Ticket summary") or "Not stated."),
        "## 2. Implementation plan\nApproved by the tech lead and the ticket owner before any code was written.\n\n"
        "### Steps of the ticket plan\n" + (section(ctx["plan"], "Implementation plan") or "Not stated.") + "\n\n### Planned changes\n" + (chg or "Not stated."),
        "## 3. Changed files (from git)\n| File | Kind | Lines added | Lines removed |\n|---|---|---|---|\n" + files
        + f"\n\nThe full diff is `change.diff` next to this package (SHA-256 `{ctx['diff_sha'][:12]}`).",
        "## 4. Acceptance criteria mapping (from the approved pull request description)\n" + (ac or "Not stated.")
        + "\n\n**Criteria not fully met:**\n" + bullets(i["unmet"], "None recorded."),
        "## 5. Tests run and results\n**" + verdict_t + "**\n\n" + (results or "No check results were recorded.")
        + "\n\nThese are development tests and local checks, **not independent QA sign-off**.\n\n### Test review flags\n" + (rflags or "Not stated."),
        "## 6. Checks not run and coverage gaps\n### Selected checks that did not run\n" + bullets(i["not_run"]) + "\n\n### Checks that could not run (environment)\n"
        + bullets(i["env"]) + "\n\n### Gaps: kinds of check the repository has no way to run\n" + bullets(i["gaps"]) + "\n\n### Unsupported technologies\n"
        + bullets(i["unsupported"]) + "\n\n### Not covered by anything the agent can run\nCI, independent QA, performance and security testing, and manual review of "
        "configuration and permissions are for people. The agent never claims they passed.",
        "## 7. Known risks and open items\n### Risks (from the pull request description)\n" + (section(ctx["pr"], "Risks") or "Not stated.")
        + "\n\n### Should-fix items from the self-review\n" + bullets(i["should_fix"])
        + "\n\n### Limitations (from the self-review)\n" + (sub(ctx["review"], "Limitations") or section(ctx["review"], "Limitations") or "Not stated.")
        + "\n\n### Remaining questions\n" + (section(ctx["review"], "Remaining questions") or "Not stated.")
        + "\n\n### Migration and compatibility notes\n" + (section(ctx["pr"], "Migration and compatibility notes") or "Not stated.")
        + (("\n\n### Dependency changes\n" + section(ctx["pr"], "Dependency changes")) if section(ctx["pr"], "Dependency changes") else ""),
        "## 8. Evidence and integrity\nEvery document below was approved by the named roles and has not been edited since (checked by the code when this "
        "package was built).\n\n| Document | SHA-256 (first 12) | Approved by |\n|---|---|---|\n" + docs
        + "\n\nThe self-review was written by the system that wrote the change. It is **not** an independent review.",
        "## 9. What the agent did and did not do\n- Did: read the approved ticket and design, planned, edited the files its plan lists on a new branch, "
        "added developer tests, ran the local checks it could, scanned the diff, and prepared this package and the pull request description.\n"
        "- Did not: commit, push, open the pull request, merge, approve, or run checks that need credentials, a database or the network.\n"
        "- The commands to open the pull request are at the end of `pull-request.md` and are for a person to run.",
        "## 10. For the reviewer\n- [ ] Read the diff (`change.diff`) and the acceptance criteria mapping; each criterion is really met\n"
        "- [ ] The changed files are only what this ticket needs\n- [ ] Open items in sections 4 to 7 are answered or accepted\n"
        "- [ ] Re-run the tests locally and run the checks in section 6 that the agent could not\n"
        "- [ ] Decide: approve, request changes or reject. The agent records your decision here only if you answer at a terminal.",
    ]
    return "\n\n".join(parts) + "\n", i


def is_tty():
    return sys.stdin.isatty()


def decide(briefs, package, branch, head, i, input_fn=None, tty=None):
    """Ask the reviewer for the merge decision. Returns (decision, record or None). Nothing is recorded for 'later', for an
    unrecognised answer, or when no person is at a terminal, so a script or a piped 'yes' can never make the decision."""
    input_fn = input_fn or input  # looked up now, not when the module loaded
    if not (is_tty() if tty is None else tty):
        print("Reviewer decision not recorded: it must be answered by a person at a terminal. Run `handoff` again there.")
        return "later", None
    try:
        d = input_fn("[Reviewer] decision (approve / changes / reject / later)> ").strip().lower()
    except EOFError:
        return "later", None
    if d not in ("approve", "changes", "reject"):
        print("Decision not recorded." if d in ("", "later") else f"'{d}' is not a decision; nothing was recorded.")
        return "later", None
    name = input_fn("reviewer name> ").strip()
    if not name:
        print("A decision needs the reviewer's name; nothing was recorded.")
        return "later", None
    why = needs_reason(i)
    reason = input_fn("reason" + (f" (required: {', '.join(why)})" if d == "approve" and why else "") + "> ").strip()
    err = record_problem(d, name, reason, i)
    if err:
        print(err + "; nothing was recorded.")
        return "later", None
    return d, record(briefs, package, branch, head, i, d, name, reason)


def record_problem(decision, name, reason, i):
    """Why a decision cannot be recorded ('' if it can). The same rules for the terminal and for the web page."""
    if decision not in ("approve", "changes", "reject"):
        return f"'{decision}' is not a decision"
    if not (name or "").strip():
        return "A decision needs the reviewer's name"
    if (decision == "approve" and needs_reason(i) or decision in ("changes", "reject")) and not (reason or "").strip():
        return "A reason is required here"
    return ""


def record(briefs, package, branch, head, i, decision, name, reason):
    """Append the reviewer's decision to handoff-decisions.log (never merges anything) and return the record."""
    rec = dict(time=datetime.now(timezone.utc).isoformat(timespec="seconds"), decision=decision, meaning=DECISIONS[decision],
               reviewer=name.strip(), role=REVIEWER, package_sha256=sha(pathlib.Path(package).read_text()), branch=branch,
               start_commit=head, reason=(reason or "").strip(), known_issues_at_decision=needs_reason(i), merged_by_agent=False)
    with open(pathlib.Path(briefs) / "handoff-decisions.log", "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec
