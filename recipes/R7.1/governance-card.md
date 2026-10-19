# Governance card: R7.1 Extract supplier invoice fields into a structured record

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Workflow: R7.1 invoice intake. Owner: Aisha Karim. Review date: annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential. Hosting: n8n Cloud on Azure, Frankfurt. AI processing: Claude Haiku 5.5, Anthropic API, Northstar's own key, US-only inference |
| Approver | Aisha reviews every flagged record and a weekly sample of 25; Helen Brandt, Owner and CEO, approves spend |
| Access | `svc-ap-intake`: read the mailbox, write the review list |
| Logging | Rule results; accounts masked. Decision logs 13 months |
| Kill switch | Aisha sets the stop flag (Chapter 3) or Owen unpublishes; invoices wait in the mailbox |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
