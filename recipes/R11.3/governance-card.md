# Governance card: R11.3 Route purchase approval by amount and remaining budget

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Owner: Aisha Karim. Review date: the annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential: amounts, budget lines. Hosting: Northstar's Power Platform environment, in its Microsoft 365 tenant's region. No AI processing |
| Approver | By Table 11.2: Tom up to $10,000 within budget, Helen otherwise; never the requester or payment approver |
| Access | `svc-purchase-approvals`: read requests and budget; write approvals and commitments. Editor: Owen |
| Logging | Request, version, approver, decision, time, budget before and after: kept as long as Northstar's accountant requires; decision logs 13 months |
| Kill switch | Owen, or Aisha or Helen by the stop flag (Chapter 3); nothing in flight is released; approvers sign paper requests, which Aisha logs |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
