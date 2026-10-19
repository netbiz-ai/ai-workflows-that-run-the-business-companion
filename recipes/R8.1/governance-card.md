# Governance card: R8.1 Send staged overdue reminders that stop on payment or dispute

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Workflow: R8.1 overdue reminders. Owner: Aisha Karim. Review date: annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential: contacts and amounts. Hosting: Northstar's Power Platform environment, in its Microsoft 365 tenant's region. No AI |
| Approver | Aisha approved the workflow and templates, and approves every final notice; Helen Brandt, Owner and CEO, when Aisha is away |
| Access | `svc-ar-reminders`: read the export, lists and CRM; write the reminder list and logs; send from the AR mailbox |
| Logging | Invoice, stage, sent or stopped, reason, template version: 13 months. Final-notice approvals: as the accountant requires |
| Kill switch | Aisha sets the stop flag (Chapter 3) or Owen turns the flow off; nothing sends, and finance chases from the export |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
