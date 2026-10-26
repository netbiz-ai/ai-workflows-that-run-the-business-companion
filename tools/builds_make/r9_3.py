"""R9.3 Take leave requests, check the balance and route to the manager, as Make scenarios: rules only, no AI step.

Source: book Chapter 9, recipe R9.3, build steps 1 to 8 (recipes/R9.3/build-spec.md).
The rules are the n8n build's own JavaScript (tools/builds/r9_3.py), run through n8n_rule.
Three scenarios, because a Make scenario has one trigger: the request or cancellation
(webhook), the manager's decision (webhook) and the morning reminders (schedule, daily at 08:00).
The rules read the webhook body as n8n's $('<trigger>').first().json.body; a Make webhook
step's output cannot be mapped whole, so trigger_body() passes its fields one by one and
the prelude rebuilds that body before the rule runs.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R9.3"
N8N = n8n_build(R)
T, D, M = N8N.T, N8N.D, N8N.M
CONFIG = {
    "employees_url": "https://<your employee list API>",
    "balances_url": "https://<your daily balance export API>",
    "requests_url": "https://<your leave request list API>",
    "record_list_url": "https://<your HR to-record list API>",
    "messaging_url": "https://<your messaging API>",
    "hr_owner": "<your HR owner>",
    "protected_types": ["<leave types that go to HR alone, such as sick and family>"],
    "notice_days": {"<leave type>": 0},
    "remind_working_days": 2,
    "standin_working_days": 4,
}
# JavaScript shorthands for the bodies, as in the n8n build.
B = f"$('{T}').first().json.body"
CFG = "$('Config').first().json"
TODAY = "new Date().toISOString().slice(0, 10)"


def trigger_body(trigger: str, fields: tuple[str, ...], webhook_id: int) -> tuple[str, dict[str, str]]:
    """(prelude, inputs): the webhook's fields, rebuilt as n8n's $('<trigger>').first().json.body."""
    inputs = {f"t_{f}": "{{" + f"{webhook_id}.{f}" + "}}" for f in fields}
    body = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in fields)
    prelude = (f"// The webhook's fields, as the rule reads them in n8n: $('{trigger}').first().json.body.\n"
               f"DATA[{json.dumps(trigger)}] = [{{ json: {{ body: {{ {body} }} }} }}];")
    return prelude, inputs


def rule(js: str, sources: dict[str, str], trigger: tuple[str, tuple[str, ...]] | None = None, **kw):
    """n8n_rule, with the scenario's webhook body added when the rule reads it."""
    if not trigger:
        return n8n_rule(js, sources, **kw)
    prelude, extra = trigger_body(trigger[0], trigger[1], 1)
    code, inputs = n8n_rule(js, sources, prelude=prelude, **kw)
    return code, {**extra, **inputs}


def exc(fields: str) -> str:
    """An exception-queue body: recipe plus the given JavaScript object fields."""
    return f"JSON.stringify({{ recipe: '{R}', {fields} }})"


def start(s: Scenario, trigger: str | None) -> tuple:
    if trigger:
        s.flow.append(s.webhook(trigger))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    s.flow += s.stop_flag()
    return (lambda f: "{{" + f"{c}.result.{f}" + "}}"), "{{" + f"{c}.result" + "}}"


def on_fail(s: Scenario, step: str, body: str) -> list[dict]:
    """A write's error route that only adds the exception-queue row: the n8n build sends this
    write's error output straight to an exception step, with no key to mark failed."""
    return [s.exception(f"{step}: exception queue", body), s.ignore()]


