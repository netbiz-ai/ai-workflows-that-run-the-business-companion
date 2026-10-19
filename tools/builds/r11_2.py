"""R11.2 Block a purchase before the order is placed: rules only, no AI step.

Source: book Chapter 11, recipe R11.2, build steps 1 to 11 (recipes/R11.2/build-spec.md).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "n8n"))
from wf import Workflow  # noqa: E402

T = "Step 1: Request ready or edited"
M = "Step 11: Each morning"
REQ = f"$('{T}').item.json.body"

RULES_JS = r"""
// Steps 3 to 8 of the book's R11.2, in order. Returns one outcome and its reason codes.
const cfg = $('Config').first().json;
const req = $('Read request').first().json;
const supplier = $('Read supplier record').first().json;
const policy = $('Read policy list').first().json;
const lastPaid = Object.fromEntries(($('Read last prices paid').first().json.items || []).map(p => [p.item, p.unit_price]));
const recent = ($('Read recent requests').first().json.items || []).filter(r => r.id !== req.id && r.status !== 'cancelled');

const reasons = [];
const rules = {};
const day = d => new Date(d + 'T00:00:00Z');
const today = new Date(new Date().toISOString().slice(0, 10) + 'T00:00:00Z');

// Step 3: requests to one supplier and budget line within the window, crossing a limit, are a possible split.
const windowStart = new Date(today.getTime() - cfg.split_window_days * 86400000);
const sameWindow = recent.filter(r => day(r.created) >= windowStart);
const combined = sameWindow.reduce((s, r) => s + Number(r.amount), Number(req.amount));
const crossed = cfg.split_limits.some(l => Number(req.amount) <= l && combined > l);
const total = crossed ? combined : Number(req.amount);
rules.possible_split = crossed ? `combined ${combined} with ${sameWindow.map(r => r.id).join(', ')}` : 'no';

// Step 4: supplier active with no hold; then a total at or under the limit needs no PO and stops.
if (!supplier.active) reasons.push('supplier inactive');
if (supplier.hold) reasons.push('supplier on hold');
rules.supplier = reasons.length ? 'failed' : 'passed';
if (!reasons.length && total <= cfg.no_po_limit) {
  return [{ json: { outcome: 'no_po', status: 'no PO needed', total, reasons: [], rules } }];
}

// Step 5: a checked comparison row, or a waiver from the policy list (which skips step 6).
const waiver = req.waiver && (policy.waiver_grantors || []).includes(req.waiver.by) ? req.waiver : null;
if (!waiver && !(req.comparison && req.comparison.checked)) reasons.push('no checked comparison or valid waiver');
rules.comparison = waiver ? `waiver by ${waiver.by}, logged for review` : (req.comparison && req.comparison.checked ? 'passed' : 'failed');

// Step 6: the quote matches, is valid for the margin in working days, and freight is stated or included.
if (!waiver) {
  const q = req.quote || {};
  let d = new Date(today), n = 0;
  while (n < cfg.margin_working_days) { d = new Date(d.getTime() + 86400000); if (d.getUTCDay() % 6 !== 0) n++; }
  if (!q.matches) reasons.push('quote not matched');
  if (!q.valid_until || day(q.valid_until) < d) reasons.push('expires within margin');
  if (!['stated', 'included'].includes(q.freight)) reasons.push('freight not stated');
  rules.quote = q.matches && q.valid_until && day(q.valid_until) >= d && ['stated', 'included'].includes(q.freight) ? 'passed' : 'failed';
}

// Step 7: the category is allowed for the budget line.
if (!(policy.allowed_categories || []).includes(req.category)) reasons.push('category not allowed');
rules.category = (policy.allowed_categories || []).includes(req.category) ? 'passed' : 'failed';

if (reasons.length) {
  return [{ json: { outcome: 'blocked', status: 'blocked', total, reasons, rules } }];
}

// Step 8: a price more than the set share below the last price paid waits for the price approver.
const cheap = (req.lines || []).filter(l => lastPaid[l.item] && Number(l.unit_price) < lastPaid[l.item] * (1 - cfg.price_drop_pct / 100));
rules.price = cheap.length ? `over ${cfg.price_drop_pct}% below last paid: ${cheap.map(l => l.item).join(', ')}` : 'passed';
if (cheap.length) {
  return [{ json: { outcome: 'price_check', status: 'waiting for price check', total, reasons: ['price far below last paid'], rules } }];
}

