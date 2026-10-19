"""R9.1 Run onboarding: accounts, equipment, training tasks and first-week checklist.

Source: book Chapter 9, recipe R9.1, build steps 1 to 9 (recipes/R9.1/build-spec.md);
AI step: recipes/R9.1/prompts/draft-checklist.md.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

RID = "R9.1"
T = "Step 1: Hire confirmed or changed"
A = "Step 8: Manager answers"
M = "Step 8: Morning check for silent managers"
H = f"$('{T}').first().json.body"
KEY = f"{H}.person_id"
CFG = "$('Config').first().json"

DATES_JS = r"""
const isoToday = () => new Date().toISOString().slice(0, 10);
const day = d => new Date(String(d).slice(0, 10) + 'T00:00:00Z');
const addDays = (d, n) => new Date(day(d).getTime() + n * 86400000).toISOString().slice(0, 10);
// Working days (Monday to Friday) after today, up to and including the date.
function workingDaysUntil(d) {
  const end = day(d); let n = 0;
  for (let x = new Date(day(isoToday()).getTime() + 86400000); x <= end; x = new Date(x.getTime() + 86400000)) {
    if (x.getUTCDay() % 6 !== 0) n++;
  }
  return n;
}
"""

COMPLETE_JS = DATES_JS + rf"""
// Step 2: role, manager, an approved template for the role, and a future start date; or back to Aisha.
const hire = {H};
const template = ($('Read the role template').first().json.items || [])[0] || null;
const missing = [];
if (!hire.role) missing.push('role');
if (!hire.manager) missing.push('manager');
if (!template) missing.push('approved template for the role');
if (!/^\d{{4}}-\d{{2}}-\d{{2}}/.test(String(hire.start_date || ''))) missing.push('start date');
else if (day(hire.start_date) <= day(isoToday())) missing.push('future start date');
return [{{ json: {{ complete: missing.length === 0, missing, template }} }}];
"""

MOVED_JS = DATES_JS + rf"""
// Step 3: the hire was logged before; a moved start moves the tasks, nothing else runs again.
const hire = {H};
const tasks = $('Step 3: Read the hire\'s tasks').first().json.items || [];
return tasks.filter(t => t.start_date !== hire.start_date)
  .map(t => ({{ json: {{ id: t.id, start_date: hire.start_date, due: addDays(hire.start_date, Number(t.offset_days || 0)), was: t.due }} }}));
"""

GROUPS_JS = rf"""
// Step 4: only the template's groups.
const t = $('Step 2: Rule: complete hire?').first().json.template;
return (t.groups || []).map(g => ({{ json: {{ group: g }} }}));
"""

TASKS_JS = DATES_JS + rf"""
// Step 5: the template's equipment and training tasks, each with its owner and a date from the start.
const hire = {H};
const t = $('Step 2: Rule: complete hire?').first().json.template;
return (t.tasks || []).map((x, i) => ({{ json: {{
  id: hire.person_id + '-' + (i + 1), person_id: hire.person_id, kind: x.kind, task: x.task, owner: x.owner,
  start_date: hire.start_date, offset_days: Number(x.offset_days || 0), due: addDays(hire.start_date, Number(x.offset_days || 0)),
  template_version: t.version, status: 'open' }} }}));
