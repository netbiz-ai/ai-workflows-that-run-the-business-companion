"""R5.4 Route quote approval by value and discount: rules only, no AI step.

Source: book Chapter 5, recipe R5.4, Table 5.1 and build steps 1 to 8
(recipes/R5.4/build-spec.md). The failure table's weekly sent-to-approved match is
the declared backstop for a CRM that cannot lock quotes.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "n8n"))
from wf import Workflow  # noqa: E402

T = "Step 1: Quote awaiting approval"
D = "Step 8: Decision recorded"
H = "Step 7: Each hour"
WK = "Backstop: Each week"
EV = f"$('{T}').first().json.body"
DV = f"$('{D}').first().json.body"
KEY = f"{EV}.quote_id + ':' + {EV}.revision"
DKEY = f"'decision:' + {DV}.quote_id + ':' + {DV}.revision"
CFG = "$('Config').first().json"
Q = "$('Read the quote').first().json"
DQ = "$('Read the quote (decision)').first().json"

EVENT_JS = r"""
// Which of the four triggers started this run.
const ran = n => { try { return $(n).isExecuted; } catch (e) { return false; } };
const event = ran('Step 1: Quote awaiting approval') ? 'route' : ran('Step 8: Decision recorded') ? 'decision'
  : ran('Step 7: Each hour') ? 'deadlines' : 'backstop';
return [{ json: { event } }];
"""

# Shared by step 3 and step 8: recompute from the CRM record's lines, never the quote text.
RECOMPUTE = r"""
function recompute(q, list) {
  const onList = new Set((list.items || []).map(i => i.code));
  let cents = 0, largest = 0, offList = false, multiYear = Number(q.term_years || 0) > 1;
  for (const l of q.lines || []) {
    const disc = Number(l.discount_pct || 0);
    largest = Math.max(largest, disc);
    if (Number(l.years || 0) > 1) multiYear = true;
    if (l.off_list || l.unit_price == null || !onList.has(l.code)) { offList = true; continue; }
    const u = BigInt(Math.round(Number(l.unit_price) * 10000)), d = BigInt(Math.round(disc * 100));
    cents += Number((u * BigInt(Number(l.quantity)) * (10000n - d) + 500000n) / 1000000n);
  }
  return { value: cents / 100, largest_discount: largest, multi_year: multiYear, off_list: offList, non_standard: q.non_standard_terms === true };
}
function listCurrent(q, list) {
  const today = new Date().toISOString().slice(0, 10);
  return q.price_list_version === list.version && !!list.valid_until && list.valid_until >= today;
}
"""

STEP3_JS = RECOMPUTE + r"""
// Steps 3 and 4: recompute from the CRM record; is the stamped price list still current?
const q = $('Read the quote').first().json, list = $('Read the price list').first().json;
return [{ json: Object.assign(recompute(q, list), { current: listCurrent(q, list), stamped: q.price_list_version, list_version: list.version }) }];
"""

TABLE_JS = r"""
// Step 5: Table 5.1. Ben's own quotes go to Helen; an off-list line counts as over standard.
const cfg = $('Config').first().json;
const q = $('Read the quote').first().json;
const f = $('Step 3: Recompute from the CRM record').first().json;
const A = cfg.approvers;
const spLimit = Number(cfg.salesperson_limit), leadLimit = Number(cfg.sales_lead_limit), std = Number(cfg.standard_discount_pct);
if (![spLimit, leadLimit, std].every(Number.isFinite)) throw new Error('Config: set salesperson_limit, sales_lead_limit and standard_discount_pct to numbers');
const overStd = f.largest_discount > std || f.off_list;
const term = f.multi_year || f.non_standard;
let level, why;
if (q.salesperson === A.sales_lead.person) { level = 'ceo'; why = "sales lead's own quote"; }
else if (f.value > leadLimit) { level = 'ceo'; why = "over the sales lead's limit"; }
else if (f.value > spLimit) { level = 'sales_lead'; why = "between the salesperson's and the sales lead's limits"; }
else if (overStd || term) { level = 'sales_lead'; why = [f.largest_discount > std && 'discount over standard', f.off_list && 'off-list line', f.multi_year && 'multi-year', f.non_standard && 'non-standard term'].filter(Boolean).join(', '); }
else { level = 'salesperson'; why = "within the salesperson's limit and standard discount"; }
const approver = level === 'salesperson' ? q.salesperson : A[level].person;
const now = new Date();
return [{ json: { level, why, approver, deputy: A[level].deputy, deadline_hours: Number(A[level].deadline_hours), requested_at: now.toISOString() } }];
"""

DEADLINE_JS = r"""
// Step 7: remind at the deadline, ask the deputy at twice it, return at three times it.
const quotes = $('Read quotes awaiting approval').first().json.items || [];
const now = Date.now();
const out = [];
for (const q of quotes) {
  if (!q.requested_at || !q.deadline_hours || !q.approver) continue;
  const stage = Math.min(3, Math.floor((now - new Date(q.requested_at).getTime()) / 3600000 / Number(q.deadline_hours)));
  if (stage <= Number(q.escalation || 0)) continue;
  const action = ['', 'remind', 'deputy', 'return'][stage];
  out.push({ json: { quote_id: q.id, revision: q.revision, action, stage, approver: q.approver, deputy: q.deputy, salesperson: q.salesperson } });
}
return out;
"""

DECISION_JS = RECOMPUTE + r"""
// Step 8: only the routed approver or deputy, on the revision they were asked about, decides.
const q = $('Read the quote (decision)').first().json, list = $('Read the price list (decision)').first().json;
const d = $('Step 8: Decision recorded').first().json.body;
const problems = [];
if (q.status !== 'awaiting approval') problems.push(`quote is ${q.status}, not awaiting approval`);
if (Number(d.revision) !== Number(q.revision)) problems.push(`decision on revision ${d.revision}; the quote is now revision ${q.revision} and routes again`);
if (![q.approver, q.deputy].includes(d.by)) problems.push(`${d.by} is not the routed approver or deputy`);
if (!['approved', 'rejected'].includes(d.decision)) problems.push(`decision "${d.decision}" is not approved or rejected`);
if (problems.length) return [{ json: { outcome: 'refuse', reason: problems.join('; ') } }];
if (d.decision === 'approved' && !listCurrent(q, list)) return [{ json: { outcome: 'back', reason: `price list ${q.price_list_version} replaced by ${list.version} while waiting` } }];
return [{ json: Object.assign({ outcome: d.decision === 'approved' ? 'approve' : 'reject' }, recompute(q, list)) }];
"""

ROUTE_SUMMARY_JS = r"""
// What the routing run decided, for the decision log: quote, revision, value, discount, approver.
const ran = n => { try { return $(n).isExecuted; } catch (e) { return false; } };
const f = $('Step 3: Recompute from the CRM record').first().json;
const t = ran('Step 5: Rule: Table 5.1') ? $('Step 5: Rule: Table 5.1').first().json : null;
let decision;
if (!f.current) decision = 'back to R5.3: price list ' + f.stamped + ' is not current';
else if (ran('Step 6: Return the quote, locked')) decision = 'returned: approval request not sent';
else decision = 'routed to ' + t.approver;
return [{ json: { decision, approver: null, rules: { value: f.value, largest_discount: f.largest_discount, multi_year: f.multi_year,
  off_list: f.off_list, non_standard: f.non_standard, level: t ? t.level : null, approver: t ? t.approver : null, why: t ? t.why : null } } }];
