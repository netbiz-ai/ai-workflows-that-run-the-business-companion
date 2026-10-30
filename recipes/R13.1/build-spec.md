# R13.1 Answer staff questions from approved sources, with citations and a refusal path

Book chapter 13 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapters 19 and 23

Lets any employee ask in plain words and get a short, linked answer from current documents they may open, or "I don't know", the owner's name, and a logged gap.
It answers only from retrieved passages the asker may open, every sentence cites one, and it never quotes a price.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-28 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-30 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- R13.2 running; audiences as directory groups or named people.
- An answer index, specified after the build notes.
- A channel that knows the asker; read-only directory access.
- The owner-approved policy-figures list, such as the meal allowance.
- Fifty test questions; last month's questions for tuning.

Table 13.1, the source register, lists every source answers may use.

| Source | Owner | Audience | Authoritative for |
|---|---|---|---|
| Expense policy | Aisha Karim | All staff | Expense claims and the meal allowance |
| Returns and warranty terms | Tom Rivera, Operations Manager | All staff | Return windows and warranty length |
| Delivery and installation guide | Tom Rivera | Store supervisors, delivery crews | Delivery slots; installation steps, safety-critical |
| Vehicle rule | Tom Rivera | All staff | Van use, including taking a van home |
| Approved knowledge articles | Nadia Ferreira | Customer service | Product fixes from resolved tickets (R13.3) |
| Price list, in the CRM | Aisha Karim | All staff | Prices: link only, never quoted |

Each row also holds the fields R13.2 maintains: delegate, dates, status and version.
A safety-critical source (at Northstar, only the delivery and installation guide) gets link and owner only.

The answer index, as the book specifies it after the build notes:

Cut passages at headings, about 300 to 500 words each, each stored with its source, version, audience, status and dates.
Filter on audience, status and dates inside the query, before ranking, so an unpermitted passage is never scored.
Keep the five best passages above the threshold, logging scores for retuning.

## Build steps

1. Trigger on a question; take the asker from the channel, never the message.
2. Duplicate key: the message ID.
3. Rules: personal HR questions get R9.2's reply and go to Aisha; price questions get the price-list link.
4. Look up the asker's directory groups.
5. Search current, in-date passages whose audience includes the asker or their groups.
6. Rule: below the relevance threshold (tuned on last month's questions, never the fifty), reply "I don't know" with the topic's owner, or Owen, and log the gap.
7. Access check: drop any retrieved document the asker cannot open now; if none remain, reply as in step 6.
8. The AI step, without tools, answers in fixed fields: sentences with passage IDs, plus "conflict" and "not answered" flags.
9. Citation rules: each sentence cites a retrieved passage holding its numbers and dates, and quotes match exactly; an unlisted currency amount sends the price-list link.
10. Rule: "conflict" names both sources and owners; "not answered" goes as step 6.
11. Rule: a source withdrawn since step 5 fails the answer.
12. Pass: add each citation's title, date and link, ending "[Owner] decides your case; reply 'wrong' if this is."
13. Fail, or an AI error after two retries: "I don't know", reason logged.

Step 9 checks citations, not meaning; the footer and golden set catch a dropped "only if".
Table 13.2 gives each outcome's reply and log entry.

| Question or result | What the asker gets | Logged as | Step |
|---|---|---|---|
| Personal HR question | R9.2's fixed reply; question to Aisha | ID and outcome only | 3 |
| Price question, or a currency amount not on the policy-figures list | The price-list link, no price | Routed to price list | 3, 9 |
| No passage above the threshold or open to the asker, or "not answered" | "I don't know", with the topic's owner | Gap: topic and owner | 6, 7, 10 |
| The AI flags a conflict | Both sources and owners, no answer | Conflict | 10 |
| Output outside the fields, an uncited sentence, an unsupported number or date, or a misquote | "I don't know" | Check failed, with reason | 8, 9, 13 |
| A source withdrawn since the search, or an error after two retries | "I don't know" | Withdrawn, or error with reason | 11, 13 |
| Every check passes | The answer, each claim with its source's title, date and link, and the deciding owner | Answered; a "wrong" reply logs a gap | 12 |
| Every check passes, safety-critical source | The source's link and owner only | Answered, link only | 12 |

## AI steps

- Step 8 returns `sentences` (each with its passage IDs), `conflict` and `not_answered`: [`prompts/answer.md`](prompts/answer.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).
Go-live, as in Book 1: 45 of 50 correct, a right "I don't know" included, and zero answers beyond access.

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Audience differs from sharing | R13.2's comparison | Owen fixes the register |
| Model update strays | Citation failures rise | Owen pins the model, reruns the fifty |
| A gap or "wrong" recurs | Monthly gap count | The owner fixes the section |

## Variations

Smaller: library search, no AI.
Larger: an index each for stores, office and crews.
Different system: Google Workspace Studio allows 20 steps a flow, as of October 2026; use two flows.

## Source

*AI Workflows That Run the Business*, Chapter 13, recipe R13.1. Pattern diagram: Figure 13.1 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
