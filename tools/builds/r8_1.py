"""R8.1 Send staged overdue reminders that stop on payment or dispute: rules only, no AI step.

Source: book Chapter 8, recipe R8.1, Table 8.1 and build steps 1 to 10 (recipes/R8.1/build-spec.md).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "n8n"))
from wf import V, Workflow  # noqa: E402

M = "Step 1: Each working morning after the export is due"
A = "Step 9: Aisha decides on a final notice"
CFG = "$('Config').first().json"
R = "$('Rules: steps 3 to 5').item.json"
CHECK = "$('Step 8: Rule: number, amount and no blank field').item.json"

GATE_JS = r"""
// Step 2: today's export, and where R8.3 runs its mailbox check today; otherwise no run.
const cfg = $('Config').first().json;
const today = new Date().toISOString().slice(0, 10);
// A read that failed has no item on its success output.
const ok = n => { const a = $(n).all(0); return a.length ? a[0].json : null; };
const exp = ok("Step 2: Read today's export");
const problems = [];
if (!exp || exp.error || !Array.isArray(exp.rows)) problems.push('export missing');
else if (String(exp.saved_at || '').slice(0, 10) !== today) problems.push('export old: saved ' + exp.saved_at);
let hold_final = false;
if (cfg.r8_3_runs) {
  const st = ok('Step 2: Read the mailbox check (R8.3)');
  if (!st || st.error || String(st.last_check || '').slice(0, 10) !== today) problems.push('R8.3 logged no mailbox check today');
  hold_final = Number($('Step 2: Count unreviewed unlinked items (R8.3)').first().json.count || 0) > 0;
}
return [{ json: { run: problems.length === 0, problems, hold_final, today } }];
"""

RULES_JS = r"""
// Steps 3 to 5 of the book's R8.1, in order; step 9 reruns 4 and 5 before an approved final notice sends.
const cfg = $('Config').first().json;
const A = 'Step 9: Aisha decides on a final notice';
const decision = $(A).isExecuted ? $(A).first().json.body : null;
const gate = $('Step 2: Rule: export and intake current?').first().json;
const today = gate.today;
const rows = $("Step 2: Read today's export").first().json.rows || [];
const list = Object.fromEntries(($('Step 3: Read the reminder list').first().json.items || []).map(r => [String(r.id), r]));
const disputes = ($('Step 5: Read the dispute list').first().json.items || []).filter(d => !d.until || d.until >= today);
const holds = ($('Step 5: Read the hold list').first().json.items || []).filter(h => !h.until || h.until >= today);
const crm = Object.fromEntries(($('Read CRM contacts (for step 7)').first().json.items || []).map(a => [String(a.id), a]));
const sd = cfg.stage_days;
const day = (d, n) => new Date(Date.parse(d + 'T00:00:00Z') + Number(n) * 86400000).toISOString().slice(0, 10);
const covers = (e, r) => e.invoice ? String(e.invoice) === String(r.invoice) : String(e.account) === String(r.account);

// Table 8.1: a new invoice starts at the courtesy reminder, or at the first overdue reminder once its due date has passed.
function firstStage(r) {
  return today < r.due_date
    ? { stage: 'courtesy reminder', due_on: day(r.due_date, -sd.courtesy_before_due) }
    : { stage: 'first overdue reminder', due_on: day(r.due_date, sd.first_after_due) };
}
function nextStage(stage, r) {
  if (stage === 'courtesy reminder') return { stage: 'first overdue reminder', due_on: day(r.due_date, sd.first_after_due) };
  if (stage === 'first overdue reminder') return { stage: 'second overdue reminder', due_on: day(today, sd.second_after_first) };
  if (stage === 'second overdue reminder') return { stage: 'final notice', due_on: day(today, sd.final_after_second) };
  return { stage: 'handoff', due_on: today };
}
function stopFor(r) {
  const amount = Number(r.amount), open = Number(r.open_amount);
  const chase = holds.some(h => h.type === 'chase' && covers(h, r));
  // Step 4: paid, part-paid or a negative amount stops; a part payment or negative amount goes to Aisha.
  if (open === 0) return { reason: 'paid', tell: false };
  if (open < 0) return { reason: 'negative open amount', tell: true };
  if (open < amount && !chase) return { reason: 'part-paid', tell: true };
  // Step 5: an open dispute, or a hold other than "chase", on the invoice or its account.
  const d = disputes.find(e => covers(e, r));
  if (d) return { reason: (d.invoice ? 'open dispute' : 'open dispute on the account') + (d.set_by ? ', set by ' + d.set_by : ''), tell: false };
  const h = holds.find(e => e.type !== 'chase' && covers(e, r));
  if (h) return { reason: 'hold: ' + (h.type || 'hold') + (h.set_by ? ', set by ' + h.set_by : ''), tell: false };
  return null;
}

