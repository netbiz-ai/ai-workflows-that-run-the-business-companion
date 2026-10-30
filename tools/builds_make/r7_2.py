"""R7.2 Match the invoice to the purchase order and delivery receipt, as Make scenarios.

Source: book Chapter 7, recipe R7.2, build steps 1 to 9 and Table 7.1 (recipes/R7.2/build-spec.md);
AI step: recipes/R7.2/prompts/pair-line.md. The rules are the n8n build's own JavaScript
(tools/builds/r7_2.py), run through n8n_rule. The AI only proposes a pairing; the rules apply
Table 7.1 and a person approves. It never pays or changes an order.
Two scenarios, because a Make scenario has one trigger: a ready invoice (webhook, steps 1 to 7,
blueprint.json) and the approver's decision (webhook, steps 8 and 9, approval.blueprint.json).
n8n's "Approval decision?" node only asked which trigger ran, so it is not built.

Differences from the n8n build, all forced by Make:
- Every lookup tries three times, as n8n's reads do, with each try in the error route of the one
  before (mk with_tries); after the third failed try the status is passed on and the next rule
  stops the invoice with "lookup error". n8n sends every stop (held, no PO or receipt, a lookup
  error, a Table 7.1 failure, a failed reservation) to one "Exception: Stop the invoice" node.
  Make branches never meet again, so each stop route repeats the closing steps (mark the record
  stopped, decision log, one R7.4 queue item per reason code), with the stop in the step's name.
- To keep the stop routes few, the rules run several n8n Code nodes in one Make Code step, each
  node's JavaScript unchanged and in n8n's order, and each one answering $('its name') for the
  nodes after it: a gate's rule also checks its lookups' statuses and, for a stop, runs n8n's
  "Exception: Stop the invoice" and "Exception: Queue items" nodes. So a lookup that failed lets
  the other lookup before the same rule run (a read; nothing changes): R7.3's check after a failed
  invoice read, the receipts after a failed PO lookup. The supplier-item map is read with the PO
  and the receipts, so an invoice with no PO or receipt costs one read of the map.
- Step 4 runs one AI call per unmapped line (an iterator), tried three times, and an aggregator
  gathers the replies back for n8n's "Step 4: Collect the AI pairings", which runs inside the
  Table 7.1 step. With no unmapped line the aggregator still answers once, empty, so the route
  goes on without n8n's "Lines left for the AI?" node.
- Step 6's reservation writes and releases keep a failed line in line, as n8n's
  continueRegularOutput does: each write's error route is Make's Resume handler with no data, and
  the rule after the aggregator reads a missing status as the error.
- The webhook's fields are passed one by one and rebuilt as n8n's $('<trigger>').first().json.body,
  because a Make webhook's output cannot be mapped whole.
- Step 8 builds the decision, decision-log and step 9 message bodies in one Code step (n8n writes
  them inline), because Make mappings cannot escape text for JSON; n8n's $now.toISO() is
  new Date().toISOString() there. The rejected invoice's reservations are released by iterating
  over the read's items, which is what n8n's "Step 8: Reservations to release" node returns.
- The ready-invoice scenario takes invoices one at a time (sequential processing), so a second
  invoice for the same goods reads the first one's reservations, as in n8n.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R7.2"
N8N = n8n_build(R)
T, A = N8N.T, N8N.A
RECORD, CHECK = "Step 1: Read the invoice record", "Step 2: Read R7.3's check"
PO, RECEIPTS, MAP = "Step 3: Look up the PO", "Step 3: Look up the receipts", "Step 4: Read the supplier-item map"
RESERVATIONS = "Step 5: Read reservations on this order"
CALL = "Step 4: AI call"
CONFIG = {
    "review_url": "https://<your review list API>",
    "checks_url": "https://<your R7.3 check list API>",
    "ledger_url": "https://<your accounting platform API>",
    "map_url": "https://<your supplier-item map API>",
    "reservations_url": "https://<your reservation list API>",
    "approvals_url": "https://<your approval list API>",
    "queue_url": "https://<your R7.4 queue list API>",
    "messaging_url": "https://<your messaging API>",
    "tolerance_version": "<your Table 7.1 version>",
    "price_tolerance_pct": "<your unit price tolerance, percent>",
    "freight_tolerance": "<your freight tolerance, amount>",
    "tax_rate_pct": "<your tax rate, percent>",
    "tax_rounding": "<your tax rounding, amount>",
    "approval_limit": 10000,
    "approver_to_limit": "<your approver up to the limit>",
    "approver_above": "<your approver above the limit>",
    "approver_own_items": "<who approves the approvers' own items>",
    "purchasing": "<your purchasing map keeper>",
    "workflow_owner": "<your workflow owner>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
READY_FIELDS = ("record_id", "resolved_by")
APPROVAL_FIELDS = ("invoice_id", "decision", "decided_by")
EV = f"$('{T}').first().json.body"
AEV = f"$('{A}').first().json.body"
CFG = "$('Config').first().json"
SUPPLIER_ON_HOLD_JS = "return [{ json: { reason_code: 'supplier on hold', details: $json.detail } }];"  # n8n's "Step 2: Supplier on hold"
WRITE_FAILED_DETAIL = "A result, approval or queue write failed, never retried; check the invoice before it rematches"

# Run n8n Code nodes one after another in one Make Code step (see the docstring).
STEPS = r"""
// Several n8n Code nodes in one step: each runs unchanged, and its result answers $('its name') for the next.
const __run = (node, rule) => { const r = one(rule()); DATA[node] = r.map(j => ({ json: j })); return r; };
const __ok = (node) => { const st = Number(DATA['status: ' + node][0].json); return st >= 200 && st < 300; };
// A lookup that failed after its three tries reaches the stop as n8n's error output: { error: { message } }.
const __lookup = (nodes) => { for (const n of nodes) if (!__ok(n)) return { error: { message: n + ' returned ' + (DATA['status: ' + n][0].json || 'no answer') } }; return null; };
const __stop = (j) => {
  const stop = __run('Exception: Stop the invoice', () => (($input) => {
""" + N8N.STOP_JS.strip() + r"""
  })({ first: () => ({ json: j }), all: () => [{ json: j }] }))[0];
  const queue = __run('Exception: Queue items', () => {
""" + N8N.STOP_ITEMS_JS.strip() + r"""
  });
  return [{ json: Object.assign({}, stop, { route: 'stop', queue_items: queue }) }];
};
"""

# What a stop's closing steps map: n8n's "Exception: Mark the record stopped", "Exception: Decision log"
# and "Exception: Add to the R7.4 queue" bodies.
STOP_BODIES = {
    "stop_body": ("out.route === 'stop' ? JSON.stringify({ match_status: 'stopped', "
                  "match_reasons: out.codes.map(c => c.reason_code + ': ' + c.details) }) : null"),
    "stop_log_body": (f"out.route === 'stop' ? JSON.stringify({{ recipe: '{R}', item: {EV}.record_id, "
                      "decision: 'stopped: ' + out.codes.map(c => c.reason_code).join(', '), "
                      f"rules: Object.assign({{ tolerance_version: {CFG}.tolerance_version }}, out.rules) }}) : null"),
    "queue": "out.route === 'stop' ? out.queue_items.map(i => ({ body: JSON.stringify(i) })) : []",
}


def body_prelude(trigger: str, fields: tuple[str, ...]) -> tuple[str, dict[str, str]]:
    """The webhook's fields rebuilt as n8n's $('<trigger>').first().json.body, and their inputs."""
    body = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in fields)
    prelude = (f"// The webhook's fields, as the rule reads them in n8n: $('{trigger}').first().json.body.\n"
               f"DATA[{json.dumps(trigger)}] = [{{ json: {{ body: {{ {body} }} }} }}];")
    return prelude, {f"t_{f}": "{{1." + f + "}}" for f in fields}


def rule(js: str, sources: dict[str, str], trigger: str = T, fields: tuple[str, ...] = READY_FIELDS,
         prelude: str = "", **kw) -> tuple[str, dict[str, str]]:
    """n8n_rule, plus the webhook's body and the STEPS helpers."""
    ev, ev_inputs = body_prelude(trigger, fields)
    code, inputs = n8n_rule(js, sources, prelude=ev + "\n" + STEPS + prelude, **kw)
    return code, {**ev_inputs, **inputs}


