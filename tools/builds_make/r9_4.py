"""R9.4 Remove a leaver's access the same day, as Make scenarios: rules only, no AI step.

Source: book Chapter 9, recipe R9.4, build steps 1 to 9 (recipes/R9.4/build-spec.md).
The rules are the n8n build's own JavaScript (tools/builds/r9_4.py), run through n8n_rule.
Four scenarios, because a Make scenario has one trigger: the immediate leaver (webhook,
blueprint.json), the daily leaver check (schedule, every day at 19:00, after closing; it also
runs the step 8 deadline check), a person's tick (webhook) and the access owner's close (webhook).

Each leaver, and each item to remove, is one bundle, as each is one item in n8n. A bundle's
fields cannot be mapped whole, so the rules that make them add `self` (the item as JSON),
which the next rule reads as that item. The rules that read a webhook body get it rebuilt
from the webhook's fields (trigger_body). The group-evidence rule asks n8n's itemMatching(),
which the shared adapter does not answer; with_item_matching() adds it for that one step.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R9.4"
N8N = n8n_build(R)
DAILY, NOW, TICK, CLOSE = N8N.DAILY, N8N.NOW, N8N.TICK, N8N.CLOSE
CONFIG = {
    "leavers_url": "https://<your leaver list API>",
    "inventory_url": "https://<your access inventory API>",
    "directory_url": "https://<your directory API>",
    "pos_url": "https://<your point-of-sale API>",
    "tasks_url": "https://<your task list API>",
    "evidence_url": "https://<your evidence list API>",
    "itsm_url": "https://<your IT provider's ticket API>",
    "messaging_url": "https://<your messaging API>",
    "leaver_list_owner": "<your HR owner, the only person who edits the leaver list>",
    "access_owner": "<your IT owner, who checks evidence and closes cases>",
    "deadline_working_days": 1,
}
CFG = "$('Config').first().json"
NOW_JS = "new Date().toISOString()"
SELF = "JSON.stringify(out)"


def trigger_body(trigger: str, fields: tuple[str, ...]) -> tuple[str, dict[str, str]]:
    """(prelude, inputs): the webhook's fields, rebuilt as n8n's $('<trigger>').first().json.body."""
    inputs = {f"t_{f}": "{{" + f"1.{f}" + "}}" for f in fields}
    body = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in fields)
    prelude = (f"// The webhook's fields, as the rule reads them in n8n: $('{trigger}').first().json.body.\n"
               f"DATA[{json.dumps(trigger)}] = [{{ json: {{ body: {{ {body} }} }} }}];")
    return prelude, inputs


def rule(js: str, sources: dict[str, str], trigger: tuple[str, tuple[str, ...]] | None = None, **kw):
    """n8n_rule, with the scenario's webhook body added when the rule reads it."""
    if not trigger:
        return n8n_rule(js, sources, **kw)
    prelude, extra = trigger_body(*trigger)
    code, inputs = n8n_rule(js, sources, prelude=prelude, **kw)
    return code, {**extra, **inputs}


def with_item_matching(code: str) -> str:
    """Answer $('X').itemMatching(n) as the n-th item of X: here X is the one item being removed."""
    old = "return { isExecuted: ran, first: () => list()[0],"
    assert old in code, "the adapter changed; revisit with_item_matching"
    return code.replace(old, "return { isExecuted: ran, itemMatching: (n) => list()[n], first: () => list()[0],")


def exc(fields: str) -> str:
    return f"JSON.stringify({{ recipe: '{R}', {fields} }})"


class Build:
    """One scenario's modules, with shorthands for Config fields and step outputs."""

    def __init__(self, s: Scenario):
        self.s = s
        c = s.ref("Config")
        self.cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
        self.cfg_all = "{{" + f"{c}.result" + "}}"
        self.msg = self.cfg("messaging_url") + "/messages"
        self.ev = self.cfg("evidence_url")

    def out(self, name: str, field: str = "") -> str:
        """A Code step's result ({{N.result.field}}), an HTTP step's data, or a bundle field."""
        n = self.s.ref(name)
        return "{{" + f"{n}.{field}" + "}}"


