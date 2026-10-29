# R6.1 Log emails and meeting notes to the right account and deal

Book chapter 6 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapter 13

Logs each marked customer email and meeting note to the right account and deal.
It never changes a deal's stage, amount or owner, or guesses an unclear match.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-28 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/note.blueprint.json`](make/note.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-27 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- A CRM that takes activities and drafts from a service account and searches by email address.
- A "CRM" folder in each sales mailbox and the shared trade mailbox.
- A named cover for each absent salesperson.
- Meeting notes with the customer's address in a fixed field, held under Book 1's customer-meeting notice rule.
- A note telling the team what AI summarizes; check local monitoring rules (operational guidance, not legal advice).
- A never-log list of own domains and staff private addresses.
- An exception queue for unmatched items, checked daily.

## Build steps

1. Trigger on an email in a "CRM" folder or a saved note.
2. Check the key log for the email's Internet Message-ID header (the same in every mailbox) or the note ID; if logged, stop.
3. Take the customer's address: a received email's sender, a sent one's external recipient, a note's fixed field.
   None, or never-log listed: stop; several external recipients: exception queue.
4. Search the CRM for that full address, never the domain; unless exactly one account matches, queue the item.
5. Read the open deals: with none, log at account level; with several, the AI names one or answers "unclear", which queues it.
6. The AI step, with no write tool, summarizes the untrusted message in at most three sentences, plus any next-step date named.
7. Rules check that any deal is open on this account and the summary within length, or queue it; a past or impossible date is dropped.
8. Write the activity, link and last-contact date; attach the summary and date as a one-click draft for the owner, flagging an AI-chosen deal.

Step 4 never matches on domain because a property manager emails for several owners, each a separate trade account; the golden set includes that case.

## AI steps

- Step 5, only when the account has several open deals, returns `deal` (one listed open deal, or `unclear`): [`prompts/choose-deal.md`](prompts/choose-deal.md).
- Step 6 returns `summary` and `next_step_date`: [`prompts/summarize.md`](prompts/summarize.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| CRM write fails | Write error (no automatic retry) | Owen checks the CRM, then releases or closes the key |
| Wrong deal logged | Owner sees the draft | Owner moves it; Owen adds a golden case |
| Flow stops silently | Nothing logged for a day (Chapter 17) | Owen restarts it; catch-up runs |
| Queue or drafts ignored | Items over two working days old | Ben reassigns them |

## Variations

Smaller: forward marked emails to the CRM's logging address; with no AI summary, Ben alone approves.
Larger: log phone calls, keyed on the call ID, with an unknown number in the golden set.
Different system: a firm on Google Workspace marks mail with a "CRM" label instead of a folder, keyed on the same Message-ID.

## Source

*AI Workflows That Run the Business*, Chapter 6, recipe R6.1. Pattern diagram: Figure 6.1 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
