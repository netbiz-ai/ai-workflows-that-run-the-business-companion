# R15.3 Keep consent and unsubscribes in sync across every list

Book chapter 15 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapters 10 and 20

When anyone opts out of or into marketing, it records the change in the master consent record, applies it to every list, and confirms each list took it; an opt-out always wins, so an unconfirmed list is suppressed for that person, or held.
It never infers consent from a purchase or blocks a transactional message.
An opt-out covers every marketing channel, as Northstar's outside legal adviser ruled.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- Every list that can send marketing: at Northstar, the CRM, the shop, store point-of-sale (POS) sign-ups and the helpdesk.
- The CRM's consent fields as the system of record, with the wording version the person saw.
- A "marketing opt-out" helpdesk tag, and a send-status record Ben checks before every marketing send.

## Build steps

1. Trigger on a consent event: unsubscribe, opt-in, POS sign-up or helpdesk tag.
2. Duplicate key: the event ID; a repeat stops.
3. Rule: an opt-in counts only with its wording version and time stamp.
4. Rule: order by the event's own time stamp; an opt-in older than an opt-out is ignored.
5. Write the change to the CRM for every channel in scope.
6. Apply it to every other list, matched on email or phone, never name, and read it back.
7. If a list does not confirm an opt-out, do not retry: suppress the person elsewhere, or mark the list "paused", and tell Owen.
8. Each night, correct any list that differs from the master.

## AI steps

None: this recipe has no AI step.

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Unlisted list | Quarterly review | Owen adds it |
| R15.3 stopped | An n8n heartbeat sees no nightly run; Owen told | Owen marks every list "paused" within an hour |
| Write still failing | List held next day | Owen checks, then applies the change by hand |

## Variations

Smaller: one sending tool; steps 1 to 5.
Larger: text-message (SMS) consent as its own channel, with its own proof field and golden cases.
Different system: a consent tool as master; the CRM becomes one more list to write and read back.

## Source

*AI Workflows That Run the Business*, Chapter 15, recipe R15.3. Pattern diagram: Figure 15.3 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
