Task: ASSESS THE CURRENT ENVIRONMENT.

Review every source document listed below: architecture diagrams (images or PDFs), system inventories,
standards, policies, and constraints. If an opportunity brief or requirements register is listed, use it
to decide what matters and to link findings to requirement IDs (R-001...).

Rules:
- Extract only what the documents show or say; never invent. If something is not stated, write "Not stated".
- Cite the source file after every item, e.g. (inventory.md). For diagrams, describe only what is visible
  and write "unclear in diagram" for anything you cannot read.
- When two documents disagree (e.g. diagram vs inventory), do not pick a side: list it under Gaps.

Reply in markdown with exactly these sections:

## Documents reviewed (file, what it is; and which expected inputs were NOT supplied: diagrams, inventory, standards, network, security, data)
## Current systems (table: system | purpose | owner | technology/version | hosting | criticality | source)
## Interfaces and integrations (table: from | to | protocol/data | direction | frequency | auth | source)
## Data flows (table: from | to | data | volume | sensitivity | residency | source)
## Hosting and infrastructure (platforms, regions, networks, DR/backup)
## Identity and access (identity providers, SSO, directories, roles, MFA, privileged access)
## Standards and constraints (technology standards, security/compliance policies, change windows, procurement; each with its source)
## Known pain points (problem, who reports it, evidence, systems affected)
## Dependencies (what depends on what, and which requirement IDs touch each system)
## Current-state diagram
One Mermaid `flowchart LR` block of systems and interfaces. Draw only what the documents confirm;
draw anything uncertain with a dashed edge `-.->` and suffix its label with "?".
## Gaps (missing, outdated, or contradictory information, ordered by impact)
## Items requiring client confirmation (table: question | why it matters | who can answer | blocks requirement IDs)

Do not write solution design or code at this stage.
