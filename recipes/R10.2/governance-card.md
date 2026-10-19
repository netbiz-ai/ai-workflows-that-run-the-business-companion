# Governance card: R10.2 Send delivery confirmations and handle reschedule replies

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Owner: Tom Rivera. Review date: the annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential: name, contact, address, replies; codes masked. Hosting: n8n Cloud on Azure, Frankfurt. AI: Claude Haiku 5.5, Anthropic application programming interface (API), Northstar's own key, US-only inference |
| Approver | Tom, for templates and workflow; a dispatcher confirms every slot change |
| Access | `svc-delivery-messages`: read work orders and open slots; send templates; create dispatcher tasks; no schedule write |
| Logging | Job, message, intent, slots offered, outcome: 13 months; masked replies 30 days |
| Kill switch | Owen, or Tom by the stop flag (Chapter 3); sent offers stay requests; dispatchers confirm picks by phone |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
