# Governance card: R13.1 Answer staff questions from approved sources, with citations and a refusal path

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Owner: Helen Brandt; builder: Owen Clarke; review date: the annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential. Hosting: n8n Cloud, Frankfurt. Index and embeddings: IT provider's server, Northstar's Microsoft 365 region; backups kept no longer than the question log. AI: Claude Haiku 5.5, Anthropic API, Northstar's key, US-only inference |
| Approver | Each owner, their source's indexing; Owen, prompt and threshold; Helen Brandt, Owner and CEO, the workflow |
| Access | `svc-knowledge` alone queries the index and reads sharing. Editors: Owen, the IT engineer |
| Logging | Question, asker, sources: 30 days, as in Book 1. HR questions: ID and outcome. Gaps, no question text: 13 months |
| Kill switch | Helen sets the stop flag (Chapter 3), or Owen or the IT engineer turns it off; a question in flight gets "I don't know", and staff fall back to library search |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
