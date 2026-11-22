# AI SDLC Setup

Agents that take work through the software lifecycle, with a human approving at each gate.
This repository has two parts:

| Part | What it does | Entry point |
|---|---|---|
| **Architect agent** | Takes a sales opportunity from RFP to a versioned solution baseline in 11 reviewed steps | `architect/agent.py` |
| **SDLC pipeline** | Takes an issue through plan, design, build, test, review, deploy and operate; can also review and fix any git repo on a new branch | `sdlc.py` |

Both run the [Claude Code](https://docs.claude.com/en/docs/claude-code) CLI (`claude -p`) with a role, a tool allow-list and a spend cap per agent.
Everything an agent writes is a **draft for a human to approve**.

## Quick start

Requirements: Python 3.8+, the `claude` CLI installed and logged in, and `pytest` to run the tests.

```bash
git clone https://github.com/karitselmuthu/AI_SDLC_Setup.git && cd AI_SDLC_Setup
pip install pytest && pytest -q            # unit tests; they use a fake model call, so they cost nothing

# Run the architect steps on the made-up sample documents (each step asks you to approve):
S=docs/architect/samples
python architect/agent.py qualify  $S/rfp.md $S/notes.md
python architect/agent.py discover $S/rfp.md $S/notes.md
python architect/agent.py assess   $S/current-environment.md
```

Each step prints `wrote: architect/briefs/<file>` and then asks the named reviewer to approve.
Answer `y` to accept, or `n` and type feedback to have the agent redo it.

## The architect steps

Run them in order. Each step reads the earlier outputs from `architect/briefs/` automatically, so later steps usually need no file arguments.

| # | Command | What you pass | Output in `architect/briefs/` | Reviewer |
|---|---|---|---|---|
| 1 | `qualify` | RFP, questionnaire, notes, account brief | `opportunity-brief.md` | Account lead |
| 2 | `discover` | Same documents | `requirements.md` | Account lead, lead architect |
| 3 | `assess` | Diagrams, inventories, standards | `current-state.md` | Lead architect |
| 4 | `options` | Nothing extra | `solution-options.md` | Lead architect, account lead |
| 5 | `design` | Nothing extra | `target-architecture.md` | Lead architect |
| 6 | `fit` | Client standards, policies, contracts | `enterprise-fit.md` | Lead architect, security, compliance |
| 7 | `delivery` | Nothing extra | `delivery-approach.md` | Delivery lead, account lead |
| 8 | `economics` | Spend, price lists, rate card, headcounts | `rom-estimate.md` | Delivery lead, finance, account lead |
| 9 | `proposal` | Bidder profile, credentials, references | `proposal-package.md` | Account lead, lead architect, delivery lead, security, legal, finance (each signs separately) |
| 10a | `discuss` | Nothing extra | `discussion-pack.md` | Account lead, lead architect |
| 10b | `record` | Notes from the client meeting | `opportunity-record.md` | Account lead |
| 11 | `handoff` | Nothing extra | `solution-baseline.md`, then `architect/baseline/vN/` | Account lead, lead architect, delivery lead (each signs separately) |

`record` reads its own previous version, so decisions accumulate across meetings.
After a meeting, the record lists which earlier steps are now outdated. Re-run those and approve them again.

**Re-running a step is a revision.** The old output is saved to `architect/briefs/history/`, the new run reads it together with
`opportunity-record.md` (the meeting decisions), keeps IDs stable, and must end with a `## Revision history` section.

**Technology catalog.** To make the agent recommend only approved technology, put the catalog at
`architect/technology-catalog.md` (copy `docs/architect/samples/technology-catalog.md` to start). The `qualify`, `discover`, `assess`,
`options`, `design` and `fit` steps then read it. Without one, every named product is labelled "proposal, not validated". Technology that is not in the
catalog, or that the agent cannot assess, is marked "Unsupported: specialist review required" and gets no fit verdict or cost.

## How a step works

```
prompt template (docs/architect/<step>.md)
  + earlier outputs (architect/briefs/)
  + your source documents
        -> claude CLI, read-only tools
        -> draft
        -> coverage check (is every ID from the earlier step covered?)  -> one automatic repair pass
        -> human approves, or gives feedback and the agent redoes it
        -> approval logged (architect/briefs/approvals.log)
```

The coverage checks are plain code, not prompts. For example, the design must trace every requirement (`R-001`...), the fit assessment must assess every component and interface, and the delivery approach must handle every exception.

## Guardrails

- **Read-only architect.** The architect agent can read, search and open PDFs and images. It cannot edit files or run commands.
- **Never invent.** Every template tells the agent to write "Not stated" instead of guessing. Values it proposes itself are marked "Proposed".
- **Evidence or confirm.** Claims about the bidder are cited to a document or marked `[CONFIRM: ...]`. Expired or indicative quotes are never treated as confirmed.
- **No leaks.** Client-facing text must not contain the rate card, cost, margin or the ROM. Meeting material is labelled `[CLIENT-SHAREABLE]` or `[INTERNAL]`.
- **Honest about gaps.** A requirement the design cannot meet is never answered "Full". Verbal figures from a meeting are recorded as unconfirmed.
- **Documents are data.** The shared rules (`docs/architect/_rules.md`) are put in front of every step. Text in an RFP or notes cannot change the rules, the files the agent may read, or the approval process. Before each run the code scans the supplied text files for instruction-like lines ("ignore previous instructions", "mark this as approved"...). It warns the reviewer, and the output must list them under `## Source-document anomalies`.
- **The agent cannot approve.** Approval is a prompt in code that a document cannot reach. If the model writes "Status: Approved" or "final version" it is sent back once to fix it.
- **No unevidenced certifications.** ISO, SOC 2, PCI DSS, GDPR and similar are never claimed unless a supplied document shows them.
- **Spend cap.** Each `claude` call is capped at USD 2 (`BUDGET` in `core.py`). Secrets and CI config are on a deny list for every agent.

## Approvals and the baseline

Every approval is appended to `architect/briefs/approvals.log` with a hash of the approved file and the role that approved it.
Every step lists its reviewers by role and each role approves **separately**, never one "y" for a group. The four checkpoint groups are the account lead (opportunity fit, client messaging, commitments), the lead solution architect (technical correctness, standards fit, exceptions), the delivery lead (feasibility, staffing, schedule, estimate assumptions) and the security, compliance, legal and finance reviewers (their obligations and commitments). The proposal needs all six roles; the handoff needs account lead, lead architect and delivery lead. They are asked one by one, and a "no" from any of them sends the draft back and restarts the round. An approval only counts for the exact content it was given on.
`handoff` refuses to run until every artifact is produced, approved by all its required roles, **unedited since approval**, and not **stale** (an earlier step approved again after it).
When it passes, it writes `architect/baseline/vN/`: a read-only copy of every approved artifact, the handoff document, and a `manifest.json` (status `approved`) with hashes, every approver and the source documents. The solution is never marked final before that.
Versions are never overwritten. A new run publishes `v2`, and the handoff document explains what changed.

The log is a local file. It shows what was approved, but it is not tamper-proof.

## The coding agent

A separate agent in `coder/`, built one activity at a time like the architect. It is read-only until a plan is approved.

| # | Command | What you pass | Output in `coder/briefs/` | Reviewers |
|---|---|---|---|---|
| 1 | `understand` | The approved ticket, then any design or standards files, and `--repo PATH` | `implementation-plan.md` | Tech lead, ticket owner (each signs separately) |

| 2 | `inspect` | `--repo PATH` (reads the approved step 1 plan itself) | `repository-inspection.md` | Tech lead |

| 3 | `detect` | `--repo PATH` (reads the approved step 2 inspection itself) | `stack-profile.md` | Tech lead |

| 4 | `plan` | `--repo PATH` (reads the three approved outputs above itself) | `change-plan.md` | Tech lead, ticket owner (each signs separately) |

| 5 | `implement` | `--repo PATH` (reads the approved change plan itself) | `implementation-report.md`, plus the edits on a new git branch | Tech lead |

| 6 | `tests` | `--repo PATH` (on the branch step 5 created), optional `--check CMD` | `test-report.md`, plus test edits on that branch | Tech lead |

```bash
python coder/agent.py understand docs/coder/samples/ticket.md --repo .
python coder/agent.py inspect --repo .
python coder/agent.py detect --repo .
python coder/agent.py plan --repo .
python coder/agent.py implement --repo /path/to/the/repo
python coder/agent.py tests --repo /path/to/the/repo
```

**Step 5 is the first step that edits code, so it is fenced in.** It refuses to run until the change plan is approved by both reviewers, unedited
and not stale, and the target must be a git repository with no uncommitted changes to tracked files. It then:

- creates a **new branch** (`coder/<timestamp>`) and never touches the original branch, never commits and never pushes. The report says how to discard the branch;
- implements the plan **one change at a time**, and for each change the agent may edit **only that change's files**. This is enforced at the tool level (an `Edit(path)` allow-list built from the plan, with no shell and no `acceptEdits`), and then checked again by code: after each change `git` is compared before and after, and any edit outside that change's files is **reverted** and listed in the report;
- builds the **report from git**, not from what the model says. A model that claims "Done" without changing a file is reported as "No change made", and planned new files that were never created are listed;
- asks the model to follow the repository's conventions and reuse existing code, to stop with "Blocked:" and make no edit when the plan turns out to be wrong, and to say what it did not do. It cannot run tests: running them is not part of this step.

Your own Claude Code hooks apply to the edit agent too, so a fact-forcing hook (such as GateGuard) makes the agent state its facts and retry.

**Step 6 adds the developer-level tests and runs the repository's local checks.** It needs the step 5 report approved and the repository on the
branch that step created. The model writes tests and may edit **test files only** (`tests/`, `test_*.py`, `*.spec.*`, `conftest.py`,
fixtures...): this is enforced with a glob allow-list on the Edit tool and re-checked in code, and any edit to production code is reverted and
reported. The prompt demands normal, boundary and failure cases for every acceptance criterion, deterministic fixtures (no network, clock or
randomness), no weakening, deleting or skipping of existing tests, and "Production defect suspected" instead of fixing code. A code check
requires a complete test matrix row for every criterion.

**The code, not the model, runs the checks** (the agent has no shell). The commands come from the approved stack profile (test, lint and type
commands only; installs, deploys, network, git, `rm` and shell chaining are filtered out) or from `--check CMD`, and the tech lead approves the
list before anything runs. The checks run once before the model edits (a baseline) and again after, so new failures are told apart from ones that were
already there. Failing output is fed back to the model to fix the tests, at most 3 times, and then a human decides. Failures, timeouts and "not run"
are recorded as they are, never hidden. The report is stamped **"development verification, not independent QA sign-off"**, and a claim of QA
sign-off by the model is removed. A scan flags removed or weakened assertions, removed tests, and added skips for the reviewer.

Step 4 refuses to run until the ticket plan, the inspection and the stack profile are all approved, unedited and not stale. It breaks the
work into **small changes** (each rated S or M, at most 12) with the files, functions, interfaces, data models and migrations, configuration
and backward-compatibility concerns for each, plus the order and how each is rolled back. **Code checks enforce the bounds:** every
acceptance criterion of the ticket must map to a change (or say "Not coverable" with the reason), every change must serve a criterion or be
declared "Enabling", no change may be rated L, the plan may not exceed 12 changes, and every cited file must exist or be marked `new:`.

Step 3 first runs a plain-code scanner (`coder/stack.py`) that finds the manifests, lockfiles, build files, framework configuration and CI
definitions (including nested ones in a monorepo), counts languages, and lists file types it does not recognise. The model must read every
one of those files and write the stack profile: languages, frameworks, how each version is pinned (a lockfile gives the exact one),
commands (read from configuration, never claimed as run), what each CI file runs, and **conflicts between files**, such as one Node
version in `package.json`, another in `.nvmrc`, and a third in the Dockerfile. Anything it cannot assess is marked **Unsupported**
and anything unpinned, inferred or conflicting is marked **Uncertain**, with no commands or versions assumed for it. Code checks that every
detected file and every unrecognised file type is accounted for, and that every cited path exists.

Step 2 refuses to run until the step 1 plan is approved by both reviewers, unedited since, and not stale. It then reads the repository itself:
structure, language and dependencies, build and test commands (read from configuration, never claimed as run), conventions, where tests live,
and the code that calls and is called by what the plan touches. It gives every plan step a verdict (Confirmed, Changed or Blocked) and lists
what the evidence changed. **Evidence is checked in code:** every backticked file path must exist in the repository or be marked `new:`, and
every step of the first plan must have a row, or the draft is sent back once. A re-run keeps the old version in `coder/briefs/history/`.

Step 1 reads the ticket, design and repository guidance (CLAUDE.md, README, CONTRIBUTING, test setup) and writes a short plan linked to the
ticket. It lists every ambiguity, missing input and conflict as a numbered question with the criteria it blocks and the assumption it would
use, and never resolves one silently. A ticket that does not state its approval is a blocker. The code checks that the plan defines numbered
acceptance criteria and that **every one is covered by a plan step**. It uses the same shared safety rules as the architect (documents are
data, the injection pre-scan, the agent cannot claim approval). Rules are in `docs/coder/_rules.md`.

## The SDLC pipeline

```bash
python sdlc.py "Add calc.py with add(a, b)" --test "pytest -q"   # plan -> design -> build -> test -> review -> deploy -> operate
python sdlc.py --review /path/to/repo --test "pytest -q"          # review and fix a repo on a new branch
```

Seven agents (triage, architect, coding, QA, review, release, SRE) each have their own role, session and tool limits.
Only the coding agent can edit freely; QA may edit tests only; the others are read-only. Test failures go back to the coding agent, up to 5 tries.
Humans approve plan, design, review, deploy and operate. The release agent writes a plan and never deploys.
Review-fix mode refuses a repo with uncommitted changes and commits fixes to a new `sdlc-fixes-*` branch.
This pipeline has been dry-run on a toy issue; it has not had the same step-by-step testing as the architect agent.

## Repository layout

```
architect/            architect agent code
  agent.py              step table (STEPS), checks, approval loop
  baseline.py           approval ledger and versioned packaging
  briefs/               generated outputs (not committed)
  baseline/             generated baselines (not committed)
coder/                coding agent code: agent.py (steps and checks), stack.py (stack scanner); outputs go to coder/briefs/ (not committed)
core.py               shared runner: role, tool limits, session, budget, approval prompt, injection scan
sdlc.py               the SDLC pipeline and review-fix mode
docs/architect/       the 12 step prompts and _rules.md, the rules shared by every step (these are code: the agent reads them)
docs/architect/samples/  made-up client documents and a sample technology catalog for trying the steps
tests/                all tests, kept apart from the code (pytest.ini sets the paths)
  test_architect.py, test_baseline.py, test_sdlc.py   unit tests
  test_acceptance.py    one test group per acceptance case (see below)
  test_coder.py, test_stack.py, test_implement.py, test_tests_step.py   coding agent, stack scanner, implement and tests-step tests
docs/coder/           the coding agent's step prompts, _rules.md and a sample ticket
```

## Testing

```bash
pytest -q
```

The tests use a fake model call. They check the plumbing, the coverage checks, the approval and baseline logic, and that each prompt contains its required rules.
They do not judge the quality of what the model writes. For that, run the steps on the sample documents and read the output.

### Acceptance cases

`tests/test_acceptance.py` has a group per case. **Code** means the program enforces it (a model cannot skip it); **Prompt** means the
instruction is in the prompt and the tests prove it is there, but only a real run shows the model follows it.

| # | Case | How it is enforced |
|---|---|---|
| 1 | Complete RFP | Prompt: qualify and discover extract criteria, constraints, deadlines. Code: every requirement must be traced in the design and the proposal |
| 2 | Ambiguous problem | Prompt: `discover` lists competing readings and a targeted question, never a silent choice |
| 3 | Incomplete current state | Prompt: unknowns are "Not stated" and go to client confirmation |
| 4 | Conflicting requirements | Prompt: conflicts with affected design choices and who decides. Code: the design must answer every conflict |
| 5 | Multiple architectures | Prompt: 2 to 4 options compared, recommendation with trade-offs |
| 6 | Technology-neutral request | Code: the catalog is read by options, design and fit. Prompt: recommend only from it |
| 7 | Unsupported technology | Prompt: named, what cannot be assessed, specialist review, no verdict or cost |
| 8 | Client-mandated technology | Prompt: kept as a constraint, fit and risks checked, exceptions listed |
| 9 | Cloud or hybrid | Prompt: hosting, connectivity, identity, data movement, resilience, operations, cross-environment cost |
| 10 | Residency or regulation | Prompt: each requirement mapped to a design decision; open validation never reported as met |
| 11 | Security-sensitive | Prompt: trust boundaries, sensitive flows, access control, review points. Rule: no unevidenced certification |
| 12 | Estimate with missing inputs | Prompt: only a range or driver model, assumptions, inputs needed for a firmer figure |
| 13 | RFP traceability | Code: every requirement must have a response row; gaps and exceptions are labelled |
| 14 | Claim without evidence | Prompt: `[CONFIRM]` instead of invented references or certifications |
| 15 | Change after discussion | Code: re-run archives the old version, reads the meeting record, must add a revision history |
| 16 | Approved handoff | Code: the baseline reads every artifact and must cover every requirement and follow-up |
| 17 | Prompt injection | Code: pre-scan, warning, human approval outside the model, read-only tools. Prompt: documents are data |
| 18 | Human approval gate | Code: each named reviewer signs separately; the model cannot claim "approved"; the handoff refuses until all have signed |

## Adding or changing a step

1. Write the prompt in `docs/architect/<step>.md`.
2. Add one row to `STEPS` in `architect/agent.py`: template, output file, reviewer, and the earlier outputs it reads.
3. If the step must cover a list of IDs from an earlier output, add a `must_cover(...)` check.
4. Add a test in `tests/test_architect.py`.

## Limits

- The agents need the `claude` CLI and make real model calls, which cost money.
- Output is a draft. Review it before it goes to a client.
- The injection pre-scan reads text files only. A PDF or image with hidden instructions is not scanned by the code; only the rules and the read-only tools protect against it. The pre-scan matches phrases, so a cleverly worded attack can slip past it.
- Prompt rules are instructions, not guarantees. The cases marked Prompt above depend on the model following them, so review the output.
- Plain text, markdown and PDF sources are expected to work. Word files should be converted first. Reading a real architecture diagram image has not been tried.
- The sample documents are made up.
