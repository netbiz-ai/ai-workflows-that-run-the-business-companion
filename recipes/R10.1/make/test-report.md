# R10.1 Make build: golden-set run

Run 2026-10-27 on Make (cloud service, Core plan, us2.make.com), against the companion's mock systems (`tools/mock-systems/`).
Result: 11 of 11 cases passed.
Make credits used by the whole set: 224.

| Case | Input | Result | Credits | Checked |
|---|---|---|---|---|
| Normal | Online order, complete address, elevator, paid | Pass | 19 | scheduling/work_orders/online:4417:delivery:1.status = "ready to schedule"; scheduling/work_orders/online:4417:delivery:1.lift = "yes"; scheduling/work_orders/online:4417:delivery:1.access_code = null; tasks/tasks: 0 records; select status from key_log where recipe='R10.1' -> done |
| Edge | "Gate code 4821" or "key safe 19#73" | Pass | 20 | scheduling/work_orders/online:4417:delivery:1.notes = "Gate code [masked]; key safe [masked] by the door. Elevator available. No stairs. Parking in the visitor bay."; scheduling/work_orders/online:4417:delivery:1.status = "missing details"; scheduling/work_orders/online:4417:delivery:1.code_in_notes = true; tasks/tasks/online:4417:delivery:1.gaps = ["code in notes: move it to the restricted access-code field"]; select count(*) from decision_log where recipe='R10.1' and rules::text like '%4821%' -> 0 |
| Edge, no code word | "Entry is 4821, third floor" | Pass | 20 | scheduling/work_orders/online:4417:delivery:1.notes = "Entry is [masked], third floor. Elevator available. No stairs. Parking in the visitor bay."; scheduling/work_orders/online:4417:delivery:1.code_in_notes = true; scheduling/work_orders/online:4417:delivery:1.floor = 3; scheduling/work_orders/online:4417:delivery:1.status = "missing details" |
| Edge | AI returns "elevator: yes"; notes say "no elevator until November" | Pass | 19 | scheduling/work_orders/online:4417:delivery:1.lift = "no" |
| Duplicate | Paid-order webhook sent twice | Pass | 25 | scheduling/work_orders: 1 records; PUT /scheduling/work_orders/online:4417:delivery:1: 1 call(s); select copies_skipped from key_log where recipe='R10.1' -> 1 |
| Refuse | Address outside every zone | Pass | 21 | scheduling/work_orders/online:4417:delivery:1.status = "missing details"; scheduling/work_orders/online:4417:delivery:1.gaps = ["address outside every zone"]; select reason || ' / ' || owner from exception_queue where recipe='R10.1' -> address outside every zone / tom@example.test |
| Changed order | The order changes after its work order is made (companion extension) | Pass | 38 | scheduling/work_orders: 1 records; PUT /scheduling/work_orders/online:4417:delivery:1: 2 call(s); select count(*) from decision_log where recipe='R10.1' -> 2 |
| AI error | The AI call fails twice (companion extension) | Pass | 21 | scheduling/work_orders/online:4417:delivery:1.status = "missing details"; tasks/tasks/online:4417:delivery:1.gaps = ["AI error: details not read from the notes", "stairs", "lift", "parking"]; POST /anthropic/v1/messages: 2 call(s) |
| Write fails | The scheduling system is down (companion extension) | Pass | 20 | PUT /scheduling/work_orders/online:4417:delivery:1: 1 call(s); select status from key_log where recipe='R10.1' -> failed; select reason || ' / ' || owner from exception_queue where recipe='R10.1' -> write failed / owen@example.test |
| Late task | A task open four days (companion extension) | Pass | 17 | select reason || ' / ' || owner from exception_queue where recipe='R10.1' -> task open two working days / tom@example.test |
| Stop flag | The stop flag is set (companion extension) | Pass | 4 | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
