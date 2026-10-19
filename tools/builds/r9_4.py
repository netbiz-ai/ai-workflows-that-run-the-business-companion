"""R9.4 Remove a leaver's access the same day: rules only, no AI step.

Source: book Chapter 9, recipe R9.4, build steps 1 to 9 (recipes/R9.4/build-spec.md).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import Workflow  # noqa: E402

RID = "R9.4"
DAILY = "Step 1: Daily leaver check after closing"
NOW = "Step 1: Immediate leaver"
TICK = "Step 7: Person ticks an item"
CLOSE = "Step 9: Owen closes the case"
CFG = "$('Config').first().json"
LV = "$('Step 1: Leavers to process').item.json"
ITEM = "$('Steps 4 to 6: Items to remove').item.json"

DATES_JS = r"""
const isoToday = () => new Date().toISOString().slice(0, 10);
const day = d => new Date(String(d).slice(0, 10) + 'T00:00:00Z');
// The date a number of working days (Monday to Friday) after a date.
function addWorkingDays(d, n) {
  let x = day(d), k = 0;
  while (k < n) { x = new Date(x.getTime() + 86400000); if (x.getUTCDay() % 6 !== 0) k++; }
  return x.toISOString().slice(0, 10);
}
"""

LEAVERS_JS = rf"""
// Step 1: every leaver to process now; an entry not made by HR is flagged here.
const cfg = {CFG};
const leavers = $input.all().flatMap(i => i.json.items || []);
return leavers.map(l => ({{ json: Object.assign({{}}, l, {{
  by_hr: String(l.entered_by || '').toLowerCase() === String(cfg.leaver_list_owner).toLowerCase(),
  case_id: l.employee_id + '-' + String(l.last_day).slice(0, 10),
  key: l.employee_id + ':' + String(l.last_day).slice(0, 10) }}) }}));
