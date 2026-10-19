"""R7.2 Match the invoice to the purchase order and delivery receipt.

Source: book Chapter 7, recipe R7.2, build steps 1 to 9 and Table 7.1 (recipes/R7.2/build-spec.md);
AI step: recipes/R7.2/prompts/pair-line.md. The AI only proposes a pairing; the rules apply
Table 7.1 and a person approves. It never pays or changes an order.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

T = "Step 1: Ready invoice"
A = "Step 8: Approval decided"
EV = f"$('{T}').item.json.body"
AEV = f"$('{A}').item.json.body"
INV = "$('Step 1: Read the invoice record').first().json"
CFG = "$('Config').item.json"

HELD_JS = r"""
// Step 2: R7.3's check for this invoice must be logged and show the supplier not held.
const checks = $('Step 2: Read R7.3\'s check').first().json.items || [];
if (!checks.length) return [{ json: { held: true, detail: 'no R7.3 check logged for this invoice' } }];
const held = checks.some(c => c.hold);
return [{ json: { held, detail: held ? 'supplier held by R7.3 for a bank-detail difference' : 'check logged; supplier not held' } }];
"""

FOUND_JS = r"""
// Step 3: the PO and at least one receipt must both be found.
const orders = $('Step 3: Look up the PO').first().json.items || [];
const receipts = $('Step 3: Look up the receipts').first().json.items || [];
if (!orders.length) return [{ json: { found: false, reason_code: 'no PO', details: 'no PO found for order number ' + ($('Step 1: Read the invoice record').first().json.order_number || '(none)') } }];
if (!receipts.length) return [{ json: { found: false, reason_code: 'no receipt', details: 'no delivery receipt for order ' + orders[0].number } }];
return [{ json: { found: true } }];
"""

PAIR_JS = r"""
// Step 4: pair each invoice line by the supplier-item map; lines the map does not cover go to the AI.
const inv = $('Step 1: Read the invoice record').first().json;
const order = $('Step 3: Look up the PO').first().json.items[0];
const map = $('Step 4: Read the supplier-item map').first().json.items || [];
const norm = s => String(s || '').toLowerCase().replace(/\s+/g, ' ').trim();
const pairs = [], unmapped = [];
(inv.lines || []).forEach((line, i) => {
  const m = map.find(e => norm(e.invoice_text) === norm(line.description));
  if (!m) { unmapped.push({ index: i, description: line.description }); return; }
  const ol = (order.lines || []).find(l => l.item === m.item);
  pairs.push({ index: i, order_line_id: ol ? ol.id : null, paired_by: 'map', problem: ol ? null : `map item ${m.item} is not on this order` });
});
return [{ json: { pairs, unmapped, need_ai: unmapped.length > 0 } }];
"""

UNMAPPED_JS = r"""
// Step 4: one AI call for each line the map did not pair.
return $('Step 4: Rule: pair by the map').first().json.unmapped.map(u => ({ json: u }));
"""

COLLECT_JS = AI_PARSE_JS + r"""
// Step 4: collect the AI's proposals; 'none', a malformed reply or an AI error leaves the line unpaired.
const base = $('Step 4: Rule: pair by the map').first().json;
const unmapped = $('Step 4: Unmapped lines').all().map(i => i.json);
const replies = $('Step 4: AI call').all().map(i => i.json);
const pairs = base.pairs.slice();
unmapped.forEach((u, k) => {
  const r = replies[k] || {};
  if (r.error) { pairs.push({ index: u.index, order_line_id: null, paired_by: 'AI', problem: 'AI error, no pairing proposed' }); return; }
  const p = parseAi(r, ['order_line_id']);
  if (!p.ok || typeof p.value.order_line_id !== 'string') { pairs.push({ index: u.index, order_line_id: null, paired_by: 'AI', problem: 'AI output failed the check' }); return; }
  pairs.push({ index: u.index, order_line_id: p.value.order_line_id, paired_by: 'AI', problem: null });
});
return [{ json: { pairs } }];
"""

TABLE_JS = r"""
// Step 5: confirm each pairing is on this order and apply Table 7.1; every failed line is named.
const cfg = $('Config').first().json;
const inv = $('Step 1: Read the invoice record').first().json;
const order = $('Step 3: Look up the PO').first().json.items[0];
const receipts = $('Step 3: Look up the receipts').first().json.items || [];
const reservations = ($('Step 5: Read reservations on this order').first().json.items || []).filter(r => r.invoice_id !== inv.id);
const src = $('Step 4: Collect the AI pairings').isExecuted ? $('Step 4: Collect the AI pairings') : $('Step 4: Rule: pair by the map');
const pairs = src.first().json.pairs.slice().sort((a, b) => a.index - b.index);
const lines = inv.lines || [];
const failures = [];
const fail = (code, text) => failures.push({ reason_code: code, text });
const name = i => `line ${i + 1} "${lines[i].description}"`;
const byId = Object.fromEntries((order.lines || []).map(l => [l.id, l]));

