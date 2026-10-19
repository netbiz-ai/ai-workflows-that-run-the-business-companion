"""R8.2 Prepare and send monthly statements for trade accounts: rules only, no AI step.

Source: book Chapter 8, recipe R8.2, build steps 1 to 9 (recipes/R8.2/build-spec.md).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "n8n"))
from wf import V, Workflow  # noqa: E402

S = "Step 1: First working day of the month"
RUN = "Step 9: Run again after a release or restart"
DEC = "Step 8: Aisha decides on the batch"
CFG = "$('Config').first().json"
B = "$('Rules: steps 3 to 6').item.json"
ST = "$('Step 8: One item per statement').item.json"
SAVE_NOTE = "Book build note: in n8n, set the workflow's \"Save successful production executions\" to \"Do not save\"."

CUTOFF_JS = r"""
// The statement month's cut-off: the last month-end, unless Config names one.
const cutoffFor = (cfg) => {
  if (cfg.cutoff) return String(cfg.cutoff).slice(0, 10);
  const n = new Date();
  return new Date(Date.UTC(n.getUTCFullYear(), n.getUTCMonth(), 0)).toISOString().slice(0, 10);
};
"""

DAY_JS = r"""
// Step 1: the schedule runs each weekday; only the month's first working day goes on. A run again always goes on.
if (!$('Step 1: First working day of the month').isExecuted) return [{ json: { go: true } }];
const n = new Date();
let first = true;
for (let d = 1; d < n.getUTCDate(); d++) {
  const wd = new Date(Date.UTC(n.getUTCFullYear(), n.getUTCMonth(), d)).getUTCDay();
  if (wd !== 0 && wd !== 6) { first = false; break; }
}
return [{ json: { go: first } }];
"""

GATE_JS = CUTOFF_JS + r"""
// Step 2: both exports saved, at the one expected month-end cut-off.
const cfg = $('Config').first().json;
const ok = n => { const a = $(n).all(0); return a.length ? a[0].json : null; };
const cutoff = cutoffFor(cfg);
const problems = [];
for (const [name, node] of [['balances', 'Step 2: Read the balances export'], ['open items', 'Step 2: Read the open-items export']]) {
  const e = ok(node);
  if (!e || !Array.isArray(e.rows)) problems.push(name + ' export missing');
  else if (String(e.cutoff || '').slice(0, 10) !== cutoff) problems.push(name + ' export cut-off ' + e.cutoff + ', expected ' + cutoff);
}
return [{ json: { run: problems.length === 0, problems, cutoff, month: cutoff.slice(0, 7) } }];
"""

RULES_JS = r"""
// Steps 3 to 6 of the book's R8.2, in order. Returns one batch for Aisha's approval.
const cfg = $('Config').first().json;
const g = $('Step 2: Rule: exports present, one cut-off?').first().json;
const balances = $('Step 2: Read the balances export').first().json.rows || [];
const items = $('Step 2: Read the open-items export').first().json.rows || [];
const disputed = new Set(($('Step 4: Read the dispute list').first().json.items || []).filter(d => d.invoice).map(d => String(d.invoice)));
const crm = Object.fromEntries(($('Read CRM contacts (for step 6)').first().json.items || []).map(a => [String(a.id), a]));
const sent = new Set($('Step 5: Read statements already sent').all().map(i => i.json.key).filter(Boolean));
const cents = x => Math.round(Number(x) * 100);
const money = c => (c / 100).toFixed(2);
const fill = (s, f) => String(s || '').replace(/\{\{(\w+)\}\}/g, (_, k) => (k in f ? String(f[k]) : ''));

