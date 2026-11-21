Task: DEFINE THE DELIVERY APPROACH.

Use the opportunity brief, requirements, current-state view, solution options, target architecture and
enterprise-fit assessment listed below. Propose how the recommended solution would be delivered.

Rules:
- Ground everything in the documents. Cite requirement IDs (R-001...), design elements (K1..., I1...),
  exceptions (E1...), standards (S1...) and source files. Never invent. If something is not known, write "Not stated".
- Do not invent dates, prices or headcounts. Express timing relative to a start point T0 (contract start; the
  actual date is Not stated). A duration is an "Estimate" and must state its basis and assumptions. The only
  durations the documents give are facts (e.g. a vendor security review of 6 to 8 weeks); use them as facts.
- Test the roadmap against the stated deadlines and constraints (go-live dates, change freezes, review lead times,
  contract notice periods). If no phasing can meet a deadline, say so plainly with the arithmetic.
- Anything not stated by the client that you propose (wave order, role split, responsibilities) is "Proposed".
- This is a high-level approach for review, not a detailed project plan, a contract, or a price.

Reply in markdown with exactly these sections:

## Scope and basis (the option and design assumed, what this approach covers and does not)
## Delivery principles (3 to 6, each derived from a stated constraint or risk)
## Phases (table: ID P0... | name | objectives | design elements in scope (K/I ids) | entry criteria | exit criteria | duration Estimate + basis | requirements delivered (R ids))
## Roadmap (a Mermaid flowchart of the phases, decision points as diamonds, constraints such as freezes marked; then a table: constraint or deadline | where it falls against the phases | feasible? Yes / No / Unknown, with the reason)
## Dependency map (a Mermaid diagram, then a table: dependency | type: client / vendor / internal / external | needed by phase | owner | risk if late)
## Migration and transition approach (waves and order (Proposed), cut-over, parallel running, reconciliation, rollback, decommissioning of legacy systems, and contract notice periods and renewals that constrain it)
## Prerequisites (table: ID Q1... | prerequisite | owner | needed before phase | status: Not started / In progress / Unknown)
## Client responsibilities (what the client must provide or do, with the phase; labelled as assumptions to confirm)
## Decision points (table: ID D1... | decision | options | who decides | needed by phase | what it unblocks)
## Likely delivery roles (role | responsibility | phases involved; no headcounts unless a document gives them)
## Responsibility assumptions (table: activity | bidder | client | vendor/third party; each row Proposed)
## Exceptions and fit items (table with ONE ROW FOR EVERY exception ID E in the fit assessment: ID | handled in phase, decision point or prerequisite | how)
## Delivery risks (table: risk | rating High/Med/Low | likelihood and impact | linked ids | mitigation | owner)
## Assumptions
## Open questions (each tagged with the phases or decisions it blocks)

Do not write detailed design, a work breakdown, or code.
