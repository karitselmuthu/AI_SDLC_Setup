STEP 5 - Recommend response actions.
Read the approved triage and the approved service context. Suggest the least risky relevant action from the runbooks in the context, and say why. You recommend; nothing is run and nothing is changed by this step.

Sections, in this order:
## Status
## Recommendations
Table `| ID | Action | Runbook | Risk | Expected effect | Prerequisites | Rollback or recovery | Addresses |` with ids A1, A2, ..., ordered least risky first (Low, then Medium, then High).
- Action: the action name exactly as the Runbooks table lists it, or `Escalate` or `Gather more information` (both Low risk, no runbook), or `Manual: <what>` when no runbook applies (then Runbook is `None`).
- Runbook and Risk: copy from the context table. Never invent a runbook.
- Rollback or recovery: how to undo it or recover if it makes things worse. If there is none write `None: say who must decide`.
- Addresses: hypothesis and fact ids from the triage (H1, F2).
## Not recommended
Actions you considered and rejected, and why (risk too high for the evidence, no runbook, prerequisite missing).
## Open questions for the on-call engineer