const accounts = [...new Set([...balances.map(b => String(b.account)), ...items.map(i => String(i.account))])];
const statements = [], held = [], skipped = [];
for (const acc of accounts) {
  // Step 5: skip an account plus statement month already sent.
  if (sent.has(acc + ':' + g.month)) { skipped.push(acc); continue; }
  const b = balances.find(x => String(x.account) === acc);
  const its = items.filter(i => String(i.account) === acc);
  const balance = b ? cents(b.balance) : 0;
  const openTotal = its.reduce((s, i) => s + cents(i.amount), 0);
  // Step 3: any difference, even a cent, holds the account.
  if (balance !== openTotal) {
    held.push({ account: acc, balance: balance / 100, open_items_total: openTotal / 100, difference: (balance - openTotal) / 100 });
    continue;
  }
  // Step 4: a disputed item is "in dispute, not due", outside the total; an account in credit shows nothing due.
  const lines = its.map(i => ({ item: String(i.item), type: i.type || 'invoice', date: i.date || null, due_date: i.due_date || null,
    amount: cents(i.amount) / 100, status: disputed.has(String(i.item)) ? 'in dispute, not due' : 'due' }));
  const dueCents = lines.filter(l => l.status === 'due').reduce((s, l) => s + cents(l.amount), 0);
  const totalCents = balance <= 0 || dueCents <= 0 ? 0 : dueCents;
  // Step 6: items, total due, how to pay, where to ask.
  const a = crm[acc] || {};
  const text = [
    'Statement for ' + (a.name || acc) + ', at ' + g.cutoff,
    '',
    ...lines.map(l => [l.date, l.type, l.item, money(cents(l.amount))].filter(Boolean).join('  ') + (l.status === 'due' ? '' : '  (in dispute, not due)')),
    '',
    totalCents > 0 ? 'Total due: ' + money(totalCents) : (balance < 0 ? 'Your account is in credit: nothing is due.' : 'Nothing is due.'),
    'How to pay: ' + cfg.how_to_pay,
    'Questions about this statement: ' + cfg.where_to_ask,
  ].join('\n');
  statements.push({ account: acc, account_name: a.name || '', to: a.contact_email || '', balance: balance / 100, lines,
    total_due: totalCents / 100, subject: fill(cfg.statement_subject, { month: g.month, account_name: a.name || acc }), text });
}
const pick = statements.slice().sort(() => Math.random() - 0.5).slice(0, 5);
return [{ json: { id: 'statements-' + g.month, month: g.month, cutoff: g.cutoff, status: 'pending', approver: cfg.ar_lead,
  count: statements.length, total_due: statements.reduce((s, x) => s + cents(x.total_due), 0) / 100,
  held, samples: pick.map(s => ({ account: s.account, total_due: s.total_due, text: s.text })),
  skipped: skipped.length, statements }, pairedItem: 0 }];
