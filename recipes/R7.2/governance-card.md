# Governance card: R7.2 Match the invoice to the purchase order and delivery receipt

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Workflow: R7.2 three-way match. Owner: Aisha Karim. Review date: annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential. Hosting and AI processing: as R7.1 |
| Approver | Aisha, tolerances. Payments: Aisha to $10,000, Tom above, Helen where Tom raised the order or resolved the item |
| Access | `svc-ap-match`: reads orders, receipts, R7.3's check list; writes results |
| Logging | Results, tolerance version: decision logs 13 months; approvals as the accountant requires |
| Kill switch | Aisha sets the stop flag (Chapter 3) or Owen unpublishes; Aisha matches waiting invoices by hand |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
