"""R8.2 Prepare and send monthly statements for trade accounts, as Make scenarios: rules only, no AI step.

Source: book Chapter 8, recipe R8.2, build steps 1 to 9 (recipes/R8.2/build-spec.md).
The rules are the n8n build's own JavaScript (tools/builds/r8_2.py), run through n8n_rule.
Three scenarios, because a Make scenario has one trigger: the statement build (schedule, every
weekday at 09:00, going on only on the month's first working day), the same build run again
(webhook, step 9: after a late export, a failed send or a released account) and Aisha's
decision on the batch (webhook, step 8).
Book build note: Make stores each run's data in its history; for statements, set the scenario's
"Data is confidential" option, the Make equivalent of n8n's "Do not save" (book Chapter 8).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R8.2"
N8N = n8n_build(R)
S, RUN, DEC = N8N.S, N8N.RUN, N8N.DEC
CONFIG = {
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
}
LEAD = "$('Config').first().json.ar_lead"


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
    sends its error output to the same next step. The rule that follows reports it missing."""
    return {"id": s._id(f"_resume{s._next}"), "module": "builtin:Resume", "version": 1, "parameters": {},
            "mapper": {"data": ""}, "metadata": {"designer": {"x": 0, "y": 0}}}


def start(s: Scenario, webhook: str | None):
    if webhook:
        s.flow.append(s.webhook(webhook))
    s.flow.append(s.config(CONFIG))
    s.flow += s.stop_flag()
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    out = lambda step, f: "{{" + f"{s.ref(step)}.result.{f}" + "}}"  # noqa: E731
    return cfg, out


def statements(scheduled: bool) -> Scenario:
    """Steps 1 to 7. The schedule's scenario runs step 1's rule; a run again always goes on,
    so its scenario has no step 1 rule (in n8n that rule only asks which trigger ran)."""
    if scheduled:
        s = Scenario(R, "R8.2 Prepare and send monthly statements for trade accounts", "schedule",
                     test_key=S, schedule="every weekday at 09:00, after both month-end exports are saved")
    else:
        s = Scenario(R, "R8.2 Prepare and send monthly statements: run again", "webhook", test_key="r8-2-run-again")
    cfg, out = start(s, None if scheduled else RUN)
    config = "{{" + f"{s.ref('Config')}.result" + "}}"
    first = s.continue_unless_stopped()
    if scheduled:
        day = "Step 1: Rule: first working day, or a run again?"
        code, inputs = rule(N8N.DAY_JS, {}, executed=(S,))
        m = s.code(day, code, inputs)
        m["filter"] = first
        s.flow.append(m)
        first = s.when("first working day", out(day, "go"), "true")
    exp = cfg("sharepoint_url") + "/exports/"
    bal = s.http("Step 2: Read the balances export", "GET", exp + "balances", onerror=[resume(s)])
    bal["filter"] = first
    s.flow.append(bal)
    s.flow.append(s.http("Step 2: Read the open-items export", "GET", exp + "open-items", onerror=[resume(s)]))
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    g = "Step 2: Rule: exports present, one cut-off?"
    code, inputs = rule(N8N.GATE_JS, {
        "Config": config, "Step 2: Read the balances export": data("Step 2: Read the balances export"),
        "Step 2: Read the open-items export": data("Step 2: Read the open-items export"),
    }, bodies={
        "no_run_log": f"JSON.stringify({{ recipe: '{R}', item: 'statements ' + out.month, decision: 'no run', rules: {{ problems: out.problems }} }})",
        "alert_message": f"JSON.stringify({{ to: [{LEAD}], subject: 'Statements for ' + out.month + ': nothing built', text: out.problems.join('; ') }})",
    })
    s.flow.append(s.code(g, code, inputs))

    run = [s.http("Step 4: Read the dispute list", "GET", cfg("sharepoint_url") + "/disputes", query={"_wrap": "1", "status": "open"}),
           s.http("Read CRM contacts (for step 6)", "GET", cfg("crm_url") + "/accounts", query={"_wrap": "1"}),
           s.http("Step 5: Read statements already sent", "GET", s.table("/key_log"),
                  query={"recipe": f"eq.{R}", "key": "like.*:" + out(g, "month"), "select": "key"})]
    rb = "Rules: steps 3 to 6"
    code, inputs = rule(N8N.RULES_JS, {
        "Config": config, g: "{{" + f"{s.ref(g)}.result" + "}}",
        "Step 2: Read the balances export": data("Step 2: Read the balances export"),
        "Step 2: Read the open-items export": data("Step 2: Read the open-items export"),
        "Step 4: Read the dispute list": data("Step 4: Read the dispute list"),
        "Read CRM contacts (for step 6)": data("Read CRM contacts (for step 6)"),
        "Step 5: Read statements already sent": data("Step 5: Read statements already sent"),
    }, items=("Step 5: Read statements already sent",), input_node="Config", bodies={
        "anything": "out.count > 0 || out.held.length > 0",
        "approval_body": "JSON.stringify(out)",
        "batch_log": f"JSON.stringify({{ recipe: '{R}', item: 'statements ' + out.month, decision: 'batch sent for approval', "
                     "rules: { count: out.count, total_due: out.total_due, held: out.held, skipped: out.skipped } })",
        "failed_body": f"JSON.stringify({{ recipe: '{R}', item: out.id, reason: 'write failed', detail: 'The batch approval was not written; run again', owner: {LEAD} }})",
    })
    run.append(s.code(rb, code, inputs))
    approval = s.http("Step 7: Send Aisha one approval", "PUT", cfg("approvals_url") + "/requests/{{encodeURL(" + f"{s.ref(rb)}.result.id" + ")}}",
                      body=out(rb, "approval_body"), parse=False,
                      onerror=[s.exception("Exception queue: approval write failed", out(rb, "failed_body")), s.ignore()])
    approval["filter"] = s.when("anything to approve", out(rb, "anything"), "true")  # otherwise every statement was sent
    run += [approval, s.decision_log("Step 7: Decision log: batch", out(rb, "batch_log"))]

    current = out(g, "run")
    s.flow.append(s.router("Exports current?", [
        (s.when("exports current", current, "true"), run),
        (s.when("exports missing or cut-offs differ", current, "true", "text:notequal"),
         [s.decision_log("Step 2: Decision log: no run", out(g, "no_run_log")),
          s.http("Step 2: Alert Aisha", "POST", cfg("messaging_url") + "/messages", body=out(g, "alert_message"), parse=False)]),
    ]))
    return s


