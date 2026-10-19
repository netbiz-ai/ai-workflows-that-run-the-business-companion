# R9.1 Run onboarding: accounts, equipment, training tasks and first-week checklist

Book chapter 9 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapter 16

Gives every new hire the accounts, equipment, training and first-week plan their role needs on day one.
It never decides hiring, pay or role, or grants access the template does not list.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- Confirmed hires in a SharePoint list Aisha fills from the HR platform (Power Automate lists no BambooHR connector, as of October 2026).
- An approved template per role; manager's notes in task, day and owner fields.

## Build steps

1. Trigger on a confirmed hire; "withdrawn" asks Aisha to start R9.4.
2. Rule: role, manager, template and future start date, or return it to Aisha.
3. Duplicate key, the person ID: if logged, stop; a moved start moves the tasks.
4. Create only the template's accounts and groups, logging its version; write each to the inventory.
5. Raise equipment and training tasks with owners and dates.
6. AI, with no tools, drafts the checklist: "List week-one tasks only from these inputs, as rows of day (1 to 5), task, owner."
7. Rules: every task from the inputs, owner in the directory; otherwise use the template's.
8. The manager approves or edits; under 2 working days from the start, the template's goes.
9. Send the welcome pack; log.

## AI steps

- Step 6 returns rows of `day`, `task` and `owner`: [`prompts/draft-checklist.md`](prompts/draft-checklist.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Account creation fails | Write error (no retry) | Owen checks, then raises an IT ticket |
| AI fails, or manager silent | Error, or 2 working days | Template checklist goes |
| Welcome pack not sent | Send error | Aisha sends it |

## Variations

Smaller: below about 30 people, drop the AI step; the template is the checklist.
Larger: one template per role and site, each with its own golden case.
Different system: your HR platform's onboarding module, keeping the inventory (Case Example 9.1).

## Source

*AI Workflows That Run the Business*, Chapter 9, recipe R9.1. Pattern diagram: Figure 9.1 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
