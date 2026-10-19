# R12.1 Pull the weekly figures from source systems into one dated table

Book chapter 12 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapter 12

Each week, computes every figure in your metric dictionary from its source by a written rule, into one dated table with source links and freshness stamps.
It never estimates a missing figure, carries a value forward, writes to a source, or comments on the numbers.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- Book 1's metric dictionary, each measure marked **period** (a total between two dates) or **status** (open at one moment).
- Six sources: helpdesk; online shop and point-of-sale, exported together; delivery scheduling; accounting; the task system; and Aisha's weekly HR form, a manual source.
- One SharePoint library per source, readable only by that system's users.
- A named person to save any export that cannot be scheduled, 5 to 7 p.m. Thursday.
- A control total per system source (its own report or a second export); for the HR form, Aisha's typed row count.
- A weekly table (a SharePoint list only the workflow writes and leadership reads) and, per status measure, a snapshot list only the report's approvers read.

## Build steps

The cut-off is a dated setting, Thursday 5 p.m. by default; a figure is **fresh** when its export was made after it and covers data to it.
Moving the cut-off, restating a week or changing a formula goes through Chapter 17's change control.

1. Trigger at Thursday 7:30 p.m. local time, after the save window; recheck it after each daylight-saving change.
2. Duplicate check: if every file and control total matches the current version, stop.
3. Rule, per source: a fresh, non-empty export, or its figures are "stale".
4. Rule: columns match the saved list, or "format changed".
5. Rule: totals match the control total, or "does not reconcile"; HR form figures are "manual".
6. Rule: each formula is the version Aisha approved, or the run stops and alerts Owen and Aisha.
7. Compute each fresh or manual measure and its change from last week.
8. Rule: counts of people below 3 print "fewer than 3"; confirm this with your data-protection adviser.
9. Write one row per measure: value, change, cut-off, source link, status, rule version; snapshot each status measure's counted rows, which its link opens with the reader's own access.
10. Any failed source: alert Owen and its data owner with the reason.
11. Mark the version "written"; the latest written version is **current**, starts R12.3 and feeds R12.2.

What the weekly table shows for each status (book Table 12.2):

| Status | When | What the table shows | What happens next |
|---|---|---|---|
| Fresh | After the cut-off; columns and totals match | Value, change, source link | R12.3 checks its line; R12.2 may describe it |
| Manual | HR form, or no control total | Value, change, "manual, not reconciled" | As for fresh |
| Stale | Export old, empty or missing | Blank, "stale", last good date | Owen, data owner alerted; R12.2 says "missing this week" |
| Format changed | A column renamed or missing | Blank, "format changed" | As for stale |
| Does not reconcile | Total differs from control total | Blank, "does not reconcile" | As for stale |
| Fewer than 3 | People below 3, this week or last | "Fewer than 3", change blank | R12.3 never checks the measure |

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

Retried: each file read, three times over 30 minutes; then the source is stale.
A failed write to the table is not retried: it is logged, and Owen checks the table before any rerun.

| Failure | How the workflow notices | What a person does |
|---|---|---|
| A scheduled export did not run | Freshness rule | Owen reruns the export, then the workflow |
| Formula edited, old version kept | Golden-set rerun after every change (Chapter 17) | Owen restores it, or Aisha approves a new version |

## Variations

Smaller: one spreadsheet with an import tab per source and the rules as formulas.
Larger: read each system's application programming interface (API), on a Premium license or Growth-band platform.
Different system: any file store, with one restricted folder per source.

## Source

*AI Workflows That Run the Business*, Chapter 12, recipe R12.1. Pattern diagram: Figure 12.1 in the book.
Northstar Home & Appliance is fictional; names in the lists and tables are its people.
