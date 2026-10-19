"""R11.3 Route purchase approval by amount and remaining budget: rules only, no AI step.

Source: book Chapter 11, recipe R11.3, Table 11.2 and build steps 1 to 12 (recipes/R11.3/build-spec.md).

Four events, all through one Config node:
- Step 1: the request list calls a webhook when a request's status becomes "checked; to approval".
- Step 9: the approvals system calls a webhook when an approver answers.
- Steps 7 and 8: each morning, open approvals are reminded or sent to the stand-in.
- Step 12: the accounting export calls a webhook when a new export lands.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "n8n"))
from wf import Workflow  # noqa: E402

T = "Step 1: Status set to checked; to approval"
A = "Step 9: Approval answered"
M = "Steps 7 and 8: Each morning"
E = "Step 12: New accounting export"
REQ = f"$('{T}').item.json.body"
ANS = f"$('{A}').item.json.body"
CFG = "$('Config').item.json"
KEY = f"{REQ}.request_id + ':' + {REQ}.version"
ANS_KEY = f"'answer:' + {ANS}.approval_id"

DATES_JS = r"""
const iso = d => d.toISOString().slice(0, 10);
const day = s => new Date(String(s).slice(0, 10) + 'T00:00:00Z');
const today = day(iso(new Date()));
const addWorkingDays = (d, n) => { let x = new Date(d), k = 0; while (k < n) { x = new Date(x.getTime() + 86400000); if (x.getUTCDay() % 6 !== 0) k++; } return x; };
const same = (a, b) => String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
"""

ROUTE_JS = DATES_JS + r"""
// Steps 3 to 5 of the book's R11.3, in Table 11.2's order.
const cfg = $('Config').first().json;
const ev = $('Step 1: Status set to checked; to approval').first().json.body;
const req = $('Read request').first().json;
const line = $('Read budget line').first().json;
const commitments = $('Read commitments').first().json.items || [];
const amount = Number(req.amount);
const total = Number(req.total != null ? req.total : req.amount);

// Step 10's lock: a released request is never approved again; an edit needs a new request.
if (req.locked) {
  return [{ json: { route: 'edit_refused', decision: 'edit refused; new request needed',
    rules: { locked: true, approved_version: req.approved_version, version: ev.version } } }];
}

// Step 3: remaining budget is budget less spent and committed; an export over the limit waits for the budget owner.
const committed = commitments.reduce((s, c) => s + Number(c.remaining || 0), 0);
const remaining = Number(line.budget) - Number(line.spent) - committed;
const age = line.export_date ? Math.round((today - day(line.export_date)) / 86400000) : null;
const rules = { export_date: line.export_date || null, export_age_days: age, budget: Number(line.budget), spent: Number(line.spent),
  committed, budget_before: remaining, amount, total };
if (age === null || !(age <= cfg.budget_export_max_days)) {
  return [{ json: { route: 'held', decision: 'held: budget export stale', rules,
    detail: `Budget export for ${req.budget_line} is ${age === null ? 'missing' : age + ' days old'}; refresh it, then rerun request ${req.id}` } }];
}

// Step 4: over remaining budget on this request alone (budget owner copied), or over the limit on R11.2's split total, goes to the senior approver.
const overBudget = amount > remaining;
const overLimit = total > cfg.senior_limit;
rules.over_budget = overBudget;
rules.over_limit = overLimit;
const chain = overBudget || overLimit ? [cfg.senior_approver, cfg.approver] : [cfg.approver, cfg.senior_approver];

