# Governance card: R8.3 Take in a dispute and brief the account owner

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Workflow: R8.3 dispute intake. Owner: Ben Hollis. Review date: annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential: messages and amounts. Hosting: n8n Cloud on Azure, Frankfurt. AI processing: Claude Haiku 5.5, Anthropic API, Northstar's own key, US only |
| Approver | Ben confirms every narrowed or lifted pause and each response; Aisha, credit notes and the exception queue; Helen, when Aisha is away |
| Access | `svc-ar-disputes`: read the AR mailbox, export, CRM and R8.1's key log; write the dispute and status lists; post to Microsoft Teams |
| Logging | Message ID, category, invoices, pause time, brief, owner's decision: 13 months. Credit-note decisions: as the accountant requires |
| Kill switch | Ben or Aisha sets the stop flag (Chapter 3), or Owen unpublishes; replies wait in the AR mailbox for finance, and R8.1 holds until Aisha lets it run alone |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
