# Governance card: R11.1 Collect supplier quotes into one normalized comparison

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Owner: Tom Rivera. Review date: the annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential prices. Hosting: n8n Cloud on Azure, Frankfurt. AI: Claude Haiku 5.5, Anthropic application programming interface (API), Northstar's own key, US-only inference |
| Approver | Tom; the stockroom lead checks AI-filled rows |
| Access | `svc-quotes-intake`: read mailbox and export; write sheet and queue. Editor: Owen |
| Logging | Message ID, fingerprint, flags, outcome: 13 months |
| Kill switch | Owen, or Tom by the stop flag (Chapter 3); queued quotes wait; the stockroom lead types them |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