"""

DECISION_SUMMARY_JS = r"""
const r = $('Step 8: Rule: accept the decision?').first().json;
const d = $('Step 8: Decision recorded').first().json.body;
const q = $('Read the quote (decision)').first().json;
const decision = { approve: 'approved; sending unlocked', reject: 'rejected; returned with the comment', back: 'back to R5.3: ' + r.reason, refuse: 'decision not accepted: ' + r.reason }[r.outcome];
return [{ json: { decision, approver: r.outcome === 'approve' ? d.by : null,
  rules: { revision: q.revision, value: r.value ?? null, largest_discount: r.largest_discount ?? null, by: d.by, decision: d.decision, price_list_version: q.price_list_version } } }];
"""

BACKSTOP_JS = r"""
// Backstop: any quote sent in the last week without approval of the revision sent.
const cfg = $('Config').first().json;
const since = Date.now() - 7 * 86400000;
const sent = $('Read quotes sent').first().json.items || [];
return sent.filter(q => (!q.sent_at || new Date(q.sent_at).getTime() >= since) && Number(q.approved_revision) !== Number(q.revision))
  .map(q => ({ json: { quote_id: q.id, revision: q.revision, salesperson: q.salesperson } }));
"""


def build() -> Workflow:
    w = Workflow("R5.4", "R5.4 Route quote approval by value and discount")
    w.webhook(T, "r5-4-awaiting-approval", "Your CRM calls this when a quote is set \"awaiting approval\". Body: {quote_id, revision}.", pos=[0, 0])
    w.webhook(D, "r5-4-decision", "Your CRM calls this when an approver records a decision. Body: {quote_id, revision, decision: approved|rejected, by, comment}.", pos=[0, 600])
    w.node(H, "n8n-nodes-base.scheduleTrigger", 1.2, {"rule": {"interval": [{"field": "hours", "hoursInterval": 1}]}},
           pos=[0, 1100], notes="Step 7's deadline check.")
    w.schedule(WK, 7, "The declared backstop where the CRM cannot lock quotes (runs each Monday).", pos=[0, 1400])
    wk = next(n for n in w.nodes if n["name"] == WK)
    wk["parameters"] = {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1, "triggerAtDay": [1], "triggerAtHour": 7}]}}
    w.config("Config", {
        "crm_url": "https://<your CRM API>",
        "messaging_url": "https://<your messaging API>",
        "salesperson_limit": "<your salesperson's limit, after discount>",
        "sales_lead_limit": "<your sales lead's limit, after discount>",
        "standard_discount_pct": "<your standard line discount, %>",
        "approvers": {
            "salesperson": {"deputy": "<your salespeople's deputy>", "deadline_hours": "<hours>"},
            "sales_lead": {"person": "<your sales lead>", "deputy": "<deputy>", "deadline_hours": "<hours>"},
            "ceo": {"person": "<your owner or CEO>", "deputy": "<deputy>", "deadline_hours": "<hours>"},
        },
        "checklist": "<link to your copy of Book 1's Checklist 13.1, the quote approver's check>",
        "systems_owner": "<your systems owner>",
    }, pos=[260, 600])
    for t in (T, D, H, WK):
        w.connect(t, "Config")
    w.code("Which event?", EVENT_JS, mode="runOnceForAllItems", pos=[520, 600])
    w.switch("Event", "={{ $json.event }}", ["route", "decision", "deadlines", "backstop"], pos=[780, 600])
    w.chain("Config", "Which event?", "Event")
    msg_url = f"={{{{ {CFG}.messaging_url }}}}/messages"
    crm = f"{CFG}.crm_url"

    # ---- routing: steps 2 to 6 ------------------------------------------------------
    w.reserve_key("Step 2: Reserve key", KEY, pos=[1040, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1300, 0])
    w.noop("Duplicate: stop", pos=[1560, -200], notes="This quote revision was routed before.")
    w.connect("Event", "Step 2: Reserve key", output=0)
    w.chain("Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)
    w.http("Read the quote", "GET", f"={{{{ {crm} }}}}/quotes/{{{{ {EV}.quote_id }}}}", write=False, error_output=False, pos=[1560, 0])
    w.http("Read the price list", "GET", f"={{{{ {crm} }}}}/price_lists/current", write=False, error_output=False, pos=[1820, 0])
    w.code("Step 3: Recompute from the CRM record", STEP3_JS, mode="runOnceForAllItems", pos=[2080, 0],
           notes="Value after discount, largest line discount, multi-year, off-list and non-standard flags; never the quote text.")
    w.connect("New key?", "Read the quote", output=0)
    w.chain("Read the quote", "Read the price list", "Step 3: Recompute from the CRM record")
    w.if_("Step 4: Stamped price list current?", "={{ $json.current }}", pos=[2340, 0])
    w.connect("Step 3: Recompute from the CRM record", "Step 4: Stamped price list current?")

    qurl = f"={{{{ {crm} }}}}/quotes/{{{{ {EV}.quote_id }}}}"
    w.http("Step 4: Send back to R5.3", "PATCH", qurl,
           body="={{ JSON.stringify({ status: 'back to R5.3', locked: true, return_reason: 'price list ' + $json.stamped + ' replaced by ' + $json.list_version }) }}",
           write=True, pos=[2600, 240])
    w.http("Step 4: Tell the salesperson", "POST", msg_url,
           body=f"={{{{ JSON.stringify({{ to: {Q}.salesperson, subject: 'Quote ' + {EV}.quote_id + ' back to drafting', text: 'The price list it was drafted from is no longer current; mark the opportunity ready to quote again to redraft it.' }}) }}}}",
           write=True, pos=[2860, 240])
    w.connect("Step 4: Stamped price list current?", "Step 4: Send back to R5.3", output=1)
    w.connect("Step 4: Send back to R5.3", "Step 4: Tell the salesperson")

    w.code("Step 5: Rule: Table 5.1", TABLE_JS, mode="runOnceForAllItems", pos=[2600, 0], notes="The rule decides who approves; nobody else can.")
    w.connect("Step 4: Stamped price list current?", "Step 5: Rule: Table 5.1", output=0)
    w.http("Step 6: Lock and record the approver", "PATCH", qurl,
           body="={{ JSON.stringify({ locked: true, approver: $json.approver, deputy: $json.deputy, approval_level: $json.level, deadline_hours: $json.deadline_hours, requested_at: $json.requested_at, escalation: 0 }) }}",
           write=True, pos=[2860, 0], notes="Locked where the CRM can; only approval unlocks sending.")
    t5 = "$('Step 5: Rule: Table 5.1').first().json"
    f3 = "$('Step 3: Recompute from the CRM record').first().json"
    w.http("Step 6: Send the request with Checklist 13.1", "POST", msg_url,
           body=(f"={{{{ JSON.stringify({{ to: {t5}.approver, subject: 'Approve quote ' + {EV}.quote_id + ' revision ' + {EV}.revision, "
                 f"text: 'Value after discount ' + {f3}.value + '; largest line discount ' + {f3}.largest_discount + '%; ' + {t5}.why + '. Record your decision in the CRM within ' + {t5}.deadline_hours + ' hours.', "
                 f"checklist: {CFG}.checklist }}) }}}}"),
           write=True, pos=[3120, 0])
    w.chain("Step 5: Rule: Table 5.1", "Step 6: Lock and record the approver", "Step 6: Send the request with Checklist 13.1")
    w.http("Step 6: Return the quote, locked", "PATCH", qurl,
           body="={{ JSON.stringify({ status: 'returned', locked: true, return_reason: 'approval request not sent' }) }}", write=True, pos=[3380, 160])
    w.http("Step 6: Tell Owen", "POST", msg_url,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.systems_owner, subject: 'Approval request not sent: quote ' + {EV}.quote_id, text: 'The quote is returned and locked; check the messaging connection, then set it awaiting approval again.' }}) }}}}",
           write=True, pos=[3640, 160])
    w.connect("Step 6: Send the request with Checklist 13.1", "Step 6: Return the quote, locked", output=1)
    w.connect("Step 6: Return the quote, locked", "Step 6: Tell Owen")

    w.code("Routing summary", ROUTE_SUMMARY_JS, mode="runOnceForAllItems", pos=[3900, 0])
    for n in ["Step 6: Send the request with Checklist 13.1", "Step 6: Tell Owen", "Step 4: Tell the salesperson"]:
        w.connect(n, "Routing summary")
    w.finish_key("Mark key done", KEY, "done", "$json.decision", pos=[4160, 0])
    w.decision_log("Decision log", f"{EV}.quote_id + ':' + {EV}.revision", "$('Routing summary').first().json.decision",
                   "JSON.stringify($('Routing summary').first().json.rules)", pos=[4420, 0])
    w.chain("Routing summary", "Mark key done", "Decision log")

    w.finish_key("Mark key failed", KEY, "failed", "'write failed: ' + (($json.error && $json.error.message) || 'unknown')", pos=[3900, 400])
    w.exception("Exception queue: write failed", f"{EV}.quote_id", "write failed",
                "'Quote status or request write failed, not retried; route by hand, then release the key'",
                f"{CFG}.approvers.sales_lead.person", pos=[4160, 400])
    for n in ["Step 4: Send back to R5.3", "Step 4: Tell the salesperson", "Step 6: Lock and record the approver",
              "Step 6: Return the quote, locked", "Step 6: Tell Owen"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- step 8: the approver's decision -----------------------------------------------
    w.reserve_key("Step 8: Reserve decision key", DKEY, pos=[1040, 600])
    w.if_("New decision?", "={{ $json.is_new }}", pos=[1300, 600])
    w.noop("Duplicate decision: stop", pos=[1560, 440])
    w.connect("Event", "Step 8: Reserve decision key", output=1)
    w.chain("Step 8: Reserve decision key", "New decision?")
    w.connect("New decision?", "Duplicate decision: stop", output=1)
    w.http("Read the quote (decision)", "GET", f"={{{{ {crm} }}}}/quotes/{{{{ {DV}.quote_id }}}}", write=False, error_output=False, pos=[1560, 600])
    w.http("Read the price list (decision)", "GET", f"={{{{ {crm} }}}}/price_lists/current", write=False, error_output=False, pos=[1820, 600])
    w.code("Step 8: Rule: accept the decision?", DECISION_JS, mode="runOnceForAllItems", pos=[2080, 600])
    w.connect("New decision?", "Read the quote (decision)", output=0)
    w.chain("Read the quote (decision)", "Read the price list (decision)", "Step 8: Rule: accept the decision?")
    w.switch("Step 8: Outcome", "={{ $json.outcome }}", ["approve", "reject", "back", "refuse"], pos=[2340, 600])
    w.connect("Step 8: Rule: accept the decision?", "Step 8: Outcome")
    durl = f"={{{{ {crm} }}}}/quotes/{{{{ {DV}.quote_id }}}}"
    w.http("Step 8: Unlock sending", "PATCH", durl,
           body=f"={{{{ JSON.stringify({{ status: 'approved', locked: false, approved_by: {DV}.by, approved_at: new Date().toISOString(), approved_revision: {DQ}.revision }}) }}}}",
           write=True, pos=[2600, 440])
    w.http("Step 8: Return with the comment", "PATCH", durl,
           body=f"={{{{ JSON.stringify({{ status: 'returned', locked: true, rejected_by: {DV}.by, comment: {DV}.comment || '' }}) }}}}",
           write=True, pos=[2600, 600])
    w.http("Step 8: Send back to R5.3", "PATCH", durl,
           body="={{ JSON.stringify({ status: 'back to R5.3', locked: true, return_reason: $json.reason }) }}", write=True, pos=[2600, 760])
    w.http("Step 8: Tell the salesperson", "POST", msg_url,
           body=f"={{{{ JSON.stringify({{ to: {DQ}.salesperson, subject: 'Quote ' + {DV}.quote_id + ' back to drafting', text: 'The price list changed while it waited for approval; mark the opportunity ready to quote again to redraft it.' }}) }}}}",
           write=True, pos=[2860, 760])
    w.exception("Exception queue: decision not accepted", f"{DV}.quote_id", "decision not accepted", "$json.reason",
                f"{CFG}.approvers.sales_lead.person", pos=[2600, 920])
    for i, n in enumerate(["Step 8: Unlock sending", "Step 8: Return with the comment", "Step 8: Send back to R5.3",
                           "Exception queue: decision not accepted"]):
        w.connect("Step 8: Outcome", n, output=i)
    w.connect("Step 8: Send back to R5.3", "Step 8: Tell the salesperson")
    w.code("Decision summary", DECISION_SUMMARY_JS, mode="runOnceForAllItems", pos=[3120, 600])
    for n in ["Step 8: Unlock sending", "Step 8: Return with the comment", "Step 8: Tell the salesperson", "Exception queue: decision not accepted"]:
        w.connect(n, "Decision summary")
    w.finish_key("Mark decision key done", DKEY, "done", "$json.decision", pos=[3380, 600])
    w.pg("Step 8: Log approver, time and version",
         "INSERT INTO decision_log (recipe, item, decision, rules, approved_by) VALUES ($1, $2, $3, $4::jsonb, $5) RETURNING id",
         args=[json.dumps("R5.4"), f"{DV}.quote_id + ':' + {DQ}.revision", "$('Decision summary').first().json.decision",
               "JSON.stringify($('Decision summary').first().json.rules)", "$('Decision summary').first().json.approver"],
         pos=[3640, 600], notes="Decision log: approver, time and version; never the quote's content.")
    w.chain("Decision summary", "Mark decision key done", "Step 8: Log approver, time and version")
    w.finish_key("Mark decision key failed", DKEY, "failed", "'write failed: ' + (($json.error && $json.error.message) || 'unknown')", pos=[3120, 1000])
    w.exception("Exception queue: decision write failed", f"{DV}.quote_id", "write failed",
                "'Decision write failed, not retried; set the quote by hand, then release the key'", f"{CFG}.approvers.sales_lead.person", pos=[3380, 1000])
    for n in ["Step 8: Unlock sending", "Step 8: Return with the comment", "Step 8: Send back to R5.3", "Step 8: Tell the salesperson"]:
        w.connect(n, "Mark decision key failed", output=1)
    w.connect("Mark decision key failed", "Exception queue: decision write failed")

    # ---- step 7: deadlines ----------------------------------------------------------------
    w.http("Read quotes awaiting approval", "GET", f"={{{{ {crm} }}}}/quotes", query={"_wrap": "1", "status": "awaiting approval"},
           write=False, error_output=False, pos=[1040, 1200])
    w.code("Step 7: Rule: deadline passed?", DEADLINE_JS, mode="runOnceForAllItems", pos=[1300, 1200])
    w.connect("Event", "Read quotes awaiting approval", output=2)
    w.chain("Read quotes awaiting approval", "Step 7: Rule: deadline passed?")
    w.switch("Step 7: Action", "={{ $json.action }}", ["remind", "deputy", "return"], pos=[1560, 1200])
    w.connect("Step 7: Rule: deadline passed?", "Step 7: Action")
    pq = "$('Step 7: Rule: deadline passed?').item.json"
    w.http("Step 7: Remind the approver", "POST", msg_url,
           body="={{ JSON.stringify({ to: $json.approver, subject: 'Reminder: approve quote ' + $json.quote_id, text: 'The response deadline has passed. ' + $('Config').first().json.checklist }) }}",
           write=True, pos=[1820, 1060])
    w.http("Step 7: Ask the deputy", "POST", msg_url,
           body="={{ JSON.stringify({ to: $json.deputy, subject: 'Please approve quote ' + $json.quote_id + ' as deputy', text: 'The approver has not decided by twice the deadline. ' + $('Config').first().json.checklist }) }}",
           write=True, pos=[1820, 1200])
    w.http("Step 7: Return the quote, locked", "PATCH", f"={{{{ {crm} }}}}/quotes/{{{{ $json.quote_id }}}}",
           body="={{ JSON.stringify({ status: 'returned', locked: true, escalation: 3, return_reason: 'no decision by three times the deadline' }) }}",
           write=True, pos=[1820, 1340])
    for i, n in enumerate(["Step 7: Remind the approver", "Step 7: Ask the deputy", "Step 7: Return the quote, locked"]):
        w.connect("Step 7: Action", n, output=i)
    w.http("Step 7: Record the escalation", "PATCH", f"={{{{ {crm} }}}}/quotes/{{{{ {pq}.quote_id }}}}",
           body=f"={{{{ JSON.stringify({{ escalation: {pq}.stage }}) }}}}", write=True, pos=[2080, 1130])
    w.connect("Step 7: Remind the approver", "Step 7: Record the escalation")
    w.connect("Step 7: Ask the deputy", "Step 7: Record the escalation")
    w.http("Step 7: Tell Ben", "POST", msg_url,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.approvers.sales_lead.person, subject: 'Quote ' + {pq}.quote_id + ' returned: no decision', text: 'No decision by three times the deadline; the quote is returned, locked.' }}) }}}}",
           write=True, pos=[2080, 1340])
    w.connect("Step 7: Return the quote, locked", "Step 7: Tell Ben")
    w.exception("Exception queue: deadline action failed", f"{pq}.quote_id", "deadline action failed",
                "'A reminder, deputy request or return failed, not retried; act on the quote by hand'",
                f"{CFG}.approvers.sales_lead.person", pos=[2340, 1500])
    for n in ["Step 7: Remind the approver", "Step 7: Ask the deputy", "Step 7: Return the quote, locked",
              "Step 7: Record the escalation", "Step 7: Tell Ben"]:
        w.connect(n, "Exception queue: deadline action failed", output=1)

    # ---- weekly backstop -------------------------------------------------------------------
    w.http("Read quotes sent", "GET", f"={{{{ {crm} }}}}/quotes", query={"_wrap": "1", "status": "sent"},
           write=False, error_output=False, pos=[1040, 1700])
    w.code("Rule: sent without approval?", BACKSTOP_JS, mode="runOnceForAllItems", pos=[1300, 1700])
    w.exception("Exception queue: sent unapproved", "$json.quote_id", "quote sent unapproved",
                "'Quote ' + $json.quote_id + ' revision ' + $json.revision + ' was sent without approval of that revision'",
                f"{CFG}.approvers.sales_lead.person", pos=[1560, 1700])
    w.http("Backstop: Tell Ben", "POST", msg_url,
           body=(f"={{{{ JSON.stringify({{ to: {CFG}.approvers.sales_lead.person, subject: 'Quote sent without approval', "
                 "text: 'Quote ' + $('Rule: sent without approval?').item.json.quote_id + ' was sent unapproved; call the customer.' }) }}"),
           write=True, error_output=False, pos=[1820, 1700])
    w.connect("Event", "Read quotes sent", output=3)
    w.chain("Read quotes sent", "Rule: sent without approval?", "Exception queue: sent unapproved", "Backstop: Tell Ben")
    return w
