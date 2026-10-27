# R12.3 Alert the owner when a measure crosses its threshold

Book chapter 12 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapters 11 and 12

When a fresh figure crosses its owner's line, tells that owner once, with the source link.
A **line** is the threshold the **measure owner** writes before seeing the figure: a value, a direction, and whether landing on it counts; the **data owner** answers for the export.
The workflow explains nothing, suggests no action, and never moves a line.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/friday.blueprint.json`](make/friday.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-26 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- R12.1's current table.
- A threshold list: measure, direction, line, measure owner, data owner, approver; every change system-stamped.
- A Teams chat or email address per owner, and an alert log owners can read.

## Build steps

1. Trigger when a version of the weekly table becomes current.
2. Find each measure's outcome: stale, past the line, or not (Table 12.2 lists those skipped).
3. Duplicate key: week, measure, line version and outcome; if logged, skip, so only a changed outcome alerts.
4. Stale: alert the data owner with the source and last good date.
5. Rule: compare the value or change with the line in its direction; optionally, alert only in a second week past it.
6. Alert the measure owner: value, line, change, cut-off and source link.
7. Log every check, including silent ones.
8. An alert not marked "seen" by Friday 4 p.m. becomes an open issue in the pre-read.
9. A line change takes effect from the next cut-off after its system-stamped approval.

Table 12.2 is reproduced in [`../R12.1/build-spec.md`](../R12.1/build-spec.md); R12.3 never checks a measure marked "fewer than 3".

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

Retried: each alert post, three times; then by email.

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Too many alerts; owners stop reading | Monthly count of unseen alerts | Owner resets the line with Tom |
| Owner has left | Post fails or goes unread | Tom reassigns the measure |

## Variations

Smaller: conditional formatting on the weekly sheet.
Larger: a mid-week check on overdue work orders, which doubles the runs.
Different system: any tool, if only the workflow writes the decision log.

## Source

*AI Workflows That Run the Business*, Chapter 12, recipe R12.3. Pattern diagram: Figure 12.3 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
