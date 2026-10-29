# R4.3 Draft a reply from approved sources for a person to edit and send

Book chapter 4 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapters 14 and 19

Gives whoever answers a first draft built only from owned policy articles and the order.
A person edits and sends every reply; the workflow never sends or drafts without a source.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-28 ([report](n8n/test-report.md)) |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- Short, owned, dated policy, price and warranty articles, and read access to orders.
- An internal note field a customer cannot see.
- R4.1 and R4.2 running.

## Build steps

1. Trigger when a ticket enters a draft queue (Table 4.1).
2. Check the duplicate key; if a draft exists for that message, stop.
3. If R4.2 has escalated the ticket, stop; if R4.2 has not logged it yet, recheck every five minutes, up to three times, then flag it for a person.
4. Retrieve the approved article for the topic, and the order; with no article, flag "no source" and stop.
5. Ask the AI to draft from those sources only: "Use only these sources. Cite a source ID after every sentence or question stating a policy, price, date, duration, amount or commitment. Write GAP where they do not answer; offer nothing they do not state."
6. Check with rules: each such sentence or question cites a retrieved source, and its amounts, dates and durations ("two years") appear in that source; a commitment word (free, refund, replace, credit, visit) fails unless that source contains it.
   The rules test form, not meaning; the sender still checks what each sentence promises.
7. On a failed check, or an AI error after one retry, save no draft and flag the ticket; otherwise save an internal note listing its sources.
8. When the reply is posted, log the draft as unchanged, edited or discarded.

Table 4.1 is printed in [R4.2's build spec](../R4.2/build-spec.md#build-steps).

## AI steps

- Step 5 returns `draft`, the reply text with a source ID cited after every policy, price, date, duration, amount or commitment, and GAP where the sources do not answer: [`prompts/draft-reply.md`](prompts/draft-reply.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Lookup or AI step fails | Error after one retry | Person writes the reply |
| Article out of date | Review date passes | Nadia updates or withdraws it |
| Drafts quietly edited | Logged edit rate rises | Nadia samples them, fixes the article |

## Variations

Smaller: suggest an article, not a draft, with no AI step.
Larger: draft in two languages, with articles and golden cases in both.
Different system: with a helpdesk's own AI drafts, keep the claim check; turn off auto-send.

## Source

*AI Workflows That Run the Business*, Chapter 4, recipe R4.3. Pattern diagram: Figure 4.3 in the book.
The golden set's refusal cases replay Book 1's Incident A; the book's Example 4.1 walks it through the claim check.
Northstar Home & Appliance is fictional; names in the tables are its people.