"""

VALID_JS = rf"""
// Step 2: resume at the first unconfirmed item. Step 3: an empty inventory, or one listing an
// administrator account, stops everything: empty means unknown.
const l = {LV};
const inventory = $('Step 3: Read the inventory').item.json.items || [];
const evidence = $json.items || [];
const done = new Set(evidence.filter(e => e.status === 'confirmed').map(e => e.item_id));
const tasked = new Set(evidence.filter(e => e.status === 'open' && e.task_id).map(e => e.item_id));
const base = {{ case_id: l.case_id, key: l.key, leaver: {{ id: l.id, employee_id: l.employee_id, name: l.name, last_day: l.last_day, manager: l.manager }} }};
if (!inventory.length) return {{ json: Object.assign(base, {{ valid: false, why: 'inventory empty' }}) }};
const admins = inventory.filter(i => i.admin);
if (admins.length) return {{ json: Object.assign(base, {{ valid: false, why: 'inventory lists an administrator account: ' + admins.map(i => i.system).join(', ') }}) }};
const rank = i => (i.kind === 'sso account' ? 0 : 1);
const todo = inventory.filter(i => !done.has(i.id) && !tasked.has(i.id)).sort((a, b) => rank(a) - rank(b));
return {{ json: Object.assign(base, {{ valid: true, item_ids: inventory.map(i => i.id), todo }}) }};
"""

ITEMS_JS = rf"""
// Steps 4 to 6: one item per removal still to do, the SSO account first.
// Groups go with the SSO account; apps with a connection are removed through it;
// everything else is a task for its administrator, or the manager for keys, codes and devices.
const cfg = {CFG};
const out = [];
for (const c of $input.all().map(i => i.json)) {{
  const sso = c.todo.find(i => i.kind === 'sso account');
  for (const i of c.todo) {{
    if (i.kind === 'group' && sso) continue;
    const base = {{ case_id: c.case_id, key: c.key, leaver: c.leaver, item_id: i.id, evidence_id: c.case_id + '-' + i.id,
      kind: i.kind, system: i.system, account: i.account }};
    if (i.kind === 'sso account') {{
      out.push({{ json: Object.assign(base, {{ action: 'sso', covers: c.todo.filter(g => g.kind === 'group').map(g => g.id) }}) }});
    }} else if (i.connection && cfg[i.connection + '_url']) {{
      out.push({{ json: Object.assign(base, {{ action: 'connection', url: cfg[i.connection + '_url'] + '/users/' + i.account }}) }});
    }} else {{
      const collect = ['key', 'alarm code', 'device'].includes(i.kind);
      const shared = ['shared login', 'token'].includes(i.kind);
      const task = collect ? `Collect the ${{i.kind}} "${{i.account}}" from ${{c.leaver.name}}`
        : shared ? (i.kind === 'token' ? `Revoke the token "${{i.account}}" (${{i.system}})` : `Change the shared password for ${{i.system}} (${{i.account}})`)
        : `Remove ${{c.leaver.name}}'s account "${{i.account}}" from ${{i.system}}`;
      const assignee = collect ? c.leaver.manager : (i.administrator || cfg.access_owner);
      out.push({{ json: Object.assign(base, {{ action: 'task', assignee, task }}) }});
    }}
  }}
}}
return out;
"""

COVERED_JS = rf"""
// Step 4: group memberships end with the SSO account.
const now = new Date().toISOString();
return $input.all().flatMap((x, n) => {{
  const s = $('Steps 4 to 6: Items to remove').itemMatching(n).json;
  return (s.covers || []).map(g => ({{ json: {{ id: s.case_id + '-' + g, case_id: s.case_id, item_id: g, status: 'confirmed',
    action: 'ended with the SSO account', by: 'response: SSO disabled', at: now }} }}));
}});
"""

CASE_JS = r"""
// Step 7 runs after every pass: from the leaver run, or after a person's tick.
if ($('Step 7: Person ticks an item').isExecuted) {
  return [{ json: { case_id: $('Step 7: Rule: open item?').first().json.case_id } }];
}
return $input.all().map(i => ({ json: { case_id: i.json.case_id, key: i.json.key, leaver: i.json.leaver, item_ids: i.json.item_ids } }));
"""

CONFIRMED_JS = DATES_JS + rf"""
// Step 7: every item confirmed, by a response or a person's timed tick.
const cfg = {CFG};
const c = $('Step 7: Case to check').item.json;
const existing = ($('Step 7: Read the case').item.json.items || [])[0] || {{}};
const evidence = $json.items || [];
const l = c.leaver || {{}};
const record = Object.assign({{ id: c.case_id, key: c.key, employee_id: l.employee_id, name: l.name, last_day: l.last_day, manager: l.manager,
  deadline_on: l.last_day ? addWorkingDays(l.last_day, cfg.deadline_working_days) : null, ticketed: false, opened: new Date().toISOString() }},
  existing, c.item_ids ? {{ items: c.item_ids }} : {{}});
const confirmed = new Set(evidence.filter(e => e.status === 'confirmed').map(e => e.item_id));
const items = record.items || [];
const all = items.length > 0 && items.every(i => confirmed.has(i));
const before = existing.status;
record.unconfirmed = items.filter(i => !confirmed.has(i));
record.status = before === 'closed' ? 'closed' : all ? 'all confirmed; to close' : 'open';
return {{ json: {{ record, newly_confirmed: record.status === 'all confirmed; to close' && before !== record.status }} }};
"""

TICK_JS = r"""
// Step 7: a person's tick confirms an item that is still open; the time is recorded.
const t = $('Step 7: Person ticks an item').first().json.body;
const e = ($('Step 7: Read the item').first().json.items || [])[0];
if (!e || e.status === 'confirmed' || !t.by) return [];
return [{ json: { id: e.id, case_id: e.case_id, by: t.by, at: new Date().toISOString() } }];
"""

OVERDUE_JS = rf"""
// Step 8: a case still open at its deadline gets an IT ticket and an alert, once.
const today = new Date().toISOString().slice(0, 10);
return ($('Step 8: Read open cases').first().json.items || [])
  .filter(c => c.deadline_on && c.deadline_on <= today && !c.ticketed)
  .map(c => ({{ json: c }}));
