# R13.2 Flag stale documents to their owners and pull expired ones from answers

Book chapter 13 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapter 19

Weekly, reminds each owner before their source's review date and withdraws it at its expiry date, 30 days later in Book 1.
It never edits a document or restores one without its owner.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- The register (Table 13.1) as a SharePoint list.
- One home per document, linked from policy emails.
- An archive no bought assistant can open, and an owner form.

Table 13.1 is printed in [`../R13.1/build-spec.md`](../R13.1/build-spec.md); each row also holds the fields R13.2 maintains: delegate, dates, status and version.

## Build steps

1. Trigger weekly, early on the first working day.
2. Read rows due within 14 days, past review or expiry, or lacking an owner or date.
3. Duplicate key: source, week and action.
4. Rule: no owner or review date means withdrawn, with Owen alerted.
5. Rule: a departed owner goes to Owen to reassign; one on vacation, to the delegate.
6. Due or past review: remind the owner, with the pull date.
7. Past expiry: set "withdrawn", archive the file away from any bought assistant's search, and tell the owner and Owen.
8. The owner renews, replaces or retires it.
9. On publishing a major version, rebuild its passages.
10. Compare stored audience with sharing, and register version with index; mismatches go to Owen.
11. Log every check.

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Owner ignores reminders | Source expires | Owen tells their manager |
| Index rebuild fails | Step 10's comparison | Owen reruns it |
| Weekly run never fires | No log by midday | Owen restarts it |

## Variations

Smaller: a review-date column and a weekly email.
Larger: also flag shared-drive copies.
Different system: a shared-sheet register in Google Workspace Studio.

## Source

*AI Workflows That Run the Business*, Chapter 13, recipe R13.2. Pattern diagram: Figure 13.2 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
