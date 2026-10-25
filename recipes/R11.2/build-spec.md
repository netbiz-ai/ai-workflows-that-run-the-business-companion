# R11.2 Block expired quotes and out-of-policy orders before they are placed

Book chapter 11 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapter 18

Stops a request, with the reason, before any approver sees it, if its quote has expired or does not match, or its supplier or item is outside policy.
It never approves, places or changes an order, waives a rule, or adds a supplier.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/backstop.blueprint.json`](make/backstop.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-25 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- A SharePoint request list: requester, supplier, lines, amount, budget line, and a comparison row or waiver.
- A version column that rises on a requester's edit.
- The daily vendor-record export, with R7.3's bank-detail hold flag (Chapter 7).
- Tom's policy list: allowed categories per budget line, and who may grant a waiver.
- A daily PO export from the accounting platform.

## Build steps

A split order is one purchase broken up to stay under a limit.
A waiver is a named person's written reason to skip the quote rule, in an emergency or for a sole source; never the supplier or policy rules.

1. Trigger: a request saved as "ready", or a version change.
2. Duplicate key: request ID and version; if logged, stop.
3. Rule: total requests to one supplier and budget line within 14 days; crossing $500 or $10,000 is a "possible split".
4. Rule: supplier active, no hold; then a total of $500 or less is "no PO needed" and stops.
5. Rule: a checked comparison row, or a waiver from Tom's list that skips step 6, logged for Aisha.
6. Rules: the quote matches and is valid for five more working days, a margin sized to cover the approval window; freight is stated or "included".
7. Rule: category allowed for the budget line.
8. Rule: price over 30% off the last paid waits for Tom.
9. Pass: set "checked; to approval" with the total, which starts R11.3.
10. Block: set "blocked" with reason codes; tell the requester what to do.
11. Backstop: each morning, any PO over $500 with no approved request goes to Aisha.

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

Reads retry three times, then the request is "unchecked" and Owen is alerted; a failed write is never retried (as in R11.1).

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Export missing | Export date check fails | Owen restarts it; requests rerun |
| PO raised outside the workflow | Step 11's morning report | Aisha asks why; Tom decides |

## Variations

Smaller: the same rules as conditional formatting on the request sheet.
Different system: run steps 3 to 8 before a module's own approval chain.

## Source

*AI Workflows That Run the Business*, Chapter 11, recipe R11.2. Pattern diagram: Figure 11.2 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
