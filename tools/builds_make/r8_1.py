"""R8.1 Send staged overdue reminders that stop on payment or dispute, as Make scenarios: rules only, no AI step.

Source: book Chapter 8, recipe R8.1, Table 8.1 and build steps 1 to 10 (recipes/R8.1/build-spec.md).
The rules are the n8n build's own JavaScript (tools/builds/r8_1.py), run through n8n_rule.
Two scenarios, because a Make scenario has one trigger: the reminder run (schedule, Monday to
Friday at 07:00, after the open-invoice export is due) and Aisha's decision on a final notice
(webhook, step 9), which reruns steps 2, 4 and 5 for that invoice before an approved notice sends.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R8.1"
N8N = n8n_build(R)
M, A = N8N.M, N8N.A
CONFIG = {
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
}
CFG = "$('Config').first().json"
EXPORT, MAILBOX, COUNT = "Step 2: Read today's export", "Step 2: Read the mailbox check (R8.3)", "Step 2: Count unreviewed unlinked items (R8.3)"
GATE, RULES = "Step 2: Rule: export and intake current?", "Rules: steps 3 to 5"
FILL, CHECK = "Step 7: Fill the template", "Step 8: Rule: number, amount and no blank field"


def rule(js, sources, *, trigger=None, prelude="", **kw):
    """n8n_rule, plus the webhook's fields as n8n gives them ($('Trigger').first().json.body).
    trigger: (n8n trigger name, [field, ...]). A Make mapping cannot pass the whole webhook bundle,
    so each field is its own input and the adapter's table gets {body: {...}}; a field the
    caller left out is left out of body too."""
    code, inputs = n8n_rule(js, sources, prelude=prelude, **kw)
    if not trigger:
        return code, inputs
    name, fields = trigger
    for f in fields:
        inputs[f"tr_{f}"] = "{{1." + f + "}}"
    pairs = ", ".join(f"{f}: input.tr_{f}" for f in fields)
    shim = ("// The webhook's fields, as n8n's Webhook node gives them.\n"
            f"DATA[{name!r}] = [{{ json: {{ body: Object.fromEntries(Object.entries({{ {pairs} }})"
            ".filter(([, v]) => v !== undefined && v !== null && v !== '')) } }];\n")
    return code.replace("const BODIES = ", shim + "const BODIES = ", 1), inputs


def resume(s: Scenario) -> dict:
    """Make's Resume handler: the failed read gives no data and the run goes on, as n8n's read
    sends its error output to the same next step. The step 2 rule reports it missing."""
    return {"id": s._id(f"_resume{s._next}"), "module": "builtin:Resume", "version": 1, "parameters": {},
            "mapper": {"data": ""}, "metadata": {"designer": {"x": 0, "y": 0}}}


# The n8n build counts the open, unreviewed R8.3 items older than the limit in SQL; the table API
# returns those rows, so the count is taken here, before the step 2 rule reads it.
COUNT_PRELUDE = f"""
{{
  const rows = DATA[{COUNT!r}][0].json;
  const limit = Date.now() - Number(DATA['Config'][0].json.unlinked_hold_hours) * 3600000;
  DATA[{COUNT!r}] = [{{ json: {{ count: (Array.isArray(rows) ? rows : []).filter(r => Date.parse(r.created_at) < limit).length }} }}];
}}
"""


def reminders(s: Scenario, entry: dict, decision: bool) -> list[dict]:
    """Steps 2 to 10, the same in both scenarios; entry is the first step's filter."""
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    out = lambda step, f: "{{" + f"{s.ref(step)}.result.{f}" + "}}"  # noqa: E731
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    config = "{{" + f"{c}.result" + "}}"
    sp = cfg("sharepoint_url")
    trig = (A, ["invoice", "approved", "by"]) if decision else None

    # ---- step 2: export and intake current ---------------------------------------
    # Where R8.3 does not run, n8n skips its two reads; a Make step cannot be skipped and the flow
    # go on, so they always run (a failed mailbox read resumes empty) and the rule ignores them.
    flow = [s.http(EXPORT, "GET", sp + "/exports/open-invoices", onerror=[resume(s)])]
    flow[0]["filter"] = entry
    flow.append(s.http(MAILBOX, "GET", sp + "/status/mailbox-check", onerror=[resume(s)]))
    flow.append(s.http(COUNT, "GET", s.table("/exception_queue"),
                       query={"recipe": "eq.R8.3", "reason": "eq.unlinked item", "status": "eq.open", "select": "created_at"}))
    code, inputs = rule(N8N.GATE_JS, {"Config": config, EXPORT: data(EXPORT), MAILBOX: data(MAILBOX), COUNT: data(COUNT)},
                        prelude=COUNT_PRELUDE, input_node="Config", bodies={
        "no_run_log": f"JSON.stringify({{ recipe: '{R}', item: 'run ' + out.today, decision: 'no run', rules: {{ problems: out.problems }} }})",
        "alert_message": f"JSON.stringify({{ to: [{CFG}.ar_lead], subject: 'R8.1 reminders: no run today', text: 'Nothing was sent: ' + out.problems.join('; ') }})",
    })
    flow.append(s.code(GATE, code, inputs))
    no_run = [s.decision_log("Step 2: Decision log: no run", out(GATE, "no_run_log")),
              s.http("Step 2: Alert Aisha", "POST", cfg("messaging_url") + "/messages", body=out(GATE, "alert_message"), parse=False)]

    # ---- steps 3 to 5 -----------------------------------------------------------------
    run = [s.http("Step 3: Read the reminder list", "GET", sp + "/reminders", query={"_wrap": "1"}),
           s.http("Step 5: Read the dispute list", "GET", sp + "/disputes", query={"_wrap": "1", "status": "open"}),
           s.http("Step 5: Read the hold list", "GET", sp + "/holds", query={"_wrap": "1"}),
           s.http("Read CRM contacts (for step 7)", "GET", cfg("crm_url") + "/accounts", query={"_wrap": "1"})]
    exc = lambda reason, detail: (f"JSON.stringify({{ recipe: '{R}', item: out.invoice, reason: '{reason}', detail: {detail}, owner: {CFG}.ar_lead }})")  # noqa: E731
    code, inputs = rule(N8N.RULES_JS, {
        "Config": config, GATE: "{{" + f"{s.ref(GATE)}.result" + "}}", EXPORT: data(EXPORT),
        "Step 3: Read the reminder list": data("Step 3: Read the reminder list"),
        "Step 5: Read the dispute list": data("Step 5: Read the dispute list"),
        "Step 5: Read the hold list": data("Step 5: Read the hold list"),
        "Read CRM contacts (for step 7)": data("Read CRM contacts (for step 7)"),
    }, trigger=trig, many=True, input_node="Config", bodies={
        "self": "JSON.stringify(out)",  # the item as later rules read it with $('Rules: steps 3 to 5').item
        "invoice_q": "encodeURIComponent(out.invoice)",
        "key_q": "encodeURIComponent(out.key || '')",
        "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: out.key || '' }})",
        "approval_q": "encodeURIComponent(out.approval_id || '')",
        "record_body": "JSON.stringify(out.record || {})",
        "handoff": "(out.next || {}).stage === 'handoff'",
        "handoff_body": f"JSON.stringify({{ id: out.invoice, invoice: out.invoice, account: out.account, owner: {CFG}.ar_lead, status: 'open', opened_on: new Date().toISOString().slice(0, 10) }})",
        "tell_message": f"JSON.stringify({{ to: [{CFG}.ar_lead], subject: 'Invoice ' + out.invoice + ' stopped: ' + out.reason, "
                        "text: 'Reminders stopped. Log a dispute or a \"chase\" hold for invoice ' + out.invoice + ' (open ' + out.open_amount + ' of ' + out.amount + ').' })",
        "done_body": "JSON.stringify({ status: 'done', result: 'sent ' + out.stage })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: out.invoice, decision: out.decision, rules: {{ stage: out.stage, reason: out.reason || null, "
                    f"next_stage: (out.next || {{}}).stage || null, next_date: (out.next || {{}}).due_on || null, approved_by: out.approved_by || null, template_version: {CFG}.template_version }} }})",
        "unsent_exception": exc("send failed", "'Not sent: ' + out.stage + '; it stays due for the next run'"),
        "unsent_log": f"JSON.stringify({{ recipe: '{R}', item: out.invoice, decision: 'unsent: ' + out.stage, rules: {{ stage: out.stage, template_version: {CFG}.template_version }} }})",
        "failed_exception": exc("write failed", "'Reminder list or approval write failed; check the invoice before the next run'"),
    })
    run.append(s.code(RULES, code, inputs))
    run.append(s.iterator("Each invoice", "{{" + f"{s.ref(RULES)}.result.items" + "}}"))
    it = s.ref("Each invoice")
    f = lambda k: "{{" + f"{it}.{k}" + "}}"  # noqa: E731
    rec_url = sp + "/reminders/" + f("invoice_q")
    to_queue = lambda name: [s.exception(f"{name}: exception queue", f("failed_exception")), s.ignore()]  # noqa: E731
    log = lambda tag: s.decision_log(f"Step 10: Decision log ({tag})", f("log_body"))  # noqa: E731
    list_failed = lambda name: [s.finish_key(f"{name}: mark key failed", f("key_q"), '{"status": "failed", "result": "sent; reminder list write failed"}'),  # noqa: E731
                                s.exception(f"{name}: exception queue", f("failed_exception")), s.ignore()]

    def template(tag: str, passed: list[dict]) -> list[dict]:
        """Steps 7 and 8: fill the template, check it; a failed check holds the reminder."""
        fill, check = f"{FILL}{tag}", f"{CHECK}{tag}"
        code, inputs = rule(N8N.FILL_JS, {"Config": config, RULES: f("self")}, input_node=RULES)
        steps = [s.code(fill, code, inputs)]
        code, inputs = rule(N8N.CHECK_JS, {"Config": config, RULES: f("self"), fill: "{{" + f"{s.ref(fill)}.result" + "}}"},
                            input_node=fill, bodies={
            "approval_body": f"JSON.stringify({{ id: $('{RULES}').item.json.approval_id, invoice: $('{RULES}').item.json.invoice, account: $('{RULES}').item.json.account, "
                             f"approver: {CFG}.ar_lead, status: 'pending', to: out.to, subject: out.subject, text: out.text, template_version: out.template_version }})",
            "mail_body": f"JSON.stringify({{ from: {CFG}.ar_mailbox, to: out.to, subject: out.subject, text: out.text }})",
            "held_exception": f"JSON.stringify({{ recipe: '{R}', item: $('{RULES}').item.json.invoice, reason: 'held: template check', detail: out.problems.join('; '), owner: {CFG}.ar_lead }})",
            "held_alert": f"JSON.stringify({{ to: [{CFG}.ar_lead], subject: 'Reminder held: invoice ' + $('{RULES}').item.json.invoice, text: out.problems.join('; ') }})",
            "held_log": f"JSON.stringify({{ recipe: '{R}', item: $('{RULES}').item.json.invoice, decision: 'held: ' + $('{RULES}').item.json.stage, "
                        f"rules: {{ stage: $('{RULES}').item.json.stage, problems: out.problems, template_version: {CFG}.template_version }} }})",
        })
        steps.append(s.code(check, code, inputs))
        ok = "{{" + f"{s.ref(check)}.result.ok" + "}}"
        ch = lambda k: "{{" + f"{s.ref(check)}.result.{k}" + "}}"  # noqa: E731
        held = [s.release_key(f"Step 8: Release key: held{tag}", f("reserve_body")),  # the stage stays due for the next run
                s.exception(f"Exception queue: held by step 8{tag}", ch("held_exception")),
                s.http(f"Step 8: Alert Aisha{tag}", "POST", cfg("messaging_url") + "/messages", body=ch("held_alert"), parse=False),
                s.decision_log(f"Step 8: Decision log: held{tag}", ch("held_log"))]
        steps.append(s.router(f"Step 8: Passes?{tag}", [
            (s.when("template check passes", ok, "true"), passed(ch)),
            (s.when("template check fails", ok, "true", "text:notequal"), held),
        ]))
        return steps

    def send_path(ch):
        """Steps 9 and 10 for a reminder that may send now."""
        send = s.http("Step 9: Send from the AR mailbox", "POST", cfg("mail_url") + "/outbox", body=ch("mail_body"), parse=False, onerror=[
            s.release_key("Release key: the stage stays due", f("reserve_body")),
            s.exception("Exception queue: send failed", f("unsent_exception")),
            s.decision_log("Decision log: unsent", f("unsent_log")), s.ignore()])
        stage = s.http("Step 10: Set the next stage and date", "PUT", rec_url, body=f("record_body"), parse=False,
                       onerror=list_failed("Step 10: Set the next stage and date"))
        handoff = f("handoff")
        return [send, stage, s.router("After the final notice?", [
            (s.when("next is the handoff", handoff, "true"),
             [s.http("Step 10: Open Aisha's handoff", "PUT", sp + "/handoffs/" + f("invoice_q"), body=f("handoff_body"), parse=False,
                     onerror=list_failed("Step 10: Open Aisha's handoff")),
              s.finish_key("Mark key done (handoff)", f("key_q"), f("done_body")), log("handoff")]),
            (s.when("another stage follows", handoff, "true", "text:notequal"),
             [s.finish_key("Mark key done", f("key_q"), f("done_body")), log("sent")]),
        ])]

    def final_path(ch):
        """Step 9: a final notice due waits for Aisha's approval."""
        return [s.http("Step 9: Ask Aisha to approve the final notice", "PUT", cfg("approvals_url") + "/requests/" + f("approval_q"),
                       body=ch("approval_body"), parse=False, onerror=to_queue("Step 9: Ask Aisha to approve the final notice")),
                log("final notice")]

    reserve = s.rpc("Step 6: Reserve key", "reserve_key", f("reserve_body"))
    send_steps = template("", send_path)
    send_steps[0]["filter"] = s.is_new_key("Step 6: Reserve key")  # a copy stops here: this invoice and stage were sent
    stop_tell = f("tell")
    outcome = f("outcome")
    run.append(s.router("Outcome", [
        (s.when("outcome is send", outcome, "send"), [reserve] + send_steps),
        (s.when("outcome is final", outcome, "final"), template(" (final notice)", final_path)),
        (s.when("outcome is stop", outcome, "stop"),
         [s.http("Steps 4 and 5: Record the stop", "PUT", rec_url, body=f("record_body"), parse=False, onerror=to_queue("Steps 4 and 5: Record the stop")),
          s.router("Tell Aisha?", [
              (s.when("part-paid or negative", stop_tell, "true"),
               [s.http("Step 4: Tell Aisha", "POST", cfg("messaging_url") + "/messages", body=f("tell_message"), parse=False,
                       onerror=to_queue("Step 4: Tell Aisha")), log("stop, Aisha told")]),
              (s.when("paid, disputed or held", stop_tell, "true", "text:notequal"), [log("stop")]),
          ])]),
        (s.when("outcome is list", outcome, "list"),
         [s.http("Step 3: Add to the reminder list", "PUT", rec_url, body=f("record_body"), parse=False, onerror=to_queue("Step 3: Add to the reminder list"))]),
        (s.when("outcome is wait", outcome, "wait"), [log("wait")]),
    ]))

    run_today = out(GATE, "run")
    flow.append(s.router("Run today?", [
        (s.when("export and intake current", run_today, "true"), run),
        (s.when("no run today", run_today, "true", "text:notequal"), no_run),
    ]))
    return flow


