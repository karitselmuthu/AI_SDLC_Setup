# AI SDLC Setup

AI agents that take a piece of work through the software lifecycle, **with a person approving at every gate**. Nothing an agent writes is final:
every output is a draft, and only a named human reviewer can approve it (or send it back with feedback).

## What is in this repository

| Part | Role | What it produces | Steps | Run it |
|---|---|---|---|---|
| **Architect agent** | Solution architect for a sales opportunity | A versioned, approved solution baseline: requirements, architecture, delivery approach, estimate, proposal | 12 | `architect/agent.py` |
| **Coding agent** | Developer for one approved ticket | A reviewed code change on a new git branch, tests, pull-request text and a package for the human reviewer | 9 | `coder/agent.py` |
| **Review agent** | Senior engineering reviewer for that change | Evidence-based findings (each cites a real file and line), a verification pass, a scorecard, and unresolved High findings routed to a person | 9 | `review/agent.py` |
| **QA agent** | Senior quality analyst for that change | Risk-based test plan, test cases and automated tests, execution evidence, defects, and a quality recommendation | 10 | `qa/agent.py` |
| **Release agent** | Senior release manager for the approved artifact | A release record, a readiness decision, a versioned plan, provenance, configuration status, a recorded promotion, rollout health, a rollback record and the release history | 9 | `release/agent.py` |
| **Web page** | One place to enter a project and follow all five | Status of every step, the approval buttons, the reviewer decision, skip plan | - | `web/app.py` |

