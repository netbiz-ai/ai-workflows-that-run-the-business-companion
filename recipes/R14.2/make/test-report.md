# R14.2 Make build: golden-set run

Run 2026-10-26 on Make (cloud service, Core plan, us2.make.com), against the companion's mock systems (`tools/mock-systems/`).
Result: 9 of 9 cases passed.
Make credits used by the whole set: 167.

| Case | Input | Result | Credits | Checked |
|---|---|---|---|---|
| Normal | Complete verified item | Pass | 20 | tasks/tasks: 1 records; tasks/tasks/1.item_id = "OCC-1-000412-1"; tasks/tasks/1.owner_email = "nadia@example.test"; tasks/tasks/1.series = "Delivery planning"; actions/items/OCC-1-000412-1.task_id = "1"; actions/items/OCC-1-000412-1.verified_due_date = "2026-10-29"; messaging/messages: 1 records; messaging/messages/2.to = ["nadia@example.test"]; select approved_by from decision_log where recipe='R14.2' and decision='task created' -> tom@example.test |
| Edge | Due date still "next week" | Pass | 20 | tasks/tasks: 0 records; POST /tasks/tasks: 0 call(s); actions/items/OCC-1-000412-1.status = "returned"; actions/items/OCC-1-000412-1.return_reason = "due date is not a calendar date"; messaging/messages: 1 records |
| Duplicate | Chair presses "verified" twice | Pass | 31 | POST /tasks/tasks: 1 call(s); tasks/tasks: 1 records; messaging/messages: 1 records |
| Refuse | Verified by someone not registered | Pass | 13 | POST /tasks/tasks: 0 call(s); GET /tasks/tasks: 0 call(s); select reason || ' / ' || owner from exception_queue where recipe='R14.2' -> verifier not chair or backup / tom@example.test; messaging/messages: 1 records; messaging/messages/1.to = ["tom@example.test"] |
| Owner has left | Owner's staff account inactive (companion extension) | Pass | 20 | POST /tasks/tasks: 0 call(s); actions/items/OCC-1-000412-1.status = "returned"; actions/items/OCC-1-000412-1.return_reason = "owner not an active staff account"; messaging/messages/1.to = ["tom@example.test"] |
| Task system down | Task creation fails twice (companion extension) | Pass | 20 | POST /tasks/tasks: 2 call(s); tasks/tasks: 0 records; actions/items/OCC-1-000412-1.task_id = null; select reason || ' / ' || owner from exception_queue where recipe='R14.2' -> task system error / tom@example.test; messaging/messages: 1 records; messaging/messages/1.to = ["tom@example.test"] |
| Rerun | Rerun after a task was created but its ID not written back (companion extension) | Pass | 18 | POST /tasks/tasks: 0 call(s); actions/items/OCC-1-000412-1.task_id = "TK-7"; messaging/messages: 0 records |
| Outside owner | Item owned by a supplier (companion extension) | Pass | 21 | minutes/entries/OCC-1-000412-1.text = "Brightline Freight (outside the company): Confirm the Saturday collection slot, due 2026-10-29"; tasks/tasks: 1 records; tasks/tasks/1.owner_email = "tom@example.test"; tasks/tasks/1.title = "Follow up with Brightline Freight: Confirm the Saturday collection slot"; messaging/messages: 1 records; messaging/messages/2.to = ["tom@example.test"] |
| Stop flag | The stop flag is set (companion extension) | Pass | 4 | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
