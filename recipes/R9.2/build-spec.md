# R9.2 Answer policy questions from approved sources and hand off to HR

Book chapter 9 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapters 16 and 19

Answers what a policy says by quoting it, and sends every other question to HR.
It never reads personnel records, and a keyword screen and the model's check stop answers about the asker's own situation.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | `n8n/workflow.json` | Not yet available |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- One approved policy folder all staff can read, each document with an owner, effective date and status.
- Aisha's list of personal phrasings ("my pay"); a fixed reply naming her and Tom Rivera, Operations Manager.
- An intake channel that knows who asks; restricted and gap logs; twenty test phrasings kept out of the screen.

## Build steps

1. Trigger on a question; duplicate key, the message ID: if logged, stop.
2. Rule: on a sensitive match, send the fixed reply and pass the text to Aisha.
3. Retrieve passages from current approved documents only; if none, reply "no source", hand off, and log a gap.
4. AI, with no tools: "Answer only from these passages, quoting word for word; set about_asker to yes if it concerns the asker's own situation."
   Fields: answer, document, quote, about_asker (yes or no).
5. Rules: citations retrieved, quotes word for word, every number in the quote, about_asker is no; otherwise hand off.
6. Send the quote and link, ending "For your own situation, ask Aisha."
7. Log the outcome, handoffs by ID only.

Each month Owen runs the twenty test phrasings; one answered switches R9.2 off.

## AI steps

- Step 4 returns `answer`, `document`, `quote` and `about_asker`: [`prompts/answer-policy-question.md`](prompts/answer-policy-question.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| Model or intake fails | Error after retries | Owen fixes it; Aisha answers |
| Personal question answered | Monthly test, or an employee | R9.2 goes off; Aisha adds phrasings |
| Re-asked share rising | Monthly count | Aisha fills the gap log |

## Variations

Smaller: no AI; a page of the twenty most-asked questions, each linked.
Larger: R13.1 in Chapter 13, with permission checks.
Different system: a shared Google Drive folder changes only step 3's source.

## Source

*AI Workflows That Run the Business*, Chapter 9, recipe R9.2. Pattern diagram: Figure 9.2 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
