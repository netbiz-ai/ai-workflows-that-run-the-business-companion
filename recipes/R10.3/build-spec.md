# R10.3 Prepare tomorrow's dispatch briefing, read-only

Book chapter 10 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapters 17 and 24

Each afternoon, gives the lead dispatcher one briefing on tomorrow's jobs, crews, overdue work, open messages, stock and site risks.
It never changes the schedule, messages anyone, retries a source in a loop, or includes a restricted field.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-28 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/second-start.blueprint.json`](make/second-start.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-27 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- Read-only credentials for work orders (no restricted fields), crew schedule, helpdesk messages, overdue work and stock exceptions.
- A budget table: date, starts today, full briefing posted, AI spend this month.
- A dispatch channel and a raw job-list template.

## Build steps

1. Trigger each working afternoon at a time Tom sets, with a second start later.
2. Rule: no full briefing posted today, starts under two, AI spend under its caps; otherwise stop, alerting Owen if capped.
3. Add one to today's starts.
4. Read each source once, with a time limit and no retry; a failed source is listed "not available".
5. Copy job IDs, times, crews and addresses into the briefing table by rule; the AI never writes them.
6. Rule: mask codes in notes and messages with R10.1's step 4 rule.
7. AI fills, with no tools, two fixed fields: a note of up to 25 words per job ID, headed "unchecked", and a risks list.
8. Rules: every source reached, the job list not empty; every job ID once, none new; no table time or address, and nothing maskable, in the AI text.
9. Pass: post and mark "full briefing posted"; fail: post the raw list from what was reached, headed "partial", for the second start to retry.
10. Record AI spend in the budget table.
11. The lead dispatcher makes any change in the scheduling system.

## AI steps

- Step 7 returns `notes` (one note of up to 25 words per job ID) and `risks` (the risks list): [`prompts/briefing-notes.md`](prompts/briefing-notes.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Cap reached early | Step 2 alert | Owen finds the cause before raising any cap |
| Source credential expires | "Not available" on both starts | Owen renews it |

## Variations

Smaller: no AI; post the raw job list with overdue and stock flags.
Larger: one briefing and budget per store, and a Friday briefing for weekend jobs.

## Source

*AI Workflows That Run the Business*, Chapter 10, recipe R10.3. Pattern diagram: Figure 10.3 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