// Line pairing: every goods line pairs to a line on this order.
for (const p of pairs) {
  if (p.problem) fail('pairing rejected', `${name(p.index)}: ${p.problem}`);
  else if (p.order_line_id === 'none' || !byId[p.order_line_id]) fail('pairing rejected', `${name(p.index)}: pairs to ${p.order_line_id}, not a line on order ${order.number}`);
}
const good = pairs.filter(p => !p.problem && byId[p.order_line_id]);

// Quantity: within received, less other invoices' reservations.
const billed = {};
for (const p of good) billed[p.order_line_id] = (billed[p.order_line_id] || 0) + Number(lines[p.index].qty);
for (const [id, qty] of Object.entries(billed)) {
  const received = receipts.reduce((s, r) => s + (r.lines || []).filter(l => l.order_line_id === id).reduce((t, l) => t + Number(l.qty), 0), 0);
  const reserved = reservations.filter(r => r.order_line_id === id).reduce((s, r) => s + Number(r.qty), 0);
  const who = good.filter(p => p.order_line_id === id).map(p => name(p.index)).join(', ');
  if (qty > received) fail('outside tolerance', `${who}: over receipt, ${qty} billed, ${received} received`);
  else if (qty > received - reserved) fail('already invoiced', `${who}: ${qty} billed, ${received} received, ${reserved} already invoiced`);
}

// Unit price: within the price tolerance of the order price.
for (const p of good) {
  const limit = Number(byId[p.order_line_id].unit_price) * (1 + Number(cfg.price_tolerance_pct) / 100);
  if (!(Number(lines[p.index].unit_price) <= limit + 1e-9)) fail('outside tolerance', `${name(p.index)}: unit price ${lines[p.index].unit_price} above tolerance of order price ${byId[p.order_line_id].unit_price}`);
}

// Freight: on the order, or within the freight tolerance.
const freight = Number(inv.freight || 0);
const onOrder = order.freight !== undefined && order.freight !== null && freight <= Number(order.freight);
if (freight > 0 && !onOrder && !(freight <= Number(cfg.freight_tolerance))) fail('outside tolerance', `freight ${freight} not on the order and above the freight tolerance`);

// Tax: within rounding of tax on the lines.
const goods = lines.reduce((s, l) => s + Number(l.amount !== undefined ? l.amount : l.qty * l.unit_price), 0);
const expected = Math.round(goods * Number(cfg.tax_rate_pct)) / 100;
if (!(Math.abs(Number(inv.tax || 0) - expected) <= Number(cfg.tax_rounding))) fail('outside tolerance', `tax ${inv.tax} differs from ${expected} on the lines`);

const rules = { tolerance_version: cfg.tolerance_version, lines: lines.length, ai_paired: good.filter(p => p.paired_by === 'AI').length,
  failures: failures.map(f => f.reason_code) };
if (failures.length) {
  const codes = [...new Set(failures.map(f => f.reason_code))];
  return [{ json: { route: 'stop', codes: codes.map(c => ({ reason_code: c, details: failures.filter(f => f.reason_code === c).map(f => f.text).join('; ') })), rules } }];
}
return [{ json: { route: 'pass', pairs: good.map(p => ({ invoice_line: p.index + 1, description: lines[p.index].description, order_line_id: p.order_line_id,
  qty: Number(lines[p.index].qty), ai_paired: p.paired_by === 'AI' })), rules } }];
