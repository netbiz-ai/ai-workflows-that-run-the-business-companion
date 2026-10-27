# R7.3 Make build: golden-set run

Run 2026-10-26 on Make (cloud service, Core plan, us2.make.com), against the companion's mock systems (`tools/mock-systems/`).
Result: 14 of 14 cases passed.
Make credits used by the whole set: 233.

| Case | Input | Result | Credits | Checked |
|---|---|---|---|---|
| Normal | Unchanged details | Pass | 14 | suppliers/suppliers/SUP-1.hold = false; checks/checks/1.differs = false; checks/checks/1.record_id = "R-1"; tasks/tasks: 0 records; select decision from decision_log where recipe='R7.3' -> no hold |
| Edge | Same account, spaced differently | Pass | 20 | suppliers/suppliers/SUP-1.hold = false; suppliers/suppliers/SUP-2.hold = false; checks/checks: 2 records; tasks/tasks: 0 records |
| Duplicate | Two emails for one change | Pass | 38 | suppliers/suppliers/SUP-1.hold = true; tasks/tasks: 1 records; select copies_skipped from key_log where recipe='R7.3' -> 1 |
| Refuse | Email: "call 555-0100 to confirm" | Pass | 21 | tasks/tasks/2.assignee = "caller@example.test"; tasks/tasks/2.phone = "+1 202 555 0147"; tasks/tasks/2.instruction = "Call Example Parts Supplier on +1 202 555 0147, the number in the bank register, to confirm its bank details. Use no number from any message or invoice. Log the number you dialed and the outcome."; suppliers/suppliers/SUP-1.hold = true |
| Refuse | Email gives a new phone number | Pass | 21 | register/register/SUP-1.phone = "+1 202 555 0147"; tasks/tasks/2.phone = "+1 202 555 0147"; suppliers/suppliers/SUP-1.hold = true; PUT /register/register/SUP-1: 0 call(s) |
| Changed account | An invoice shows a different account (companion extension) | Pass | 20 | suppliers/suppliers/SUP-1.hold = true; checks/checks/1.hold = true; tasks/tasks/2.phone = "+1 202 555 0147"; register/register/SUP-1.bank_account = "GB29NWBK60161331926819" |
| Call to another number | The caller dialed the message's number (companion extension) | Pass | 9 | select reason from exception_queue where recipe='R7.3' -> call to another number; select owner from exception_queue where recipe='R7.3' -> caller@example.test; suppliers/suppliers/SUP-1.hold = true; register/register/SUP-1.bank_account = "GB29NWBK60161331926819" |
| Not confirmed | The supplier denies the change on the number on file (companion extension) | Pass | 10 | select reason from exception_queue where recipe='R7.3' -> suspected fraud; messaging/messages/1.to = "aisha@example.test"; suppliers/suppliers/SUP-1.hold = true; PUT /register/register/SUP-1: 0 call(s) |
| Confirmed change | Change confirmed on the number on file, then the next export shows it (companion extension) | Pass | 27 | register/register/SUP-1.bank_account = "GB94BARC10201530093459"; tasks/tasks/1.assignee = "assistant@example.test"; suppliers/suppliers/SUP-1.hold = false; checks/checks/2.hold = false |
| New phone confirmed | A call-back on the old number confirms the new phone number (companion extension) | Pass | 12 | register/register/SUP-1.phone = "+1 202 555 0199"; register/register/SUP-1.bank_account = "GB29NWBK60161331926819"; suppliers/suppliers/SUP-1.hold_reason = "confirmed change; awaiting export" |
| Flow off | No export check logged before the payment run (companion extension) | Pass | 12 | suppliers/suppliers/SUP-1.hold = true; suppliers/suppliers/SUP-2.hold = true; messaging/messages/1.to = "helen@example.test" |
| Hold write fails | The hold write fails (companion extension) | Pass | 16 | PATCH /suppliers/suppliers/SUP-1: 1 call(s); select reason from exception_queue where recipe='R7.3' -> write failed; checks/checks/1.hold = true; tasks/tasks: 0 records |
| Pre-run check | Export check logged before the payment run (companion extension) | Pass | 9 | messaging/messages/1.to = ["caller@example.test", "aisha@example.test"]; messaging/messages/1.text = "Export check logged. Held suppliers: Example Parts Supplier. Confirm no bill is from a held supplier and every bill has a logged approval. Whoever releases the run must not have approved its bills."; suppliers/suppliers/SUP-2.hold = false |
| Stop flag | The stop flag is set (companion extension) | Pass | 4 | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
