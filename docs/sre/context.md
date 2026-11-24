STEP 1 - Establish service context.
Read the service catalog entry and the other documents named below (ownership, dependencies, runbooks, SLOs, alert rules, recent changes, escalation). Write the service context record. If a fact is not in the documents write "Not stated": a missing fact is a documentation gap, not something to fill in.

Sections, in this order:
## Status
## Service
Table `| Field | Value | Source |` with rows: Name, Tier, Owner, On-call rotation, Escalation path. Owner, On-call rotation and Escalation path must be copied exactly from the documents.
## Dependencies
Table `| Dependency | Direction | Criticality | Owner | Source |` (Direction is upstream or downstream).
## SLOs
Table `| SLO | Metric | Kind | Objective | Window |`. Kind is exactly one of error_rate, success_ratio, latency_ms, saturation. Metric is the metric name the documents use. Objective is the target as the documents state it: for error_rate and success_ratio the success target such as `99.9%`; for latency_ms the threshold such as `300 ms`; for saturation the maximum such as `80%`. Window such as `30d`.
## Alert rules
Table `| Rule | Metric | Condition | For | Severity |`. Condition is an operator and a number such as `> 0.05`. For is a duration such as `5 min`. Severity as the documents state it.
## Runbooks
Table `| Runbook | Path | Action | Risk | Last reviewed |`, one row per action a runbook offers. Path is the file the documents name. Risk is Low, Medium or High as the runbook states, else Not stated. Last reviewed is a date or Not stated.
## Recent changes
Table `| Time | Change | Source |`, newest first, times as written in the documents.
## Documentation gaps
What is missing, unclear or looks stale, one line each. The system also adds the gaps it can compute.
