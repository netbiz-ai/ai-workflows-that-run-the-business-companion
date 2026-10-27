"""R7.3 Stop and verify any change to a supplier's bank details, as Make scenarios: rules only, no AI step.

Source: book Chapter 7, recipe R7.3, build steps 1 to 9 and the rules that follow them
(recipes/R7.3/build-spec.md). The rules are the n8n build's own JavaScript (tools/builds/r7_3.py),
run through n8n_rule. Five scenarios, because a Make scenario has one trigger, all webhooks:
an R7.1 record saved, a supplier message, a new export (step 1's three sources, each running
steps 2 to 6), the caller's logged call-back (steps 7 to 9) and the check before each payment run.
Any difference holds the supplier; only a call to the number on file, logged by the caller, and
entry by a second person lift it. It never accepts a change from an email or invoice.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R7.3"
N8N = n8n_build(R)
CONFIG = {
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
}
CFG = "$('Config').first().json"
DIFF = "Step 2: Rule: differs from the register?"


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


def start(s: Scenario, webhook: str):
    s.flow.append(s.webhook(webhook))
    s.flow.append(s.config(CONFIG))
    s.flow += s.stop_flag()
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    out = lambda step, f: "{{" + f"{s.ref(step)}.result.{f}" + "}}"  # noqa: E731
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    return cfg, out, data, "{{" + f"{c}.result" + "}}"


def checks(s: Scenario, from_step: str, js: str, sources: dict) -> None:
    """Step 1's rule turns the trigger into checks, one per supplier; steps 2 to 6 run for each.
    Make's iterator is n8n's pass-through "Step 2: Checks"; each bundle carries its check as JSON."""
    cfg = lambda f: "{{" + f"{s.ref('Config')}.result.{f}" + "}}"  # noqa: E731
    out = lambda step, f: "{{" + f"{s.ref(step)}.result.{f}" + "}}"  # noqa: E731
    code, inputs = rule(js, sources, many=True, bodies={"check_json": "JSON.stringify(out)"})
    s.flow.append(s.code(from_step, code, inputs))
    s.flow.append(s.iterator("Step 2: Checks", "{{" + f"{s.ref(from_step)}.result.items" + "}}"))
    it = s.ref("Step 2: Checks")
    s.flow.append(s.http("Step 2: Read the register", "GET", cfg("register_url") + "/register",
                         query={"_wrap": "1", "supplier_id": "{{" + f"{it}.supplier_id" + "}}"}))
    s.flow.append(s.http("Step 2: Read the supplier", "GET", cfg("suppliers_url") + "/suppliers",
                         query={"_wrap": "1", "id": "{{" + f"{it}.supplier_id" + "}}"}))
    log = lambda decision: (f"JSON.stringify({{ recipe: '{R}', item: out.supplier_id, decision: '{decision}', rules: out.rules }})")  # noqa: E731
    code, inputs = rule(N8N.DIFF_JS, {
        "Config": "{{" + f"{s.ref('Config')}.result" + "}}",
        "Step 2: Checks": "{{" + f"{it}.check_json" + "}}",
        "Step 2: Read the register": "{{" + f"{s.ref('Step 2: Read the register')}.data" + "}}",
        "Step 2: Read the supplier": "{{" + f"{s.ref('Step 2: Read the supplier')}.data" + "}}",
    }, input_node="Step 2: Checks", bodies={
        "check_body": "JSON.stringify({ supplier_id: out.supplier_id, record_id: out.record_id, source: out.source, ref: out.ref, "
                      "differs: out.differs, hold: out.differs || (out.held_before && !out.lift), checked_on: out.checked_on, checked_at: new Date().toISOString() })",
        "supplier_q": "encodeURIComponent(out.supplier_id)",
        "key_q": "encodeURIComponent(out.key)",
        "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: out.key }})",
        "failed_body": f"JSON.stringify({{ recipe: '{R}', item: out.supplier_id, reason: 'write failed', "
                       f"detail: 'A check, hold or task write failed, never retried; hold the supplier by hand and check the log', owner: {CFG}.workflow_owner }})",
        # n8n's "Result: ..." steps only name the decision; here the decision log bodies carry it.
        "log_no_hold": log("no hold"),
        "log_lifted": log("hold lifted: export shows the confirmed change"),
        "log_open_hold": log("held; open hold, no second task"),
        "log_tasked": log("held; caller tasked"),
    })
    s.flow.append(s.code(DIFF, code, inputs))
    d = lambda f: out(DIFF, f)  # noqa: E731
    failed = lambda step: s.write_failed(step, d("key_q"), d("failed_body"))  # noqa: E731
    s.flow.append(s.http("Step 3: Log the check", "POST", cfg("checks_url") + "/checks", body=d("check_body"), parse=False,
                         onerror=failed("Step 3: Log the check")))
    supplier_url = cfg("suppliers_url") + "/suppliers/" + d("supplier_q")

    code, inputs = rule(N8N.TASK_JS, {DIFF: "{{" + f"{s.ref(DIFF)}.result" + "}}", "Config": "{{" + f"{s.ref('Config')}.result" + "}}"},
                        input_node=DIFF, bodies={"task_body": "JSON.stringify(out)"})
    task = s.code("Step 6: Caller's task", code, inputs)
    new_key = [task,
               s.http("Step 6: Send the caller a task", "POST", cfg("tasks_url") + "/tasks", body=out("Step 6: Caller's task", "task_body"),
                      parse=False, onerror=failed("Step 6: Send the caller a task")),
               s.finish_key("Mark key done", d("key_q"), '{"status": "done", "result": "task sent"}'),
               s.decision_log("Decision log (held, task sent)", d("log_tasked"))]
    held = [s.http("Step 4: Set the hold flag", "PATCH", supplier_url, parse=False,
                   body='{"hold": true, "hold_reason": "bank-detail difference"}', onerror=failed("Step 4: Set the hold flag")),
            s.rpc("Step 5: Reserve key", "reserve_key", d("reserve_body"))]
    reserved = "{{" + f"{s.ref('Step 5: Reserve key')}.data" + "}}"
    held.append(s.router("New key?", [
        (s.is_new_key("Step 5: Reserve key"), new_key),
        (s.when("a copy: the hold already has a task", reserved, "true", "text:notequal"),
         [s.decision_log("Decision log (open hold, no second task)", d("log_open_hold"))]),
    ]))
    same = [s.router("Confirmed change now shown?", [
        (s.when("export shows the confirmed change", d("lift"), "true"),
         [s.http("Step 8: Lift the hold", "PATCH", supplier_url, parse=False, body='{"hold": false, "hold_reason": null}',
                 onerror=failed("Step 8: Lift the hold")),
          s.decision_log("Decision log (hold lifted)", d("log_lifted"))]),
        (s.when("nothing to lift", d("lift"), "true", "text:notequal"), [s.decision_log("Decision log (no hold)", d("log_no_hold"))]),
    ])]
    s.flow.append(s.router("Differs?", [
        (s.when("differs from the register", d("differs"), "true"), held),
        (s.when("same as the register", d("differs"), "true", "text:notequal"), same),
    ]))


def from_record() -> Scenario:
    s = Scenario(R, "R7.3 Stop and verify any change to a supplier's bank details: R7.1 record", "webhook", test_key="r7-3-record")
    cfg, out, data, config = start(s, "Step 1: R7.1 record saved")
    read = s.http("Step 1: Read the R7.1 record", "GET", cfg("review_url") + "/records/{{encodeURL(1.record_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    checks(s, "Step 1: From the record", N8N.FROM_RECORD_JS, {"Step 1: Read the R7.1 record": data("Step 1: Read the R7.1 record")})
    return s


def from_message() -> Scenario:
    s = Scenario(R, "R7.3 Stop and verify any change to a supplier's bank details: supplier message", "webhook", test_key="r7-3-message")
    cfg, out, data, config = start(s, "Step 1: Supplier message")
    read = s.http("Step 1: Read the message", "GET", cfg("mailbox_url") + "/messages/{{encodeURL(1.message_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    s.flow.append(s.http("Step 1: Find the sender's supplier", "GET", cfg("suppliers_url") + "/suppliers",
                         query={"_wrap": "1", "contact_email": "{{" + f"{s.ref('Step 1: Read the message')}.data.from" + "}}"}))
    checks(s, "Step 1: From the message", N8N.FROM_MESSAGE_JS, {
        "Config": config, "Step 1: Read the message": data("Step 1: Read the message"),
        "Step 1: Find the sender's supplier": data("Step 1: Find the sender's supplier")})
    return s


def from_export() -> Scenario:
    s = Scenario(R, "R7.3 Stop and verify any change to a supplier's bank details: new export", "webhook", test_key="r7-3-export")
    cfg, out, data, config = start(s, "Step 1: New export")
    read = s.http("Step 1: Read the export", "GET", cfg("exports_url") + "/exports/{{encodeURL(1.export_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    checks(s, "Step 1: From the export", N8N.FROM_EXPORT_JS, {"Step 1: Read the export": data("Step 1: Read the export")})
    return s


def callback() -> Scenario:
    T = N8N.T_CALL
    s = Scenario(R, "R7.3 Stop and verify any change to a supplier's bank details: call-back logged", "webhook", test_key="r7-3-callback")
    cfg, out, data, config = start(s, T)
    read = s.http("Step 7: Read the register entry", "GET", cfg("register_url") + "/register",
                  query={"_wrap": "1", "supplier_id": "{{1.supplier_id}}"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    cb = f"$('{T}').first().json.body"
    task = lambda text: (f"JSON.stringify({{ assignee: {CFG}.finance_assistant, supplier_id: {cb}.supplier_id, status: 'open', instruction: '{text}' }})")  # noqa: E731
    exc = lambda reason, detail, owner: (f"JSON.stringify({{ recipe: '{R}', item: {cb}.supplier_id, reason: '{reason}', detail: '{detail}', owner: {CFG}.{owner} }})")  # noqa: E731
    s7 = "Step 7: Rule: call-back outcome"
    code, inputs = rule(N8N.CALL_JS, {"Config": config, "Step 7: Read the register entry": data("Step 7: Read the register entry")},
                        trigger=(T, ["supplier_id", "task_id", "number_dialed", "outcome", "new_bank_account", "new_phone", "logged_by"]), bodies={
        "entry_body": "JSON.stringify(out.entry)",
        "register_q": "encodeURIComponent(out.register_id)",
        "enter_task": task("The caller confirmed a bank-detail change on the number on file. Enter it in the ledger; the hold lifts when the next export shows it."),
        "release_task": task("The caller confirmed no change on the number on file. Release the hold."),
        "release_keys_body": f"JSON.stringify({{ p_recipe: '{R}', p_item: {cb}.supplier_id }})",
        "fraud_message": f"JSON.stringify({{ to: {CFG}.fraud_report_to, subject: 'Suspected payment fraud: supplier ' + {cb}.supplier_id, "
                         "text: 'A bank-detail change was not confirmed on the number on file. The hold stays.' })",
        "fraud_exception": exc("suspected fraud", "Change not confirmed on the number on file; hold stays", "fraud_report_to"),
        "wrong_number_exception": exc("call to another number", "Logged number differs from the register; hold stays; ring the register number", "bank_caller"),
        "failed_body": exc("write failed", "A register, hold, task or report write failed after a call-back, never retried; finish it by hand", "workflow_owner"),
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {cb}.supplier_id, decision: 'call-back: ' + out.route, rules: out.rules }})",
    })
    s.flow.append(s.code(s7, code, inputs))
    r = lambda f: out(s7, f)  # noqa: E731

    def write(name, method, url, body):
        """A call-back write never retries; a failure goes to the exception queue and ends the run."""
        return s.http(name, method, url, body=body, parse=False,
                      onerror=[s.exception(f"{name}: exception queue", r("failed_body")), s.ignore()])

    tasks = cfg("tasks_url") + "/tasks"
    close = lambda tag: [s.rpc(f"Step 8: Close the hold's keys ({tag})", "release_keys_for", r("release_keys_body"))]  # noqa: E731
    log = lambda tag: s.decision_log(f"Step 7: Decision log ({tag})", r("log_body"))  # noqa: E731
    route = r("route")
    s.flow.append(s.router("Call-back outcome", [
        (s.when("confirmed change", route, "change"),
         [write("Step 8: Save the confirmed details to the register", "PUT", cfg("register_url") + "/register/" + r("register_q"), r("entry_body")),
          write("Step 8: Hold until the export shows it", "PATCH", cfg("suppliers_url") + "/suppliers/{{encodeURL(1.supplier_id)}}",
                '{"hold": true, "hold_reason": "confirmed change; awaiting export"}'),
          write("Step 8: Ask the finance assistant to enter it", "POST", tasks, r("enter_task"))] + close("change") + [log("change")]),
        (s.when("confirmed, no change", route, "no change"),
         [write("Step 8: Ask the finance assistant to release", "POST", tasks, r("release_task"))] + close("no change") + [log("no change")]),
        (s.when("not confirmed", route, "not confirmed"),
         [write("Step 9: Report suspected fraud", "POST", cfg("messaging_url") + "/messages", r("fraud_message")),
          s.exception("Step 9: Exception queue: hold stays", r("fraud_exception")), log("not confirmed")]),
        (s.when("wrong number", route, "wrong number"),
         [s.exception("Exception queue: call to another number", r("wrong_number_exception")), log("wrong number")]),
    ]))
    return s


def pre_run() -> Scenario:
    s = Scenario(R, "R7.3 Stop and verify any change to a supplier's bank details: before each payment run", "webhook", test_key="r7-3-pre-run")
    cfg, out, data, config = start(s, N8N.T_RUN)
    read = s.http("Pre-run: Read the export checks", "GET", cfg("checks_url") + "/checks", query={"_wrap": "1", "source": "export"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    s.flow.append(s.http("Pre-run: Read the suppliers", "GET", cfg("suppliers_url") + "/suppliers", query={"_wrap": "1"}))
    p = "Pre-run: Rule: export check logged?"
    code, inputs = rule(N8N.PRERUN_JS, {
        "Config": config, "Pre-run: Read the export checks": data("Pre-run: Read the export checks"),
        "Pre-run: Read the suppliers": data("Pre-run: Read the suppliers"),
    }, bodies={
        "confirm_message": f"JSON.stringify({{ to: [{CFG}.bank_caller, {CFG}.pre_run_reviewer], subject: 'Payment run check', "
                           "text: 'Export check logged. Held suppliers: ' + (out.held.join(', ') || 'none') + "
                           "'. Confirm no bill is from a held supplier and every bill has a logged approval. Whoever releases the run must not have approved its bills.' })",
        "alert_message": f"JSON.stringify({{ to: {CFG}.kill_switch_alert, subject: 'No R7.3 export check before the payment run', "
                         "text: 'No export check is logged today, so every supplier is held until the check runs.' })",
        # n8n's "Pre-run: Every supplier" Code step splits out.all into items; Make's iterator does that split.
        "every": f"out.all.map(id => ({{ id, supplier_q: encodeURIComponent(id), failed_body: JSON.stringify({{ recipe: '{R}', item: id || 'supplier', "
                 f"reason: 'write failed', detail: 'Pre-run hold write failed; hold this supplier by hand', owner: {CFG}.workflow_owner }}) }}))",
    })
    s.flow.append(s.code(p, code, inputs))
    msg = cfg("messaging_url") + "/messages"
    each = s.iterator("Pre-run: Every supplier", out(p, "every"))
    it = s.ref("Pre-run: Every supplier")
    hold = s.http("Pre-run: Hold the supplier", "PATCH", cfg("suppliers_url") + "/suppliers/{{" + f"{it}.supplier_q" + "}}", parse=False,
                  body='{"hold": true, "hold_reason": "no export check before the payment run"}',
                  onerror=[s.exception("Exception queue: hold write failed", "{{" + f"{it}.failed_body" + "}}"), s.ignore()])
    logged = out(p, "logged")
    s.flow.append(s.router("Logged?", [
        (s.when("export check logged today", logged, "true"),
         [s.http("Pre-run: Ask the caller and AP owner to confirm", "POST", msg, body=out(p, "confirm_message"), parse=False)]),
        (s.when("no export check today", logged, "true", "text:notequal"),
         [s.http("Pre-run: Alert, R7.3 check missing", "POST", msg, body=out(p, "alert_message"), parse=False), each, hold]),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R7.3/make/, scenario)."""
    return [("blueprint.json", from_record()), ("message.blueprint.json", from_message()), ("export.blueprint.json", from_export()),
            ("callback.blueprint.json", callback()), ("pre-run.blueprint.json", pre_run())]
