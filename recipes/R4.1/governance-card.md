# Governance card: R4.1 Classify and route every incoming message to the right queue

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Workflow: R4.1 inbox routing. Owner: Tom Rivera. Review date: annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential. Hosting: Northstar's Power Platform environment, in its tenant's region. AI processing: the same, with "Move data across regions" and EU flex routing off, as of October 2026 |
| Approver | Tom, owner of the category list |
| Access | `svc-inbox-triage`: read tickets; set category, queue, tags. Editors: Owen, IT provider |
| Logging | Ticket ID, category, confidence, rule result; never the body. 13 months |
| Kill switch | Tom sets the stop flag (Chapter 3) or Owen turns it off; messages land in the general queue; R4.2 still escalates |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
