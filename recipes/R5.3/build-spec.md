# R5.3 Draft a quote from the current price table only

Book chapter 5 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapter 13

Drafts a quote in minutes, every number from the current price list.
It never sets a price or sends.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/expiry-warning.blueprint.json`](make/expiry-warning.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-27 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- Aisha's price list in the CRM: code, unit price, version, valid-until date.
- Opportunity lines as product codes, quantities and the salesperson's discount.
- A dated, owned library of approved terms and scope paragraphs, none priced; for AI-drafting disclosure, see R4.3.

## Build steps

1. Trigger when an opportunity is marked "ready to quote".
2. Stop if the duplicate key, opportunity ID plus revision, was seen.
3. If the price list or terms library has expired, stop and tell Ben and Aisha.
4. Price each line by fixed rule: unit price times quantity, less discount, rounded once; the total sums rounded lines.
   Quotes are tax-exclusive and single-currency; the CRM's quote tool adds tax; an off-list code stays unpriced, flagged for Ben.
5. The AI writes cover note and scope, with a placeholder such as `{{line_3_total}}` for every number.
   Send it only customer, need and product names, never a price, amount or discount.
6. Fill every placeholder from step 4.
7. Check with rules: every placeholder filled, except an off-list line's, and the lines add up to the total.
   Any number no placeholder supplied was invented and fails the draft.
8. Add the approved terms after the check, since their numbers would fail it, and save the draft, stamped with the price list version, for R5.4; on a fail or AI error, save nothing and flag the opportunity.

## AI steps

- Step 5 returns `cover_note` and `scope`, with a placeholder for every number: [`prompts/draft-quote-text.md`](prompts/draft-quote-text.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Price list expiring | Warning a week ahead | Aisha publishes a new one |
| CRM read fails | Error after three read retries | Salesperson quotes by hand |
| Off-list code | Line unpriced, flagged | Ben prices it before R5.4 routes it |

## Variations

Smaller: price by rule; the salesperson writes every word.
Different system: a CRM quote tool can do steps 3 and 4; keep step 7 and R5.4.

## Source

*AI Workflows That Run the Business*, Chapter 5, recipe R5.3. Pattern diagram: Figure 5.3 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
