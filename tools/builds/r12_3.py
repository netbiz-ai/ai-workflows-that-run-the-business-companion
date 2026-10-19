"""R12.3 Alert the owner when a measure crosses its threshold: rules only, no AI step.

Source: book Chapter 12, recipe R12.3, build steps 1 to 9 (recipes/R12.3/build-spec.md).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "n8n"))
from wf import V, Workflow  # noqa: E402

T = "Step 1: Table version current"
F = "Step 8: Friday 16:00"
EV = f"$('{T}').item.json.body"

OUTCOME_JS = r"""
// Step 2: each measure's outcome. Step 5 compares with the line; step 9 picks the line in force.
const cfg = $('Config').first().json;
const version = $('Read the version').first().json;
if (version.status !== 'written') return [];
const rows = $('Read the table rows').first().json.items || [];
const lines = $('Read the threshold list').first().json.items || [];
const versions = $('Read versions').first().json.items || [];
const all = $('Read earlier rows').first().json.items || [];
const FAILED = ['stale', 'format changed', 'does not reconcile'];
const WEEK = 7 * 86400000;

// Step 9: a line version is in force for a week only if its system-stamped approval came before that
// week's counting period began (the previous cut-off): it takes effect from the next cut-off after approval.
function lineFor(measure, cutoff) {
  const start = new Date(cutoff).getTime() - WEEK;
  return lines.filter(l => l.measure === measure && l.approved_at && new Date(l.approved_at).getTime() <= start)
    .sort((a, b) => Number(a.version) - Number(b.version)).pop() || null;
}
// Step 5: compare the value or the change with the line, in its direction; "inclusive" says whether landing on it counts.
function past(row, line) {
  const x = row[line.field];
  if (typeof x !== 'number') return false;
  if (line.direction === 'above') return line.inclusive ? x >= line.line : x > line.line;
  return line.inclusive ? x <= line.line : x < line.line;
}
// The optional second-week rule reads the current version of the week before.
const seq = v => Number(String(v.id).replace(/\D/g, '')) || 0;
const prev = versions.filter(v => v.status === 'written' && v.week < version.week).sort((a, b) => seq(a) - seq(b)).pop();
const prevRows = prev ? all.filter(r => r.version === prev.id) : [];

return rows.map(row => {
  const line = lineFor(row.measure, row.cutoff);
  const base = { week: row.week, version: row.version, measure: row.measure, value: row.value, change: row.change,
                 cutoff: row.cutoff, source: row.source, source_link: row.source_link, status: row.status, last_good: row.last_good || null,
                 line_version: line ? line.version : null, line: line ? line.line : null, field: line ? line.field : null,
                 direction: line ? line.direction : null, inclusive: line ? !!line.inclusive : null,
                 measure_owner: line ? line.measure_owner : null, data_owner: line ? line.data_owner : null };
  let outcome;
  if (String(row.status).startsWith('fewer than')) outcome = 'not checked';  // Table 12.2: never checked
  else if (!line) outcome = 'no line';
  else if (FAILED.includes(row.status)) outcome = 'stale';
  else if (!past(row, line)) outcome = 'within the line';
  else if (cfg.second_week_only) {
    const before = prevRows.find(r => r.measure === row.measure);
    const prevLine = before ? lineFor(before.measure, before.cutoff) : null;
    outcome = before && prevLine && past(before, prevLine) ? 'past the line' : 'past the line, first week';
  } else outcome = 'past the line';
  return { json: Object.assign(base, { outcome, key: `${row.week}:${row.measure}:${line ? line.version : 'none'}:${outcome}` }) };
});
"""

ALERT_JS = r"""
// Steps 4 and 6: the alert text. It explains nothing and suggests no action.
const o = $('Step 2: Rule: each measure\'s outcome').item.json;
if (o.outcome === 'stale') {
  return { json: { to: o.data_owner, kind: 'stale',
    subject: `Weekly figures: ${o.measure} is ${o.status}`,
    text: `${o.measure} printed blank (${o.status}) at the ${o.cutoff} cut-off. Source: ${o.source} ${o.source_link || ''}. Last good: ${o.last_good || 'none'}.` } };
}
const cmp = (o.direction === 'above' ? (o.inclusive ? 'at or above' : 'above') : (o.inclusive ? 'at or below' : 'below'));
return { json: { to: o.measure_owner, kind: 'past the line',
  subject: `Weekly figures: ${o.measure} is past your line`,
  text: `${o.measure}: value ${o.value}, change ${o.change === null ? 'none' : o.change}; your line is ${o.field} ${cmp} ${o.line} (line version ${o.line_version}). Cut-off ${o.cutoff}. Source: ${o.source_link}` } };