"""

FIND_JS = CUTOFF_JS + r"""
// Step 8: Aisha's decision is on this month's batch.
const month = cutoffFor($('Config').first().json).slice(0, 7);
return [{ json: { id: 'statements-' + month, month } }];
"""

SPLIT_JS = r"""
// Step 8: one item per approved statement, each with its key (account plus statement month).
const b = $('Step 8: Read the batch').first().json;
return (b.statements || []).map(s => ({ json: Object.assign({}, s, { month: b.month, key: s.account + ':' + b.month }), pairedItem: 0 }));
"""


def build() -> Workflow:
    w = Workflow("R8.2", "R8.2 Prepare and send monthly statements for trade accounts")
    w.node(S, "n8n-nodes-base.scheduleTrigger", V["schedule"],
           {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1, "triggerAtDay": [1, 2, 3, 4, 5], "triggerAtHour": 9}]}},
           pos=[0, 0], notes="Each weekday; set the hour to after both month-end exports are saved. " + SAVE_NOTE)
    w.webhook(RUN, "r8-2-run-again",
              "Call this to run again: after finance saves a late export, after a failed send (Owen restarts), or when Aisha releases a corrected held account (step 9). Body: {}.",
              pos=[0, 200])
    w.webhook(DEC, "r8-2-batch-decision",
              "Your approvals tool calls this when Aisha approves or rejects the batch. Body: {approved, by}.", pos=[0, 600])
    w.config("Config", {
        "sharepoint_url": "https://<your SharePoint lists API>",
        "crm_url": "https://<your CRM API>",
        "mail_url": "https://<your AR mailbox API>",
        "approvals_url": "https://<your approvals API>",
        "messaging_url": "https://<your messaging API>",
        "ar_mailbox": "<your shared AR mailbox>",
        "ar_lead": "<your AR lead, who approves the batch>",
        "cutoff": "",
        "statement_subject": "<your statement subject; merge fields {{month}} and {{account_name}}>",
        "how_to_pay": "<how your customers pay>",
        "where_to_ask": "<where a customer asks about a statement>",
    }, pos=[260, 300])
    for t in (S, RUN, DEC):
        w.connect(t, "Config")
    w.if_("Batch decision?", f"={{{{ $('{DEC}').isExecuted }}}}", pos=[520, 300],
          notes="Config cutoff: leave blank for the last month-end; name a date only to rerun an earlier month.")
    w.connect("Config", "Batch decision?")

    # ---- steps 1 and 2 ---------------------------------------------------------------
    w.code("Step 1: Rule: first working day, or a run again?", DAY_JS, mode="runOnceForAllItems", pos=[780, 200])
    w.if_("Go?", "={{ $json.go }}", pos=[1040, 200])
    w.noop("Not the first working day", pos=[1300, 40])
    w.connect("Batch decision?", "Step 1: Rule: first working day, or a run again?", output=1)
    w.connect("Step 1: Rule: first working day, or a run again?", "Go?")
    w.connect("Go?", "Not the first working day", output=1)
    w.http("Step 2: Read the balances export", "GET", f"={{{{ {CFG}.sharepoint_url }}}}/exports/balances", write=False, pos=[1300, 200])
    w.http("Step 2: Read the open-items export", "GET", f"={{{{ {CFG}.sharepoint_url }}}}/exports/open-items", write=False, pos=[1560, 200],
           notes="Invoices and credit notes, not unapplied payments.")
    w.code("Step 2: Rule: exports present, one cut-off?", GATE_JS, mode="runOnceForAllItems", pos=[1820, 200])
    w.connect("Go?", "Step 2: Read the balances export", output=0)
    for o in (0, 1):
        w.connect("Step 2: Read the balances export", "Step 2: Read the open-items export", output=o)
        w.connect("Step 2: Read the open-items export", "Step 2: Rule: exports present, one cut-off?", output=o)
    w.if_("Exports current?", "={{ $json.run }}", pos=[2080, 200])
    w.connect("Step 2: Rule: exports present, one cut-off?", "Exports current?")
    gate = "$('Step 2: Rule: exports present, one cut-off?').item.json"
    w.decision_log("Step 2: Decision log: no run", f"'statements ' + {gate}.month", "'no run'",
                   f"JSON.stringify({{ problems: {gate}.problems }})", pos=[2340, 440])
    w.http("Step 2: Alert Aisha", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: [{CFG}.ar_lead], subject: 'Statements for ' + {gate}.month + ': nothing built', text: {gate}.problems.join('; ') }}) }}}}",
           write=True, error_output=False, pos=[2600, 440])
    w.connect("Exports current?", "Step 2: Decision log: no run", output=1)
    w.connect("Step 2: Decision log: no run", "Step 2: Alert Aisha")

    # ---- steps 3 to 7 ------------------------------------------------------------------
    w.http("Step 4: Read the dispute list", "GET", f"={{{{ {CFG}.sharepoint_url }}}}/disputes",
           query={"_wrap": "1", "status": "open"}, write=False, error_output=False, pos=[2340, 200])
    w.http("Read CRM contacts (for step 6)", "GET", f"={{{{ {CFG}.crm_url }}}}/accounts",
           query={"_wrap": "1"}, write=False, error_output=False, pos=[2600, 200])
    w.pg("Step 5: Read statements already sent", "SELECT key FROM key_log WHERE recipe = 'R8.2' AND key LIKE '%:' || $1",
         args=[f"{gate}.month"], pos=[2860, 200])
    w.code("Rules: steps 3 to 6", RULES_JS, mode="runOnceForAllItems", pos=[3120, 200],
           notes="Rules decide; there is no AI step in R8.2. Nothing fixes a difference: a held account waits for Aisha.")
    w.connect("Exports current?", "Step 4: Read the dispute list", output=0)
    w.chain("Step 4: Read the dispute list", "Read CRM contacts (for step 6)", "Step 5: Read statements already sent", "Rules: steps 3 to 6")
    w.if_("Anything to approve?", f"={{{{ {B}.count > 0 || {B}.held.length > 0 }}}}", pos=[3380, 200])
    w.noop("Nothing to build", pos=[3640, 360], notes="Every account's statement for this month was sent.")
    w.connect("Rules: steps 3 to 6", "Anything to approve?")
    w.connect("Anything to approve?", "Nothing to build", output=1)
    w.http("Step 7: Send Aisha one approval", "PUT", f"={{{{ {CFG}.approvals_url }}}}/requests/{{{{ {B}.id }}}}",
           body=f"={{{{ JSON.stringify({B}) }}}}", write=True, pos=[3640, 120],
           notes="Count, total due, each held account's difference and five random statements; the batch waits for her decision.")
    w.decision_log("Step 7: Decision log: batch", f"'statements ' + {B}.month", "'batch sent for approval'",
                   f"JSON.stringify({{ count: {B}.count, total_due: {B}.total_due, held: {B}.held, skipped: {B}.skipped }})",
                   pos=[3900, 120])
    w.connect("Anything to approve?", "Step 7: Send Aisha one approval", output=0)
    w.connect("Step 7: Send Aisha one approval", "Step 7: Decision log: batch")
    w.exception("Exception queue: approval write failed", f"{B}.id", "write failed",
                "'The batch approval was not written; run again'", f"{CFG}.ar_lead", pos=[3900, 300])
    w.connect("Step 7: Send Aisha one approval", "Exception queue: approval write failed", output=1)

    # ---- step 8: Aisha's decision --------------------------------------------------------
    w.code("Step 8: Find this month's batch", FIND_JS, mode="runOnceForAllItems", pos=[780, 600])
    w.http("Step 8: Read the batch", "GET",
           f"={{{{ {CFG}.approvals_url }}}}/requests/{{{{ $('Step 8: Find this month\\'s batch').item.json.id }}}}",
           write=False, error_output=False, pos=[1040, 600])
    w.if_("Step 8: Approved?", f"={{{{ $('{DEC}').item.json.body.approved === true }}}}", pos=[1300, 600])
    w.connect("Batch decision?", "Step 8: Find this month's batch", output=0)
    w.chain("Step 8: Find this month's batch", "Step 8: Read the batch", "Step 8: Approved?")
    w.decision_log("Step 8: Decision log: rejected", "'statements ' + $('Step 8: Read the batch').item.json.month",
                   "'batch rejected; nothing sent'", f"JSON.stringify({{ by: $('{DEC}').item.json.body.by || null }})", pos=[1560, 800])
    w.connect("Step 8: Approved?", "Step 8: Decision log: rejected", output=1)
    w.code("Step 8: One item per statement", SPLIT_JS, mode="runOnceForAllItems", pos=[1560, 600])
    w.connect("Step 8: Approved?", "Step 8: One item per statement", output=0)
    w.reserve_key("Step 5: Reserve key", f"{ST}.key", pos=[1820, 600])
    w.if_("New key?", "={{ $json.is_new }}", pos=[2080, 600])
    w.noop("Duplicate: skip", pos=[2340, 460], notes="This account's statement for the month was sent.")
    w.chain("Step 8: One item per statement", "Step 5: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: skip", output=1)
    w.http("Step 8: Send the statement", "POST", f"={{{{ {CFG}.mail_url }}}}/outbox",
           body=f"={{{{ JSON.stringify({{ from: {CFG}.ar_mailbox, to: {ST}.to, subject: {ST}.subject, text: {ST}.text }}) }}}}",
           write=True, pos=[2340, 600], notes="A write: never retried.")
    w.connect("New key?", "Step 8: Send the statement", output=0)
    w.finish_key("Mark key done", f"{ST}.key", "done", "'sent'", pos=[2600, 600])
    w.decision_log("Step 8: Decision log: sent", f"{ST}.account", f"'sent statement ' + {ST}.month",
                   f"JSON.stringify({{ month: {ST}.month, balance: {ST}.balance, total_due: {ST}.total_due, held: false, by: $('{DEC}').item.json.body.by || null }})",
                   pos=[2860, 600])
    w.chain("Step 8: Send the statement", "Mark key done", "Step 8: Decision log: sent")
    w.pg("Release key: logged unsent", "DELETE FROM key_log WHERE recipe = $1 AND key = $2 RETURNING key",
         args=[json.dumps("R8.2"), f"{ST}.key"], pos=[2600, 800], notes="Unsent: the next run includes this account again.")
    w.connect("Step 8: Send the statement", "Release key: logged unsent", output=1)
    w.exception("Exception queue: send failed", f"{ST}.account", "send failed",
                f"'Statement for ' + {ST}.month + ' not sent; Owen restarts the run'", f"{CFG}.ar_lead", pos=[2860, 800])
    w.decision_log("Decision log: unsent", f"{ST}.account", f"'unsent statement ' + {ST}.month",
                   f"JSON.stringify({{ month: {ST}.month, balance: {ST}.balance }})", pos=[3120, 800])
    w.chain("Release key: logged unsent", "Exception queue: send failed", "Decision log: unsent")
    return w
