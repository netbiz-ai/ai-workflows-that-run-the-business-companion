# Governance card: R11.2 Block expired quotes and out-of-policy orders before they are placed

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Owner: Tom Rivera. Review date: the annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential: supplier prices, budget lines. Hosting: Northstar's Power Platform environment, in its Microsoft 365 tenant's region. No AI processing |
| Approver | Tom; Aisha Karim, Finance and HR Manager, reviews waivers monthly |
| Access | `svc-purchase-checks`: read requests, sheet and exports; write status. Editor: Owen |
| Logging | Request ID, version, rule results, reason codes: 13 months |
| Kill switch | Owen, or Tom by the stop flag (Chapter 3); requests stay "ready", and Tom checks them by hand against Table 11.2 |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
