# R7.2 n8n build: golden-set run

Run 2026-10-28 on n8n 2.42.7 (self-hosted), against the companion's mock systems (`tools/mock-systems/`).
Result: 13 of 13 cases passed.

| Case | Input | Result | Checked |
|---|---|---|---|
| Normal | Every line matches | Pass | approvals/approvals/R-1.approver = "aisha@example.test"; review/records/R-1.match_status = "matched; to approval"; reservations/reservations: 2 records; reservations/reservations/R-1:L1.qty = 10; queue/items: 0 records; POST /anthropic/v1/messages: 0 call(s) |
| Edge | Twelve billed, ten received | Pass | review/records/R-1.match_status = "stopped"; queue/items/1.reason_code = "outside tolerance"; queue/items/1.details = "line 1 \"Base cabinet 60\": over receipt, 12 billed, 10 received"; approvals/approvals: 0 records; reservations/reservations: 0 records |
| Duplicate | Two invoices for the same goods | Pass | approvals/approvals: 1 records; approvals/approvals/R-1.approver = "aisha@example.test"; review/records/R-2.match_status = "stopped"; queue/items/1.invoice_id = "R-2"; queue/items/1.reason_code = "already invoiced" |
| Escalate | $12,000 invoice on an order Tom raised | Pass | approvals/approvals/R-1.approver = "helen@example.test"; approvals/approvals/R-1.total = 12000 |
| Supplier held | R7.3 holds the supplier (companion extension) | Pass | queue/items/1.reason_code = "supplier on hold"; review/records/R-1.match_status = "stopped"; GET /ledger/orders: 0 call(s); approvals/approvals: 0 records |
| No receipt | Receipt not entered (companion extension) | Pass | queue/items/1.reason_code = "no receipt"; approvals/approvals: 0 records |
| Lookup error | The PO lookup fails three times (companion extension) | Pass | GET /ledger/orders: 3 call(s); queue/items/1.reason_code = "lookup error"; review/records/R-1.match_status = "stopped"; approvals/approvals: 0 records |
| AI error | An unmapped line; the AI call fails three times (companion extension) | Pass | POST /anthropic/v1/messages: 3 call(s); queue/items/1.reason_code = "pairing rejected"; queue/items/1.details = "line 2 \"Wall unit 40\": AI error, no pairing proposed"; approvals/approvals: 0 records; reservations/reservations: 0 records |
| Reservation fails partway | The second line's reservation write fails (companion extension) | Pass | PUT /reservations/reservations/R-1:L2: 1 call(s); DELETE /reservations/reservations/R-1:L1: 1 call(s); reservations/reservations: 0 records; queue/items/1.reason_code = "reservation failed"; approvals/approvals: 0 records |
| Rejected | The approver rejects the invoice (companion extension) | Pass | reservations/reservations: 0 records; approvals/approvals/R-1.status = "rejected"; select approved_by || ': ' || decision from decision_log where recipe='R7.2' -> aisha@example.test: approval rejected |
| Write fails | The approval write fails (companion extension) | Pass | PUT /approvals/approvals/R-1: 1 call(s); select reason from exception_queue where recipe='R7.2' -> write failed; select owner from exception_queue where recipe='R7.2' -> owen@example.test |
| AI-paired line | A line the map does not cover, paired by the AI (companion extension) | Pass | approvals/approvals/R-1.approver = "aisha@example.test"; approvals/approvals/R-1.lines = [{"invoice_line": 1, "description": "Base cabinet 60", "order_line_id": "L1", "qty": 10, "ai_paired": false}, {"invoice_line": 2, "description": "Wall unit 40", "order_line_id": "L2", "qty": 5, "ai_paired": true}]; reservations/reservations/R-1:L2.qty = 5 |
| Stop flag | The stop flag is set (companion extension) | Pass | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