"""

RESERVE_JS = r"""
// Step 6: one reservation per paired order line, keyed by invoice and order line so it is made once.
const inv = $('Step 1: Read the invoice record').first().json;
const order = $('Step 3: Look up the PO').first().json.items[0];
const qty = {};
for (const p of $('Step 5: Rule: Table 7.1').first().json.pairs) qty[p.order_line_id] = (qty[p.order_line_id] || 0) + p.qty;
return Object.entries(qty).map(([id, q]) => ({ json: { id: `${inv.id}:${id}`,
  body: { invoice_id: inv.id, order_number: order.number, order_line_id: id, qty: q } } }));
"""

RESERVED_JS = r"""
// Step 6: did every reservation write succeed? If not, the ones that did are released.
const sent = $('Step 6: Lines to reserve').all().map(i => i.json);
const results = $input.all().map(i => i.json);
const failed = sent.filter((s, k) => results[k] && results[k].error).map(s => s.id);
const reserved = sent.filter((s, k) => !(results[k] && results[k].error)).map(s => s.id);
return [{ json: { all_reserved: failed.length === 0, failed, reserved, to_release: reserved.length > 0 } }];
"""

RELEASE_ITEMS_JS = r"""
return $('Step 6: Rule: every line reserved?').first().json.reserved.map(id => ({ json: { id } }));
"""

RES_FAILED_JS = r"""
// Step 6: raise "reservation failed"; any line that could not be released is marked for the workflow owner.
const r = $('Step 6: Rule: every line reserved?').first().json;
let marked = [];
if ($('Step 6: Release reserved line').isExecuted) {
  const tried = $('Step 6: Reserved lines to release').all().map(i => i.json.id);
  const out = $('Step 6: Release reserved line').all().map(i => i.json);
  marked = tried.filter((id, k) => out[k] && out[k].error);
}
const details = `reservation write failed for ${r.failed.join(', ')}; released ${r.reserved.filter(id => !marked.includes(id)).join(', ') || 'none'}`
  + (marked.length ? `; still reserved, marked for the workflow owner: ${marked.join(', ')}` : '');
return [{ json: { codes: [{ reason_code: 'reservation failed', details }], rules: { reservation: 'failed', failed: r.failed, marked } } }];
"""

APPROVER_JS = r"""
// Step 7: the approver by amount; nobody approves what they requested or resolved.
const cfg = $('Config').first().json;
const inv = $('Step 1: Read the invoice record').first().json;
const order = $('Step 3: Look up the PO').first().json.items[0];
const resolvedBy = $('Step 1: Ready invoice').first().json.body.resolved_by || inv.resolved_by || null;
let approver = Number(inv.total) <= Number(cfg.approval_limit) ? cfg.approver_to_limit : cfg.approver_above;
let rule = Number(inv.total) <= Number(cfg.approval_limit) ? 'up to the limit' : 'above the limit';
const own = [order.raised_by, resolvedBy].filter(Boolean);
if (own.includes(approver)) { approver = cfg.approver_own_items; rule += '; approver raised the order or resolved the item'; }
const t = $('Step 5: Rule: Table 7.1').first().json;
return [{ json: { approver, approval: { invoice_id: inv.id, approver, total: inv.total, status: 'waiting',
  tolerance_version: cfg.tolerance_version, lines: t.pairs }, rules: Object.assign({}, t.rules, { approver: rule }) } }];
"""

STOP_ITEMS_JS = r"""
// One R7.4 queue item for each reason code, naming the failed lines.
let inv;
try { inv = $('Step 1: Read the invoice record').first().json; } catch (e) { inv = null; }
if (!inv || !inv.id) inv = { id: $('Step 1: Ready invoice').first().json.body.record_id };
return $('Exception: Stop the invoice').first().json.codes.map(c => ({ json: { invoice_id: inv.id, supplier: inv.supplier || null,
  supplier_id: inv.supplier_id || null, reason_code: c.reason_code, details: c.details, raised_by: 'R7.2',
  raised_at: new Date().toISOString().slice(0, 10), status: 'open' } }));
