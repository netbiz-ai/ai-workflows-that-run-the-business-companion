"""R7.3 Stop and verify any change to a supplier's bank details: rules only, no AI step.

Source: book Chapter 7, recipe R7.3, build steps 1 to 9 and the rules that follow them
(recipes/R7.3/build-spec.md). Any difference holds the supplier; only a call to the number
on file, logged by the caller, and entry by a second person lift it. It never accepts a
change from an email or invoice.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "n8n"))
from wf import Workflow  # noqa: E402

T_REC = "Step 1: R7.1 record saved"
T_MSG = "Step 1: Supplier message"
T_EXP = "Step 1: New export"
T_CALL = "Step 7: Call-back logged"
T_RUN = "Pre-run check: payment run due"
CFG = "$('Config').item.json"
CHK = "$('Step 2: Rule: differs from the register?').item.json"
CB = f"$('{T_CALL}').first().json.body"
CBR = "$('Step 7: Rule: call-back outcome').first().json"

NORM_JS = "const norm = s => String(s || '').replace(/[\\s\\-]/g, '').toLowerCase();\n"

ROUTE_JS = f"""
// Five events share one Config; this names the one that ran.
const t = {{ record: '{T_REC}', message: '{T_MSG}', export: '{T_EXP}', callback: '{T_CALL}', prerun: '{T_RUN}' }};
for (const [path, node] of Object.entries(t)) {{ try {{ if ($(node).isExecuted) return [{{ json: {{ path }} }}]; }} catch (e) {{}} }}
return [{{ json: {{ path: 'none' }} }}];
"""

FROM_RECORD_JS = r"""
// Step 1: an R7.1 record carries the bank details printed on the invoice.
const r = $('Step 1: Read the R7.1 record').first().json;
if (!r.supplier_id) return [];
return [{ json: { supplier_id: r.supplier_id, details: r.bank_account || null, phrase: null, source: 'R7.1 record', ref: r.id, record_id: r.id } }];
"""

FROM_MESSAGE_JS = r"""
// Step 1: a supplier message counts only if it holds a change-request phrase; a phrase match is a difference.
const cfg = $('Config').first().json;
const m = $('Step 1: Read the message').first().json;
const sup = ($('Step 1: Find the sender\'s supplier').first().json.items || [])[0];
const text = `${m.subject || ''} ${m.text || ''}`.toLowerCase();
const phrase = cfg.change_phrases.find(p => text.includes(p.toLowerCase()));
if (!phrase || !sup) return [];
return [{ json: { supplier_id: sup.id, details: null, phrase, source: 'supplier message', ref: m.id, record_id: null } }];
"""

FROM_EXPORT_JS = r"""
// Step 1: a new export: one check for each supplier in it.
const e = $('Step 1: Read the export').first().json;
return (e.suppliers || []).map(s => ({ json: { supplier_id: s.supplier_id, details: s.bank_account || null, phrase: null,
  source: 'export', ref: e.id, record_id: null } }));
"""

DIFF_JS = NORM_JS + r"""
// Step 2: normalize spaces, dashes and case, then compare with the register; a phrase match is a difference.
const c = $('Step 2: Checks').item.json;
const reg = ($('Step 2: Read the register').item.json.items || [])[0] || null;
const sup = ($('Step 2: Read the supplier').item.json.items || [])[0] || {};
let differs, why;
if (c.phrase) { differs = true; why = `change-request phrase "${c.phrase}"`; }
else if (!c.details) { differs = false; why = 'no bank details to compare'; }
else if (!reg) { differs = true; why = 'supplier not in the register'; }
else { differs = norm(c.details) !== norm(reg.bank_account); why = differs ? 'bank details differ from the register' : 'same as the register'; }
const today = new Date().toISOString().slice(0, 10);
return { json: Object.assign({}, c, {
  differs, why, held_before: !!sup.hold, hold_reason: sup.hold_reason || null, supplier_name: sup.name || c.supplier_id,
  register_phone: reg ? reg.phone : null, checked_on: today,
  key: `${c.supplier_id}:${norm(c.details)}`,
  lift: !differs && c.source === 'export' && !!sup.hold && sup.hold_reason === 'confirmed change; awaiting export',
  rules: { source: c.source, differs, why, held_before: !!sup.hold } }) };
