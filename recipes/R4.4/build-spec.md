# R4.4 Summarize a long thread for a handoff or escalation

Book chapter 4 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapter 22

Puts a four-field summary atop a long thread (request, promises made, open items, next step), each linked to its message.
It never replaces the thread, replies or copies restricted data.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-27 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- Read access to threads, with message links.
- A restricted-field list, starting with building access codes, which only dispatch and crews read.

## Build steps

1. Trigger on an R4.2 escalation.
2. Check the duplicate key, the escalation's ID; if summarized, stop.
3. Fetch the thread with message links; mask restricted fields before the AI sees it.
4. Ask the AI for the four fields, each linked to its message.
5. Check that all four are present, every link points into the thread, and no restricted data appears, with a broader detector than step 3 (digits near code, gate or keypad).
6. Post a passing summary as an internal note; otherwise, post only the pointer note.

## AI steps

- Step 4 returns `request`, `promises_made`, `open_items` and `next_step`, each with its message links: [`prompts/summarize-thread.md`](prompts/summarize-thread.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Summary invents a promise | Receiver finds no source message | Nadia adds a golden case |
| AI step or note write fails | AI error after one retry; write error, no retry | Receiver reads the thread |
| Restricted data in a note | Owen's weekly sweep | Owen deletes it; reviews the mask |

## Variations

Smaller: summarize on request only; runs and cost follow requests.
Larger: also trigger on reassignment, which joins the duplicate key.
Different system: in a shared mailbox, send it to an internal address.

## Source

*AI Workflows That Run the Business*, Chapter 4, recipe R4.4. Pattern diagram: Figure 4.4 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
