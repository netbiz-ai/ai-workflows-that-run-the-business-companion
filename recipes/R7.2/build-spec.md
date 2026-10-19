# R7.2 Match the invoice to the purchase order and delivery receipt

Book chapter 7 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapters 15 and 18

Matches each ready invoice to its purchase order (PO) and delivery receipt, a three-way match, and sends it for approval only if every line is within tolerance.
It never pays or changes an order.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- A supplier-item map, kept by purchasing.
- A signed Table 7.1 and R7.3's check list.

## Build steps

Table 7.1: Tolerances That Pass, Changes That Always Stop

| Check | Passes to the approver when | Stops for R7.4 when |
|---|---|---|
| Supplier hold | Check logged; supplier not held | Held, for any bank-detail difference |
| Order and receipt | Both found | Either missing (rent, utilities, carriers) |
| Line pairing | Every goods line pairs to this order | A line pairs elsewhere or nowhere |
| Quantity | Within received, less other invoices' reservations | Over received, or already invoiced |
| Unit price | Within the price tolerance | Above it |
| Freight | On the order, or within the freight tolerance | Above it |
| Tax | Within rounding of tax on the lines | Any other difference |

1. Trigger when R7.1 saves a "ready" invoice.
2. Read R7.3's check from its SharePoint list; a held supplier raises an exception, and an unreadable list holds the invoice.
3. Look up the PO and receipts; with no PO, raise "no PO".
4. Pair lines by the supplier-item map; for the rest, the AI is told: "Return the ID of the one order line this invoice line describes, or none."
5. Rules confirm each ID is on this order and apply Table 7.1; a failed line raises an exception naming it.
6. Reserve each line's quantity once; if a write fails partway, release the reserved lines (or mark them for Owen) and raise "reservation failed".
7. Send the approval, AI-paired lines marked: to Aisha up to $10,000, Tom above, or Helen if Tom raised the order; nobody approves what they requested or resolved.
8. Log the approval; a rejection releases reservations.
9. Purchasing adds confirmed AI pairings to the map.

## AI steps

- Step 4 returns the ID of one order line, or `none`, for each invoice line the supplier-item map does not pair: [`prompts/pair-line.md`](prompts/pair-line.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | Noticed by | What a person does |
|---|---|---|
| Receipt not entered | No receipt | Stockroom enters it |
| Lookup error | Fails three retries | Owen checks the connection |
| Reservation fails partway | Write error | Owen clears marked lines; invoice rematches |
| Tolerance too loose | Monthly review | Aisha versions a tighter Table 7.1 |

## Variations

Smaller: with no receipts, a two-way match drops the quantity check.

## Source

*AI Workflows That Run the Business*, Chapter 7, recipe R7.2. Pattern diagram: Figure 7.2 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
