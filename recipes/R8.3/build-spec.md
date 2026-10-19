# R8.3 Take in a dispute and brief the account owner

Book chapter 8 · Band: Growth · Northstar built it on: n8n Cloud · Book 1: Chapters 13 and 15

Turns any reply questioning an invoice into a logged dispute, pauses its reminders, and briefs the account owner.
It never replies, promises a credit, decides who is right, or lifts a pause.

## Status

| Platform | File | Status |
|---|---|---|
| Tool-neutral | `build-spec.md` | Available |
| n8n | [`n8n/workflow.json`](n8n/workflow.json) | Available: golden set passed on n8n 2.42.7, 2026-10-19 ([report](n8n/test-report.md)) |
| Make | `make/blueprint.json` | Not yet available |
| Power Automate | `power-automate/` | Not yet available |
| Zapier | `zapier.md` | Not yet available |

## Prerequisites

- R8.1's AR mailbox, export and dispute list; the CRM's account owners.
- An unlinked-item exception queue Aisha works each morning, and a status list of mailbox checks.
- R4.2's escalation rules for legal threats and safety (Chapter 4).

## Build steps

1. Trigger on each new outside message in the AR mailbox, skipping automatic replies; write each check's time to the status list.
2. Stop on a message ID already logged.
   Match the sender to a CRM account; failing that, an invoice number to the export, then the domain to the CRM; otherwise, the exception queue.
3. Write a whole-account pause to the dispute list, marked "reply received".
4. The AI step, with no tools, returns fixed JavaScript Object Notation (JSON) fields: category (dispute, says paid, promise to pay with its date, question, other), invoice numbers, any amount questioned, and a summary of at most 80 words.
5. Rules check the category, that each invoice is open on this account, and that no amount exceeds its invoice; failures go to the queue.
6. If R4.2's rules match a legal threat or safety issue, escalate to Aisha and the owner.
7. A message on an invoice already in dispute adds a note, not a dispute.
8. Brief the account owner (and Aisha, for "says paid"): amount, due date and reminders sent, from the export and R8.1's key log; the AI output, labeled as AI; a message link.
9. The owner confirms which invoices the reply covers; only then does the pause narrow.
10. The owner decides and writes any reply; a credit note goes to Aisha.
11. A person ends each pause (Table 8.2); only Aisha clears a whole-account pause.

| Reply | Pause covers | Brief goes to | Pause ends when |
|---|---|---|---|
| Dispute | Confirmed invoices | Account owner | Closed: "resume reminders" or "credit raised" |
| Says paid | Confirmed invoices | Owner and Aisha | Aisha finds the payment, or the owner logs a dispute |
| Promise to pay | Confirmed invoices | Account owner | The date the owner confirms passes unpaid |
| Question or other | Confirmed invoices, or the account | Account owner | The owner marks it handled |
| Fails the check, or unmatched | The whole account | Aisha, in the unlinked queue | Aisha links it; then as above |

*Table 8.2: What Each Reply Does to the Pause*

## AI steps

- Step 4 returns `category`, `promise_date`, `invoice_numbers`, `amounts_questioned` and `summary`: [`prompts/extract-reply.md`](prompts/extract-reply.md).

## Golden set

See `golden-set.csv`; run it before go-live and after every change (book Chapter 16, Appendix D).

## Failure modes and recovery

| Failure | How the workflow notices | What a person does |
|---|---|---|
| AI or mailbox error | Error workflow after three retries | Aisha links it; final notices hold |
| Mailbox access lost | The status list goes stale | R8.1 sends nothing; Owen restores access |
| Brief not acted on | Dispute open past the limit Aisha sets | Aisha reassigns it |

## Variations

Smaller: no AI; every reply pauses the account for Aisha.
Larger: link the brief to the work order.
Different system: a plumbing firm reads call-out charge disputes, the job sheet in the brief.

## Source

*AI Workflows That Run the Business*, Chapter 8, recipe R8.3. Pattern diagram: Figure 8.3 in the book.
Northstar Home & Appliance is fictional; names in the tables are its people.
