# R6.1 Make build: golden-set run

Run 2026-10-30 on Make (cloud service, Core plan, us2.make.com), against the companion's mock systems (`tools/mock-systems/`).
Result: 12 of 12 cases passed.
Make credits used by the whole set: 268.

| Case | Input | Result | Credits | Checked |
|---|---|---|---|---|
| Normal | Reply about one open quote | Pass | 27 | crm/activities/1.deal_id = "D-1"; crm/activities/1.link = "https://mail.example.test/items/M-1"; crm/activities/1.summary = null; crm/accounts/A-1.last_contact = "2026-10-30"; crm/drafts/2.status = "waiting for owner"; crm/drafts/2.owner = "ben@northstar.example.test"; crm/drafts/2.ai_chosen_deal = false; select count(*) from exception_queue where recipe='R6.1' -> 0; select decision from decision_log where recipe='R6.1' -> logged to deal D-1 |
| Edge | Two open deals; email fits either | Pass | 25 | select count(*) from exception_queue where recipe='R6.1' and reason='unmatched' and detail like 'deal unclear%' -> 1; POST /crm/activities: 0 call(s); POST /crm/drafts: 0 call(s) |
| Duplicate | Same email in two mailboxes | Pass | 35 | GET /mail/messages/M-1: 1 call(s); GET /mail/messages/M-2: 1 call(s); select copies_skipped from key_log where recipe='R6.1' -> 1; GET /crm/contacts: 1 call(s); select count(*) from decision_log where recipe='R6.1' -> 1 |
| Escalate | Manager's address on two accounts | Pass | 16 | select detail from exception_queue where recipe='R6.1' and reason='unmatched' -> several accounts match: A-1, A-2; POST /crm/activities: 0 call(s); PATCH /crm/accounts/A-1: 0 call(s); POST /crm/drafts: 0 call(s); POST /anthropic/v1/messages: 0 call(s) |
| Refuse | Colleague's lunch email, marked by mistake | Pass | 12 | GET /crm/contacts: 0 call(s); POST /anthropic/v1/messages: 0 call(s); POST /crm/activities: 0 call(s); select count(*) from exception_queue where recipe='R6.1' -> 0; select decision from decision_log where recipe='R6.1' -> not logged: never-log listed |
| Several recipients | A sent email to two external recipients (companion extension) | Pass | 13 | select detail from exception_queue where recipe='R6.1' and reason='unmatched' -> several external recipients: 2 external recipients; GET /crm/contacts: 0 call(s); POST /crm/activities: 0 call(s) |
| AI error | The AI call fails on every try (companion extension) | Pass | 27 | POST /anthropic/v1/messages: 3 call(s); select count(*) from exception_queue where recipe='R6.1' and reason='unmatched' and detail like 'AI error%' -> 1; POST /crm/activities: 0 call(s); select status from key_log where recipe='R6.1' -> done |
| Write fails | The CRM activity write fails, given a valid summary (companion extension) | Pass | 25 | POST /crm/activities: 1 call(s); POST /crm/drafts: 0 call(s); select status from key_log where recipe='R6.1' -> failed; select reason from exception_queue where recipe='R6.1' -> write failed |
| Meeting note | A meeting note for an account with no open deal (companion extension) | Pass | 27 | crm/activities/1.type = "meeting note"; crm/activities/1.deal_id = null; crm/drafts/2.deal_id = null; select decision from decision_log where recipe='R6.1' -> logged at account level |
| Deal not open | The AI names a deal that is not open on the account (companion extension) | Pass | 30 | select detail from exception_queue where recipe='R6.1' and reason='unmatched' -> deal not open on this account: the AI named D-0; POST /crm/activities: 0 call(s); POST /crm/drafts: 0 call(s) |
| Past date | The AI returns a next-step date in the past (companion extension) | Pass | 27 | crm/activities/1.deal_id = "D-1"; crm/drafts/2.summary = "The customer confirmed they will call back about the lobby bar stools."; crm/drafts/2.next_step_date = null; select rules->>'date' from decision_log where recipe='R6.1' -> dropped: past |
| Stop flag | The stop flag is set (companion extension) | Pass | 4 | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
