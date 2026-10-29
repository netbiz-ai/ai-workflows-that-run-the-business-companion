# R4.1 n8n build: golden-set run

Run 2026-10-28 on n8n 2.42.7 (self-hosted), against the companion's mock systems (`tools/mock-systems/`).
Result: 8 of 8 cases passed.

| Case | Input | Result | Checked |
|---|---|---|---|
| Normal | "When is my sofa arriving? Order 4417" | Pass | helpdesk/tickets/T-1.queue = "Delivery"; select count(*) from exception_queue -> 0 |
| Edge | Return complaining about the driver | Pass | helpdesk/tickets/T-1.queue = "Manual triage" |
| Duplicate | Same message ID twice | Pass | PATCH /helpdesk/tickets/T-1: 1 call(s); select copies_skipped from key_log where recipe='R4.1' -> 1 |
| Escalate | Uncovered language | Pass | helpdesk/tickets/T-1.queue = "Manual triage"; select reason from exception_queue where recipe='R4.1' -> needs manual triage |
| Automatic sender | An out-of-office reply (companion extension) | Pass | helpdesk/tickets/T-1.queue = "Low priority"; POST /anthropic/v1/messages: 0 call(s) |
| AI error | The AI call fails twice (companion extension) | Pass | helpdesk/tickets/T-1.queue = "Manual triage"; POST /anthropic/v1/messages: 2 call(s); select reason from exception_queue where recipe='R4.1' -> needs manual triage |
| Write fails | The routing write fails (companion extension) | Pass | PATCH /helpdesk/tickets/T-1: 1 call(s); select status from key_log where recipe='R4.1' -> failed; select reason from exception_queue where recipe='R4.1' -> write failed |
| Stop flag | The stop flag is set (companion extension) | Pass | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