const out = [];
const emit = (r, o) => {
  const a = crm[String(r.account)] || {};
  out.push({ json: Object.assign({ invoice: String(r.invoice), account: String(r.account), amount: r.amount, open_amount: r.open_amount,
    due_date: r.due_date, contact_name: a.contact_name || '', contact_email: a.contact_email || '', account_name: a.name || '' }, o), pairedItem: 0 });
};
const targets = decision ? rows.filter(r => String(r.invoice) === String(decision.invoice)) : rows;
if (decision && !targets.length) {
  out.push({ json: { outcome: 'wait', invoice: String(decision.invoice), decision: "final notice not sent: invoice not in today's export" }, pairedItem: 0 });
}
for (const r of targets) {
  const rec = list[String(r.invoice)];
  const cur = rec ? { stage: rec.stage, due_on: rec.due_on } : firstStage(r);
  if (cur.stage === 'handoff') continue;
  const base = { id: String(r.invoice), invoice: String(r.invoice), account: String(r.account), stage: cur.stage, due_on: cur.due_on };
  const s = stopFor(r);
  const stopItem = (prefix) => emit(r, { outcome: 'stop', stage: cur.stage, reason: s.reason, tell: s.tell, decision: prefix + s.reason,
    record: Object.assign({}, base, { status: 'stopped', reason: s.reason, stopped_on: today }) });
  const sendItem = (decisionText) => {
    const next = nextStage(cur.stage, r);
    emit(r, { outcome: 'send', stage: cur.stage, key: r.invoice + ':' + cur.stage, decision: decisionText, next,
      approved_by: decision ? (decision.by || null) : null,
      record: Object.assign({}, base, next, { status: 'active', reason: null, last_sent: today, last_stage: cur.stage }) });
  };
  if (decision) {
    // Step 9: an approved final notice sends only if steps 2, 4 and 5 still pass.
    if (cur.stage !== 'final notice') { emit(r, { outcome: 'wait', stage: cur.stage, decision: 'final notice not sent: none awaiting approval' }); continue; }
    if (s) { stopItem('final notice not sent; stopped: '); continue; }
    if (gate.hold_final) { emit(r, { outcome: 'wait', stage: cur.stage, decision: 'final notice held: an unlinked reply over a day old is unreviewed' }); continue; }
    sendItem('sent final notice');
    continue;
  }
  if (s) {
    if (!rec || rec.status !== 'stopped' || rec.reason !== s.reason) stopItem('stopped: ');
    continue;
  }
  if (cur.due_on > today) {
    // Step 3: a new invoice is added at its first stage; a stop that has ended resumes at its paused stage.
    if (!rec || rec.status === 'stopped') emit(r, { outcome: 'list', stage: cur.stage, record: Object.assign({}, base, { status: 'active', reason: null }) });
    continue;
  }
  if (cur.stage === 'final notice') {
    if (gate.hold_final) emit(r, { outcome: 'wait', stage: cur.stage, decision: 'final notice held: an unlinked reply over a day old is unreviewed' });
    else emit(r, { outcome: 'final', stage: cur.stage, decision: 'final notice: approval requested', approval_id: r.invoice + '-' + today,
      record: Object.assign({}, base, { status: 'active', reason: null }) });
    continue;
  }
  sendItem('sent ' + cur.stage);
}
return out;
"""

FILL_JS = r"""
// Step 7: fill the stage's template from the export and the CRM only.
const cfg = $('Config').first().json;
const r = $('Rules: steps 3 to 5').item.json;
const t = (cfg.templates || {})[r.stage] || {};
const fields = { invoice: r.invoice, amount: Number(r.open_amount).toFixed(2), due_date: r.due_date,
  contact_name: r.contact_name, account_name: r.account_name };
