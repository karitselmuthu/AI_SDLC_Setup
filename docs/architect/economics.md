Task: ESTIMATE AND EXPLAIN THE ECONOMICS (ROM).

Use the opportunity brief, requirements, current-state view, options, target architecture, enterprise-fit
assessment and delivery approach listed below, plus any commercial documents supplied (current spend, price
lists, quotes, rate cards, headcounts, contracts). Produce a rough-order-of-magnitude estimate for review.

Rules:
- This is a ROM, not a quote or a price. Say so.
- Every number carries exactly one label:
  Confirmed = stated in a supplied document, in date, unambiguous (cite file and section);
  Calculated = derived from Confirmed figures and shown with the arithmetic and its inputs;
  Estimate = your judgement, with its basis and assumptions;
  Not stated = no figure available.
- Never invent prices, rates, volumes or headcounts. If no rate card is supplied, give effort in person-days only
  and no currency amount for delivery.
- Do not convert between currencies unless a document gives the rate. Show each currency separately.
- A quote or price that is expired, indicative, or not a quote is NOT Confirmed. Say why.
- Ranges are Low / Likely / High, with High >= Likely >= Low, and every total must equal the sum of its parts
  (show the working). State the sensitivity: which assumptions move the total most.
- Savings are never counted in the totals until the evidence is Confirmed; list them separately with their status.
- Cite phase IDs (P0...), design elements (K/I), requirement IDs (R-), exceptions (E), standards (S) and source files.

Reply in markdown with exactly these sections:

## Scope and basis (option and phases estimated, ROM class and accuracy, currency policy, what is excluded)
## Confirmed figures (table: figure | value and currency | source | date | still valid? Yes / No / Unclear, with the reason)
## Assumptions (table: ID A1... | assumption | what it affects | sensitivity High/Med/Low)
## Effort estimate by phase (table with ONE ROW FOR EVERY phase ID P in the delivery approach: phase | main roles | Low / Likely / High person-days | basis (scope drivers used) | confidence)
## Effort by role (roll-up across phases: role | Low / Likely / High person-days)
## Delivery cost (apply the supplied rate card only: role | days Low/Likely/High | rate | cost Low/Likely/High. Show the arithmetic. If no rate card, say so and stop at effort)
## Licensing and subscription (per-seat or other drivers, the counts that are Confirmed vs Not stated, prices used and their status, existing licences that could be reused, contract notice periods and renewals)
## Cloud and service usage factors (the usage units that drive cost, the volumes Confirmed vs Not stated, and any price documented; no invented prices)
## Existing spend and dual running (current costs that continue during transition and when they stop)
## Potential savings (table: saving | basis | Confirmed / Estimate | timing | depends on | counted in totals? No)
## ROM summary (one-time and recurring, Low / Likely / High, one table per currency; effort-only items listed separately)
## Sensitivity and cost drivers (the few assumptions or drivers that swing the result, and by how much)
## Confidence (per section High / Med / Low with the reason, and overall)
## Exclusions (what the ROM does not cover)
## Inputs needed for a firmer estimate (table: input | why it matters | who supplies it | which estimate line it would narrow. When key inputs such as volumes, usage, scope or rates are missing, give ONLY a clearly labelled range or a cost-driver model, never a single figure, state every assumption used, and list the missing inputs here)
## Validation needs (table: item | who validates: vendor / delivery lead / client finance / other | what could change | needed by which decision point D or phase)
## Open questions

Do not present estimates as commitments. Do not write design or code.
