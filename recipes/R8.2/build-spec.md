# R8.2 Prepare and send monthly statements for trade accounts

Book chapter 8 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapter 15

Sends every trade account a monthly statement that matches the ledger to the cent, with disputed items marked.
It never sends a statement that does not reconcile, adds fees, or shows a disputed item as due.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/decision.blueprint.json`](make/decision.blueprint.json) and [`make/run-again.blueprint.json`](make/run-again.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-26 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- Two ledger exports at one month-end cut-off: balances, and open items (invoices and credit notes, not unapplied payments).
- A written rule that a payment after month-end shows next month.
- The dispute list, a statement template, and CRM contacts.

## Build steps

1. Trigger on the month's first working day, after both exports are saved.
2. Stop and alert Aisha if an export is missing or its cut-off wrong.
3. Compare each account's open-item total with its balance; any difference, even a cent, holds the account.
4. Mark each disputed item "in dispute, not due", outside the total; an account in credit shows nothing due.
5. Skip any account plus statement month already sent.
6. Build each statement: items, total due, how to pay, where to ask.
7. Send Aisha one approval: count, total due, each held account's difference, and five random statements.
8. On approval, send and log each statement; on rejection, nothing.
9. Aisha corrects each held account in the ledger and releases it to step 3.

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Export late | Step 2 stops | Finance saves it; the run restarts |
| Send fails mid-batch | Outlook error (no automatic retry) | Logged unsent; Owen restarts |
| Error found after sending | A customer query | Aisha corrects it; no resend |

## Variations

Smaller: statements only for accounts with an overdue item.
Larger: a PDF statement saved to the account record.
Different system: another ledger changes only the exports and step 2.

## Source

*AI Workflows That Run the Business*, Chapter 8, recipe R8.2. Pattern diagram: Figure 8.2 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
