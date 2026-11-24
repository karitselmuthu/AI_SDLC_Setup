STEP 1 - Receive the release request.
Read the release request and the other documents named below (pull request or change record, QA and review results, release window, target environment, rollback criteria). Write the release record.

Sections, in this order:
## Status
## Release
A table with exactly the columns `| Field | Value | Source |` and one row for each of these fields: Artifact, Version, Source commit, Build record, Checksum, Target environment, Promotion path, Release window, Change freeze, Release Manager, Rollback criteria, Dependencies, Linked change.
- Value: copy it exactly from the source documents. Artifact, Version, Source commit and Checksum must appear verbatim in them. Write "Not stated" if the documents do not give it.
- Source: the document name and line where you found it.
- Release window: write it as `YYYY-MM-DD HH:MM to YYYY-MM-DD HH:MM` (add UTC if the request says UTC).
- Promotion path: environments in order, for example `staging -> production`.
- Change freeze: dates as above, or "none" only if the request says there is none.
- Dependencies: one `name (ready)` or `name (not ready)` per item separated by `;`, or "none" only if stated.
## Approvals stated in the request
Who approved what according to the documents, quoted. This is what the documents claim, not what the system has verified.
## Not stated
Every field above that is "Not stated", and what is needed.