def start(s: Scenario, trigger: str | None) -> Build:
    if trigger:
        s.flow.append(s.webhook(trigger))
    s.flow.append(s.config(CONFIG))
    s.flow += s.stop_flag()
    return Build(s)


def case_check(b: Build, case_sources: dict[str, str], trigger=None, executed=()) -> list[dict]:
    """Step 7: every item confirmed? Then step 9: log the case and, once, ask Owen to close it."""
    s = b.s
    code, inputs = rule(N8N.CASE_JS, case_sources, trigger=trigger, executed=executed)
    flow = [s.code("Step 7: Case to check", code, inputs)]
    flow.append(s.http("Step 7: Read the case", "GET", b.ev + "/cases", query={"_wrap": "1", "id": b.out("Step 7: Case to check", "result.case_id")}))
    flow.append(s.http("Step 7: Read the case evidence", "GET", b.ev + "/items",
                       query={"_wrap": "1", "case_id": b.out("Step 7: Case to check", "result.case_id")}))
    rec = "out.record"
    code, inputs = n8n_rule(N8N.CONFIRMED_JS, {
        "Config": b.cfg_all,
        "Step 7: Case to check": b.out("Step 7: Case to check", "result"),
        "Step 7: Read the case": b.out("Step 7: Read the case", "data"),
        "Step 7: Read the case evidence": b.out("Step 7: Read the case evidence", "data"),
    }, bodies={
        "id_q": f"encodeURIComponent({rec}.id)",
        "record_body": f"JSON.stringify({rec})",
        "close_message": f"JSON.stringify({{ to: {CFG}.access_owner, subject: 'Leaver ' + {rec}.name + ': every item confirmed', "
                         f"text: 'Check the evidence for case ' + {rec}.id + ' and close it.' }})",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {rec}.id, decision: 'every item confirmed; to the access owner', "
                    f"rules: {{ items: ({rec}.items || []).length }} }})",
    })
    flow.append(s.code("Step 7: Rule: every item confirmed?", code, inputs))
    r = lambda f: b.out("Step 7: Rule: every item confirmed?", "result." + f)  # noqa: E731
    # n8n gives this write no error output: a failed evidence write ends the run in error.
    flow.append(s.http("Step 9: Log the case", "PUT", b.ev + "/cases/" + r("id_q"), body=r("record_body"), parse=False))
    ask = s.http("Step 9: Ask Owen to check and close", "POST", b.msg, body=r("close_message"), parse=False)
    ask["filter"] = s.when("all confirmed now", r("newly_confirmed"), "true")
    flow += [ask, s.decision_log("Step 9: Decision log: all confirmed", r("log_body"))]
    return flow