// Step 5: skip any approver or stand-in who is the requester or the payment approver; the senior approver's own go to the approver.
const barred = p => same(p, req.requester) || same(p, cfg.payment_approver);
const eligible = chain.filter(p => !barred(p));
rules.skipped = chain.filter(barred);
if (!eligible.length) {
  return [{ json: { route: 'no_approver', decision: 'no eligible approver', rules,
    detail: `Every approver and stand-in for request ${req.id} is the requester or the payment approver` } }];
}
const approval = {
  id: `${req.id}-v${ev.version}`, request_id: req.id, version: ev.version, status: 'open',
  approver: eligible[0], standin: eligible[1] || null, requester: req.requester,
  amount, total, valid_until: (req.quote && req.quote.valid_until) || null, waiver: !!req.waiver,
  comparison_link: (req.comparison && req.comparison.link) || null,
  budget_line: req.budget_line, budget_before: remaining, budget_after: remaining - amount,
  created: iso(today),
  remind_on: iso(addWorkingDays(today, cfg.remind_working_days)),
  standin_on: iso(addWorkingDays(today, cfg.standin_working_days)),
};
rules.approver = approval.approver;
rules.standin = approval.standin;
rules.budget_after = approval.budget_after;
return [{ json: { route: 'approval', decision: `sent to ${approval.approver}`, copy_budget_owner: overBudget, approval, rules } }];
"""

ANSWER_JS = DATES_JS + r"""
// Steps 9 to 11: an answer counts only for an open approval of the request's current version.
const cfg = $('Config').first().json;
const ans = $('Step 9: Approval answered').first().json.body;
const appr = $('Read the approval').first().json;
const req = $('Read request at answer').first().json;
const supplier = $('Read supplier record').first().json;
const policy = $('Read policy list').first().json;
const by = ans.by || appr.approver;
const base = { approval: appr.id, version: appr.version, approver: appr.approver, answered_by: by,
  budget_before: appr.budget_before, budget_after: appr.budget_after };

if (appr.status !== 'open') return [{ json: { outcome: 'void', decision: `answer ignored: approval ${appr.status}`, rules: base } }];
if (Number(req.version) !== Number(appr.version)) {
  return [{ json: { outcome: 'void', decision: 'answer ignored: request changed since the approval started', rules: base } }];
}
if (ans.decision === 'rejected') {
  return [{ json: { outcome: 'rejected', decision: 'rejected', by, comment: ans.comment || '', rules: base } }];
}
if (ans.decision !== 'approved') return [{ json: { outcome: 'void', decision: `answer ignored: unknown decision ${ans.decision}`, rules: base } }];

// Step 9: rerun R11.2's supplier rule and its step 6 with the release margin; a waiver skips the quote half.
const reasons = [];
if (!supplier.active) reasons.push('supplier inactive');
if (supplier.hold) reasons.push('supplier on hold');
const waiver = req.waiver && (policy.waiver_grantors || []).includes(req.waiver.by) ? req.waiver : null;
if (!waiver) {
  const q = req.quote || {};
  const margin = addWorkingDays(today, cfg.release_margin_working_days);
  if (!q.valid_until || day(q.valid_until) < today) reasons.push('quote expired during approval');
  else if (day(q.valid_until) < margin) reasons.push('expires within release margin');
  if (!q.matches) reasons.push('quote not matched');
  if (!['stated', 'included'].includes(q.freight)) reasons.push('freight not stated');
}
const rules = Object.assign(base, { supplier: supplier.active && !supplier.hold ? 'passed' : 'failed',
  quote: waiver ? `waiver by ${waiver.by}` : (reasons.some(r => r.startsWith('quote') || r.startsWith('expires') || r.startsWith('freight')) ? 'failed' : 'passed'),
  reasons });
