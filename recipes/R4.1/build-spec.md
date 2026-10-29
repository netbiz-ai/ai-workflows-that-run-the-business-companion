# R4.1 Classify and route every incoming message to the right queue

Book chapter 4 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapters 14 and 22

Lands every message in the right queue within minutes, so nobody searches the whole inbox.
It never replies, closes, lowers a priority or deletes.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-28 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-27 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- A helpdesk that triggers on each new message; a service account that sets category, queue and tags.
- A category list, each with an owner and three examples; the languages covered.
- An exception queue with a named triage lead.
- A duplicate key: ticket ID plus message ID (Chapter 2).

## Build steps

1. Trigger on each new message, instantly if offered.
2. Check the duplicate key in the key log; if seen, stop.
3. A sender rule sends auto-replies and bulk mail to a low-priority queue; go to step 6.
4. Ask the AI to return only `category` (a listed name or `none`), `confidence` (`high`, `medium` or `low`) and `language` (a language code).
5. Use the category only if it matches a listed name exactly, `confidence` is `high`, and `language` is covered.
   Anything else, including an AI error after one retry, goes to the exception queue.
   So does a failed write, marked failed in the key log, never retried.
6. Record the result in the decision log.

## AI steps

- Step 4 returns `category`, `confidence` and `language`: [`prompts/classify.md`](prompts/classify.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Write fails | Write error (no automatic retry) | Owen checks the ticket; triage lead sorts it |
| Category renamed | Every run fails the list check | Owen updates the list; Tom approves |

## Variations

Smaller: sender and form-field rules alone; without AI, a standard-connector flow needs no Premium license.
Larger: add a language, with its own keywords and golden cases.
Different system: a shared mailbox with a folder per queue, any built-in classifier behind the same rule.

## Source

*AI Workflows That Run the Business*, Chapter 4, recipe R4.1. Pattern diagram: Figure 4.1 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