def batch_decision() -> Scenario:
    s = Scenario(R, "R8.2 Prepare and send monthly statements: Aisha's decision on the batch", "webhook", test_key="r8-2-batch-decision")
    cfg, out = start(s, DEC)
    config = "{{" + f"{s.ref('Config')}.result" + "}}"
    trig = (DEC, ["approved", "by"])
    by = f"($('{DEC}').first().json.body.by || null)"
    find = "Step 8: Find this month's batch"
    code, inputs = rule(N8N.FIND_JS, {"Config": config}, trigger=trig, bodies={
        # The batch read below is this month's by its id, so its month is this one.
        "rejected_log": f"JSON.stringify({{ recipe: '{R}', item: 'statements ' + out.month, decision: 'batch rejected; nothing sent', rules: {{ by: {by} }} }})",
    })
    m = s.code(find, code, inputs)
    m["filter"] = s.continue_unless_stopped()
    s.flow.append(m)
    s.flow.append(s.http("Step 8: Read the batch", "GET", cfg("approvals_url") + "/requests/{{encodeURL(" + f"{s.ref(find)}.result.id" + ")}}"))
    split = "Step 8: One item per statement"
    code, inputs = rule(N8N.SPLIT_JS, {"Config": config, "Step 8: Read the batch": "{{" + f"{s.ref('Step 8: Read the batch')}.data" + "}}"},
                        trigger=trig, many=True, bodies={
        "key_q": "encodeURIComponent(out.key)",
        "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: out.key }})",
        "mail_body": "JSON.stringify({ from: $('Config').first().json.ar_mailbox, to: out.to, subject: out.subject, text: out.text })",
        "sent_log": f"JSON.stringify({{ recipe: '{R}', item: out.account, decision: 'sent statement ' + out.month, "
                    f"rules: {{ month: out.month, balance: out.balance, total_due: out.total_due, held: false, by: {by} }} }})",
        "unsent_exception": f"JSON.stringify({{ recipe: '{R}', item: out.account, reason: 'send failed', "
                            f"detail: 'Statement for ' + out.month + ' not sent; Owen restarts the run', owner: {LEAD} }})",
        "unsent_log": f"JSON.stringify({{ recipe: '{R}', item: out.account, decision: 'unsent statement ' + out.month, rules: {{ month: out.month, balance: out.balance }} }})",
    })
    sp = s.code(split, code, inputs)
    each = "Each approved statement"
    it_mod = s.iterator(each, "{{" + f"{s.ref(split)}.result.items" + "}}")
    it = s.ref(each)
    f = lambda k: "{{" + f"{it}.{k}" + "}}"  # noqa: E731
    reserve = s.rpc("Step 5: Reserve key", "reserve_key", f("reserve_body"))
    send = s.http("Step 8: Send the statement", "POST", cfg("mail_url") + "/outbox", body=f("mail_body"), parse=False, onerror=[
        s.release_key("Release key: logged unsent", f("reserve_body")),  # unsent: the next run includes this account again
        s.exception("Exception queue: send failed", f("unsent_exception")),
        s.decision_log("Decision log: unsent", f("unsent_log")),
        s.ignore()])
    send["filter"] = s.is_new_key("Step 5: Reserve key")  # a copy stops here: this account's statement was sent
    approved = s.when("approved", "{{1.approved}}", "true")
    s.flow.append(s.router("Step 8: Approved?", [
        (approved, [sp, it_mod, reserve, send,
                    s.finish_key("Mark key done", f("key_q"), '{"status": "done", "result": "sent"}'),
                    s.decision_log("Step 8: Decision log: sent", f("sent_log"))]),
        (s.when("not approved", "{{1.approved}}", "true", "text:notequal"),
         [s.decision_log("Step 8: Decision log: rejected", out(find, "rejected_log"))]),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R8.2/make/, scenario)."""
    return [("blueprint.json", statements(True)), ("run-again.blueprint.json", statements(False)),
            ("decision.blueprint.json", batch_decision())]
