# R5.1 Make build: golden-set run

Run 2026-10-30 on Make (cloud service, Core plan, us2.make.com), against the companion's mock systems (`tools/mock-systems/`).
Result: 10 of 10 cases passed.
Make credits used by the whole set: 209.

| Case | Input | Result | Credits | Checked |
|---|---|---|---|---|
| Normal | Property manager's web form | Pass | 21 | crm/leads: 1 records; crm/leads/1.status = "new, unassigned"; crm/leads/1.source_id = "SUB-1"; crm/leads/1.phone = "5550142"; crm/attachments: 1 records; POST /anthropic/v1/messages: 0 call(s); select decision from decision_log where recipe='R5.1' -> new lead; select count(*) from exception_queue where recipe='R5.1' -> 0 |
| Duplicate | Same form twice | Pass | 28 | crm/leads: 1 records; POST /crm/leads: 1 call(s); select copies_skipped from key_log where recipe='R5.1' -> 1 |
| Edge | Sunday form, Monday email, same address | Pass | 45 | crm/leads: 1 records; crm/activities: 1 records; crm/activities/3.source_id = "MSG-1"; crm/activities/3.lead_id = "1" |
| Escalate | Two records share the email | Pass | 19 | select reason from exception_queue where recipe='R5.1' -> CRM match unclear; select owner from exception_queue where recipe='R5.1' -> ben@example.test; crm/leads: 2 records; crm/activities: 0 records |
| Refuse | "Please put us on your supplier list" | Pass | 23 | crm/leads: 0 records; crm/activities: 0 records; messaging/messages: 1 records; messaging/messages/1.to = "shared-inbox@example.test" |
| Incomplete | A web form with no email or phone (companion extension) | Pass | 14 | select reason from exception_queue where recipe='R5.1' -> incomplete inquiry; select owner from exception_queue where recipe='R5.1' -> queue-checker@example.test; select detail from exception_queue where recipe='R5.1' -> Missing or malformed: email or phone; crm/leads: 0 records; GET /crm/leads: 0 call(s) |
| Company name only | A web form whose only CRM match is the company name (companion extension) | Pass | 19 | select reason from exception_queue where recipe='R5.1' -> CRM match unclear; crm/leads: 1 records; crm/activities: 0 records |
| AI error | The AI call fails twice (companion extension) | Pass | 19 | POST /anthropic/v1/messages: 2 call(s); select reason from exception_queue where recipe='R5.1' -> incomplete inquiry; select detail like 'AI error after one retry%' from exception_queue where recipe='R5.1' -> t; crm/leads: 0 records; messaging/messages: 0 records |
| CRM write fails | The lead create fails (companion extension) | Pass | 17 | POST /crm/leads: 1 call(s); select status from key_log where recipe='R5.1' -> failed; select reason from exception_queue where recipe='R5.1' -> write failed; select owner from exception_queue where recipe='R5.1' -> ben@example.test |
| Stop flag | The stop flag is set (companion extension) | Pass | 4 | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
