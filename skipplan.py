"""Which steps a project may not need, decided by plain rules on the inputs. Only a SUGGESTION: a person confirms each skip (name and reason),
the system writes a placeholder document and the ledger records who skipped it and why. A skipped step is never silent and never run by a model.
suggest(agent, step, ctx) -> reason ('' = run it).  ctx: src (text of the source documents), meetings (count), repo (path or None), scope (QA scope+risk text),
changed (files, lines changed in the repository, or None)."""
import re

SKIPPABLE = {"architect": ["assess", "economics", "discuss", "record"], "coder": ["detect"], "qa": ["explore", "nonfunctional"]}
THIN = 400  # words of source documents below which later architect steps would mostly repeat "Not stated"
ENV = re.compile(r"(?i)current (system|environment|stack|process)|existing (system|platform|infrastructure|application)|legacy|on-?prem|migrat")
MONEY = re.compile(r"(?i)budget|cost|price|[$€£]|\busers\b|volume|per (month|year|day)|headcount|timeline|deadline|go-?live")
NFR = re.compile(r"(?i)performance|latency|throughput|accessib|security|privacy|availab|reliab|compatib|scalab|load|resilien|encrypt|gdpr|hipaa")


def words(text):
    return len((text or "").split())


def suggest(agent, step, ctx):
    src, n = ctx.get("src", ""), words(ctx.get("src", ""))
    if agent == "architect":
        if step == "assess" and n < THIN and not ENV.search(src):
            return f"The supplied input is only {n} words and describes no current environment, so this step could only say 'Not stated'."
        if step == "economics" and n < THIN and not MONEY.search(src):
            return f"The supplied input is only {n} words and gives no budget, volumes, users or dates to estimate from."
        if step == "discuss" and n < THIN:
            return f"The supplied input is only {n} words; a client discussion pack would repeat the open questions the earlier steps already list."
        if step == "record" and not ctx.get("meetings"):
            return "No client meeting notes were supplied, so there is nothing to record."
    if agent == "coder" and step == "detect" and ctx.get("stacks") is not None:
        st = ctx["stacks"]
        if len(st) == 1 and not ctx.get("gaps") and not ctx.get("unsupported"):
            return f"The stack adapters identified the only technology ({st[0]}) with no gaps and no unsupported files; a written profile adds nothing."
    if agent == "qa":
        if step == "nonfunctional" and ctx.get("scope") is not None and not NFR.search(ctx["scope"]):
            return "The approved scope and risk plan state no performance, accessibility, security, reliability or compatibility expectation."
        if step == "explore" and ctx.get("changed") and not ctx.get("high"):
            files, lines = ctx["changed"]
            if files <= 2 and lines <= 80:
                return f"A small change ({files} file(s), {lines} line(s)) with no High-rated risk."
    return ""


def placeholder(step, person, reason, rule, date):
    return (f"## Status\nSkipped. This step was not run, and no model wrote anything here.\n\nSkipped by: {person}, on {date}.\nReason: {reason}\n"
            f"Suggested by the rule: {rule or 'none (the person chose to skip it)'}\n\nEverything this step would have covered is Not stated. "
            f"Re-run `{step}` at any time to replace this placeholder with a real document.\n")
