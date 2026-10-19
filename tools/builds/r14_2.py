"""R14.2 Create tasks with owners and due dates after verification: rules only, no AI step.

Source: book Chapter 14, recipe R14.2, build steps 1 to 9 and Table 14.1 (recipes/R14.2/build-spec.md).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "n8n"))
from wf import Workflow  # noqa: E402

T = "Step 1: List verified"
EV = f"$('{T}').first().json.body"
CFG = "$('Config').first().json"
R = "$('Steps 2 to 5: Rules').item.json"
SERIES = "($('Read the register').first().json.items || [])[0]"

RULES_JS = r"""
// Steps 2 to 5 of the book's R14.2 and the checks in Table 14.1. The workflow never fills a gap.
const ev = $('Step 1: List verified').first().json.body;
const series = ($('Read the register').first().json.items || [])[0] || null;
const staff = $('Read staff accounts').first().json.items || [];
const items = ($('Read the verified list').first().json.items || []).filter(i => i.status === 'approved');
const today = new Date().toISOString().slice(0, 10);
const low = s => String(s || '').trim().toLowerCase();

// Step 2: the verifier must be the series' chair or backup.
if (!series || ![series.chair, series.backup].map(low).includes(low(ev.verified_by))) {
  return [{ json: { route: 'refuse', reason: series ? 'verifier not chair or backup' : 'series not in the register', verified_by: ev.verified_by } }];
}
const chair = staff.find(s => low(s.email) === low(series.chair)) || { name: series.chair, email: series.chair };

// The owner as a staff account: full name or address, else a unique first-name match.
function account(owner) {
  const o = low(owner);
  const exact = staff.filter(s => low(s.name) === o || low(s.email) === o);
  if (exact.length) return { acct: exact[0] };
  const first = staff.filter(s => low(s.name).split(/\s+/)[0] === o);
  if (first.length > 1) return { ambiguous: true };
  return { acct: first[0] || null };
}
const isDate = d => /^\d{4}-\d{2}-\d{2}$/.test(d || '') && !isNaN(Date.parse(d + 'T00:00:00Z'))
  && new Date(d + 'T00:00:00Z').toISOString().slice(0, 10) === d;

