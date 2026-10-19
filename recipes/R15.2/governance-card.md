# Governance card: R15.2 Check delivery and installation capacity before a promotion launches

Northstar's filled card from the book.
Northstar is fictional; copy the structure, not the entries.

Owner: Tom Rivera; review date: annual library review (Chapter 18).

| Field | Entry |
|---|---|
| Data class | Internal: forecasts and counts. Hosting: Northstar's Power Platform environment, in its Microsoft 365 tenant's region. No AI |
| Approver | Tom decides what the rule cannot read; Ben agrees date changes and checks clearance before each wave |
| Access | `svc-promo-capacity`: reads briefs and slots; writes capacity status |
| Logging | Each check's inputs and result: 13 months |
| Kill switch | Owen turns it off, or Tom sets the stop flag (Chapter 3); status reads "manual check" and Tom signs capacity by hand |

## Fill your own

Start from [`governance/governance-card.md`](../../governance/governance-card.md).
A card is complete only when every field names a person, an account, a place or a period; no go-live without it (book Chapter 3).
