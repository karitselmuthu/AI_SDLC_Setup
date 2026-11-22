Task: CHECK ENTERPRISE FIT.

Compare the target architecture with the client's standards and constraints. Use the target architecture, the
earlier briefs listed below, and every client standards document supplied (approved platforms, security
policies, residency and regulatory rules, accessibility needs, contracts and existing services).

Rules:
- Ground everything in the documents. Cite sources (file, section) and design element IDs (K1..., I1...) and
  requirement IDs (R-001...). Never invent a standard, policy or contract term. If something is not stated, write "Not stated".
- Separate what the client STATED from what is merely COMMONLY EXPECTED. Label the latter
  "Commonly expected, not stated by client" and never treat it as a client requirement.
- Do not give legal conclusions. For regulatory and privacy matters, record the question for a qualified
  compliance/legal reviewer; say what the documents show and what they do not.
- A verdict is Compliant, Partly compliant, Non-compliant, or Unknown. Use Unknown when the evidence is missing; never
  round up to Compliant.
- Note which expected inputs were NOT supplied (e.g. approved platform list, security policy, accessibility standard,
  contract terms) so reviewers know what the assessment could not cover.

Reply in markdown with exactly these sections:

## Scope and basis (design version assessed, documents used, expected inputs NOT supplied)
## Standards and constraints inventory (table: ID S1... | standard or constraint | category: approved platform / security / data residency / regulatory / accessibility / contract-service / procurement-change | mandatory or advisory | source)
## Fit assessment (table with ONE ROW FOR EVERY design component K and interface I in the target architecture: element | applicable standards (S ids) | verdict | evidence | note)
## Approved platforms and technology (check each component's technology against the approved catalog and standards. Anything not covered is Unsupported: say what cannot be assessed and why, and name the specialist review required. A client-mandated technology is a constraint: assess its fit and risks and list an exception if it breaks a standard, and never replace it silently)
## Security policy
## Data residency
## Regulatory and privacy (questions for compliance/legal, not conclusions)
## Accessibility
## Existing contracts and services (reuse, overlap, licence or contract limits, notice periods)
## Exceptions (table: ID E1... | standard not met | design element | why needed | proposed mitigation | who must approve)
## Compliance questions (each tagged with the S, K, I and R ids it affects and who can answer)
## Risks (risk | rating High/Med/Low | linked ids | suggested owner)
## Items for human review (the decisions people must make, who decides, and what is blocked until they do)

Do not redesign the solution here; record where it does not fit and what must change or be approved.
