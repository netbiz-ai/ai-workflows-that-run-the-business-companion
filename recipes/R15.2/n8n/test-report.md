# R15.2 n8n build: golden-set run

Run 2026-10-19 on n8n 2.42.7 (self-hosted), against the companion's mock systems (`tools/mock-systems/`).
Result: 11 of 11 cases passed.

| Case | Input | Result | Checked |
|---|---|---|---|
| Normal | Forecast 15 a week; 25 free | Pass | briefs/briefs/B-1.capacity = "cleared"; briefs/briefs/B-1.capacity_figures = {"checked_at": "2026-10-19T18:39:24.367Z", "export": "2026-10-19T00:00:00Z", "weeks": [{"week": "2026-11-02", "open": 30, "non_promoted": 5, "free": 25, "forecast": 15, "shortfall": 0}, {"week": "2026-11-09", "open": 30, "non_promoted": 5, "free": 25, "forecast": 15, "shortfall": 0}, {"week": "2026-11-16", "open": 30, "non_promoted": 5, "free": 25, "forecast": 15, "shortfall": 0}]}; messaging/messages: 0 records; select status from key_log where recipe='R15.2' -> done; select decision from decision_log where recipe='R15.2' -> check: cleared |
| Edge | Fits the window, not week one | Pass | briefs/briefs/B-1.capacity = "held"; briefs/briefs/B-1.capacity_reasons = ["week 2026-11-02 short by 5"]; messaging/messages/1.to = ["tom@example.test", "ben@example.test"]; messaging/messages/1.text = "week 2026-11-02 short by 5" |
| Duplicate | Brief re-marked "ready" | Pass | PATCH /briefs/briefs/B-1: 1 call(s); select copies_skipped from key_log where recipe='R15.2' -> 1; select count(*) from decision_log where recipe='R15.2' -> 1 |
| Escalate | Live week at 90% | Pass | briefs/briefs/B-1.capacity = "held"; briefs/briefs/B-1.capacity_reasons = ["week 2026-11-02 at 90% of its planned share"]; messaging/messages/1.to = ["tom@example.test", "ben@example.test"]; messaging/messages/1.subject = "Promotion B-1: next wave held" |
| Stale export | Slot export two days old (companion extension) | Pass | briefs/briefs/B-1.capacity = "held"; briefs/briefs/B-1.capacity_reasons = ["slot export stale"]; messaging/messages/1.to = ["owen@example.test"]; select owner from exception_queue where recipe='R15.2' -> owen@example.test |
| Export format changed | Slot export with no week columns (companion extension) | Pass | briefs/briefs/B-1.capacity = "held"; briefs/briefs/B-1.capacity_reasons = ["export format changed"]; messaging/messages/1.to = ["owen@example.test"]; select detail from exception_queue where recipe='R15.2' -> export format changed: Slot export has no week columns |
| No forecast | A week with no forecast (companion extension) | Pass | briefs/briefs/B-1.capacity = "held"; briefs/briefs/B-1.capacity_reasons = ["no forecast for week 2026-11-09"]; messaging/messages/1.to = ["tom@example.test"]; select owner from exception_queue where recipe='R15.2' -> tom@example.test |
| Recheck | Held brief; Tom adds crew time and the morning export fits (companion extension) | Pass | briefs/briefs/B-1.capacity = "cleared"; briefs/briefs/B-1.capacity_reasons = []; messaging/messages: 0 records |
| Live and fitting | Live weeks at 80% or less (companion extension) | Pass | briefs/briefs/B-1.capacity = "cleared"; briefs/briefs/B-1.capacity_checked_at = "2026-10-19T18:39:35.058Z"; messaging/messages: 0 records |
| Write fails | Capacity status write fails (companion extension) | Pass | PATCH /briefs/briefs/B-1: 1 call(s); select status from key_log where recipe='R15.2' -> failed; select reason from exception_queue where recipe='R15.2' -> write failed |
| Stop flag | The stop flag is set (companion extension) | Pass | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
