"""R12.1 Pull the weekly figures from source systems into one dated table, as a Make scenario: rules only, no AI step.

Source: book Chapter 12, recipe R12.1, build steps 1 to 11 and Table 12.2 (recipes/R12.1/build-spec.md).
The rules are the n8n build's own JavaScript (tools/builds/r12_1.py), run through n8n_rule.
One scenario, because the recipe's only trigger is the schedule: every Thursday at 19:30, after
the save window.

Time zone: n8n's $now is Luxon in the workflow's time zone; Make's Code app has no Luxon and runs
in UTC, so the cut-off rule gets a small $now shim (set, minus, toISODate, toUTC, toISO) and the
cut-off weekday and time in Config are read as UTC. Set them as the UTC equivalent of your local
cut-off, and recheck them after each daylight-saving change.

The two reads per source keep the n8n build's fallback: a file or control total that cannot be
read is passed on as an error, so its source prints stale (or manual). A Make step has one error
handler, so these reads pass an error status on instead of retrying it; a connection that fails
outright is retried.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R12.1"
N8N = n8n_build(R)
T = N8N.T
LIST, FP, RULES = "Step 1: List the sources", "Step 2: Fingerprint the files", "Rules: steps 3 to 8"
CONFIG = {
    "library_url": "https://<your file store API>",
    "table_url": "https://<your weekly table API>",
    "snapshots_url": "https://<your snapshot list API>",
    "approved_rules_url": "https://<your approved rule versions list API>",
    "messaging_url": "https://<your messaging API>",
    # The cut-off, in UTC: Make's Code app runs in UTC (see the docstring).
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
}

NOW_SHIM = r"""
// $now: the Luxon DateTime methods the cut-off rule uses, in UTC (Make's Code app has no Luxon).
// set({ weekday }) moves within the ISO week (Monday 1 to Sunday 7), as Luxon does.
const $now = (() => {
  const DAY = 86400000;
  const at = (ms) => ({
    valueOf: () => ms,
    set(o) {
      const d = new Date(ms);
      if (o.weekday !== undefined) d.setTime(d.getTime() + (o.weekday - (((d.getUTCDay() + 6) % 7) + 1)) * DAY);
      if (o.hour !== undefined) d.setUTCHours(o.hour);
      if (o.minute !== undefined) d.setUTCMinutes(o.minute);
      if (o.second !== undefined) d.setUTCSeconds(o.second);
      if (o.millisecond !== undefined) d.setUTCMilliseconds(o.millisecond);
      return at(d.getTime());
    },
    minus: (o) => at(ms - ((o.weeks || 0) * 7 + (o.days || 0)) * DAY),
    toISODate: () => new Date(ms).toISOString().slice(0, 10),
    toUTC() { return this; },
    toISO: () => new Date(ms).toISOString(),
  });
  return at(Date.now());
})();
"""

# The aggregator holds each source's two reads with their HTTP status; n8n passes a failed read on
# as an item with an error, and these lines give the rules the same items.
READS = r"""
// Each source's export and control total, as the n8n build's reads pass them on: a failed read is { error }.
const asRead = (data, status) => (Number(status) >= 300 || data === undefined || data === null || data === ''
  ? { error: 'HTTP ' + status } : (typeof data === 'string' ? JSON.parse(data) : data));
