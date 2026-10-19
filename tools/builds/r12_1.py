"""R12.1 Pull the weekly figures from source systems into one dated table: rules only, no AI step.

Source: book Chapter 12, recipe R12.1, build steps 1 to 11 and Table 12.2
(recipes/R12.1/build-spec.md).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "n8n"))
from wf import V, Workflow  # noqa: E402

T = "Step 1: Thursday 19:30"

CUTOFF_JS = r"""
// The cut-off: the latest cut-off weekday and time at or before now, in the workflow's time zone.
const cfg = $('Config').first().json;
const [h, m] = String(cfg.cutoff_time).split(':').map(Number);
let c = $now.set({ weekday: cfg.cutoff_weekday, hour: h, minute: m || 0, second: 0, millisecond: 0 });
if (c > $now) c = c.minus({ weeks: 1 });
return cfg.sources.map(s => ({ json: {
  source: s.id, week: c.toISODate(), cutoff: c.toUTC().toISO(),
  export_url: cfg.library_url + '/' + s.export_path,
  control_url: cfg.library_url + '/' + s.control_path,
} }));
"""

FINGERPRINT_JS = r"""
// Step 2: the duplicate key is the week and a fingerprint of every file and control total.
const srcs = $('Step 1: List the sources').all().map(i => i.json);
const files = $('Read source export').all().map(i => i.json);
const controls = $('Read control total').all().map(i => i.json);
const parts = srcs.map((s, i) => {
  const f = files[i] || {}, c = controls[i] || {};
  const file = f.error ? 'missing' : `${f.file}|${f.created}|${(f.rows || []).length}`;
  const total = c.error || c.total === undefined ? 'none' : c.total;
  return `${s.source}=${file}|${total}`;
});
let h = 5381;
for (const ch of parts.join(';')) h = ((h * 33) ^ ch.charCodeAt(0)) >>> 0;
return [{ json: { week: srcs[0].week, cutoff: srcs[0].cutoff, key: `${srcs[0].week}:${h.toString(16)}`, files: parts } }];
"""

RULES_JS = r"""
// Steps 3 to 8 of the book's R12.1, in order, with Table 12.2's statuses.
const cfg = $('Config').first().json;
const fp = $('Step 2: Fingerprint the files').first().json;
const table = $('Read the weekly table').first().json.items || [];
const versions = $('Read versions').first().json.items || [];
const srcs = $('Step 1: List the sources').all().map(i => i.json);
const files = $('Read source export').all().map(i => i.json);
const controls = $('Read control total').all().map(i => i.json);
const approved = Object.fromEntries(($('Read approved rule versions').first().json.items || []).map(r => [r.measure, r.version]));
// The version this run writes, and the current version of an earlier week, for each change from last week.
const seq = v => Number(String(v.id).replace(/\D/g, '')) || 0;
const ver = { version: 'V-' + (Math.max(0, ...versions.map(seq)) + 1) };
const written = versions.filter(v => v.status === 'written');
const earlier = written.filter(v => v.week < fp.week).sort((a, b) => seq(a) - seq(b)).pop();
const lastRows = earlier ? table.filter(r => r.version === earlier.id) : [];
const writtenIds = new Set(written.map(v => v.id));
const history = table.filter(r => writtenIds.has(r.version));
const cutoff = new Date(fp.cutoff);
const OK = ['fresh', 'manual'];

// Step 6 first in code, because a stop writes nothing: each formula must be the version the rule approver approved.
const unapproved = cfg.measures.filter(m => approved[m.name] !== m.rule_version);
if (unapproved.length) {
  return [{ json: { stop: true, detail: unapproved.map(m => `${m.name}: rule ${m.rule_version}, approved ${approved[m.name] || 'none'}`).join('; ') } }];
}

