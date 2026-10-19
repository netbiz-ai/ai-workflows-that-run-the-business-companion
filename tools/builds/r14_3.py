"""R14.3 Chase overdue actions and carry them into the next agenda: rules only, no AI step.

Source: book Chapter 14, recipe R14.3, build steps 1 to 10 (recipes/R14.3/build-spec.md).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "n8n"))
from wf import V, Workflow  # noqa: E402

D = "Step 1: Early each working day"
F = "Step 8: Each Friday"
A = "Step 9: Meeting decisions recorded"
CFG = "$('Config').first().json"
R = "$('Steps 2 to 8: Rules').item.json"

DAYS_JS = r"""
// Working days: the weekdays in Config, less the holidays in your working-day calendar.
const iso = d => d.toISOString().slice(0, 10);
const todayUtc = () => new Date(iso(new Date()) + 'T00:00:00Z');
const addDays = (d, n) => new Date(d.getTime() + n * 86400000);
const isWorkday = (d, cfg, holidays) => cfg.working_weekdays.includes(d.getUTCDay()) && !holidays.includes(iso(d));
"""

WORKDAY_JS = DAYS_JS + r"""
// Step 1: the morning run skips weekends and holidays; the Friday count (step 8) always runs, as the heartbeat.
const cfg = $('Config').first().json;
const holidays = ($('Read holidays').first().json.items || []).map(h => String(h.date).slice(0, 10));
const friday = $('Step 8: Each Friday').isExecuted;
return [{ json: { run: friday || isWorkday(todayUtc(), cfg, holidays), friday } }];
"""

RULES_JS = DAYS_JS + r"""
// Steps 2 to 8 and 10 of the book's R14.3. Each output item is one action, with its duplicate key.
const cfg = $('Config').first().json;
const friday = $('Step 1: Rule: working day?').first().json.friday;
const holidays = ($('Read holidays').first().json.items || []).map(h => String(h.date).slice(0, 10));
const series = Object.fromEntries(($('Read the register').first().json.items || []).map(s => [s.id, s]));
const allTasks = $('Read tasks').first().json.items || [];
const tracking = Object.fromEntries(($('Read the tracking list').first().json.items || []).map(r => [r.id, r]));
const meetings = $('Read series meetings').first().json.items || [];
const listed = $('Read listed agenda items').first().json.items || [];
const today = todayUtc(), t = iso(today);
let prev = addDays(today, -1);
while (!isWorkday(prev, cfg, holidays)) prev = addDays(prev, -1);
const windowEnd = iso(addDays(today, cfg.meeting_window_days));

// Step 2: open tasks tagged with a registered series; a hand-made task's first-seen date counts as verified.
const open = allTasks.filter(k => k.status === 'open' && series[k.series_id]);
const verifiedOf = (k, row) => (row && row.verified_date) || k.verified_due_date || k.due_date;
const newRow = k => ({ id: k.id, series_id: k.series_id, verified_date: verifiedOf(k, null), first_seen: t, last_due_seen: k.due_date,
                       changes: 0, reminder_key: '', reminder_state: 'none', reminded_on: '' });
const base = (k, row) => ({ task_id: k.id, title: k.title, owner: k.owner, owner_email: k.owner_email, due_date: k.due_date,
                            source_link: k.source_link || '', series_id: k.series_id, series: series[k.series_id].name,
                            verified_date: verifiedOf(k, row),
                            days_overdue: Math.max(0, Math.round((today - new Date(k.due_date + 'T00:00:00Z')) / 86400000)) });
const out = [];

// Steps 5 to 7: the series' next meeting within the window gets an agenda item; none, and the register owner is told once.
function carry(k, row, why) {
  const m = meetings.filter(x => x.series_id === k.series_id && String(x.start).slice(0, 10) >= t && String(x.start).slice(0, 10) <= windowEnd)
    .sort((a, b) => String(a.start).localeCompare(String(b.start)))[0];
  const b = base(k, row);
  if (m) out.push({ ...b, kind: 'agenda', why, meeting_id: m.id, meeting_start: String(m.start).slice(0, 10), key: `${k.id}:${m.id}` });
  else out.push({ ...b, kind: 'no_meeting', why, key: `${k.id}:${b.verified_date}:no meeting` });
}