const used = [...new Set(((t.subject || '') + ' ' + (t.text || '')).match(/\{\{(\w+)\}\}/g) || [])].map(s => s.slice(2, -2));
const fill = s => String(s || '').replace(/\{\{(\w+)\}\}/g, (_, k) => (k in fields ? String(fields[k] ?? '') : ''));
return { json: { to: r.contact_email, subject: fill(t.subject), text: fill(t.text), used, fields, template_version: cfg.template_version } };
"""

CHECK_JS = r"""
// Step 8: the number and amount shown match the export, and no field is blank; otherwise hold.
const r = $('Rules: steps 3 to 5').item.json;
const m = $json;
const problems = [];
if (!m.to) problems.push('no AR contact in the CRM');
if (!m.subject || !m.text) problems.push('no template for ' + r.stage);
for (const k of m.used) {
  if (!(k in m.fields)) problems.push('unknown field ' + k);
  else if (String(m.fields[k] ?? '').trim() === '') problems.push('blank field ' + k);
}
const shown = m.subject + '\n' + m.text;
if (!shown.includes(r.invoice)) problems.push('invoice number not shown');
if (!shown.includes(Number(r.open_amount).toFixed(2))) problems.push('amount does not match the export');
return { json: Object.assign({}, m, { ok: problems.length === 0, problems }) };
"""


def build() -> Workflow:
    w = Workflow("R8.1", "R8.1 Send staged overdue reminders that stop on payment or dispute")
    w.node(M, "n8n-nodes-base.scheduleTrigger", V["schedule"],
           {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1, "triggerAtDay": [1, 2, 3, 4, 5], "triggerAtHour": 7}]}},
           pos=[0, 0], notes="Monday to Friday; set the hour to after your open-invoice export is due.")
    w.webhook(A, "r8-1-final-notice-decision",
              "Your approvals tool calls this when Aisha decides on a final notice. Body: {invoice, approved, by}.", pos=[0, 400])
    w.config("Config", {
        "sharepoint_url": "https://<your SharePoint lists API>",
        "crm_url": "https://<your CRM API>",
        "mail_url": "https://<your AR mailbox API>",
        "approvals_url": "https://<your approvals API>",
        "messaging_url": "https://<your messaging API>",
        "ar_mailbox": "<your shared AR mailbox>",
        "ar_lead": "<your AR lead, who approves final notices>",
        "stage_days": {"courtesy_before_due": "<days before due>", "first_after_due": "<days after due>",
                       "second_after_first": "<days after the first>", "final_after_second": "<days after the second>"},
        "templates": {
            "courtesy reminder": {"subject": "<your reviewed subject>", "text": "<your reviewed courtesy reminder; merge fields {{invoice}}, {{amount}}, {{due_date}}, {{contact_name}}, {{account_name}}>"},
            "first overdue reminder": {"subject": "<your reviewed subject>", "text": "<your reviewed first overdue reminder>"},
            "second overdue reminder": {"subject": "<your reviewed subject>", "text": "<your reviewed second overdue reminder>"},
            "final notice": {"subject": "<your reviewed subject>", "text": "<your reviewed final notice>"},
        },
        "template_version": "<your template version>",
        "r8_3_runs": False,
        "unlinked_hold_hours": 24,
    }, pos=[260, 200])
    w.connect(M, "Config")
    w.connect(A, "Config")

    w.if_("Final-notice decision?", f"={{{{ $('{A}').isExecuted }}}}", pos=[520, 200])
    w.if_("Step 9: Approved?", f"={{{{ $('{A}').item.json.body.approved === true }}}}", pos=[780, 400])
    w.decision_log("Step 9: Decision log: not approved", f"String($('{A}').item.json.body.invoice)",
                   "'final notice not approved; waits a day'", f"JSON.stringify({{ by: $('{A}').item.json.body.by || null }})", pos=[1040, 560])
    w.connect("Config", "Final-notice decision?")
    w.connect("Final-notice decision?", "Step 9: Approved?", output=0)
    w.connect("Step 9: Approved?", "Step 9: Decision log: not approved", output=1)

    # ---- step 2: export and intake current --------------------------------------
    w.http("Step 2: Read today's export", "GET", f"={{{{ {CFG}.sharepoint_url }}}}/exports/open-invoices",
           write=False, pos=[1040, 200], notes="A missing export arrives on the error output and fails the step 2 rule.")
    w.connect("Final-notice decision?", "Step 2: Read today's export", output=1)
    w.connect("Step 9: Approved?", "Step 2: Read today's export", output=0)
    w.if_("Where R8.3 runs?", f"={{{{ {CFG}.r8_3_runs === true }}}}", pos=[1300, 200])
    w.connect("Step 2: Read today's export", "Where R8.3 runs?", output=0)
    w.connect("Step 2: Read today's export", "Where R8.3 runs?", output=1)
    w.http("Step 2: Read the mailbox check (R8.3)", "GET", f"={{{{ {CFG}.sharepoint_url }}}}/status/mailbox-check",
           write=False, pos=[1560, 80])
    w.pg("Step 2: Count unreviewed unlinked items (R8.3)",
         "SELECT count(*)::int AS count FROM exception_queue WHERE recipe = 'R8.3' AND reason = 'unlinked item' "
         "AND status = 'open' AND created_at < now() - make_interval(hours => $1::int)",
         args=[f"{CFG}.unlinked_hold_hours"], pos=[1820, 80])
    w.code("Step 2: Rule: export and intake current?", GATE_JS, mode="runOnceForAllItems", pos=[2080, 200])
    w.connect("Where R8.3 runs?", "Step 2: Read the mailbox check (R8.3)", output=0)
    w.connect("Step 2: Read the mailbox check (R8.3)", "Step 2: Count unreviewed unlinked items (R8.3)", output=0)
    w.connect("Step 2: Read the mailbox check (R8.3)", "Step 2: Count unreviewed unlinked items (R8.3)", output=1)
    w.connect("Step 2: Count unreviewed unlinked items (R8.3)", "Step 2: Rule: export and intake current?")
    w.connect("Where R8.3 runs?", "Step 2: Rule: export and intake current?", output=1)
    w.if_("Run today?", "={{ $json.run }}", pos=[2340, 200])
    w.connect("Step 2: Rule: export and intake current?", "Run today?")
    gate = "$('Step 2: Rule: export and intake current?').item.json"
    w.decision_log("Step 2: Decision log: no run", f"'run ' + {gate}.today", "'no run'",
                   f"JSON.stringify({{ problems: {gate}.problems }})", pos=[2600, 440])
    w.http("Step 2: Alert Aisha", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: [{CFG}.ar_lead], subject: 'R8.1 reminders: no run today', text: 'Nothing was sent: ' + {gate}.problems.join('; ') }}) }}}}",
           write=True, error_output=False, pos=[2860, 440], notes="Ends cleanly: nothing is sent.")
    w.connect("Run today?", "Step 2: Decision log: no run", output=1)
    w.connect("Step 2: Decision log: no run", "Step 2: Alert Aisha")

    # ---- steps 3 to 5 --------------------------------------------------------------
    w.http("Step 3: Read the reminder list", "GET", f"={{{{ {CFG}.sharepoint_url }}}}/reminders",
           query={"_wrap": "1"}, write=False, error_output=False, pos=[2600, 200])
    w.http("Step 5: Read the dispute list", "GET", f"={{{{ {CFG}.sharepoint_url }}}}/disputes",
           query={"_wrap": "1", "status": "open"}, write=False, error_output=False, pos=[2860, 200])
    w.http("Step 5: Read the hold list", "GET", f"={{{{ {CFG}.sharepoint_url }}}}/holds",
           query={"_wrap": "1"}, write=False, error_output=False, pos=[3120, 200])
    w.http("Read CRM contacts (for step 7)", "GET", f"={{{{ {CFG}.crm_url }}}}/accounts",
           query={"_wrap": "1"}, write=False, error_output=False, pos=[3380, 200])
    w.code("Rules: steps 3 to 5", RULES_JS, mode="runOnceForAllItems", pos=[3640, 200],
           notes="Stop rules run before any send; there is no AI step in R8.1.")
    w.connect("Run today?", "Step 3: Read the reminder list", output=0)
    w.chain("Step 3: Read the reminder list", "Step 5: Read the dispute list", "Step 5: Read the hold list",
            "Read CRM contacts (for step 7)", "Rules: steps 3 to 5")
    w.switch("Outcome", "={{ $json.outcome }}", ["send", "final", "stop", "list", "wait"], pos=[3900, 200])
    w.connect("Rules: steps 3 to 5", "Outcome")

    sp = f"{CFG}.sharepoint_url"
    rec_url = f"={{{{ {sp} }}}}/reminders/{{{{ {R}.invoice }}}}"
    rec_body = f"={{{{ JSON.stringify({R}.record) }}}}"

    # ---- send and final paths: steps 6 to 9 ---------------------------------------
    w.reserve_key("Step 6: Reserve key", f"{R}.key", pos=[4160, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[4420, 0])
    w.noop("Duplicate: skip", pos=[4680, -160], notes="This invoice number plus stage is in the key log.")
    w.connect("Outcome", "Step 6: Reserve key", output=0)
    w.connect("Step 6: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: skip", output=1)
    w.code("Step 7: Fill the template", FILL_JS, pos=[4680, 80])
    w.connect("New key?", "Step 7: Fill the template", output=0)
    w.connect("Outcome", "Step 7: Fill the template", output=1)
    w.code("Step 8: Rule: number, amount and no blank field", CHECK_JS, pos=[4940, 80])
    w.connect("Step 7: Fill the template", "Step 8: Rule: number, amount and no blank field")
    w.if_("Step 8: Passes?", "={{ $json.ok }}", pos=[5200, 80])
    w.connect("Step 8: Rule: number, amount and no blank field", "Step 8: Passes?")
    w.if_("Final notice?", f"={{{{ {R}.outcome }}}}", op="equals", right="final", pos=[5460, 0])
    w.connect("Step 8: Passes?", "Final notice?", output=0)

    w.http("Step 9: Ask Aisha to approve the final notice", "PUT",
           f"={{{{ {CFG}.approvals_url }}}}/requests/{{{{ {R}.approval_id }}}}",
           body=f"={{{{ JSON.stringify({{ id: {R}.approval_id, invoice: {R}.invoice, account: {R}.account, approver: {CFG}.ar_lead, status: 'pending', to: {CHECK}.to, subject: {CHECK}.subject, text: {CHECK}.text, template_version: {CHECK}.template_version }}) }}}}",
           write=True, pos=[5720, -160], notes="Unapproved, the final notice waits a day: tomorrow's run asks again.")
    w.connect("Final notice?", "Step 9: Ask Aisha to approve the final notice", output=0)
    w.http("Step 9: Send from the AR mailbox", "POST", f"={{{{ {CFG}.mail_url }}}}/outbox",
           body=f"={{{{ JSON.stringify({{ from: {CFG}.ar_mailbox, to: {CHECK}.to, subject: {CHECK}.subject, text: {CHECK}.text }}) }}}}",
           write=True, pos=[5720, 80], notes="A write: never retried.")
    w.connect("Final notice?", "Step 9: Send from the AR mailbox", output=1)
    w.http("Step 10: Set the next stage and date", "PUT", rec_url, body=rec_body, write=True, pos=[5980, 80])
    w.connect("Step 9: Send from the AR mailbox", "Step 10: Set the next stage and date")
    w.if_("After the final notice?", f"={{{{ {R}.next.stage }}}}", op="equals", right="handoff", pos=[6240, 80])
    w.connect("Step 10: Set the next stage and date", "After the final notice?")
    w.http("Step 10: Open Aisha's handoff", "PUT", f"={{{{ {sp} }}}}/handoffs/{{{{ {R}.invoice }}}}",
           body=f"={{{{ JSON.stringify({{ id: {R}.invoice, invoice: {R}.invoice, account: {R}.account, owner: {CFG}.ar_lead, status: 'open', opened_on: $now.toISODate() }}) }}}}",
           write=True, pos=[6500, 0], notes="Nothing more is sent; Aisha decides: a call, a credit stop, a write-off.")
    w.connect("After the final notice?", "Step 10: Open Aisha's handoff", output=0)
    w.finish_key("Mark key done", f"{R}.key", "done", f"'sent ' + {R}.stage", pos=[6760, 80])
    w.connect("Step 10: Open Aisha's handoff", "Mark key done")
    w.connect("After the final notice?", "Mark key done", output=1)

    # ---- stop, list and wait paths -------------------------------------------------
    w.http("Steps 4 and 5: Record the stop", "PUT", rec_url, body=rec_body, write=True, pos=[4160, 360],
           notes="The stage is kept: a closed dispute or an ended hold resumes at its paused stage.")
    w.connect("Outcome", "Steps 4 and 5: Record the stop", output=2)
    w.if_("Tell Aisha?", f"={{{{ {R}.tell === true }}}}", pos=[4420, 360])
    w.connect("Steps 4 and 5: Record the stop", "Tell Aisha?")
    w.http("Step 4: Tell Aisha", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: [{CFG}.ar_lead], subject: 'Invoice ' + {R}.invoice + ' stopped: ' + {R}.reason, text: 'Reminders stopped. Log a dispute or a \"chase\" hold for invoice ' + {R}.invoice + ' (open ' + {R}.open_amount + ' of ' + {R}.amount + ').' }}) }}}}",
           write=True, pos=[4680, 280])
    w.connect("Tell Aisha?", "Step 4: Tell Aisha", output=0)
    w.http("Step 3: Add to the reminder list", "PUT", rec_url, body=rec_body, write=True, pos=[4160, 560],
           notes="A new invoice at its first stage, or a resumed invoice not yet due.")
    w.connect("Outcome", "Step 3: Add to the reminder list", output=3)

    # ---- step 10: decision log --------------------------------------------------------
    w.decision_log("Step 10: Decision log", f"{R}.invoice", f"{R}.decision",
                   f"JSON.stringify({{ stage: {R}.stage, reason: {R}.reason || null, next_stage: ({R}.next || {{}}).stage || null, next_date: ({R}.next || {{}}).due_on || null, approved_by: {R}.approved_by || null, template_version: {CFG}.template_version }})",
                   pos=[7020, 280])
    for n in ["Mark key done", "Step 9: Ask Aisha to approve the final notice", "Step 4: Tell Aisha"]:
        w.connect(n, "Step 10: Decision log")
    w.connect("Tell Aisha?", "Step 10: Decision log", output=1)
    w.connect("Outcome", "Step 10: Decision log", output=4)

    # ---- step 8 hold ------------------------------------------------------------------
    release_sql = "DELETE FROM key_log WHERE recipe = $1 AND key = $2 RETURNING key"
    w.pg("Step 8: Release key: held", release_sql, args=[json.dumps("R8.1"), f"{R}.key || ''"], pos=[5460, 300],
         notes="The stage stays due; the next run checks it again once the CRM is fixed.")
    w.connect("Step 8: Passes?", "Step 8: Release key: held", output=1)
    w.exception("Exception queue: held by step 8", f"{R}.invoice", "held: template check",
                f"{CHECK}.problems.join('; ')", f"{CFG}.ar_lead", pos=[5720, 300])
    w.http("Step 8: Alert Aisha", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: [{CFG}.ar_lead], subject: 'Reminder held: invoice ' + {R}.invoice, text: {CHECK}.problems.join('; ') }}) }}}}",
           write=True, error_output=False, pos=[5980, 300])
    w.decision_log("Step 8: Decision log: held", f"{R}.invoice", f"'held: ' + {R}.stage",
                   f"JSON.stringify({{ stage: {R}.stage, problems: {CHECK}.problems, template_version: {CFG}.template_version }})", pos=[6240, 300])
    w.chain("Step 8: Release key: held", "Exception queue: held by step 8", "Step 8: Alert Aisha", "Step 8: Decision log: held")

    # ---- send failed: logged unsent, the stage stays due --------------------------
    w.pg("Release key: the stage stays due", release_sql, args=[json.dumps("R8.1"), f"{R}.key"], pos=[5980, 520])
    w.connect("Step 9: Send from the AR mailbox", "Release key: the stage stays due", output=1)
    w.exception("Exception queue: send failed", f"{R}.invoice", "send failed",
                f"'Not sent: ' + {R}.stage + '; it stays due for the next run'", f"{CFG}.ar_lead", pos=[6240, 520])
    w.decision_log("Decision log: unsent", f"{R}.invoice", f"'unsent: ' + {R}.stage",
                   f"JSON.stringify({{ stage: {R}.stage, template_version: {CFG}.template_version }})", pos=[6500, 520])
    w.chain("Release key: the stage stays due", "Exception queue: send failed", "Decision log: unsent")

    # ---- list writes that fail --------------------------------------------------------
    w.finish_key("Mark key failed", f"{R}.key", "failed", "'sent; reminder list write failed'", pos=[6500, 720])
    w.connect("Step 10: Set the next stage and date", "Mark key failed", output=1)
    w.connect("Step 10: Open Aisha's handoff", "Mark key failed", output=1)
    w.exception("Exception queue: write failed", f"{R}.invoice", "write failed",
                "'Reminder list or approval write failed; check the invoice before the next run'", f"{CFG}.ar_lead", pos=[6760, 720])
    w.connect("Mark key failed", "Exception queue: write failed")
    for n in ["Step 9: Ask Aisha to approve the final notice", "Steps 4 and 5: Record the stop", "Step 4: Tell Aisha",
              "Step 3: Add to the reminder list"]:
        w.connect(n, "Exception queue: write failed", output=1)
    return w
