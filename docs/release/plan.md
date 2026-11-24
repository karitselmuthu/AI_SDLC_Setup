STEP 3 - Prepare the release plan.
Read the approved release record and write a reviewable release plan for the target environment in it. The release request describes the deployment tooling (deploy, rollback and health commands and arguments): use them exactly as written there. A table cell cannot contain the | character, so a command with a pipe goes in a script the plan names. Use only commands and names the source documents or the repository show; if the deployment tooling is not described, write "Not stated" in the command cell rather than guessing.

Sections, in this order:
## Status
## Rollout sequence
Numbered steps, who does each, the target environment and the version.
## Deployment strategy
First line exactly `Strategy: <one of rolling, canary, blue-green, phased, feature-flagged>`, then why.
## Feature flags
Table `| Flag | State at release | Owner |` or "None used".
## Configuration references
Table `| Name | Kind | Check command |`. Kind is `config` or `secret`. Names and references only, never values. Check command is a command that exits 0 when the reference is present in the target environment, or "Not checkable here".
## Migration steps
Numbered list, or "None".
## Promotion commands
Table `| Step | Command | Purpose |` in the order they run. These are run by the system only after the Release Manager approves the exact list.
## Health checks
Table `| Check | Command | Pass condition | Pause after | Roll back after |`. Pass condition is exactly `exit 0` or `value <= N` (also `>=`, `<`, `>`, `==`; the command prints the number last). Pause after and Roll back after are whole numbers of consecutive failures (the pause column may be `-`).
## Monitoring window
Exactly `Window: N samples every S seconds`.
## Rollback
Table `| Step | Command | Purpose |` that restores the previous version. Pre-approved with this plan; the system runs it only when a Roll back after threshold is reached.
## Communications
Table `| Audience | Message | When |` for operators and stakeholders.
## Success criteria
Bullet list a person can check.
## Target checks
The code detects which deployment targets this release involves and lists them, with their checks, below the request. Add a table `| Target | Check | How it is covered |` with one row for every target and check listed (copy the names exactly). "How it is covered" must be one of: `Promotion command N`, `Rollback step N`, `Health check <name>`, `Configuration reference <name>` (an item that exists in this plan), `Manual: <what> by <role>`, `Not covered: <reason>` or `Not applicable: <reason>`. Never claim a check is handled by "the platform" or "the pipeline" without a plan item that does it. A target the code lists as unsupported gets one row `| <target> | All checks | Not covered: needs a specialist |`.
