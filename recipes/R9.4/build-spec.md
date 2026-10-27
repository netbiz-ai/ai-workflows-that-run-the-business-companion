# R9.4 Remove a leaver's access the same day

Book chapter 9 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapters 10 and 16

On a leaver's last day, removes every item in their access inventory, the single sign-on (SSO) account first, with evidence.
It never decides who leaves, deletes a mailbox or files, or closes a case with an item unconfirmed.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/close.blueprint.json`](make/close.blueprint.json) and [`make/daily.blueprint.json`](make/daily.blueprint.json) and [`make/tick.blueprint.json`](make/tick.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-26 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- A leaver list only Aisha edits, with last day and time.
- R9.1's access inventory, with shared logins, keys, alarm codes and devices; Owen builds earlier staff's.
- A connection or named administrator for each app outside SSO.

## Build steps

1. Trigger daily after closing, or at once for "immediate"; an entry not made by Aisha stops and alerts her.
2. Duplicate key, employee and date: if logged, resume at the first unconfirmed item.
3. If the inventory is empty or lists an administrator, stop and alert Owen: empty means unknown.
4. Disable the SSO account and end its sessions.
5. Remove each app outside SSO through its connection, or task its administrator.
6. Task shared-password changes and token revocation; the manager collects keys, codes and devices.
7. Rule: every item confirmed, by response or a person's timed tick.
8. Unconfirmed at the deadline: IT ticket and alert Owen.
9. Log evidence; Owen closes.

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Disable fails | Step 4 error | Owen disables it |
| Administrator does not tick | Step 8 deadline | IT provider removes it |
| Account missing from inventory | Quarterly access review | Owen removes it; Aisha fixes the template |

## Variations

Smaller: no workflow; a printed inventory checklist on the last day.
Larger: one leaver list for all sites, each site's apps tasked to its administrators.
Role change: run steps 5 to 9 on what only the old template grants.

## Source

*AI Workflows That Run the Business*, Chapter 9, recipe R9.4. Pattern diagram: Figure 9.4 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