"""

UNSEEN_JS = r"""
// Step 8: alerts from the last week not marked "seen" become open issues in the pre-read.
const alerts = $('Read the alert log').first().json.items || [];
const since = Date.now() - 7 * 86400000;
return alerts.filter(a => a.seen !== true && new Date(a.cutoff).getTime() >= since)
  .map(a => ({ json: { id: a.id, measure: a.measure, owner: a.to, text: `Alert not seen: ${a.subject}` } }));
"""


def build() -> Workflow:
    w = Workflow("R12.3", "R12.3 Alert the owner when a measure crosses its threshold")
    w.webhook(T, "r12-3-version-current",
              "Your weekly table calls this when R12.1 marks a version written, which makes it current. Body: {version}.", pos=[0, 0])
    w.node(F, "n8n-nodes-base.scheduleTrigger", V["schedule"],
           {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1, "triggerAtDay": [5], "triggerAtHour": 16, "triggerAtMinute": 0}]}},
           pos=[0, 560], notes="Friday 4 p.m.: unseen alerts become open issues in the pre-read (step 8).")
    w.config("Config", {
        "table_url": "https://<your weekly table API>",
        "thresholds_url": "https://<your threshold list API>",
        "chat_url": "https://<your Teams or chat API>",
        "email_url": "https://<your email API>",
        "alert_log_url": "https://<your alert log API>",
        "preread_url": "https://<your pre-read API>",
        "second_week_only": False,
        "list_editor": "<your threshold list editor>",
    }, pos=[260, 280])
    w.connect(T, "Config")
    w.connect(F, "Config")
    w.if_("Friday check?", f"={{{{ $('{F}').isExecuted }}}}", pos=[520, 280])
    w.connect("Config", "Friday check?")

    # ---- a version becomes current ------------------------------------------
    cfg = "$('Config').first().json"
    w.http("Read the version", "GET", f"={{{{ {cfg}.table_url }}}}/versions/{{{{ {EV}.version }}}}", write=False, error_output=False, pos=[780, 0])
    w.http("Read the table rows", "GET", f"={{{{ {cfg}.table_url }}}}/weekly_table",
           query={"_wrap": "1", "version": f"={{{{ {EV}.version }}}}"}, write=False, error_output=False, pos=[1040, 0])
    w.http("Read the threshold list", "GET", f"={{{{ {cfg}.thresholds_url }}}}/lines", query={"_wrap": "1"},
           write=False, error_output=False, pos=[1300, 0], notes="Every line version, with its system-stamped approval.")
    w.http("Read versions", "GET", f"={{{{ {cfg}.table_url }}}}/versions", query={"_wrap": "1"}, write=False, error_output=False, pos=[1560, 0])
    w.http("Read earlier rows", "GET", f"={{{{ {cfg}.table_url }}}}/weekly_table", query={"_wrap": "1"}, write=False,
           error_output=False, pos=[1820, 0], notes="Last week's figures, for the optional second-week rule.")
    w.code("Step 2: Rule: each measure's outcome", OUTCOME_JS, mode="runOnceForAllItems", pos=[2080, 0],
           notes="One item per measure; steps 5 and 9 are applied here. A measure marked \"fewer than 3\" is never checked.")
    w.connect("Friday check?", "Read the version", output=1)
    w.chain("Read the version", "Read the table rows", "Read the threshold list", "Read versions", "Read earlier rows",
            "Step 2: Rule: each measure's outcome")

    w.reserve_key("Step 3: Reserve key", "$json.key", pos=[2340, 0])
    w.if_("New outcome?", "={{ $json.is_new }}", pos=[2600, 0])
    w.chain("Step 2: Rule: each measure's outcome", "Step 3: Reserve key", "New outcome?")
    o = "$('Step 2: Rule: each measure\\'s outcome').item.json"
    w.switch("Outcome", f"={{{{ {o}.outcome }}}}", ["stale", "past the line"], pos=[2860, -80])
    w.connect("New outcome?", "Outcome", output=0)

    w.code("Steps 4 and 6: Alert text", ALERT_JS, pos=[3120, -200],
           notes="Step 4 tells the data owner the source and last good date; step 6 tells the measure owner the value, line, change, cut-off and link.")
    w.connect("Outcome", "Steps 4 and 6: Alert text", output=0)
    w.connect("Outcome", "Steps 4 and 6: Alert text", output=1)
    body = "={{ JSON.stringify({ to: $json.to, subject: $json.subject, text: $json.text }) }}"
    w.http("Steps 4 and 6: Post the alert", "POST", f"={{{{ {cfg}.chat_url }}}}/messages", body=body, write=False, pos=[3380, -200],
           notes="Retried three times (book), safe because step 3's key stops a double alert; then by email.")
    a = "$('Steps 4 and 6: Alert text').item.json"
    w.http("Steps 4 and 6: Email the alert", "POST", f"={{{{ {cfg}.email_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: {a}.to, subject: {a}.subject, text: {a}.text }}) }}}}", write=True, pos=[3640, -40],
           notes="After three failed posts. A write: never retried.")
    w.http("Steps 4 and 6: Add to the alert log", "POST", f"={{{{ {cfg}.alert_log_url }}}}/alerts",
           body=f"={{{{ JSON.stringify({{ id: {o}.key, week: {o}.week, measure: {o}.measure, outcome: {o}.outcome, to: {a}.to, subject: {a}.subject, cutoff: {o}.cutoff, seen: false }}) }}}}",
           write=True, pos=[3900, -200], notes="Owners read the log and mark each alert seen.")
    w.connect("Steps 4 and 6: Alert text", "Steps 4 and 6: Post the alert")
    w.connect("Steps 4 and 6: Post the alert", "Steps 4 and 6: Add to the alert log", output=0)
    w.connect("Steps 4 and 6: Post the alert", "Steps 4 and 6: Email the alert", output=1)
    w.connect("Steps 4 and 6: Email the alert", "Steps 4 and 6: Add to the alert log", output=0)

    w.finish_key("Mark key done", f"{o}.key", "done", "$('Steps 4 and 6: Alert text').item.json.kind + ' alert sent'", pos=[4160, -200])
    w.connect("Steps 4 and 6: Add to the alert log", "Mark key done")
    decision = (f"{o}.outcome + ($('New outcome?').item.json.is_new ? "
                f"(['stale', 'past the line'].includes({o}.outcome) ? ': alert sent' : ': no alert') : ': alert suppressed, outcome unchanged')")
    w.decision_log("Step 7: Log every check", f"{o}.week + ':' + {o}.measure", decision,
                   f"JSON.stringify({{ version: {o}.version, value: {o}.value, change: {o}.change, status: {o}.status, line_version: {o}.line_version, line: {o}.line, field: {o}.field, direction: {o}.direction }})",
                   pos=[4420, 0])
    w.connect("Mark key done", "Step 7: Log every check")
    w.connect("Outcome", "Step 7: Log every check", output=2)
    w.connect("New outcome?", "Step 7: Log every check", output=1)
    for n in w.nodes:
        if n["name"] == "Outcome":
            n["parameters"]["options"] = {"fallbackOutput": "extra"}

    w.finish_key("Mark key failed", f"{o}.key", "failed", "'alert failed: ' + ($json.error && $json.error.message || 'unknown')", pos=[4160, 240])
    w.exception("Exception queue: alert failed", f"{o}.week + ':' + {o}.measure", "alert failed",
                f"'Post and email failed for ' + {a}.to + '; reassign the measure or fix the address'",
                f"{cfg}.list_editor", pos=[4420, 240])
    w.connect("Steps 4 and 6: Email the alert", "Mark key failed", output=1)
    w.connect("Steps 4 and 6: Add to the alert log", "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: alert failed")

    # ---- step 8: Friday 4 p.m. ------------------------------------------------
    w.http("Read the alert log", "GET", f"={{{{ {cfg}.alert_log_url }}}}/alerts", query={"_wrap": "1"}, write=False,
           error_output=False, pos=[780, 560])
    w.code("Step 8: Rule: alerts not seen", UNSEEN_JS, mode="runOnceForAllItems", pos=[1040, 560])
    w.http("Step 8: Open issue in the pre-read", "POST", f"={{{{ {cfg}.preread_url }}}}/open_issues",
           body="={{ JSON.stringify({ alert: $json.id, measure: $json.measure, owner: $json.owner, text: $json.text }) }}",
           write=True, error_output=False, pos=[1300, 560])
    w.connect("Friday check?", "Read the alert log", output=0)
    w.chain("Read the alert log", "Step 8: Rule: alerts not seen", "Step 8: Open issue in the pre-read")
    return w
