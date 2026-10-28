# R6.2 Make build: golden-set run

Run 2026-10-27 on Make (cloud service, Core plan, us2.make.com), against the companion's mock systems (`tools/mock-systems/`).
Result: 12 of 12 cases passed.
Make credits used by the whole set: 204.

| Case | Input | Result | Credits | Checked |
|---|---|---|---|---|
| Normal | Quote quiet past the window | Pass | 19 | crm/tasks/1.title = "Follow up quote Q-1042"; crm/tasks/1.owner = "ben@northstar.example.test"; teams/messages/2.draft = "Hello,\n\nI wanted to follow up on Q-1042 for the walnut finish lobby bar stools, including delivery and assembly. I hope my earlier answers on your questions about delivery timing and assembly were helpful. If anything is still unclear, or you would like to talk through next steps, please let me know and I will be glad to help.\n\nBest regards"; select decision from decision_log where recipe='R6.2' -> reminder 1, with draft; select key from key_log where recipe='R6.2' -> Q-1:1:1 |
| Edge | Quote expires in two days | Pass | 16 | teams/messages/2.text = "Requote before following up (R5.3): quote Q-1042 expires 2026-10-29"; teams/messages/2.draft = null; crm/tasks: 1 records; POST /anthropic/v1/messages: 0 call(s); select decision from decision_log where recipe='R6.2' -> reminder 1, no draft: requote |
| Duplicate | Schedule fires twice | Pass | 28 | POST /crm/tasks: 1 call(s); POST /teams/messages: 1 call(s); select count(*) from key_log where recipe='R6.2' -> 1; select count(*) from decision_log where recipe='R6.2' -> 1 |
| Escalate | Account flagged for a dispute | Pass | 25 | POST /teams/messages: 1 call(s); teams/messages/1.to = "ben@northstar.example.test"; POST /crm/tasks: 0 call(s); POST /anthropic/v1/messages: 0 call(s); select key || ' ' || copies_skipped from key_log where recipe='R6.2' -> Q-1:dispute 1; select decision from decision_log where recipe='R6.2' -> no reminder; sales lead told (dispute) |
| Refuse | Draft offers "an extra 5% off" | Pass | 19 | crm/tasks: 1 records; teams/messages/2.draft = null; select decision from decision_log where recipe='R6.2' -> reminder 1, without draft; select rules->>'draft_check' from decision_log where recipe='R6.2' -> dropped: number not in the description: 5 |
| AI error | The AI call fails on every try (companion extension) | Pass | 21 | POST /anthropic/v1/messages: 3 call(s); crm/tasks/1.title = "Follow up quote Q-1042"; teams/messages/2.draft = null; select decision || ' / ' || (rules->>'draft_check') from decision_log where recipe='R6.2' -> reminder 1, without draft / dropped: AI error after three retries |
| Write fails | The CRM task write fails (companion extension) | Pass | 18 | POST /crm/tasks: 1 call(s); POST /teams/messages: 0 call(s); select status from key_log where recipe='R6.2' -> failed; select reason from exception_queue where recipe='R6.2' -> write failed |
| Last reminder | Quote due its last allowed reminder (companion extension) | Pass | 16 | crm/tasks/1.title = "Call, or mark the quote lost: quote Q-1042, last allowed reminder"; teams/messages/2.draft = null; POST /anthropic/v1/messages: 0 call(s); select key from key_log where recipe='R6.2' -> Q-1:1:3 |
| Limit reached | Quote has had every reminder the limit allows (companion extension) | Pass | 9 | POST /crm/tasks: 0 call(s); POST /teams/messages: 0 call(s); select count(*) from key_log where recipe='R6.2' -> 0 |
| Within the gap | Quote reminded yesterday (companion extension) | Pass | 9 | POST /crm/tasks: 0 call(s); POST /teams/messages: 0 call(s); select count(*) from key_log where recipe='R6.2' -> 0 |
| Owner absent | Quote owner on leave, with a named cover (companion extension) | Pass | 21 | crm/tasks/1.owner = "sam@northstar.example.test"; teams/messages/2.to = "sam@northstar.example.test" |
| Stop flag | The stop flag is set (companion extension) | Pass | 3 | writes to systems: none; select count(*) from key_log -> 0; select count(*) from decision_log -> 0 |

The mock systems stand in for the business systems; connect your own before go-live and rerun the golden set with your data (book Chapter 16).