"""

TASK_JS = r"""
// Step 6: the caller's task carries the register's number, never one from the message or invoice.
const c = $('Step 2: Rule: differs from the register?').item.json;
const cfg = $('Config').first().json;
const instruction = c.register_phone
  ? `Call ${c.supplier_name} on ${c.register_phone}, the number in the bank register, to confirm its bank details. Use no number from any message or invoice. Log the number you dialed and the outcome.`
  : `${c.supplier_name} has no number in the bank register. Take one from the contract, its official website or a previously verified document, never the invoice or a change email, then call to confirm its bank details. Log the number you dialed and the outcome.`;
return { json: { assignee: cfg.bank_caller, supplier_id: c.supplier_id, supplier: c.supplier_name, phone: c.register_phone,
  instruction, status: 'open', raised_on: c.checked_on } };
"""

CALL_JS = r"""
// Step 7: the caller logged the number dialed and the outcome; only the register's number counts.
const b = $('Step 7: Call-back logged').first().json.body;
const reg = ($('Step 7: Read the register entry').first().json.items || [])[0] || null;
const digits = s => String(s || '').replace(/\D/g, '');
const onFile = reg && reg.phone ? digits(reg.phone) : null;
const rules = { outcome: b.outcome, number_on_file: !!onFile };
let route;
if (onFile && digits(b.number_dialed) !== onFile) route = 'wrong number';
else if (b.outcome !== 'confirmed') route = 'not confirmed';
else if (b.new_bank_account || b.new_phone) route = 'change';
else route = 'no change';
rules.route = route;
const entry = Object.assign({}, reg || { id: b.supplier_id, supplier_id: b.supplier_id });
if (b.new_bank_account) entry.bank_account = b.new_bank_account;
if (b.new_phone) entry.phone = b.new_phone;
entry.verified_on = new Date().toISOString().slice(0, 10);
entry.verified_by = b.logged_by || null;
return [{ json: { route, rules, entry, register_id: entry.id } }];
"""

PRERUN_JS = r"""
// Before each payment run: today's export check must be logged; held suppliers are listed for the caller and the AP owner.
const today = new Date().toISOString().slice(0, 10);
const checks = ($('Pre-run: Read the export checks').first().json.items || []).filter(c => c.source === 'export' && c.checked_on === today);
const sups = $('Pre-run: Read the suppliers').first().json.items || [];
return [{ json: { logged: checks.length > 0, held: sups.filter(s => s.hold).map(s => s.name || s.id), all: sups.map(s => s.id) } }];
"""


def build() -> Workflow:
    w = Workflow("R7.3", "R7.3 Stop and verify any change to a supplier's bank details")
    w.webhook(T_REC, "r7-3-record", "R7.1 calls this when it saves a record. Body: {record_id}.", pos=[0, 0])
    w.webhook(T_MSG, "r7-3-message", "Your AP mailbox calls this for each supplier message, and for a logged phoned or texted request. Body: {message_id}.", pos=[0, 200])
    w.webhook(T_EXP, "r7-3-export", "Called when the caller saves a new supplier export. Body: {export_id}.", pos=[0, 400])
    w.webhook(T_CALL, "r7-3-callback", "The caller's task form calls this. Body: {supplier_id, task_id, number_dialed, outcome: confirmed | not confirmed, new_bank_account, new_phone, logged_by}.", pos=[0, 900])
    w.webhook(T_RUN, "r7-3-pre-run", "Called before each payment run. Body: {run_date}.", pos=[0, 1300])
    w.config("Config", {
        "review_url": "https://<your review list API>",
        "mailbox_url": "https://<your AP mailbox API>",
        "exports_url": "https://<your supplier export library API>",
        "suppliers_url": "https://<your supplier list API>",
        "register_url": "https://<your bank register API>",
        "checks_url": "https://<your R7.3 check list API>",
        "tasks_url": "https://<your task list API>",
        "messaging_url": "https://<your messaging API>",
        "change_phrases": ["new bank", "<your change-request phrases>"],
        "bank_caller": "<your caller, not a payment approver>",
        "finance_assistant": "<your bank-change enterer, not a payment approver>",
        "fraud_report_to": "<who you report suspected fraud to>",
        "pre_run_reviewer": "<your AP owner>",
        "kill_switch_alert": "<who is alerted when R7.3 is off>",
        "workflow_owner": "<your workflow owner>",
    }, pos=[260, 600])
    for t in [T_REC, T_MSG, T_EXP, T_CALL, T_RUN]:
        w.connect(t, "Config")
    w.code("Which event?", ROUTE_JS, mode="runOnceForAllItems", pos=[520, 600])
    w.switch("Event", "={{ $json.path }}", ["record", "message", "export", "callback", "prerun"], pos=[780, 600])
    w.chain("Config", "Which event?", "Event")

    # ---- step 1: three triggers become one check per supplier ------------------------
    w.http("Step 1: Read the R7.1 record", "GET", f"={{{{ {CFG}.review_url }}}}/records/{{{{ $('{T_REC}').first().json.body.record_id }}}}",
           write=False, error_output=False, pos=[1040, 0])
    w.code("Step 1: From the record", FROM_RECORD_JS, mode="runOnceForAllItems", pos=[1300, 0])
    w.http("Step 1: Read the message", "GET", f"={{{{ {CFG}.mailbox_url }}}}/messages/{{{{ $('{T_MSG}').first().json.body.message_id }}}}",
           write=False, error_output=False, pos=[1040, 200])
    w.http("Step 1: Find the sender's supplier", "GET", f"={{{{ {CFG}.suppliers_url }}}}/suppliers",
           query={"_wrap": "1", "contact_email": "={{ $('Step 1: Read the message').first().json.from }}"}, write=False, error_output=False, pos=[1300, 200])
    w.code("Step 1: From the message", FROM_MESSAGE_JS, mode="runOnceForAllItems", pos=[1560, 200],
           notes="A phoned or texted request is logged as a message: a trigger, never a change.")
    w.http("Step 1: Read the export", "GET", f"={{{{ {CFG}.exports_url }}}}/exports/{{{{ $('{T_EXP}').first().json.body.export_id }}}}",
           write=False, error_output=False, pos=[1040, 400])
    w.code("Step 1: From the export", FROM_EXPORT_JS, mode="runOnceForAllItems", pos=[1300, 400])
    w.connect("Event", "Step 1: Read the R7.1 record", output=0)
    w.connect("Event", "Step 1: Read the message", output=1)
    w.connect("Event", "Step 1: Read the export", output=2)
    w.connect("Step 1: Read the R7.1 record", "Step 1: From the record")
    w.chain("Step 1: Read the message", "Step 1: Find the sender's supplier", "Step 1: From the message")
    w.connect("Step 1: Read the export", "Step 1: From the export")

    # ---- steps 2 to 6 -----------------------------------------------------------------
    w.code("Step 2: Checks", "return { json: $json };", pos=[1820, 200])
    for n in ["Step 1: From the record", "Step 1: From the message", "Step 1: From the export"]:
        w.connect(n, "Step 2: Checks")
    w.http("Step 2: Read the register", "GET", f"={{{{ {CFG}.register_url }}}}/register",
           query={"_wrap": "1", "supplier_id": "={{ $json.supplier_id }}"}, write=False, error_output=False, pos=[2080, 200])
    w.http("Step 2: Read the supplier", "GET", f"={{{{ {CFG}.suppliers_url }}}}/suppliers",
           query={"_wrap": "1", "id": "={{ $('Step 2: Checks').item.json.supplier_id }}"}, write=False, error_output=False, pos=[2340, 200])
    w.code("Step 2: Rule: differs from the register?", DIFF_JS, pos=[2600, 200], notes="Rules only; there is no AI step in R7.3.")
    w.chain("Step 2: Checks", "Step 2: Read the register", "Step 2: Read the supplier", "Step 2: Rule: differs from the register?")

    w.http("Step 3: Log the check", "POST", f"={{{{ {CFG}.checks_url }}}}/checks",
           body=("={{ JSON.stringify({ supplier_id: $json.supplier_id, record_id: $json.record_id, source: $json.source, ref: $json.ref, "
                 "differs: $json.differs, hold: $json.differs || ($json.held_before && !$json.lift), checked_on: $json.checked_on, checked_at: $now.toISO() }) }}"),
           write=True, pos=[2860, 200], notes="The list R7.2 reads before it matches an invoice.")
    w.if_("Differs?", f"={{{{ {CHK}.differs }}}}", pos=[3120, 200])
    w.chain("Step 2: Rule: differs from the register?", "Step 3: Log the check", "Differs?")

    w.if_("Confirmed change now shown?", f"={{{{ {CHK}.lift }}}}", pos=[3380, 400])
    w.http("Step 8: Lift the hold", "PATCH", f"={{{{ {CFG}.suppliers_url }}}}/suppliers/{{{{ {CHK}.supplier_id }}}}",
           body="={{ JSON.stringify({ hold: false, hold_reason: null }) }}", write=True, pos=[3640, 400],
           notes="The export shows the change the caller confirmed and the assistant entered.")
    w.code("Result: no hold", "return { json: { decision: 'no hold' } };", pos=[3640, 560])
    w.code("Result: hold lifted", "return { json: { decision: 'hold lifted: export shows the confirmed change' } };", pos=[3900, 400])
    w.connect("Differs?", "Confirmed change now shown?", output=1)
    w.connect("Confirmed change now shown?", "Step 8: Lift the hold", output=0)
    w.connect("Confirmed change now shown?", "Result: no hold", output=1)
    w.connect("Step 8: Lift the hold", "Result: hold lifted")

    w.http("Step 4: Set the hold flag", "PATCH", f"={{{{ {CFG}.suppliers_url }}}}/suppliers/{{{{ {CHK}.supplier_id }}}}",
           body="={{ JSON.stringify({ hold: true, hold_reason: 'bank-detail difference' }) }}", write=True, pos=[3380, 0])
    w.reserve_key("Step 5: Reserve key", f"{CHK}.key", pos=[3640, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[3900, 0])
    w.code("Result: open hold, no second task", "return { json: { decision: 'held; open hold, no second task' } };", pos=[4160, -160])
    w.code("Step 6: Caller's task", TASK_JS, pos=[4160, 0])
    w.http("Step 6: Send the caller a task", "POST", f"={{{{ {CFG}.tasks_url }}}}/tasks",
           body="={{ JSON.stringify($json) }}", write=True, pos=[4420, 0])
    w.finish_key("Mark key done", f"{CHK}.key", "done", "'task sent'", pos=[4680, 0])
    w.code("Result: held, task sent", "return { json: { decision: 'held; caller tasked' } };", pos=[4940, 0])
    w.connect("Differs?", "Step 4: Set the hold flag", output=0)
    w.chain("Step 4: Set the hold flag", "Step 5: Reserve key", "New key?")
    w.connect("New key?", "Result: open hold, no second task", output=1)
    w.connect("New key?", "Step 6: Caller's task", output=0)
    w.chain("Step 6: Caller's task", "Step 6: Send the caller a task", "Mark key done", "Result: held, task sent")

    w.decision_log("Decision log", f"{CHK}.supplier_id", "$json.decision", f"JSON.stringify({CHK}.rules)", pos=[5200, 200])
    for n in ["Result: no hold", "Result: hold lifted", "Result: open hold, no second task", "Result: held, task sent"]:
        w.connect(n, "Decision log")

    w.finish_key("Mark key failed", f"{CHK}.key", "failed", "'write failed: ' + (($json.error && $json.error.message) || 'unknown')", pos=[4680, 700])
    w.exception("Exception queue: write failed", f"{CHK}.supplier_id", "write failed",
                "'A check, hold or task write failed, never retried; hold the supplier by hand and check the log'",
                f"{CFG}.workflow_owner", pos=[4940, 700])
    for n in ["Step 3: Log the check", "Step 8: Lift the hold", "Step 4: Set the hold flag", "Step 6: Send the caller a task"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- steps 7 to 9: the call-back ---------------------------------------------------------
    w.http("Step 7: Read the register entry", "GET", f"={{{{ {CFG}.register_url }}}}/register",
           query={"_wrap": "1", "supplier_id": f"={{{{ {CB}.supplier_id }}}}"}, write=False, error_output=False, pos=[1040, 900])
    w.code("Step 7: Rule: call-back outcome", CALL_JS, mode="runOnceForAllItems", pos=[1300, 900])
    w.switch("Call-back outcome", "={{ $json.route }}", ["change", "no change", "not confirmed", "wrong number"], pos=[1560, 900])
    w.connect("Event", "Step 7: Read the register entry", output=3)
    w.chain("Step 7: Read the register entry", "Step 7: Rule: call-back outcome", "Call-back outcome")

    w.http("Step 8: Save the confirmed details to the register", "PUT",
           f"={{{{ {CFG}.register_url }}}}/register/{{{{ {CBR}.register_id }}}}",
           body=f"={{{{ JSON.stringify({CBR}.entry) }}}}", write=True, pos=[1820, 700],
           notes="Only the flow writes the register, and only after a call to the number on file. A new number is saved here too.")
    w.http("Step 8: Hold until the export shows it", "PATCH", f"={{{{ {CFG}.suppliers_url }}}}/suppliers/{{{{ {CB}.supplier_id }}}}",
           body="={{ JSON.stringify({ hold: true, hold_reason: 'confirmed change; awaiting export' }) }}", write=True, pos=[2080, 700])
    w.http("Step 8: Ask the finance assistant to enter it", "POST", f"={{{{ {CFG}.tasks_url }}}}/tasks",
           body=(f"={{{{ JSON.stringify({{ assignee: {CFG}.finance_assistant, supplier_id: {CB}.supplier_id, status: 'open', "
                 "instruction: 'The caller confirmed a bank-detail change on the number on file. Enter it in the ledger; the hold lifts when the next export shows it.' }) }}"),
           write=True, pos=[2340, 700])
    w.http("Step 8: Ask the finance assistant to release", "POST", f"={{{{ {CFG}.tasks_url }}}}/tasks",
           body=(f"={{{{ JSON.stringify({{ assignee: {CFG}.finance_assistant, supplier_id: {CB}.supplier_id, status: 'open', "
                 "instruction: 'The caller confirmed no change on the number on file. Release the hold.' }) }}"),
           write=True, pos=[1820, 900])
    w.pg("Step 8: Close the hold's keys", "DELETE FROM key_log WHERE recipe = $1 AND left(key, length($2) + 1) = $2 || ':' RETURNING key",
         args=['"R7.3"', f"{CB}.supplier_id"], pos=[2600, 800],
         notes="The call-back answered the hold; a later change gets its own task.")
    w.connect("Call-back outcome", "Step 8: Save the confirmed details to the register", output=0)
    w.chain("Step 8: Save the confirmed details to the register", "Step 8: Hold until the export shows it",
            "Step 8: Ask the finance assistant to enter it", "Step 8: Close the hold's keys")
    w.connect("Call-back outcome", "Step 8: Ask the finance assistant to release", output=1)
    w.connect("Step 8: Ask the finance assistant to release", "Step 8: Close the hold's keys")

    w.http("Step 9: Report suspected fraud", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=(f"={{{{ JSON.stringify({{ to: {CFG}.fraud_report_to, subject: 'Suspected payment fraud: supplier ' + {CB}.supplier_id, "
                 "text: 'A bank-detail change was not confirmed on the number on file. The hold stays.' }) }}"),
           write=True, pos=[1820, 1100])
    w.exception("Step 9: Exception queue: hold stays", f"{CB}.supplier_id", "suspected fraud",
                "'Change not confirmed on the number on file; hold stays'", f"{CFG}.fraud_report_to", pos=[2080, 1100])
    w.exception("Exception queue: call to another number", f"{CB}.supplier_id", "call to another number",
                "'Logged number differs from the register; hold stays; ring the register number'", f"{CFG}.bank_caller", pos=[1820, 1300])
    w.connect("Call-back outcome", "Step 9: Report suspected fraud", output=2)
    w.connect("Step 9: Report suspected fraud", "Step 9: Exception queue: hold stays")
    w.connect("Call-back outcome", "Exception queue: call to another number", output=3)

    w.decision_log("Step 7: Decision log", f"{CB}.supplier_id", f"'call-back: ' + {CBR}.route", f"JSON.stringify({CBR}.rules)", pos=[2860, 1000])
    for n in ["Step 8: Close the hold's keys", "Step 9: Exception queue: hold stays", "Exception queue: call to another number"]:
        w.connect(n, "Step 7: Decision log")
    w.exception("Exception queue: call-back write failed", f"{CB}.supplier_id", "write failed",
                "'A register, hold, task or report write failed after a call-back, never retried; finish it by hand'",
                f"{CFG}.workflow_owner", pos=[2860, 1200])
    for n in ["Step 8: Save the confirmed details to the register", "Step 8: Hold until the export shows it",
              "Step 8: Ask the finance assistant to enter it", "Step 8: Ask the finance assistant to release", "Step 9: Report suspected fraud"]:
        w.connect(n, "Exception queue: call-back write failed", output=1)

    # ---- before each payment run ----------------------------------------------------------------
    w.http("Pre-run: Read the export checks", "GET", f"={{{{ {CFG}.checks_url }}}}/checks",
           query={"_wrap": "1", "source": "export"}, write=False, error_output=False, pos=[1040, 1500])
    w.http("Pre-run: Read the suppliers", "GET", f"={{{{ {CFG}.suppliers_url }}}}/suppliers",
           query={"_wrap": "1"}, write=False, error_output=False, pos=[1300, 1500])
    w.code("Pre-run: Rule: export check logged?", PRERUN_JS, mode="runOnceForAllItems", pos=[1560, 1500])
    w.if_("Logged?", "={{ $json.logged }}", pos=[1820, 1500])
    w.connect("Event", "Pre-run: Read the export checks", output=4)
    w.chain("Pre-run: Read the export checks", "Pre-run: Read the suppliers", "Pre-run: Rule: export check logged?", "Logged?")
    pr = "$('Pre-run: Rule: export check logged?').first().json"
    w.http("Pre-run: Ask the caller and AP owner to confirm", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=(f"={{{{ JSON.stringify({{ to: [{CFG}.bank_caller, {CFG}.pre_run_reviewer], subject: 'Payment run check', "
                 f"text: 'Export check logged. Held suppliers: ' + ({pr}.held.join(', ') || 'none') + "
                 "'. Confirm no bill is from a held supplier and every bill has a logged approval. Whoever releases the run must not have approved its bills.' }) }}"),
           write=True, error_output=False, pos=[2080, 1400])
    w.http("Pre-run: Alert, R7.3 check missing", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=(f"={{{{ JSON.stringify({{ to: {CFG}.kill_switch_alert, subject: 'No R7.3 export check before the payment run', "
                 "text: 'No export check is logged today, so every supplier is held until the check runs.' }) }}"),
           write=True, error_output=False, pos=[2080, 1600])
    w.code("Pre-run: Every supplier", f"return {pr}.all.map(id => ({{ json: {{ id }} }}));", mode="runOnceForAllItems", pos=[2340, 1600])
    w.http("Pre-run: Hold the supplier", "PATCH", f"={{{{ {CFG}.suppliers_url }}}}/suppliers/{{{{ $json.id }}}}",
           body="={{ JSON.stringify({ hold: true, hold_reason: 'no export check before the payment run' }) }}", write=True, pos=[2600, 1600])
    w.exception("Exception queue: hold write failed", "$json.id || 'supplier'", "write failed",
                "'Pre-run hold write failed; hold this supplier by hand'", f"{CFG}.workflow_owner", pos=[2860, 1700])
    w.connect("Logged?", "Pre-run: Ask the caller and AP owner to confirm", output=0)
    w.connect("Logged?", "Pre-run: Alert, R7.3 check missing", output=1)
    w.chain("Pre-run: Alert, R7.3 check missing", "Pre-run: Every supplier", "Pre-run: Hold the supplier")
    w.connect("Pre-run: Hold the supplier", "Exception queue: hold write failed", output=1)
    return w
