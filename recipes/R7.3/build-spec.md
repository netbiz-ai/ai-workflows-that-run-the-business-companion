# R7.3 Stop and verify any change to a supplier's bank details

Book chapter 7 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapters 10 and 15

Holds payments to any supplier whose bank details differ from the record until one person phones the number on file and a second enters the change, neither a payment approver.
It never accepts a change from an email or invoice.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/callback.blueprint.json`](make/callback.blueprint.json) and [`make/export.blueprint.json`](make/export.blueprint.json) and [`make/message.blueprint.json`](make/message.blueprint.json) and [`make/pre-run.blueprint.json`](make/pre-run.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-26 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- A bank register only the flow writes, with call-back numbers sourced as below.
- A supplier export with bank details, saved to SharePoint by the caller before each payment run.
- Change-request phrases, such as "new bank".
- Two named non-approvers: a caller, and the finance assistant who enters changes.

## Build steps

1. Trigger on an R7.1 record, a supplier message with a change-request phrase, or a new export.
2. Normalize spaces, dashes and case, then compare with the register; a phrase match is a difference.
3. Log the check to the list R7.2 reads; if nothing differs, stop.
4. Set the supplier's hold flag.
5. Check the duplicate key, supplier ID plus new details; an open hold gets no second task.
6. Send the caller a task with the register's phone number, never the message's.
7. The caller logs the number dialed and the outcome.
8. Change confirmed: the finance assistant enters it, and the hold lifts when the next export shows it; no change: the assistant releases the hold.
9. Not confirmed: the hold stays; report suspected fraud.

A new supplier takes the same call-back, on a number from the contract, its official website or a previously verified document, never the invoice or a change email.
Changing the number on file is itself a change: a call-back on the old number, or a second person's check, comes before saving.
A phoned or texted request is a trigger, never a change.
Before each payment run, the caller and Aisha confirm the export check is logged, no bill is from a held supplier, and every bill has a logged approval; a missing check holds every supplier and alerts Helen.
Whoever releases the payment run must not have approved its bills.

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | Noticed by | What a person does |
|---|---|---|
| Flow off or failing | No check logged | Hold every supplier |
| Supplier unreachable | Task open a day | Caller retries |
| Call to another number | Logged number differs | Hold stays; caller rings the register's number |

## Variations

Smaller: weekly exports; an outside accountant as caller, the owner as second person.

## Source

*AI Workflows That Run the Business*, Chapter 7, recipe R7.3. Pattern diagram: Figure 7.3 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
