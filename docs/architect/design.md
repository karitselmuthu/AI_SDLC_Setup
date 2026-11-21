Task: DESIGN THE RECOMMENDED SOLUTION.

Use the opportunity brief, requirements register, current-state view and solution options listed below.
Design the target architecture for the RECOMMENDED option (state which one, and any condition attached to it).

Rules:
- Ground everything in the documents. Cite requirement IDs (R-001...), capabilities (C1...), option letters and source files.
  Never invent. If something is not known, write "Not stated" and list it under Assumptions or Open questions.
- Do not name a specific vendor or product unless a document does. Otherwise write "Product: to be selected"
  and give the selection criteria taken from the requirements.
- Values the documents do not give (RPO/RTO, retention, capacity) must be marked "Proposed", never presented as the client's.
- Respect the client's constraints from the current-state view (identity standard, hosting rules, residency,
  change freeze, security review lead times).
- If the design cannot meet a requirement, say so plainly; do not hide it.
- Diagrams are Mermaid. Draw only what is confirmed with solid edges; draw uncertain items with dashed edges `-.->` and a "?" label.

Reply in markdown with exactly these sections:

## Scope and basis (which option is designed, why, conditions, and what this design does not cover)
## Architecture overview (a short summary, then a Mermaid context diagram: users, the solution, surrounding systems)
## Components (table: ID K1... | name | responsibility | product/technology | hosting | build / buy / reuse | requirements served)
## Boundaries (system boundaries, trust zones and network zones, what is inside vs outside the solution, who owns each side; Mermaid diagram)
## Interfaces (table: ID I1... | from | to | protocol | data | auth | sync/async | requirements served)
## Data flows (Mermaid diagram of the main flows including migration, plus a table: flow | data | classification | residency | retention (Proposed if not stated))
## Identity and access (providers, SSO, customer vs staff login, roles, MFA, service identities, admin access)
## Security controls (table: control | what it protects or requirement it meets | where applied)
## Resilience (availability design against the stated target, failure modes and mitigation, backup, DR with Proposed RPO/RTO)
## Observability (logging, metrics, tracing, alerting, the SLIs that prove each non-functional requirement)
## Deployment model (environments, regions, hosting, CI/CD, release and migration waves, how the change freeze and lead times are handled)
## Requirement traceability (table with ONE ROW FOR EVERY requirement ID in the register: ID | requirement | class | design elements (K/I ids) | how it is met | status Met / Partly met / Not met / Unknown)
## Key design decisions (decision | alternatives considered | rationale | trade-off)
## Assumptions
## Risks
## Open questions and client confirmations (each tagged with the requirement IDs it blocks)

Do not write code.