const sources = {};
srcs.forEach((s, i) => {
  const def = cfg.sources.find(d => d.id === s.source);
  const f = files[i] || {}, c = controls[i] || {};
  const rows = Array.isArray(f.rows) ? f.rows : [];
  const info = { id: def.id, name: def.name, data_owner: def.data_owner, file: f.file || null, link: f.link || null,
                 created: f.created || null, row_count: rows.length, control_total: c.error ? null : (c.total ?? null) };
  // Step 3: a fresh, non-empty export: made after the cut-off and covering data to it.
  if (f.error || !f.created || !(new Date(f.created) > cutoff) || !f.covers_to || new Date(f.covers_to) < cutoff || !rows.length) {
    info.status = 'stale';
    info.reason = f.error ? 'export missing' : !rows.length ? 'export empty' : 'export older than the cut-off';
  // Step 4: columns match the saved list.
  } else if (JSON.stringify([...(f.columns || [])].sort()) !== JSON.stringify([...def.columns].sort())) {
    info.status = 'format changed';
    info.reason = `columns ${JSON.stringify(f.columns || [])}, saved list ${JSON.stringify(def.columns)}`;
  // Step 5: totals match the control total; the manual source's rows match its typed row count.
  } else if (info.control_total === null) {
    info.status = 'manual';
  } else {
    const got = def.control_column ? rows.reduce((t, r) => t + Number(r[def.control_column] || 0), 0) : rows.length;
    if (Math.abs(got - Number(info.control_total)) > 0.005) {
      info.status = 'does not reconcile';
      info.reason = `${def.control_column || 'row count'} ${got}, control total ${info.control_total}`;
    } else {
      info.status = def.manual ? 'manual' : 'fresh';
    }
  }
  info.rows = rows;
  sources[def.id] = info;
});

// Step 7: compute each fresh or manual measure and its change from last week.
const match = (r, where) => Object.entries(where || {}).every(([k, v]) => Array.isArray(v) ? v.includes(r[k]) : r[k] === v);
const out = [];
const snapshots = [];
for (const m of cfg.measures) {
  const s = sources[m.source];
  const id = `${ver.version}:${m.id}`;
  const last = lastRows.find(r => r.measure === m.name);
  const good = history.filter(r => r.measure === m.name && OK.includes(r.status)).map(r => r.week).sort().pop() || null;
  const row = { id, version: ver.version, week: fp.week, measure: m.name, kind: m.kind, value: null, change: null,
                cutoff: fp.cutoff, source: s.name, source_link: s.link, status: s.status, note: null, rule_version: m.rule_version };
  if (!OK.includes(s.status)) {
    row.note = s.status === 'stale' ? `stale; last good ${good || 'none'}` : s.status;
    row.last_good = good;
    out.push(row);
    continue;
  }
  const counted = s.rows.filter(r => match(r, m.formula.where));
  const value = m.formula.op === 'sum' ? counted.reduce((t, r) => t + Number(r[m.formula.column] || 0), 0) : counted.length;
  const lastValue = last && OK.includes(last.status) && typeof last.value === 'number' ? last.value : null;
  row.value = value;
  row.change = lastValue === null ? null : Math.round((value - lastValue) * 100) / 100;
  if (s.status === 'manual') row.note = 'manual, not reconciled';
  // Step 8: counts of people below the limit, this week or last, print "fewer than 3" with the change blank.
  const lastFew = last && (last.status === 'fewer than 3' || (typeof last.value === 'number' && last.value < cfg.fewer_than));
  if (m.people && (value < cfg.fewer_than || lastFew)) {
    row.value = `fewer than ${cfg.fewer_than}`;
    row.change = null;
    row.status = `fewer than ${cfg.fewer_than}`;
    row.note = null;
  } else if (m.kind === 'status') {
    // Step 9: a status measure's link opens the snapshot of its counted rows.
    snapshots.push({ id, version: ver.version, measure: m.name, cutoff: fp.cutoff, rows: counted });
    row.source_link = `${cfg.snapshots_url}/snapshots/${encodeURIComponent(id)}`;
  }
  out.push(row);
}

const failed = Object.values(sources).filter(s => !OK.includes(s.status))
  .map(s => ({ source: s.name, data_owner: s.data_owner, status: s.status, reason: s.reason }));
const log = Object.values(sources).map(s => ({ source: s.id, file: s.file, created: s.created, rows: s.row_count, control_total: s.control_total, status: s.status }));
return [{ json: { stop: false, version: ver.version, week: fp.week, cutoff: fp.cutoff, rows: out, snapshots, failed, log } }];
"""

WRITES_JS = r"""
// Step 9: one version record, then one row per measure and one snapshot per status measure.
const cfg = $('Config').first().json;
const r = $('Rules: steps 3 to 8').first().json;
const items = [{ url: `${cfg.table_url}/versions`, body: { id: r.version, week: r.week, cutoff: r.cutoff, status: 'writing', files: r.log } }];
for (const row of r.rows) items.push({ url: `${cfg.table_url}/weekly_table`, body: row });
for (const s of r.snapshots) items.push({ url: `${cfg.snapshots_url}/snapshots`, body: s });
return items.map(i => ({ json: i }));
"""

ALL_WRITTEN_JS = r"""
// Only a complete table is marked written; a failed write went to the exception queue instead.
return $input.all().length === $('Step 9: Rows and snapshots').all().length ? [{ json: { complete: true } }] : [];
"""

FAILED_JS = r"""
// Step 10: one alert per failed source, to the report builder and the source's data owner.
const cfg = $('Config').first().json;
const r = $('Rules: steps 3 to 8').first().json;
return r.failed.map(f => ({ json: {
  source: f.source, reason: f.reason, status: f.status,
  message: { to: [cfg.report_builder, f.data_owner],
             subject: `Weekly figures ${r.week}: ${f.source} ${f.status}`,
             text: `${f.source}: ${f.status} (${f.reason}). Its figures print blank in version ${r.version}.` } } }));