def leavers(b: Build, read_name: str) -> list[dict]:
    """Steps 1 to 7 for each leaver the read returned: the same in the daily and the immediate scenario."""
    s = b.s
    lv = "out"
    code, inputs = n8n_rule(N8N.LEAVERS_JS, {"Config": b.cfg_all, read_name: b.out(read_name, "data")}, many=True, bodies={
        "self": SELF,
        "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: {lv}.key }})",
        "not_hr_body": exc(f"item: {lv}.id, reason: 'not entered by HR', detail: 'Leaver entry ' + {lv}.id + ' was made by ' + {lv}.entered_by + '; nothing removed', "
                           f"owner: {CFG}.leaver_list_owner"),
        "not_hr_message": f"JSON.stringify({{ to: {CFG}.leaver_list_owner, subject: 'Leaver entry not made by you: nothing removed', "
                          f"text: 'Entry ' + {lv}.id + ' for ' + {lv}.name + ' was made by ' + {lv}.entered_by + '. Confirm it and enter it yourself.' }})",
    })
    flow = [s.code("Step 1: Leavers to process", code, inputs),
            s.iterator("Each leaver", b.out("Step 1: Leavers to process", "result.items"))]
    each = lambda f: b.out("Each leaver", f)  # noqa: E731

    # ---- Step 1: an entry not made by HR stops and alerts Aisha ---------------------------------
    not_hr = [s.exception("Step 1: Exception queue: not entered by HR", each("not_hr_body")),
              s.http("Step 1: Alert Aisha", "POST", b.msg, body=each("not_hr_message"), parse=False)]

    # ---- Step 2: key, employee and date; a logged key resumes at the first unconfirmed item -----
    by_hr = [s.rpc("Step 2: Reserve key", "reserve_key", each("reserve_body")),
             s.http("Step 3: Read the inventory", "GET", b.cfg("inventory_url") + "/items", query={"_wrap": "1", "person_id": each("employee_id")}),
             s.http("Step 2: Read the evidence so far", "GET", b.ev + "/items", query={"_wrap": "1", "case_id": each("case_id")})]
    inv = "out"
    code, inputs = n8n_rule(N8N.VALID_JS, {
        "Config": b.cfg_all,
        "Step 1: Leavers to process": each("self"),
        "Step 3: Read the inventory": b.out("Step 3: Read the inventory", "data"),
        "Step 2: Read the evidence so far": b.out("Step 2: Read the evidence so far", "data"),
    }, bodies={
        "key_q": f"encodeURIComponent({inv}.key)",
        "invalid_body": exc(f"item: {inv}.case_id, reason: 'inventory not valid', detail: {inv}.why + '; nothing removed', owner: {CFG}.access_owner"),
        "invalid_message": f"JSON.stringify({{ to: {CFG}.access_owner, subject: 'Leaver ' + {inv}.leaver.name + ': stopped, nothing removed', "
                           f"text: {inv}.why + '. Empty means unknown: build the inventory, then save the leaver again.' }})",
        "invalid_key_body": f"JSON.stringify({{ status: 'failed', result: 'stopped: ' + {inv}.why }})",
    })
    # The n8n node runs once per leaver; here each leaver is its own bundle, so the step runs once per bundle.
    by_hr.append(s.code("Step 3: Rule: inventory valid?", code, inputs))
    v = lambda f: b.out("Step 3: Rule: inventory valid?", "result." + f)  # noqa: E731

    # ---- Step 3: empty, or lists an administrator: stop and alert Owen ---------------------------
    invalid = [s.exception("Step 3: Exception queue: inventory not valid", v("invalid_body")),
               s.http("Step 3: Alert Owen", "POST", b.msg, body=v("invalid_message"), parse=False),
               s.finish_key("Mark key failed: inventory", v("key_q"), v("invalid_key_body"))]

    # ---- Steps 4 to 6: each item, SSO first --------------------------------------------------
    it = "out"
    code, inputs = n8n_rule(N8N.ITEMS_JS, {"Config": b.cfg_all, "Step 3: Rule: inventory valid?": b.out("Step 3: Rule: inventory valid?", "result")}, many=True, bodies={
        "self": SELF,
        "account_q": f"encodeURIComponent({it}.account)",
        "evidence_q": f"encodeURIComponent({it}.evidence_id)",
        "key_q": f"encodeURIComponent({it}.key)",
        "sessions_body": f"JSON.stringify({{ user: {it}.account }})",
        "sso_evidence": f"JSON.stringify({{ id: {it}.evidence_id, case_id: {it}.case_id, item_id: {it}.item_id, system: {it}.system, "
                        f"account: {it}.account, action: 'disabled; sessions ended', status: 'confirmed', by: 'response: directory', at: {NOW_JS} }})",
        "removed_evidence": f"JSON.stringify({{ id: {it}.evidence_id, case_id: {it}.case_id, item_id: {it}.item_id, system: {it}.system, "
                            f"account: {it}.account, action: 'removed through its connection', status: 'confirmed', by: 'response: ' + {it}.system, at: {NOW_JS} }})",
        "task_body": f"JSON.stringify({{ id: {it}.evidence_id, case_id: {it}.case_id, assignee: {it}.assignee, task: {it}.task, "
                     "tick: 'Tick it done with your name; the time is recorded' })",
        "task_evidence": f"JSON.stringify({{ id: {it}.evidence_id, case_id: {it}.case_id, item_id: {it}.item_id, system: {it}.system, "
                         f"account: {it}.account, action: {it}.task, task_id: {it}.evidence_id, assignee: {it}.assignee, status: 'open', at: {NOW_JS} }})",
        "failed_key_body": f"JSON.stringify({{ status: 'failed', result: 'removal failed: ' + {it}.system }})",
        "ticket_body": f"JSON.stringify({{ case_id: {it}.case_id, subject: 'Leaver access not removed: ' + {it}.system, "
                       f"detail: {it}.kind + ' ' + {it}.account + ' for ' + {it}.leaver.name + ' failed; remove it by hand' }})",
        "alert_message": f"JSON.stringify({{ to: {CFG}.access_owner, subject: 'Leaver ' + {it}.leaver.name + ': ' + {it}.system + ' not removed', "
                         f"text: 'The ' + {it}.kind + ' ' + {it}.account + ' failed and was not retried. IT ticket raised; the case stays open.' }})",
        "failed_body": exc(f"item: {it}.case_id, reason: 'removal failed', detail: {it}.system + ' ' + {it}.account + ': never retried; remove it by hand', "
                           f"owner: {CFG}.access_owner"),
    })
    remove = [s.code("Steps 4 to 6: Items to remove", code, inputs),
              s.iterator("Each item to remove", b.out("Steps 4 to 6: Items to remove", "result.items"))]
    item = lambda f: b.out("Each item to remove", f)  # noqa: E731

    def failed(step: str) -> list[dict]:
        """A removal fails: never retried; the key is marked failed, an IT ticket, an alert and an
        exception-queue row; the case stays open and the next item goes on."""
        return [s.finish_key(f"{step}: mark key failed", item("key_q"), item("failed_key_body")),
                s.http(f"{step}: IT ticket: removal failed", "POST", b.cfg("itsm_url") + "/tickets", body=item("ticket_body"), parse=False),
                s.http(f"{step}: alert Owen: removal failed", "POST", b.msg, body=item("alert_message"), parse=False),
                s.exception(f"{step}: exception queue: removal failed", item("failed_body")),
                s.ignore()]

    def write(name: str, method: str, url: str, body: str, parse: bool = False) -> dict:
        return s.http(name, method, url, body=body, parse=parse, onerror=failed(name))

    sso = [write("Step 4: Disable the SSO account", "PATCH", b.cfg("directory_url") + "/users/" + item("account_q"), '{"enabled": false}'),
           write("Step 4: End its sessions", "POST", b.cfg("directory_url") + "/sign_in_revocations", item("sessions_body")),
           write("Step 4: Evidence: SSO disabled", "PUT", b.ev + "/items/" + item("evidence_q"), item("sso_evidence"), parse=True)]
    code, inputs = n8n_rule(N8N.COVERED_JS, {"Steps 4 to 6: Items to remove": item("self"),
                                             "Step 4: Evidence: SSO disabled": b.out("Step 4: Evidence: SSO disabled", "data")},
                            many=True, bodies={"id_q": "encodeURIComponent(out.id)", "body": "JSON.stringify(Object.assign({}, out))"})
    sso += [s.code("Step 4: Groups ended with the account", with_item_matching(code), inputs),
            s.iterator("Each group", b.out("Step 4: Groups ended with the account", "result.items"))]
    # The group's evidence is the rule's item as it is (n8n: JSON.stringify($json)), without the step's own fields.
    sso.append(s.http("Step 4: Evidence: group ended", "PUT", b.ev + "/items/" + b.out("Each group", "id_q"), body=b.out("Each group", "body"),
                      parse=False, onerror=failed("Step 4: Evidence: group ended")))
    connection = [write("Step 5: Remove from the app", "PATCH", item("url"), '{"active": false}'),
                  write("Step 5: Evidence: removed", "PUT", b.ev + "/items/" + item("evidence_q"), item("removed_evidence"))]
    task = [write("Steps 5 and 6: Task a person", "POST", b.cfg("tasks_url") + "/tasks", item("task_body")),
            write("Steps 5 and 6: Evidence: task open", "PUT", b.ev + "/items/" + item("evidence_q"), item("task_evidence"))]
    how = lambda a: s.when(f"action is {a}", item("action"), a)  # noqa: E731
    remove.append(s.router("How is it removed?", [(how("sso"), sso), (how("connection"), connection), (how("task"), task)]))

    # The removals run first (route 1, every item), then step 7 checks the case (route 2), as in n8n.
    check = case_check(b, {"Step 3: Rule: inventory valid?": b.out("Step 3: Rule: inventory valid?", "result")})
    valid = lambda label: s.when(label, v("valid"), "true")  # noqa: E731
    by_hr.append(s.router("Inventory valid?", [
        (s.when("inventory not valid", v("valid"), "true", "text:notequal"), invalid),
        (valid("inventory valid: remove"), remove),
        (valid("inventory valid: check the case"), check),
    ]))
    flow.append(s.router("Entered by HR?", [
        (s.when("not entered by HR", each("by_hr"), "true", "text:notequal"), not_hr),
        (s.when("entered by HR", each("by_hr"), "true"), by_hr),
    ]))
    return flow


