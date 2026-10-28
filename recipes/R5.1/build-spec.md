# R5.1 Capture inquiries from web, email and phone notes into one lead record

Book chapter 5 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapter 13

Turns every trade inquiry into one CRM lead record within minutes, source attached.
It never replies, overwrites, merges or deletes.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/email.blueprint.json`](make/email.blueprint.json) and [`make/phone-note.blueprint.json`](make/phone-note.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-27 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- A CRM taking leads from a service account, searchable by email, phone and company.
- Forms by webhook or email, an inquiry mailbox and a phone-note form.
- A duplicate key per channel: submission, message or note ID (Chapter 2).
- An exception queue, checked daily by a named person.

## Build steps

1. Trigger on each form, inquiry email and phone note.
2. Check the duplicate key; if seen, log and stop.
3. For emails and notes, the AI returns name, company, email, phone and need, each text or empty, and a label, "trade inquiry" or "not an inquiry"; it gets no tool that writes.
4. Check with rules: name or company, one contact route and the need present; email well-formed; phone digits only; label one of the two.
   A "not an inquiry" from an unknown sender goes to the shared inbox; anything incomplete, or an AI error after one retry, to the exception queue.
5. Search the CRM by email, then phone, then company.
   One match: add an activity stamped with the source ID; none: create a stamped lead; several, or a company-name match alone: queue it for Ben.
6. Attach the source, set "new, unassigned", and log the run.

## AI steps

- Step 3 returns `name`, `company`, `email`, `phone`, `need` and `label`, for emails and phone notes only: [`prompts/extract-inquiry.md`](prompts/extract-inquiry.md).
  Web forms skip the AI step and go straight to the step 4 rules.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| CRM write fails | Write error, not retried | Ben checks the CRM, then releases or closes the key |
| AI omits a field or invents a label | Step 4 fails it | Queue checker completes it from the source |
| Wrong record matched | Salesperson reports it | Ben moves the activity |

## Variations

Smaller: send the form and mailbox to the CRM's capture address; no workflow.

## Source

*AI Workflows That Run the Business*, Chapter 5, recipe R5.1. Pattern diagram: Figure 5.1 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
