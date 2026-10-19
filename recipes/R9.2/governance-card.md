# Governance card: R9.2 Answer policy questions from approved sources and hand off to HR

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Workflow: R9.2 policy answers. Owner: Aisha Karim. Review date: annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Restricted: questions. Hosting: n8n Cloud on Azure, Frankfurt. AI: Claude Haiku 5.5, Anthropic API, Northstar's own key, US-only inference |
| Approver | Aisha: sources, list, reply, golden set; she answers handoffs, Tom those about her |
| Access | `svc-hr-policy`: the policy folder only |
| Logging | Answered: 30 days, read by Owen and the IT provider. Handed off: ID and outcome; text to Aisha only |
| Kill switch | Aisha sets the stop flag (Chapter 3) or Owen unpublishes; a pinned message sends questions to Aisha |

Check local rules on consulting staff before logging; Example 9.1 is Aisha's pinned notice.

## What employees are told

Example 9.1 from the book, Aisha's pinned notice.
Write your own with your names, log, readers and regions, and reissue it when the tool, the log or its readers change.

> This assistant answers what Northstar's written policies say, linking the policy it quotes.
> It reads only the policy folder, never your personnel record, and does not answer about your own pay, health, leave, performance or a complaint; those go to Aisha Karim, or Tom Rivera if they concern Aisha.
> If it ever answers one, tell Aisha.
> Answered questions are kept 30 days in a restricted log that Owen Clarke and our IT provider's engineer can read; for questions sent to HR, only a reference and outcome.
> Our automation platform, n8n, runs in Frankfurt; our AI provider, Anthropic, processes your question in the US.
> If the tool, the log or its readers change, we will reissue this notice.

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
