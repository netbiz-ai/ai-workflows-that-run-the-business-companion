# Governance card: R10.3 Prepare tomorrow's dispatch briefing, read-only

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Owner: Tom Rivera. Review date: the annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential: names, addresses, job notes; codes masked before AI and post. Hosting and AI: as R10.2 |
| Approver | Tom, for sources, caps and workflow; the lead dispatcher acts on each briefing |
| Access | `svc-dispatch-read`: read-only; posts to one channel; writes only its budget table |
| Logging | Run time, sources reached, job count, AI spend, outcome: 13 months; briefings 30 days |
| Kill switch | Owen or the IT provider's engineer, or Tom by the stop flag (Chapter 3); the lead dispatcher uses the overdue list |

"As R10.2" means: hosting on n8n Cloud on Azure, Frankfurt; AI: Claude Haiku 5.5, Anthropic application programming interface (API), Northstar's own key, US-only inference (see [`../R10.2/governance-card.md`](../R10.2/governance-card.md)).

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
