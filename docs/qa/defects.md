STEP 9: Report defects. Read the execution, exploration and non-functional reports. Write:
## Status
## Failing checks
Table: X id from the execution report | Classification (product defect, test defect, environment, dependency) | Evidence. Every X id appears. "None" if there were no failures.
## Defects
Table: ID (DEF1 ...) | Title | Severity (Critical, High, Medium or Low) and one line of reasoning | Confidence (Confirmed = reproduced with evidence, Potential = a concern) | Steps to reproduce (short, repeatable) | Expected | Actual | Evidence | Environment | Affected scope | Status (Open). Include only real, evidenced defects; recommend a fix but never apply one.
## Re-test
Never delete an earlier defect: keep its original report and add the retest result (the failing test re-run plus the relevant regression checks) here; flaky checks are reported with their attempts, never retried until they pass; otherwise "No fix provided yet".
