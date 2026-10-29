# R6.3 n8n build: golden-set run

Run 2026-10-28 on n8n 2.42.7 (self-hosted), against the companion's mock systems (`tools/mock-systems/`).
Result: 13 of 13 cases passed.

| Case | Input | Result | Checked |
|---|---|---|---|
| Normal | Same phone, name with and without "LLC" | Pass | queue/pairs/A-1:A-2.signals = ["phone", "name"]; queue/pairs/A-1:A-2.reason_check = "passed"; queue/pairs/A-1:A-2.status = "waiting"; queue/pairs: 1 records |
| Edge | Managed owner accounts sharing the firm's phone, rejected; later one phone changes | Pass | queue/pairs: 1 records; queue/pairs/E-3:E-4.status = "waiting"; queue/pairs/E-1:E-2.status = null; select rules->>'suppression' from decision_log where recipe='R6.3' and item='E-3:E-4' -> lifted: a signal field changed |
| Duplicate | Pair already in the queue | Pass | POST /queue/pairs: 1 call(s); select copies_skipped from key_log where recipe='R6.3' and key='A-1:A-2' -> 1; select count(*) from decision_log where recipe='R6.3' -> 1 |
| Escalate | Open quote, or credit terms | Pass | queue/pairs/A-1:A-2.confirm_first = ["Ben confirms first"]; queue/pairs/B-1:B-2.confirm_first = ["Aisha confirms first"]; queue/pairs/B-1:B-2.signals = ["tax_id"] |
| Refuse | Unrelated accounts on one webmail domain | Pass | POST /queue/pairs: 0 call(s); POST /anthropic/v1/messages: 0 call(s); select count(*) from key_log where recipe='R6.3' -> 0 |
| AI error | The AI call fails on every try (companion extension) | Pass | POST /anthropic/v1/messages: 3 call(s); queue/pairs/A-1:A-2.reason = null; queue/pairs/A-1:A-2.reason_check = "AI error after three retries"; queue/pairs/A-1:A-2.signals = ["phone", "name"] |
| Export fails | The account export fails (companion extension) | Pass | GET /crm-export/accounts: 3 call(s); select reason || ' / ' || split_part(detail, ':', 1) from exception_queue where recipe='R6.3' -> export check failed / export failed; messaging/messages: 1 records; POST /queue/pairs: 0 call(s) |
| Export short | The export shrinks sharply (companion extension) | Pass | select detail from exception_queue where recipe='R6.3' and reason='export check failed' -> export shrank: 2 accounts, expected about 4; messaging/messages: 1 records; GET /queue/suppressions: 0 call(s); POST /queue/pairs: 0 call(s) |
| Export changed | The export changes format (companion extension) | Pass | select count(*) from exception_queue where recipe='R6.3' and detail like 'export changed format: 3 account record(s)%' -> 1; messaging/messages: 1 records; POST /queue/pairs: 0 call(s) |
| Queue write fails | The queue write fails (companion extension) | Pass | POST /queue/pairs: 1 call(s); select status from key_log where recipe='R6.3' -> failed; select reason from exception_queue where recipe='R6.3' -> write failed |
| Rejection | The merger rejects a queued pair; the next weekly run (companion extension) | Pass | POST /queue/pairs: 1 call(s); queue/suppressions/A-1:A-2.rejected_by = "Owen Clarke"; select count(*) from decision_log where recipe='R6.3' and decision='reject by Owen Clarke' -> 1; select count(*) from key_log where recipe='R6.3' -> 0 |
| Reason names another field | The AI's reason names a field that did not match (companion extension) | Pass | queue/pairs/A-1:A-2.reason = null; queue/pairs/A-1:A-2.reason_check = "dropped: names address"; queue/pairs/A-1:A-2.signals = ["phone", "name"] |
| Stop flag | The stop flag is set (companion extension) | Pass | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