def daily() -> Scenario:
    s = Scenario(R, "R9.4 Remove a leaver's access: daily check after closing", "schedule", test_key=DAILY, schedule="every day at 19:00")
    b = start(s, None)
    read = s.http("Step 1: Read today's leavers", "GET", b.cfg("leavers_url") + "/leavers",
                  query={"_wrap": "1", "last_day": '{{formatDate(now; "YYYY-MM-DD"; "UTC")}}'})
    read["filter"] = s.continue_unless_stopped()
    process = [read] + leavers(b, "Step 1: Read today's leavers")

    # ---- Step 8: a case unconfirmed at its deadline: IT ticket and alert Owen, once ----------------
    od = "out"
    open_cases = s.http("Step 8: Read open cases", "GET", b.ev + "/cases", query={"_wrap": "1", "status": "open"})
    open_cases["filter"] = s.continue_unless_stopped()
    # OVERDUE_JS reads no Config; the alert body does, so Config is a source too.
    code, inputs = n8n_rule(N8N.OVERDUE_JS, {"Config": b.cfg_all, "Step 8: Read open cases": b.out("Step 8: Read open cases", "data")},
                            many=True, bodies={
        "id_q": f"encodeURIComponent({od}.id)",
        "ticket_body": f"JSON.stringify({{ case_id: {od}.id, subject: 'Leaver access unconfirmed at the deadline: ' + {od}.name, "
                       f"detail: 'Unconfirmed: ' + ({od}.unconfirmed || []).join(', ') + '; remove them' }})",
        "alert_message": f"JSON.stringify({{ to: {CFG}.access_owner, subject: 'Leaver ' + {od}.name + ': unconfirmed at the deadline', "
                         f"text: 'Unconfirmed: ' + ({od}.unconfirmed || []).join(', ') + '. IT ticket raised.' }})",
    })
    deadline = [open_cases, s.code("Step 8: Rule: past the deadline?", code, inputs),
                s.iterator("Each case past the deadline", b.out("Step 8: Rule: past the deadline?", "result.items"))]
    each = lambda f: b.out("Each case past the deadline", f)  # noqa: E731
    deadline += [s.http("Step 8: IT ticket: unconfirmed at the deadline", "POST", b.cfg("itsm_url") + "/tickets", body=each("ticket_body"), parse=False),
                 s.http("Step 8: Alert Owen", "POST", b.msg, body=each("alert_message"), parse=False),
                 s.http("Step 8: Mark the case ticketed", "PATCH", b.ev + "/cases/" + each("id_q"), body='{"ticketed": true}', parse=False)]
    # n8n runs both from the daily trigger, the leavers first; a router runs its routes in order.
    s.flow.append(s.router("Leavers, then the deadline check", [(None, process), (None, deadline)]))
    return s


