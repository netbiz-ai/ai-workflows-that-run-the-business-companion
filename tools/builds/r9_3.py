"""R9.3 Take leave requests, check the balance and route to the manager: rules only, no AI step.

Source: book Chapter 9, recipe R9.3, build steps 1 to 8 (recipes/R9.3/build-spec.md).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import Workflow  # noqa: E402

RID = "R9.3"
T = "Step 1: Request or cancellation"
D = "Step 6: Manager decides"
M = "Step 6: Morning reminders"
B = f"$('{T}').first().json.body"
CFG = "$('Config').first().json"
EMP = "$('Step 2: Rule: listed? protected?').first().json.employee"
KEY = f"{EMP}.id + ':' + {B}.type + ':' + {B}.start + ':' + {B}.end"

DATES_JS = r"""
const isoToday = () => new Date().toISOString().slice(0, 10);
const day = d => new Date(String(d).slice(0, 10) + 'T00:00:00Z');
const isDate = d => /^\d{4}-\d{2}-\d{2}$/.test(String(d || '')) && !isNaN(day(d));
// Working days (Monday to Friday) after the date, up to and including today.
function workingDaysSince(d) {
  let n = 0;
  for (let x = new Date(day(d).getTime() + 86400000); x <= day(isoToday()); x = new Date(x.getTime() + 86400000)) {
    if (x.getUTCDay() % 6 !== 0) n++;
  }
  return n;
}
"""

ROUTE_JS = rf"""
// Step 2: an unlisted requester gets nothing sent and HR is told; sick or family leave goes to HR alone.
const cfg = {CFG};
const b = {B};
const employee = ($('Step 2: Read the employee list').first().json.items || [])[0] || null;
let route = 'check';
if (!employee) route = 'unlisted';
else if (b.action === 'cancel') route = 'cancel';
else if ((cfg.protected_types || []).map(t => String(t).toLowerCase()).includes(String(b.type || '').toLowerCase())) route = 'hr';
return [{{ json: {{ route, employee }} }}];
"""

CHECK_JS = DATES_JS + rf"""
// Step 4 and step 5: today's balance, then dates, notice, balance less open requests, overlap.
// Each failure is a warning for the manager; none ends the request.
const cfg = {CFG};
const b = {B};
const emp = {EMP};
const all = $('Step 5: Read the request list').first().json.items || [];
const OPEN = ['with manager', 'with stand-in'];
const TAKEN = ['with manager', 'with stand-in', 'approved'];
const overlaps = r => isDate(r.start) && isDate(r.end) && day(r.start) <= day(b.end) && day(r.end) >= day(b.start);
const workDays = emp.work_days || [1, 2, 3, 4, 5];
const warnings = [];
let days = 0;
const valid = isDate(b.start) && isDate(b.end) && day(b.end) >= day(b.start) && day(b.start) >= day(isoToday());
if (valid) {{
  for (let x = day(b.start); x <= day(b.end); x = new Date(x.getTime() + 86400000)) if (workDays.includes(x.getUTCDay() || 7)) days++;
}}
if (!valid || days === 0) warnings.push('dates not valid');
const notice = Number((cfg.notice_days || {{}})[b.type] || 0);
const given = valid ? Math.round((day(b.start) - day(isoToday())) / 86400000) : 0;
if (valid && given < notice) warnings.push(`notice not met: ${{given}} days given, ${{notice}} needed`);
const balance = ($('Step 4: Read today\'s balance').first().json.items || []).find(r => r.type === b.type);
let available = null;
if (!balance || String(balance.as_of).slice(0, 10) !== isoToday()) warnings.push('balance not checked');
else {{
  const open = all.filter(r => r.employee_id === emp.id && r.type === b.type && OPEN.includes(r.status) && r.id !== b.request_id);
  available = Number(balance.days) - open.reduce((s, r) => s + Number(r.days || 0), 0);
  if (available < days) warnings.push(`balance less open requests (${{available}}) does not cover ${{days}} days`);
}}
const own = all.filter(r => r.employee_id === emp.id && r.id !== b.request_id && TAKEN.includes(r.status) && overlaps(r));
if (own.length) warnings.push('overlaps request ' + own.map(r => r.id).join(', '));
const others = all.filter(r => r.employee_id !== emp.id && r.manager === emp.manager && TAKEN.includes(r.status) && overlaps(r));
return [{{ json: {{ days, warnings, available, who_else_off: [...new Set(others.map(r => r.name))] }} }}];
"""

DECIDED_JS = rf"""
// Step 6: the manager, stand-in or HR decides a request that is still open.
const d = $('{D}').first().json.body;
const r = ($('Step 6: Read the request').first().json.items || [])[0];
if (!r || !['with manager', 'with stand-in', 'with HR'].includes(r.status) || !['approved', 'declined'].includes(d.decision)) return [];
return [{{ json: Object.assign({{}}, r, {{ decision: d.decision, decided_by: d.by || r.decider, decided_on: new Date().toISOString().slice(0, 10) }}) }}];
"""

REMIND_JS = DATES_JS + rf"""
// Step 6: remind the manager at 2 working days; at 4 go to the stand-in and tell HR.
const cfg = {CFG};
const open = $('Step 6: Read requests with the manager').first().json.items || [];
const out = [];
for (const r of open) {{
  const n = workingDaysSince(r.sent_on);
  if (n >= cfg.standin_working_days) out.push({{ json: Object.assign({{}}, r, {{ action: 'stand-in', waited: n }}) }});
  else if (n >= cfg.remind_working_days && !r.reminded) out.push({{ json: Object.assign({{}}, r, {{ action: 'remind', waited: n }}) }});
}}
return out;
"""

CANCEL_JS = rf"""
// Step 8: a cancellation of a request that is not already closed.
const r = ($('Step 8: Read the request to cancel').first().json.items || [])[0];
if (!r || ['cancelled', 'declined'].includes(r.status)) return [];
return [{{ json: Object.assign({{}}, r, {{ was: r.status }}) }}];
"""

RESERVE_SQL = (
    "WITH reserved AS (INSERT INTO key_log (recipe, key, status) VALUES ($1, $2, 'in progress') "
    "ON CONFLICT (recipe, key) DO UPDATE SET status = 'in progress', result = NULL, reserved_at = now() "
    "WHERE key_log.status = 'done' RETURNING key), "
    "skipped AS (UPDATE key_log SET copies_skipped = copies_skipped + 1 "
    "WHERE recipe = $1 AND key = $2 AND NOT EXISTS (SELECT 1 FROM reserved)) "
    "SELECT (SELECT count(*) FROM reserved) = 1 AS is_new, $2::text AS key")


def build() -> Workflow:
    w = Workflow(RID, "R9.3 Take leave requests, check the balance and route to the manager")
    w.webhook(T, "r9-3-leave", "Your signed-in leave form calls this. Body: {request_id, employee (the signed-in email), type, start, end, "
              "action: request | cancel}; no free-text reason.", pos=[0, 0])
    w.webhook(D, "r9-3-decision", "The approval calls this when the manager, stand-in or HR decides. Body: {request_id, decision: approved | declined, by}.", pos=[0, 900])
    w.schedule(M, 8, "Step 6's reminders: 2 working days to the manager, 4 to the stand-in and HR.", pos=[0, 1200])
    w.config("Config", {
        "employees_url": "https://<your employee list API>",
        "balances_url": "https://<your daily balance export API>",
        "requests_url": "https://<your leave request list API>",
        "record_list_url": "https://<your HR to-record list API>",
        "messaging_url": "https://<your messaging API>",
        "hr_owner": "<your HR owner>",
        "protected_types": ["<leave types that go to HR alone, such as sick and family>"],
        "notice_days": {"<leave type>": 0},
        "remind_working_days": 2,
        "standin_working_days": 4,
    }, pos=[260, 600])
    for trig in (T, D, M):
        w.connect(trig, "Config")
    w.switch("Which event?", f"={{{{ $('{D}').isExecuted ? 'decision' : $('{M}').isExecuted ? 'morning' : 'request' }}}}",
             ["request", "decision", "morning"], pos=[520, 600])
    w.connect("Config", "Which event?")
    cfg = "$('Config').item.json"
    msg = f"={{{{ {cfg}.messaging_url }}}}/messages"
    req_url = f"={{{{ {cfg}.requests_url }}}}/requests"

    # ---- Step 2: listed requester; sick or family leave to HR alone -------------------
    w.http("Step 2: Read the employee list", "GET", f"={{{{ {cfg}.employees_url }}}}/employees",
           query={"_wrap": "1", "email": f"={{{{ {B}.employee }}}}"}, write=False, error_output=False, pos=[780, 0])
    w.code("Step 2: Rule: listed? protected?", ROUTE_JS, mode="runOnceForAllItems", pos=[1040, 0])
    w.switch("Route", "={{ $json.route }}", ["check", "hr", "unlisted", "cancel"], pos=[1300, 0])
    w.connect("Which event?", "Step 2: Read the employee list", output=0)
    w.chain("Step 2: Read the employee list", "Step 2: Rule: listed? protected?", "Route")

    w.http("Step 2: To HR alone", "PUT", f"{req_url}/{{{{ {B}.request_id }}}}",
           body=f"={{{{ JSON.stringify({{ id: {B}.request_id, employee_id: {EMP}.id, employee: {B}.employee, name: {EMP}.name, type: {B}.type, "
                f"start: {B}.start, end: {B}.end, status: 'with HR', decider: {CFG}.hr_owner, sent_on: new Date().toISOString().slice(0, 10) }}) }}}}",
           write=True, pos=[1560, -400])
    w.http("Step 2: Send it to Aisha", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.hr_owner, subject: 'Leave request ' + {B}.request_id + ' for you alone', "
                f"text: {EMP}.name + ': ' + {B}.type + ' leave, ' + {B}.start + ' to ' + {B}.end + '. Not sent to the manager.' }}) }}}}",
           write=True, pos=[1820, -400])
    w.decision_log("Step 2: Decision log: to HR alone", f"{B}.request_id", "'to HR alone'", "JSON.stringify({ route: 'protected type' })", pos=[2080, -400])
    w.connect("Route", "Step 2: To HR alone", output=1)
    w.chain("Step 2: To HR alone", "Step 2: Send it to Aisha", "Step 2: Decision log: to HR alone")

    w.exception("Step 2: Exception queue: unlisted requester", f"{B}.request_id", "unlisted requester",
                f"'Requester ' + {B}.employee + ' is not on the employee list; nothing sent'", f"{CFG}.hr_owner", pos=[1560, -240])
    w.http("Step 2: Tell Aisha", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.hr_owner, subject: 'Leave request from an unlisted requester', "
                f"text: {B}.employee + ' asked for ' + {B}.type + ' leave, ' + {B}.start + ' to ' + {B}.end + '. Nothing was sent.' }}) }}}}",
           write=True, error_output=False, pos=[1820, -240])
    w.connect("Route", "Step 2: Exception queue: unlisted requester", output=2)
    w.connect("Step 2: Exception queue: unlisted requester", "Step 2: Tell Aisha")

    # ---- Step 8 (cancellation): mark it, HR reverses it, the employee is told ---------
    w.http("Step 8: Read the request to cancel", "GET", req_url, query={"_wrap": "1", "id": f"={{{{ {B}.request_id }}}}"},
           write=False, error_output=False, pos=[1560, -80])
    w.code("Step 8: Rule: still cancellable?", CANCEL_JS, mode="runOnceForAllItems", pos=[1820, -80])
    w.http("Step 8: Mark it cancelled", "PATCH", f"{req_url}/{{{{ $json.id }}}}",
           body="={{ JSON.stringify({ status: 'cancelled', cancelled_on: new Date().toISOString().slice(0, 10) }) }}", write=True, pos=[2080, -80])
    can = "$('Step 8: Rule: still cancellable?').item.json"
    w.http("Step 8: Ask Aisha to reverse it", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.hr_owner, subject: 'Leave cancelled: ' + {can}.id, "
                f"text: {can}.name + ' cancelled ' + {can}.type + ' leave, ' + {can}.start + ' to ' + {can}.end + ' (was ' + {can}.was + '). Reverse it if recorded.' }}) }}}}",
           write=True, pos=[2340, -80])
    w.connect("Route", "Step 8: Read the request to cancel", output=3)
    w.chain("Step 8: Read the request to cancel", "Step 8: Rule: still cancellable?", "Step 8: Mark it cancelled", "Step 8: Ask Aisha to reverse it")

    # ---- Step 3: duplicate key, employee, type and dates: if open, stop ----------------
    w.pg("Step 3: Reserve key", RESERVE_SQL, args=[json.dumps(RID), KEY], pos=[1560, 160],
         notes="Key log: an open request with the same employee, type and dates stops here; a closed one may be asked again.")
    w.if_("New or closed key?", "={{ $json.is_new }}", pos=[1820, 160])
    w.noop("Open duplicate: stop", pos=[2080, 40], notes="The same request is already open.")
    w.connect("Route", "Step 3: Reserve key", output=0)
    w.connect("Step 3: Reserve key", "New or closed key?")
    w.connect("New or closed key?", "Open duplicate: stop", output=1)

    # ---- Steps 4 and 5: balance, then the rules; each failure a warning ---------------
    w.http("Step 4: Read today's balance", "GET", f"={{{{ {cfg}.balances_url }}}}/balances",
           query={"_wrap": "1", "employee_id": f"={{{{ {EMP}.id }}}}"}, write=False, error_output=False, pos=[2080, 200])
    w.http("Step 5: Read the request list", "GET", req_url, query={"_wrap": "1"}, write=False, error_output=False, pos=[2340, 200])
    w.code("Step 5: Rules: dates, notice, balance, overlap", CHECK_JS, mode="runOnceForAllItems", pos=[2600, 200],
           notes="Warnings tell the manager a fact; never a reason to refuse.")
    w.connect("New or closed key?", "Step 4: Read today's balance", output=0)
    w.chain("Step 4: Read today's balance", "Step 5: Read the request list", "Step 5: Rules: dates, notice, balance, overlap")

    # ---- Step 6: to the manager, with warnings and who else is off --------------------
    chk = "$('Step 5: Rules: dates, notice, balance, overlap').first().json"
    w.http("Step 6: Put it before the manager", "PUT", f"{req_url}/{{{{ {B}.request_id }}}}",
           body=f"={{{{ JSON.stringify({{ id: {B}.request_id, key: {KEY}, employee_id: {EMP}.id, employee: {B}.employee, name: {EMP}.name, "
                f"type: {B}.type, start: {B}.start, end: {B}.end, days: $json.days, warnings: $json.warnings, who_else_off: $json.who_else_off, "
                f"manager: {EMP}.manager, stand_in: {EMP}.stand_in, decider: {EMP}.manager, status: 'with manager', "
                f"sent_on: new Date().toISOString().slice(0, 10), reminded: false }}) }}}}",
           write=True, pos=[2860, 200])
    w.http("Step 6: Ask the manager", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {EMP}.manager, subject: 'Leave request ' + {B}.request_id + ' from ' + {EMP}.name, "
                f"text: {B}.type + ' leave, ' + {B}.start + ' to ' + {B}.end + ' (' + {chk}.days + ' days). Warnings: ' + ({chk}.warnings.join('; ') || 'none') + "
                f"'. Also off: ' + ({chk}.who_else_off.join(', ') || 'nobody') + '.' }}) }}}}",
           write=True, pos=[3120, 200])
    w.decision_log("Step 8: Decision log: to the manager", f"{B}.request_id", "'to the manager'",
                   f"JSON.stringify({{ days: {chk}.days, warnings: {chk}.warnings }})", pos=[3380, 200])
    w.chain("Step 5: Rules: dates, notice, balance, overlap", "Step 6: Put it before the manager", "Step 6: Ask the manager",
            "Step 8: Decision log: to the manager")

    # ---- Step 6 decision, step 7 record, step 8 notify and log ------------------------
    w.http("Step 6: Read the request", "GET", req_url, query={"_wrap": "1", "id": f"={{{{ $('{D}').first().json.body.request_id }}}}"},
           write=False, error_output=False, pos=[780, 900])
    w.code("Step 6: Rule: still open?", DECIDED_JS, mode="runOnceForAllItems", pos=[1040, 900])
    w.http("Step 6: Record the decision", "PATCH", f"{req_url}/{{{{ $json.id }}}}",
           body="={{ JSON.stringify({ status: $json.decision, decided_by: $json.decided_by, decided_on: $json.decided_on }) }}",
           write=True, pos=[1300, 900])
    dec = "$('Step 6: Rule: still open?').item.json"
    w.if_("Approved?", f"={{{{ {dec}.decision }}}}", op="equals", right="approved", pos=[1560, 900])
    w.http("Step 7: To Aisha's to-record list", "POST", f"={{{{ {cfg}.record_list_url }}}}/items",
           body=f"={{{{ JSON.stringify({{ request_id: {dec}.id, employee_id: {dec}.employee_id, name: {dec}.name, type: {dec}.type, start: {dec}.start, "
                f"end: {dec}.end, days: {dec}.days, warnings: {dec}.warnings || [], decided_by: {dec}.decided_by, task: 'Re-check the balance as you record it' }}) }}}}",
           write=True, pos=[1820, 820])
    w.http("Step 8: Notify the employee", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {dec}.employee, subject: 'Your leave request ' + {dec}.id + ' was ' + {dec}.decision, "
                f"text: {dec}.type + ' leave, ' + {dec}.start + ' to ' + {dec}.end + ': ' + {dec}.decision + ' by ' + {dec}.decided_by + '.' }}) }}}}",
           write=True, pos=[2080, 900])
    w.finish_key("Close the key", f"{dec}.key || ''", "done", f"'closed: ' + {dec}.decision", pos=[2340, 900])
    w.decision_log("Step 8: Decision log: decided", f"{dec}.id", f"{dec}.decision", f"JSON.stringify({{ decided_by: {dec}.decided_by, warnings: {dec}.warnings || [] }})",
                   pos=[2600, 900])
    w.connect("Which event?", "Step 6: Read the request", output=1)
    w.chain("Step 6: Read the request", "Step 6: Rule: still open?", "Step 6: Record the decision", "Approved?")
    w.connect("Approved?", "Step 7: To Aisha's to-record list", output=0)
    w.connect("Approved?", "Step 8: Notify the employee", output=1)
    w.connect("Step 7: To Aisha's to-record list", "Step 8: Notify the employee")
    w.chain("Step 8: Notify the employee", "Close the key", "Step 8: Decision log: decided")

    # Cancellation, continued: the employee is told and the key closes.
    w.http("Step 8: Notify the employee of the cancellation", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {can}.employee, subject: 'Your leave request ' + {can}.id + ' is cancelled', "
                f"text: {can}.type + ' leave, ' + {can}.start + ' to ' + {can}.end + ' is cancelled.' }}) }}}}",
           write=True, pos=[2600, -80])
    w.finish_key("Close the key: cancelled", f"{can}.key || ''", "done", "'closed: cancelled'", pos=[2860, -80])
    w.decision_log("Step 8: Decision log: cancelled", f"{can}.id", "'cancelled'", f"JSON.stringify({{ was: {can}.was }})", pos=[3120, -80])
    w.chain("Step 8: Ask Aisha to reverse it", "Step 8: Notify the employee of the cancellation", "Close the key: cancelled", "Step 8: Decision log: cancelled")

    # ---- Step 6 reminders ----------------------------------------------------------
    w.http("Step 6: Read requests with the manager", "GET", req_url, query={"_wrap": "1", "status": "with manager"},
           write=False, error_output=False, pos=[780, 1200])
    w.code("Step 6: Rule: 2 or 4 working days?", REMIND_JS, mode="runOnceForAllItems", pos=[1040, 1200])
    w.switch("Remind or stand-in?", "={{ $json.action }}", ["remind", "stand-in"], pos=[1300, 1200])
    w.connect("Which event?", "Step 6: Read requests with the manager", output=2)
    w.chain("Step 6: Read requests with the manager", "Step 6: Rule: 2 or 4 working days?", "Remind or stand-in?")
    rem = "$('Step 6: Rule: 2 or 4 working days?').item.json"
    w.http("Step 6: Remind the manager", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {rem}.manager, subject: 'Reminder: leave request ' + {rem}.id + ' from ' + {rem}.name, "
                f"text: 'Waiting ' + {rem}.waited + ' working days. Warnings: ' + (({rem}.warnings || []).join('; ') || 'none') }}) }}}}",
           write=True, pos=[1560, 1120])
    w.http("Step 6: Mark reminded", "PATCH", f"{req_url}/{{{{ {rem}.id }}}}", body="={{ JSON.stringify({ reminded: true }) }}",
           write=True, pos=[1820, 1120])
    w.connect("Remind or stand-in?", "Step 6: Remind the manager", output=0)
    w.connect("Step 6: Remind the manager", "Step 6: Mark reminded")
    w.http("Step 6: Move it to the stand-in", "PATCH", f"{req_url}/{{{{ $json.id }}}}",
           body="={{ JSON.stringify({ status: 'with stand-in', decider: $json.stand_in }) }}", write=True, pos=[1560, 1300])
    w.http("Step 6: Ask the stand-in", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {rem}.stand_in, subject: 'Leave request ' + {rem}.id + ' from ' + {rem}.name + ': please decide', "
                f"text: {rem}.manager + ' has not answered in ' + {rem}.waited + ' working days. Warnings: ' + (({rem}.warnings || []).join('; ') || 'none') }}) }}}}",
           write=True, pos=[1820, 1300])
    w.http("Step 6: Tell Aisha", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.hr_owner, subject: 'Leave request ' + {rem}.id + ' moved to the stand-in', "
                f"text: 'No answer from ' + {rem}.manager + ' in ' + {rem}.waited + ' working days; sent to ' + {rem}.stand_in + '.' }}) }}}}",
           write=True, pos=[2080, 1300])
    w.connect("Remind or stand-in?", "Step 6: Move it to the stand-in", output=1)
    w.chain("Step 6: Move it to the stand-in", "Step 6: Ask the stand-in", "Step 6: Tell Aisha")

    # ---- failures: writes never retry ----------------------------------------------
    w.exception("Exception queue: employee notice failed", f"{dec}.id", "employee notice failed",
                "'The employee was not told (' + (($json.error && $json.error.message) || 'send error') + '); HR tells them'",
                f"{CFG}.hr_owner", pos=[2340, 1100])
    w.connect("Step 8: Notify the employee", "Exception queue: employee notice failed", output=1)
    w.exception("Exception queue: cancellation notice failed", f"{can}.id", "employee notice failed",
                "'The employee was not told of the cancellation; HR tells them'", f"{CFG}.hr_owner", pos=[2860, 100])
    w.connect("Step 8: Notify the employee of the cancellation", "Exception queue: cancellation notice failed", output=1)
    w.finish_key("Mark key failed", KEY, "failed", "'write failed: ' + (($json.error && $json.error.message) || 'unknown')", pos=[3120, 500])
    w.exception("Exception queue: request write failed", f"{B}.request_id", "write failed",
                "'The request or the manager message was not written, never retried; check it'", f"{CFG}.hr_owner", pos=[3380, 500])
    for n in ["Step 6: Put it before the manager", "Step 6: Ask the manager"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: request write failed")
    w.exception("Exception queue: write failed", f"($('{T}').isExecuted ? {B}.request_id : $('{D}').first().json.body.request_id)", "write failed",
                "'A leave write failed, never retried: ' + (($json.error && $json.error.message) || 'unknown')", f"{CFG}.hr_owner", pos=[3380, 700])
    for n in ["Step 2: To HR alone", "Step 2: Send it to Aisha", "Step 8: Mark it cancelled", "Step 8: Ask Aisha to reverse it",
              "Step 6: Record the decision", "Step 7: To Aisha's to-record list"]:
        w.connect(n, "Exception queue: write failed", output=1)
    w.exception("Exception queue: reminder failed", f"{rem}.id", "reminder failed",
                "'A reminder or stand-in step failed, never retried; chase the decider'", f"{CFG}.hr_owner", pos=[2340, 1500])
    for n in ["Step 6: Remind the manager", "Step 6: Mark reminded", "Step 6: Move it to the stand-in", "Step 6: Ask the stand-in", "Step 6: Tell Aisha"]:
        w.connect(n, "Exception queue: reminder failed", output=1)
    return w
