"""R14.1 Turn a transcript into a draft action list for the chair to verify.

Source: book Chapter 14, recipe R14.1, build steps 1 to 9 (recipes/R14.1/build-spec.md);
AI step: recipes/R14.1/prompts/propose-actions.md.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

T = "Step 1: Transcript saved"
M = "Step 8: Each morning"
EV = f"$('{T}').first().json.body"
KEY = f"{EV}.occurrence_id"
CFG = "$('Config').first().json"
# The check result, from whichever of step 6 or step 9 ran (an If node's first() reads only its true branch).
CHK = "($('Step 9: AI error').isExecuted ? $('Step 9: AI error').first().json : $('Step 6: Rules: check the items').first().json)"

WORKDAY_JS = r"""
// Working days come from Config: the weekdays you work and your holiday dates.
const isWorkday = (d, cfg) => cfg.working_weekdays.includes(d.getUTCDay()) && !cfg.holidays.includes(d.toISOString().slice(0, 10));
const nextWorkday = (d, cfg) => { let x = new Date(d.getTime() + 86400000); while (!isWorkday(x, cfg)) x = new Date(x.getTime() + 86400000); return x; };
const todayUtc = () => new Date(new Date().toISOString().slice(0, 10) + 'T00:00:00Z');
"""

REGISTERED_JS = r"""
// Step 1: only a transcript saved for a series in the register goes on; anything else stops, no AI call.
const series = ($('Step 1: Read the register').first().json.items || [])[0] || null;
return [{ json: { registered: !!series, series } }];
"""

DRAFT_JS = r"""
// Step 2: a re-saved transcript replaces only an untouched draft: every row still "proposed".
const rows = $('Step 2: Read the current draft').first().json.items || [];
const started = rows.some(r => r.status !== 'proposed');
return [{ json: { started, old_ids: rows.map(r => r.id) } }];
"""

SCOPE_JS = r"""
// Step 3: the register's flag plus a title check; a match stops before the AI.
const cfg = $('Config').first().json;
const series = $('Step 1: Rule: registered series?').first().json.series;
const title = String($('Step 3: Read the meeting').first().json.title || '');
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const hit = cfg.out_of_scope_titles.find(w => new RegExp('\\b' + esc(w) + '\\b', 'i').test(title));
const flagged = series.in_scope !== true;
const reason = flagged ? 'series not flagged in scope' : hit ? `title contains "${hit}"` : '';
return [{ json: { in_scope: !flagged && !hit, reason } }];
"""

CHECK_JS = AI_PARSE_JS + WORKDAY_JS + r"""
// Step 6: rules on the proposed items. The AI proposes; these rules decide what is written.
const cfg = $('Config').first().json;
const ev = $('Step 1: Transcript saved').first().json.body;
const lines = $('Read the transcript').first().json.lines || [];
const attendees = $('Step 4: Read attendees').first().json.items || [];
const meeting = $('Step 3: Read the meeting').first().json;
const fail = problem => [{ json: { ok: false, reason: 'AI output failed the check', detail: problem } }];

const p = parseAi($('Step 5: AI call').first().json, ['items']);
if (!p.ok) return fail(p.problem);
if (!Array.isArray(p.value.items)) return fail('items is not a list');
const FIELDS = ['action', 'owner', 'due_date', 'time_stamp', 'quoted_line', 'status'];
for (const it of p.value.items) {
  if (!it || typeof it !== 'object') return fail('an item is not an object');
  for (const f of FIELDS) if (typeof it[f] !== 'string') return fail(`an item is missing ${f}`);
  if (!['agreed', 'discussed, not agreed'].includes(it.status)) return fail('status not one of agreed, discussed, not agreed');
  if (!it.action.trim()) return fail('an item has no action');
  // Each time stamp exists in the transcript.
  if (!lines.some(l => l.time_stamp === it.time_stamp.trim())) return fail(`time stamp ${it.time_stamp} is not in the transcript`);
}

const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const words = s => String(s).toLowerCase().split(/\s+/).filter(w => w.length > 1);
const says = (name, text) => words(name).some(w => new RegExp('\\b' + esc(w) + '\\b', 'i').test(text));
const norm = s => String(s).toLowerCase().replace(/\s+/g, ' ').trim();
const DAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
const meetingDay = new Date(String(meeting.start || new Date().toISOString()).slice(0, 10) + 'T00:00:00Z');
const perLine = {};
for (const it of p.value.items) perLine[it.time_stamp.trim()] = (perLine[it.time_stamp.trim()] || 0) + 1;

