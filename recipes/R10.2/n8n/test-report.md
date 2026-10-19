# R10.2 n8n build: golden-set run

Run 2026-10-19 on n8n 2.42.7 (self-hosted), against the companion's mock systems (`tools/mock-systems/`).
Result: 12 of 12 cases passed.

| Case | Input | Result | Checked |
|---|---|---|---|
| Normal | "Can we do Thursday instead?", then "2" | Pass | messaging/messages/O-M-1.text = "1. 2026-10-23 09:00-12:00\n2. 2026-10-24 13:00-16:00\n3. 2026-10-25 09:00-12:00\nReply 1, 2 or 3 within 24 hours and a dispatcher will confirm your new time; until then your booking stays as it is."; tasks/tasks/T-M-2.slot = "S-2"; PATCH /scheduling/work_orders/J-1: 0 call(s) |
| Edge | "Thursday's fine, gate code 4821" | Pass | tasks/tasks/T-M-1.reply = "Thursday's fine, gate code [masked]"; messaging/messages: 0 records |
| Duplicate | Same reply delivered twice | Pass | select copies_skipped from key_log where recipe='R10.2' -> 1; select count(*) from decision_log where recipe='R10.2' -> 1 |
| Escalate | Trade account: "fridge leaking onto the floor" | Pass | tasks/tasks/T-M-1.type = "urgent"; helpdesk/tickets: 1 records; POST /anthropic/v1/messages: 0 call(s) |
| Refuse | "Cancel it and refund me today" | Pass | tasks/tasks/T-M-1.type = "reply"; messaging/messages: 0 records; PATCH /scheduling/work_orders/J-1: 0 call(s); DELETE /scheduling/work_orders/J-1: 0 call(s) |
| AI error | The AI call fails twice (companion extension) | Pass | tasks/tasks/T-M-1.reason = "AI error after retries. Read the reply and deal with it."; tasks/tasks/T-M-1.reply = "Can we do Thursday instead?"; POST /anthropic/v1/messages: 2 call(s); messaging/messages: 0 records |
| Slot lookup fails | The open-slot read fails after a reschedule reply (companion extension) | Pass | tasks/tasks/T-M-1.reason = "The customer asks to reschedule; the slot lookup failed. Phone the customer."; messaging/messages: 0 records |
| Trade reply | Trade account: "Can we move it to next week?" (companion extension) | Pass | tasks/tasks/T-M-1.type = "trade reply"; POST /anthropic/v1/messages: 0 call(s) |
| Slot set | A slot is set (companion extension) | Pass | messaging/messages: 1 records; messaging/messages/1.text = "Your delivery is booked for 2026-10-22, 09:00-12:00. Please clear a path to the room."; messaging/messages/1.to = "+1 555 0100" |
| Not delivered | The confirmation send fails (companion extension) | Pass | POST /messaging/messages: 1 call(s); tasks/tasks/ND-J-1-confirmation.type = "message not delivered" |
| Reminders | One job tomorrow, one in three days (companion extension) | Pass | messaging/messages: 1 records; messaging/messages/R-J-2-2026-10-20.to = "second@example.test" |
| Stop flag | The stop flag is set (companion extension) | Pass | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
