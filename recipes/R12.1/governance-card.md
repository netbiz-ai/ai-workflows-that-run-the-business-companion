# Governance card: R12.1 Pull the weekly figures from source systems into one dated table

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Owner: Tom Rivera; builder: Owen Clarke; review date: annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential: receivables, margins, names, HR data. Hosting: Northstar's Power Platform environment, in its Microsoft 365 tenant's region. No AI |
| Approver | Aisha approves every rule; each measure's owner signs their entry; Helen approved the workflow |
| Access | `svc-weekly-numbers`: read source libraries; write the table, snapshots and log. Editors: Owen, the IT provider's engineer |
| Logging | Each file's name, time, row count and control total; each figure as printed; rule versions: 13 months |
| Kill switch | Tom sets the stop flag (Chapter 3) or Owen unpublishes; Tom builds that week's table by hand |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