const seen = {};
const items = p.value.items.map(it => {
  const ts = it.time_stamp.trim();
  const line = lines.find(l => l.time_stamp === ts);
  const flags = [];
  // Its owner named or speaking there; absent owners become "unassigned".
  let owner = it.owner.trim() || 'unassigned';
  if (owner.toLowerCase() !== 'unassigned') {
    if (!says(owner, line.text) && !says(owner, line.speaker)) { flags.push(`owner "${owner}" not named or speaking at this line`); owner = 'unassigned'; }
    else if (!attendees.some(a => says(owner, a.name))) { flags.push(`owner "${owner}" not an attendee`); owner = 'unassigned'; }
  } else owner = 'unassigned';
  // Unquoted dates are dropped; "by Friday" is dated by rule; "next week" is left to the chair.
  let quoted = it.due_date.trim(), due = quoted;
  if (quoted && !norm(line.text).includes(norm(quoted))) { flags.push(`date "${quoted}" not said at this line`); quoted = ''; due = ''; }
  const day = DAYS.findIndex(d => new RegExp('\\b' + d + '\\b', 'i').test(quoted));
  if (day >= 0) {
    let d = new Date(meetingDay.getTime() + 86400000);
    while (d.getUTCDay() !== day) d = new Date(d.getTime() + 86400000);
    due = d.toISOString().slice(0, 10);
  }
  // Over two items on a line are flagged.
  if (perLine[ts] > cfg.max_items_per_line) flags.push(`more than ${cfg.max_items_per_line} items on this line`);
  seen[ts] = (seen[ts] || 0) + 1;
  const id = `${ev.occurrence_id}-${ts.replace(/\D/g, '')}-${seen[ts]}`;
  const link = cfg.transcript_link.replace('{transcript_id}', encodeURIComponent(ev.transcript_id)).replace('{time_stamp}', encodeURIComponent(ts));
  return { id, occurrence_id: ev.occurrence_id, series_id: ev.series_id, action: it.action.trim(), owner,
           due_date: due, due_date_quoted: quoted, time_stamp: ts, quoted_line: it.quoted_line, agreement: it.status,
           source_link: link, flags, status: 'proposed' };
});
const verifyBy = nextWorkday(todayUtc(), cfg).toISOString().slice(0, 10);
for (const it of items) it.verify_by = verifyBy;
return [{ json: { ok: true, items, verify_by: verifyBy,
  rules: { items: items.length, flagged: items.filter(i => i.flags.length).length, unassigned: items.filter(i => i.owner === 'unassigned').length } } }];
"""

OPS_JS = r"""
// Step 7: write each item as "proposed"; an untouched earlier draft (step 2) is replaced.
const check = $('Step 6: Rules: check the items').first().json;
const keep = new Set(check.items.map(i => i.id));
const ops = $('Step 2: Rule: has the chair started?').first().json.old_ids.filter(id => !keep.has(id)).map(id => ({ op: 'DELETE', id, body: {} }))
  .concat(check.items.map(i => ({ op: 'PUT', id: i.id, body: i })));