// Step 9: pass.
return [{ json: { outcome: 'pass', status: 'checked; to approval', total, reasons: [], rules } }];
"""

BACKSTOP_JS = r"""
// Step 11: any PO over the limit with no approved request goes to the finance reviewer.
const cfg = $('Config').first().json;
const pos = $('Read yesterday\'s POs').first().json.items || [];
const approved = new Set(($('Read approved requests').first().json.items || []).map(r => r.id));
const orphans = pos.filter(p => Number(p.amount) > cfg.no_po_limit && !approved.has(p.request_id));
return orphans.map(p => ({ json: { po: p.id, amount: p.amount, request_id: p.request_id || null } }));
"""


def build() -> Workflow:
    w = Workflow("R11.2", "R11.2 Block a purchase before the order is placed")
    w.webhook(T, "r11-2-request", "Your request list calls this when a request is saved as \"ready\" or its version changes. Body: {request_id, version}.", pos=[0, 0])
    w.schedule(M, 7, "The morning backstop (step 11).", pos=[0, 520])
    w.config("Config", {
        "requests_url": "https://<your request list API>",
        "vendors_url": "https://<your vendor-record export API>",
        "policy_url": "https://<your policy list API>",
        "ledger_url": "https://<your accounting platform export API>",
        "messaging_url": "https://<your messaging API>",
        "split_window_days": 14,
        "split_limits": [500, 10000],
        "no_po_limit": 500,
        "margin_working_days": 5,
        "price_drop_pct": 30,
        "price_approver": "<your purchasing approver>",
        "backstop_reviewer": "<your finance reviewer>",
    }, pos=[260, 260])
    w.connect(T, "Config")
    w.connect(M, "Config")
    w.if_("Morning backstop?", f"={{{{ $('{M}').isExecuted }}}}", pos=[520, 260])
    w.connect("Config", "Morning backstop?")

    # ---- request path ---------------------------------------------------------
    w.http("Read request", "GET", f"={{{{ $('Config').item.json.requests_url }}}}/requests/{{{{ {REQ}.request_id }}}}",
           write=False, error_output=False, pos=[780, 0])
    w.connect("Morning backstop?", "Read request", output=1)
    w.reserve_key("Step 2: Reserve key", f"{REQ}.request_id + ':' + {REQ}.version", pos=[1040, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1300, 0])
    w.noop("Duplicate: stop", pos=[1560, -160], notes="Key already logged: this request version was checked before.")
    w.chain("Read request", "Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    req = "$('Read request').item.json"
    w.http("Read supplier record", "GET", f"={{{{ $('Config').item.json.vendors_url }}}}/records/{{{{ {req}.supplier_id }}}}",
           write=False, error_output=False, pos=[1560, 0])
    w.http("Read policy list", "GET", f"={{{{ $('Config').item.json.policy_url }}}}/budget_lines/{{{{ {req}.budget_line }}}}",
           write=False, error_output=False, pos=[1820, 0])
    w.http("Read last prices paid", "GET", "={{ $('Config').item.json.ledger_url }}/last_prices",
           query={"_wrap": "1"}, write=False, error_output=False, pos=[2080, 0])
    w.http("Read recent requests", "GET", "={{ $('Config').item.json.requests_url }}/requests",
           query={"_wrap": "1", "supplier_id": f"={{{{ {req}.supplier_id }}}}", "budget_line": f"={{{{ {req}.budget_line }}}}"},
           write=False, error_output=False, pos=[2340, 0])
    w.code("Rules: steps 3 to 8", RULES_JS, mode="runOnceForAllItems", pos=[2600, 0],
           notes="Rules decide; there is no AI step in R11.2.")
    w.connect("New key?", "Read supplier record", output=0)
    w.chain("Read supplier record", "Read policy list", "Read last prices paid", "Read recent requests", "Rules: steps 3 to 8")

    w.switch("Outcome", "={{ $json.outcome }}", ["pass", "no_po", "blocked", "price_check"], pos=[2860, 0])
    w.connect("Rules: steps 3 to 8", "Outcome")
    status_body = "={{ JSON.stringify({ status: $json.status, total: $json.total, reasons: $json.reasons }) }}"
    url = f"={{{{ $('Config').item.json.requests_url }}}}/requests/{{{{ {REQ}.request_id }}}}"
    w.http("Step 9: Set checked; to approval", "PATCH", url, body=status_body, write=True, pos=[3120, -240],
           notes="Starts R11.3. A write: never retried.")
    w.http("Step 4: Set no PO needed", "PATCH", url, body=status_body, write=True, pos=[3120, -80])
    w.http("Step 10: Set blocked", "PATCH", url, body=status_body, write=True, pos=[3120, 80])
    w.http("Step 8: Set waiting for price check", "PATCH", url, body=status_body, write=True, pos=[3120, 240])
    for i, n in enumerate(["Step 9: Set checked; to approval", "Step 4: Set no PO needed", "Step 10: Set blocked", "Step 8: Set waiting for price check"]):
        w.connect("Outcome", n, output=i)

    msg = "$('Config').item.json.messaging_url"
    w.http("Step 10: Tell the requester", "POST", f"={{{{ {msg} }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: {req}.requester, subject: 'Purchase request ' + {REQ}.request_id + ' blocked', text: 'Fix and save again: ' + $('Rules: steps 3 to 8').item.json.reasons.join('; ') }}) }}}}",
           write=True, pos=[3380, 80])
    w.http("Step 8: Tell the price approver", "POST", f"={{{{ {msg} }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: $('Config').item.json.price_approver, subject: 'Price check: request ' + {REQ}.request_id, text: $('Rules: steps 3 to 8').item.json.rules.price }}) }}}}",
           write=True, pos=[3380, 240])
    w.connect("Step 10: Set blocked", "Step 10: Tell the requester")
    w.connect("Step 8: Set waiting for price check", "Step 8: Tell the price approver")

    key = f"{REQ}.request_id + ':' + {REQ}.version"
    rules = "$('Rules: steps 3 to 8').item.json"
    w.finish_key("Mark key done", key, "done", f"{rules}.status", pos=[3640, -80])
    w.decision_log("Decision log", f"{REQ}.request_id", f"{rules}.status",
                   f"JSON.stringify(Object.assign({{}}, {rules}.rules, {{ reasons: {rules}.reasons, total: {rules}.total }}))", pos=[3900, -80])
    for n in ["Step 9: Set checked; to approval", "Step 4: Set no PO needed", "Step 10: Tell the requester", "Step 8: Tell the price approver"]:
        w.connect(n, "Mark key done")
    w.connect("Mark key done", "Decision log")

    w.finish_key("Mark key failed", key, "failed", "'write failed: ' + ($json.error && $json.error.message || 'unknown')", pos=[3640, 400])
    w.exception("Exception queue: write failed", f"{REQ}.request_id", "write failed",
                "'Status write failed; check the request before releasing the key'", "$('Config').item.json.price_approver", pos=[3900, 400])
    for n in ["Step 9: Set checked; to approval", "Step 4: Set no PO needed", "Step 10: Set blocked", "Step 8: Set waiting for price check",
              "Step 10: Tell the requester", "Step 8: Tell the price approver"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- morning backstop -----------------------------------------------------
    w.http("Read yesterday's POs", "GET", "={{ $('Config').item.json.ledger_url }}/pos", query={"_wrap": "1"},
           write=False, error_output=False, pos=[780, 520])
    w.http("Read approved requests", "GET", "={{ $('Config').item.json.requests_url }}/requests",
           query={"_wrap": "1", "status": "approved"}, write=False, error_output=False, pos=[1040, 520])
    w.code("Rule: POs with no approved request", BACKSTOP_JS, mode="runOnceForAllItems", pos=[1300, 520])
    w.exception("Exception queue: PO without approval", "$json.po", "PO without approved request",
                "'PO ' + $json.po + ' for ' + $json.amount + ' has no approved request'", "$('Config').item.json.backstop_reviewer", pos=[1560, 520])
    w.http("Step 11: Tell the finance reviewer", "POST", "={{ $('Config').item.json.messaging_url }}/messages",
           body="={{ JSON.stringify({ to: $('Config').item.json.backstop_reviewer, subject: 'PO without an approved request', text: 'PO ' + $('Rule: POs with no approved request').item.json.po + ' for ' + $('Rule: POs with no approved request').item.json.amount }) }}",
           write=True, error_output=False, pos=[1820, 520])
    w.connect("Morning backstop?", "Read yesterday's POs", output=0)
    w.chain("Read yesterday's POs", "Read approved requests", "Rule: POs with no approved request",
            "Exception queue: PO without approval", "Step 11: Tell the finance reviewer")
    return w
