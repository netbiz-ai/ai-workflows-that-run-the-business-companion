# R9.4 Make build: golden-set run

Run 2026-10-26 on Make (cloud service, Core plan, us2.make.com), against the companion's mock systems (`tools/mock-systems/`).
Result: 10 of 10 cases passed.
Make credits used by the whole set: 255.

| Case | Input | Result | Credits | Checked |
|---|---|---|---|---|
| Normal | Seasonal leaver, SSO and point-of-sale | Pass | 47 | directory/users/u-e1.enabled = false; directory/sign_in_revocations: 1 records; pos/users/pos-e1.active = false; evidence/items/E-1-2026-10-26-I-SSO.status = "confirmed"; evidence/items/E-1-2026-10-26-I-POS.status = "confirmed"; evidence/cases/E-1-2026-10-26.status = "closed"; evidence/cases/E-1-2026-10-26.closed_by = "owen@example.test"; select status from key_log where recipe='R9.4' -> done; select string_agg(decision, ', ' order by id) from decision_log where recipe='R9.4' -> every item confirmed; to the access owner, closed |
| Edge | Empty inventory | Pass | 19 | PATCH /directory/users/u-e1: 0 call(s); evidence/cases: 0 records; POST /messaging/messages: 1 call(s); select reason || ' / ' || detail || ' / ' || owner from exception_queue where recipe='R9.4' -> inventory not valid / inventory empty; nothing removed / owen@example.test |
| Edge | Supplier-portal login lent after hire | Pass | 36 | tasks/tasks/E-1-2026-10-26-I-PORTAL.assignee = "portal-admin@example.test"; evidence/items/E-1-2026-10-26-I-PORTAL.status = "open"; evidence/items/E-1-2026-10-26-I-SSO.status = "confirmed"; evidence/cases/E-1-2026-10-26.status = "open"; evidence/cases/E-1-2026-10-26.unconfirmed = ["I-PORTAL"]; POST /messaging/messages: 0 call(s) |
| Duplicate | Leaver saved twice | Pass | 56 | PATCH /directory/users/u-e1: 1 call(s); POST /directory/sign_in_revocations: 1 call(s); PATCH /pos/users/pos-e1: 1 call(s); POST /messaging/messages: 1 call(s); select copies_skipped from key_log where recipe='R9.4' -> 1 |
| Refuse | Entered by a store manager; an administrator | Pass | 21 | PATCH /directory/users/u-e1: 0 call(s); PATCH /directory/users/admin-e2: 0 call(s); PATCH /pos/users/pos-e1: 0 call(s); POST /messaging/messages: 2 call(s); select string_agg(reason || ' / ' || owner, ', ' order by reason) from exception_queue where recipe='R9.4' -> inventory not valid / owen@example.test, not entered by HR / aisha@example.test |
| Disable fails | The SSO disable fails (companion extension) | Pass | 33 | PATCH /directory/users/u-e1: 1 call(s); itsm/tickets: 1 records; pos/users/pos-e1.active = false; evidence/cases/E-1-2026-10-26.status = "open"; select status from key_log where recipe='R9.4' -> failed; select reason || ' / ' || owner from exception_queue where recipe='R9.4' -> removal failed / owen@example.test |
| Administrator does not tick | An item still open at the deadline (companion extension) | Pass | 14 | itsm/tickets: 1 records; POST /messaging/messages: 1 call(s); evidence/cases/E-1-OLD.ticketed = true; evidence/cases/E-1-OLD.status = "open" |
| Administrator ticks | The last open item is ticked (companion extension) | Pass | 17 | evidence/items/E-1-C-I-PORTAL.status = "confirmed"; evidence/items/E-1-C-I-PORTAL.by = "portal-admin@example.test"; evidence/cases/E-1-C.status = "all confirmed; to close"; POST /messaging/messages: 1 call(s) |
| Close refused | Closing with an item unconfirmed (companion extension) | Pass | 9 | evidence/cases/E-1-C.status = "open"; POST /messaging/messages: 1 call(s); select count(*) from decision_log where recipe='R9.4' -> 0 |
| Stop flag | The stop flag is set (companion extension) | Pass | 3 | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
