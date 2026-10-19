# Governance card: R7.3 Stop and verify any change to a supplier's bank details

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Workflow: R7.3 bank-detail stop. Owner: Aisha Karim. Review date: annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential. Hosting: Northstar's Power Platform environment, in its Microsoft 365 tenant's region. No AI |
| Approver | The caller confirms and co-signs the pre-run check; the finance assistant enters; Aisha reviews monthly |
| Access | `svc-ap-bankcheck`: read records and exports; write holds and the check list |
| Logging | Checks: decision logs 13 months; masked call-backs as the accountant requires |
| Kill switch | Aisha sets the stop flag (Chapter 3) or Owen turns it off; Helen is alerted; every supplier is held |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