def request_or_cancellation() -> Scenario:
    s = Scenario(R, "R9.3 Take leave requests: request or cancellation", "webhook", test_key="r9-3-leave")
    cfg, cfg_all = start(s, T)
    fields = ("request_id", "employee", "type", "start", "end", "action")
    msg = cfg("messaging_url") + "/messages"
    req_url = cfg("requests_url") + "/requests/{{encodeURL(1.request_id)}}"

    read = s.http("Step 2: Read the employee list", "GET", cfg("employees_url") + "/employees",
                  query={"_wrap": "1", "email": "{{1.employee}}"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    emp = "out.employee"
    key = f"{emp}.id + ':' + {B}.type + ':' + {B}.start + ':' + {B}.end"
    listed = lambda js: f"({emp} ? {js} : null)"  # noqa: E731  (bodies for a listed requester only)
    code, inputs = rule(N8N.ROUTE_JS, {"Config": cfg_all, "Step 2: Read the employee list": "{{" + f"{s.ref('Step 2: Read the employee list')}.data" + "}}"},
                        trigger=(T, fields), bodies={
        "reserve_body": listed(f"JSON.stringify({{ p_recipe: '{R}', p_key: {key}, p_reopen_done: true }})"),
        "hr_body": listed(f"JSON.stringify({{ id: {B}.request_id, employee_id: {emp}.id, employee: {B}.employee, name: {emp}.name, type: {B}.type, "
                          f"start: {B}.start, end: {B}.end, status: 'with HR', decider: {CFG}.hr_owner, sent_on: {TODAY} }})"),
        "hr_message": listed(f"JSON.stringify({{ to: {CFG}.hr_owner, subject: 'Leave request ' + {B}.request_id + ' for you alone', "
                             f"text: {emp}.name + ': ' + {B}.type + ' leave, ' + {B}.start + ' to ' + {B}.end + '. Not sent to the manager.' }})"),
        "hr_log_body": f"JSON.stringify({{ recipe: '{R}', item: {B}.request_id, decision: 'to HR alone', rules: {{ route: 'protected type' }} }})",
        "unlisted_body": exc(f"item: {B}.request_id, reason: 'unlisted requester', "
                             f"detail: 'Requester ' + {B}.employee + ' is not on the employee list; nothing sent', owner: {CFG}.hr_owner"),
        "unlisted_message": f"JSON.stringify({{ to: {CFG}.hr_owner, subject: 'Leave request from an unlisted requester', "
                            f"text: {B}.employee + ' asked for ' + {B}.type + ' leave, ' + {B}.start + ' to ' + {B}.end + '. Nothing was sent.' }})",
        "failed_body": exc(f"item: {B}.request_id, reason: 'write failed', detail: 'A leave write failed, never retried', owner: {CFG}.hr_owner"),
    })
    s.flow.append(s.code("Step 2: Rule: listed? protected?", code, inputs))
    ro = s.ref("Step 2: Rule: listed? protected?")
    out = lambda f, n=ro: "{{" + f"{n}.result.{f}" + "}}"  # noqa: E731

    # ---- Step 2: sick or family leave to Aisha alone ---------------------------------
    hr = [s.http("Step 2: To HR alone", "PUT", req_url, body=out("hr_body"), parse=False,
                 onerror=on_fail(s, "Step 2: To HR alone", out("failed_body"))),
          s.http("Step 2: Send it to Aisha", "POST", msg, body=out("hr_message"), parse=False,
                 onerror=on_fail(s, "Step 2: Send it to Aisha", out("failed_body"))),
          s.decision_log("Step 2: Decision log: to HR alone", out("hr_log_body"))]

    # ---- Step 2: an unlisted requester gets nothing sent; Aisha is told -------------------
    unlisted = [s.exception("Step 2: Exception queue: unlisted requester", out("unlisted_body")),
                s.http("Step 2: Tell Aisha", "POST", msg, body=out("unlisted_message"), parse=False)]

    # ---- Step 8 (cancellation): mark it, Aisha reverses it, the employee is told -----------
    can_read = s.http("Step 8: Read the request to cancel", "GET", cfg("requests_url") + "/requests",
                      query={"_wrap": "1", "id": "{{1.request_id}}"})
    can = "out"
    code, inputs = rule(N8N.CANCEL_JS, {"Config": cfg_all, "Step 8: Read the request to cancel": "{{" + f"{s.ref('Step 8: Read the request to cancel')}.data" + "}}"},
                        trigger=(T, fields), bodies={
        "id_q": "encodeURIComponent(out.id || '')",
        "key_q": "encodeURIComponent(out.key || '')",
        "cancel_body": f"JSON.stringify({{ status: 'cancelled', cancelled_on: {TODAY} }})",
        "reverse_message": f"JSON.stringify({{ to: {CFG}.hr_owner, subject: 'Leave cancelled: ' + {can}.id, "
                           f"text: {can}.name + ' cancelled ' + {can}.type + ' leave, ' + {can}.start + ' to ' + {can}.end + ' (was ' + {can}.was + '). Reverse it if recorded.' }})",
        "notify_message": f"JSON.stringify({{ to: {can}.employee, subject: 'Your leave request ' + {can}.id + ' is cancelled', "
                          f"text: {can}.type + ' leave, ' + {can}.start + ' to ' + {can}.end + ' is cancelled.' }})",
        "done_body": "JSON.stringify({ status: 'done', result: 'closed: cancelled' })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {can}.id, decision: 'cancelled', rules: {{ was: {can}.was }} }})",
        "notice_failed_body": exc(f"item: {can}.id, reason: 'employee notice failed', "
                                  f"detail: 'The employee was not told of the cancellation; HR tells them', owner: {CFG}.hr_owner"),
        "failed_body": exc(f"item: {B}.request_id, reason: 'write failed', detail: 'A leave write failed, never retried', owner: {CFG}.hr_owner"),
    })
    can_rule = s.code("Step 8: Rule: still cancellable?", code, inputs)
    cr = s.ref("Step 8: Rule: still cancellable?")
    co = lambda f: out(f, cr)  # noqa: E731
    mark = s.http("Step 8: Mark it cancelled", "PATCH", cfg("requests_url") + "/requests/" + co("id_q"), body=co("cancel_body"), parse=False,
                  onerror=on_fail(s, "Step 8: Mark it cancelled", co("failed_body")))
    mark["filter"] = s.when("still cancellable", "{{" + f"{cr}.result.id" + "}}", "", "exist")
    cancel = [can_read, can_rule, mark,
              s.http("Step 8: Ask Aisha to reverse it", "POST", msg, body=co("reverse_message"), parse=False,
                     onerror=on_fail(s, "Step 8: Ask Aisha to reverse it", co("failed_body"))),
              s.http("Step 8: Notify the employee of the cancellation", "POST", msg, body=co("notify_message"), parse=False,
                     onerror=[s.exception("Exception queue: cancellation notice failed", co("notice_failed_body")), s.ignore()]),
              s.finish_key("Close the key: cancelled", co("key_q"), co("done_body")),
              s.decision_log("Step 8: Decision log: cancelled", co("log_body"))]

    # ---- Step 3: duplicate key, employee, type and dates: an open one stops; a closed one may be asked again
    reserve = s.rpc("Step 3: Reserve key", "reserve_key", out("reserve_body"))
    # ---- Steps 4 and 5: balance, then the rules; each failure a warning ---------------------
    bal = s.http("Step 4: Read today's balance", "GET", cfg("balances_url") + "/balances",
                 query={"_wrap": "1", "employee_id": out("employee.id")})
    bal["filter"] = s.is_new_key("Step 3: Reserve key")  # an open copy stops here
    lst = s.http("Step 5: Read the request list", "GET", cfg("requests_url") + "/requests", query={"_wrap": "1"})
    emp = "$('Step 2: Rule: listed? protected?').first().json.employee"
    chk = "out"
    code, inputs = rule(N8N.CHECK_JS, {
        "Config": cfg_all,
        "Step 2: Rule: listed? protected?": "{{" + f"{ro}.result" + "}}",
        "Step 4: Read today's balance": "{{" + f"{s.ref("Step 4: Read today's balance")}.data" + "}}",
        "Step 5: Read the request list": "{{" + f"{s.ref('Step 5: Read the request list')}.data" + "}}",
    }, trigger=(T, fields), bodies={
        "key_q": f"encodeURIComponent({emp}.id + ':' + {B}.type + ':' + {B}.start + ':' + {B}.end)",
        "put_body": f"JSON.stringify({{ id: {B}.request_id, key: {emp}.id + ':' + {B}.type + ':' + {B}.start + ':' + {B}.end, employee_id: {emp}.id, "
                    f"employee: {B}.employee, name: {emp}.name, type: {B}.type, start: {B}.start, end: {B}.end, days: {chk}.days, warnings: {chk}.warnings, "
                    f"who_else_off: {chk}.who_else_off, manager: {emp}.manager, stand_in: {emp}.stand_in, decider: {emp}.manager, status: 'with manager', "
                    f"sent_on: {TODAY}, reminded: false }})",
        "ask_message": f"JSON.stringify({{ to: {emp}.manager, subject: 'Leave request ' + {B}.request_id + ' from ' + {emp}.name, "
                       f"text: {B}.type + ' leave, ' + {B}.start + ' to ' + {B}.end + ' (' + {chk}.days + ' days). Warnings: ' + ({chk}.warnings.join('; ') || 'none') + "
                       f"'. Also off: ' + ({chk}.who_else_off.join(', ') || 'nobody') + '.' }})",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {B}.request_id, decision: 'to the manager', rules: {{ days: {chk}.days, warnings: {chk}.warnings }} }})",
        "failed_body": exc(f"item: {B}.request_id, reason: 'write failed', "
                           "detail: 'The request or the manager message was not written, never retried; check it', owner: " + f"{CFG}.hr_owner"),
    })
    s_chk = s.code("Step 5: Rules: dates, notice, balance, overlap", code, inputs)
    ck = s.ref("Step 5: Rules: dates, notice, balance, overlap")
    ko = lambda f: out(f, ck)  # noqa: E731
    # ---- Step 6: to the manager, with warnings and who else is off -------------------------
    failed = lambda step: s.write_failed(step, ko("key_q"), ko("failed_body"))  # noqa: E731
    check = [reserve, bal, lst, s_chk,
             s.http("Step 6: Put it before the manager", "PUT", req_url, body=ko("put_body"), parse=False,
                    onerror=failed("Step 6: Put it before the manager")),
             s.http("Step 6: Ask the manager", "POST", msg, body=ko("ask_message"), parse=False, onerror=failed("Step 6: Ask the manager")),
             s.decision_log("Step 8: Decision log: to the manager", ko("log_body"))]

    route = lambda r: s.when(f"route is {r}", out("route"), r)  # noqa: E731
    s.flow.append(s.router("Route", [(route("check"), check), (route("hr"), hr), (route("unlisted"), unlisted), (route("cancel"), cancel)]))
    return s


