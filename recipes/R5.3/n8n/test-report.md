# R5.3 n8n build: golden-set run

Run 2026-10-28 on n8n 2.42.7 (self-hosted), against the companion's mock systems (`tools/mock-systems/`).
Result: 11 of 11 cases passed.

| Case | Input | Result | Checked |
|---|---|---|---|
| Normal | Three-line quote | Pass | crm/quotes: 1 records; crm/quotes/1.total = 35101.2; crm/quotes/1.price_list_version = "PL-2026-10"; crm/quotes/1.status = "awaiting approval"; select rules->>'check' from decision_log where recipe='R5.3' -> passed |
| Edge | Unrounded sum differs from rounded lines | Pass | select rules->>'total' from decision_log where recipe='R5.3' -> 52.29 |
| Duplicate | "Ready to quote" clicked twice | Pass | GET /crm/opportunities/OPP-1: 1 call(s); select copies_skipped from key_log where recipe='R5.3' -> 1; select count(*) from decision_log where recipe='R5.3' -> 1 |
| Refuse | Incident D's price in the AI's text, as digits, then words | Pass | crm/quotes: 0 records; crm/opportunities/OPP-1.quote_flag = "No draft: number no placeholder supplied: 185; number in words: one, five, eighty, hundred"; crm/opportunities/OPP-1.quote_flag = "No draft: number no placeholder supplied: 185; number in words: one, five, eighty, hundred"; select reason from exception_queue where recipe='R5.3' -> no draft |
| Stale price list | Price list valid until yesterday (companion extension) | Pass | POST /anthropic/v1/messages: 0 call(s); crm/quotes: 0 records; messaging/messages: 1 records; messaging/messages/1.to = ["ben@example.test", "aisha@example.test"]; select count(*) from key_log where recipe='R5.3' -> 0 |
| Off-list code | A line whose code is not on the price list (companion extension) | Pass | select owner from exception_queue where recipe='R5.3' and reason='off-list line' -> ben@example.test; select rules->>'total' from decision_log where recipe='R5.3' -> 9900; select rules->>'off_list_lines' from decision_log where recipe='R5.3' -> [2] |
| AI error | The AI call fails twice (companion extension) | Pass | POST /anthropic/v1/messages: 2 call(s); crm/quotes: 0 records; crm/opportunities/OPP-1.quote_flag = "No draft: AI error after one retry: The service failed to process your request"; select reason from exception_queue where recipe='R5.3' -> no draft; select detail like 'AI error after one retry%' from exception_queue where recipe='R5.3' -> t |
| CRM read fails | The opportunity read fails three times (companion extension) | Pass | GET /crm/opportunities/OPP-1: 3 call(s); POST /anthropic/v1/messages: 0 call(s); select status from key_log where recipe='R5.3' -> failed; select reason from exception_queue where recipe='R5.3' -> write or read failed |
| Write fails | The opportunity flag write fails (companion extension) | Pass | PATCH /crm/opportunities/OPP-1: 1 call(s); select status from key_log where recipe='R5.3' -> failed; select reason from exception_queue where recipe='R5.3' -> write or read failed |
| Expiry warning | Price list expires in five days (companion extension) | Pass | messaging/messages: 1 records; messaging/messages/1.to = "aisha@example.test" |
| Stop flag | The stop flag is set (companion extension) | Pass | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