if (reasons.length) return [{ json: { outcome: 'blocked', decision: 'blocked', by, reasons, rules } }];
return [{ json: { outcome: 'release', decision: 'approved', by, rules } }];
"""

MORNING_JS = DATES_JS + r"""
// Steps 7 and 8: remind after two working days (warning the requester if the quote expires first), then the stand-in after three.
const cfg = $('Config').first().json;
const open = $('Read open approvals').first().json.items || [];
const t = iso(today);
const out = [];
for (const a of open) {
  const what = `Approval ${a.id}: request ${a.request_id}, ${a.amount}`;
  if (a.escalated) {
    if (!a.final_sent && a.final_on && t >= a.final_on) {
      out.push({ action: 'final', id: a.id, request_id: a.request_id, patch: { final_sent: true },
        to: cfg.senior_approver, subject: `No answer after the stand-in: ${a.id}`, text: `${what}; no answer from ${a.approver}. Decide it.` });
    }
    continue;
  }
  if (a.standin_on && t >= a.standin_on) {
    if (a.standin) {
      out.push({ action: 'standin', id: a.id, request_id: a.request_id,
        patch: { approver: a.standin, standin: null, escalated: true, final_on: iso(addWorkingDays(today, cfg.standin_working_days)) },
        to: a.standin, subject: `Approval waiting for you as stand-in: ${a.id}`, text: `${what}; no answer from ${a.approver}.` });
    } else {
      out.push({ action: 'final', id: a.id, request_id: a.request_id, patch: { escalated: true, final_sent: true },
        to: cfg.senior_approver, subject: `No answer and no stand-in: ${a.id}`, text: `${what}; no answer from ${a.approver} and no eligible stand-in. Decide it.` });
    }
    continue;
  }
  if (!a.reminded && a.remind_on && t >= a.remind_on) {
    out.push({ action: 'remind', id: a.id, request_id: a.request_id, patch: { reminded: true },
      to: a.approver, subject: `Reminder: approval ${a.id}`, text: `${what} is waiting for your answer.` });
    if (!a.waiver && a.valid_until && day(a.valid_until) < addWorkingDays(today, cfg.release_margin_working_days)) {
      out.push({ action: 'warn', id: a.id, request_id: a.request_id, to: a.requester,
        subject: `Quote may expire before approval: ${a.request_id}`,
        text: `The quote is valid until ${a.valid_until}; if it expires before the approval arrives, the request is blocked and needs a fresh quote.` });
    }
  }
}
return out.map(json => ({ json }));
"""

BILLS_JS = r"""
// Step 12: only bills against a commitment count; each bill is counted once (key log).
const bills = $('Read the export\'s bills').first().json.items || [];
const commitments = new Set(($('Read commitments for bills').first().json.items || []).map(c => c.request_id));
const keys = bills.filter(b => commitments.has(b.request_id)).map(b => 'bill:' + b.id);
return keys.length ? [{ json: { keys: keys.join('|') } }] : [];
"""

REDUCE_JS = r"""
// Step 12: reduce each commitment by its new bills; a bill over its commitment by more than the tolerance goes to the budget owner.
const cfg = $('Config').first().json;
const tolerance = Number(cfg.bill_tolerance);
if (!Number.isFinite(tolerance)) throw new Error('Set bill_tolerance in Config to a number of dollars');
const fresh = new Set(String($('Reserve bill keys').first().json.new_keys || '').split('|').filter(Boolean));
const bills = ($('Read the export\'s bills').first().json.items || []).filter(b => fresh.has('bill:' + b.id));
const out = [];
for (const c of $('Read commitments for bills').first().json.items || []) {
  const mine = bills.filter(b => b.request_id === c.request_id);
  if (!mine.length) continue;
  const billed = Number(c.billed || 0) + mine.reduce((s, b) => s + Number(b.amount), 0);
  const remaining = Math.max(0, Number(c.amount) - billed);
  const over = billed > Number(c.amount) + tolerance;
  out.push({ json: { commitment: c.id, request_id: c.request_id, amount: Number(c.amount), billed, remaining, over,
    bills: mine.map(b => b.id), keys: mine.map(b => 'bill:' + b.id).join('|'),
    detail: `Commitment ${c.id}: ${c.amount}; billed ${billed} (${mine.map(b => b.id).join(', ')}); tolerance ${tolerance}` } });
}
return out;
"""


def _independent(w: Workflow, *names: str) -> None:
    """Postgres nodes that receive several items run one query per item."""
    for n in w.nodes:
        if n["name"] in names:
            n["parameters"]["options"]["queryBatching"] = "independently"


def build() -> Workflow:
    w = Workflow("R11.3", "R11.3 Route purchase approval by amount and remaining budget")
    w.webhook(T, "r11-3-to-approval", "Your request list calls this when a request's status becomes \"checked; to approval\" (set by R11.2). Body: {request_id, version}.", pos=[0, 0])
    w.webhook(A, "r11-3-approval-answered", "Your approvals system calls this when an approver answers. Body: {approval_id, decision: approved | rejected, by, comment}.", pos=[0, 800])
    w.schedule(M, 7, "Steps 7 and 8: reminders and stand-ins for open approvals.", pos=[0, 1400])
    w.webhook(E, "r11-3-new-export", "Your accounting platform calls this when a new export lands. Body: {export_date}.", pos=[0, 1900])
    w.config("Config", {
        "requests_url": "https://<your request list API>",
        "budget_url": "https://<your budget list API>",
        "approvals_url": "https://<your approvals API>",
        "vendors_url": "https://<your vendor-record export API>",
        "policy_url": "https://<your policy list API>",
        "ledger_url": "https://<your accounting platform export API>",
        "messaging_url": "https://<your messaging API>",
        "budget_export_max_days": 7,
        "senior_limit": 10000,
        "release_margin_working_days": 2,
        "remind_working_days": 2,
        "standin_working_days": 3,
        "bill_tolerance": "<your bill tolerance, in dollars>",
        "approver": "<your approver up to the limit>",
        "senior_approver": "<your senior approver>",
        "payment_approver": "<your payment approver>",
        "budget_owner": "<your budget owner>",
        "buyer": "<your buyer>",
        "editor": "<your workflow editor>",
    }, pos=[260, 900])
    for t in (T, A, M, E):
        w.connect(t, "Config")
    w.switch("Which event?",
             f"={{{{ $('{T}').isExecuted ? 'request' : $('{A}').isExecuted ? 'answer' : $('{M}').isExecuted ? 'morning' : 'export' }}}}",
             ["request", "answer", "morning", "export"], pos=[520, 900])
    w.connect("Config", "Which event?")

    # ---- steps 1 to 6: route a checked request -------------------------------
    req = "$('Read request').item.json"
    w.http("Read request", "GET", f"={{{{ {CFG}.requests_url }}}}/requests/{{{{ {REQ}.request_id }}}}",
           write=False, error_output=False, pos=[780, 0])
    w.connect("Which event?", "Read request", output=0)
    w.reserve_key("Step 2: Reserve key", KEY, pos=[1040, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1300, 0])
    w.noop("Duplicate: stop", pos=[1560, -160], notes="An approval for this request version is open or decided.")
    w.chain("Read request", "Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)
    w.http("Read budget line", "GET", f"={{{{ {CFG}.budget_url }}}}/lines/{{{{ {req}.budget_line }}}}",
           write=False, error_output=False, pos=[1560, 0])
    w.http("Read commitments", "GET", f"={{{{ {CFG}.budget_url }}}}/commitments",
           query={"_wrap": "1", "budget_line": f"={{{{ {req}.budget_line }}}}"}, write=False, error_output=False, pos=[1820, 0])
    w.code("Rules: steps 3 to 5", ROUTE_JS, mode="runOnceForAllItems", pos=[2080, 0],
           notes="Table 11.2, R11.3 rows: budget export age, remaining budget and amount, then who may approve.")
    w.connect("New key?", "Read budget line", output=0)
    w.chain("Read budget line", "Read commitments", "Rules: steps 3 to 5")
    w.switch("Route", "={{ $json.route }}", ["approval", "held", "edit_refused", "no_approver"], pos=[2340, 0])
    w.connect("Rules: steps 3 to 5", "Route")
    rules = "$('Rules: steps 3 to 5').item.json"
    msg = f"={{{{ {CFG}.messaging_url }}}}/messages"

    w.http("Step 6: Start one approval", "POST", f"={{{{ {CFG}.approvals_url }}}}/approvals",
           body=f"={{{{ JSON.stringify({rules}.approval) }}}}", write=True, pos=[2600, -240],
           notes="Shows amount, valid-until date, comparison link and budget after. A write: never retried.")
    w.if_("Over budget?", f"={{{{ {rules}.copy_budget_owner }}}}", pos=[2860, -240])
    w.http("Step 4: Copy the budget owner", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.budget_owner, subject: 'Over budget: request ' + {REQ}.request_id, text: 'Sent to ' + {rules}.approval.approver + ': ' + {rules}.approval.amount + ' against ' + {rules}.approval.budget_before + ' remaining on ' + {rules}.approval.budget_line }}) }}}}",
           write=True, pos=[3120, -320])
    w.connect("Route", "Step 6: Start one approval", output=0)
    w.connect("Step 6: Start one approval", "Over budget?")
    w.connect("Over budget?", "Step 4: Copy the budget owner", output=0)

    w.exception("Step 3: Exception queue: budget export stale", f"{REQ}.request_id", "budget export stale",
                f"{rules}.detail", f"{CFG}.budget_owner", pos=[2600, -40])
    w.http("Step 3: Tell the budget owner", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.budget_owner, subject: 'Refresh the budget export', text: {rules}.detail }}) }}}}",
           write=True, pos=[2860, -40])
    w.connect("Route", "Step 3: Exception queue: budget export stale", output=1)
    w.connect("Step 3: Exception queue: budget export stale", "Step 3: Tell the budget owner")

    url = f"={{{{ {CFG}.requests_url }}}}/requests/{{{{ {REQ}.request_id }}}}"
    w.http("Step 10: Keep it approved; edit refused", "PATCH", url,
           body="={{ JSON.stringify({ status: 'approved', edit_refused: 'new request needed' }) }}", write=True, pos=[2600, 140],
           notes="The request was approved and locked; its edit does not reopen it.")
    w.http("Step 10: Tell the requester a new request is needed", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {req}.requester, subject: 'Request ' + {REQ}.request_id + ' is approved and locked', text: 'Edit refused: this request was approved and released. Raise a new request for the change.' }}) }}}}",
           write=True, pos=[2860, 140])
    w.connect("Route", "Step 10: Keep it approved; edit refused", output=2)
    w.connect("Step 10: Keep it approved; edit refused", "Step 10: Tell the requester a new request is needed")

    w.exception("Exception queue: no eligible approver", f"{REQ}.request_id", "no eligible approver",
                f"{rules}.detail", f"{CFG}.senior_approver", pos=[2600, 320])
    w.connect("Route", "Exception queue: no eligible approver", output=3)

    w.pg("Release key: no approval open", "DELETE FROM key_log WHERE recipe = $1 AND key = $2 RETURNING key",
         args=[json.dumps("R11.3"), KEY], pos=[3380, 120],
         notes="No approval is open or decided, so a rerun after the fix must not stop at step 2.")
    w.connect("Step 3: Tell the budget owner", "Release key: no approval open")
    w.connect("Exception queue: no eligible approver", "Release key: no approval open")

    w.finish_key("Mark key done", KEY, "done", f"{rules}.decision", pos=[3380, -160])
    for n, o in [("Over budget?", 1), ("Step 4: Copy the budget owner", 0), ("Step 10: Tell the requester a new request is needed", 0)]:
        w.connect(n, "Mark key done", output=o)
    w.decision_log("Decision log", f"{REQ}.request_id + ' v' + {REQ}.version", f"{rules}.decision",
                   f"JSON.stringify({rules}.rules)", pos=[3640, -40])
    w.connect("Mark key done", "Decision log")
    w.connect("Release key: no approval open", "Decision log")

    w.finish_key("Mark key failed", KEY, "failed", "'write failed: ' + ($json.error && $json.error.message || 'unknown')", pos=[3380, 400])
    w.exception("Exception queue: write failed", f"{REQ}.request_id", "write failed",
                "'Approval write failed; check the request list, then rerun it'", f"{CFG}.editor", pos=[3640, 400])
    for n in ["Step 6: Start one approval", "Step 4: Copy the budget owner", "Step 3: Tell the budget owner",
              "Step 10: Keep it approved; edit refused", "Step 10: Tell the requester a new request is needed"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- steps 9 to 11: an approver answers ----------------------------------
    appr = "$('Read the approval').item.json"
    areq = "$('Read request at answer').item.json"
    w.http("Read the approval", "GET", f"={{{{ {CFG}.approvals_url }}}}/approvals/{{{{ {ANS}.approval_id }}}}",
           write=False, error_output=False, pos=[780, 800])
    w.connect("Which event?", "Read the approval", output=1)
    w.reserve_key("Reserve key: approval answer", ANS_KEY, pos=[1040, 800])
    w.if_("New answer?", "={{ $json.is_new }}", pos=[1300, 800])
    w.noop("Duplicate answer: stop", pos=[1560, 640], notes="This approval's answer was handled before.")
    w.chain("Read the approval", "Reserve key: approval answer", "New answer?")
    w.connect("New answer?", "Duplicate answer: stop", output=1)
    w.http("Read request at answer", "GET", f"={{{{ {CFG}.requests_url }}}}/requests/{{{{ {appr}.request_id }}}}",
           write=False, error_output=False, pos=[1560, 800])
    w.http("Read supplier record", "GET", f"={{{{ {CFG}.vendors_url }}}}/records/{{{{ {areq}.supplier_id }}}}",
           write=False, error_output=False, pos=[1820, 800])
    w.http("Read policy list", "GET", f"={{{{ {CFG}.policy_url }}}}/budget_lines/{{{{ {areq}.budget_line }}}}",
           write=False, error_output=False, pos=[2080, 800], notes="For R11.2's waiver rule: who may grant a waiver.")
    w.code("Rules: steps 9 to 11", ANSWER_JS, mode="runOnceForAllItems", pos=[2340, 800],
           notes="Table 11.2, last row: the quote and supplier are checked again when the approval arrives.")
    w.connect("New answer?", "Read request at answer", output=0)
    w.chain("Read request at answer", "Read supplier record", "Read policy list", "Rules: steps 9 to 11")
    ar = "$('Rules: steps 9 to 11').item.json"
    w.if_("Answer counts?", "={{ $json.outcome }}", op="equals", right="void", pos=[2600, 800])
    w.noop("Answer ignored", pos=[2860, 960], notes="The approval is no longer open, or the request changed since it started.")
    w.connect("Rules: steps 9 to 11", "Answer counts?")
    w.connect("Answer counts?", "Answer ignored", output=0)
    w.http("Step 9: Record the answer", "PATCH", f"={{{{ {CFG}.approvals_url }}}}/approvals/{{{{ {ANS}.approval_id }}}}",
           body=f"={{{{ JSON.stringify({{ status: {ANS}.decision, decided_by: {ar}.by, comment: {ANS}.comment || '', decided_on: $now.toISODate() }}) }}}}",
           write=True, pos=[2860, 760])
    w.connect("Answer counts?", "Step 9: Record the answer", output=1)
    w.switch("Decision", f"={{{{ {ar}.outcome }}}}", ["release", "blocked", "rejected"], pos=[3120, 760])
    w.connect("Step 9: Record the answer", "Decision")

    aurl = f"={{{{ {CFG}.requests_url }}}}/requests/{{{{ {appr}.request_id }}}}"
    w.http("Step 10: Set approved and lock it", "PATCH", aurl,
           body=f"={{{{ JSON.stringify({{ status: 'approved', locked: true, approved_by: {ar}.by, approved_version: {appr}.version }}) }}}}",
           write=True, pos=[3380, 600], notes="Locked: an edit needs a new request.")
    w.http("Step 10: Write the commitment", "POST", f"={{{{ {CFG}.budget_url }}}}/commitments",
           body=f"={{{{ JSON.stringify({{ id: {appr}.request_id, request_id: {appr}.request_id, budget_line: {appr}.budget_line, amount: {appr}.amount, billed: 0, remaining: {appr}.amount }}) }}}}",
           write=True, pos=[3640, 600])
    w.http("Step 10: Tell the buyer to raise the PO", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.buyer, subject: 'Raise the PO: request ' + {appr}.request_id, text: 'Approved by ' + {ar}.by + ' for ' + {appr}.amount + '; quote valid until ' + {appr}.valid_until }}) }}}}",
           write=True, pos=[3900, 600])
    w.connect("Decision", "Step 10: Set approved and lock it", output=0)
    w.chain("Step 10: Set approved and lock it", "Step 10: Write the commitment", "Step 10: Tell the buyer to raise the PO")
    w.http("Step 9: Set blocked", "PATCH", aurl,
           body=f"={{{{ JSON.stringify({{ status: 'blocked', reasons: {ar}.reasons }}) }}}}", write=True, pos=[3380, 760])
    w.http("Step 9: Tell the requester", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {areq}.requester, subject: 'Purchase request ' + {appr}.request_id + ' blocked at release', text: 'Approved, but not released: ' + {ar}.reasons.join('; ') + '. Fix and raise it again.' }}) }}}}",
           write=True, pos=[3640, 760])
    w.connect("Decision", "Step 9: Set blocked", output=1)
    w.connect("Step 9: Set blocked", "Step 9: Tell the requester")
    w.http("Step 11: Record the comment", "PATCH", aurl,
           body=f"={{{{ JSON.stringify({{ status: 'rejected', rejected_by: {ar}.by, rejection_comment: {ar}.comment }}) }}}}",
           write=True, pos=[3380, 920], notes="Rejected: no commitment is written.")
    w.connect("Decision", "Step 11: Record the comment", output=2)

    w.finish_key("Mark answer key done", ANS_KEY, "done", f"{ar}.decision", pos=[4160, 760])
    for n in ["Answer ignored", "Step 10: Tell the buyer to raise the PO", "Step 9: Tell the requester", "Step 11: Record the comment"]:
        w.connect(n, "Mark answer key done")
    w.decision_log("Decision log: answer", f"{appr}.request_id + ' v' + {appr}.version", f"{ar}.decision",
                   f"JSON.stringify({ar}.rules)", pos=[4420, 760])
    w.connect("Mark answer key done", "Decision log: answer")
    w.finish_key("Mark answer key failed", ANS_KEY, "failed", "'write failed: ' + ($json.error && $json.error.message || 'unknown')", pos=[4160, 1100])
    w.exception("Exception queue: answer write failed", f"{appr}.request_id", "write failed",
                "'Write after the approval answer failed; check the request, approval and commitment before rerunning'", f"{CFG}.editor", pos=[4420, 1100])
    for n in ["Step 9: Record the answer", "Step 10: Set approved and lock it", "Step 10: Write the commitment",
              "Step 10: Tell the buyer to raise the PO", "Step 9: Set blocked", "Step 9: Tell the requester", "Step 11: Record the comment"]:
        w.connect(n, "Mark answer key failed", output=1)
    w.connect("Mark answer key failed", "Exception queue: answer write failed")

    # ---- steps 7 and 8: each morning ------------------------------------------
    w.http("Read open approvals", "GET", f"={{{{ {CFG}.approvals_url }}}}/approvals", query={"_wrap": "1", "status": "open"},
           write=False, error_output=False, pos=[780, 1400])
    w.code("Rules: steps 7 and 8", MORNING_JS, mode="runOnceForAllItems", pos=[1040, 1400])
    w.switch("Action", "={{ $json.action }}", ["remind", "warn", "standin", "final"], pos=[1300, 1400])
    w.connect("Which event?", "Read open approvals", output=2)
    w.chain("Read open approvals", "Rules: steps 7 and 8", "Action")
    act = "$('Action').item.json"
    aprurl = f"={{{{ {CFG}.approvals_url }}}}/approvals/{{{{ {act}.id }}}}"
    patch = f"={{{{ JSON.stringify({act}.patch) }}}}"
    send = f"={{{{ JSON.stringify({{ to: {act}.to, subject: {act}.subject, text: {act}.text }}) }}}}"
    w.http("Step 7: Record the reminder", "PATCH", aprurl, body=patch, write=True, error_output=False, pos=[1560, 1240])
    w.http("Step 7: Remind the approver", "POST", msg, body=send, write=True, error_output=False, pos=[1820, 1240])
    w.http("Step 7: Warn the requester", "POST", msg, body=send, write=True, error_output=False, pos=[1560, 1400],
           notes="The quote expires within the release margin, so it would be blocked at step 9.")
    w.http("Step 8: Send to the stand-in", "PATCH", aprurl, body=patch, write=True, error_output=False, pos=[1560, 1560])
    w.http("Step 8: Tell the stand-in", "POST", msg, body=send, write=True, error_output=False, pos=[1820, 1560])
    w.exception("Exception queue: no answer after the stand-in", f"{act}.request_id", "no answer after the stand-in",
                f"{act}.text", f"{CFG}.senior_approver", pos=[1560, 1720])
    w.http("Record the final escalation", "PATCH", aprurl, body=patch, write=True, error_output=False, pos=[1820, 1720])
    w.http("Tell the senior approver", "POST", msg, body=send, write=True, error_output=False, pos=[2080, 1720])
    w.connect("Action", "Step 7: Record the reminder", output=0)
    w.connect("Step 7: Record the reminder", "Step 7: Remind the approver")
    w.connect("Action", "Step 7: Warn the requester", output=1)
    w.connect("Action", "Step 8: Send to the stand-in", output=2)
    w.connect("Step 8: Send to the stand-in", "Step 8: Tell the stand-in")
    w.connect("Action", "Exception queue: no answer after the stand-in", output=3)
    w.chain("Exception queue: no answer after the stand-in", "Record the final escalation", "Tell the senior approver")

    # ---- step 12: with each export --------------------------------------------
    w.http("Read the export's bills", "GET", f"={{{{ {CFG}.ledger_url }}}}/bills", query={"_wrap": "1"},
           write=False, error_output=False, pos=[780, 1900])
    w.http("Read commitments for bills", "GET", f"={{{{ {CFG}.budget_url }}}}/commitments", query={"_wrap": "1"},
           write=False, error_output=False, pos=[1040, 1900])
    w.code("Bills against a commitment", BILLS_JS, mode="runOnceForAllItems", pos=[1300, 1900])
    w.pg("Reserve bill keys",
         "WITH input AS (SELECT DISTINCT unnest(string_to_array($2, '|')) AS key), "
         "reserved AS (INSERT INTO key_log (recipe, key, status) SELECT $1, key, 'in progress' FROM input "
         "ON CONFLICT (recipe, key) DO NOTHING RETURNING key), "
         "skipped AS (UPDATE key_log SET copies_skipped = copies_skipped + 1 WHERE recipe = $1 "
         "AND key IN (SELECT key FROM input) AND key NOT IN (SELECT key FROM reserved) RETURNING key) "
         "SELECT coalesce((SELECT string_agg(key, '|') FROM reserved), '') AS new_keys",
         args=[json.dumps("R11.3"), "$json.keys"], pos=[1560, 1900],
         notes="Key log: each bill reduces its commitment once, however many exports carry it.")
    w.code("Step 12: Rule: reduce commitments by bills", REDUCE_JS, mode="runOnceForAllItems", pos=[1820, 1900])
    w.connect("Which event?", "Read the export's bills", output=3)
    w.chain("Read the export's bills", "Read commitments for bills", "Bills against a commitment", "Reserve bill keys",
            "Step 12: Rule: reduce commitments by bills")
    red = "$('Step 12: Rule: reduce commitments by bills').item.json"
    w.http("Step 12: Reduce the commitment", "PATCH", f"={{{{ {CFG}.budget_url }}}}/commitments/{{{{ {red}.commitment }}}}",
           body=f"={{{{ JSON.stringify({{ billed: {red}.billed, remaining: {red}.remaining }}) }}}}", write=True, pos=[2080, 1900])
    w.if_("Over tolerance?", f"={{{{ {red}.over }}}}", pos=[2340, 1900])
    w.exception("Step 12: Exception queue: bill over commitment", f"{red}.request_id", "bill over commitment",
                f"{red}.detail", f"{CFG}.budget_owner", pos=[2600, 1820])
    w.http("Step 12: Tell the budget owner", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.budget_owner, subject: 'Bill over its commitment: request ' + {red}.request_id, text: {red}.detail }}) }}}}",
           write=True, error_output=False, pos=[2860, 1820])
    w.chain("Step 12: Rule: reduce commitments by bills", "Step 12: Reduce the commitment", "Over tolerance?")
    w.connect("Over tolerance?", "Step 12: Exception queue: bill over commitment", output=0)
    w.connect("Step 12: Exception queue: bill over commitment", "Step 12: Tell the budget owner")
    keys_sql = ("WITH marked AS (UPDATE key_log SET status = $3, result = $4 WHERE recipe = $1 "
                "AND key = ANY(string_to_array($2, '|')) RETURNING key) SELECT count(*) AS marked FROM marked")
    w.pg("Mark bill keys done", keys_sql,
         args=[json.dumps("R11.3"), f"{red}.keys", json.dumps("done"), f"'billed ' + {red}.billed + ', remaining ' + {red}.remaining"],
         pos=[3120, 1900])
    w.connect("Over tolerance?", "Mark bill keys done", output=1)
    w.connect("Step 12: Tell the budget owner", "Mark bill keys done")
    w.decision_log("Decision log: commitment", f"{red}.commitment",
                   f"{red}.over ? 'bill over commitment' : 'commitment reduced by bills'",
                   f"JSON.stringify({{ amount: {red}.amount, billed: {red}.billed, remaining: {red}.remaining, bills: {red}.bills }})",
                   pos=[3380, 1900])
    w.connect("Mark bill keys done", "Decision log: commitment")
    w.pg("Mark bill keys failed", keys_sql,
         args=[json.dumps("R11.3"), f"{red}.keys", json.dumps("failed"), "'write failed: ' + ($json.error && $json.error.message || 'unknown')"],
         pos=[2340, 2100])
    w.exception("Exception queue: commitment write failed", f"{red}.request_id", "write failed",
                "'Commitment write failed; check the budget list before rerunning'", f"{CFG}.editor", pos=[2600, 2100])
    w.connect("Step 12: Reduce the commitment", "Mark bill keys failed", output=1)
    w.connect("Mark bill keys failed", "Exception queue: commitment write failed")

    _independent(w, "Exception queue: no answer after the stand-in", "Step 12: Exception queue: bill over commitment",
                 "Mark bill keys done", "Decision log: commitment", "Mark bill keys failed", "Exception queue: commitment write failed")
    return w