return ops.length ? ops.map(o => ({ json: o })) : [{ json: { op: 'none' } }];
"""

COLLECT_JS = r"""
// One message to the chair and backup, whatever the number of items.
const check = $('Step 6: Rules: check the items').first().json;
return [{ json: { items: check.items.length, flagged: check.rules.flagged, verify_by: check.verify_by }, pairedItem: { item: 0 } }];
"""

EXPIRE_JS = WORKDAY_JS + r"""
// Step 8: a draft still unverified after its deadline (the end of the next working day) expires.
const today = todayUtc().toISOString().slice(0, 10);
const rows = ($('Step 8: Read proposed items').first().json.items || []).filter(r => r.status === 'proposed' && r.verify_by && r.verify_by < today);
return rows.map(r => ({ json: { id: r.id, occurrence_id: r.occurrence_id, series_id: r.series_id } }));
"""

EXPIRED_LIST_JS = r"""
// One message to the register owner listing the expired drafts.
const rows = $input.all().map((_, i) => $('Step 8: Rule: past the deadline?').itemMatching(i).json);
const lists = [...new Set(rows.map(r => `${r.series_id} ${r.occurrence_id}`))];
return [{ json: { lists, count: lists.length }, pairedItem: { item: 0 } }];
"""


def build() -> Workflow:
    w = Workflow("R14.1", "R14.1 Turn a transcript into a draft action list for the chair to verify")
    w.webhook(T, "r14-1-transcript-saved",
              "Your transcription service calls this when a transcript is saved. Body: {series_id, occurrence_id, transcript_id}.",
              pos=[0, 0])
    w.schedule(M, 7, "The morning expiry check (step 8).", pos=[0, 700])
    w.config("Config", {
        "register_url": "https://<your meeting register API>",
        "calendar_url": "https://<your calendar API>",
        "transcripts_url": "https://<your transcription API>",
        "actions_url": "https://<your action list API>",
        "messaging_url": "https://<your messaging API>",
        "transcript_link": "https://<your transcript viewer>/{transcript_id}?t={time_stamp}",
        "action_list_link": "https://<your action list>?occurrence={occurrence_id}",
        "out_of_scope_titles": ["HR", "disciplinary", "negotiation"],
        "max_items_per_line": 2,
        "working_weekdays": [1, 2, 3, 4, 5],
        "holidays": ["<your holiday dates, YYYY-MM-DD>"],
        "register_owner": "<your register owner>",
        "exception_owner": "<your workflow editor>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 340])
    w.connect(T, "Config")
    w.connect(M, "Config")
    w.if_("Morning expiry?", f"={{{{ $('{M}').isExecuted }}}}", pos=[520, 340])
    w.connect("Config", "Morning expiry?")

    # ---- steps 1 to 4 ---------------------------------------------------------------
    w.http("Step 1: Read the register", "GET", f"={{{{ {CFG}.register_url }}}}/series",
           query={"_wrap": "1", "id": f"={{{{ {EV}.series_id }}}}"}, write=False, error_output=False, pos=[780, 0])
    w.connect("Morning expiry?", "Step 1: Read the register", output=1)
    w.code("Step 1: Rule: registered series?", REGISTERED_JS, mode="runOnceForAllItems", pos=[1040, 0])
    w.if_("Registered?", "={{ $json.registered }}", pos=[1300, 0])
    w.noop("Not registered: stop", pos=[1560, -200], notes="Not a registered series: no AI call, nothing read.")
    w.chain("Step 1: Read the register", "Step 1: Rule: registered series?", "Registered?")
    w.connect("Registered?", "Not registered: stop", output=1)

    w.reserve_key("Step 2: Reserve key", KEY, pos=[1560, 0])
    w.http("Step 2: Read the current draft", "GET", f"={{{{ {CFG}.actions_url }}}}/items",
           query={"_wrap": "1", "occurrence_id": f"={{{{ {EV}.occurrence_id }}}}"}, write=False, error_output=False, pos=[1820, 0])
    w.code("Step 2: Rule: has the chair started?", DRAFT_JS, mode="runOnceForAllItems", pos=[2080, 0])
    w.if_("Chair started?", "={{ $json.started }}", pos=[2340, 0])
    w.noop("Draft kept: stop", pos=[2600, -200], notes="The chair has started on this draft: it is kept, and nothing is proposed again.")
    w.connect("Registered?", "Step 2: Reserve key", output=0)
    w.chain("Step 2: Reserve key", "Step 2: Read the current draft", "Step 2: Rule: has the chair started?", "Chair started?")
    w.connect("Chair started?", "Draft kept: stop", output=0)

    w.http("Step 3: Read the meeting", "GET", f"={{{{ {CFG}.calendar_url }}}}/occurrences/{{{{ {EV}.occurrence_id }}}}",
           write=False, error_output=False, pos=[2600, 0])
    w.code("Step 3: Rule: in scope?", SCOPE_JS, mode="runOnceForAllItems", pos=[2860, 0])
    w.if_("In scope?", "={{ $json.in_scope }}", pos=[3120, 0])
    w.connect("Chair started?", "Step 3: Read the meeting", output=1)
    w.chain("Step 3: Read the meeting", "Step 3: Rule: in scope?", "In scope?")

    series = "$('Step 1: Rule: registered series?').first().json.series"
    w.exception("Step 3: Exception queue: out of scope", f"{EV}.occurrence_id", "out of scope",
                "'No AI call: ' + $('Step 3: Rule: in scope?').first().json.reason + '; the chair deletes the transcript'",
                f"{series}.chair", pos=[3380, -240])
    w.http("Step 3: Tell the chair to delete the transcript", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: [{series}.chair], subject: 'Transcript out of scope: ' + {series}.name, "
                f"text: 'This meeting is out of scope for action lists (' + $('Step 3: Rule: in scope?').first().json.reason + '). No AI call was made. Please delete transcript ' + {EV}.transcript_id + ' today.' }}) }}}}",
           write=True, pos=[3640, -240])
    w.connect("In scope?", "Step 3: Exception queue: out of scope", output=1)
    w.connect("Step 3: Exception queue: out of scope", "Step 3: Tell the chair to delete the transcript")

    w.http("Step 4: Read attendees", "GET", f"={{{{ {CFG}.calendar_url }}}}/attendees",
           query={"_wrap": "1", "occurrence_id": f"={{{{ {EV}.occurrence_id }}}}"}, write=False, error_output=False, pos=[3380, 0],
           notes="Attendees come from the meeting, never the transcript; they stay in the workflow for step 6.")
    w.http("Read the transcript", "GET", f"={{{{ {CFG}.transcripts_url }}}}/transcripts/{{{{ {EV}.transcript_id }}}}",
           write=False, error_output=False, pos=[3640, 0])
    w.connect("In scope?", "Step 4: Read attendees", output=0)
    w.connect("Step 4: Read attendees", "Read the transcript")

    # ---- steps 5, 6 and 9 -----------------------------------------------------------
    vars_js = ("{ series: $('Step 1: Rule: registered series?').first().json.series.name, "
               "transcript: ($('Read the transcript').first().json.lines || []).map(l => `${l.time_stamp} ${l.speaker}: ${l.text}`).join('\\n') }")
    build_, call = ai_step(w, "Step 5", ROOT / "recipes/R14.1/prompts/propose-actions.md", vars_js,
                           max_tokens=2048, tries=3, pos_build=[3900, 0], pos_call=[4160, 0])
    w.connect("Read the transcript", build_)
    w.code("Step 6: Rules: check the items", CHECK_JS, mode="runOnceForAllItems", pos=[4420, 0],
           notes="The rules decide what is written; the AI only proposes.")
    w.connect(call, "Step 6: Rules: check the items", output=0)
    w.code("Step 9: AI error", "return [{ json: { ok: false, reason: 'AI error after two retries', detail: String(($json.error && $json.error.message) || '') } }];",
           mode="runOnceForAllItems", pos=[4420, 240])
    w.connect(call, "Step 9: AI error", output=1)
    w.if_("Items pass the check?", "={{ $json.ok }}", pos=[4680, 0])
    w.connect("Step 6: Rules: check the items", "Items pass the check?")
    w.connect("Step 9: AI error", "Items pass the check?")

    w.exception("Step 9: Exception queue: chair writes the list", f"{EV}.occurrence_id", "chair writes the list from the read-back",
                f"{CHK}.reason + ': ' + ({CHK}.detail || '')",
                f"{series}.chair", pos=[4940, 240])
    w.http("Step 9: Tell the chair to use the read-back", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: [{series}.chair, {series}.backup], subject: 'No draft action list: ' + {series}.name, "
                f"text: 'No draft could be proposed for this meeting (' + {CHK}.reason + '). Please write the action list from the read-back.' }}) }}}}",
           write=True, pos=[5200, 240])
    w.connect("Items pass the check?", "Step 9: Exception queue: chair writes the list", output=1)
    w.connect("Step 9: Exception queue: chair writes the list", "Step 9: Tell the chair to use the read-back")

    # ---- step 7 ----------------------------------------------------------------------
    w.code("Step 7: Rows to write", OPS_JS, mode="runOnceForAllItems", pos=[4940, 0])
    w.if_("Anything to write?", "={{ $json.op !== 'none' }}", pos=[5200, 0])
    w.http("Step 7: Write proposed items", "={{ $json.op }}", f"={{{{ {CFG}.actions_url }}}}/items/{{{{ encodeURIComponent($json.id) }}}}",
           body="={{ JSON.stringify($json.body) }}", write=True, pos=[5460, -120],
           notes="Each item as \"proposed\", linked to its line; rows of an untouched earlier draft are removed. A write: never retried.")
    w.code("Step 7: One message", COLLECT_JS, mode="runOnceForAllItems", pos=[5720, 0])
    w.http("Step 7: Send the chair and backup the link", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: [{series}.chair, {series}.backup], subject: 'Draft action list to verify: ' + {series}.name, "
                f"text: $json.items + ' proposed item(s), ' + $json.flagged + ' flagged. Verify by the end of ' + $json.verify_by + ': ' + "
                f"{CFG}.action_list_link.replace('{{occurrence_id}}', encodeURIComponent({EV}.occurrence_id)) }}) }}}}",
           write=True, pos=[5980, 0])
    w.connect("Items pass the check?", "Step 7: Rows to write", output=0)
    w.connect("Step 7: Rows to write", "Anything to write?")
    w.connect("Anything to write?", "Step 7: Write proposed items", output=0)
    w.connect("Anything to write?", "Step 7: One message", output=1)
    w.connect("Step 7: Write proposed items", "Step 7: One message")
    w.connect("Step 7: One message", "Step 7: Send the chair and backup the link")

    # ---- key log and decision log ---------------------------------------------------
    scope = "$('Step 3: Rule: in scope?').first().json"
    outcome = (f"{scope}.in_scope === false ? 'out of scope: no AI call' : "
               f"{CHK}.ok ? 'proposed ' + {CHK}.items.length + ' item(s)' : 'chair writes the list: ' + {CHK}.reason")
    w.finish_key("Mark key done", KEY, "done", outcome, pos=[6240, 0])
    w.decision_log("Decision log", f"{EV}.occurrence_id", outcome,
                   f"JSON.stringify({scope}.in_scope === false ? {{ scope: {scope}.reason }} : ({CHK}.rules || {{ ai: {CHK}.reason }}))", pos=[6500, 0])
    for n in ["Step 3: Tell the chair to delete the transcript", "Step 9: Tell the chair to use the read-back",
              "Step 7: Send the chair and backup the link"]:
        w.connect(n, "Mark key done")
    w.connect("Mark key done", "Decision log")

    w.finish_key("Mark key failed", KEY, "failed", "'write failed'", pos=[6240, 480])
    w.exception("Exception queue: write failed", f"{EV}.occurrence_id", "write failed",
                "'An action-list write or message failed; never retried. Check the draft, then release the key.'",
                f"{CFG}.exception_owner", pos=[6500, 480])
    for n in ["Step 3: Tell the chair to delete the transcript", "Step 9: Tell the chair to use the read-back",
              "Step 7: Write proposed items", "Step 7: Send the chair and backup the link"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- step 8: morning expiry ------------------------------------------------------
    w.http("Step 8: Read proposed items", "GET", f"={{{{ {CFG}.actions_url }}}}/items",
           query={"_wrap": "1", "status": "proposed"}, write=False, error_output=False, pos=[780, 700])
    w.code("Step 8: Rule: past the deadline?", EXPIRE_JS, mode="runOnceForAllItems", pos=[1040, 700])
    w.http("Step 8: Mark expired", "PATCH", f"={{{{ {CFG}.actions_url }}}}/items/{{{{ encodeURIComponent($json.id) }}}}",
           body="={{ JSON.stringify({ status: 'expired' }) }}", write=True, pos=[1300, 700])
    w.decision_log("Step 8: Decision log", "$('Step 8: Rule: past the deadline?').item.json.id", "'expired unverified'",
                   "JSON.stringify({ occurrence: $('Step 8: Rule: past the deadline?').item.json.occurrence_id, series: $('Step 8: Rule: past the deadline?').item.json.series_id })",
                   pos=[1560, 560])
    w.code("Step 8: One message", EXPIRED_LIST_JS, mode="runOnceForAllItems", pos=[1560, 700])
    w.http("Step 8: Tell the register owner", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: [{CFG}.register_owner], subject: $json.count + ' draft action list(s) expired unverified', "
                "text: 'The chair or backup types these actions in: ' + $json.lists.join('; ') }) }}",
           write=True, pos=[1820, 700])
    w.exception("Step 8: Exception queue: write failed", "$('Step 8: Rule: past the deadline?').item.json.id", "write failed",
                "'Expiry write failed; never retried'", f"{CFG}.exception_owner", pos=[1560, 900])
    w.exception("Step 8: Exception queue: message failed", "'expiry ' + new Date().toISOString().slice(0, 10)", "write failed",
                "'Message to the register owner failed; never retried: ' + $('Step 8: One message').first().json.lists.join('; ')",
                f"{CFG}.exception_owner", pos=[2080, 900])
    w.connect("Morning expiry?", "Step 8: Read proposed items", output=0)
    w.chain("Step 8: Read proposed items", "Step 8: Rule: past the deadline?", "Step 8: Mark expired")
    w.connect("Step 8: Mark expired", "Step 8: Decision log")
    w.connect("Step 8: Mark expired", "Step 8: One message")
    w.connect("Step 8: One message", "Step 8: Tell the register owner")
    w.connect("Step 8: Mark expired", "Step 8: Exception queue: write failed", output=1)
    w.connect("Step 8: Tell the register owner", "Step 8: Exception queue: message failed", output=1)
    return w