def morning() -> Scenario:
    s = Scenario(R, "R8.1 Send staged overdue reminders that stop on payment or dispute", "schedule", test_key=M,
                 schedule="Monday to Friday at 07:00, after your open-invoice export is due")
    s.flow.append(s.config(CONFIG))
    s.flow += s.stop_flag()
    s.flow += reminders(s, s.continue_unless_stopped(), decision=False)
    return s


def final_notice_decision() -> Scenario:
    s = Scenario(R, "R8.1 Send staged overdue reminders: Aisha's decision on a final notice", "webhook", test_key="r8-1-final-notice-decision")
    s.flow.append(s.webhook(A))
    s.flow.append(s.config(CONFIG))
    s.flow += s.stop_flag()
    stop = s.continue_unless_stopped()["conditions"][0][0]
    approved = {"a": "{{1.approved}}", "b": "true", "o": "text:equal"}
    rejected = dict(approved, o="text:notequal")
    # Unapproved, the final notice waits a day; the log entry's body is built in Code, as every data-carrying body is.
    code, inputs = rule("return [{ json: {} }];", {}, trigger=(A, ["invoice", "by"]), bodies={
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: String($('{A}').first().json.body.invoice), decision: 'final notice not approved; waits a day', "
                    f"rules: {{ by: $('{A}').first().json.body.by || null }} }})",
    })
    log_entry = s.code("Step 9: Decision log entry: not approved", code, inputs)
    not_approved = [log_entry, s.decision_log("Step 9: Decision log: not approved", "{{" + f"{s.ref('Step 9: Decision log entry: not approved')}.result.log_body" + "}}")]
    flow = reminders(s, {"name": "stop flag not set; approved", "conditions": [[stop, approved]]}, decision=True)
    not_approved[0]["filter"] = {"name": "stop flag not set; not approved", "conditions": [[stop, rejected]]}
    s.flow.append(s.router("Step 9: Approved?", [(None, flow), (None, not_approved)]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R8.1/make/, scenario)."""
    return [("blueprint.json", morning()), ("decision.blueprint.json", final_notice_decision())]
