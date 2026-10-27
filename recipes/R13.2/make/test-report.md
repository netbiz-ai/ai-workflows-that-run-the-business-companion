# R13.2 Make build: golden-set run

Run 2026-10-26 on Make (cloud service, Core plan, us2.make.com), against the companion's mock systems (`tools/mock-systems/`).
Result: 13 of 13 cases passed.
Make credits used by the whole set: 189.

| Case | Input | Result | Credits | Checked |
|---|---|---|---|---|
| Normal | Delivery guide 10 days before review | Pass | 15 | messaging/messages: 1 records; messaging/messages/1.to = "tom@example.test"; messaging/messages/1.text = "Delivery and installation guide is due for review on 2026-11-05. It is withdrawn from answers on 2026-12-05 unless you renew, replace or retire it: https://forms.example.test/owner"; sharepoint/sources/S-DELIV.status = "current"; select status from key_log where recipe='R13.2' -> done; select decision from decision_log where recipe='R13.2' and item='S-DELIV' -> remind |
| Edge | New source without a review date | Pass | 16 | sharepoint/sources/S-NEW.status = "withdrawn"; sharepoint/sources/S-NEW.withdrawn_reason = "no review date"; messaging/messages: 1 records; messaging/messages/1.to = "owen@example.test"; POST /index/rebuilds: 0 call(s) |
| Duplicate | Weekly run fires twice | Pass | 27 | messaging/messages: 1 records; select copies_skipped from key_log where recipe='R13.2' -> 1; select count(*) from decision_log where recipe='R13.2' and decision='remind' -> 1 |
| Refuse | Last year's expense policy, past expiry | Pass | 17 | sharepoint/sources/S-EXP.status = "withdrawn"; documents/files/F-EXP.folder = "archive"; messaging/messages: 1 records; messaging/messages/1.to = "aisha@example.test"; messaging/messages/1.cc = "owen@example.test"; select decision from decision_log where recipe='R13.2' and item='S-EXP' -> withdraw_expired |
| Escalate | Owner has left | Pass | 16 | select reason || ' / ' || owner from exception_queue where recipe='R13.2' -> owner left / owen@example.test; messaging/messages: 1 records; messaging/messages/1.to = "owen@example.test"; sharepoint/sources/S-VEH.status = "current" |
| Vacation | Owner on vacation, review due (companion extension) | Pass | 15 | messaging/messages: 1 records; messaging/messages/1.to = "aisha-delegate@example.test" |
| Two actions | One source past expiry and another due, in one run (companion extension) | Pass | 21 | messaging/messages: 2 records; sharepoint/sources/S-VEH.status = "withdrawn"; documents/files/F-VEH.folder = "archive"; sharepoint/sources/S-EXP.status = "current"; select count(*) from key_log where recipe='R13.2' and status='done' -> 2; select count(*) from decision_log where recipe='R13.2' -> 3 |
| Index rebuild failed | Index still holds the previous major version (companion extension) | Pass | 16 | select reason || ' / ' || owner from exception_queue where recipe='R13.2' -> register mismatch / owen@example.test; select detail from exception_queue where recipe='R13.2' -> Vehicle rule: register version 2.0, index 1.0; messaging/messages: 1 records |
| Audience differs from sharing | Expense policy folder narrowed to finance (companion extension) | Pass | 16 | select detail from exception_queue where recipe='R13.2' -> Expense policy: audience differs from sharing; messaging/messages/1.to = "owen@example.test" |
| Major version | Vehicle rule publishes version 3.0 (companion extension) | Pass | 8 | POST /index/rebuilds: 1 call(s); index/rebuilds/1.source_id = "S-VEH"; select decision from decision_log where recipe='R13.2' -> rebuild passages |
| Minor version | Vehicle rule publishes version 2.1 (companion extension) | Pass | 4 | POST /index/rebuilds: 0 call(s); select count(*) from key_log where recipe='R13.2' -> 0 |
| Write fails | The withdrawal write fails (companion extension) | Pass | 15 | PATCH /sharepoint/sources/S-EXP: 1 call(s); PATCH /documents/files/F-EXP: 0 call(s); select status from key_log where recipe='R13.2' -> failed; select reason from exception_queue where recipe='R13.2' -> write failed |
| Stop flag | The stop flag is set (companion extension) | Pass | 3 | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
