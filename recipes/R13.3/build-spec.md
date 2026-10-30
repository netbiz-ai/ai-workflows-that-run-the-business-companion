# R13.3 Turn a resolved ticket into a draft knowledge article for the owner to approve

Book chapter 13 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapters 14 and 19

Has AI draft a short article from a resolved ticket that taught the team something, customer details removed first; Nadia approves, and the source's owner signs any policy statement.
It never publishes or writes a price.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-28 ([report](n8n/test-report.md)) |
| Make | [`make/blueprint.json`](make/blueprint.json) and [`make/decision.blueprint.json`](make/decision.blueprint.json) and [`make/weekly.blueprint.json`](make/weekly.blueprint.json) | Available: golden set passed on Make (Core plan), 2026-10-30 ([report](make/test-report.md)) |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- A "reusable" tag, set by the resolver, and an article template.
- R13.1's policy-figures list, and a drafts area only Nadia's team reads.

## Build steps

1. Trigger on a ticket resolved with the "reusable" tag.
2. Duplicate key: ticket ID plus resolution time.
3. Drop Chapter 10's access-code field; replace the customer's name, email, phone, address and order number with labels.
4. Personal-data rule: if such patterns remain, the ticket goes to Nadia with no AI call.
5. AI drafts in fixed fields, with no tools: title, question, answer, steps, and each policy claim.
6. Rules: anything outside the fields fails; step 4's check reruns, and a match discards the draft.
7. Price rule: a currency amount becomes the price-list link.
8. Policy rule: a figure off the policy-figures list, or any warranty, returns or delivery sentence, is marked "needs source".
9. A close title match makes the draft a suggested update.
10. Nadia edits and approves or discards; the source's owner words any "needs source" claim.
11. On approval, publish and register the article with Nadia as owner, so R13.2 watches it.

## AI steps

- Step 5 returns `title`, `question`, `answer`, `steps` and `policy_claims`: [`prompts/draft-article.md`](prompts/draft-article.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Helpdesk adds a customer field | Step 4 matches rise | Owen adds it to step 3 |
| Drafts pile up | Weekly count of drafts over 14 days old | Nadia clears them |

## Variations

Smaller: a weekly list of tagged tickets, no AI.
Larger: one drafts area and lead per support team.
Different system: run steps 3, 4 and 6 to 8 on a helpdesk's own article suggestions.

## Source

*AI Workflows That Run the Business*, Chapter 13, recipe R13.3. Pattern diagram: Figure 13.3 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
