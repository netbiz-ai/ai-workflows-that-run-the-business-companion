# Governance card: R5.1 Capture inquiries from web, email and phone notes into one lead record

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Workflow: R5.1 lead capture. Owner: Ben Hollis. Review date: the annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential. Hosting: Northstar's Power Platform environment, in its Microsoft 365 tenant's region. AI processing: the same region while "Move data across regions" and EU flex routing are off, as of October 2026 |
| Approver | Ben, who assigns each lead |
| Access | `svc-leads-capture`: read inbound channels; create leads, activities. Flow owner `svc-flow-owner`. Editors: Owen, IT provider |
| Logging | Source ID, channel, match, lead ID; never the body. 13 months (Chapter 3 default) |
| Kill switch | Ben sets the stop flag (Chapter 3), or Owen turns the flow off; inquiries wait in their channels; a rerun skips stamped ones |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
