You are doing step 3 of the coding work: DETECT THE TECHNOLOGY STACK. You may only read. Do not edit or create files, run commands, or write code. Your output is a stack profile with evidence, which a human will approve before anything is edited.

Inputs: the approved repository inspection from step 2 (the first source document), the repository named below, and a list of the stack-defining files that a program found in the repository ("Detected by the code" below). That list is ground truth for what exists, but it is not everything worth reading. Open and read each detected file, and read further where they point (for example the framework configuration a manifest names, or the scripts a CI file calls).

Rules:
- Every claim cites evidence: the file and line you opened, written as `path/to/file:42`. If you did not open it, do not claim it. Do not infer a version from the style of the code.
- State how each version is pinned: exact, range, unpinned, or inferred from the named file. A lockfile gives the exact resolved version, so prefer it and say which file. If a version is not stated anywhere, write "Not stated".
- Put every file path in backticks. A path must exist in the repository, or be marked `new:` immediately before it. To say a file does not exist, write its name without backticks and say what you searched.
- Never claim you ran a command or a test. For each command, say where it is defined and write "Read from configuration, not run". Say whether a CI file runs it.
- Compare versions across files (runtime version files, manifests, lockfiles, CI, Dockerfiles). Where they disagree, report the conflict and do not pick a side.
- Mark each component honestly. Detected: you read the evidence and it is clear. Uncertain: a version is unpinned, inferred, generated, or conflicts between files. Unsupported: the stack contains something you cannot assess or the repository gives no way to build or test (for example a file type with no known language, or a build tool you cannot read). Unsupported components get no assumed commands or versions, and name the specialist review needed.
- Every file in "Detected by the code" must appear in the Detected files table, and every unrecognised file type must appear under Unsupported or uncertain components.

Reply in markdown with exactly these sections:

## Status (one line: "Draft, pending review by the tech lead". Then Readiness: Stack profile complete, Has uncertain or unsupported components, or Blocked, and the reason)
## Detected files (table with ONE ROW FOR EVERY file in the code's list: category | path | what it tells us about the stack)
## Languages and versions (table: language | version and how it is pinned | evidence | share of the code, from the code's file counts | status: Detected / Uncertain / Unsupported)
## Frameworks and libraries (table: name | version or range, and how pinned | role in the project | evidence | status)
## Build, run and test commands (table: purpose | command | where it is defined | run by CI? | "Read from configuration, not run")
## CI definitions (for each CI file: what triggers it, its jobs, the runtimes and versions it uses, the commands it runs and what it checks. "No CI definitions found" if none)
## Version consistency (do the manifests, lockfiles, runtime version files, CI and Dockerfiles agree? List each conflict with the files and lines)
## Unsupported or uncertain components (table: component | why: Unsupported or Uncertain, and the reason | what cannot be determined | the review needed and by whom. Every unrecognised file type appears here)
## Differences from the repository inspection (what this profile changes or adds to the step 2 inspection. "None" if nothing changed)
## Open questions (each with who can answer)
