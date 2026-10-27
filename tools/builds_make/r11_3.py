"""R11.3 Route purchase approval by amount and remaining budget, as Make scenarios: rules only, no AI step.

Source: book Chapter 11, recipe R11.3, Table 11.2 and build steps 1 to 12 (recipes/R11.3/build-spec.md).
The rules are the n8n build's own JavaScript (tools/builds/r11_3.py), run through n8n_rule.
Four scenarios, because a Make scenario has one trigger: the request set to "checked; to
approval" (webhook), the approver's answer (webhook), steps 7 and 8 each morning (schedule,
daily at 07:00) and step 12 with each new accounting export (webhook).
The rules read the webhook body as n8n's $('<trigger>').first().json.body; a Make webhook
step's output cannot be mapped whole, so trigger_body() passes its fields one by one and the
prelude rebuilds that body before the rule runs. The n8n build's own SQL becomes the key-log
functions: the bill keys use reserve_keys and finish_keys, a held request's key release_key.
The answer's decided_on date is the UTC date the rule runs, as $now.toISODate() is on n8n in UTC.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R11.3"
N8N = n8n_build(R)
T, A, M, E = N8N.T, N8N.A, N8N.M, N8N.E
CONFIG = {
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
}
CFG = "$('Config').first().json"


def trigger_body(trigger: str, fields: tuple[str, ...]) -> tuple[str, dict[str, str]]:
    """(prelude, inputs): the webhook's fields, rebuilt as n8n's $('<trigger>').first().json.body."""
    inputs = {f"t_{f}": "{{" + f"1.{f}" + "}}" for f in fields}
    body = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in fields)
    prelude = (f"// The webhook's fields, as the rule reads them in n8n: $('{trigger}').first().json.body.\n"
               f"DATA[{json.dumps(trigger)}] = [{{ json: {{ body: {{ {body} }} }} }}];")
    return prelude, inputs


def rule(js: str, sources: dict[str, str], trigger: tuple[str, tuple[str, ...]], prelude: str = "", **kw):
    """n8n_rule, with the scenario's webhook body added for the rule to read."""
    pre, extra = trigger_body(*trigger)
    code, inputs = n8n_rule(js, sources, prelude=pre + "\n" + prelude, **kw)
    return code, {**extra, **inputs}


def exc(fields: str) -> str:
    return f"JSON.stringify({{ recipe: '{R}', {fields} }})"


def start(s: Scenario, trigger: str | None):
    if trigger:
        s.flow.append(s.webhook(trigger))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    s.flow += s.stop_flag()
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    data = lambda n, f="data": "{{" + f"{s.ref(n)}.{f}" + "}}"  # noqa: E731
    return cfg, "{{" + f"{c}.result" + "}}", data


