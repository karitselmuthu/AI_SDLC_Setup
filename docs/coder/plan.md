You are doing step 4 of the coding work: PLAN THE CHANGE. You may only read. Do not edit or create files, run commands, or write code. Your output is a bounded change plan that maps every acceptance criterion to code changes, which humans will approve before anything is edited.

Inputs: three approved earlier outputs (the ticket plan with its acceptance criteria AC1..., the repository inspection, and the stack profile) and the repository named below. Use them, and open the code you plan to change to confirm what you write about it.

Rules:
- Break the work into SMALL changes C1, C2... Each one is a single reviewable step that leaves the build and the existing tests passing, touches few files, and can be tested by itself. Rate each S (a few lines or one file) or M (a few files). Never write an L: split it. A plan needs no more than 12 changes. If the work needs more, plan the first coherent slice that fits and put the rest under Out of scope, saying a follow-up ticket is needed.
- Every change serves at least one acceptance criterion, and says which. A change that serves none is allowed only if it is enabling work (for example a refactor that a later change needs), says "Enabling" and names the change it enables. Do not add work the ticket does not ask for.
- Every acceptance criterion maps to at least one change and to the test that proves it. If one cannot be met, write "Not coverable" with the reason and the question that blocks it. Never drop one quietly.
- Put every file path in backticks. A path must exist in the repository, or be marked `new:` immediately before it. To say a file does not exist, write its name without backticks and say what you searched.
- Name the existing functions, classes and tests you will change or reuse, with file and line (`path/to/file.py:42`). Search for callers (Grep) before changing anything that others use, and list the callers you found.
- Be explicit about the contracts: function signatures, command-line options, API shapes, events and file formats that change, before and after, and who depends on them.
- Data models and migrations: say what changes in any schema, stored file or format, how existing data is migrated or backfilled, and how it is rolled back. Write "None" only if you searched for stored data and found none, and say what you searched.
- Configuration: every new or changed setting, environment variable, feature flag, default and CI change. Never put a secret in the plan.
- Backward compatibility: what existing behaviour, callers, tests, scripts or data could break, and how each is preserved. Write "No compatibility concerns found" only with what you searched.
- Do not run or claim to run anything. Say how each change will be verified.

Reply in markdown with exactly these sections:

## Status (one line: "Draft, pending review by the tech lead and the ticket owner". Then Readiness: Ready to implement, Ready with assumptions, or Blocked, and the reason)
## Scope and bounds (what this change includes, what it excludes, the number of changes, and why it fits the limit)
## Change set (table with ONE ROW FOR EVERY change C1...: ID | the small change | files (existing paths, or new: path) | what changes (functions, classes, with file and line) | AC ids it serves, or "Enabling" and the change it enables | size S or M | depends on | how it is verified)
## Acceptance criteria map (table with ONE ROW FOR EVERY acceptance criterion AC in the ticket plan: AC | the criterion | the changes C that deliver it, or "Not coverable" and why | the test that proves it | status: Covered / Partly covered / Not coverable)
## Affected files (table: path | existing or new | the change | callers or dependants found)
## Interfaces and contracts (what changes in signatures, options, APIs, events or formats: before, after, who depends on it. "None" with what you searched)
## Data models and migrations (schema or stored-data changes, migration, backfill, rollback. "None" with what you searched)
## Configuration and environment (new or changed settings, variables, flags, defaults, CI)
## Backward compatibility (what could break, for whom, and how it is preserved)
## Order and rollback (the order of the changes, and how each is backed out)
## Risks and assumptions (open questions from the earlier plan that still matter, and assumptions marked Assumption)
## Modules and dependent builds (only when the code lists several modules below the task: table with ONE ROW FOR EVERY module the code lists, '.' written as root: module | affected by this plan? | shared interfaces it exposes or consumes | dependent modules whose build and tests must be checked | evidence. Change only the affected modules. Write "Single module" otherwise)
## Out of scope (what you noticed but this plan does not do)
## Open questions (each tagged with the change C or criterion AC it blocks, and who can answer)
