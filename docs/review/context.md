STEP 1: Establish review context. Read the ticket, the design or baseline and pull-request text given, the repository guidance and the surrounding code of what changed. Write:
## Status (Draft, pending review by the senior reviewer)
## Inputs
What you read, with paths. What the ticket, design and guidance require of this change.
## Scope of change
The files changed (given), what each does, in one line each. New files versus modified files.
## Components affected
Components, consumers and interfaces the change touches or could touch.
## Requirement to change map
Table: AC id | Criterion | Files and lines that implement it (`path:line`) | Notes. One row for EVERY acceptance criterion id in the ticket.
## Not provided
Inputs that were not given (design, standards, consumers) and what that limits.
