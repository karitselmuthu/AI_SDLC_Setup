STEP 4: Design scenarios and data. Write:
## Status
## Test cases
Table with exactly these columns: ID (TC1, TC2 ...) | AC | Kind (positive, negative, boundary, state, role, failure) | Preconditions | Steps | Expected | Data. Be proportionate (token cost matters): normally 3 to 6 cases per criterion, up to 10 for High risk; merge near-duplicates. Every AC has a positive case and at least one negative, boundary or failure case.
## Boundary inputs considered
One row each for: minimum, maximum, empty, malformed, duplicate, out-of-range. Give the TC ids that cover it, or "Not relevant: reason".
## Test data
Deterministic, synthetic data only (invented names, user@example.invalid addresses, fake keys); never real or sensitive values. If the change touches roles or permissions, include allowed and denied cases (also a direct access attempt); for an API, error handling, contract compatibility, authentication and consumers; for a migration, success, data preservation, deployment compatibility and recovery. High-risk acceptance criteria get at least three cases.
