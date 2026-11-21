Task: PREPARE THE CLIENT DISCUSSION.

Prepare meeting-ready materials for a discussion with the prospect, using the opportunity brief, requirements,
current-state view, options, target architecture, enterprise-fit assessment, delivery approach, ROM estimate and
proposal package listed below (plus any other documents supplied, e.g. an agenda or attendee list).

Rules:
- Ground everything in the documents. Cite IDs (R-, D-, E-, K-, I-, P-) and source files. Never invent; write "Not stated"
  when unknown, including attendees, dates and the meeting length (propose them and label "Proposed").
- Label every section [CLIENT-SHAREABLE] or [INTERNAL]. Client-shareable material must not contain the bidder's
  internal rate card, cost, margin, ROM figures, pricing strategy, how the client is expected to score, or internal
  risk commentary. Pending references and unevidenced claims are [INTERNAL] items to resolve, never client claims.
- Any claim about the bidder is evidenced (name the source) or marked "[CONFIRM: what and who]".
- Responses to objections must be honest: use the evidence we have; where we have none, say so, acknowledge the
  concern, and commit to a follow-up instead of bluffing. Never promise what the analysis says cannot be met.
- Discovery questions must be specific, answerable in the room, and tied to what they unblock.
- Keep it usable in a live meeting: short talk tracks, plain language, one message per slide.

Reply in markdown with exactly these sections:

## Meeting objectives and attendees [INTERNAL] (objectives, desired outcomes, attendees and roles from the documents or "Not stated", proposed length)
## Presentation flow [CLIENT-SHAREABLE] (agenda, then a table: slide | title | key message | source artifact | presenter role | Proposed minutes)
## Key messages [INTERNAL] (3 to 5, each evidenced or [CONFIRM])
## Discovery questions [CLIENT-SHAREABLE] (table: ID Q1... | question | why we ask | what it unblocks (R, D, E ids) | who we expect to answer | priority High/Med/Low; ordered by impact)
## Decisions we need [INTERNAL] (table with ONE ROW FOR EVERY decision point D in the delivery approach: D | decision | options | our recommendation | who decides | what we will propose if it stays undecided)
## Architecture walkthrough [CLIENT-SHAREABLE] (a talk track of 5 to 7 steps, with Mermaid diagrams simplified from the target architecture; what to show and what to leave out)
## Option comparison [CLIENT-SHAREABLE] (balanced table of the options on fit, risk, cost drivers (no figures), complexity, time to deliver; the recommendation and its conditions)
## Anticipated objections [INTERNAL] (table: objection | likelihood | underlying concern | suggested response | evidence or [CONFIRM] | follow-up if unresolved)
## Sensitive topics and things not to say [INTERNAL]
## Capture plan [INTERNAL] (who scribes; the fields to record for every decision: what, who, source, explicit vs implied; how follow-ups are logged)
## Pre-meeting checklist [INTERNAL] (items to resolve first, especially every [CONFIRM], and materials to bring)

Do not write detailed design or code.
