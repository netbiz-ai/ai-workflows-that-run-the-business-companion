# R14.3 Make build: golden-set run

Run 2026-10-25 on Make (cloud service, Core plan, us2.make.com), against the companion's mock systems (`tools/mock-systems/`).
Result: 10 of 10 cases passed.
Make credits used by the whole set: 206.

| Case | Input | Result | Credits | Checked |
|---|---|---|---|---|
| Normal | Task one day overdue, not reminded | Pass | 20 | messaging/messages: 1 records; messaging/messages/1.to = ["nadia@example.test"]; messaging/messages/1.text = "Send reschedule list to crews was due 2026-10-24 (Delivery planning). Source: https://transcripts.example.test/TR-1?t=00%3A04%3A12"; tracking/rows/TK-1.reminder_state = "sent"; tracking/rows/TK-1.reminder_key = "TK-1:2026-10-24"; agenda/items: 0 records; select status from key_log where recipe='R14.3' -> done |
| Edge | Date moved twice, not overdue | Pass | 22 | agenda/items: 1 records; agenda/items/1.meeting_id = "M-1"; agenda/items/1.verified_date = "2026-10-23"; agenda/items/1.due_date = "2026-10-30"; tracking/rows/TK-1.changes = 2; tracking/rows/TK-1.last_due_seen = "2026-10-30"; POST /messaging/messages: 1 call(s); select status from key_log where recipe='R14.3' and key='TK-1:M-1' -> done |
| Duplicate | Message sent, key not marked "sent" | Pass | 30 | messaging/messages: 0 records; select reason || ' / ' || owner from exception_queue where recipe='R14.3' -> reminder key pending / owen@example.test; tracking/rows/TK-1.reminder_state = "pending" |
| Escalate | No series meeting within 14 days | Pass | 33 | messaging/messages: 1 records; messaging/messages/1.to = ["tom@example.test"]; agenda/items: 0 records; select copies_skipped from key_log where recipe='R14.3' and key like '%:no meeting' -> 1 |
| Carried | Reminded a working day ago, still open, series meets in 7 days (companion extension) | Pass | 33 | agenda/items: 1 records; agenda/items/1.meeting_id = "M-1"; agenda/items/1.days_overdue = 3; agenda/items/1.owner = "Nadia Ferreira"; agenda/items/1.status = "listed"; messaging/messages: 0 records |
| Write fails | The reminder send fails (companion extension) | Pass | 34 | POST /messaging/messages: 1 call(s); tracking/rows/TK-1.reminder_state = "pending"; select status from key_log where recipe='R14.3' -> failed; select reason || ' / ' || owner from exception_queue where recipe='R14.3' -> write failed / owen@example.test |
| Holiday | The morning run on a holiday (companion extension) | Pass | 6 | GET /tasks/tasks: 0 call(s); messaging/messages: 0 records |
| New date | The chair sets a new date at the meeting (companion extension) | Pass | 10 | tracking/rows/TK-1.verified_date = "2026-11-04"; tracking/rows/TK-1.changes = 0; PATCH /tasks/tasks/TK-1: 0 call(s); select count(*) from decision_log where recipe='R14.3' and decision='new date verified' -> 1 |
| Closed since listed | A listed task closed before its meeting (companion extension) | Pass | 15 | agenda/items/AG-1.status = "closed since listed"; agenda/items: 1 records; messaging/messages: 0 records |
| Stop flag | The stop flag is set (companion extension) | Pass | 3 | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
