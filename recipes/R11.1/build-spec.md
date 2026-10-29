# R11.1 Collect supplier quotes into one normalized comparison

Book chapter 11 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapter 18

Turns every emailed quote into rows on one comparison sheet where prices, units, freight and expiry dates line up.
It never ranks quotes, chooses or contacts a supplier, creates a vendor or raises an order.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-28 ([report](n8n/test-report.md)) |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- A shared quotes mailbox, readable by a service account.
- Northstar's response table from Book 1, sent with every request for quotation.
- The comparison sheet, editable only by the workflow and the stockroom lead.
- A daily vendor-record export, with last price paid.
- Tom's unit table and sheet basis: one currency, no tax, and the delivery terms that include freight, such as "delivered".

## Build steps

"Normalized" means every row answers the same questions in the same units.
Landed cost is the price per base unit once freight and other charges are added.

1. Trigger: a new quotes-mailbox message; no attachment, or only a scan, goes to the exception queue.
2. Duplicate key: the attachment's fingerprint; if logged, stop (Chapter 2).
3. Rule: a response-table attachment is read cell by cell and skips step 4.
4. AI step, no tools: return supplier, quote number, quote date, valid-until date, currency, freight (amount, "included" or blank) and subtotal, and per line description, quantity, unit, unit price and line total, each with its page; blank, never guessed.
5. Rules: schema matches; lines add to the subtotal to the cent; every value is on its page.
6. Rule: freight is "included" only if the page carries one of Tom's delivery terms.
7. Rule: match the supplier to the vendor record, or flag "unknown supplier".
8. Rules: convert to base units; flag another currency; compute landed cost, or "cannot compute" without freight.
9. Rules: flag a quote inside R11.2's margin or over 30% off the last price paid; a revision supersedes the older row.
10. Write one row per line, with flags, page and message link.
11. A failed step 5 check or an AI error sends the quote to the exception queue.
12. Each shift, the stockroom lead checks every AI-filled row against its page and marks it "checked".

## AI steps

- Step 4 returns the quote header fields and its lines, each value with its page: [`prompts/extract-quote.md`](prompts/extract-quote.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

Reads and AI calls retry three times, then go to the exception queue.
A failed write is never retried: the key log marks it failed, and Owen checks the sheet before redoing it.

| Failure | How the workflow notices | What a person does |
|---|---|---|
| A misread value passes every rule | The page check | Lead corrects it; Owen adds a golden case |
| Supplier changes its quote layout | Queue fills from one supplier | Owen reruns the golden set |

## Variations

Smaller, below about ten quoted purchases a month: type quotes; flags as sheet formulas.
Larger, several stockrooms: one sheet per site, each with a named checker.
Different system: a module that reads quotes still needs steps 5 to 9.

## Source

*AI Workflows That Run the Business*, Chapter 11, recipe R11.1. Pattern diagram: Figure 11.1 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
