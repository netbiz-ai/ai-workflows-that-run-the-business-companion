# R4.2 Escalate complaints, safety issues and legal threats to a person at once

Book chapter 4 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapters 5 and 14

Puts the burning-oven message before a named person within minutes, at any hour.
It notifies and waits; it never replies, decides or closes the case.
This is operational guidance, not legal advice.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-28 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/clock.blueprint.json`](make/clock.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-30 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- A safety and legal keyword list, owned by Tom, reviewed quarterly.
- An owner and backup for every hour; out of hours, Book 1's on-call phone, reached by text message.
- Acknowledgment limits (*modeled*): 15 minutes in opening hours, 30 out of hours.

## Build steps

R4.2 enforces Table 4.1: who sees each message first, and what reaches R4.3.

| Message type | First seen by | AI may draft from |
|---|---|---|
| Safety report, legal threat or complaint | A named person, at once | Nothing; the person writes |
| Unclear, low confidence or uncovered language | The triage lead | Nothing until it is sorted |
| Warranty question | Its queue | The current warranty article |
| Return request | Its queue | The returns article and the order |
| Delivery date or order status | Its queue | The customer's order |

Table 4.1: Who Sees It First, and What AI May Draft.

1. Trigger on each new message directly, so R4.1 being off never stops escalation.
2. Check its own duplicate key; a new message on an escalated ticket is rechecked.
3. A keyword, or an attachment with almost no text, escalates at once.
4. Otherwise, the AI rates complaint, safety and legal risk, each yes or no; any yes, other value or error escalates.
5. Escalate: raise the priority, text and call the owner, and start the clock; only the owner taking the ticket stops it.
6. If the limit passes, text and call the backup on a fresh clock, then Tom; log every step.

## AI steps

- Step 4 returns `complaint`, `safety` and `legal`, each `yes` or `no`: [`prompts/rate-risk.md`](prompts/rate-risk.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| No runs (flow off) | Outside monitor (Chapter 17) | Owen restarts; triage lead scans the queue |
| Nobody acknowledges | Clock passes the limit | Backup, then Tom, takes the case |
| Too many false alarms | Weekly count closed as routine | Tom prunes keywords, reruns golden set |

## Variations

Smaller: keywords and a phone notice; no AI step, credits or AI golden cases.
Larger: separate legal and safety owners, each with a backup.
Different system: keep the helpdesk's escalation rules and add the clock and backup.

## Source

*AI Workflows That Run the Business*, Chapter 4, recipe R4.2. Pattern diagram: Figure 4.2 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
