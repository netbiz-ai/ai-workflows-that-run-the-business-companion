# Governance card: R10.1 Turn a sale into a complete work order, with restricted fields protected

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Owner: Tom Rivera. Review date: the annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential: name, phone, address, order, notes. Restricted: the access-code field, never read. Hosting and AI: below |
| Approver | Tom, for the field list, masking list and workflow; the dispatcher adds each code and releases the job |
| Access | `svc-workorders`: read sales and zone sheet; write work orders. Editors: Owen, the information technology (IT) provider's engineer |
| Logging | Order ID, key, missing fields, work order, outcome: 13 months. Run history, with raw notes: 30 days, as of October 2026; editors only |
| Kill switch | Owen, or Tom by the stop flag (Chapter 3); held orders wait; dispatchers key new orders by hand |

Hosting: Northstar's Power Platform environment, in its tenant's region; AI processing: the same, with "Move data across regions" and EU flex routing off, as of October 2026.

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
