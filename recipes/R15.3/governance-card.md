# Governance card: R15.3 Keep consent and unsubscribes in sync across every list

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Owner: Ben Hollis; builder: Owen Clarke; review date: annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Confidential: contacts and consent. Hosting: Northstar's Power Platform environment, in its Microsoft 365 tenant's region. No AI |
| Approver | None per event; the adviser set the rules; Ben approves every change to the workflow |
| Access | `svc-consent-sync`: writes consent, suppressions and send status only |
| Logging | Consent proof and opt-outs: as long as Northstar's outside legal adviser requires. Decision logs and failures: 13 months |
| Kill switch | Owen turns it off, or Helen sets the stop flag (Chapter 3); whoever does, or Owen on a heartbeat alert, marks every list "paused" within an hour |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).

Consent rules are law, not preference.
Before the first sync, have your outside legal adviser set the proof an opt-in needs, which channels an opt-out covers, and how long proof is kept, and record them on the card (book Chapter 15).
