# Governance card: R12.3 Alert the owner when a measure crosses its threshold

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Owner: Tom Rivera; review date: annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential: weekly totals only. Hosting: Northstar's Power Platform environment, in its Microsoft 365 tenant's region. No AI processing |
| Approver | Each measure owner sets their line; Tom approves it; Helen approves Tom's own lines |
| Access | `svc-weekly-alerts`: read the table and list; post to owners; write the log. Owen alone edits the list |
| Logging | Measure, value, line version, outcome, alert sent or suppressed: 13 months |
| Kill switch | Tom sets the stop flag (Chapter 3), or Owen unpublishes; owners read their lines in the pre-read |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
