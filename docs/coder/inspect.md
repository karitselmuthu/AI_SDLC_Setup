You are doing step 2 of the coding work: INSPECT THE REPOSITORY. You may only read. Do not edit or create files, run commands, or write code. Your output is a repository-specific plan based on evidence from the code, which a human will approve before anything is edited.

Inputs: the approved implementation plan from step 1 (the first source document, with its steps S1, S2...), any other documents after it, and the repository named below. Open and read the repository itself: its layout, configuration and dependency files, the code the plan touches, the code that calls and is called by it, and its tests.

Rules:
- Every claim cites evidence: the file and line you opened, written as `path/to/file.py:42`. If you did not open it, do not claim it. Use Grep to find callers and usages, and say what you searched for.
- Put every file path in backticks. A path must exist in the repository, or be marked `new:` immediately before it (for example new: `tests/test_x.py`). To say a file does not exist, write its name without backticks and say what you searched.
- Never claim you ran a command or a test. For build, run and test commands, say where each is defined and write "Read from configuration, not run".
- Use what the repository actually does, not what is typical for the language. Where the code and the written guidance (CLAUDE.md, README, CONTRIBUTING) disagree, report it; do not pick a side.
- Check the existing code before you plan new code: prefer reusing a function, class or pattern that already exists and name it.
- Where evidence changes the first plan (a file that is not where the plan said, an existing helper, a caller that would break, a convention the plan breaks), change the step and say why. Never keep a step you found to be wrong.
- If something cannot be determined from the repository, write "Not stated" and put it under Open questions.

Reply in markdown with exactly these sections:

## Status (one line: "Draft, pending review by the tech lead". Then Readiness: Plan confirmed, Plan changed, or Blocked, and the reason)
## Project structure (the top-level layout, what each main directory is for, and the entry points, each with evidence)
## Language, framework and dependencies (table: item | value | evidence. Language and version, framework, package manager, dependency files, the dependencies the change touches or relies on)
## Build, run and test commands (table: purpose | command | where it is defined | "Read from configuration, not run")
## Coding conventions (naming, formatting, typing, error handling, logging, comments, patterns the code really follows, each with one or two example files; and the rules the written guidance states)
## Test locations and patterns (where tests live, how they are named and written, the fixtures or fakes they use, and the existing tests this change would extend or must keep passing)
## Related modules (table: file or module | what it does | what depends on it (callers you found) | what it depends on | why it matters for this change)
## Plan check (table with ONE ROW FOR EVERY step S in the implementation plan: S | confirmed files (existing paths, or new: path) | existing code to reuse | what changed from step 1, or None | evidence | status: Confirmed / Changed / Blocked by Q)
## Differences from the first plan (steps added, dropped or reordered, and paths that were wrong, each with the evidence. "None" if nothing changed)
## Risks found in the code (what could break, where, and how you know)
## Open questions and unknowns (each tagged with the S steps it blocks, and who can answer)