"""

CLOSE_JS = rf"""
// Step 9: only the access owner closes, and never with an item unconfirmed.
const cfg = {CFG};
const b = $('{CLOSE}').first().json.body;
const c = ($('Step 9: Read the case').first().json.items || [])[0];
const evidence = $('Step 9: Read its evidence').first().json.items || [];
const confirmed = new Set(evidence.filter(e => e.status === 'confirmed').map(e => e.item_id));
let why = '';
if (!c) why = 'no such case';
else if (String(b.by || '').toLowerCase() !== String(cfg.access_owner).toLowerCase()) why = 'only the access owner closes a case';
else if (c.status === 'closed') why = 'already closed';
else if (!(c.items || []).length || !(c.items || []).every(i => confirmed.has(i))) why = 'items unconfirmed: ' + (c.items || []).filter(i => !confirmed.has(i)).join(', ');
return [{{ json: {{ ok: !why, why, case_id: b.case_id, key: c && c.key, by: b.by }} }}];
"""


def build() -> Workflow:
    w = Workflow(RID, "R9.4 Remove a leaver's access the same day")
    w.schedule(DAILY, 19, "Set the hour to after your closing time. Processes leavers whose last day is today, then the deadline check (step 8).",
               pos=[0, 0])
    w.webhook(NOW, "r9-4-immediate", "Your leaver list calls this when an entry is saved as \"immediate\". Body: {leaver_id}.", pos=[0, 200])
    w.webhook(TICK, "r9-4-tick", "A person ticks a task done. Body: {evidence_id, by}.", pos=[0, 1400])
    w.webhook(CLOSE, "r9-4-close", "The access owner closes a case. Body: {case_id, by}.", pos=[0, 1700])
    w.config("Config", {
        "leavers_url": "https://<your leaver list API>",
        "inventory_url": "https://<your access inventory API>",
        "directory_url": "https://<your directory API>",
        "pos_url": "https://<your point-of-sale API>",
        "tasks_url": "https://<your task list API>",
        "evidence_url": "https://<your evidence list API>",
        "itsm_url": "https://<your IT provider's ticket API>",
        "messaging_url": "https://<your messaging API>",
        "leaver_list_owner": "<your HR owner, the only person who edits the leaver list>",
        "access_owner": "<your IT owner, who checks evidence and closes cases>",
        "deadline_working_days": 1,
    }, pos=[260, 700])
    for trig in (DAILY, NOW, TICK, CLOSE):
        w.connect(trig, "Config")
    w.switch("Which event?", f"={{{{ $('{TICK}').isExecuted ? 'tick' : $('{CLOSE}').isExecuted ? 'close' : $('{NOW}').isExecuted ? 'immediate' : 'daily' }}}}",
             ["daily", "immediate", "tick", "close"], pos=[520, 700])
    w.connect("Config", "Which event?")
    cfg = "$('Config').item.json"
    msg = f"={{{{ {cfg}.messaging_url }}}}/messages"
    ev_url = f"={{{{ {cfg}.evidence_url }}}}"

    # ---- Step 1: today's leavers, or one at once; only HR's entries ------------------
    w.http("Step 1: Read today's leavers", "GET", f"={{{{ {cfg}.leavers_url }}}}/leavers",
           query={"_wrap": "1", "last_day": "={{ new Date().toISOString().slice(0, 10) }}"}, write=False, error_output=False, pos=[780, 0])
    w.http("Step 1: Read the immediate leaver", "GET", f"={{{{ {cfg}.leavers_url }}}}/leavers",
           query={"_wrap": "1", "id": f"={{{{ $('{NOW}').first().json.body.leaver_id }}}}"}, write=False, error_output=False, pos=[780, 200])
    w.connect("Which event?", "Step 1: Read today's leavers", output=0)
    w.connect("Which event?", "Step 1: Read the immediate leaver", output=1)
    w.code("Step 1: Leavers to process", LEAVERS_JS, mode="runOnceForAllItems", pos=[1040, 100])
    w.connect("Step 1: Read today's leavers", "Step 1: Leavers to process")
    w.connect("Step 1: Read the immediate leaver", "Step 1: Leavers to process")
    w.if_("Entered by HR?", "={{ $json.by_hr }}", pos=[1300, 100])
    w.connect("Step 1: Leavers to process", "Entered by HR?")
    w.exception("Step 1: Exception queue: not entered by HR", "$json.id", "not entered by HR",
                "'Leaver entry ' + $json.id + ' was made by ' + $json.entered_by + '; nothing removed'", f"{CFG}.leaver_list_owner", pos=[1560, -160])
    w.http("Step 1: Alert Aisha", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.leaver_list_owner, subject: 'Leaver entry not made by you: nothing removed', "
                f"text: 'Entry ' + {LV}.id + ' for ' + {LV}.name + ' was made by ' + {LV}.entered_by + '. Confirm it and enter it yourself.' }}) }}}}",
           write=True, error_output=False, pos=[1820, -160])
    w.connect("Entered by HR?", "Step 1: Exception queue: not entered by HR", output=1)
    w.connect("Step 1: Exception queue: not entered by HR", "Step 1: Alert Aisha")

    # ---- Step 2: key, employee and date; resume. Step 3: inventory valid? -------------------
    w.reserve_key("Step 2: Reserve key", "$json.key", pos=[1560, 100])
    w.http("Step 3: Read the inventory", "GET", f"={{{{ {cfg}.inventory_url }}}}/items",
           query={"_wrap": "1", "person_id": f"={{{{ {LV}.employee_id }}}}"}, write=False, error_output=False, pos=[1820, 100])
    w.http("Step 2: Read the evidence so far", "GET", f"{ev_url}/items",
           query={"_wrap": "1", "case_id": f"={{{{ {LV}.case_id }}}}"}, write=False, error_output=False, pos=[2080, 100],
           notes="A key already logged resumes at the first unconfirmed item; nothing is done twice.")
    w.code("Step 3: Rule: inventory valid?", VALID_JS, pos=[2340, 100])
    w.if_("Inventory valid?", "={{ $json.valid }}", pos=[2600, 100])
    w.connect("Entered by HR?", "Step 2: Reserve key", output=0)
    w.chain("Step 2: Reserve key", "Step 3: Read the inventory", "Step 2: Read the evidence so far", "Step 3: Rule: inventory valid?", "Inventory valid?")
    inv = "$('Step 3: Rule: inventory valid?').item.json"
    w.exception("Step 3: Exception queue: inventory not valid", f"{inv}.case_id", "inventory not valid",
                f"{inv}.why + '; nothing removed'", f"{CFG}.access_owner", pos=[2860, -80])
    w.http("Step 3: Alert Owen", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.access_owner, subject: 'Leaver ' + {inv}.leaver.name + ': stopped, nothing removed', "
                f"text: {inv}.why + '. Empty means unknown: build the inventory, then save the leaver again.' }}) }}}}",
           write=True, error_output=False, pos=[3120, -80])
    w.finish_key("Mark key failed: inventory", f"{inv}.key", "failed", f"'stopped: ' + {inv}.why", pos=[3380, -80])
    w.connect("Inventory valid?", "Step 3: Exception queue: inventory not valid", output=1)
    w.chain("Step 3: Exception queue: inventory not valid", "Step 3: Alert Owen", "Mark key failed: inventory")

    # ---- Steps 4 to 6: each item, SSO first ----------------------------------------
    w.code("Steps 4 to 6: Items to remove", ITEMS_JS, mode="runOnceForAllItems", pos=[2860, 160])
    w.switch("How is it removed?", "={{ $json.action }}", ["sso", "connection", "task"], pos=[3120, 160])
    w.connect("Inventory valid?", "Steps 4 to 6: Items to remove", output=0)
    w.connect("Steps 4 to 6: Items to remove", "How is it removed?")
    d_user = f"={{{{ {cfg}.directory_url }}}}/users/{{{{ $json.account }}}}"
    w.http("Step 4: Disable the SSO account", "PATCH", d_user, body="={{ JSON.stringify({ enabled: false }) }}", write=True, pos=[3380, 0],
           notes="Disable, never delete. A write: never retried.")
    w.http("Step 4: End its sessions", "POST", f"={{{{ {cfg}.directory_url }}}}/sign_in_revocations",
           body=f"={{{{ JSON.stringify({{ user: {ITEM}.account }}) }}}}", write=True, pos=[3640, 0])
    now_expr = "new Date().toISOString()"
    w.http("Step 4: Evidence: SSO disabled", "PUT", f"{ev_url}/items/{{{{ {ITEM}.evidence_id }}}}",
           body=f"={{{{ JSON.stringify({{ id: {ITEM}.evidence_id, case_id: {ITEM}.case_id, item_id: {ITEM}.item_id, system: {ITEM}.system, "
                f"account: {ITEM}.account, action: 'disabled; sessions ended', status: 'confirmed', by: 'response: directory', at: {now_expr} }}) }}}}",
           write=True, pos=[3900, 0])
    w.code("Step 4: Groups ended with the account", COVERED_JS, mode="runOnceForAllItems", pos=[4160, 0])
    w.http("Step 4: Evidence: group ended", "PUT", f"{ev_url}/items/{{{{ $json.id }}}}",
           body="={{ JSON.stringify($json) }}", write=True, pos=[4420, 0])
    w.connect("How is it removed?", "Step 4: Disable the SSO account", output=0)
    w.chain("Step 4: Disable the SSO account", "Step 4: End its sessions", "Step 4: Evidence: SSO disabled",
            "Step 4: Groups ended with the account", "Step 4: Evidence: group ended")

    w.http("Step 5: Remove from the app", "PATCH", "={{ $json.url }}", body="={{ JSON.stringify({ active: false }) }}", write=True, pos=[3380, 160],
           notes="Through the app's connection: the Config field <connection>_url. Removes the user's access; never deletes.")
    w.http("Step 5: Evidence: removed", "PUT", f"{ev_url}/items/{{{{ {ITEM}.evidence_id }}}}",
           body=f"={{{{ JSON.stringify({{ id: {ITEM}.evidence_id, case_id: {ITEM}.case_id, item_id: {ITEM}.item_id, system: {ITEM}.system, "
                f"account: {ITEM}.account, action: 'removed through its connection', status: 'confirmed', by: 'response: ' + {ITEM}.system, at: {now_expr} }}) }}}}",
           write=True, pos=[3640, 160])
    w.connect("How is it removed?", "Step 5: Remove from the app", output=1)
    w.connect("Step 5: Remove from the app", "Step 5: Evidence: removed")

    w.http("Steps 5 and 6: Task a person", "POST", f"={{{{ {cfg}.tasks_url }}}}/tasks",
           body=f"={{{{ JSON.stringify({{ id: $json.evidence_id, case_id: $json.case_id, assignee: $json.assignee, task: $json.task, "
                f"tick: 'Tick it done with your name; the time is recorded' }}) }}}}",
           write=True, pos=[3380, 320])
    w.http("Steps 5 and 6: Evidence: task open", "PUT", f"{ev_url}/items/{{{{ {ITEM}.evidence_id }}}}",
           body=f"={{{{ JSON.stringify({{ id: {ITEM}.evidence_id, case_id: {ITEM}.case_id, item_id: {ITEM}.item_id, system: {ITEM}.system, "
                f"account: {ITEM}.account, action: {ITEM}.task, task_id: {ITEM}.evidence_id, assignee: {ITEM}.assignee, status: 'open', at: {now_expr} }}) }}}}",
           write=True, pos=[3640, 320])
    w.connect("How is it removed?", "Steps 5 and 6: Task a person", output=2)
    w.connect("Steps 5 and 6: Task a person", "Steps 5 and 6: Evidence: task open")

    # A removal fails: never retried; IT ticket, alert, exception queue; the case stays open.
    w.finish_key("Mark key failed", f"{ITEM}.key", "failed", f"'removal failed: ' + {ITEM}.system", pos=[3900, 500])
    w.http("Step 8: IT ticket: removal failed", "POST", f"={{{{ {cfg}.itsm_url }}}}/tickets",
           body=f"={{{{ JSON.stringify({{ case_id: {ITEM}.case_id, subject: 'Leaver access not removed: ' + {ITEM}.system, "
                f"detail: {ITEM}.kind + ' ' + {ITEM}.account + ' for ' + {ITEM}.leaver.name + ' failed; remove it by hand' }}) }}}}",
           write=True, error_output=False, pos=[4160, 500])
    w.http("Step 8: Alert Owen: removal failed", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.access_owner, subject: 'Leaver ' + {ITEM}.leaver.name + ': ' + {ITEM}.system + ' not removed', "
                f"text: 'The ' + {ITEM}.kind + ' ' + {ITEM}.account + ' failed and was not retried. IT ticket raised; the case stays open.' }}) }}}}",
           write=True, error_output=False, pos=[4420, 500])
    w.exception("Exception queue: removal failed", f"{ITEM}.case_id", "removal failed",
                f"{ITEM}.system + ' ' + {ITEM}.account + ': never retried; remove it by hand'", f"{CFG}.access_owner", pos=[4680, 500])
    for n in ["Step 4: Disable the SSO account", "Step 4: End its sessions", "Step 4: Evidence: SSO disabled",
              "Step 5: Remove from the app", "Step 5: Evidence: removed", "Steps 5 and 6: Task a person", "Steps 5 and 6: Evidence: task open"]:
        w.connect(n, "Mark key failed", output=1)
    w.chain("Mark key failed", "Step 8: IT ticket: removal failed", "Step 8: Alert Owen: removal failed", "Exception queue: removal failed")

    # ---- Step 7: every item confirmed? (after the removals, and after each tick) -------------
    w.code("Step 7: Case to check", CASE_JS, mode="runOnceForAllItems", pos=[2860, 800])
    w.connect("Inventory valid?", "Step 7: Case to check", output=0)
    w.http("Step 7: Read the case", "GET", f"{ev_url}/cases", query={"_wrap": "1", "id": "={{ $json.case_id }}"},
           write=False, error_output=False, pos=[3120, 800])
    w.http("Step 7: Read the case evidence", "GET", f"{ev_url}/items",
           query={"_wrap": "1", "case_id": "={{ $('Step 7: Case to check').item.json.case_id }}"}, write=False, error_output=False, pos=[3380, 800])
    w.code("Step 7: Rule: every item confirmed?", CONFIRMED_JS, pos=[3640, 800])
    w.http("Step 9: Log the case", "PUT", f"{ev_url}/cases/{{{{ $json.record.id }}}}",
           body="={{ JSON.stringify($json.record) }}", write=True, error_output=False, pos=[3900, 800],
           notes="Evidence: each item, by whom and when, in its own list; run history does not last.")
    w.chain("Step 7: Case to check", "Step 7: Read the case", "Step 7: Read the case evidence", "Step 7: Rule: every item confirmed?", "Step 9: Log the case")
    rec = "$('Step 7: Rule: every item confirmed?').item.json"
    w.if_("All confirmed now?", f"={{{{ {rec}.newly_confirmed }}}}", pos=[4160, 800])
    w.http("Step 9: Ask Owen to check and close", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.access_owner, subject: 'Leaver ' + {rec}.record.name + ': every item confirmed', "
                f"text: 'Check the evidence for case ' + {rec}.record.id + ' and close it.' }}) }}}}",
           write=True, error_output=False, pos=[4420, 800])
    w.decision_log("Step 9: Decision log: all confirmed", f"{rec}.record.id", "'every item confirmed; to the access owner'",
                   f"JSON.stringify({{ items: ({rec}.record.items || []).length }})", pos=[4680, 800])
    w.connect("Step 9: Log the case", "All confirmed now?")
    w.chain("All confirmed now?", "Step 9: Ask Owen to check and close", "Step 9: Decision log: all confirmed")

    # ---- Step 8: unconfirmed at the deadline ----------------------------------------
    w.http("Step 8: Read open cases", "GET", f"{ev_url}/cases", query={"_wrap": "1", "status": "open"},
           write=False, error_output=False, pos=[780, 1100])
    w.code("Step 8: Rule: past the deadline?", OVERDUE_JS, mode="runOnceForAllItems", pos=[1040, 1100])
    w.connect("Which event?", "Step 8: Read open cases", output=0)
    w.connect("Step 8: Read open cases", "Step 8: Rule: past the deadline?")
    od = "$('Step 8: Rule: past the deadline?').item.json"
    w.http("Step 8: IT ticket: unconfirmed at the deadline", "POST", f"={{{{ {cfg}.itsm_url }}}}/tickets",
           body=f"={{{{ JSON.stringify({{ case_id: $json.id, subject: 'Leaver access unconfirmed at the deadline: ' + $json.name, "
                f"detail: 'Unconfirmed: ' + ($json.unconfirmed || []).join(', ') + '; remove them' }}) }}}}",
           write=True, error_output=False, pos=[1300, 1100])
    w.http("Step 8: Alert Owen", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.access_owner, subject: 'Leaver ' + {od}.name + ': unconfirmed at the deadline', "
                f"text: 'Unconfirmed: ' + ({od}.unconfirmed || []).join(', ') + '. IT ticket raised.' }}) }}}}",
           write=True, error_output=False, pos=[1560, 1100])
    w.http("Step 8: Mark the case ticketed", "PATCH", f"{ev_url}/cases/{{{{ {od}.id }}}}",
           body="={{ JSON.stringify({ ticketed: true }) }}", write=True, error_output=False, pos=[1820, 1100])
    w.chain("Step 8: Rule: past the deadline?", "Step 8: IT ticket: unconfirmed at the deadline", "Step 8: Alert Owen", "Step 8: Mark the case ticketed")

    # ---- Step 7: a person's timed tick --------------------------------------------------
    w.http("Step 7: Read the item", "GET", f"{ev_url}/items", query={"_wrap": "1", "id": f"={{{{ $('{TICK}').first().json.body.evidence_id }}}}"},
           write=False, error_output=False, pos=[780, 1400])
    w.code("Step 7: Rule: open item?", TICK_JS, mode="runOnceForAllItems", pos=[1040, 1400])
    w.http("Step 7: Record the tick", "PATCH", f"{ev_url}/items/{{{{ $json.id }}}}",
           body="={{ JSON.stringify({ status: 'confirmed', by: $json.by, at: $json.at }) }}", write=True, error_output=False, pos=[1300, 1400])
    w.connect("Which event?", "Step 7: Read the item", output=2)
    w.chain("Step 7: Read the item", "Step 7: Rule: open item?", "Step 7: Record the tick", "Step 7: Case to check")

    # ---- Step 9: Owen closes ---------------------------------------------------------
    w.http("Step 9: Read the case", "GET", f"{ev_url}/cases", query={"_wrap": "1", "id": f"={{{{ $('{CLOSE}').first().json.body.case_id }}}}"},
           write=False, error_output=False, pos=[780, 1700])
    w.http("Step 9: Read its evidence", "GET", f"{ev_url}/items", query={"_wrap": "1", "case_id": f"={{{{ $('{CLOSE}').first().json.body.case_id }}}}"},
           write=False, error_output=False, pos=[1040, 1700])
    w.code("Step 9: Rule: may it close?", CLOSE_JS, mode="runOnceForAllItems", pos=[1300, 1700])
    w.if_("Close it?", "={{ $json.ok }}", pos=[1560, 1700])
    w.connect("Which event?", "Step 9: Read the case", output=3)
    w.chain("Step 9: Read the case", "Step 9: Read its evidence", "Step 9: Rule: may it close?", "Close it?")
    cl = "$('Step 9: Rule: may it close?').item.json"
    w.http("Step 9: Close the case", "PATCH", f"{ev_url}/cases/{{{{ $json.case_id }}}}",
           body="={{ JSON.stringify({ status: 'closed', closed_by: $json.by, closed_at: new Date().toISOString() }) }}",
           write=True, error_output=False, pos=[1820, 1620])
    w.finish_key("Mark key done", f"{cl}.key", "done", f"'closed by ' + {cl}.by", pos=[2080, 1620])
    w.decision_log("Step 9: Decision log: closed", f"{cl}.case_id", "'closed'", f"JSON.stringify({{ closed_by: {cl}.by }})", pos=[2340, 1620])
    w.connect("Close it?", "Step 9: Close the case", output=0)
    w.chain("Step 9: Close the case", "Mark key done", "Step 9: Decision log: closed")
    w.http("Step 9: Not closed: tell Owen", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.access_owner, subject: 'Case ' + {cl}.case_id + ' not closed', text: {cl}.why }}) }}}}",
           write=True, error_output=False, pos=[1820, 1800])
    w.connect("Close it?", "Step 9: Not closed: tell Owen", output=1)
    return w