def to_approval() -> Scenario:
    s = Scenario(R, "R11.3 Route purchase approval: request to approval", "webhook", test_key="r11-3-to-approval")
    cfg, cfg_all, data = start(s, T)
    msg = cfg("messaging_url") + "/messages"
    read = s.http("Read request", "GET", cfg("requests_url") + "/requests/{{encodeURL(1.request_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    s.flow.append(s.reserve_key("Step 2: Reserve key", "{{1.request_id}}:{{1.version}}"))
    line = s.http("Read budget line", "GET", cfg("budget_url") + "/lines/{{encodeURL(" + f"{s.ref('Read request')}.data.budget_line" + ")}}")
    line["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: an approval for this version is open or decided
    s.flow.append(line)
    s.flow.append(s.http("Read commitments", "GET", cfg("budget_url") + "/commitments",
                         query={"_wrap": "1", "budget_line": data("Read request", "data.budget_line")}))
    ev = f"$('{T}').first().json.body"
    req = "$('Read request').first().json"
    key = f"{ev}.request_id + ':' + {ev}.version"
    code, inputs = rule(N8N.ROUTE_JS, {
        "Config": cfg_all,
        "Read request": data("Read request"),
        "Read budget line": data("Read budget line"),
        "Read commitments": data("Read commitments"),
    }, trigger=(T, ("request_id", "version")), bodies={
        "key_q": f"encodeURIComponent({key})",
        "approval_body": "JSON.stringify(out.approval || {})",
        "copy_message": f"(out.approval ? JSON.stringify({{ to: {CFG}.budget_owner, subject: 'Over budget: request ' + {ev}.request_id, "
                        "text: 'Sent to ' + out.approval.approver + ': ' + out.approval.amount + ' against ' + out.approval.budget_before + "
                        "' remaining on ' + out.approval.budget_line }) : null)",
        "stale_body": exc(f"item: {ev}.request_id, reason: 'budget export stale', detail: out.detail, owner: {CFG}.budget_owner"),
        "stale_message": f"JSON.stringify({{ to: {CFG}.budget_owner, subject: 'Refresh the budget export', text: out.detail }})",
        "edit_message": f"JSON.stringify({{ to: {req}.requester, subject: 'Request ' + {ev}.request_id + ' is approved and locked', "
                        "text: 'Edit refused: this request was approved and released. Raise a new request for the change.' })",
        "no_approver_body": exc(f"item: {ev}.request_id, reason: 'no eligible approver', detail: out.detail, owner: {CFG}.senior_approver"),
        "release_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: {key} }})",
        "done_body": "JSON.stringify({ status: 'done', result: out.decision })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {ev}.request_id + ' v' + {ev}.version, decision: out.decision, rules: out.rules }})",
        "failed_body": exc(f"item: {ev}.request_id, reason: 'write failed', detail: 'Approval write failed; check the request list, then rerun it', "
                           f"owner: {CFG}.editor"),
    })
    s.flow.append(s.code("Rules: steps 3 to 5", code, inputs))
    out = lambda f: data("Rules: steps 3 to 5", "result." + f)  # noqa: E731
    failed = lambda step: s.write_failed(step, out("key_q"), out("failed_body"))  # noqa: E731

    def write(name: str, method: str, url: str, body: str) -> dict:
        return s.http(name, method, url, body=body, parse=False, onerror=failed(name))

    def done(tag: str) -> list[dict]:
        return [s.finish_key(f"Mark key done ({tag})", out("key_q"), out("done_body")), s.decision_log(f"Decision log ({tag})", out("log_body"))]

    def released(tag: str) -> list[dict]:
        """No approval is open or decided, so a rerun after the fix must not stop at step 2."""
        return [s.release_key(f"Release key: no approval open ({tag})", out("release_body")), s.decision_log(f"Decision log ({tag})", out("log_body"))]

    # ---- Step 6: one approval; step 4 copies the budget owner when it is over budget ------------
    approval = [write("Step 6: Start one approval", "POST", cfg("approvals_url") + "/approvals", out("approval_body")),
                s.router("Over budget?", [
                    (s.when("over budget", out("copy_budget_owner"), "true"),
                     [write("Step 4: Copy the budget owner", "POST", msg, out("copy_message"))] + done("over budget")),
                    (s.when("within budget", out("copy_budget_owner"), "true", "text:notequal"), done("approval")),
                ])]
    # ---- Step 3: an old budget export waits for the budget owner ---------------------------------
    held = [s.exception("Step 3: Exception queue: budget export stale", out("stale_body")),
            write("Step 3: Tell the budget owner", "POST", msg, out("stale_message"))] + released("held")
    # ---- Step 10's lock: an edit after release needs a new request -------------------------------
    url = cfg("requests_url") + "/requests/{{encodeURL(1.request_id)}}"
    edit = [write("Step 10: Keep it approved; edit refused", "PATCH", url, '{"status": "approved", "edit_refused": "new request needed"}'),
            write("Step 10: Tell the requester a new request is needed", "POST", msg, out("edit_message"))] + done("edit refused")
    nobody = [s.exception("Exception queue: no eligible approver", out("no_approver_body"))] + released("no approver")
    route = lambda r: s.when(f"route is {r}", out("route"), r)  # noqa: E731
    s.flow.append(s.router("Route", [(route("approval"), approval), (route("held"), held),
                                     (route("edit_refused"), edit), (route("no_approver"), nobody)]))
    return s


def approval_answered() -> Scenario:
    s = Scenario(R, "R11.3 Route purchase approval: approval answered", "webhook", test_key="r11-3-approval-answered")
    cfg, cfg_all, data = start(s, A)
    msg = cfg("messaging_url") + "/messages"
    read = s.http("Read the approval", "GET", cfg("approvals_url") + "/approvals/{{encodeURL(1.approval_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    s.flow.append(s.reserve_key("Reserve key: approval answer", "answer:{{1.approval_id}}"))
    areq = s.http("Read request at answer", "GET", cfg("requests_url") + "/requests/{{encodeURL(" + f"{s.ref('Read the approval')}.data.request_id" + ")}}")
    areq["filter"] = s.is_new_key("Reserve key: approval answer")  # a copy stops here: this answer was handled before
    s.flow.append(areq)
    rq = s.ref("Read request at answer")
    s.flow.append(s.http("Read supplier record", "GET", cfg("vendors_url") + "/records/{{encodeURL(" + f"{rq}.data.supplier_id" + ")}}"))
    s.flow.append(s.http("Read policy list", "GET", cfg("policy_url") + "/budget_lines/{{encodeURL(" + f"{rq}.data.budget_line" + ")}}"))
    ans = f"$('{A}').first().json.body"
    appr = "$('Read the approval').first().json"
    req = "$('Read request at answer').first().json"
    code, inputs = rule(N8N.ANSWER_JS, {
        "Config": cfg_all,
        "Read the approval": data("Read the approval"),
        "Read request at answer": data("Read request at answer"),
        "Read supplier record": data("Read supplier record"),
        "Read policy list": data("Read policy list"),
    }, trigger=(A, ("approval_id", "decision", "by", "comment")), bodies={
        "key_q": f"encodeURIComponent('answer:' + {ans}.approval_id)",
        "approval_q": f"encodeURIComponent({ans}.approval_id)",
        "request_q": f"encodeURIComponent({appr}.request_id)",
        "answer_body": f"JSON.stringify({{ status: {ans}.decision, decided_by: out.by, comment: {ans}.comment || '', decided_on: new Date().toISOString().slice(0, 10) }})",
        "approved_body": f"JSON.stringify({{ status: 'approved', locked: true, approved_by: out.by, approved_version: {appr}.version }})",
        "commitment_body": f"JSON.stringify({{ id: {appr}.request_id, request_id: {appr}.request_id, budget_line: {appr}.budget_line, amount: {appr}.amount, "
                           f"billed: 0, remaining: {appr}.amount }})",
        "buyer_message": f"JSON.stringify({{ to: {CFG}.buyer, subject: 'Raise the PO: request ' + {appr}.request_id, "
                         f"text: 'Approved by ' + out.by + ' for ' + {appr}.amount + '; quote valid until ' + {appr}.valid_until }})",
        "blocked_body": "JSON.stringify({ status: 'blocked', reasons: out.reasons })",
        "requester_message": f"JSON.stringify({{ to: {req}.requester, subject: 'Purchase request ' + {appr}.request_id + ' blocked at release', "
                             "text: 'Approved, but not released: ' + (out.reasons || []).join('; ') + '. Fix and raise it again.' })",
        "rejected_body": "JSON.stringify({ status: 'rejected', rejected_by: out.by, rejection_comment: out.comment })",
        "done_body": "JSON.stringify({ status: 'done', result: out.decision })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {appr}.request_id + ' v' + {appr}.version, decision: out.decision, rules: out.rules }})",
        "failed_body": exc(f"item: {appr}.request_id, reason: 'write failed', "
                           "detail: 'Write after the approval answer failed; check the request, approval and commitment before rerunning', "
                           f"owner: {CFG}.editor"),
    })
    s.flow.append(s.code("Rules: steps 9 to 11", code, inputs))
    out = lambda f: data("Rules: steps 9 to 11", "result." + f)  # noqa: E731

    def write(name: str, method: str, url: str, body: str) -> dict:
        return s.http(name, method, url, body=body, parse=False, onerror=s.write_failed(name, out("key_q"), out("failed_body")))

    def done(tag: str) -> list[dict]:
        return [s.finish_key(f"Mark answer key done ({tag})", out("key_q"), out("done_body")),
                s.decision_log(f"Decision log: answer ({tag})", out("log_body"))]

    url = cfg("requests_url") + "/requests/" + out("request_q")
    decision = lambda o: s.when(f"outcome is {o}", out("outcome"), o)  # noqa: E731
    counts = [write("Step 9: Record the answer", "PATCH", cfg("approvals_url") + "/approvals/" + out("approval_q"), out("answer_body")),
              s.router("Decision", [
                  (decision("release"), [write("Step 10: Set approved and lock it", "PATCH", url, out("approved_body")),
                                         write("Step 10: Write the commitment", "POST", cfg("budget_url") + "/commitments", out("commitment_body")),
                                         write("Step 10: Tell the buyer to raise the PO", "POST", msg, out("buyer_message"))] + done("released")),
                  (decision("blocked"), [write("Step 9: Set blocked", "PATCH", url, out("blocked_body")),
                                         write("Step 9: Tell the requester", "POST", msg, out("requester_message"))] + done("blocked")),
                  (decision("rejected"), [write("Step 11: Record the comment", "PATCH", url, out("rejected_body"))] + done("rejected")),
              ])]
    # The approval is no longer open, or the request changed since it started: the answer is ignored and logged.
    s.flow.append(s.router("Answer counts?", [
        (s.when("answer ignored", out("outcome"), "void"), done("ignored")),
        (s.when("answer counts", out("outcome"), "void", "text:notequal"), counts),
    ]))
    return s


def each_morning() -> Scenario:
    s = Scenario(R, "R11.3 Route purchase approval: each morning", "schedule", test_key=M, schedule="every day at 07:00")
    cfg, cfg_all, data = start(s, None)
    msg = cfg("messaging_url") + "/messages"
    read = s.http("Read open approvals", "GET", cfg("approvals_url") + "/approvals", query={"_wrap": "1", "status": "open"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    code, inputs = n8n_rule(N8N.MORNING_JS, {"Config": cfg_all, "Read open approvals": data("Read open approvals")}, many=True, bodies={
        "id_q": "encodeURIComponent(out.id)",
        "patch_body": "JSON.stringify(out.patch || {})",
        "send_body": "JSON.stringify({ to: out.to, subject: out.subject, text: out.text })",
        "exception_body": exc(f"item: out.request_id, reason: 'no answer after the stand-in', detail: out.text, owner: {CFG}.senior_approver"),
    })
    s.flow.append(s.code("Rules: steps 7 and 8", code, inputs))
    s.flow.append(s.iterator("Each action", data("Rules: steps 7 and 8", "result.items")))
    it = lambda f: data("Each action", f)  # noqa: E731
    url = cfg("approvals_url") + "/approvals/" + it("id_q")
    # These writes have no error output in the n8n build: a failure ends the run in error.
    patch = lambda n: s.http(n, "PATCH", url, body=it("patch_body"), parse=False)  # noqa: E731
    send = lambda n: s.http(n, "POST", msg, body=it("send_body"), parse=False)  # noqa: E731
    action = lambda a: s.when(f"action is {a}", it("action"), a)  # noqa: E731
    s.flow.append(s.router("Action", [
        (action("remind"), [patch("Step 7: Record the reminder"), send("Step 7: Remind the approver")]),
        (action("warn"), [send("Step 7: Warn the requester")]),
        (action("standin"), [patch("Step 8: Send to the stand-in"), send("Step 8: Tell the stand-in")]),
        (action("final"), [s.exception("Exception queue: no answer after the stand-in", it("exception_body")),
                           patch("Record the final escalation"), send("Tell the senior approver")]),
    ]))
    return s


# reserve_keys returns the new keys as a list; the n8n rule reads them as one '|'-joined text, as the n8n SQL returned them.
NEW_KEYS_JS = """// Reserve bill keys: the function's list of new keys, as the n8n rule reads it: {new_keys: 'a|b'}.
const __keys = (DATA['Reserve bill keys'] || [{ json: [] }])[0].json;
DATA['Reserve bill keys'] = [{ json: { new_keys: (Array.isArray(__keys) ? __keys : [])
  .map(k => (k && typeof k === 'object' ? Object.values(k)[0] : k)).filter(Boolean).join('|') } }];"""


def new_export() -> Scenario:
    s = Scenario(R, "R11.3 Route purchase approval: new accounting export", "webhook", test_key="r11-3-new-export")
    cfg, cfg_all, data = start(s, E)
    bills = s.http("Read the export's bills", "GET", cfg("ledger_url") + "/bills", query={"_wrap": "1"})
    bills["filter"] = s.continue_unless_stopped()
    s.flow += [bills, s.http("Read commitments for bills", "GET", cfg("budget_url") + "/commitments", query={"_wrap": "1"})]
    code, inputs = n8n_rule(N8N.BILLS_JS, {"Read the export's bills": data("Read the export's bills"),
                                           "Read commitments for bills": data("Read commitments for bills")}, bodies={
        "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_keys: String(out.keys || '').split('|').filter(Boolean) }})",
    })
    s.flow.append(s.code("Bills against a commitment", code, inputs))
    reserve = s.rpc("Reserve bill keys", "reserve_keys", data("Bills against a commitment", "result.reserve_body"))
    reserve["filter"] = s.when("bills against a commitment", data("Bills against a commitment", "result.keys"), "", "exist")
    s.flow.append(reserve)
    red = "out"
    code, inputs = n8n_rule(N8N.REDUCE_JS, {
        "Config": cfg_all,
        "Read the export's bills": data("Read the export's bills"),
        "Read commitments for bills": data("Read commitments for bills"),
        "Reserve bill keys": data("Reserve bill keys"),
    }, many=True, prelude=NEW_KEYS_JS, bodies={
        "commitment_q": f"encodeURIComponent({red}.commitment)",
        "reduce_body": f"JSON.stringify({{ billed: {red}.billed, remaining: {red}.remaining }})",
        "over_body": exc(f"item: {red}.request_id, reason: 'bill over commitment', detail: {red}.detail, owner: {CFG}.budget_owner"),
        "owner_message": f"JSON.stringify({{ to: {CFG}.budget_owner, subject: 'Bill over its commitment: request ' + {red}.request_id, text: {red}.detail }})",
        "done_keys_body": f"JSON.stringify({{ p_recipe: '{R}', p_keys: {red}.keys.split('|'), p_status: 'done', "
                          f"p_result: 'billed ' + {red}.billed + ', remaining ' + {red}.remaining }})",
        "failed_keys_body": f"JSON.stringify({{ p_recipe: '{R}', p_keys: {red}.keys.split('|'), p_status: 'failed', p_result: 'write failed' }})",
        "failed_body": exc(f"item: {red}.request_id, reason: 'write failed', detail: 'Commitment write failed; check the budget list before rerunning', "
                           f"owner: {CFG}.editor"),
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {red}.commitment, decision: {red}.over ? 'bill over commitment' : 'commitment reduced by bills', "
                    f"rules: {{ amount: {red}.amount, billed: {red}.billed, remaining: {red}.remaining, bills: {red}.bills }} }})",
    })
    s.flow.append(s.code("Step 12: Rule: reduce commitments by bills", code, inputs))
    s.flow.append(s.iterator("Each commitment billed", data("Step 12: Rule: reduce commitments by bills", "result.items")))
    it = lambda f: data("Each commitment billed", f)  # noqa: E731
    s.flow.append(s.http("Step 12: Reduce the commitment", "PATCH", cfg("budget_url") + "/commitments/" + it("commitment_q"),
                         body=it("reduce_body"), parse=False, onerror=[
                             s.rpc("Mark bill keys failed", "finish_keys", it("failed_keys_body")),
                             s.exception("Exception queue: commitment write failed", it("failed_body")),
                             s.ignore()]))

    def done(tag: str) -> list[dict]:
        return [s.rpc(f"Mark bill keys done ({tag})", "finish_keys", it("done_keys_body")),
                s.decision_log(f"Decision log: commitment ({tag})", it("log_body"))]

    s.flow.append(s.router("Over tolerance?", [
        (s.when("over tolerance", it("over"), "true"),
         [s.exception("Step 12: Exception queue: bill over commitment", it("over_body")),
          s.http("Step 12: Tell the budget owner", "POST", cfg("messaging_url") + "/messages", body=it("owner_message"), parse=False)]
         + done("over tolerance")),
        (s.when("within tolerance", it("over"), "true", "text:notequal"), done("within tolerance")),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R11.3/make/, scenario)."""
    return [("blueprint.json", to_approval()), ("answer.blueprint.json", approval_answered()),
            ("morning.blueprint.json", each_morning()), ("export.blueprint.json", new_export())]
