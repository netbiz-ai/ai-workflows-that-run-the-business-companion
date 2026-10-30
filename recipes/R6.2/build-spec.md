# R6.2 Remind the owner and draft a follow-up when a quote goes quiet

Book chapter 6 · Band: Starter · Northstar built it on: Power Automate · Book 1: Chapter 13

Each working morning, reminds owners of quiet quotes, with a draft to send, rewrite or ignore.
It never emails a customer, changes a price, or chases a disputed account.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-28 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-30 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- R6.1 running.
- Quotes with a status, sent date, valid-until date and owner.
- A window, gap and reminder limit from the sales lead, say five working days, three days and three.
- A dispute flag, set by hand until R8.3 is built.
- A list of phrases a follow-up may never contain, such as "discount", "price match" or "free".
- Chapter 4's AI-drafting disclosure decision (R4.3).

## Build steps

In Table 6.2, the first row that fits, read from the top, decides.

Table 6.2 in the book: What Each Quiet Quote Gets.

| If the quote | The owner gets | AI draft |
|---|---|---|
| Is quiet for less than the window, or was reminded within the gap | Nothing today | No |
| Is on an account flagged for a dispute or complaint | Nothing; Ben is told once | No |
| Has had every reminder the limit allows | Nothing more; Ben reviews it at the pipeline meeting | No |
| Expires within the window | Reminder: "requote before following up" (R5.3) | No |
| Is due its last allowed reminder | Task: "call, or mark the quote lost" | No |
| Is quiet past the window and the gap | Reminder in Teams and a CRM task | Yes, if it passes step 7 |

1. Trigger each working day, before the trade desk opens.
2. List "sent" quotes with their last activity.
3. Sort each by Table 6.2; only the last row reaches step 6.
4. Check the key log for quote ID plus revision plus reminder number, or quote ID plus "dispute"; if used, skip.
5. Act on the dispute, expiry and last-reminder rows now, without a draft.
6. The AI drafts at most 120 words from the quote's description and last activity summary, with no prices, and `{{quote_ref}}` for the reference.
7. Rules check, as in Example 5.2: placeholder present, length within limit, no listed phrase, no number not copied from the description; a failure drops the draft, not the reminder.
8. Fill `{{quote_ref}}`, task the owner or their cover, post the reminder and any draft in Teams, and write the decision log.

## AI steps

- Step 6 returns `draft`: [`prompts/draft-follow-up.md`](prompts/draft-follow-up.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Reply missed | Reminder for an answered quote | Owner files it; Owen checks R6.1 |
| AI or CRM error | AI: error after three retries. CRM write: error, not retried | AI: reminder without draft. CRM: Owen checks it before anything is redone |
| Flow turned off | No run logged by 9 a.m. (Chapter 17) | Owen restarts; owners check the quote list |
| Reminders ignored | Quote hits the reminder limit | Ben reviews it at the pipeline meeting |

## Variations

Smaller: below about 20 open quotes, a Monday CRM report to Ben, with no AI, is enough.
Larger: a shorter window for larger quotes, the value threshold on the card.
Different system: a cleaning firm chases unsigned proposals, with "cancel" on the never-say list.

## Source

*AI Workflows That Run the Business*, Chapter 6, recipe R6.2. Pattern diagram: Figure 6.2 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