"""

STOP_JS = r"""
// Every stop meets here with { codes: [{ reason_code, details }], rules }.
const j = $input.first().json;
if (j.codes) return [{ json: j }];
if (j.reason_code) return [{ json: { codes: [{ reason_code: j.reason_code, details: j.details }], rules: { stop: j.reason_code } } }];
return [{ json: { codes: [{ reason_code: 'lookup error', details: 'a lookup failed after three tries: ' + String((j.error && j.error.message) || '').slice(0, 200) }], rules: { stop: 'lookup error' } } }];
"""

REJECT_JS = r"""
// Step 8: a rejection releases this invoice's reservations.
return ($('Step 8: Read this invoice\'s reservations').first().json.items || []).map(r => ({ json: { id: r.id } }));
"""


def build() -> Workflow:
    w = Workflow("R7.2", "R7.2 Match the invoice to the purchase order and delivery receipt")
    w.webhook(T, "r7-2-ready", "R7.1 calls this when it saves a record as \"ready\", and R7.4 when a corrected item rematches. Body: {record_id, resolved_by}.", pos=[0, 0])
    w.webhook(A, "r7-2-approval", "Your approval list calls this when the approver decides. Body: {invoice_id, decision: approved | rejected, decided_by}.", pos=[0, 900])
    w.config("Config", {
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
    }, pos=[260, 450])
    w.connect(T, "Config")
    w.connect(A, "Config")
    w.if_("Approval decision?", f"={{{{ $('{A}').isExecuted }}}}", pos=[520, 450])
    w.connect("Config", "Approval decision?")

    # ---- steps 1 to 3 -----------------------------------------------------------
    w.http("Step 1: Read the invoice record", "GET", f"={{{{ {CFG}.review_url }}}}/records/{{{{ {EV}.record_id }}}}",
           write=False, pos=[780, 0])
    w.connect("Approval decision?", "Step 1: Read the invoice record", output=1)
    w.http("Step 2: Read R7.3's check", "GET", f"={{{{ {CFG}.checks_url }}}}/checks",
           query={"_wrap": "1", "record_id": f"={{{{ {INV}.id }}}}"}, write=False, pos=[1040, 0],
           notes="An unreadable list holds the invoice (lookup error).")
    w.code("Step 2: Rule: supplier held?", HELD_JS, mode="runOnceForAllItems", pos=[1300, 0])
    w.if_("Held?", "={{ $json.held }}", pos=[1560, 0])
    w.code("Step 2: Supplier on hold", "return [{ json: { reason_code: 'supplier on hold', details: $json.detail } }];",
           mode="runOnceForAllItems", pos=[1820, -300])
    w.chain("Step 1: Read the invoice record", "Step 2: Read R7.3's check", "Step 2: Rule: supplier held?", "Held?")
    w.connect("Held?", "Step 2: Supplier on hold", output=0)

    w.http("Step 3: Look up the PO", "GET", f"={{{{ {CFG}.ledger_url }}}}/orders",
           query={"_wrap": "1", "number": f"={{{{ {INV}.order_number || '(none)' }}}}"}, write=False, pos=[1820, 0])
    w.http("Step 3: Look up the receipts", "GET", f"={{{{ {CFG}.ledger_url }}}}/receipts",
           query={"_wrap": "1", "order_number": f"={{{{ {INV}.order_number || '(none)' }}}}"}, write=False, pos=[2080, 0])
    w.code("Step 3: Rule: PO and receipt found?", FOUND_JS, mode="runOnceForAllItems", pos=[2340, 0])
    w.if_("Found?", "={{ $json.found }}", pos=[2600, 0])
    w.connect("Held?", "Step 3: Look up the PO", output=1)
    w.chain("Step 3: Look up the PO", "Step 3: Look up the receipts", "Step 3: Rule: PO and receipt found?", "Found?")

    # ---- step 4: pairing ---------------------------------------------------------
    w.http("Step 4: Read the supplier-item map", "GET", f"={{{{ {CFG}.map_url }}}}/map",
           query={"_wrap": "1", "supplier_id": f"={{{{ {INV}.supplier_id }}}}"}, write=False, pos=[2860, 0])
    w.code("Step 4: Rule: pair by the map", PAIR_JS, mode="runOnceForAllItems", pos=[3120, 0])
    w.if_("Lines left for the AI?", "={{ $json.need_ai }}", pos=[3380, 0])
    w.connect("Found?", "Step 4: Read the supplier-item map", output=0)
    w.chain("Step 4: Read the supplier-item map", "Step 4: Rule: pair by the map", "Lines left for the AI?")
    w.code("Step 4: Unmapped lines", UNMAPPED_JS, mode="runOnceForAllItems", pos=[3640, 200])
    order = "$('Step 3: Look up the PO').first().json.items[0]"
    vars_js = (f"{{ order_lines: ({order}.lines || []).map(l => l.id + ': ' + l.description).join('\\n'), "
               "invoice_line: $json.description }")
    build_, call = ai_step(w, "Step 4", ROOT / "recipes/R7.2/prompts/pair-line.md", vars_js,
                           max_tokens=100, tries=3, pos_build=[3900, 200], pos_call=[4160, 200])
    # One call per unmapped line: errors stay in line with their line so the collector can name it.
    next(n for n in w.nodes if n["name"] == call)["onError"] = "continueRegularOutput"
    w.code("Step 4: Collect the AI pairings", COLLECT_JS, mode="runOnceForAllItems", pos=[4420, 200],
           notes="An AI error or 'none' leaves the line unpaired, which Table 7.1 stops.")
    w.connect("Lines left for the AI?", "Step 4: Unmapped lines", output=0)
    w.connect("Step 4: Unmapped lines", build_)
    w.connect(call, "Step 4: Collect the AI pairings")

    # ---- step 5: Table 7.1 -----------------------------------------------------
    w.http("Step 5: Read reservations on this order", "GET", f"={{{{ {CFG}.reservations_url }}}}/reservations",
           query={"_wrap": "1", "order_number": f"={{{{ {order}.number }}}}"}, write=False, pos=[4680, 0])
    w.code("Step 5: Rule: Table 7.1", TABLE_JS, mode="runOnceForAllItems", pos=[4940, 0], notes="The rules decide, not the AI.")
    w.if_("Within Table 7.1?", "={{ $json.route }}", op="equals", right="pass", pos=[5200, 0])
    w.connect("Lines left for the AI?", "Step 5: Read reservations on this order", output=1)
    w.connect("Step 4: Collect the AI pairings", "Step 5: Read reservations on this order")
    w.chain("Step 5: Read reservations on this order", "Step 5: Rule: Table 7.1", "Within Table 7.1?")

    # ---- step 6: reservations -------------------------------------------------------
    w.code("Step 6: Lines to reserve", RESERVE_JS, mode="runOnceForAllItems", pos=[5460, -200])
    w.http("Step 6: Reserve line quantity", "PUT", f"={{{{ {CFG}.reservations_url }}}}/reservations/{{{{ $json.id }}}}",
           body="={{ JSON.stringify($json.body) }}", write=True, pos=[5720, -200],
           notes="A write, never retried; a failed line stays in line so the rule can release the others.")
    next(n for n in w.nodes if n["name"] == "Step 6: Reserve line quantity")["onError"] = "continueRegularOutput"
    w.code("Step 6: Rule: every line reserved?", RESERVED_JS, mode="runOnceForAllItems", pos=[5980, -200])
    w.if_("All reserved?", "={{ $json.all_reserved }}", pos=[6240, -200])
    w.if_("Any to release?", "={{ $json.to_release }}", pos=[6500, 100])
    w.code("Step 6: Reserved lines to release", RELEASE_ITEMS_JS, mode="runOnceForAllItems", pos=[6760, 100])
    w.http("Step 6: Release reserved line", "DELETE", f"={{{{ {CFG}.reservations_url }}}}/reservations/{{{{ $json.id }}}}",
           write=True, pos=[7020, 100])
    next(n for n in w.nodes if n["name"] == "Step 6: Release reserved line")["onError"] = "continueRegularOutput"
    w.code("Step 6: Reservation failed", RES_FAILED_JS, mode="runOnceForAllItems", pos=[7280, 260])
    w.connect("Within Table 7.1?", "Step 6: Lines to reserve", output=0)
    w.chain("Step 6: Lines to reserve", "Step 6: Reserve line quantity", "Step 6: Rule: every line reserved?", "All reserved?")
    w.connect("All reserved?", "Any to release?", output=1)
    w.connect("Any to release?", "Step 6: Reserved lines to release", output=0)
    w.connect("Any to release?", "Step 6: Reservation failed", output=1)
    w.chain("Step 6: Reserved lines to release", "Step 6: Release reserved line", "Step 6: Reservation failed")

    # ---- step 7: approval ---------------------------------------------------------
    w.code("Step 7: Rule: choose the approver", APPROVER_JS, mode="runOnceForAllItems", pos=[6500, -400])
    w.http("Step 7: Send the approval", "PUT", f"={{{{ {CFG}.approvals_url }}}}/approvals/{{{{ {INV}.id }}}}",
           body="={{ JSON.stringify($json.approval) }}", write=True, pos=[6760, -400],
           notes="AI-paired lines are marked; the approver decides.")
    w.http("Step 7: Mark the record matched", "PATCH", f"={{{{ {CFG}.review_url }}}}/records/{{{{ {INV}.id }}}}",
           body="={{ JSON.stringify({ match_status: 'matched; to approval', approver: $('Step 7: Rule: choose the approver').first().json.approver }) }}",
           write=True, pos=[7020, -400])
    w.decision_log("Step 7: Decision log", f"{INV}.id",
                   "'matched; to ' + $('Step 7: Rule: choose the approver').first().json.approver",
                   "JSON.stringify($('Step 7: Rule: choose the approver').first().json.rules)", pos=[7280, -400])
    w.connect("All reserved?", "Step 7: Rule: choose the approver", output=0)
    w.chain("Step 7: Rule: choose the approver", "Step 7: Send the approval", "Step 7: Mark the record matched", "Step 7: Decision log")

    # ---- every stop: the record is marked and R7.4 gets the reason -------------------
    lookups = ["Step 1: Read the invoice record", "Step 2: Read R7.3's check", "Step 3: Look up the PO", "Step 3: Look up the receipts",
               "Step 4: Read the supplier-item map", "Step 5: Read reservations on this order"]
    w.code("Exception: Stop the invoice", STOP_JS, mode="runOnceForAllItems", pos=[5460, 500],
           notes="Held, no PO or receipt, a lookup error, a Table 7.1 failure or a failed reservation.")
    for n in lookups:
        w.connect(n, "Exception: Stop the invoice", output=1)
    w.connect("Step 2: Supplier on hold", "Exception: Stop the invoice")
    w.connect("Found?", "Exception: Stop the invoice", output=1)
    w.connect("Within Table 7.1?", "Exception: Stop the invoice", output=1)
    w.connect("Step 6: Reservation failed", "Exception: Stop the invoice")
    w.http("Exception: Mark the record stopped", "PATCH", f"={{{{ {CFG}.review_url }}}}/records/{{{{ {EV}.record_id }}}}",
           body="={{ JSON.stringify({ match_status: 'stopped', match_reasons: $json.codes.map(c => c.reason_code + ': ' + c.details) }) }}",
           write=True, pos=[5720, 500])
    w.decision_log("Exception: Decision log", f"{EV}.record_id",
                   "'stopped: ' + $('Exception: Stop the invoice').first().json.codes.map(c => c.reason_code).join(', ')",
                   f"JSON.stringify(Object.assign({{ tolerance_version: {CFG}.tolerance_version }}, $('Exception: Stop the invoice').first().json.rules))",
                   pos=[5980, 500])
    w.code("Exception: Queue items", STOP_ITEMS_JS, mode="runOnceForAllItems", pos=[6240, 500])
    w.http("Exception: Add to the R7.4 queue", "POST", f"={{{{ {CFG}.queue_url }}}}/items",
           body="={{ JSON.stringify($json) }}", write=True, pos=[6500, 500], notes="R7.4 assigns the owner and the clock.")
    w.chain("Exception: Stop the invoice", "Exception: Mark the record stopped", "Exception: Decision log",
            "Exception: Queue items", "Exception: Add to the R7.4 queue")

    w.exception("Exception queue: write failed", f"($('{T}').isExecuted ? {EV}.record_id : {AEV}.invoice_id)", "write failed",
                "'A result, approval or queue write failed, never retried; check the invoice before it rematches'",
                f"{CFG}.workflow_owner", pos=[7540, 700])
    for n in ["Step 7: Send the approval", "Step 7: Mark the record matched", "Exception: Mark the record stopped", "Exception: Add to the R7.4 queue"]:
        w.connect(n, "Exception queue: write failed", output=1)

    # ---- steps 8 and 9: the approver's decision -------------------------------------------
    w.http("Step 8: Read the approval", "GET", f"={{{{ {CFG}.approvals_url }}}}/approvals/{{{{ {AEV}.invoice_id }}}}",
           write=False, error_output=False, pos=[780, 900])
    w.http("Step 8: Record the decision", "PATCH", f"={{{{ {CFG}.approvals_url }}}}/approvals/{{{{ {AEV}.invoice_id }}}}",
           body=f"={{{{ JSON.stringify({{ status: {AEV}.decision, decided_by: {AEV}.decided_by, decided_at: $now.toISO() }}) }}}}",
           write=True, pos=[1040, 900])
    w.pg("Step 8: Log the approval",
         "INSERT INTO decision_log (recipe, item, decision, rules, approved_by) VALUES ($1, $2, $3, $4::jsonb, $5) RETURNING id",
         args=['"R7.2"', f"{AEV}.invoice_id", f"'approval ' + {AEV}.decision",
               "JSON.stringify({ approver: $('Step 8: Read the approval').first().json.approver, tolerance_version: $('Step 8: Read the approval').first().json.tolerance_version })",
               f"{AEV}.decided_by"],
         pos=[1300, 900], notes="Decision log: who approved or rejected, and when.")
    w.if_("Rejected?", f"={{{{ {AEV}.decision }}}}", op="equals", right="rejected", pos=[1560, 900])
    w.connect("Approval decision?", "Step 8: Read the approval", output=0)
    w.chain("Step 8: Read the approval", "Step 8: Record the decision", "Step 8: Log the approval", "Rejected?")
    w.connect("Step 8: Record the decision", "Exception queue: write failed", output=1)

    w.http("Step 8: Read this invoice's reservations", "GET", f"={{{{ {CFG}.reservations_url }}}}/reservations",
           query={"_wrap": "1", "invoice_id": f"={{{{ {AEV}.invoice_id }}}}"}, write=False, error_output=False, pos=[1820, 800])
    w.code("Step 8: Reservations to release", REJECT_JS, mode="runOnceForAllItems", pos=[2080, 800])
    w.http("Step 8: Release reservation", "DELETE", f"={{{{ {CFG}.reservations_url }}}}/reservations/{{{{ $json.id }}}}",
           write=True, pos=[2340, 800])
    w.connect("Rejected?", "Step 8: Read this invoice's reservations", output=0)
    w.chain("Step 8: Read this invoice's reservations", "Step 8: Reservations to release", "Step 8: Release reservation")
    w.connect("Step 8: Release reservation", "Exception queue: write failed", output=1)

    ap = "$('Step 8: Read the approval').first().json"
    w.if_("AI-paired lines?", f"={{{{ ({ap}.lines || []).some(l => l.ai_paired) }}}}", pos=[1820, 1000])
    w.http("Step 9: Ask purchasing to add the AI pairings", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=(f"={{{{ JSON.stringify({{ to: {CFG}.purchasing, subject: 'Confirm AI pairings for invoice ' + {AEV}.invoice_id, "
                 f"text: 'Approved with AI-paired lines; add the ones you confirm to the supplier-item map: ' + "
                 f"({ap}.lines || []).filter(l => l.ai_paired).map(l => l.description + ' -> ' + l.order_line_id).join('; ') }}) }}}}"),
           write=True, pos=[2080, 1000], notes="Purchasing, not the workflow, adds confirmed pairings to the map.")
    w.connect("Rejected?", "AI-paired lines?", output=1)
    w.connect("AI-paired lines?", "Step 9: Ask purchasing to add the AI pairings", output=0)
    w.connect("Step 9: Ask purchasing to add the AI pairings", "Exception queue: write failed", output=1)
    return w
