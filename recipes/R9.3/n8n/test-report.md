# R9.3 n8n build: golden-set run

Run 2026-10-19 on n8n 2.42.7 (self-hosted), against the companion's mock systems (`tools/mock-systems/`).
Result: 10 of 10 cases passed.

| Case | Input | Result | Checked |
|---|---|---|---|
| Normal | Three days, balance ten | Pass | leave/requests/R-1.status = "approved"; leave/requests/R-1.days = 3; leave/requests/R-1.warnings = []; torecord/items: 1 records; POST /messaging/messages: 2 call(s); select string_agg(decision, ', ' order by id) from decision_log where recipe='R9.3' -> to the manager, approved; select status || ' / ' || result from key_log where recipe='R9.3' -> done / closed: approved |
| Edge | Two open requests over the balance | Pass | leave/requests/R-1.warnings = []; leave/requests/R-2.status = "with manager"; leave/requests/R-2.warnings = ["balance less open requests (4) does not cover 5 days"]; POST /messaging/messages: 2 call(s) |
| Duplicate | Submitted twice | Pass | leave/requests: 1 records; POST /messaging/messages: 1 call(s); select copies_skipped from key_log where recipe='R9.3' -> 1 |
| Escalate | Family leave | Pass | leave/requests/R-1.status = "with HR"; leave/requests/R-1.decider = "aisha@example.test"; POST /messaging/messages: 1 call(s); GET /balances/balances: 0 call(s); select decision from decision_log where recipe='R9.3' -> to HR alone |
| Balance export missing | Today's balance is not in the export (companion extension) | Pass | leave/requests/R-1.status = "with manager"; leave/requests/R-1.warnings = ["balance not checked"]; POST /messaging/messages: 1 call(s) |
| Employee notice fails | The decision is made and the notice fails (companion extension) | Pass | leave/requests/R-1.status = "approved"; torecord/items: 1 records; POST /messaging/messages: 1 call(s); select reason || ' / ' || owner from exception_queue where recipe='R9.3' -> employee notice failed / aisha@example.test |
| Manager silent | No decision after 4 working days (companion extension) | Pass | leave/requests/R-1.status = "with stand-in"; leave/requests/R-1.decider = "tom@example.test"; POST /messaging/messages: 2 call(s) |
| Unlisted requester | A requester not on the employee list (companion extension) | Pass | leave/requests: 0 records; POST /messaging/messages: 1 call(s); select reason || ' / ' || owner from exception_queue where recipe='R9.3' -> unlisted requester / aisha@example.test |
| Cancellation | An approved request is cancelled (companion extension) | Pass | leave/requests/R-1.status = "cancelled"; POST /messaging/messages: 2 call(s); select decision from decision_log where recipe='R9.3' -> cancelled |
| Stop flag | The stop flag is set (companion extension) | Pass | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
