# R7.4 n8n build: golden-set run

Run 2026-10-28 on n8n 2.42.7 (self-hosted), against the companion's mock systems (`tools/mock-systems/`).
Result: 11 of 11 cases passed.

| Case | Input | Result | Checked |
|---|---|---|---|
| Normal | Quantity mismatch | Pass | queue/items/Q-1.owner = "tom@example.test"; teams/messages/1.to = "tom@example.test"; teams/messages/1.draft_check = "passed" |
| Edge | Unknown reason code | Pass | queue/items/Q-1.owner = "aisha@example.test"; teams/messages/1.to = "aisha@example.test"; POST /anthropic/v1/messages: 0 call(s) |
| Duplicate | Same invoice and reason twice | Pass | teams/messages: 1 records; queue/items/Q-1.status = "open"; queue/items/Q-1.notes = [{"on": "2026-10-28", "from_item": "Q-2", "raised_by": "R7.2", "details": "supplier held by R7.3, raised again"}]; queue/items/Q-2.status = "merged"; select copies_skipped from key_log where recipe='R7.4' -> 1 |
| Refuse | Draft says "we will pay on Friday" | Pass | teams/messages/1.draft = null; teams/messages/1.draft_check = "dropped: banned word pay"; queue/items/Q-1.status = "open"; queue/items/Q-1.owner = "tom@example.test" |
| AI error | The AI call fails three times (companion extension) | Pass | POST /anthropic/v1/messages: 3 call(s); teams/messages/1.to = "tom@example.test"; teams/messages/1.draft = null; queue/items/Q-1.status = "open" |
| Morning list | Two items past the aging limit, one new (companion extension) | Pass | teams/messages/1.to = "aisha@example.test"; teams/messages/1.items = ["Q-2", "Q-1"] |
| Write fails | The Teams post fails (companion extension) | Pass | POST /teams/messages: 1 call(s); select reason from exception_queue where recipe='R7.4' -> write failed; select status from key_log where recipe='R7.4' -> failed |
| Resolved above the limit | Tom resolves a $12,000 item (companion extension) | Pass | approvals/approvals/R-1.approver = "helen@example.test"; approvals/approvals/R-1.note = "Supplier confirmed two units are on back order."; queue/items/Q-1.status = "closed" |
| Rematch | Closed with a corrected record (companion extension) | Pass | POST /n8n/rematch: 1 call(s); approvals/approvals: 0 records; queue/items/Q-1.status = "closed" |
| Refuse, live model | The item asks for "we will pay on Friday", sent to the live model (companion extension) | Pass | teams/messages/1.draft_check = "passed"; queue/items/Q-1.status = "open"; queue/items/Q-1.owner = "tom@example.test" |
| Stop flag | The stop flag is set (companion extension) | Pass | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
