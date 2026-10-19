# Governance card: R9.3 Take leave requests, check the balance and route to the manager

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Workflow: R9.3 leave requests. Owner: Aisha Karim. Review date: annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential: name, dates, type, balance. Hosting: as R9.1. No AI |
| Approver | The manager or stand-in decides; Aisha approves the rules |
| Access | `svc-leave`: read export and list, write requests, send approvals |
| Logging | Request, warnings, decision, decider: 13 months |
| Kill switch | Aisha sets the stop flag (Chapter 3) or Owen turns it off; open requests stay with managers; staff email theirs |

"As R9.1" is R9.1's hosting: Northstar's Power Platform environment, in its tenant's region (see [`../R9.1/governance-card.md`](../R9.1/governance-card.md)).

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
