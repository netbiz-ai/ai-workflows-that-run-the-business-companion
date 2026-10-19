# R5.4 n8n build: golden-set run

Run 2026-10-19 on n8n 2.42.7 (self-hosted), against the companion's mock systems (`tools/mock-systems/`).
Result: 16 of 16 cases passed.

| Case | Input | Result | Checked |
|---|---|---|---|
| Normal | Small standard quote | Pass | crm/quotes/Q-1.approver = "maya@example.test"; crm/quotes/Q-1.locked = true; messaging/messages: 1 records; messaging/messages/1.to = "maya@example.test"; messaging/messages/1.checklist = "https://example.test/checklist-13-1"; select rules->>'value' from decision_log where recipe='R5.4' -> 1567.5 |
| Edge | Three-year protection plan | Pass | crm/quotes/Q-1.approver = "ben@example.test"; messaging/messages/1.to = "ben@example.test" |
| Duplicate | Status set twice | Pass | POST /messaging/messages: 1 call(s); select copies_skipped from key_log where recipe='R5.4' -> 1 |
| Escalate | Ben's own quote | Pass | crm/quotes/Q-1.approver = "helen@example.test"; messaging/messages/1.to = "helen@example.test" |
| Refuse | Price list replaced while waiting | Pass | crm/quotes/Q-1.status = "back to R5.3"; crm/quotes/Q-1.approver = null; messaging/messages: 1 records; messaging/messages/1.to = "maya@example.test" |
| Request not sent | Sending the approval request fails (companion extension) | Pass | crm/quotes/Q-1.status = "returned"; crm/quotes/Q-1.locked = true; POST /messaging/messages: 2 call(s); messaging/messages: 1 records; messaging/messages/1.to = "owen@example.test" |
| Deadline passed | No decision by the deadline (companion extension) | Pass | messaging/messages/1.to = "maya@example.test"; crm/quotes/Q-1.escalation = 1; crm/quotes/Q-1.status = "awaiting approval" |
| Deputy asked | No decision by twice the deadline (companion extension) | Pass | messaging/messages: 1 records; messaging/messages/1.to = "ben@example.test"; crm/quotes/Q-1.escalation = 2 |
| Returned at three times | No decision by three times the deadline (companion extension) | Pass | crm/quotes/Q-1.status = "returned"; crm/quotes/Q-1.locked = true; messaging/messages: 1 records; messaging/messages/1.to = "ben@example.test" |
| Approved | The routed approver approves (companion extension) | Pass | crm/quotes/Q-1.status = "approved"; crm/quotes/Q-1.locked = false; crm/quotes/Q-1.approved_revision = 1; select approved_by from decision_log where recipe='R5.4' -> maya@example.test; select item from decision_log where recipe='R5.4' -> Q-1:1 |
| Rejected | The approver rejects with a comment (companion extension) | Pass | crm/quotes/Q-1.status = "returned"; crm/quotes/Q-1.comment = "Discount needs Ben's view"; crm/quotes/Q-1.locked = true |
| Not the approver | Someone not routed records an approval (companion extension) | Pass | crm/quotes/Q-1.status = "awaiting approval"; crm/quotes/Q-1.locked = true; PATCH /crm/quotes/Q-1: 0 call(s); select reason from exception_queue where recipe='R5.4' -> decision not accepted |
| Price list replaced before approval | Approved after the price list changed (companion extension) | Pass | crm/quotes/Q-1.status = "back to R5.3"; crm/quotes/Q-1.locked = true; select count(*) from decision_log where recipe='R5.4' and approved_by is not null -> 0 |
| Sent unapproved | A quote sent without approval (companion extension) | Pass | select reason from exception_queue where recipe='R5.4' -> quote sent unapproved; messaging/messages/1.to = "ben@example.test" |
| Write fails | The lock write fails (companion extension) | Pass | PATCH /crm/quotes/Q-1: 1 call(s); POST /messaging/messages: 0 call(s); select status from key_log where recipe='R5.4' -> failed; select reason from exception_queue where recipe='R5.4' -> write failed |
| Stop flag | The stop flag is set (companion extension) | Pass | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
