# TICKET-142: Add a --list option to the architect agent (made-up sample)

Status: Approved by Priya (product owner), 12 Nov.

## Description
Reviewers want to see which steps exist and which output file each one writes, without reading the code.

## Acceptance criteria
1. `python architect/agent.py --list` prints one line per step: step name, output file, and the roles that must approve it.
2. The command makes no model calls and exits with code 0.
3. Running it must be fast, and it should also work for the coder agent.
4. Existing step commands keep working unchanged.

## Notes
Keep the change small. Follow the repository conventions.
