# R12.2 Draft the weekly briefing narrative with a link behind every figure

Book chapter 12 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapter 12

Turns the finished table into a short narrative of what changed, using only its numbers, each with its source link.
The AI computes nothing, gives no cause an owner did not write, recommends no decision, and never sees a source export.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- R12.1's current table.
- An owner commentary field per measure, closed at Friday 2 p.m.; untrusted input to the AI.
- The prompt and the banned-cause list, each versioned.
- A must-mention list: every R12.3 crossing and every change above a stated size.

## Build steps

1. Trigger at Friday 2 p.m., or when the table is first written, up to 3:30 p.m.
2. Duplicate key: week and table version; if a draft exists, stop.
3. Rule: hold back commentary naming anyone on the customer or staff lists, for Tom to read.
4. Build the input from the table and remaining commentary only.
5. AI step, with no tools: "Write one sentence for each must-mention measure, using only numbers in the table, copied exactly, and tag each number."
6. Schema: sentences, each with its text and numbers, each number tagged with measure and field (value or change); anything else fails.
7. Number rule: every number, with word-numbers such as "twelve" converted, equals its tagged field, and "rose" or "fell" matches the change's sign.
8. Cause rule: a banned-cause word, such as "because", fails unless the sentence names the owner and quotes their commentary word for word.
9. Rules: a measure neither fresh nor manual appears only as "missing this week"; every must-mention measure has a sentence.
10. Pass: the workflow, not the AI, inserts each source link.
11. Fail, or an AI error: publish table and commentary with "no narrative this week".
12. Tom approves or deletes sentences, Aisha those on his measures, and each deletion is logged.
13. Not verified by 4 p.m.: Aisha verifies by 4:45 p.m., or step 11 runs, marked "not verified".
14. A newer table version before 4 p.m. is drafted again; after 4 p.m., no narrative.

A cause without a banned word ("as customers rescheduled, overdue jobs rose") passes; catching it is Tom's job.

## AI steps

- Step 5 returns `sentences`, each with its `text` and `numbers`, each number tagged with `measure` and `field`: [`prompts/draft-narrative.md`](prompts/draft-narrative.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

Retried: the AI call, twice; then table only.

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Model update starts rounding | Check fails two weeks running | Owen reruns the golden set |
| A word-number slips past the rule | Tom spots it | Owen adds it to the rule and a golden case |

## Variations

Smaller: paste the table into an approved AI workspace; match every number by hand.
Larger: one draft per department, verified by its measure owners.
Different system: run the number and cause rules on any summary your reporting tool writes.

## Source

*AI Workflows That Run the Business*, Chapter 12, recipe R12.2. Pattern diagram: Figure 12.2 in the book.
Northstar Home & Appliance is fictional; names in the lists and tables are its people.