"""

CHECK_JS = AI_PARSE_JS + rf"""
// Step 7: use the draft only if every task comes from the inputs, every owner is in the
// directory and every day is 1 to 5; otherwise the template's checklist.
const hire = {H};
const t = $('Step 2: Rule: complete hire?').first().json.template;
const directory = $('Step 7: Read the directory').first().json.items || [];
const norm = s => String(s || '').trim().replace(/\s+/g, ' ').toLowerCase();
const inputs = new Set([...(t.checklist || []), ...(hire.notes || [])].map(r => norm(r.task)));
const people = new Set(directory.flatMap(u => [norm(u.name), norm(u.email)]).filter(Boolean));
const template = {{ source: 'template', rows: t.checklist || [] }};
const p = parseAi($('Step 6: AI call').first().json, ['rows']);
if (!p.ok) return [{{ json: Object.assign({{}}, template, {{ reason: 'AI output failed the check: ' + p.problem }}) }}];
const rows = p.value.rows;
const problems = [];
if (!Array.isArray(rows) || !rows.length) problems.push('no rows');
for (const r of (Array.isArray(rows) ? rows : [])) {{
  if (!Number.isInteger(r.day) || r.day < 1 || r.day > 5) problems.push('day not 1 to 5');
  if (!inputs.has(norm(r.task))) problems.push('task not in the inputs');
  if (!people.has(norm(r.owner))) problems.push('owner not in the directory');
}}
if (problems.length) return [{{ json: Object.assign({{}}, template, {{ reason: [...new Set(problems)].join('; ') }}) }}];
return [{{ json: {{ source: 'ai draft', rows: rows.map(r => ({{ day: r.day, task: r.task, owner: r.owner }})), reason: '' }} }}];
"""

AI_ERROR_JS = rf"""
// Failure table: the AI fails, so the template's checklist goes.
const t = $('Step 2: Rule: complete hire?').first().json.template;
return [{{ json: {{ source: 'template', rows: t.checklist || [], reason: 'AI error after retries: ' + String(($json.error && $json.error.message) || '') }} }}];
"""

ROUTE_JS = DATES_JS + rf"""
// Step 8: the manager approves or edits; under 2 working days from the start, the template's goes now.
const cfg = {CFG};
const hire = {H};
const t = $('Step 2: Rule: complete hire?').first().json.template;
const c = $input.first().json;
const base = {{ person_id: hire.person_id, name: hire.name, email: hire.email, manager: hire.manager, start_date: hire.start_date,
  template_version: t.version, template_rows: t.checklist || [] }};
if (workingDaysUntil(hire.start_date) < cfg.approval_working_days) {{
  return [{{ json: Object.assign(base, {{ route: 'now', rows: t.checklist || [], source: 'template', reason: c.reason,
    how: 'template: start under ' + cfg.approval_working_days + ' working days away' }}) }}];
}}
return [{{ json: Object.assign(base, {{ route: 'manager', rows: c.rows, source: c.source, reason: c.reason }}) }}];
"""

ANSWER_JS = rf"""
// Step 8: the manager approves or edits the checklist that is waiting for them.
const a = $('{A}').first().json.body;
const c = ($('Step 8: Read the checklist').first().json.items || [])[0];
if (!c || c.status !== 'awaiting manager') return [];
const base = {{ person_id: c.person_id, name: c.name, email: c.email, manager: c.manager, start_date: c.start_date,
  template_version: c.template_version, template_rows: c.template_rows }};
if (a.decision === 'approved') return [{{ json: Object.assign(base, {{ rows: c.rows, source: c.source, how: 'approved by manager' }}) }}];
if (a.decision === 'edited' && Array.isArray(a.rows) && a.rows.length) {{
  return [{{ json: Object.assign(base, {{ rows: a.rows.map(r => ({{ day: r.day, task: r.task, owner: r.owner }})), source: 'manager edit', how: 'edited by manager' }}) }}];
}}
return [];
"""

SILENT_JS = DATES_JS + rf"""
// Step 8 and the failure table: the manager is silent and the start is under 2 working days away,
// so the template's checklist goes.
const cfg = {CFG};
const waiting = $('Step 8: Read checklists awaiting the manager').first().json.items || [];
return waiting.filter(c => workingDaysUntil(c.start_date) < cfg.approval_working_days).map(c => ({{ json: {{
  person_id: c.person_id, name: c.name, email: c.email, manager: c.manager, start_date: c.start_date,
  template_version: c.template_version, template_rows: c.template_rows, rows: c.template_rows, source: 'template',
  how: 'template: manager silent' }} }}));