def fn(js: str) -> str:
    return "() => {\n" + js.strip() + "\n}"


class SequentialScenario(Scenario):
    """A scenario whose webhook runs are processed one at a time, in order of arrival."""

    def blueprint(self) -> dict:
        bp = super().blueprint()
        bp["metadata"]["scenario"]["sequential"] = True
        return bp


def resume_empty(s: Scenario) -> dict:
    """Make's Resume handler with no data: a failed write stays in line, its status missing."""
    return {"id": s._id(f"_resume{s._next}"), "module": "builtin:Resume", "version": 1, "parameters": {},
            "mapper": {"data": ""}, "metadata": {"designer": {"x": 0, "y": 0}}}


def ready() -> Scenario:
    s = SequentialScenario(R, "R7.2 Match the invoice to the purchase order and delivery receipt", "webhook",
                           test_key="r7-2-ready")
    s.flow.append(s.webhook(T))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    res = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    status = lambda n: {f"status: {n}": "{{" + f"{s.ref(n)}.statusCode" + "}}"}  # noqa: E731
    s.flow += s.stop_flag()

    def write_failed(step: str) -> list[dict]:
        # A write: never retried; the workflow owner checks the invoice before it rematches.
        return [s.exception(f"{step}: exception queue",
                            '{"recipe": "' + R + '", "item": "{{1.record_id}}", "reason": "write failed", '
                            '"detail": "' + WRITE_FAILED_DETAIL + '", "owner": "' + cfg("workflow_owner") + '"}'),
                s.ignore()]

    def write(name: str, method: str, url: str, body: str) -> dict:
        return s.http(name, method, url, body=body, parse=False, onerror=write_failed(name))

    def read(name: str, url: str, query: dict | None = None) -> dict:
        return s.with_tries(s.http(name, "GET", url, query=query), 3)

    def stop(tag: str, step: str) -> list[dict]:
        """Every stop: the record is marked stopped, logged, and R7.4 gets one item per reason code."""
        each = s.iterator(f"Exception: Queue items ({tag})", res(step, "queue"))
        return [write(f"Exception: Mark the record stopped ({tag})", "PATCH",
                      cfg("review_url") + "/records/{{encodeURL(1.record_id)}}", res(step, "stop_body")),
                s.decision_log(f"Exception: Decision log ({tag})", res(step, "stop_log_body")),
                each,
                write(f"Exception: Add to the R7.4 queue ({tag})", "POST", cfg("queue_url") + "/items",
                      "{{" + f"{each['id']}.body" + "}}")]

    def gate(name: str, route: str, go: str, step: str, tag: str, flow: list[dict]) -> dict:
        return s.router(name, [
            (s.when(f"route is {route}", res(step, "route"), "stop"), stop(tag, step)),
            (s.when(f"route is {go}", res(step, "route"), go), flow),
        ])

    # Steps 1 and 2: the invoice record and R7.3's check; a held supplier stops the invoice.
    rec = read(RECORD, cfg("review_url") + "/records/{{encodeURL(1.record_id)}}")
    rec["filter"] = s.continue_unless_stopped()
    s.flow.append(rec)
    inv = lambda f: "{{" + f"{rec['id']}.data.{f}" + "}}"  # noqa: E731
    s.flow.append(read(CHECK, cfg("checks_url") + "/checks", {"_wrap": "1", "record_id": inv("id")}))
    base = {"Config": "{{" + f"{c}.result" + "}}", RECORD: data(RECORD)}
    held_js = (f"const failed = __lookup([{json.dumps(RECORD)}, {json.dumps(CHECK)}]);\n"
               "if (failed) return __stop(failed);\n"
               f"const h = __run('Step 2: Rule: supplier held?', {fn(N8N.HELD_JS)})[0];\n"
               f"if (h.held) return __stop(__run('Step 2: Supplier on hold', () => (($json) => {{ {SUPPLIER_ON_HOLD_JS} }})(h))[0]);\n"
               "return [{ json: { route: 'go' } }];")
    code, inputs = rule(held_js, {**base, CHECK: data(CHECK), **status(RECORD), **status(CHECK)}, bodies=STOP_BODIES)
    held = s.code("Step 2: Rule: supplier held?", code, inputs)

    # Step 3: the PO and its receipts (and step 4's supplier-item map); with no PO, "no PO".
    po = read(PO, cfg("ledger_url") + "/orders", {"_wrap": "1", "number": "{{ifempty(" + f"{rec['id']}.data.order_number" + '; "(none)")}}'})
    receipts = read(RECEIPTS, cfg("ledger_url") + "/receipts",
                    {"_wrap": "1", "order_number": "{{ifempty(" + f"{rec['id']}.data.order_number" + '; "(none)")}}'})
    smap = read(MAP, cfg("map_url") + "/map", {"_wrap": "1", "supplier_id": inv("supplier_id")})
    found_js = (f"const failed = __lookup([{json.dumps(PO)}, {json.dumps(RECEIPTS)}]);\n"
                "if (failed) return __stop(failed);\n"
                f"const found = __run('Step 3: Rule: PO and receipt found?', {fn(N8N.FOUND_JS)})[0];\n"
                "if (!found.found) return __stop(found);\n"
                f"const failedMap = __lookup([{json.dumps(MAP)}]);\n"
                "if (failedMap) return __stop(failedMap);\n"
                f"const p = __run('Step 4: Rule: pair by the map', {fn(N8N.PAIR_JS)})[0];\n"
                "return [{ json: Object.assign({ route: 'go' }, p) }];")
    po_sources = {PO: data(PO), RECEIPTS: data(RECEIPTS)}
    code, inputs = rule(found_js, {**base, **po_sources, MAP: data(MAP), **status(PO), **status(RECEIPTS), **status(MAP)},
                        bodies={**STOP_BODIES, "unmapped_items": "(out.unmapped || []).map(u => ({ line: JSON.stringify(u) }))"})
    pair = s.code("Steps 3 and 4: Rules: PO and receipt found? pair by the map", code, inputs)
    pair_name = pair["metadata"]["designer"]["name"]

    # Step 4: one AI call for each line the map did not pair, three tries; the replies are gathered back.
    each_line = s.iterator("Step 4: Unmapped lines", res(pair_name, "unmapped_items"))
    vars_js = (f"{{ order_lines: ($('{PO}').first().json.items[0].lines || []).map(l => l.id + ': ' + l.description).join('\\n'), "
               "invoice_line: $json.description }")
    ai = s.ai_step("Step 4", ROOT / "recipes/R7.2/prompts/pair-line.md", vars_js,
                   {"Config": "{{" + f"{c}.result" + "}}", PO: data(PO),
                    "Step 4: Unmapped lines": "{{" + f"{each_line['id']}.line" + "}}"}, max_tokens=100, tries=3)
    call = s.ref(CALL)
    gathered = s.aggregator("Step 4: AI pairings gathered", "Step 4: Unmapped lines", {
        "line": "{{" + f"{each_line['id']}.line" + "}}", "status": "{{" + f"{call}.statusCode" + "}}",
        "reply": "{{" + f"{call}.data" + "}}"})
    resv = read(RESERVATIONS, cfg("reservations_url") + "/reservations",
                {"_wrap": "1", "order_number": "{{" + f"{po['id']}.data.items[1].number" + "}}"})

    # Step 5: Table 7.1; the rules decide, not the AI. A pass names the lines step 6 reserves.
    gathered_prelude = (
        "\n// The aggregator's bundles, as n8n's per-line items: the unmapped lines and the AI call's replies\n"
        "// (a call that failed its three tries is n8n's error item).\n"
        "const __g = DATA['Step 4: AI pairings gathered'].map(i => i.json);\n"
        "DATA['Step 4: Unmapped lines'] = __g.map(g => ({ json: JSON.parse(g.line) }));\n"
        f"DATA[{json.dumps(CALL)}] = __g.map(g => ({{ json: Number(g.status) === 200 ? g.reply : "
        "{ error: { message: 'AI call returned ' + (g.status || 'no answer') } } }));\n")
    table_js = (f"const failed = __lookup([{json.dumps(RESERVATIONS)}]);\n"
                "if (failed) return __stop(failed);\n"
                f"if (DATA['Step 4: Unmapped lines'].length) __run('Step 4: Collect the AI pairings', {fn(N8N.COLLECT_JS)});\n"
                f"const t = __run('Step 5: Rule: Table 7.1', {fn(N8N.TABLE_JS)})[0];\n"
                "if (t.route !== 'pass') return __stop(t);\n"
                f"const lines = __run('Step 6: Lines to reserve', {fn(N8N.RESERVE_JS)});\n"
                "return [{ json: Object.assign({}, t, { reserve: lines }) }];")
    table_sources = {**base, **po_sources, "Step 4: Rule: pair by the map": "{{" + f"{pair['id']}.result" + "}}",
                     "Step 4: AI pairings gathered": "{{" + f"{gathered['id']}.array" + "}}",
                     RESERVATIONS: data(RESERVATIONS), **status(RESERVATIONS)}
    code, inputs = rule(table_js, table_sources, items=("Step 4: AI pairings gathered",), prelude=gathered_prelude, bodies={
        **STOP_BODIES, "reserve_items": "(out.reserve || []).map(r => ({ id: r.id, body: JSON.stringify(r.body) }))"})
    table = s.code("Step 5: Rule: Table 7.1", code, inputs)

    # Step 6: reserve each line's quantity once; a failed line stays in line so the others can be released.
    each_res = s.iterator("Step 6: Lines to reserve", res("Step 5: Rule: Table 7.1", "reserve_items"))
    put = s.http("Step 6: Reserve line quantity", "PUT", cfg("reservations_url") + "/reservations/{{" + f"{each_res['id']}.id" + "}}",
                 body="{{" + f"{each_res['id']}.body" + "}}", parse=False, onerror=[resume_empty(s)])
    reserved = s.aggregator("Step 6: Reservations written", "Step 6: Lines to reserve", {
        "id": "{{" + f"{each_res['id']}.id" + "}}", "status": "{{" + f"{put['id']}.statusCode" + "}}"})
    ok_prelude = (
        "\n// Each write's status, as n8n's per-line results: a failed write is an error item.\n"
        "const __written = (node) => { DATA[node] = DATA[node].map(i => ({ json: (Number(i.json.status) >= 200 && "
        "Number(i.json.status) < 300) ? {} : { error: { message: 'write returned ' + (i.json.status || 'an error') } } })); };\n")
    reserved_js = (f"const r = __run('Step 6: Rule: every line reserved?', {fn(N8N.RESERVED_JS)})[0];\n"
                   "if (!r.all_reserved) {\n"
                   f"  const release = r.to_release ? __run('Step 6: Reserved lines to release', {fn(N8N.RELEASE_ITEMS_JS)}) : [];\n"
                   "  return [{ json: Object.assign({ route: 'failed', release }, r) }];\n"
                   "}\n"
                   f"const a = __run('Step 7: Rule: choose the approver', {fn(N8N.APPROVER_JS)})[0];\n"
                   "return [{ json: Object.assign({ route: 'approve' }, r, a) }];")
    t_out = "{{" + f"{table['id']}.result" + "}}"
    code, inputs = rule(reserved_js, {**base, PO: data(PO), "Step 5: Rule: Table 7.1": t_out,
                                      "Step 6: Lines to reserve": "{{" + f"{table['id']}.result.reserve" + "}}",
                                      "Step 6: Reserve line quantity": "{{" + f"{reserved['id']}.array" + "}}"},
                        items=("Step 6: Lines to reserve", "Step 6: Reserve line quantity"),
                        input_node="Step 6: Reserve line quantity",
                        prelude=ok_prelude + "__written('Step 6: Reserve line quantity');\n", bodies={
        "approval_body": "out.approval ? JSON.stringify(out.approval) : null",
        "matched_body": "out.approval ? JSON.stringify({ match_status: 'matched; to approval', approver: out.approver }) : null",
        "log_body": (f"out.approval ? JSON.stringify({{ recipe: '{R}', item: $('{RECORD}').first().json.id, "
                     "decision: 'matched; to ' + out.approver, rules: out.rules }) : null"),
    })
    every = s.code("Step 6: Rule: every line reserved?", code, inputs)
    ev_ = lambda f: res("Step 6: Rule: every line reserved?", f)  # noqa: E731
    each_rel = s.iterator("Step 6: Reserved lines to release", ev_("release"))
    delete = s.http("Step 6: Release reserved line", "DELETE", cfg("reservations_url") + "/reservations/{{" + f"{each_rel['id']}.id" + "}}",
                    parse=False, onerror=[resume_empty(s)])
    released = s.aggregator("Step 6: Releases written", "Step 6: Reserved lines to release", {
        "id": "{{" + f"{each_rel['id']}.id" + "}}", "status": "{{" + f"{delete['id']}.statusCode" + "}}"})
    failed_js = f"return __stop(__run('Step 6: Reservation failed', {fn(N8N.RES_FAILED_JS)})[0]);"
    code, inputs = rule(failed_js, {**base, "Step 6: Rule: every line reserved?": "{{" + f"{every['id']}.result" + "}}",
                                    "Step 6: Reserved lines to release": ev_("release"),
                                    "Step 6: Release reserved line": "{{" + f"{released['id']}.array" + "}}"},
                        items=("Step 6: Reserved lines to release", "Step 6: Release reserved line"),
                        prelude=(ok_prelude + "__written('Step 6: Release reserved line');\n"
                                 "// n8n runs the release only when a line was reserved.\n"
                                 "if (!DATA['Step 6: Reserved lines to release'].length) { delete DATA['Step 6: Reserved lines to release']; "
                                 "delete DATA['Step 6: Release reserved line']; }\n"),
                        bodies=STOP_BODIES)
    res_failed = s.code("Step 6: Reservation failed", code, inputs)

    # Step 7: the approval goes to the approver, AI-paired lines marked.
    rec_url = cfg("review_url") + "/records/{{encodeURL(" + f"{rec['id']}.data.id" + ")}}"
    approve = [
        write("Step 7: Send the approval", "PUT", cfg("approvals_url") + "/approvals/{{encodeURL(" + f"{rec['id']}.data.id" + ")}}",
              ev_("approval_body")),
        write("Step 7: Mark the record matched", "PATCH", rec_url, ev_("matched_body")),
        s.decision_log("Step 7: Decision log", ev_("log_body")),
    ]
    all_reserved = s.router("All reserved?", [
        (s.when("route is approve", ev_("route"), "approve"), approve),
        (s.when("route is failed", ev_("route"), "failed"),
         [each_rel, delete, released, res_failed] + stop("reservation failed", "Step 6: Reservation failed")),
    ])
    within = gate("Within Table 7.1?", "stop", "pass", "Step 5: Rule: Table 7.1", "Table 7.1",
                  [each_res, put, reserved, every, all_reserved])
    found = gate("Found?", "stop", "go", pair_name, "no PO, receipt or map",
                 [each_line] + ai + [gathered, resv, table, within])
    s.flow += [held, gate("Held?", "stop", "go", "Step 2: Rule: supplier held?", "held or check",
                          [po, receipts, smap, pair, found])]
    return s