"""


def build() -> Workflow:
    w = Workflow("R12.1", "R12.1 Pull the weekly figures into one dated table")
    w.node(T, "n8n-nodes-base.scheduleTrigger", V["schedule"],
           {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1, "triggerAtDay": [4], "triggerAtHour": 19, "triggerAtMinute": 30}]}},
           pos=[0, 0], notes="Thursday 7:30 p.m. in the workflow's time zone, after the save window; recheck it after each daylight-saving change.")
    w.config("Config", {
        "library_url": "https://<your file store API>",
        "table_url": "https://<your weekly table API>",
        "snapshots_url": "https://<your snapshot list API>",
        "approved_rules_url": "https://<your approved rule versions list API>",
        "messaging_url": "https://<your messaging API>",
        "cutoff_weekday": 4,
        "cutoff_time": "17:00",
        "fewer_than": 3,
        "sources": [
            {"id": "<source>", "name": "<source name>", "export_path": "<path to its export>", "control_path": "<path to its control total>",
             "columns": ["<saved column list>"], "control_column": "<column the control total sums, or empty for the row count>",
             "manual": False, "data_owner": "<its data owner>"}
        ],
        "measures": [
            {"id": "<measure-id>", "name": "<measure>", "source": "<source>", "kind": "<period or status>", "people": False,
             "formula": {"op": "<count or sum>", "column": "<column summed>", "where": {"<column>": "<value>"}},
             "rule_version": "<approved rule version>"}
        ],
        "report_builder": "<your report builder>",
        "rule_approver": "<your rule approver>",
    }, pos=[260, 0])
    w.code("Step 1: List the sources", CUTOFF_JS, mode="runOnceForAllItems", pos=[520, 0],
           notes="One item per source; the cut-off is Config's weekday and time, a dated setting changed only through change control.")
    w.chain(T, "Config", "Step 1: List the sources")

    w.http("Read source export", "GET", "={{ $json.export_url }}", write=False, error_output=False, pos=[780, 0],
           notes="Retried three times; a file that still cannot be read makes its source stale.")
    w.http("Read control total", "GET", "={{ $('Step 1: List the sources').item.json.control_url }}", write=False,
           error_output=False, pos=[1040, 0], notes="No control total: the source's figures are manual.")
    for n in w.nodes:
        if n["name"] in ("Read source export", "Read control total"):
            n["onError"] = "continueRegularOutput"
    w.chain("Step 1: List the sources", "Read source export", "Read control total")

    w.code("Step 2: Fingerprint the files", FINGERPRINT_JS, mode="runOnceForAllItems", pos=[1300, 0])
    w.reserve_key("Step 2: Reserve key", "$json.key", pos=[1560, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1820, 0])
    w.noop("Duplicate: stop", pos=[2080, -200], notes="Every file and control total matches a version already made.")
    w.chain("Read control total", "Step 2: Fingerprint the files", "Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    table = "$('Config').first().json.table_url"
    w.http("Read versions", "GET", f"={{{{ {table} }}}}/versions", query={"_wrap": "1"}, write=False, error_output=False, pos=[2080, 0])
    w.http("Read the weekly table", "GET", f"={{{{ {table} }}}}/weekly_table", query={"_wrap": "1"}, write=False,
           error_output=False, pos=[2340, 0], notes="Earlier versions: last week's figures and each measure's last good date.")
    w.http("Read approved rule versions", "GET", "={{ $('Config').first().json.approved_rules_url }}/approved_rules",
           query={"_wrap": "1"}, write=False, error_output=False, pos=[2600, 0])
    w.code("Rules: steps 3 to 8", RULES_JS, mode="runOnceForAllItems", pos=[2860, 0], notes="Rules decide; there is no AI step in R12.1.")
    w.connect("New key?", "Read versions", output=0)
    w.chain("Read versions", "Read the weekly table", "Read approved rule versions", "Rules: steps 3 to 8")

    # ---- step 6: an unapproved rule version stops the run --------------------
    w.if_("Step 6: Rule version approved?", "={{ $json.stop }}", pos=[3640, 0])
    w.connect("Rules: steps 3 to 8", "Step 6: Rule version approved?")
    msg = "$('Config').first().json.messaging_url"
    w.http("Step 6: Alert the builder and rule approver", "POST", f"={{{{ {msg} }}}}/messages",
           body="={{ JSON.stringify({ to: [$('Config').first().json.report_builder, $('Config').first().json.rule_approver], subject: 'Weekly figures stopped: rule version not approved', text: $json.detail }) }}",
           write=True, error_output=False, pos=[3900, -320])
    w.exception("Exception queue: rule version not approved", "$('Step 2: Fingerprint the files').first().json.week", "rule version not approved",
                "$('Rules: steps 3 to 8').first().json.detail", "$('Config').first().json.report_builder", pos=[4160, -320])
    w.pg("Release key", "DELETE FROM key_log WHERE recipe = $1 AND key = $2 RETURNING key",
         args=['"R12.1"', "$('Step 2: Fingerprint the files').first().json.key"], pos=[4420, -320],
         notes="No version was written, so the same files run again once the rule is approved or restored.")
    w.connect("Step 6: Rule version approved?", "Step 6: Alert the builder and rule approver", output=0)
    w.chain("Step 6: Alert the builder and rule approver", "Exception queue: rule version not approved", "Release key")

    # ---- step 9: write the table ---------------------------------------------
    w.code("Step 9: Rows and snapshots", WRITES_JS, mode="runOnceForAllItems", pos=[3900, 0])
    w.http("Step 9: Write to the weekly table", "POST", "={{ $json.url }}", body="={{ JSON.stringify($json.body) }}",
           write=True, pos=[4160, 0], notes="A write: never retried; a failure is logged and the builder checks the table before any rerun.")
    w.code("All rows written?", ALL_WRITTEN_JS, mode="runOnceForAllItems", pos=[4420, 0])
    w.connect("Step 6: Rule version approved?", "Step 9: Rows and snapshots", output=1)
    w.chain("Step 9: Rows and snapshots", "Step 9: Write to the weekly table", "All rows written?")

    w.code("Step 10: Each failed source", FAILED_JS, mode="runOnceForAllItems", pos=[4680, 200])
    w.http("Step 10: Alert the builder and data owner", "POST", f"={{{{ {msg} }}}}/messages",
           body="={{ JSON.stringify($json.message) }}", write=True, pos=[4940, 200])
    w.exception("Exception queue: source failed", "$('Rules: steps 3 to 8').first().json.week + ':' + $('Step 10: Each failed source').item.json.source",
                "source failed", "$('Step 10: Each failed source').item.json.status + ': ' + $('Step 10: Each failed source').item.json.reason",
                "$('Config').first().json.report_builder", pos=[5200, 200])
    w.connect("All rows written?", "Step 10: Each failed source")
    w.chain("Step 10: Each failed source", "Step 10: Alert the builder and data owner", "Exception queue: source failed")

    r = "$('Rules: steps 3 to 8').first().json"
    w.http("Step 11: Mark the version written", "PATCH", f"={{{{ {table} }}}}/versions/{{{{ {r}.version }}}}",
           body="={{ JSON.stringify({ status: 'written' }) }}", write=True, pos=[4680, 0],
           notes="The latest written version is current: it starts R12.3 and feeds R12.2.")
    w.connect("All rows written?", "Step 11: Mark the version written")
    key = "$('Step 2: Fingerprint the files').first().json.key"
    w.finish_key("Mark key done", key, "done", f"{r}.version", pos=[4940, 0])
    w.decision_log("Decision log", f"{r}.version", "'written'",
                   f"JSON.stringify({{ files: {r}.log, figures: {r}.rows.map(x => ({{ measure: x.measure, value: x.value, change: x.change, status: x.status, rule_version: x.rule_version }})) }})",
                   pos=[5200, 0])
    w.chain("Step 11: Mark the version written", "Mark key done", "Decision log")

    w.finish_key("Mark key failed", key, "failed", "'write failed: ' + ($json.error && $json.error.message || 'unknown')", pos=[4680, 480])
    w.exception("Exception queue: write failed", f"{r}.version", "write failed",
                "'A weekly table write failed; check the table before any rerun'", "$('Config').first().json.report_builder", pos=[4940, 480])
    for n in ["Step 9: Write to the weekly table", "Step 10: Alert the builder and data owner", "Step 11: Mark the version written"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")
    return w
