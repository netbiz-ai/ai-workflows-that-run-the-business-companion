# R7.4 Run the exception queue with reasons, owners and ageing

Book chapter 7 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapter 15

Gives every stopped invoice one place to wait, with a reason, owner, age and draft query, and raises anything too old to Aisha.
It never resolves an item, sends a query or promises payment.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-28 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/closed.blueprint.json`](make/closed.blueprint.json) and [`make/morning.blueprint.json`](make/morning.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-27 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- A SharePoint queue list, an aging limit Aisha sets, and an escalation owner.
- Banned query words, such as "paid".
- Reason codes with owners:

| Reason code | Raised by | Owner |
|---|---|---|
| Needs a person; unknown supplier | R7.1 | Aisha |
| No PO; no receipt | R7.2 | Tom; finance assistant for services |
| Outside tolerance; already invoiced; pairing rejected | R7.2 | Tom |
| Lookup error; reservation failed | R7.2 | Owen |
| Supplier on hold | R7.2 | The caller |

## Build steps

1. Trigger when R7.1, R7.2 or R7.3 adds an exception to the queue list.
2. Check the duplicate key, invoice ID plus reason code; a repeat adds a note.
3. Assign the reason code's owner; an unknown code goes to Aisha.
4. For mismatch and missing-document codes, the AI drafts a supplier query of at most 100 words, told: "Ask only for what this item names; promise nothing."
5. Rules check the draft for banned words and any number not in the item; failure drops the draft, not the item.
6. Post the item and any draft to the owner in Teams.
7. A closed item with a corrected record or released hold rematches; any other goes to the payment approver, note shown, or is rejected; nobody approves what they resolved, so Tom's resolutions above $10,000 go to Helen.
8. Each working morning, post overdue items to Aisha, oldest first.

## AI steps

- Step 4 returns a draft supplier query of at most 100 words: [`prompts/draft-query.md`](prompts/draft-query.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | Noticed by | What a person does |
|---|---|---|
| Owner absent | Item ages | Aisha reassigns it |
| Aging check stops | No morning list | Owen restarts it |

## Variations

Smaller: a shared list, no AI; owners draft queries.

## Source

*AI Workflows That Run the Business*, Chapter 7, recipe R7.4. Pattern diagram: Figure 7.4 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
