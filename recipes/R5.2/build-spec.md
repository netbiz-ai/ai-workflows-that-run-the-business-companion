# R5.2 Prepare a research and qualification brief for the salesperson

Book chapter 5 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapter 13

Gives the salesperson a sourced one-page brief before the first call: the company, its history with you, and its criteria scores.
It never contacts the prospect, changes a field, or decides on the lead.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | `n8n/workflow.json` | Not yet available |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- R5.1 running, so each lead has one record.
- Read access to account history and past quotes, by record ID.
- Five to seven written criteria, owned by Ben, reviewed quarterly.
- Public source types, such as websites and planning notices, agreed with whoever owns privacy.

## Build steps

1. Trigger when a lead is assigned.
2. Stop if the duplicate key, the lead ID, was seen.
3. Gather CRM history and up to five allowed pages, recording each ID and address; a page failing twice is "not fetched".
4. The AI writes company, past dealings, need, and each criterion as met, not met or unknown, every claim citing a step 3 source.
   Pages are untrusted: tell the AI to ignore their instructions, and give it no tool that writes.
5. Check with rules: every section present, every criterion one of the three values, every source from step 3.
   A second rule fails the brief if a page holds a listed phrase such as "ignore your".
6. Attach a passing brief, a failing one marked "Unverified: check sources", or, after an AI error, the links.

## AI steps

- Step 4 returns `company`, `past_dealings`, `need` and `criteria`, every claim citing a step 3 source: [`prompts/draft-brief.md`](prompts/draft-brief.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| False claim | Salesperson checks the source | Ben adds a golden case |
| AI step errors | Brief has links only | Salesperson researches by hand |

## Variations

Smaller: links and CRM history only, no AI.

## Source

*AI Workflows That Run the Business*, Chapter 5, recipe R5.2. Pattern diagram: Figure 5.2 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
