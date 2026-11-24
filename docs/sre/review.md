STEP 9 - Learn and improve reliability.
The system has computed the incident facts (timeline, detection delay, budget burn, recurrence) and will put them first in the document. You write the analysis from the approved records. Be blameless.

Sections, in this order:
## Status
## What went well
## Contributing factors
Table `| ID | Factor | Type | Evidence |`. Type is Confirmed (the evidence shows it) or Hypothesis. Every row cites evidence ids.
## Detection gaps
What did not alert, or alerted late, and what would have. Cite the detection delay the system computed.
## Runbook gaps
Where a runbook was missing, wrong or hard to use.
## Follow-up actions
Table `| ID | Action | Owner role | Evidence or gap | Priority |` with ids FU1, FU2, ... Owner is a role, not a person. Priority is High, Medium or Low. Each action must trace to an evidence id, a risk id or a named gap.
## Recurring incidents and SLO trends
What the system computed about recurrence and budget burn, and what it suggests.