DATA['Read source export'] = DATA['Sources read'].map(i => ({ json: asRead(i.json.export, i.json.export_status) }));
DATA['Read control total'] = DATA['Sources read'].map(i => ({ json: asRead(i.json.control, i.json.control_status) }));
"""

# Steps 9 and 10 of the n8n build are Code nodes that only lay out the writes and the alerts from the
# rules' result; they run here, unchanged, inside the rules step, so the scenario has one Code step fewer.
LAYOUT = ("const __config = () => $('Config').first().json;\n"
          "const __as = (r) => (n) => { const j = n === 'Config' ? __config() : r; return { first: () => ({ json: j }), all: () => [{ json: j }] }; };\n"
          "// Step 9: Rows and snapshots (n8n build), for one rules result.\n"
          "const rowsAndSnapshots = (result) => { const $ = __as(result);\n" + N8N.WRITES_JS.strip() + "\n};\n"
          "// Step 10: Each failed source (n8n build), for one rules result.\n"
          "const eachFailedSource = (result) => { const $ = __as(result);\n" + N8N.FAILED_JS.strip() + "\n};\n")


def build_scenario() -> Scenario:
    s = Scenario(R, "R12.1 Pull the weekly figures into one dated table", "schedule", test_key=T, schedule="every Thursday at 19:30")
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    conf = "{{" + f"{c}.result" + "}}"
    s.flow += s.stop_flag()
    # Step 1: one item per source; the cut-off is Config's weekday and time, changed only through change control.
    code, inputs = n8n_rule(N8N.CUTOFF_JS, {"Config": conf}, many=True, prelude=NOW_SHIM)
    step1 = s.code(LIST, code, inputs)
    step1["filter"] = s.continue_unless_stopped()
    s.flow.append(step1)
    s.flow.append(s.iterator("Each source", "{{" + f"{s.ref(LIST)}.result.items" + "}}"))
    it = s.ref("Each source")
    for name, url in (("Read source export", "export_url"), ("Read control total", "control_url")):
        m = s.http(name, "GET", "{{" + f"{it}.{url}" + "}}")
        # An error status passes on: a file that cannot be read makes its source stale, no control total makes it manual.
        # A connection that fails outright still gets the Retry handler.
        m["mapper"]["stopOnHttpError"] = False
        s.flow.append(m)
    ex, ct = s.ref("Read source export"), s.ref("Read control total")
    s.flow.append(s.aggregator("Sources read", "Each source", {
        "export": "{{" + f"{ex}.data" + "}}", "export_status": "{{" + f"{ex}.statusCode" + "}}",
        "control": "{{" + f"{ct}.data" + "}}", "control_status": "{{" + f"{ct}.statusCode" + "}}"}))
    srcs = "{{" + f"{s.ref(LIST)}.result.items" + "}}"
    agg = "{{" + f"{s.ref('Sources read')}.array" + "}}"

    # Step 2: the duplicate key is the week and a fingerprint of every file and control total.
    code, inputs = n8n_rule(N8N.FINGERPRINT_JS, {LIST: srcs, "Sources read": agg}, items=(LIST, "Sources read"),
                            input_node=LIST, prelude=READS, bodies={
        "key_q": "encodeURIComponent(out.key)",
        "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: out.key }})",
    })
    s.flow.append(s.code(FP, code, inputs))
    fp = s.ref(FP)
    fpo = lambda f: "{{" + f"{fp}.result.{f}" + "}}"  # noqa: E731
    s.flow.append(s.rpc("Step 2: Reserve key", "reserve_key", fpo("reserve_body")))
    versions = s.http("Read versions", "GET", cfg("table_url") + "/versions", query={"_wrap": "1"})
    versions["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: every file and control total matches a version made
    s.flow.append(versions)
    s.flow.append(s.http("Read the weekly table", "GET", cfg("table_url") + "/weekly_table", query={"_wrap": "1"}))
    s.flow.append(s.http("Read approved rule versions", "GET", cfg("approved_rules_url") + "/approved_rules", query={"_wrap": "1"}))
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    week = "$('Step 2: Fingerprint the files').first().json.week"
    code, inputs = n8n_rule(N8N.RULES_JS, {
        "Config": conf, FP: "{{" + f"{fp}.result" + "}}", "Read the weekly table": data("Read the weekly table"),
        "Read versions": data("Read versions"), LIST: srcs, "Sources read": agg,
        "Read approved rule versions": data("Read approved rule versions"),
    }, items=(LIST, "Sources read"), input_node="Read approved rule versions", prelude=READS + LAYOUT, bodies={
        "stopped": "out.stop ? 'yes' : 'no'",
        # Step 6: an unapproved rule version stops the run, and the same files run again once it is approved.
        "stop_message": "JSON.stringify({ to: [__config().report_builder, __config().rule_approver], "
                        "subject: 'Weekly figures stopped: rule version not approved', text: out.detail })",
        "stop_exception": f"JSON.stringify({{ recipe: '{R}', item: {week}, reason: 'rule version not approved', "
                          "detail: out.detail, owner: __config().report_builder })",
        "release_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: $('Step 2: Fingerprint the files').first().json.key }})",
        # Step 9: one version record, then one row per measure and one snapshot per status measure.
        "writes": "out.stop ? [] : rowsAndSnapshots(out).map(i => ({ url: i.json.url, body: JSON.stringify(i.json.body) }))",
        # Step 10: one alert per failed source, to the report builder and the source's data owner.
        "failed": f"out.stop ? [] : eachFailedSource(out).map(i => ({{ message: JSON.stringify(i.json.message), "
                  f"exception: JSON.stringify({{ recipe: '{R}', item: out.week + ':' + i.json.source, reason: 'source failed', "
                  "detail: i.json.status + ': ' + i.json.reason, owner: __config().report_builder }) }))",
        "version_q": "encodeURIComponent(out.version || '')",
        "done_body": "JSON.stringify({ status: 'done', result: out.version })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: out.version, decision: 'written', rules: {{ files: out.log, "
                    "figures: (out.rows || []).map(x => ({ measure: x.measure, value: x.value, change: x.change, status: x.status, rule_version: x.rule_version })) } })",
        "failed_body": f"JSON.stringify({{ recipe: '{R}', item: out.version, reason: 'write failed', "
                       "detail: 'A weekly table write failed; check the table before any rerun', owner: __config().report_builder })",
    })
    s.flow.append(s.code(RULES, code, inputs))  # rules decide; there is no AI step in R12.1
    ru = s.ref(RULES)
    out = lambda f: "{{" + f"{ru}.result.{f}" + "}}"  # noqa: E731
    msg = cfg("messaging_url") + "/messages"
    key_q = fpo("key_q")

    def failed(step: str) -> list[dict]:
        # A write: never retried; a failure is logged and the builder checks the table before any rerun.
        return s.write_failed(step, key_q, out("failed_body"))

    stop = [s.http("Step 6: Alert the builder and rule approver", "POST", msg, body=out("stop_message"), parse=False),
            s.exception("Exception queue: rule version not approved", out("stop_exception")),
            # No version was written, so the same files run again once the rule is approved or restored.
            s.release_key("Release key", out("release_body"))]

    write_each = s.iterator("Step 9: Rows and snapshots", out("writes"))
    wi = s.ref("Step 9: Rows and snapshots")
    write = s.http("Step 9: Write to the weekly table", "POST", "{{" + f"{wi}.url" + "}}", body="{{" + f"{wi}.body" + "}}",
                   parse=False, onerror=failed("Step 9: Write to the weekly table"))
    # Only a complete table is marked written; a failed write went to the exception queue instead.
    written = s.aggregator("All rows written?", "Step 9: Rows and snapshots", {"written": "{{" + f"{wi}.url" + "}}"})
    aw = s.ref("All rows written?")
    complete = s.when("every write succeeded", "{{length(" + f"{aw}.array" + ")}}", "{{length(" + f"{ru}.result.writes" + ")}}", "number:equal")
    mark = s.http("Step 11: Mark the version written", "PATCH", cfg("table_url") + "/versions/" + out("version_q"),
                  body='{"status": "written"}', parse=False, onerror=failed("Step 11: Mark the version written"))
    # The latest written version is current: it starts R12.3 and feeds R12.2.
    closing = [mark, s.finish_key("Mark key done", key_q, out("done_body")), s.decision_log("Decision log", out("log_body"))]
    each_failed = s.iterator("Step 10: Each failed source", out("failed"))
    fi = s.ref("Step 10: Each failed source")
    alerts = [each_failed,
              s.http("Step 10: Alert the builder and data owner", "POST", msg, body="{{" + f"{fi}.message" + "}}", parse=False,
                     onerror=failed("Step 10: Alert the builder and data owner")),
              s.exception("Exception queue: source failed", "{{" + f"{fi}.exception" + "}}")]
    after = s.router("Table complete", [(None, alerts), (None, closing)])
    after["filter"] = complete
    s.flow.append(s.router("Step 6: Rule version approved?", [
        (s.when("rule version not approved", out("stopped"), "yes"), stop),
        (s.when("rule versions approved", out("stopped"), "no"), [write_each, write, written, after]),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R12.1/make/, scenario)."""
    return [("blueprint.json", build_scenario())]