def approval() -> Scenario:
    s = Scenario(R, "R7.2 Approval decided: record it and release a rejected invoice's reservations", "webhook",
                 test_key="r7-2-approval")
    s.flow.append(s.webhook(A))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    url = cfg("approvals_url") + "/approvals/{{encodeURL(1.invoice_id)}}"

    def write_failed(step: str) -> list[dict]:
        return [s.exception(f"{step}: exception queue",
                            '{"recipe": "' + R + '", "item": "{{1.invoice_id}}", "reason": "write failed", '
                            '"detail": "' + WRITE_FAILED_DETAIL + '", "owner": "' + cfg("workflow_owner") + '"}'),
                s.ignore()]

    # Step 8: read the approval (a read: retried), record the decision and log who decided.
    read = s.http("Step 8: Read the approval", "GET", url)
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    ap = "$('Step 8: Read the approval').first().json"
    js = ("// The step 8 and 9 bodies, as the n8n build writes them inline.\n"
          f"const ap = {ap};\n"
          f"return [{{ json: {{ ai_paired: (ap.lines || []).some(l => l.ai_paired) ? 'yes' : 'no' }} }}];")
    code, inputs = n8n_rule(js, {"Config": "{{" + f"{c}.result" + "}}", "Step 8: Read the approval": "{{" + f"{read['id']}.data" + "}}"},
                            prelude=body_prelude(A, APPROVAL_FIELDS)[0], bodies={
        "decision_body": f"JSON.stringify({{ status: {AEV}.decision, decided_by: {AEV}.decided_by, decided_at: new Date().toISOString() }})",
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {AEV}.invoice_id, decision: 'approval ' + {AEV}.decision, "
                     f"rules: {{ approver: {ap}.approver, tolerance_version: {ap}.tolerance_version }}, approved_by: {AEV}.decided_by }})"),
        "message_body": (f"JSON.stringify({{ to: {CFG}.purchasing, subject: 'Confirm AI pairings for invoice ' + {AEV}.invoice_id, "
                         "text: 'Approved with AI-paired lines; add the ones you confirm to the supplier-item map: ' + "
                         f"({ap}.lines || []).filter(l => l.ai_paired).map(l => l.description + ' -> ' + l.order_line_id).join('; ') }})"),
    })
    code_inputs = {**body_prelude(A, APPROVAL_FIELDS)[1], **inputs}
    s.flow.append(s.code("Step 8: Rule: the decision's bodies", code, code_inputs))
    b = s.ref("Step 8: Rule: the decision's bodies")
    out = lambda f: "{{" + f"{b}.result.{f}" + "}}"  # noqa: E731
    s.flow.append(s.http("Step 8: Record the decision", "PATCH", url, body=out("decision_body"), parse=False,
                         onerror=write_failed("Step 8: Record the decision")))
    s.flow.append(s.decision_log("Step 8: Log the approval", out("log_body")))

    # A rejection releases this invoice's reservations; an approval with AI-paired lines goes to purchasing (step 9).
    reservations = s.http("Step 8: Read this invoice's reservations", "GET", cfg("reservations_url") + "/reservations",
                          query={"_wrap": "1", "invoice_id": "{{1.invoice_id}}"})
    each = s.iterator("Step 8: Reservations to release", "{{" + f"{reservations['id']}.data.items" + "}}")
    release = s.http("Step 8: Release reservation", "DELETE", cfg("reservations_url") + "/reservations/{{" + f"{each['id']}.id" + "}}",
                     parse=False, onerror=write_failed("Step 8: Release reservation"))
    ask = s.http("Step 9: Ask purchasing to add the AI pairings", "POST", cfg("messaging_url") + "/messages",
                 body=out("message_body"), parse=False, onerror=write_failed("Step 9: Ask purchasing to add the AI pairings"))
    s.flow.append(s.router("Rejected?", [
        (s.when("rejected", "{{1.decision}}", "rejected"), [reservations, each, release]),
        ({"name": "approved, AI-paired lines", "conditions": [[
            {"a": "{{1.decision}}", "b": "rejected", "o": "text:notequal"},
            {"a": out("ai_paired"), "b": "yes", "o": "text:equal"}]]}, [ask]),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R7.2/make/, scenario)."""
    return [("blueprint.json", ready()), ("approval.blueprint.json", approval())]
