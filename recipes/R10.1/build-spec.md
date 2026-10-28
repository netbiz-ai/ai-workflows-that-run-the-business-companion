# R10.1 Turn a sale into a complete work order, with restricted fields protected

Book chapter 10 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapters 17 and 22

Turns every sale with delivery or installation into a work order a dispatcher can schedule without phoning anyone.
It never schedules, assigns crews, changes prices or payments, or touches the restricted access-code field.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/late-tasks.blueprint.json`](make/late-tasks.blueprint.json) and [`make/task-cleared.blueprint.json`](make/task-cleared.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-27 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- Sales from Chapter 2's paid-order webhook, the register, and trade orders in the customer relationship management (CRM) system.
- Building, unit and floor fields; a product list flagging installation; Chapter 2's zone sheet and key log.
- A restricted access-code field on every sale source, readable by sales and dispatch only.
- A scheduling role that creates work orders.

## Build steps

Table 10.1 is the rule that steps 3, 4 and 6 enforce.

**Table 10.1: Work-Order Fields: Mandatory, Restricted, Source**

| Field | Needed to schedule? | Comes from | AI step |
|---|---|---|---|
| Customer name, phone and preferred channel | Yes | The sale | Not sent |
| Building, unit and floor | Yes | Address fields; the notes | Extracts from notes; rule checks |
| Stairs and lift | Yes | The notes | Extracts; rule checks |
| Parking and site rules | Yes; "none" counts | The notes | Extracts; rule checks |
| Preferred window | No | The notes | Extracts; rule checks |
| Delivery zone | Yes | The zone sheet, by rule | Not sent |
| Payment or trade terms | Yes | The sale; the CRM | Not sent |
| Product and installation flag | Yes | The sale; the product list | Not sent |
| Building access code, restricted to dispatch and the day's crew | No; the dispatcher adds it at release | The sale's restricted field, which sales and dispatch read | Never read; masked if typed in the notes |

Tom's masking list: "code", "gate", "keypad", "PIN", "key safe", plus each word added after a miss.

1. Trigger on a paid online order, store sale or accepted trade order with delivery, or a change to one.
2. Duplicate key per visit: source, order ID, visit type and number; logged and unchanged, stop; changed, update that work order from step 3.
3. Read only Table 10.1's fields.
4. Rule: mask any code (digits, letters, "*" or "#") within three words of a masking-list word, and any bare run of four or more digits, or digits with "*" or "#", not near a floor, unit or street word; flag every masked order "code in notes" for the salesperson.
5. AI, with no tools, returns Table 10.1's note fields from the masked notes, each with its source phrase: floor a number; stairs and lift yes, no or unknown; parking text or "none".
6. Rules: each value matches its phrase ("third" is floor 3; "no elevator" supports only "no"); mandatory fields filled; address in a zone; terms in place; installation flag matches the product.
7. Complete, with no code in notes: create or update the work order as "ready to schedule", with masked notes and key.
8. Otherwise, or on an AI error: create it as "missing details" and task the salesperson with the gaps, including any code to move.
9. A cleared task reruns from step 3; a task open two working days, or a delivery inside three, goes to Tom's team.
10. At release, the dispatcher copies any code from the sale's restricted field into the work order's; the scheduling system then controls who sees it.

## AI steps

- Step 5 returns Table 10.1's note fields (building, unit, floor, stairs, lift, parking, window), each with its source phrase: [`prompts/extract-notes.md`](prompts/extract-notes.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Scheduling system down | Write error (no automatic retry) | Owen checks the system, then releases or closes the key |
| Code step 4 misses | Crew or dispatcher report | Owen stops the AI step; Tom extends the masking list |

## Variations

Smaller: no AI; a required-field form at the register and trade desk.
Larger: AI reads site photos a person has checked for codes.
Different system: a service firm triggers from a booked call or a contract's due date.

## Source

*AI Workflows That Run the Business*, Chapter 10, recipe R10.1. Pattern diagram: Figure 10.1 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
