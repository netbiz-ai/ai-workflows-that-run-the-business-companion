# R14.2 Create tasks with owners and due dates after verification

Book chapter 14 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapters 8 and 26

When the chair marks a list verified, create one task per approved item, carrying its source, and tell each owner once.
It never acts on unverified items, chooses owners or dates, or edits tasks.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- R14.1 running, or chairs typing lists in by hand.
- A task plan per series, visible to attendees, and read access to the register.

## Build steps

1. Trigger when a list changes to "verified"; one list at a time.
2. Rule: the verifier must be the series' chair or backup; otherwise stop and alert Tom.
3. Rule: an item owned outside the company, such as by a supplier, goes into the minutes, with a follow-up task for the chair.
4. Check each other item against Table 14.1; a failure returns it to the chair with the reason.
5. Skip an item holding a task ID.
6. Search the task system for the item ID; a match writes that ID back and creates nothing.
7. Create the task with the fields in Table 14.1, plus the item ID and quoted line.
8. Write the task ID, verified due date and time back, then send each owner one message listing their new tasks.
9. Retry a task-system error once, then tell the chair.

Table 14.1: What a Verified Action Item Carries

| Field | Set by | Checked before a task exists | Example |
|---|---|---|---|
| Action | AI proposes; chair edits | Present, verb first | Send reschedule list to crews |
| Owner | Said aloud; chair confirms | Active staff account; outside owners go to the minutes | Nadia Ferreira |
| Due date | Said aloud or set by rule; chair confirms | Calendar date, not past; "next week" returns | October 15 |
| Source link | Workflow | Opens the transcript at the item's line | Transcript, 00:04:12 |
| Meeting series | Register | In the register; copied onto the task | Delivery planning |
| Verified by | Chair's click | The series' chair or backup | Tom Rivera |
| Verified due date | Write-back | Kept on the item for R14.3 | October 15 |
| Task ID | Workflow | Empty before; filled means skip | Step 8 |

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Owner has left | Account check fails at step 4 | Chair reassigns the item |
| Task system down | Creation fails after one retry | Owen reruns; steps 5 and 6 guard |
| Items returned often | Weekly returns per series | Tom coaches chairs |

## Variations

Smaller: no task system; each owner gets one email, and R14.3 reads the action list.
Larger: route items to each department's project tool, each with its own duplicate search.
Different system: trade-account actions become customer relationship management (CRM) tasks via R6.1.

## Source

*AI Workflows That Run the Business*, Chapter 14, recipe R14.2. Pattern diagram: Figure 14.2 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