"""

FINAL_JS = r"""
// Step 9: the checklist that goes, from whichever path decided it.
return $input.all().map(i => ({ json: i.json }));
"""


def finish_unless_failed(w: Workflow, name: str, key_expr: str, result_expr: str, pos) -> str:
    """Mark the key done, but never over a failure another branch of the same run logged."""
    sql = "UPDATE key_log SET status = 'done', result = $3 WHERE recipe = $1 AND key = $2 AND status <> 'failed' RETURNING key"
    return w.pg(name, sql, args=[json.dumps(RID), key_expr, result_expr], pos=pos)


def build() -> Workflow:
    w = Workflow(RID, "R9.1 Run onboarding: accounts, tasks and first-week checklist")
    w.webhook(T, "r9-1-hire", "Your hire list calls this when a hire is saved as confirmed, edited, or set to withdrawn. "
              "Body: the list item {id, person_id, name, email, role, manager, start_date, status, notes: [{day, task, owner}]}.", pos=[0, 0])
    w.webhook(A, "r9-1-manager-answer", "The manager's approval calls this. Body: {person_id, decision: approved | edited, rows (if edited)}.", pos=[0, 900])
    w.schedule(M, 7, "Step 8's 2-working-day rule for managers who have not answered.", pos=[0, 1200])
    w.config("Config", {
        "templates_url": "https://<your role-template list API>",
        "directory_url": "https://<your directory API>",
        "inventory_url": "https://<your access inventory API>",
        "tasks_url": "https://<your task list API>",
        "messaging_url": "https://<your messaging API>",
        "user_group": "<the one group your onboarding service account may create users in>",
        "hr_owner": "<your HR owner>",
        "it_owner": "<your IT owner>",
        "approval_working_days": 2,
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 600])
    for trig in (T, A, M):
        w.connect(trig, "Config")
    w.switch("Which event?", f"={{{{ $('{A}').isExecuted ? 'manager' : $('{M}').isExecuted ? 'morning' : 'hire' }}}}",
             ["hire", "manager", "morning"], pos=[520, 600])
    w.connect("Config", "Which event?")

    cfg = "$('Config').item.json"
    msg = f"={{{{ {cfg}.messaging_url }}}}/messages"

    # ---- Step 1: withdrawn asks Aisha to start R9.4 --------------------------------
    w.if_("Step 1: Withdrawn?", f"={{{{ {H}.status }}}}", op="equals", right="withdrawn", pos=[780, 0])
    w.connect("Which event?", "Step 1: Withdrawn?", output=0)
    w.http("Step 1: Read the hire's inventory", "GET", f"={{{{ {cfg}.inventory_url }}}}/items",
           query={"_wrap": "1", "person_id": f"={{{{ {H}.person_id }}}}"}, write=False, error_output=False, pos=[1040, -240])
    w.exception("Step 1: Exception queue: withdrawn hire", f"{H}.person_id", "withdrawn hire",
                "'Withdrawn with ' + ($json.items || []).length + ' inventory item(s). Confirm, then enter the leaver in R9.4 as \"immediate\"'",
                f"{CFG}.hr_owner", pos=[1300, -240])
    w.http("Step 1: Ask Aisha to start R9.4", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.hr_owner, subject: 'Withdrawn hire ' + {H}.person_id + ': start R9.4', "
                f"text: 'Hire ' + {H}.person_id + ' was withdrawn with ' + ($('Step 1: Read the hire\\'s inventory').first().json.items || []).length + "
                f"' inventory item(s). Confirm it, then add the leaver to the R9.4 list as \"immediate\".' }}) }}}}",
           write=True, error_output=False, pos=[1560, -240])
    w.decision_log("Step 1: Decision log", f"{H}.person_id", "'withdrawn: asked HR to start R9.4'",
                   "JSON.stringify({ inventory_items: ($('Step 1: Read the hire\\'s inventory').first().json.items || []).length })", pos=[1820, -240])
    w.connect("Step 1: Withdrawn?", "Step 1: Read the hire's inventory", output=0)
    w.chain("Step 1: Read the hire's inventory", "Step 1: Exception queue: withdrawn hire", "Step 1: Ask Aisha to start R9.4", "Step 1: Decision log")

    # ---- Step 2: complete, or back to Aisha ----------------------------------------
    w.http("Read the role template", "GET", f"={{{{ {cfg}.templates_url }}}}/templates",
           query={"_wrap": "1", "role": f"={{{{ {H}.role }}}}", "status": "approved"}, write=False, error_output=False, pos=[1040, 0])
    w.code("Step 2: Rule: complete hire?", COMPLETE_JS, mode="runOnceForAllItems", pos=[1300, 0])
    w.if_("Complete?", "={{ $json.complete }}", pos=[1560, 0])
    w.connect("Step 1: Withdrawn?", "Read the role template", output=1)
    w.chain("Read the role template", "Step 2: Rule: complete hire?", "Complete?")
    w.exception("Step 2: Exception queue: return to Aisha", f"{H}.person_id", "returned to HR",
                "'Missing: ' + $json.missing.join(', ') + '; nothing created'", f"{CFG}.hr_owner", pos=[1820, -120])
    w.http("Step 2: Tell Aisha", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.hr_owner, subject: 'Hire ' + {H}.person_id + ' returned: nothing created', "
                f"text: 'Missing: ' + $('Step 2: Rule: complete hire?').first().json.missing.join(', ') }}) }}}}",
           write=True, error_output=False, pos=[2080, -120])
    w.connect("Complete?", "Step 2: Exception queue: return to Aisha", output=1)
    w.connect("Step 2: Exception queue: return to Aisha", "Step 2: Tell Aisha")

    # ---- Step 3: duplicate key, the person ID; a moved start moves the tasks -------------
    w.reserve_key("Step 3: Reserve key", KEY, pos=[1820, 120])
    w.if_("New key?", "={{ $json.is_new }}", pos=[2080, 120])
    w.connect("Complete?", "Step 3: Reserve key", output=0)
    w.connect("Step 3: Reserve key", "New key?")
    w.http("Step 3: Read the hire's tasks", "GET", f"={{{{ {cfg}.tasks_url }}}}/tasks",
           query={"_wrap": "1", "person_id": f"={{{{ {H}.person_id }}}}"}, write=False, error_output=False, pos=[2340, -40])
    w.code("Step 3: Rule: start moved?", MOVED_JS, mode="runOnceForAllItems", pos=[2600, -40])
    w.http("Step 3: Move the task", "PATCH", f"={{{{ {cfg}.tasks_url }}}}/tasks/{{{{ $json.id }}}}",
           body="={{ JSON.stringify({ start_date: $json.start_date, due: $json.due }) }}", write=True, pos=[2860, -40])
    w.decision_log("Step 3: Decision log", f"{H}.person_id", "'start moved: task moved to ' + $('Step 3: Rule: start moved?').item.json.due",
                   "JSON.stringify({ task: $('Step 3: Rule: start moved?').item.json.id, was: $('Step 3: Rule: start moved?').item.json.was })",
                   pos=[3120, -40])
    w.connect("New key?", "Step 3: Read the hire's tasks", output=1)
    w.chain("Step 3: Read the hire's tasks", "Step 3: Rule: start moved?", "Step 3: Move the task", "Step 3: Decision log")

    # ---- Step 4: only the template's accounts and groups, each to the inventory ----------
    tpl = "$('Step 2: Rule: complete hire?').first().json.template"
    w.http("Step 4: Create the account", "POST", f"={{{{ {cfg}.directory_url }}}}/users",
           body=f"={{{{ JSON.stringify({{ id: {H}.person_id, name: {H}.name, group: {CFG}.user_group, template_version: {tpl}.version }}) }}}}",
           write=True, pos=[2340, 300], notes="A write: never retried.")
    w.http("Step 4: Write the account to the inventory", "POST", f"={{{{ {cfg}.inventory_url }}}}/items",
           body=f"={{{{ JSON.stringify({{ id: {H}.person_id + ':account', person_id: {H}.person_id, kind: 'sso account', system: 'directory', "
                f"account: {H}.person_id, via: 'connection', template_version: {tpl}.version, granted: new Date().toISOString() }}) }}}}",
           write=True, pos=[2600, 300])
    w.connect("New key?", "Step 4: Create the account", output=0)
    w.connect("Step 4: Create the account", "Step 4: Write the account to the inventory")
    w.code("Step 4: Groups from the template", GROUPS_JS, mode="runOnceForAllItems", pos=[2860, 180])
    w.http("Step 4: Add to the group", "POST", f"={{{{ {cfg}.directory_url }}}}/group_members",
           body=f"={{{{ JSON.stringify({{ id: {H}.person_id + ':' + $json.group, user: {H}.person_id, group: $json.group }}) }}}}",
           write=True, pos=[3120, 180])
    w.http("Step 4: Write the group to the inventory", "POST", f"={{{{ {cfg}.inventory_url }}}}/items",
           body=f"={{{{ JSON.stringify({{ id: {H}.person_id + ':group:' + $('Step 4: Groups from the template').item.json.group, person_id: {H}.person_id, "
                f"kind: 'group', system: 'directory', account: $('Step 4: Groups from the template').item.json.group, via: 'connection', "
                f"template_version: {tpl}.version, granted: new Date().toISOString() }}) }}}}",
           write=True, pos=[3380, 180])
    w.connect("Step 4: Write the account to the inventory", "Step 4: Groups from the template")
    w.chain("Step 4: Groups from the template", "Step 4: Add to the group", "Step 4: Write the group to the inventory")

    # ---- Step 5: equipment and training tasks ---------------------------------------
    w.code("Step 5: Tasks from the template", TASKS_JS, mode="runOnceForAllItems", pos=[2860, 340])
    w.http("Step 5: Raise the task", "POST", f"={{{{ {cfg}.tasks_url }}}}/tasks", body="={{ JSON.stringify($json) }}",
           write=True, pos=[3120, 340])
    w.connect("Step 4: Write the account to the inventory", "Step 5: Tasks from the template")
    w.connect("Step 5: Tasks from the template", "Step 5: Raise the task")

    # ---- Steps 6 and 7: AI drafts the checklist; a rule decides --------------------
    rows = "rs => (rs || []).map(r => r.day + '; ' + r.task + '; ' + r.owner).join('\\n')"
    vars_js = (f"{{ role: {H}.role, template_version: {tpl}.version, "
               f"template_tasks: ({rows})({tpl}.checklist), manager_notes: ({rows})({H}.notes) || '(none)' }}")
    build, call = ai_step(w, "Step 6", ROOT / "recipes/R9.1/prompts/draft-checklist.md", vars_js,
                          max_tokens=1024, tries=3, pos_build=[2860, 520], pos_call=[3120, 520])
    w.connect("Step 4: Write the account to the inventory", build)
    w.http("Step 7: Read the directory", "GET", f"={{{{ {cfg}.directory_url }}}}/users", query={"_wrap": "1"},
           write=False, error_output=False, pos=[3380, 520])
    w.code("Step 7: Rule: use the draft?", CHECK_JS, mode="runOnceForAllItems", pos=[3640, 520], notes="The rule decides, not the AI.")
    w.code("Step 7: AI error: template's checklist", AI_ERROR_JS, mode="runOnceForAllItems", pos=[3640, 700])
    w.connect(call, "Step 7: Read the directory", output=0)
    w.connect("Step 7: Read the directory", "Step 7: Rule: use the draft?")
    w.connect(call, "Step 7: AI error: template's checklist", output=1)

    # ---- Step 8: the manager approves or edits; under 2 working days the template's goes --
    w.code("Step 8: Rule: time for the manager?", ROUTE_JS, mode="runOnceForAllItems", pos=[3900, 600])
    w.connect("Step 7: Rule: use the draft?", "Step 8: Rule: time for the manager?")
    w.connect("Step 7: AI error: template's checklist", "Step 8: Rule: time for the manager?")
    w.if_("To the manager?", "={{ $json.route }}", op="equals", right="manager", pos=[4160, 600])
    w.connect("Step 8: Rule: time for the manager?", "To the manager?")
    w.http("Step 8: Checklist to the manager", "PUT", f"={{{{ {cfg}.tasks_url }}}}/checklists/{{{{ $json.person_id }}}}",
           body="={{ JSON.stringify(Object.assign({}, $json, { route: undefined, status: 'awaiting manager' })) }}",
           write=True, pos=[4420, 520])
    w.http("Step 8: Ask the manager to approve or edit", "POST", msg,
           body="={{ JSON.stringify({ to: $('Step 8: Rule: time for the manager?').item.json.manager, "
                "subject: 'Approve or edit the first-week checklist for ' + $('Step 8: Rule: time for the manager?').item.json.name, "
                "text: $('Step 8: Rule: time for the manager?').item.json.rows.map(r => 'Day ' + r.day + ': ' + r.task + ' (' + r.owner + ')').join('\\n') }) }}",
           write=True, pos=[4680, 520])
    finish_unless_failed(w, "Mark key done: with the manager", KEY, "'checklist with the manager'", pos=[4940, 520])
    w.decision_log("Step 8: Decision log", f"{H}.person_id", "'checklist to the manager (' + $('Step 8: Rule: time for the manager?').first().json.source + ')'",
                   "JSON.stringify({ template_version: $('Step 8: Rule: time for the manager?').first().json.template_version, "
                   "source: $('Step 8: Rule: time for the manager?').first().json.source, rejected: $('Step 8: Rule: time for the manager?').first().json.reason || 'no' })",
                   pos=[5200, 520])
    w.connect("To the manager?", "Step 8: Checklist to the manager", output=0)
    w.chain("Step 8: Checklist to the manager", "Step 8: Ask the manager to approve or edit", "Mark key done: with the manager", "Step 8: Decision log")

    # Manager's answer.
    w.http("Step 8: Read the checklist", "GET", f"={{{{ {cfg}.tasks_url }}}}/checklists",
           query={"_wrap": "1", "person_id": f"={{{{ $('{A}').first().json.body.person_id }}}}"}, write=False, error_output=False, pos=[780, 900])
    w.code("Step 8: Rule: manager's answer", ANSWER_JS, mode="runOnceForAllItems", pos=[1040, 900])
    w.connect("Which event?", "Step 8: Read the checklist", output=1)
    w.connect("Step 8: Read the checklist", "Step 8: Rule: manager's answer")

    # Manager silent.
    w.http("Step 8: Read checklists awaiting the manager", "GET", f"={{{{ {cfg}.tasks_url }}}}/checklists",
           query={"_wrap": "1", "status": "awaiting manager"}, write=False, error_output=False, pos=[780, 1200])
    w.code("Step 8: Rule: manager silent, start near", SILENT_JS, mode="runOnceForAllItems", pos=[1040, 1200])
    w.connect("Which event?", "Step 8: Read checklists awaiting the manager", output=2)
    w.connect("Step 8: Read checklists awaiting the manager", "Step 8: Rule: manager silent, start near")

    # ---- Step 9: send the welcome pack; log ---------------------------------------
    fin = "$('Step 9: Checklist that goes').item.json"
    w.code("Step 9: Checklist that goes", FINAL_JS, mode="runOnceForAllItems", pos=[4420, 900])
    w.connect("To the manager?", "Step 9: Checklist that goes", output=1)
    w.connect("Step 8: Rule: manager's answer", "Step 9: Checklist that goes")
    w.connect("Step 8: Rule: manager silent, start near", "Step 9: Checklist that goes")
    w.http("Step 9: Record the checklist", "PUT", f"={{{{ {cfg}.tasks_url }}}}/checklists/{{{{ $json.person_id }}}}",
           body="={{ JSON.stringify(Object.assign({}, $json, { route: undefined, status: 'sent' })) }}", write=True, pos=[4680, 900])
    w.http("Step 9: Send the welcome pack", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {fin}.email, cc: {fin}.manager, subject: 'Welcome: your first week from ' + {fin}.start_date, "
                f"text: {fin}.rows.map(r => 'Day ' + r.day + ': ' + r.task + ' (' + r.owner + ')').join('\\n') }}) }}}}",
           write=True, pos=[4940, 900])
    finish_unless_failed(w, "Mark key done: welcome pack sent", f"{fin}.person_id", f"'welcome pack sent: ' + {fin}.how", pos=[5200, 900])
    w.decision_log("Step 9: Decision log", f"{fin}.person_id", f"'welcome pack sent (' + {fin}.how + ')'",
                   f"JSON.stringify({{ template_version: {fin}.template_version, source: {fin}.source, how: {fin}.how, items: ({fin}.rows || []).length }})",
                   pos=[5460, 900])
    w.chain("Step 9: Checklist that goes", "Step 9: Record the checklist", "Step 9: Send the welcome pack",
            "Mark key done: welcome pack sent", "Step 9: Decision log")
    w.exception("Step 9: Exception queue: welcome pack not sent", f"{fin}.person_id", "welcome pack not sent",
                "'Welcome pack not sent (' + (($json.error && $json.error.message) || 'send error') + '); HR sends it'",
                f"{CFG}.hr_owner", pos=[5200, 1100])
    w.connect("Step 9: Record the checklist", "Step 9: Exception queue: welcome pack not sent", output=1)
    w.connect("Step 9: Send the welcome pack", "Step 9: Exception queue: welcome pack not sent", output=1)

    # ---- failures on the hire's writes (placed below, so they run after the success branches) ----
    w.finish_key("Mark key failed: account", KEY, "failed", "'account creation failed: ' + (($json.error && $json.error.message) || 'unknown')", pos=[3640, 1500])
    w.exception("Step 4: Exception queue: account creation failed", f"{H}.person_id", "account creation failed",
                "'Account or group not created, never retried; check, then raise an IT ticket'", f"{CFG}.it_owner", pos=[3900, 1500])
    for n in ["Step 4: Create the account", "Step 4: Write the account to the inventory", "Step 4: Add to the group",
              "Step 4: Write the group to the inventory"]:
        w.connect(n, "Mark key failed: account", output=1)
    w.connect("Mark key failed: account", "Step 4: Exception queue: account creation failed")
    w.finish_key("Mark key failed", KEY, "failed", "'write failed: ' + (($json.error && $json.error.message) || 'unknown')", pos=[3640, 1700])
    w.exception("Exception queue: write failed", f"{H}.person_id", "write failed",
                "'A task or checklist write failed, never retried; check the hire'", f"{CFG}.hr_owner", pos=[3900, 1700])
    for n in ["Step 3: Move the task", "Step 5: Raise the task", "Step 8: Checklist to the manager", "Step 8: Ask the manager to approve or edit"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")
    return w
