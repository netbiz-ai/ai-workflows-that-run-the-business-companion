# R14.3 Chase overdue actions and carry them into the next agenda

Book chapter 14 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapters 11 and 26

Each working morning, remind each overdue task's owner once, then put any still open on its meeting's next agenda, for the chair to decide.
A due date moved twice is flagged too.
It never moves a date, reassigns or closes a task, or reminds twice for one date.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | `n8n/workflow.json` | Not yet available |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- Tasks tagged with their meeting series, by R14.2 or by hand.
- The register, with each series' calendar and agenda list.
- A tracking list: task ID, verified or first-seen date, last date seen, changes, reminder state, failures.
- A working-day calendar with holidays.

## Build steps

1. Trigger early each working day, skipping holidays.
2. List open, past-due tasks tagged with a registered series; a hand-made task's first-seen date counts as verified.
3. Duplicate key: task ID plus current verified date, so each agreed date earns one reminder.
4. Not yet reminded: write the key "pending", message the owner with task, date and source, then mark it "sent"; a "pending" key is never resent.
5. Reminded a working day ago and still open: find the series' next meeting within 14 days.
6. Found: add an agenda item with action, owner, both dates and days overdue; key task ID plus meeting.
7. None within 14 days: tell Tom once; key task ID, verified date, "no meeting".
8. On Fridays, compare due dates with the tracking list, put a second change on the agenda, and send Tom the count of open overdue tasks by series.
9. After each meeting, read the chair's decisions; a new date becomes verified and resets the change count.
10. A task closed after listing is marked "closed since listed", never removed.

A failed send or write is never retried; it goes to Owen's exception queue.
The count is by series, not person, as Aisha Karim, Finance and HR Manager, asked: a per-person ranking is a performance record nobody approved.

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Morning run never fires | No Friday count by noon | Owen restarts it |
| Message or agenda write fails | Write error | Owen checks, then releases or closes the key |
| Series canceled | Step 7 alerts pile up | Tom moves its tasks elsewhere |

## Variations

Smaller: run weekly, emailing the chair the overdue list before the meeting.
Larger: one count per department, sent to its manager, named on the card.
Different system: the task tool's own due-date reminders can do step 4; steps 5 to 10 stay.

## Source

*AI Workflows That Run the Business*, Chapter 14, recipe R14.3. Pattern diagram: Figure 14.3 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
