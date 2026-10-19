# Governance card: R6.3 Find likely duplicate accounts and queue them for a person to merge

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Workflow: R6.3 duplicate queue. Owner: Ben Hollis; builder: Owen Clarke. Review date: the annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential: accounts, contacts, quote and order references, credit terms. Hosting: n8n Cloud on Azure, Frankfurt. AI processing: Claude Haiku 5.5, Anthropic API, Northstar's own key, US-only inference |
| Approver | Owen merges; Ben confirms first for an open quote; Aisha Karim, Finance and HR Manager, for credit terms |
| Access | `svc-crm-dedupe`: read accounts and contacts; write the queue and suppression list. No merge or delete permission. Editors: Owen |
| Logging | Pairs, signals, decision, who, when: 13 months (Chapter 3 default). Exports: Owen, Ben and Aisha only, deleted after 30 days (illustrative) |
| Kill switch | Ben sets the stop flag, or Owen turns it off in n8n; queued pairs stay for a person to decide |

Erasure covers the exports.

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
