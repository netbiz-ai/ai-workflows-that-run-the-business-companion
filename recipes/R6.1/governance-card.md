# Governance card: R6.1 Log emails and meeting notes to the right account and deal

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Workflow: R6.1 activity logging. Owner: Ben Hollis. Review date: the annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential: marked emails, meeting notes. Hosting: Northstar's Power Platform environment, in its Microsoft 365 tenant's region. AI processing: the same region while "Move data across regions" and EU flex routing are off, as of October 2026 |
| Approver | Ben, for the workflow and never-log list; owners accept summaries |
| Access | `svc-crm-log`: read the "CRM" folders and notes, granted folder by folder where the mail system allows, otherwise the wider grant recorded here and reviewed monthly; write activities, drafts, last-contact date. Flow owner `svc-flow-owner`. Editors: Owen, IT provider |
| Logging | Message ID, account, deal, result; never the body. SharePoint, 13 months (Chapter 3 default) |
| Kill switch | Ben sets the stop flag (Chapter 3), or Owen turns the flow off; marked items wait in their folders, and on restart a catch-up run skips logged items |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
