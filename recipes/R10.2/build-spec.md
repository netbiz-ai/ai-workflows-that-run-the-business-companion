# R10.2 Send delivery confirmations and handle reschedule replies

Book chapter 10 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapters 14 and 17

Confirms each job, reminds the customer the day before, and turns reschedule replies into requests a dispatcher confirms.
It never moves, cancels or assigns a job, offers an unlisted slot, or discusses refunds or damage.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- R10.1's work orders, with each customer's preferred channel.
- A scheduling-system event when a slot is set or changed, and read access to open slots by zone.
- Templates by Tom and Nadia Ferreira, Customer Service Specialist: confirmation, reminder, numbered slot request, "a dispatcher will call you".
- A reply channel keeping the job reference, such as a text-message (SMS) number per job, and consent where required.

## Build steps

1. Trigger when a slot is set or changed; send the confirmation with date, window and preparation notes.
2. Each afternoon, send reminders for tomorrow's jobs.
3. Second trigger: a customer reply; duplicate key, the message ID; if logged, stop.
4. Rule: mask codes with R10.1's step 4 rule before anything reads or logs the reply.
5. Rule: "leak", "smoke", "injured" or "damaged" goes to a dispatcher at once and to R4.2 (Chapter 4).
6. Rule: a 1, 2 or 3 answering a slot request is a pick for the dispatcher; any other trade reply goes to a dispatcher at once.
7. AI labels any other reply, with no tools: confirm, reschedule, cancel, question, other.
8. Rule: an allowed label and a valid job reference; otherwise a dispatcher task.
9. Confirm: logged only on a plain yes naming no day, date or time; question or other: the service inbox (R4.1); anything else: a dispatcher task.
10. Reschedule: send up to three open slots in the zone: "Reply 1, 2 or 3 within 24 hours and a dispatcher will confirm your new time; until then your booking stays as it is."
11. The dispatcher books the pick, triggering step 1, or phones if it has gone.
12. With no pick in 24 hours, a dispatcher decides whether to phone.

## AI steps

- Step 7 returns `label` (confirm, reschedule, cancel, question or other): [`prompts/label-reply.md`](prompts/label-reply.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Message not delivered | Send error or bounce | Dispatcher phones |
| AI or slot lookup fails | Error after retries | Dispatcher task with the reply |

## Variations

Smaller: no AI; the reminder asks for 1 to confirm or 2 to rebook, and each 2 is a dispatcher task.
Larger: several depots, each with its own zones and queue.

## Source

*AI Workflows That Run the Business*, Chapter 10, recipe R10.2. Pattern diagram: Figure 10.2 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