if (!friday) {
  for (const k of open.filter(k => k.due_date < t)) {
    const row = tracking[k.id];
    const key = `${k.id}:${verifiedOf(k, row)}`;   // Step 3: task ID plus current verified date
    if (!row || row.reminder_key !== key) {
      // Step 4: not yet reminded for this date.
      out.push({ ...base(k, row), kind: 'remind', key, row: { ...(row || newRow(k)), reminder_key: key, reminder_state: 'pending' } });
    } else if (row.reminder_state !== 'sent') {
      // A "pending" key is never resent; Owen checks it.
      out.push({ ...base(k, row), kind: 'pending', key });
    } else if (row.reminded_on && row.reminded_on <= iso(prev)) {
      carry(k, row, 'overdue after one reminder');
    }
  }
  // Step 10: a task closed after listing is marked, never removed.
  const byId = Object.fromEntries(allTasks.map(k => [k.id, k]));
  for (const a of listed) if (byId[a.task_id] && byId[a.task_id].status !== 'open') out.push({ kind: 'closed', agenda_item_id: a.id, task_id: a.task_id });
} else {
  // Step 8: compare due dates with the tracking list; a second change goes on the agenda.
  for (const k of open) {
    const row = tracking[k.id];
    if (!row) { out.push({ kind: 'track', task_id: k.id, row: newRow(k) }); continue; }
    if (k.due_date !== row.last_due_seen) {
      const changes = (Number(row.changes) || 0) + 1;
      out.push({ kind: 'track', task_id: k.id, row: { ...row, last_due_seen: k.due_date, changes } });
      if (changes >= 2) carry(k, row, `due date moved ${changes} times`);
    }
  }
  // The count is by series, never by person.
  const counts = {};
  for (const k of open.filter(k => k.due_date < t)) counts[series[k.series_id].name] = (counts[series[k.series_id].name] || 0) + 1;
  out.push({ kind: 'count', counts, total: Object.values(counts).reduce((a, b) => a + b, 0), date: t });
}
return out.map(j => ({ json: j }));
"""

DECISIONS_JS = r"""
// Step 9: a new date the chair decided becomes the verified date and resets the change count.
const isDate = d => /^\d{4}-\d{2}-\d{2}$/.test(d || '') && !isNaN(Date.parse(d + 'T00:00:00Z'));
const rows = ($('Step 9: Read the chair\'s decisions').first().json.items || []).filter(a => a.decision === 'new date' && isDate(a.new_date));
return rows.map(a => ({ json: { task_id: a.task_id, new_date: a.new_date, agenda_item_id: a.id, meeting_id: a.meeting_id } }));
"""


def build() -> Workflow:
    w = Workflow("R14.3", "R14.3 Chase overdue actions and carry them into the next agenda")
    w.schedule(D, 6, "Early each day; step 1's rule skips weekends and holidays.", pos=[0, 0])
    w.node(F, "n8n-nodes-base.scheduleTrigger", V["schedule"],
           {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1, "triggerAtDay": [5], "triggerAtHour": 6}]}},
           pos=[0, 200], notes="Step 8: the Friday comparison and count. No Friday count by noon means the run never fired.")
    w.webhook(A, "r14-3-meeting-decided",
              "Your agenda list calls this after each meeting, once the chair has recorded decisions. Body: {meeting_id}.", pos=[0, 900])
    w.config("Config", {
        "register_url": "https://<your meeting register API>",
        "tasks_url": "https://<your task system API>",
        "tracking_url": "https://<your tracking list API>",
        "calendar_url": "https://<your calendar API>",
        "agenda_url": "https://<your agenda list API>",
        "workdays_url": "https://<your working-day calendar API>",
        "messaging_url": "https://<your messaging API>",
        "working_weekdays": [1, 2, 3, 4, 5],
        "meeting_window_days": 14,
        "register_owner": "<your register owner>",
        "exception_owner": "<your workflow editor>",
    }, pos=[260, 300])
    for trig in (D, F, A):
        w.connect(trig, "Config")
    w.if_("After a meeting?", f"={{{{ $('{A}').isExecuted }}}}", pos=[520, 300])
    w.connect("Config", "After a meeting?")

    # ---- steps 1 and 2: the morning and Friday runs ---------------------------------
    w.http("Read holidays", "GET", f"={{{{ {CFG}.workdays_url }}}}/holidays", query={"_wrap": "1"},
           write=False, error_output=False, pos=[780, 0])
    w.code("Step 1: Rule: working day?", WORKDAY_JS, mode="runOnceForAllItems", pos=[1040, 0])
    w.if_("Run today?", "={{ $json.run }}", pos=[1300, 0])
    w.noop("Not a working day: stop", pos=[1560, -200])
    w.connect("After a meeting?", "Read holidays", output=1)
    w.chain("Read holidays", "Step 1: Rule: working day?", "Run today?")
    w.connect("Run today?", "Not a working day: stop", output=1)
    reads = [
        ("Read the register", "register_url", "/series", {}),
        ("Read tasks", "tasks_url", "/tasks", {}),
        ("Read the tracking list", "tracking_url", "/rows", {}),
        ("Read series meetings", "calendar_url", "/meetings", {}),
        ("Read listed agenda items", "agenda_url", "/items", {"status": "listed"}),
    ]
    prev = None
    for i, (name, url, path, q) in enumerate(reads):
        w.http(name, "GET", f"={{{{ {CFG}.{url} }}}}{path}", query={"_wrap": "1", **q}, write=False, error_output=False,
               pos=[1560 + 260 * i, 0])
        if prev:
            w.connect(prev, name)
        prev = name
    w.connect("Run today?", "Read the register", output=0)
    w.code("Steps 2 to 8: Rules", RULES_JS, mode="runOnceForAllItems", pos=[2860, 0],
           notes="Rules decide; there is no AI step in R14.3. It never moves a date, reassigns or closes a task.")
    w.connect(prev, "Steps 2 to 8: Rules")
    kinds = ["remind", "pending", "agenda", "no_meeting", "closed", "track", "count"]
    w.switch("Action", "={{ $json.kind }}", kinds, pos=[3120, 0])
    w.connect("Steps 2 to 8: Rules", "Action")

    msg = f"={{{{ {CFG}.messaging_url }}}}/messages"
    track_url = f"={{{{ {CFG}.tracking_url }}}}/rows/{{{{ encodeURIComponent({R}.task_id) }}}}"
    # ---- steps 3 and 4: one reminder per verified date ------------------------------
    w.reserve_key("Step 3: Reserve reminder key", f"{R}.key", pos=[3380, -600])
    w.if_("New reminder key?", "={{ $json.is_new }}", pos=[3640, -600])
    w.noop("Reminder key logged: stop", pos=[3900, -760], notes="This verified date has a reminder already, or one in flight.")
    w.http("Step 4: Write the key pending", "PUT", track_url, body=f"={{{{ JSON.stringify({R}.row) }}}}", write=True, pos=[3900, -600])
    w.http("Step 4: Remind the owner", "POST", msg,
           body=(f"={{{{ JSON.stringify({{ to: [{R}.owner_email], subject: 'Overdue action: ' + {R}.title, "
                 f"text: {R}.title + ' was due ' + {R}.due_date + ' (' + {R}.series + '). Source: ' + {R}.source_link }}) }}}}"),
           write=True, pos=[4160, -600], notes="One reminder for each agreed date; the next step is a meeting, never a second message.")
    w.http("Step 4: Mark it sent", "PATCH", track_url,
           body="={{ JSON.stringify({ reminder_state: 'sent', reminded_on: new Date().toISOString().slice(0, 10) }) }}",
           write=True, pos=[4420, -600])
    w.connect("Action", "Step 3: Reserve reminder key", output=0)
    w.chain("Step 3: Reserve reminder key", "New reminder key?")
    w.connect("New reminder key?", "Reminder key logged: stop", output=1)
    w.connect("New reminder key?", "Step 4: Write the key pending", output=0)
    w.chain("Step 4: Write the key pending", "Step 4: Remind the owner", "Step 4: Mark it sent")

    w.pg("Step 4: Pending key: Owen checks",
         "INSERT INTO exception_queue (recipe, item, reason, detail, owner) SELECT $1, $2, $3, $4, $5 "
         "WHERE NOT EXISTS (SELECT 1 FROM exception_queue WHERE recipe = $1 AND item = $2 AND status = 'open') RETURNING id",
         args=[json.dumps("R14.3"), f"{R}.key", json.dumps("reminder key pending"),
               "'The reminder may have been sent but was never marked sent; it is not resent. Release or close the key.'",
               f"{CFG}.exception_owner"], pos=[3380, -400],
         notes="A \"pending\" key is never resent; one open exception per key.")
    w.connect("Action", "Step 4: Pending key: Owen checks", output=1)

    # ---- steps 5 to 7: carry to the next agenda, or tell the register owner once -------
    w.reserve_key("Step 6: Reserve agenda key", f"{R}.key", pos=[3380, -200])
    w.if_("New agenda key?", "={{ $json.is_new }}", pos=[3640, -200])
    w.noop("Already on that agenda: stop", pos=[3900, -320])
    w.http("Step 6: Add the agenda item", "POST", f"={{{{ {CFG}.agenda_url }}}}/items",
           body=(f"={{{{ JSON.stringify({{ meeting_id: {R}.meeting_id, series_id: {R}.series_id, task_id: {R}.task_id, action: {R}.title, "
                 f"owner: {R}.owner, verified_date: {R}.verified_date, due_date: {R}.due_date, days_overdue: {R}.days_overdue, "
                 f"reason: {R}.why, status: 'listed' }}) }}}}"),
           write=True, pos=[3900, -200], notes="For the chair to decide at the meeting.")
    w.connect("Action", "Step 6: Reserve agenda key", output=2)
    w.chain("Step 6: Reserve agenda key", "New agenda key?")
    w.connect("New agenda key?", "Already on that agenda: stop", output=1)
    w.connect("New agenda key?", "Step 6: Add the agenda item", output=0)

    w.reserve_key("Step 7: Reserve no-meeting key", f"{R}.key", pos=[3380, 0])
    w.if_("New no-meeting key?", "={{ $json.is_new }}", pos=[3640, 0])
    w.noop("Register owner told already: stop", pos=[3900, -80])
    w.http("Step 7: Tell the register owner", "POST", msg,
           body=(f"={{{{ JSON.stringify({{ to: [{CFG}.register_owner], subject: 'No meeting within ' + {CFG}.meeting_window_days + ' days: ' + {R}.series, "
                 f"text: {R}.title + ' (' + {R}.owner + '), verified for ' + {R}.verified_date + ', is ' + {R}.days_overdue + ' day(s) overdue (' + {R}.why + '), and ' + {R}.series + ' has no meeting within ' + {CFG}.meeting_window_days + ' days.' }}) }}}}"),
           write=True, pos=[3900, 0])
    w.connect("Action", "Step 7: Reserve no-meeting key", output=3)
    w.chain("Step 7: Reserve no-meeting key", "New no-meeting key?")
    w.connect("New no-meeting key?", "Register owner told already: stop", output=1)
    w.connect("New no-meeting key?", "Step 7: Tell the register owner", output=0)

    keyed = ["Step 4: Write the key pending", "Step 4: Remind the owner", "Step 4: Mark it sent",
             "Step 6: Add the agenda item", "Step 7: Tell the register owner"]
    decision = (f"{R}.kind === 'remind' ? 'reminded' : {R}.kind === 'agenda' ? 'on agenda ' + {R}.meeting_id : "
                f"'register owner told: no meeting'")
    w.finish_key("Mark key done", f"{R}.key", "done", decision, pos=[4680, -200])
    w.decision_log("Decision log", f"{R}.task_id", decision,
                   f"JSON.stringify({{ key: {R}.key, series: {R}.series_id, reason: {R}.why || 'overdue', days_overdue: {R}.days_overdue }})",
                   pos=[4940, -200])
    for n in ["Step 4: Mark it sent", "Step 6: Add the agenda item", "Step 7: Tell the register owner"]:
        w.connect(n, "Mark key done")
    w.connect("Mark key done", "Decision log")
    w.finish_key("Mark key failed", f"{R}.key", "failed", "'write failed: ' + (($json.error && $json.error.message) || 'unknown')",
                 pos=[4680, 200])
    w.exception("Exception queue: write failed", f"{R}.key", "write failed",
                "'A send or write failed; never retried. Check, then release or close the key.'", f"{CFG}.exception_owner", pos=[4940, 200])
    for n in keyed:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- step 10 and step 8 ------------------------------------------------------------
    w.http("Step 10: Mark closed since listed", "PATCH", f"={{{{ {CFG}.agenda_url }}}}/items/{{{{ encodeURIComponent({R}.agenda_item_id) }}}}",
           body="={{ JSON.stringify({ status: 'closed since listed' }) }}", write=True, pos=[3380, 200],
           notes="Marked, never removed.")
    w.connect("Action", "Step 10: Mark closed since listed", output=4)
    w.http("Step 8: Update the tracking list", "PUT", track_url, body=f"={{{{ JSON.stringify({R}.row) }}}}", write=True, pos=[3380, 400])
    w.connect("Action", "Step 8: Update the tracking list", output=5)
    w.http("Step 8: Send the weekly count", "POST", msg,
           body=(f"={{{{ JSON.stringify({{ to: [{CFG}.register_owner], subject: 'Open overdue actions by series: ' + {R}.total, "
                 f"text: Object.entries({R}.counts).map(([s, n]) => s + ': ' + n).join('\\n') || 'None overdue.' }}) }}}}"),
           write=True, pos=[3380, 600], notes="By series, never by person: a per-person ranking is a performance record nobody approved.")
    w.connect("Action", "Step 8: Send the weekly count", output=6)
    w.decision_log("Step 8: Decision log: weekly count", f"'weekly count ' + {R}.date", "'weekly count sent'",
                   f"JSON.stringify({{ by_series: {R}.counts, total: {R}.total }})", pos=[3640, 600])
    w.connect("Step 8: Send the weekly count", "Step 8: Decision log: weekly count")
    w.decision_log("Step 8: Decision log: date change", f"{R}.task_id", f"{R}.row.changes ? 'due date change tracked' : 'first seen'",
                   f"JSON.stringify({{ changes: {R}.row.changes, series: {R}.row.series_id }})", pos=[3640, 400])
    w.connect("Step 8: Update the tracking list", "Step 8: Decision log: date change")
    w.exception("Exception queue: tracking, agenda or count write failed", f"{R}.task_id || ('weekly count ' + {R}.date)", "write failed",
                "'A tracking-list, agenda or count write failed; never retried.'", f"{CFG}.exception_owner", pos=[3900, 500])
    for n in ["Step 10: Mark closed since listed", "Step 8: Update the tracking list", "Step 8: Send the weekly count"]:
        w.connect(n, "Exception queue: tracking, agenda or count write failed", output=1)

    # ---- step 9: after each meeting -----------------------------------------------------
    w.http("Step 9: Read the chair's decisions", "GET", f"={{{{ {CFG}.agenda_url }}}}/items",
           query={"_wrap": "1", "meeting_id": f"={{{{ $('{A}').first().json.body.meeting_id }}}}"}, write=False, error_output=False, pos=[780, 900])
    w.code("Step 9: Rule: new dates", DECISIONS_JS, mode="runOnceForAllItems", pos=[1040, 900])
    w.http("Step 9: Verify the new date", "PATCH", f"={{{{ {CFG}.tracking_url }}}}/rows/{{{{ encodeURIComponent($json.task_id) }}}}",
           body="={{ JSON.stringify({ verified_date: $json.new_date, last_due_seen: $json.new_date, changes: 0 }) }}",
           write=True, pos=[1300, 900], notes="A new date becomes verified and resets the change count; the chair moves the task, not this workflow.")
    w.decision_log("Step 9: Decision log", "$('Step 9: Rule: new dates').item.json.task_id", "'new date verified'",
                   "JSON.stringify({ meeting: $('Step 9: Rule: new dates').item.json.meeting_id, verified_date: $('Step 9: Rule: new dates').item.json.new_date })",
                   pos=[1560, 900])
    w.exception("Step 9: Exception queue: write failed", "$('Step 9: Rule: new dates').item.json.task_id", "write failed",
                "'Verified-date write failed; never retried'", f"{CFG}.exception_owner", pos=[1560, 1100])
    w.connect("After a meeting?", "Step 9: Read the chair's decisions", output=0)
    w.chain("Step 9: Read the chair's decisions", "Step 9: Rule: new dates", "Step 9: Verify the new date", "Step 9: Decision log")
    w.connect("Step 9: Verify the new date", "Step 9: Exception queue: write failed", output=1)
    return w