def manager_decides() -> Scenario:
    s = Scenario(R, "R9.3 Take leave requests: manager decides", "webhook", test_key="r9-3-decision")
    cfg, cfg_all = start(s, D)
    msg = cfg("messaging_url") + "/messages"
    read = s.http("Step 6: Read the request", "GET", cfg("requests_url") + "/requests", query={"_wrap": "1", "id": "{{1.request_id}}"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    dec = "out"
    code, inputs = rule(N8N.DECIDED_JS, {"Config": cfg_all, "Step 6: Read the request": "{{" + f"{s.ref('Step 6: Read the request')}.data" + "}}"},
                        trigger=(D, ("request_id", "decision", "by")), bodies={
        "id_q": "encodeURIComponent(out.id || '')",
        "key_q": "encodeURIComponent(out.key || '')",
        "record_body": "JSON.stringify({ status: out.decision, decided_by: out.decided_by, decided_on: out.decided_on })",
        "torecord_body": f"JSON.stringify({{ request_id: {dec}.id, employee_id: {dec}.employee_id, name: {dec}.name, type: {dec}.type, start: {dec}.start, "
                         f"end: {dec}.end, days: {dec}.days, warnings: {dec}.warnings || [], decided_by: {dec}.decided_by, task: 'Re-check the balance as you record it' }})",
        "notify_message": f"JSON.stringify({{ to: {dec}.employee, subject: 'Your leave request ' + {dec}.id + ' was ' + {dec}.decision, "
                          f"text: {dec}.type + ' leave, ' + {dec}.start + ' to ' + {dec}.end + ': ' + {dec}.decision + ' by ' + {dec}.decided_by + '.' }})",
        "done_body": "JSON.stringify({ status: 'done', result: 'closed: ' + out.decision })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {dec}.id, decision: {dec}.decision, rules: {{ decided_by: {dec}.decided_by, warnings: {dec}.warnings || [] }} }})",
        "notice_failed_body": exc(f"item: {dec}.id, reason: 'employee notice failed', "
                                  f"detail: 'The employee was not told (send error); HR tells them', owner: {CFG}.hr_owner"),
        "failed_body": exc(f"item: $('{D}').first().json.body.request_id, reason: 'write failed', "
                           f"detail: 'A leave write failed, never retried', owner: {CFG}.hr_owner"),
    })
    s.flow.append(s.code("Step 6: Rule: still open?", code, inputs))
    ru = s.ref("Step 6: Rule: still open?")
    out = lambda f: "{{" + f"{ru}.result.{f}" + "}}"  # noqa: E731
    record = s.http("Step 6: Record the decision", "PATCH", cfg("requests_url") + "/requests/" + out("id_q"), body=out("record_body"),
                    parse=False, onerror=on_fail(s, "Step 6: Record the decision", out("failed_body")))
    record["filter"] = s.when("still open", "{{" + f"{ru}.result.id" + "}}", "", "exist")
    s.flow.append(record)

    def close(tag: str) -> list[dict]:
        """Step 8: notify the employee, close the key and log; a failed notice goes to Aisha."""
        return [s.http(f"Step 8: Notify the employee ({tag})", "POST", msg, body=out("notify_message"), parse=False,
                       onerror=[s.exception(f"Exception queue: employee notice failed ({tag})", out("notice_failed_body")), s.ignore()]),
                s.finish_key(f"Close the key ({tag})", out("key_q"), out("done_body")),
                s.decision_log(f"Step 8: Decision log: decided ({tag})", out("log_body"))]

    to_record = s.http("Step 7: To Aisha's to-record list", "POST", cfg("record_list_url") + "/items", body=out("torecord_body"), parse=False,
                       onerror=on_fail(s, "Step 7: To Aisha's to-record list", out("failed_body")))
    s.flow.append(s.router("Approved?", [
        (s.when("approved", out("decision"), "approved"), [to_record] + close("approved")),
        (s.when("declined", out("decision"), "approved", "text:notequal"), close("declined")),
    ]))
    return s


def morning_reminders() -> Scenario:
    s = Scenario(R, "R9.3 Take leave requests: morning reminders", "schedule", test_key=M, schedule="every day at 08:00")
    cfg, cfg_all = start(s, None)
    msg = cfg("messaging_url") + "/messages"
    read = s.http("Step 6: Read requests with the manager", "GET", cfg("requests_url") + "/requests", query={"_wrap": "1", "status": "with manager"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    rem = "out"
    code, inputs = n8n_rule(N8N.REMIND_JS, {"Config": cfg_all, "Step 6: Read requests with the manager": "{{" + f"{s.ref('Step 6: Read requests with the manager')}.data" + "}}"},
                            many=True, bodies={
        "id_q": "encodeURIComponent(out.id)",
        "remind_message": f"JSON.stringify({{ to: {rem}.manager, subject: 'Reminder: leave request ' + {rem}.id + ' from ' + {rem}.name, "
                          f"text: 'Waiting ' + {rem}.waited + ' working days. Warnings: ' + (({rem}.warnings || []).join('; ') || 'none') }})",
        "reminded_body": "JSON.stringify({ reminded: true })",
        "standin_body": "JSON.stringify({ status: 'with stand-in', decider: out.stand_in })",
        "standin_message": f"JSON.stringify({{ to: {rem}.stand_in, subject: 'Leave request ' + {rem}.id + ' from ' + {rem}.name + ': please decide', "
                           f"text: {rem}.manager + ' has not answered in ' + {rem}.waited + ' working days. Warnings: ' + (({rem}.warnings || []).join('; ') || 'none') }})",
        "hr_message": f"JSON.stringify({{ to: {CFG}.hr_owner, subject: 'Leave request ' + {rem}.id + ' moved to the stand-in', "
                      f"text: 'No answer from ' + {rem}.manager + ' in ' + {rem}.waited + ' working days; sent to ' + {rem}.stand_in + '.' }})",
        "failed_body": exc(f"item: {rem}.id, reason: 'reminder failed', detail: 'A reminder or stand-in step failed, never retried; chase the decider', "
                           f"owner: {CFG}.hr_owner"),
    })
    s.flow.append(s.code("Step 6: Rule: 2 or 4 working days?", code, inputs))
    s.flow.append(s.iterator("Each request waiting", "{{" + f"{s.ref('Step 6: Rule: 2 or 4 working days?')}.result.items" + "}}"))
    it = s.ref("Each request waiting")
    f = lambda k: "{{" + f"{it}.{k}" + "}}"  # noqa: E731
    url = cfg("requests_url") + "/requests/" + f("id_q")

    def step(name: str, method: str, u: str, body: str) -> dict:
        return s.http(name, method, u, body=f(body), parse=False, onerror=on_fail(s, name, f("failed_body")))

    s.flow.append(s.router("Remind or stand-in?", [
        (s.when("remind", f("action"), "remind"),
         [step("Step 6: Remind the manager", "POST", msg, "remind_message"), step("Step 6: Mark reminded", "PATCH", url, "reminded_body")]),
        (s.when("stand-in", f("action"), "stand-in"),
         [step("Step 6: Move it to the stand-in", "PATCH", url, "standin_body"), step("Step 6: Ask the stand-in", "POST", msg, "standin_message"),
          step("Step 6: Tell Aisha", "POST", msg, "hr_message")]),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R9.3/make/, scenario)."""
    return [("blueprint.json", request_or_cancellation()), ("decision.blueprint.json", manager_decides()),
            ("reminders.blueprint.json", morning_reminders())]
