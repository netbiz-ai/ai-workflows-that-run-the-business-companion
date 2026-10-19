# R12.3 n8n build: golden-set run

Run 2026-10-19 on n8n 2.42.7 (self-hosted), against the companion's mock systems (`tools/mock-systems/`).
Result: 9 of 9 cases passed.

| Case | Input | Result | Checked |
|---|---|---|---|
| Normal | Overdue work orders past Tom's line, fresh | Pass | chat/messages: 1 records; chat/messages/1.to = "tom@example.test"; chat/messages/1.text = "Overdue work orders: value 18, change 6; your line is value above 15 (line version 1). Cut-off 2026-10-18T17:00:00Z. Source: https://lists.example.test/snapshots/V-1:overdue-work-orders"; chat/messages/1.text = "Overdue work orders: value 18, change 6; your line is value above 15 (line version 1). Cut-off 2026-10-18T17:00:00Z. Source: https://lists.example.test/snapshots/V-1:overdue-work-orders"; alertlog/alerts: 1 records; select count(*) from decision_log where recipe='R12.3' -> 3; select decision from decision_log where recipe='R12.3' and item like '%Staff absences' -> not checked: no alert |
| Edge | Figure past the line but stale | Pass | chat/messages: 1 records; chat/messages/1.to = "dispatch-lead@example.test"; chat/messages/1.text = "Overdue work orders printed blank (stale) at the 2026-10-18T17:00:00Z cut-off. Source: Delivery scheduling https://lists.example.test/snapshots/V-1:overdue-work-orders. Last good: 2026-10-11." |
| Duplicate | New table version, same outcome | Pass | chat/messages: 1 records; select copies_skipped from key_log where recipe='R12.3' and key like '%Overdue work orders%' -> 1; select count(*) from decision_log where recipe='R12.3' and decision like '%suppressed%' -> 3 |
| Refuse | Line raised and approved Thursday at 3 p.m. | Pass | chat/messages: 1 records; chat/messages/1.text = "Overdue work orders: value 18, change 6; your line is value above 15 (line version 1). Cut-off 2026-10-18T17:00:00Z. Source: https://lists.example.test/snapshots/V-1:overdue-work-orders" |
| Escalate | Alert not seen by Friday 4 p.m. | Pass | preread/open_issues: 1 records; preread/open_issues/1.alert = "A-1" |
| Post fails | The alert post fails three times (companion extension) | Pass | POST /chat/messages: 3 call(s); email/messages: 1 records; alertlog/alerts: 1 records; select status from key_log where recipe='R12.3' and key like '%Overdue work orders%' -> done |
| Post and email fail | The owner's post and email both fail (companion extension) | Pass | POST /email/messages: 1 call(s); select status from key_log where recipe='R12.3' and key like '%Overdue work orders%' -> failed; select reason from exception_queue where recipe='R12.3' -> alert failed |
| Next week's line | The raised line in force from the next cut-off (companion extension) | Pass | chat/messages: 0 records; select decision from decision_log where recipe='R12.3' and item like '%Overdue work orders' -> within the line: no alert |
| Stop flag | The stop flag is set (companion extension) | Pass | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
