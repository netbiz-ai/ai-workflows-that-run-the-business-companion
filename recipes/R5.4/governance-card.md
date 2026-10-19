# Governance card: R5.4 Route quote approval by value and discount

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Workflow: R5.4 quote approval routing. Owner: Helen Brandt. Review date: the annual library review.

| Field | Entry |
|---|---|
| Data class | Confidential. Hosting: as R5.1. No AI processing |
| Approver | Helen, for the thresholds; the routed person, for each quote |
| Access | `svc-quote-approval`: read quotes; set status; send requests. Editors: Owen |
| Logging | Quote ID, revision, value, discount, approver, decision, time. Decision log 13 months; approval records as long as the company's accountant requires |
| Kill switch | Helen sets the stop flag, or Owen turns the flow off; quotes stay locked; Ben routes by hand |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
