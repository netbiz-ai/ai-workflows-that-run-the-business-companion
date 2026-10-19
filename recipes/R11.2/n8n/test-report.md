# R11.2 n8n build: golden-set run

Run 2026-10-19 on n8n 2.42.7 (self-hosted), against the companion's mock systems (`tools/mock-systems/`).
Result: 8 of 8 cases passed.

| Case | Input | Result | Checked |
|---|---|---|---|
| Normal | $2,400, checked row, quote valid 20 days | Pass | sharepoint/requests/REQ-1.status = "checked; to approval"; sharepoint/requests/REQ-1.total = 2400; select status from key_log where recipe='R11.2' -> done; select count(*) from decision_log where recipe='R11.2' -> 1 |
| Edge | Quote valid until tomorrow | Pass | sharepoint/requests/REQ-1.status = "blocked"; sharepoint/requests/REQ-1.reasons = ["expires within margin"]; messaging/messages: 1 records |
| Duplicate | Status write, version unchanged | Pass | PATCH /sharepoint/requests/REQ-1: 1 call(s); select copies_skipped from key_log where recipe='R11.2' -> 1; select count(*) from decision_log where recipe='R11.2' -> 1 |
| Refuse | Supplier on R7.3 hold | Pass | sharepoint/requests/REQ-1.status = "blocked"; sharepoint/requests/REQ-1.reasons = ["supplier on hold"] |
| Escalate | Two $450 requests, same supplier, three days apart | Pass | sharepoint/requests/REQ-1.status = "checked; to approval"; sharepoint/requests/REQ-1.total = 900 |
| Failure | Status write fails (companion extension) | Pass | PATCH /sharepoint/requests/REQ-1: 1 call(s); select status from key_log where recipe='R11.2' -> failed; select reason from exception_queue where recipe='R11.2' -> write failed |
| Backstop | A $1,200 PO with no approved request (companion extension) | Pass | select reason from exception_queue where recipe='R11.2' -> PO without approved request; messaging/messages: 1 records |
| Stop flag | The stop flag is set (companion extension) | Pass | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
