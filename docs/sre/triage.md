STEP 4 - Triage the incident.
Read the incident note, the approved service context, the service health record (with its evidence index) and the detected risks. Correlate symptoms with dependencies, recent changes, ownership and known failure patterns. Keep observed facts apart from possible causes.

Sections, in this order:
## Status
## Incident summary
Two or three lines: what is affected, since when, how bad, from the evidence.
## Timeline
Table `| Time (UTC) | Event | Evidence |`, oldest first. Every time and every evidence id must exist in the evidence.
## Affected components
Table `| Component | Effect | Evidence |` using the service and its dependencies from the context.
## Observed facts
Table `| ID | Fact | Evidence |` with ids F1, F2, .... Only what the evidence shows. No causes here: do not use "caused by", "due to", "because of" or "root cause".
## Hypotheses
Table `| ID | Hypothesis | Confidence | Supporting evidence | Would confirm or refute it |` with ids H1, H2, .... Confidence is High, Medium or Low. Order by confidence.
## Information still needed
Bullet list: what to look at next and who can provide it.