const out = [];
for (const it of items) {
  // Step 5: an item already holding a task ID is skipped, whatever steps 3 and 4 would say.
  if (it.task_id) continue;
  const owner = String(it.owner || '').trim();
  const { acct, ambiguous } = account(owner);
  const base = { item_id: it.id, action: String(it.action || '').trim(), owner, due_date: it.due_date || '',
                 source_link: it.source_link || '', quoted_line: it.quoted_line || '' };
  // Step 3: an owner outside the company goes into the minutes, with a follow-up task for the chair.
  if (owner && low(owner) !== 'unassigned' && !acct && !ambiguous) {
    out.push({ ...base, route: 'outside', task_owner: chair.name, task_email: chair.email,
               title: `Follow up with ${owner}: ${base.action}`,
               minutes: { id: it.id, occurrence_id: it.occurrence_id, series_id: series.id,
                          text: `${owner} (outside the company): ${base.action}${base.due_date ? ', due ' + base.due_date : ''}`,
                          source_link: base.source_link } });
    continue;
  }
  // Step 4: Table 14.1. A failure returns the item to the chair with the reason.
  const reasons = [];
  if (!base.action) reasons.push('no action');
  if (!owner || low(owner) === 'unassigned') reasons.push('no owner');
  else if (ambiguous) reasons.push('owner matches more than one staff account');
  else if (!acct.active) reasons.push('owner not an active staff account');
  if (!isDate(base.due_date)) reasons.push('due date is not a calendar date');
  else if (base.due_date < today) reasons.push('due date is in the past');
  if (!base.source_link) reasons.push('no source link');
  if (reasons.length) { out.push({ ...base, route: 'return', reasons }); continue; }
  out.push({ ...base, route: 'task', task_owner: acct.name, task_email: acct.email, title: base.action });
}
return out.map(j => ({ json: { ...j, series_id: series.id, series: series.name, chair: series.chair, verified_by: ev.verified_by } }));
"""

RETURNS_JS = r"""
// One message to the chair listing every returned item.
const rows = $input.all().map((_, i) => $('Steps 2 to 5: Rules').itemMatching(i).json);
const lines = rows.map(r => `- ${r.action || '(no action)'}: ${r.reasons.join('; ')}`);
return [{ json: { chair: rows[0].chair, series: rows[0].series, count: rows.length, text: lines.join('\n') }, pairedItem: { item: 0 } }];
"""

OWNERS_JS = r"""
// Step 8: one message to each owner, listing all of their new tasks.
const groups = {};
$input.all().forEach((_, i) => {
  const r = $('Steps 2 to 5: Rules').itemMatching(i).json;
  const task = $('Step 7: Create the task').itemMatching(i).json;
  (groups[r.task_email] = groups[r.task_email] || { to: r.task_email, series: r.series, lines: [], first: i })
    .lines.push(`- ${r.title}, due ${r.due_date} (task ${task.id}; source ${r.source_link})`);
});
return Object.values(groups).map(g => ({ json: { to: g.to, series: g.series, count: g.lines.length, text: g.lines.join('\n') }, pairedItem: { item: g.first } }));
"""

TASK_BODY = (f"={{{{ JSON.stringify({{ title: {R}.title, owner: {R}.task_owner, owner_email: {R}.task_email, due_date: {R}.due_date, "
             f"verified_due_date: {R}.due_date, series: {R}.series, series_id: {R}.series_id, source_link: {R}.source_link, "
             f"item_id: {R}.item_id, quoted_line: {R}.quoted_line, verified_by: {R}.verified_by, status: 'open' }}) }}}}")


def build() -> Workflow:
    w = Workflow("R14.2", "R14.2 Create tasks with owners and due dates after verification")
    w.webhook(T, "r14-2-list-verified",
              "Your action list calls this when a list changes to \"verified\". Body: {series_id, occurrence_id, verified_by}.", pos=[0, 0])
    w.config("Config", {
        "register_url": "https://<your meeting register API>",
        "actions_url": "https://<your action list API>",
        "directory_url": "https://<your staff directory API>",
        "tasks_url": "https://<your task system API>",
        "minutes_url": "https://<your minutes API>",
        "messaging_url": "https://<your messaging API>",
        "register_owner": "<your register owner>",
        "exception_owner": "<your workflow editor>",
    }, pos=[260, 0])
    w.http("Read the register", "GET", f"={{{{ {CFG}.register_url }}}}/series",
           query={"_wrap": "1", "id": f"={{{{ {EV}.series_id }}}}"}, write=False, error_output=False, pos=[520, 0])
    w.http("Read the verified list", "GET", f"={{{{ {CFG}.actions_url }}}}/items",
           query={"_wrap": "1", "occurrence_id": f"={{{{ {EV}.occurrence_id }}}}"}, write=False, error_output=False, pos=[780, 0])
    w.http("Read staff accounts", "GET", f"={{{{ {CFG}.directory_url }}}}/staff",
           query={"_wrap": "1"}, write=False, error_output=False, pos=[1040, 0])
    w.code("Steps 2 to 5: Rules", RULES_JS, mode="runOnceForAllItems", pos=[1300, 0],
           notes="Rules decide; there is no AI step in R14.2.")
    w.switch("Route", "={{ $json.route }}", ["refuse", "return", "outside", "task"], pos=[1560, 0])
    w.chain(T, "Config", "Read the register", "Read the verified list", "Read staff accounts", "Steps 2 to 5: Rules", "Route")

    msg = f"={{{{ {CFG}.messaging_url }}}}/messages"
    # ---- step 2: refuse ------------------------------------------------------------
    w.exception("Step 2: Exception queue: verifier not registered", f"{EV}.occurrence_id", "verifier not chair or backup",
                f"$json.reason + ': ' + {EV}.verified_by", f"{CFG}.register_owner", pos=[1820, -480])
    w.http("Step 2: Alert the register owner", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: [{CFG}.register_owner], subject: 'Action list not verified by its chair or backup', "
                f"text: 'No tasks created for meeting ' + {EV}.occurrence_id + ': ' + $('Steps 2 to 5: Rules').first().json.reason + ' (' + {EV}.verified_by + ').' }}) }}}}",
           write=True, pos=[2080, -480])
    w.connect("Route", "Step 2: Exception queue: verifier not registered", output=0)
    w.connect("Step 2: Exception queue: verifier not registered", "Step 2: Alert the register owner")

    # ---- step 4: return ------------------------------------------------------------
    item_url = f"={{{{ {CFG}.actions_url }}}}/items/{{{{ encodeURIComponent({R}.item_id) }}}}"
    w.http("Step 4: Return the item to the chair", "PATCH", item_url,
           body=f"={{{{ JSON.stringify({{ status: 'returned', return_reason: {R}.reasons.join('; ') }}) }}}}", write=True, pos=[1820, -240])
    w.code("Step 4: One message to the chair", RETURNS_JS, mode="runOnceForAllItems", pos=[2080, -240])
    w.http("Step 4: Tell the chair", "POST", msg,
           body="={{ JSON.stringify({ to: [$json.chair], subject: $json.count + ' action item(s) returned: ' + $json.series, text: 'Fix and verify again:\\n' + $json.text }) }}",
           write=True, pos=[2340, -240])
    w.connect("Route", "Step 4: Return the item to the chair", output=1)
    w.connect("Step 4: Return the item to the chair", "Step 4: One message to the chair")
    w.connect("Step 4: One message to the chair", "Step 4: Tell the chair")

    # ---- step 3: outside owner -----------------------------------------------------
    w.http("Step 3: Write to the minutes", "PUT", f"={{{{ {CFG}.minutes_url }}}}/entries/{{{{ encodeURIComponent({R}.item_id) }}}}",
           body=f"={{{{ JSON.stringify({R}.minutes) }}}}", write=True, pos=[1820, 0],
           notes="An owner outside the company goes into the minutes; the chair gets the follow-up task (steps 6 to 8).")
    w.connect("Route", "Step 3: Write to the minutes", output=2)

    # ---- steps 6 to 9 --------------------------------------------------------------
    w.http("Step 6: Search tasks for the item ID", "GET", f"={{{{ {CFG}.tasks_url }}}}/tasks",
           query={"_wrap": "1", "item_id": f"={{{{ {R}.item_id }}}}"}, write=False, pos=[2080, 160])
    w.connect("Route", "Step 6: Search tasks for the item ID", output=3)
    w.connect("Step 3: Write to the minutes", "Step 6: Search tasks for the item ID")
    w.if_("Task found?", "={{ ($json.items || []).length > 0 }}", pos=[2340, 160])
    w.connect("Step 6: Search tasks for the item ID", "Task found?")
    w.http("Step 6: Write the found task ID back", "PATCH", item_url,
           body="={{ JSON.stringify({ task_id: $json.items[0].id }) }}", write=True, pos=[2600, 0],
           notes="A task already carries this item ID: write its ID back and create nothing.")
    w.connect("Task found?", "Step 6: Write the found task ID back", output=0)

    w.http("Step 7: Create the task", "POST", f"={{{{ {CFG}.tasks_url }}}}/tasks", body=TASK_BODY, write=True, pos=[2600, 240],
           notes="Step 9: a task-system error is retried once, then the chair is told; steps 5 and 6 make a rerun safe.")
    w.connect("Task found?", "Step 7: Create the task", output=1)
    w.http("Step 8: Write task ID back", "PATCH", item_url,
           body="={{ JSON.stringify({ task_id: $json.id, verified_due_date: $('Steps 2 to 5: Rules').item.json.due_date, verified_at: new Date().toISOString() }) }}",
           write=True, pos=[2860, 240])
    w.code("Step 8: One message per owner", OWNERS_JS, mode="runOnceForAllItems", pos=[3120, 240])
    w.http("Step 8: Tell each owner", "POST", msg,
           body="={{ JSON.stringify({ to: [$json.to], subject: $json.count + ' new task(s) from ' + $json.series, text: $json.text }) }}",
           write=True, pos=[3380, 240])
    w.chain("Step 7: Create the task", "Step 8: Write task ID back", "Step 8: One message per owner", "Step 8: Tell each owner")

    # Book step 9: retry a task-system error once, then tell the chair.
    for n in w.nodes:
        if n["name"] in ("Step 6: Search tasks for the item ID", "Step 7: Create the task"):
            n.update(retryOnFail=True, maxTries=2, waitBetweenTries=2000)
    w.exception("Step 9: Exception queue: task system error", f"{R}.item_id", "task system error",
                "'Task system failed after one retry: ' + (($json.error && $json.error.message) || '')", f"{R}.chair", pos=[2860, 480])
    w.http("Step 9: Tell the chair", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: [{R}.chair], subject: 'Task not created: ' + {R}.series, "
                f"text: 'The task system failed after one retry for: ' + {R}.title + '. Owen reruns the list; items with a task ID are skipped.' }}) }}}}",
           write=True, pos=[3120, 480])
    w.connect("Step 6: Search tasks for the item ID", "Step 9: Exception queue: task system error", output=1)
    w.connect("Step 7: Create the task", "Step 9: Exception queue: task system error", output=1)
    w.connect("Step 9: Exception queue: task system error", "Step 9: Tell the chair")

    # ---- decision log: item, task ID, verifier, time (governance card) ------------
    log_sql = ("INSERT INTO decision_log (recipe, item, decision, rules, approved_by) "
               "VALUES ($1, $2, $3, $4::jsonb, $5) RETURNING id")

    def log(name, decision, rules, pos):
        w.pg(name, log_sql, args=[json.dumps("R14.2"), f"{R}.item_id", decision, rules, f"{R}.verified_by"], pos=pos,
             notes="Decision log: the item's ID, task ID and verifier; never the content (governance card).")

    log("Decision log: task created", "'task created'", f"JSON.stringify({{ task_id: $('Step 7: Create the task').item.json.id, route: {R}.route }})", [3120, 60])
    log("Decision log: task found", "'existing task linked'", f"JSON.stringify({{ task_id: $('Task found?').item.json.items[0].id, route: {R}.route }})", [2860, 0])
    log("Decision log: returned", "'returned to chair'", f"JSON.stringify({{ reasons: {R}.reasons }})", [2080, -380])
    w.connect("Step 8: Write task ID back", "Decision log: task created")
    w.connect("Step 6: Write the found task ID back", "Decision log: task found")
    w.connect("Step 4: Return the item to the chair", "Decision log: returned")

    # ---- writes never retried: failures go to the exception queue -----------------
    w.exception("Exception queue: write failed", f"{EV}.occurrence_id", "write failed",
                "'A write or message failed; never retried. Check the list, then rerun it: steps 5 and 6 guard.'",
                f"{CFG}.exception_owner", pos=[3640, 480])
    for n in ["Step 2: Alert the register owner", "Step 4: Return the item to the chair", "Step 4: Tell the chair",
              "Step 3: Write to the minutes", "Step 6: Write the found task ID back", "Step 8: Write task ID back",
              "Step 8: Tell each owner", "Step 9: Tell the chair"]:
        w.connect(n, "Exception queue: write failed", output=1)
    return w
