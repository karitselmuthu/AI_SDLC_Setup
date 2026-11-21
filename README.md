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
| 1 | `qualify` | RFP, questionnaire, notes, account brief | `opportunity-brief.md` | Pursuit lead |
| 2 | `discover` | Same documents | `requirements.md` | Product owner |
| 3 | `assess` | Diagrams, inventories, standards | `current-state.md` | Tech lead |
| 4 | `options` | Nothing extra | `solution-options.md` | Tech lead, pursuit lead |
| 5 | `design` | Nothing extra | `target-architecture.md` | Tech lead |
| 6 | `fit` | Client standards, policies, contracts | `enterprise-fit.md` | Security, compliance, enterprise architecture |
| 7 | `delivery` | Nothing extra | `delivery-approach.md` | Delivery lead, pursuit lead |
| 8 | `economics` | Spend, price lists, rate card, headcounts | `rom-estimate.md` | Delivery lead, finance, pursuit lead |
| 9 | `proposal` | Bidder profile, credentials, references | `proposal-package.md` | Bid manager, delivery lead, pursuit lead |
| 10a | `discuss` | Nothing extra | `discussion-pack.md` | Bid manager, pursuit lead |
| 10b | `record` | Notes from the client meeting | `opportunity-record.md` | Bid manager |
| 11 | `handoff` | Nothing extra | `solution-baseline.md`, then `architect/baseline/vN/` | Delivery lead, bid manager |

`record` reads its own previous version, so decisions accumulate across meetings.
After a meeting, the record lists which earlier steps are now outdated. Re-run those and approve them again.

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
- **Spend cap.** Each `claude` call is capped at USD 2 (`BUDGET` in `core.py`). Secrets and CI config are on a deny list for every agent.

## Approvals and the baseline

Every approval is appended to `architect/briefs/approvals.log` with a hash of the approved file.
`handoff` refuses to run until every artifact is produced, approved, **unedited since approval**, and not **stale** (an earlier step approved again after it).
When it passes, it writes `architect/baseline/vN/`: a read-only copy of every approved artifact, the handoff document, and a `manifest.json` with hashes, approvers and source documents.
Versions are never overwritten. A new run publishes `v2`, and the handoff document explains what changed.

The log is a local file. It shows what was approved, but it is not tamper-proof.

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
core.py               shared runner: role, tool limits, session, budget, approval prompt
sdlc.py               the SDLC pipeline and review-fix mode
docs/architect/       the 12 step prompts, one per step (these are code: the agent reads them)
docs/architect/samples/  made-up client documents for trying the steps
test_architect.py, test_baseline.py   unit tests
```

## Testing

```bash
pytest -q
```

The tests use a fake model call. They check the plumbing, the coverage checks, the approval and baseline logic, and that each prompt contains its required rules.
They do not judge the quality of what the model writes. For that, run the steps on the sample documents and read the output.

## Adding or changing a step

1. Write the prompt in `docs/architect/<step>.md`.
2. Add one row to `STEPS` in `architect/agent.py`: template, output file, reviewer, and the earlier outputs it reads.
3. If the step must cover a list of IDs from an earlier output, add a `must_cover(...)` check.
4. Add a test in `test_architect.py`.

## Limits

- The agents need the `claude` CLI and make real model calls, which cost money.
- Output is a draft. Review it before it goes to a client.
- Plain text, markdown and PDF sources are expected to work. Word files should be converted first. Reading a real architecture diagram image has not been tried.
- The sample documents are made up.
