# Governance card: R9.4 Remove a leaver's access the same day

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Workflow: R9.4 leaver access removal. Owner: Aisha Karim; built by Owen. Review date: annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential: name, accounts, last day. Hosting: as R9.1. No AI |
| Approver | Aisha confirms each leaver and approves workflow changes; Owen checks evidence and closes cases |
| Access | `svc-leavers`: disable staff accounts and end their sessions; remove users from the inventory's connected apps; no deletion |
| Logging | Each removal, by whom, when: 13 months; other HR records follow Aisha's policy |
| Kill switch | Aisha sets the stop flag (Chapter 3), or Owen or the IT provider turns it off; open cases continue by hand |

`svc-leavers` is set up like `svc-onboarding`, with only these rights.

"As R9.1" is R9.1's hosting: Northstar's Power Platform environment, in its tenant's region; `svc-onboarding` is described on the same card (see [`../R9.1/governance-card.md`](../R9.1/governance-card.md)).

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
