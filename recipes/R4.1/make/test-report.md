# R4.1 Make build: golden-set run

Run 2026-10-27 on Make (cloud service, Core plan, us2.make.com), against the companion's mock systems (`tools/mock-systems/`).
Result: 8 of 8 cases passed.
Make credits used by the whole set: 122.

| Case | Input | Result | Credits | Checked |
|---|---|---|---|---|
| Normal | "When is my sofa arriving? Order 4417" | Pass | 16 | helpdesk/tickets/T-1.queue = "Delivery"; select count(*) from exception_queue -> 0 |
| Edge | Return complaining about the driver | Pass | 17 | helpdesk/tickets/T-1.queue = "Manual triage" |
| Duplicate | Same message ID twice | Pass | 22 | PATCH /helpdesk/tickets/T-1: 1 call(s); select copies_skipped from key_log where recipe='R4.1' -> 1 |
| Escalate | Uncovered language | Pass | 17 | helpdesk/tickets/T-1.queue = "Manual triage"; select reason from exception_queue where recipe='R4.1' -> needs manual triage |
| Automatic sender | An out-of-office reply (companion extension) | Pass | 11 | helpdesk/tickets/T-1.queue = "Low priority"; POST /anthropic/v1/messages: 0 call(s) |
| AI error | The AI call fails twice (companion extension) | Pass | 18 | helpdesk/tickets/T-1.queue = "Manual triage"; POST /anthropic/v1/messages: 2 call(s); select reason from exception_queue where recipe='R4.1' -> needs manual triage |
| Write fails | The routing write fails (companion extension) | Pass | 17 | PATCH /helpdesk/tickets/T-1: 1 call(s); select status from key_log where recipe='R4.1' -> failed; select reason from exception_queue where recipe='R4.1' -> write failed |
| Stop flag | The stop flag is set (companion extension) | Pass | 4 | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