All agents run the [Claude Code](https://docs.claude.com/en/docs/claude-code) CLI (`claude -p`) with a role, a tool allow-list and a spend cap.
Facts (test results, counts, verdicts, status) are computed by plain code from real evidence, never taken from what a model says.

## Contents

[How the pieces fit](#how-the-pieces-fit) · [Quick start](#quick-start) · [Ideas that apply everywhere](#ideas-that-apply-everywhere) ·
[Architect agent](#architect-agent-12-steps) · [Coding agent](#coding-agent-9-steps) · [Review agent](#review-agent-9-steps) · [QA agent](#qa-agent-10-steps) · [Release agent](#release-agent-9-steps) · [Web page](#web-page) ·
[Repository layout](#repository-layout) · [Testing](#testing) · [Adding a step](#adding-or-changing-a-step) · [Limits](#limits)

## How the pieces fit

```
 project description, RFP, notes
            |
   Architect agent (12 steps)  ->  approved solution baseline (versioned, read-only)
            |                       a person writes or approves the ticket
            v
   Coding agent (9 steps)      ->  change on a new branch + tests + pull-request text
            |                       reviewer decides on the merge (the agent never merges or pushes)
            v
   Review agent (9 steps)      ->  findings with file and line evidence, scorecard
            |                       unresolved High findings go to a person
            v
   QA agent (10 steps)         ->  test evidence, defects, quality recommendation
                                    a person makes the release decision
            |
            v
   Release agent (9 steps)     ->  readiness, plan, provenance, promotion, health, rollback, history
                                    the Release Manager approves production; the agent never does
```

| Agent | Who approves (each role signs separately) |
|---|---|
| Architect | Account lead, lead solution architect, delivery lead, security, compliance, legal, finance reviewers (depends on the step) |
| Coding | Tech lead and ticket owner; at the end, the human code reviewer makes the merge decision |
| Review | Senior reviewer (every step); the tech lead signs the final report and takes the disposition of unresolved Critical and High findings |
| QA | QA lead, a developer (QA cannot approve its own findings), and a release owner who reads the recommendation |
| Release | The Release Manager signs every record and authorizes the promotion; a deployment operator also signs the plan |

Each step reads only the approved output of the steps before it. A step cannot run until the earlier ones are approved, and a document edited after
approval is flagged. You do not have to run every step: see the [skip plan](#skip-plan-not-every-project-needs-every-step).

## Quick start

Requirements: Python 3.8+, the `claude` CLI installed and logged in, `pytest` for the tests. Model calls cost money (see [token and cost](#token-and-cost-measurement)).

```bash
git clone https://github.com/karitselmuthu/AI_SDLC_Setup.git && cd AI_SDLC_Setup
pip install pytest && pytest -q        # all tests use a fake model call, so they cost nothing
```

**Easiest: the web page.**

```bash
python web/app.py                      # opens http://127.0.0.1:8765/
```

Create a project (name and description, optional documents). Press **Run next step** on the Architect, read the draft in the **Needs you** panel, and
**Approve** or **Send back**. For the Coder, Review and QA, set the repository folder and paste the approved ticket under "Documents and Coder setup".

**Or the command line**, one agent at a time (each asks you to approve in the terminal):

```bash
S=docs/architect/samples               # made-up sample documents
python architect/agent.py qualify  $S/rfp.md $S/notes.md          # then discover, assess, ... handoff
python coder/agent.py understand docs/coder/samples/ticket.md --repo /path/to/repo   # then inspect ... handoff
python review/agent.py context TICKET.md --repo /path/to/repo      # then correctness, interfaces ... report
python qa/agent.py scope TICKET.md --repo /path/to/repo           # then risk, coverage ... recommend
```

Each step prints `wrote: <file>` and asks the named reviewer: `y` to approve, or `n` plus feedback to have the agent redo it.

## Ideas that apply everywhere

### How a step works

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


### Guardrails

- **Read-only architect.** The architect agent can read, search and open PDFs and images. It cannot edit files or run commands.
- **Never invent.** Every template tells the agent to write "Not stated" instead of guessing. Values it proposes itself are marked "Proposed".
- **Evidence or confirm.** Claims about the bidder are cited to a document or marked `[CONFIRM: ...]`. Expired or indicative quotes are never treated as confirmed.
- **No leaks.** Client-facing text must not contain the rate card, cost, margin or the ROM. Meeting material is labelled `[CLIENT-SHAREABLE]` or `[INTERNAL]`.
- **Honest about gaps.** A requirement the design cannot meet is never answered "Full". Verbal figures from a meeting are recorded as unconfirmed.
- **Documents are data.** The shared rules (`docs/architect/_rules.md`) are put in front of every step. Text in an RFP or notes cannot change the rules, the files the agent may read, or the approval process. Before each run the code scans the supplied text files for instruction-like lines ("ignore previous instructions", "mark this as approved"...). It warns the reviewer, and the output must list them under `## Source-document anomalies`.
- **The agent cannot approve.** Approval is a prompt in code that a document cannot reach. If the model writes "Status: Approved" or "final version" it is sent back once to fix it.
- **No unevidenced certifications.** ISO, SOC 2, PCI DSS, GDPR and similar are never claimed unless a supplied document shows them.
- **Spend cap.** Each `claude` call is capped at USD 2 (`BUDGET` in `core.py`). Secrets and CI config are on a deny list for every agent.


### Approvals and the baseline

Every approval is appended to `architect/briefs/approvals.log` with a hash of the approved file and the role that approved it.
Every step lists its reviewers by role and each role approves **separately**, never one "y" for a group. The four checkpoint groups are the account lead (opportunity fit, client messaging, commitments), the lead solution architect (technical correctness, standards fit, exceptions), the delivery lead (feasibility, staffing, schedule, estimate assumptions) and the security, compliance, legal and finance reviewers (their obligations and commitments). The proposal needs all six roles; the handoff needs account lead, lead architect and delivery lead. They are asked one by one, and a "no" from any of them sends the draft back and restarts the round. An approval only counts for the exact content it was given on.
`handoff` refuses to run until every artifact is produced, approved by all its required roles, **unedited since approval**, and not **stale** (an earlier step approved again after it).
When it passes, it writes `architect/baseline/vN/`: a read-only copy of every approved artifact, the handoff document, and a `manifest.json` (status `approved`) with hashes, every approver and the source documents. The solution is never marked final before that.
Versions are never overwritten. A new run publishes `v2`, and the handoff document explains what changed.

The log is a local file. It shows what was approved, but it is not tamper-proof.


### Skip plan (not every project needs every step)

Plain rules read the inputs and *suggest* steps that may not be needed (`skipplan.py`). The page shows "Suggested skip: <reason>", and **Run all** pauses
before such a step. Nothing is skipped until a person clicks **Skip...**, gives a name and a reason; the code then writes a placeholder document and
logs it in the approvals ledger as `SKIPPED by <name>` with the reason. No model runs for a skipped step, the page shows "Skipped by ...", and
the QA recommendation lists what was skipped as a limitation. Running the step later replaces the placeholder.

| Agent | Skippable | Suggested when |
|---|---|---|
| Architect | assess | the input is under 400 words and describes no current environment |
| | economics | under 400 words and no budget, volumes, users or dates |
| | discuss | under 400 words |
| | record | no client meeting notes were supplied |
| Coder | detect | the stack adapters found one technology, no gaps, no unsupported files |
| Review | accessibility | no user-facing file (HTML, CSS, JSX, TSX, Vue, Svelte) changed |
| | interfaces | every changed source file is new (no existing consumers) and no interface, schema, dependency or configuration file changed |
| | cost | no dependency, infrastructure or cloud-service file changed and no compliance control is mentioned |
| QA | nonfunctional | the approved scope and risk plan state no performance, accessibility, security, reliability or compatibility expectation |
| | explore | 2 files or fewer and 80 lines or fewer changed, and no High-rated risk |


### Token and cost measurement

Every model call is logged to `usage.jsonl` (in `SDLC_WORKSPACE`, git-ignored) with the CLI's real token counts and cost. `python tokens.py [WORKSPACE]`
prints one row per agent step. Calls use `--disable-slash-commands --strict-mcp-config --setting-sources ""`: without them every call loaded the user's
skills, plugins and MCP tools (about 65,000 input tokens for one word); with them about 6,000. Agent tool limits and deny rules are still passed explicitly.

## Architect agent (12 steps)

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

## Coding agent (9 steps)

A separate agent in `coder/`, built one activity at a time like the architect. It is read-only until a plan is approved.

| # | Command | What you pass | Output in `coder/briefs/` | Reviewers |
|---|---|---|---|---|
| 1 | `understand` | The approved ticket, then any design or standards files, and `--repo PATH` | `implementation-plan.md` | Tech lead, ticket owner (each signs separately) |

| 2 | `inspect` | `--repo PATH` (reads the approved step 1 plan itself) | `repository-inspection.md` | Tech lead |

| 3 | `detect` | `--repo PATH` (reads the approved step 2 inspection itself) | `stack-profile.md` | Tech lead |

| 4 | `plan` | `--repo PATH` (reads the three approved outputs above itself) | `change-plan.md` | Tech lead, ticket owner (each signs separately) |

| 5 | `implement` | `--repo PATH` (reads the approved change plan itself) | `implementation-report.md`, plus the edits on a new git branch | Tech lead |

| 6 | `tests` | `--repo PATH` (on the branch step 5 created), optional `--check CMD` | `test-report.md`, plus test edits on that branch | Tech lead |
| 7 | `review` | `--repo PATH` (same branch) | `review-report.md`, `change.diff` | Tech lead |
| 8 | `pr` | `--repo PATH` (same branch) | `pull-request.md` | Tech lead, ticket owner |
| 9 | `handoff` | `--repo PATH` (same branch), optional `--no-decision` | `handoff-package.md`, `handoff-decisions.log` | Reviewer (merge decision) |

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

**Step 7 reviews the whole change before handoff; step 8 prepares the pull request.** Both only read, and neither pushes or opens the PR:
step 8 prints the `git push` and `gh pr create` commands for a human to run.

Step 7 first runs a plain-code scanner (`coder/diffscan.py`) over the **added lines** of the diff: secrets (key formats, credential-looking
assignments, secret-bearing files such as `.env` or `*.pem`, always masked in the report), merge-conflict markers, unsafe defaults (TLS verification
off, `shell=True`, `eval`, `0.0.0.0`, debug on...), swallowed or bare exceptions, and leftovers (debugger, TODO, print). Code also adds files changed
that no planned change or test covers, unplanned untracked files, plan changes not marked Done, and failing or unrun checks. The model must answer
every scanner finding, every planned change and every acceptance criterion (checked in code, one repair pass), and list limitations and remaining
questions. **The verdict comes from the code:** any Blocker from the scan or the model means "Not ready for human review", whatever the model says.
The report always says it is a self-review, not an independent review or approval.

Step 8 needs the review approved and not stale. The model writes only the title, problem, implementation summary, acceptance-criteria mapping, risks
and migration notes (checked: title length, a row per criterion, migration section present, no secrets, no approval or QA claims). Code adds the
ticket link (or says it is not stated), the files changed with line counts from git, the real check results, the review outcome with its limitations and
open questions, the approved source documents with content hashes and approvers, and a reviewer checklist. Nothing factual is left to the model.

**Step 9 is the human handoff (`coder/handoff.py`), and it calls no model.** The agent prepares the code and the evidence; **the reviewer makes
the merge decision**. The package (`handoff-package.md`) is assembled only from the approved records and from git, so nothing in it can be
embellished: the ticket and its link, the implementation plan and planned changes, the changed files with line counts, the acceptance criteria
mapping with any criterion not fully met, the tests run and their real results, the checks that were **not** run (and why), the coverage gaps and
unsupported technologies, the known risks, the self-review's should-fix items, limitations and remaining questions, and a table of every approved
document with its hash and approvers. It states what the agent did and did not do (no commit, push, pull request or merge).

Gates: the **whole** chain (not only the last step) must be approved, unedited and current, the repository must be on the implementation branch,
and the working tree must still match the diff the review saw (`change.diff`), so the reviewer sees what will actually be merged. The package says
"Not ready to merge" when it records a blocker or a failing check. The reviewer's decision (approve, changes or reject) is asked at the end and can
**only be recorded by a person at a terminal**: a script or a piped answer records nothing. It needs the reviewer's name, and a written reason for
changes, reject, or an approval that accepts known open items. It is appended to `handoff-decisions.log` with the package hash and
`merged_by_agent: false`, and only an approval is added to the approvals ledger. `--no-decision` writes the package and asks nothing.

**Stack adapters (`coder/adapters.py`) select the checks, not a fixed "all technologies" list.** Plain code detects what the repository actually
uses from its files (never from the model) and offers only that technology's own checks, in check mode: it covers web frontend
(JavaScript/TypeScript with React, Angular, Vue, Svelte, Next.js, using the repository's own `package.json` scripts and package manager), backend
services (Python, Java/Spring via Maven or Gradle, C#/.NET, Node.js, Go, Rust, PHP, Ruby), mobile and desktop (Android, Swift, Flutter/Dart, React
Native, Electron), data and databases (SQL migrations, PostgreSQL, MySQL, SQL Server, Oracle, MongoDB, Redis), data engineering and AI (Python
pipelines), infrastructure code (Terraform, CloudFormation, CDK, Pulumi, Kubernetes, Helm) and cross-stack interfaces (OpenAPI, GraphQL, protobuf,
AsyncAPI, shared schemas). A check is chosen only when the repository shows it uses that tool (a config file or a script), and the commands are fixed
in the code, never taken from a document. Nothing installs, deploys, applies or restores: a check whose tool, installed dependencies or offline
resolution is missing is **reported as not run, with the reason**. Where no safe automatic check exists (a database to migrate, `cdk synth`,
`pulumi preview`, an Xcode scheme, permission files, API contracts) it is listed as a manual item or a gap for a person. A language with no adapter,
or source files with no build file, are reported as **unsupported** and nothing is guessed. Step 3 gets these findings as ground truth, steps 5 and 6
tell the model which conventions the repository shows, and step 6 writes a **Stack coverage** section: detected stack and evidence, checks
selected, run and not run (a check is PASS or FAIL only if it really ran), gaps and unsupported technologies. The verdict line says when coverage is
incomplete and step 8 copies the coverage into the pull request. Step 7 flags changed interface, schema and migration files for a compatibility check.

**The code, not the model, runs the checks** (the agent has no shell). The commands come from the approved stack profile (only recognised check
runners such as `pytest`, `ruff`, `mypy`, `yarn test`, `go test` or `make test`, matched on the command itself; a command that merely mentions one, like a script that launches a pipeline, is never run; installs, deploys, network, git, `rm` and shell chaining are filtered out) or from `--check CMD`, and the tech lead approves the
list before anything runs. The checks run once before the model edits (a baseline) and again after, so new failures are told apart from ones that were
already there. Failing output from a check that **passed before** is fed back to the model to fix the tests, at most 3 times, and then a human decides; a check that was already failing is reported but not fed back, since the model cannot have caused it. Failures, timeouts and "not run"
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

## Review agent (9 steps)

A senior engineering reviewer for one proposed change. It **reviews only**: its tools are read-only, so it cannot edit code, run tests, approve a release or merge.
Every step writes to `review/briefs/`, and a named person approves it.

| # | Step | What it does | Output | Model? |
|---|---|---|---|---|
| 1 | `context` | Records the change under review (`change.diff`, taken from git without touching your index), detects the stack areas it touches (`review-areas.md`), and maps every acceptance criterion to the code | `review-context.md` | yes |
| 2 | `correctness` | Behaviour against the acceptance criteria and the approved design | `correctness-findings.md` | yes |
| 3 | `interfaces` | Changed APIs, schemas, configuration, shared code; existing consumers and upgrade paths | `interface-findings.md` | yes |
| 4 | `security` | Authorization, validation, secrets, sensitive data, logging. Uncertain concerns are labelled Question for a person to validate | `security-findings.md` | yes |
| 5 | `reliability` | Error paths, retries, timeouts, concurrency, resource use, performance-sensitive code | `reliability-findings.md` | yes |
| 6 | `accessibility` | Semantics, keyboard access, labels, focus, contrast, for user-facing changes | `accessibility-findings.md` | yes |
| 7 | `cost` | Code-level cost drivers and possible effects on stated compliance controls | `cost-compliance-findings.md` | yes |
| 8 | `verify` | Re-reads the code for every finding: Confirmed, Handled elsewhere, Question, Recommendation or Withdrawn | `verification.md` | yes |
| 9 | `report` | The review summary and overall status, prioritized findings, a scorecard by dimension (correctness, design fit, security, privacy, maintainability, reliability, accessibility, cost, compliance applicability), the findings routed for human disposition, coverage and limitations | `review-report.md` | no |

```bash
python review/agent.py context TICKET [FILE...] --repo PATH [--base REF]   # default: the uncommitted work; --base compares against a commit or branch
python review/agent.py correctness --repo PATH                             # then interfaces, security, reliability, accessibility, cost, verify, report
```

**Severity scale** (the same everywhere in the report):

| Severity | Meaning |
|---|---|
| Critical | A likely severe impact, such as broad unauthorized access, secret exposure or destructive data loss |
| High | A significant security, privacy, correctness or availability risk affecting important behaviour |
| Medium | A meaningful defect or maintainability risk with limited scope or a viable workaround |
| Low | A localized issue with minor impact |
| Informational | A question or improvement suggestion, not a confirmed defect |

**Stack-aware review adapters** (`review/adapters.py`, plain code, no model). The `context` step finds which areas the change touches from repository evidence
(file names, manifests, added lines) and hands the model the focus for each. Areas the change does not touch are not reviewed, and a language with no adapter
(C, C++, COBOL, Shell, Elixir, R, Lua and similar) is listed as **unsupported** and routed for specialist review, never assumed to be covered.

| Area | Detected from | Review focus |
|---|---|---|
| Frontend | `.tsx .jsx .vue .svelte .html .css`, React, Vue, Angular, Svelte in `package.json` | state and rendering, unsafe browser behaviour, accessibility, input handling, client-side secrets |
| Backend | Python, Java, Kotlin, C#, Go, Rust, PHP, Ruby, Scala, Node source (not tests) | business logic, authorization, validation, error handling, concurrency, API behaviour |
| Mobile and desktop | `AndroidManifest.xml`, `Info.plist`, `.swift`, `.dart`, Electron, React Native | permissions, sensitive storage, platform behaviour, accessibility, secure communication |
| Data and databases | `.sql`, migrations, Prisma, SQL statements or database clients in added code | query safety, schema changes, data integrity, sensitive data, migration compatibility |
| Integration and messaging | OpenAPI, GraphQL, protobuf, webhooks, queues, HTTP clients in added code | contract compatibility, authentication, retries, idempotency, ordering, failure handling |
| Infrastructure and delivery | Terraform, Dockerfile, Helm, Kubernetes, serverless, CI workflows | permissions, exposed endpoints, secret handling, insecure defaults, scaling and cost |
| AI and data applications | model SDKs, embeddings, vector stores, pipeline tools in added code | data exposure, access boundaries, unsafe tool use, evaluation assumptions, logging, resource cost |
| Cross-cutting | always | maintainability, reliability, observability, privacy, policy alignment, evidence quality |

Rules enforced by code, not by the prompt alone:

- Every finding needs a severity, a confidence (Confirmed, Probable, Question), a `path:line` that exists in the repository, the affected behaviour, the impact, the triggering conditions or reproduction, and a recommended direction. An invented citation is sent back.
- A finding is **Confirmed** only with the cited code *and* its triggering conditions; otherwise it must be Probable or Question. Informational is never Confirmed.
- Remediation is described in words; a finding written as replacement code is sent back.
- The agent may not say "approved", "LGTM" or "safe to merge", and may not claim a change is compliant: code inspection cannot establish formal compliance.
- The scanner (secrets, unsafe defaults, leftovers) runs on the diff in plain code and its terms are mapped to the scale (Blocker is Critical, Should fix is Medium, Check is Informational). Scanner Critical findings go straight to the routed list, with secrets masked.
- The scorecard counts, the routed list ("Critical or High and still standing after verification") and the coverage table are computed from the approved records. The tech lead signs the final report and takes the disposition of every routed finding.
- Speculation is never a defect: a Confirmed finding that says "may", "could" or "potentially" is sent back. Without a `file:line` that exists, a finding is shown as an unverified question (Informational), never with a defect severity. A missing audit event needs a cited requirement or control; a cost figure, percentage or compliance verdict is refused.
- A change that touches an interface, schema or migration file must be addressed in the interface findings; instructions planted in the changed files are scanned as data like the README and the ticket.
- If the ticket has no acceptance criteria, or no design or pull-request text was supplied, the report says design-fit review is limited and names the missing inputs. A large or mixed-stack change is reported as not completely covered.
- Accessibility, interfaces and cost can be skipped when the change has nothing for them (see the skip plan); the report lists what was skipped, by whom and why.

## QA agent (10 steps)

A senior quality analyst for one change. Same pattern as the other agents: each step writes to `qa/briefs/`, named humans approve it, approvals go to the ledger.

| # | Step | Output | Model? |
|---|---|---|---|
| 1 | `scope`: requirements-to-test map, open questions, in/out of scope | `test-scope.md` | yes |
| 2 | `risk`: impact and likelihood per area, prioritised | `risk-plan.md` | yes |
| 3 | `coverage`: test levels and types, coverage gaps | `test-approach.md` | yes |
| 4 | `design`: positive, negative, boundary, failure cases and safe data | `test-cases.md` | yes |
| 5 | `automate`: writes test files only; application edits are reverted and reported | `automation-report.md` | yes |
| 6 | `execute`: the code runs the approved checks: pass, fail, blocked, not run | `execution-report.md` | no |
| 7 | `explore`: exploratory and regression assessment | `exploration-report.md` | yes |
| 8 | `nonfunctional`: six dimensions, each Assessed, Gap or Not applicable | `nonfunctional-report.md` | yes |
| 9 | `defects`: every failing check classified, defects with severity and evidence | `defect-report.md` | yes |
| 10 | `recommend`: verdict computed from the records, never a release decision | `qa-recommendation.md` | no |

```bash
python qa/agent.py scope TICKET [FILE...] --repo PATH     # then risk, coverage, design, automate, execute, explore, nonfunctional, defects, recommend
```

Facts come from code (counts, results, the verdict). QA cannot approve its own findings (a developer approves the defect report too), edits test
files only, and a model that writes "approved for release" is sent back. A person makes the release decision. The web page shows it as a third track.

Acceptance: `tests/test_qa_acceptance.py` has one test for each of the 18 QA cases (complete criteria, ambiguity, high risk, boundaries, roles, API, migration, cross-stack, regression, flaky, environment, privacy, security finding, unsupported stack, defect reproduction, fix retest, report integrity, untrusted input). A failing check is re-run twice and every attempt is recorded: fail then pass is FLAKY, never PASS.

## Release agent (9 steps)

A senior release manager for one approved artifact. It prepares and documents a controlled promotion and, **only when the Release Manager authorizes it**, runs the promotion commands the approved plan lists. It does not build the application, replace QA or code review, or approve its own production release. Two steps use a model; the other seven are plain code.

| # | Step | What happens | Output | Model? |
|---|---|---|---|---|
| 1 | `request` | Reads the release request, change record and QA and review results into a release record. Every value (artifact, version, commit, checksum) must appear in the documents, or it says Not stated | `release-record.md` | yes |
| 2 | `readiness` | Gates from the approved review, QA and pull-request records, the window, freeze, dependencies and rollback criteria. **Missing** evidence is told apart from **failed** evidence | `readiness.md` | no |
| 3 | `plan` | Strategy (rolling, canary, blue-green, phased, feature-flagged), flags, configuration references, migration, the exact promotion and rollback commands, health checks with pause and rollback thresholds, communications. Versioned | `release-plan.md` | yes |
| 4 | `provenance` | Hashes the artifact, compares it with the declared checksum, finds the source commit, and locks the release candidate | `provenance.md` | no |
| 5 | `config` | Checks configuration and secret references are present in the target (names only, never values) | `config-status.md` | no |
| 6 | `promote` | **Re-checks every gate now**, shows the exact commands, and runs them only after the Release Manager says yes. Stops at the first failure | `deployment-log.md` | no |
| 7 | `monitor` | Samples the plan's health checks for its window; applies the pause and rollback thresholds | `rollout-health.md` | no |
| 8 | `rollback` | Runs the pre-approved rollback when a rollback threshold was reached (or when a person orders it with `--manual`), then re-checks health | `recovery-record.md` | no |
| 9 | `close` | The final version, environments, approvals, checks, outcome, incidents, rollback status and follow-ups | `release-history.md` | no |

```bash
python release/agent.py request REQUEST.md [PR.md QA.md ...]     # then readiness, plan, provenance, config, promote, monitor, rollback, close
python release/agent.py promote --repo PATH                      # the commands run in PATH; --repo is needed for steps 4 to 8 on the page
```

What the code enforces, not the prompt:

- **Production stays blocked** until every gate is met. A non-production target is blocked only by the essential gates (artifact identity, Release Manager named, rollback criteria, environment).
- **Gates are re-checked at promotion**, not trusted from the readiness report: an artifact changed after provenance, a failed configuration reference, a missing earlier environment (`staging -> production`) or an edited approval each refuse the promotion and nothing runs.
- **Nothing runs without the Release Manager's yes.** The authorization is pinned in the approvals ledger to the plan hash and the artifact hash. The web page's **Run all** never starts a promotion.
- **Secrets are masked** in every command, log and report (token shapes and `NAME=value` pairs). Configuration is checked by "present or absent", never by reading the value.
- **Plans are checked**: a destructive or pushing command (`rm -rf /`, `git push`, `curl | sh`), a `|` that would shift the table columns, an unknown strategy or an invalid health condition sends the plan back.
- **A pause keeps sampling; only a rollback threshold stops it.** A failed promotion is not rolled back automatically: a person decides (`rollback --manual`).

**Technology and deployment coverage** (`release/adapters.py`, plain code, no model). The agent has no native integration with any platform; it runs only the commands in the approved plan. What the adapters do is find which kinds of deployment a release involves from repository files, manifest contents, the artifact (for example an image reference or an `.aab`) and the commands in the request and plan, and list the checks that matter for each. The plan must then say, for every check, how it is covered: a plan item that exists (`Promotion command 2`, `Health check <name>`, `Configuration reference <name>`, `Rollback step 1`), `Manual: <what> by <role>`, or an honest `Not covered: <reason>`. A claim that "the platform handles it" is sent back.

| Release target | Detected from | Release checks |
|---|---|---|
| Containers and orchestration | Dockerfile, compose, Helm, Kubernetes manifests (by contents), image references | Image identity, registry provenance, configuration, readiness probes, rollout status, rollback behavior |
| Cloud application services | `appspec.yml`, `app.yaml`, `buildspec.yml`, `aws`/`az`/`gcloud` commands | Target account or project, region, identity permissions, environment configuration, health status, promotion path |
| Serverless | `serverless.yml`, `samconfig.toml`, `host.json`, SAM templates (by contents) | Package version, triggers, permissions, concurrency settings, compatibility, rollback limitations |
| Virtual machines and data centers | Packer, Ansible, Chef, Puppet, `.ova` `.vmdk` `.rpm` `.deb` | Image or package identity, host readiness, configuration drift, deployment order, recovery process |
| Web and mobile applications | Android and iOS projects, Fastlane, Netlify, Vercel, Firebase, `.apk` `.aab` `.ipa` | Environment, release channel, signing or package identity, staged rollout, user-impact checks |
| Data and database changes | `.sql`, migrations, Alembic, Flyway, Liquibase, Prisma, dbt, DAGs | Backward compatibility, migration order, lock or downtime risk, recovery strategy, data validation gates |
| Infrastructure as code | Terraform, CloudFormation (by contents), CDK, Pulumi | Plan or diff review, policy checks, target scope, dependency order, change impact |
| Cross-cutting delivery systems | Always; names the CI/CD files when there are any | Approval enforcement, immutable artifacts, credentials scope, audit record, workflow integrity |

A technology with no adapter (mainframe JCL and COBOL, Windows installers and SCCM, Cloud Foundry, Nomad, Salesforce, SAP transports, Heroku) is listed as **unsupported** and the plan must say it needs a specialist; nothing is assumed about how it deploys. The readiness report, the authorization prompt and the release history all show the targets, which checks are addressed or not covered, and the unsupported ones. Detection is by file names, a few file contents and command words, so it can miss a target that leaves no such trace; it never invents one.

Acceptance: `tests/test_release_adapters.py` has a test for each target row, unsupported targets and the plan checks. `tests/test_release.py` runs every step with tiny shell commands that write marker files, including the refusals above.

## Web page

```bash
python web/app.py            # opens http://127.0.0.1:8765/ ; use --port N to change it, --no-open to not open a browser
```

Enter the project name and information (and any documents), then follow the **Architect** (12 steps), the **Coder** (9), the **Review** agent (9), **QA** (10) and the **Release** agent (9) on one page, side by side. Each
track shows every step's status, who has approved, and buttons to run the next step or all steps. **Run all** pauses at every approval, and before any step the skip plan suggests leaving out. **Skip...** records who skipped a step and why. When a step
finishes a draft, a **Needs you** panel shows the draft and the role you are approving as: **Approve**, or **Send back** with feedback (required).
Your click is the only thing that answers the agent's `approve? [y/N]` prompt, and it is written to the same approvals ledger the command line uses.
Status comes from that ledger, not from what a model says. For the Coder, set the repository folder and paste the approved ticket under
"Documents and Coder setup" (Review, QA and Release use the same repository; add the release request as a document of kind **Release request**; the release commands run in the repository folder); the Coder's handoff step ends with a **Reviewer decision** form (the page never merges anything).

Each project keeps its own files under `projects/<id>/` (git-ignored). It uses only the standard library and listens on 127.0.0.1 only, with a
Host and Origin check and a per-run token on every change, so another web page cannot approve for you. It is not a login: anyone who can use this
computer's browser can approve. Documents can only be read from a fixed list of file names inside the project.

## Repository layout

```
architect/        Architect agent: agent.py (STEPS table, checks, approval loop), baseline.py (approval ledger, versioned baseline)
coder/            Coding agent: agent.py (steps and checks), adapters.py (stack checks), stack.py, diffscan.py, handoff.py
review/           Review agent: agent.py (nine steps, evidence and verdict checks, code-built scorecard), adapters.py (stack areas and unsupported languages)
qa/               QA agent: agent.py (ten steps, checks, execution, recommendation)
release/          Release agent: agent.py (nine steps, readiness gates, provenance, gated promotion, health, rollback), adapters.py (release targets and their checks)
web/              Web page: app.py (standard-library server) and index.html (the single page)
core.py           Shared runner: role, tool limits, session, budget, approval prompt, injection scan, token log
skipplan.py       Rules that suggest which steps a project may not need
tokens.py         Per-step token and cost report from usage.jsonl
docs/             The prompts the agents read (these are code): docs/architect, docs/coder, docs/review, docs/qa, each with _rules.md; samples in docs/*/samples
tests/            All tests (pytest.ini sets the paths)
projects/         One folder per web-page project (git-ignored)
architect/briefs, coder/briefs, review/briefs, qa/briefs, */baseline, usage.jsonl    generated outputs (git-ignored)
```

Tests, by area: `test_architect.py`, `test_baseline.py`, `test_acceptance.py` (architect); `test_coder.py`, `test_stack.py`, `test_implement.py`,
`test_tests_step.py`, `test_diffscan.py`, `test_handoff.py`, `test_adapters.py`, `test_coder_acceptance.py`, `test_human_handoff.py` (coding agent);
`test_review.py`, `test_review_acceptance.py` (Review, 15 acceptance cases); `test_qa.py`, `test_qa_acceptance.py` (QA); `test_release.py`, `test_release_adapters.py` (Release); `test_web.py`, `test_skipplan.py`, `test_tokens.py` (page, skip plan, token log).

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

### Coding agent acceptance cases (`tests/test_coder_acceptance.py`)

One test per prepared case. Models are faked and repositories are real temporary git repos, so these prove what the code guarantees.

| # | Case | What the code guarantees |
|---|---|---|
| 1 | Clear ticket and design | Edits are limited to the planned files; every change is bounded and traced to a criterion |
| 2 | Ambiguous requirement | "Ready with assumptions" needs a recorded `Assumption`; a plan marked `Blocked` stops every later step and `implement` makes no edit |
| 3 | Stack detection | The scanner and adapters find languages, frameworks and build tools from files; the build tool follows the lockfile |
| 4 | Unsupported technology | Reported as unsupported; if no check can run, the report says "NOT run" and never "passed" |
| 5 | Existing conventions | The prompt forbids unplanned dependencies; an unplanned manifest edit is reverted |
| 6 | Criteria coverage | A criterion with no test, review or PR row is sent back; "Not met" stays visible |
| 7 | Boundary and failure | Empty boundary or failure cells are sent back; removed, skipped or never-failing tests are flagged |
| 8 | Multi-module repository | Every module needs a row in "Modules and dependent builds"; untouched modules are named and dependents are stated as not computed |
| 9 | Dependency changes | A changed declaration without its lockfile is Should fix; the PR must explain each dependency and the validation limits |
| 10 | Database or schema change | Migration and schema files are flagged; the PR must state compatibility and rollback |
| 11 | Secrets | Key formats, secret files and logged credentials are flagged and masked; agents cannot touch `.env*` |
| 12 | Test failure | The real output and exit code are recorded; deleted tests are flagged; a failure is never reported as passed |
| 13 | Tool or environment failure | A missing tool, timeout or unreachable service is "could not run", not a test failure, and is never fed back to the model |
| 14 | Scope control | Out-of-scope edits are reverted and reported; the tool refuses unlisted files |
| 15 | PR readiness | Summary, results, criteria mapping, limitations, files and approvals are all present |
| 16 | Untrusted content | Instructions in tickets and repository files are flagged as data; permissions come from the code |

Limits: environment failure is a judgement from the exit code and output ("probable"); module dependents are not inferred from code;
dependency changes are detected by line patterns, so a minified single-line manifest can be missed.

## Adding or changing a step

Shown for the Architect; the Coding and QA agents use the same `STEPS` table pattern (`coder/agent.py`, `qa/agent.py`, prompts in `docs/coder`, `docs/qa`).

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
- The QA agent runs only the checks the stack adapters can run here. Anything else (for example performance, accessibility, security tools) is listed as a gap for a person or specialist, never reported as passed.
- Only the Architect and Coding agents have been run step by step with the real model on a real project; the QA agent's steps 1 to 4 and a full run were checked on one small ticket, and the token and cost figures for the Architect and Coding agents are estimates.
- Skipping a step is available on the web page only, not from the command line. Release steps cannot be skipped.
- The Release agent has been tested with canned model replies and one real run (a model-drafted record and plan, about $1.6 for 5 model calls) against fake local shell scripts, not a real deployment. Unsupported targets are reported, not blocked: there is no way yet to record a specialist's sign-off, so the Release Manager reads the warning and decides. It cannot verify a container image digest or read a build system, secret manager or monitoring tool: it runs the checks the approved plan names and records what they return. A Critical or High review finding blocks production and there is no waiver mechanism yet; a person must resolve it and re-run the review.
- The Review agent has been checked with canned model replies and one real run on a small change. Its findings are drafts for a person: a model can still miss a defect, so it supports a human review and does not replace one.