def immediate() -> Scenario:
    s = Scenario(R, "R9.4 Remove a leaver's access: immediate leaver", "webhook", test_key="r9-4-immediate")
    b = start(s, NOW)
    read = s.http("Step 1: Read the immediate leaver", "GET", b.cfg("leavers_url") + "/leavers", query={"_wrap": "1", "id": "{{1.leaver_id}}"})
    read["filter"] = s.continue_unless_stopped()
    s.flow += [read] + leavers(b, "Step 1: Read the immediate leaver")
    return s


def tick() -> Scenario:
    s = Scenario(R, "R9.4 Remove a leaver's access: a person ticks an item", "webhook", test_key="r9-4-tick")
    b = start(s, TICK)
    read = s.http("Step 7: Read the item", "GET", b.ev + "/items", query={"_wrap": "1", "id": "{{1.evidence_id}}"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    code, inputs = rule(N8N.TICK_JS, {"Step 7: Read the item": b.out("Step 7: Read the item", "data")}, trigger=(TICK, ("evidence_id", "by")), bodies={
        "id_q": "encodeURIComponent(out.id || '')",
        "tick_body": "JSON.stringify({ status: 'confirmed', by: out.by, at: out.at })",
    })
    s.flow.append(s.code("Step 7: Rule: open item?", code, inputs))
    t = lambda f: b.out("Step 7: Rule: open item?", "result." + f)  # noqa: E731
    record = s.http("Step 7: Record the tick", "PATCH", b.ev + "/items/" + t("id_q"), body=t("tick_body"), parse=False)
    record["filter"] = s.when("an open item", t("id"), "", "exist")
    s.flow.append(record)
    s.flow += case_check(b, {"Step 7: Rule: open item?": b.out("Step 7: Rule: open item?", "result")}, executed=(TICK,))
    return s


def close() -> Scenario:
    s = Scenario(R, "R9.4 Remove a leaver's access: Owen closes the case", "webhook", test_key="r9-4-close")
    b = start(s, CLOSE)
    read = s.http("Step 9: Read the case", "GET", b.ev + "/cases", query={"_wrap": "1", "id": "{{1.case_id}}"})
    read["filter"] = s.continue_unless_stopped()
    s.flow += [read, s.http("Step 9: Read its evidence", "GET", b.ev + "/items", query={"_wrap": "1", "case_id": "{{1.case_id}}"})]
    cl = "out"
    code, inputs = rule(N8N.CLOSE_JS, {
        "Config": b.cfg_all,
        "Step 9: Read the case": b.out("Step 9: Read the case", "data"),
        "Step 9: Read its evidence": b.out("Step 9: Read its evidence", "data"),
    }, trigger=(CLOSE, ("case_id", "by")), bodies={
        "case_q": f"encodeURIComponent({cl}.case_id)",
        "key_q": f"encodeURIComponent({cl}.key || '')",
        "close_body": f"JSON.stringify({{ status: 'closed', closed_by: {cl}.by, closed_at: {NOW_JS} }})",
        "done_body": f"JSON.stringify({{ status: 'done', result: 'closed by ' + {cl}.by }})",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {cl}.case_id, decision: 'closed', rules: {{ closed_by: {cl}.by }} }})",
        "refused_message": f"JSON.stringify({{ to: {CFG}.access_owner, subject: 'Case ' + {cl}.case_id + ' not closed', text: {cl}.why }})",
    })
    s.flow.append(s.code("Step 9: Rule: may it close?", code, inputs))
    r = lambda f: b.out("Step 9: Rule: may it close?", "result." + f)  # noqa: E731
    s.flow.append(s.router("Close it?", [
        (s.when("may close", r("ok"), "true"),
         [s.http("Step 9: Close the case", "PATCH", b.ev + "/cases/" + r("case_q"), body=r("close_body"), parse=False),
          s.finish_key("Mark key done", r("key_q"), r("done_body")),
          s.decision_log("Step 9: Decision log: closed", r("log_body"))]),
        (s.when("may not close", r("ok"), "true", "text:notequal"),
         [s.http("Step 9: Not closed: tell Owen", "POST", b.msg, body=r("refused_message"), parse=False)]),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R9.4/make/, scenario)."""
    return [("blueprint.json", immediate()), ("daily.blueprint.json", daily()),
            ("tick.blueprint.json", tick()), ("close.blueprint.json", close())]
