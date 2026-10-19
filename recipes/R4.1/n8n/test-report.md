# R4.1 n8n build: golden-set run

Run 2026-10-19 on n8n 2.42.7 (self-hosted), against the companion's mock systems (`tools/mock-systems/`).
Result: 4 of 7 cases passed; 3 not run until the AI key is installed.

| Case | Input | Result | Checked |
|---|---|---|---|
| Normal | "When is my sofa arriving? Order 4417" | Not run (needs the AI key) |  |
| Edge | Return complaining about the driver | Not run (needs the AI key) |  |
| Duplicate | Same message ID twice | Pass | PATCH /helpdesk/tickets/T-1: 1 call(s); select copies_skipped from key_log where recipe='R4.1' -> 1 |
| Escalate | Uncovered language | Not run (needs the AI key) |  |
| Automatic sender | An out-of-office reply (companion extension) | Pass | helpdesk/tickets/T-1.queue = "Low priority"; POST /anthropic/v1/messages: 0 call(s) |
| AI error | The AI call fails twice (companion extension) | Pass | helpdesk/tickets/T-1.queue = "Manual triage"; POST /anthropic/v1/messages: 2 call(s); select reason from exception_queue where recipe='R4.1' -> needs manual triage |
| Write fails | The routing write fails (companion extension) | Pass | PATCH /helpdesk/tickets/T-1: 1 call(s); select status from key_log where recipe='R4.1' -> failed; select reason from exception_queue where recipe='R4.1' -> write failed |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
