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
## Hosting and environments (cloud or hybrid: for every environment, what runs where and who operates it; the connectivity between environments; how identity works across them; what data moves between them, in which direction and how often; resilience and failover across the boundary; day-2 operations ownership; the cost drivers that cross environments such as egress, interconnect and dual running. If the design is one environment, say so in one line)
## Trust boundaries and sensitive data flows (every trust boundary as a numbered list T1... with what is on each side; table of sensitive data flows: flow | data and classification | crosses which boundary | protection in transit and at rest | who can access it | access-control mechanism; and the security review points: what a security reviewer must look at before build, and when. Never state that a control or the design is certified or compliant unless a supplied document evidences it)
## Data residency and regulatory decisions (table: each residency or regulatory requirement | the design decision it drives, citing K/I ids | where it is satisfied by design | what compliance validation is still unresolved and who must validate it. A requirement with unresolved validation is never reported as met)
## Identity and access (providers, SSO, customer vs staff login, roles, MFA, service identities, admin access)
## Security controls (table: control | what it protects or requirement it meets | where applied)
## Resilience (availability design against the stated target, failure modes and mitigation, backup, DR with Proposed RPO/RTO)
## Observability (logging, metrics, tracing, alerting, the SLIs that prove each non-functional requirement)
## Deployment model (environments, regions, hosting, CI/CD, release and migration waves, how the change freeze and lead times are handled)
## Requirement traceability (table with ONE ROW FOR EVERY requirement ID in the register: ID | requirement | class | design elements (K/I ids) | how it is met | status Met / Partly met / Not met / Unknown)
## Key design decisions (decision | alternatives considered | rationale | trade-off. Add ONE ROW FOR EVERY conflict X in the requirements: the design choice it affects, what this design assumes while the decision is pending, who must decide, and what changes if they decide the other way)
## Assumptions
## Risks
## Open questions and client confirmations (each tagged with the requirement IDs it blocks)

Do not write code.
