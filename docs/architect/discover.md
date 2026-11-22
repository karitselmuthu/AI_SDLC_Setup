Task: DISCOVER BUSINESS AND TECHNICAL NEEDS.

Read every source document listed below. If an opportunity brief is listed, use it as the starting point
and resolve or carry forward its open questions. Extract only what the documents say; never invent.

Classify each requirement from the document's own wording:
- Mandatory: "must", "shall", "required", legal/compliance, or a hard deadline.
- Preferred: "should", "desired", "would like", evaluation-scored extras.
- Optional: "may", "nice to have", "future", "phase 2".
- If the wording is silent, classify Preferred and append "(inferred)".
Where the documents conflict, do not pick a side: list both under Unresolved questions.

Reply in markdown with exactly these sections:

## Business capabilities (what the business must be able to do, one line each; give each an ID C1, C2...)
## Users (role, goals, volume if stated)
## Workflows (end-to-end steps per key user journey; mark steps that cross systems)
## Integrations (system, direction, protocol/data if stated, owner if stated)
## Data needs (entities, sources, volumes, residency/retention/privacy)
## Operational needs (availability, performance, security, support, monitoring, hosting, compliance)
## Requirements register
A table, one row per requirement, ordered Mandatory first then Preferred then Optional:
| ID | Requirement | Type (business/technical) | Class | Capability | Source (file + quote or section) | Acceptance measure |
- ID format R-001, R-002...
- Acceptance measure: a testable statement. Use the document's own number when given.
  If none is given, write "Proposed: ..." so it is clearly yours to confirm, never presented as the client's.
## Interpretations (for every business problem, scope item or term the sources support more than one reading of: table ID Q1... | the statement and source | reading A | reading B (and more) | what each reading changes | the targeted discovery question, who should answer | which reading you assumed for now, marked Assumption. Never silently choose one. Write "None found" only if every need is unambiguous)
## Conflicts (every pair of requirements, constraints, dates or sources that cannot all be true: table ID X1... | the conflicting statements with sources | requirement IDs involved | design choices likely affected (for example hosting, identity, migration, availability design) | the decision needed | who decides: client or account team | what you assumed until it is decided, marked Assumption. Show the conflict; never resolve it yourself)
## Unresolved questions (one per line, each tagged with the requirement IDs it blocks, ordered by impact)
## Traceability gaps (requirements with no source, no acceptance measure, or a conflict)

Do not write solution design or code at this stage.
