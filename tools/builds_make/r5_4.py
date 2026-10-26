"""R5.4 Route quote approval by value and discount, as Make scenarios: rules only, no AI step.

Source: book Chapter 5, recipe R5.4, Table 5.1 and build steps 1 to 8 (recipes/R5.4/build-spec.md).
The rules are the n8n build's own JavaScript (tools/builds/r5_4.py), run through n8n_rule.
Four scenarios, because a Make scenario has one trigger: routing (webhook, the quote is set
"awaiting approval"), the approver's decision (webhook), the deadline check (schedule, every
hour) and the declared weekly backstop (schedule, every Monday at 07:00).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R5.4"
N8N = n8n_build(R)
T, D, H, WK = N8N.T, N8N.D, N8N.H, N8N.WK
CONFIG = {
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
}
OWNER = "$('Config').first().json.approvers.sales_lead.person"


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


def start(s: Scenario, webhook: str | None) -> tuple:
    """Trigger, Config and the stop flag; returns (cfg, out) mapping helpers."""
    if webhook:
        s.flow.append(s.webhook(webhook))
    s.flow.append(s.config(CONFIG))
    s.flow += s.stop_flag()
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    out = lambda step, f: "{{" + f"{s.ref(step)}.result.{f}" + "}}"  # noqa: E731
    return cfg, out


def routing() -> Scenario:
    s = Scenario(R, "R5.4 Route quote approval by value and discount", "webhook", test_key="r5-4-awaiting-approval")
    cfg, out = start(s, T)
    reserve = s.reserve_key("Step 2: Reserve key", "{{1.quote_id}}:{{1.revision}}")
    reserve["filter"] = s.continue_unless_stopped()
    s.flow.append(reserve)
    quote_url = cfg("crm_url") + "/quotes/{{encodeURL(1.quote_id)}}"
    read = s.http("Read the quote", "GET", quote_url)
    read["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: this revision was routed before
    s.flow.append(read)
    s.flow.append(s.http("Read the price list", "GET", cfg("crm_url") + "/price_lists/current"))
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    trig = (T, ["quote_id", "revision"])
    ev = f"$('{T}').first().json.body"
    s3 = "Step 3: Recompute from the CRM record"
    code, inputs = rule(N8N.STEP3_JS, {
        "Read the quote": data("Read the quote"), "Read the price list": data("Read the price list"),
        "Config": "{{" + f"{s.ref('Config')}.result" + "}}",
    }, input_node="Read the quote", trigger=trig, bodies={
        "back_body": "JSON.stringify({ status: 'back to R5.3', locked: true, return_reason: 'price list ' + out.stamped + ' replaced by ' + out.list_version })",
        "salesperson_message": f"JSON.stringify({{ to: $('Read the quote').first().json.salesperson, subject: 'Quote ' + {ev}.quote_id + ' back to drafting', "
                               "text: 'The price list it was drafted from is no longer current; mark the opportunity ready to quote again to redraft it.' })",
        "failed_body": f"JSON.stringify({{ recipe: '{R}', item: String({ev}.quote_id), reason: 'write failed', "
                       f"detail: 'Quote status or request write failed, not retried; route by hand, then release the key', owner: {OWNER} }})",
    })
    s.flow.append(s.code(s3, code, inputs))
    key_q = "{{encodeURL(1.quote_id)}}%3A{{encodeURL(1.revision)}}"
    failed = lambda step: s.write_failed(step, key_q, out(s3, "failed_body"))  # noqa: E731
    msg = cfg("messaging_url") + "/messages"

    def close(tag: str, sources: dict, executed=()):
        """Routing summary, then the key and the decision log: repeated on each route, since routes never meet."""
        name = f"Routing summary ({tag})"
        code, inputs = rule(N8N.ROUTE_SUMMARY_JS, sources, executed=executed, trigger=trig, bodies={
            "done_body": "JSON.stringify({ status: 'done', result: out.decision })",
            "log_body": f"JSON.stringify({{ recipe: '{R}', item: {ev}.quote_id + ':' + {ev}.revision, decision: out.decision, rules: out.rules }})",
        })
        m = s.code(name, code, inputs)
        return [m, s.finish_key(f"Mark key done ({tag})", key_q, out(name, "done_body")),
                s.decision_log(f"Decision log ({tag})", out(name, "log_body"))]

    t5 = "Step 5: Rule: Table 5.1"
    code, inputs = rule(N8N.TABLE_JS, {
        "Config": "{{" + f"{s.ref('Config')}.result" + "}}", "Read the quote": data("Read the quote"),
        s3: "{{" + f"{s.ref(s3)}.result" + "}}",
    }, trigger=trig, bodies={
        "lock_body": "JSON.stringify({ locked: true, approver: out.approver, deputy: out.deputy, approval_level: out.level, "
                     "deadline_hours: out.deadline_hours, requested_at: out.requested_at, escalation: 0 })",
        "request_message": f"JSON.stringify({{ to: out.approver, subject: 'Approve quote ' + {ev}.quote_id + ' revision ' + {ev}.revision, "
                           f"text: 'Value after discount ' + $('{s3}').first().json.value + '; largest line discount ' + $('{s3}').first().json.largest_discount + '%; ' "
                           "+ out.why + '. Record your decision in the CRM within ' + out.deadline_hours + ' hours.', checklist: $('Config').first().json.checklist })",
        "owen_message": f"JSON.stringify({{ to: $('Config').first().json.systems_owner, subject: 'Approval request not sent: quote ' + {ev}.quote_id, "
                        "text: 'The quote is returned and locked; check the messaging connection, then set it awaiting approval again.' })",
    })
    summary_src = {s3: "{{" + f"{s.ref(s3)}.result" + "}}"}
    table = s.code(t5, code, inputs)
    summary_src[t5] = "{{" + f"{s.ref(t5)}.result" + "}}"
    lock = s.http("Step 6: Lock and record the approver", "PATCH", quote_url, body=out(t5, "lock_body"), parse=False,
                  onerror=failed("Step 6: Lock and record the approver"))
    # Step 6: if sending fails, return the quote, locked, and tell Owen; then close as n8n does.
    returned = "Step 6: Return the quote, locked"
    not_sent = [s.http(returned, "PATCH", quote_url, parse=False,
                       body='{"status": "returned", "locked": true, "return_reason": "approval request not sent"}', onerror=failed(returned)),
                s.http("Step 6: Tell Owen", "POST", msg, body=out(t5, "owen_message"), parse=False, onerror=failed("Step 6: Tell Owen"))]
    not_sent += close("returned", summary_src, executed=(returned,)) + [s.ignore()]
    send = s.http("Step 6: Send the request with Checklist 13.1", "POST", msg, body=out(t5, "request_message"), parse=False, onerror=not_sent)
    current_route = [table, lock, send] + close("routed", summary_src)

    back = [s.http("Step 4: Send back to R5.3", "PATCH", quote_url, body=out(s3, "back_body"), parse=False, onerror=failed("Step 4: Send back to R5.3")),
            s.http("Step 4: Tell the salesperson", "POST", msg, body=out(s3, "salesperson_message"), parse=False, onerror=failed("Step 4: Tell the salesperson"))]
    back += close("back", {s3: "{{" + f"{s.ref(s3)}.result" + "}}"})
    current = out(s3, "current")
    s.flow.append(s.router("Step 4: Stamped price list current?", [
        (s.when("price list current", current, "true"), current_route),
        (s.when("price list not current", current, "true", "text:notequal"), back),
    ]))
    return s


def decision() -> Scenario:
    s = Scenario(R, "R5.4 Route quote approval: approver's decision", "webhook", test_key="r5-4-decision")
    cfg, out = start(s, D)
    reserve = s.reserve_key("Step 8: Reserve decision key", "decision:{{1.quote_id}}:{{1.revision}}")
    reserve["filter"] = s.continue_unless_stopped()
    s.flow.append(reserve)
    quote_url = cfg("crm_url") + "/quotes/{{encodeURL(1.quote_id)}}"
    read = s.http("Read the quote (decision)", "GET", quote_url)
    read["filter"] = s.is_new_key("Step 8: Reserve decision key")  # a copy stops here: this decision was handled
    s.flow.append(read)
    s.flow.append(s.http("Read the price list (decision)", "GET", cfg("crm_url") + "/price_lists/current"))
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    trig = (D, ["quote_id", "revision", "decision", "by", "comment"])
    dv, dq = f"$('{D}').first().json.body", "$('Read the quote (decision)').first().json"
    s8 = "Step 8: Rule: accept the decision?"
    code, inputs = rule(N8N.DECISION_JS, {
        "Config": "{{" + f"{s.ref('Config')}.result" + "}}",
        "Read the quote (decision)": data("Read the quote (decision)"),
        "Read the price list (decision)": data("Read the price list (decision)"),
    }, trigger=trig, bodies={
        "unlock_body": f"JSON.stringify({{ status: 'approved', locked: false, approved_by: {dv}.by, approved_at: new Date().toISOString(), approved_revision: {dq}.revision }})",
        "return_body": f"JSON.stringify({{ status: 'returned', locked: true, rejected_by: {dv}.by, comment: {dv}.comment || '' }})",
        "back_body": "JSON.stringify({ status: 'back to R5.3', locked: true, return_reason: out.reason })",
        "salesperson_message": f"JSON.stringify({{ to: {dq}.salesperson, subject: 'Quote ' + {dv}.quote_id + ' back to drafting', "
                               "text: 'The price list changed while it waited for approval; mark the opportunity ready to quote again to redraft it.' })",
        "refused_body": f"JSON.stringify({{ recipe: '{R}', item: String({dv}.quote_id), reason: 'decision not accepted', detail: out.reason, owner: {OWNER} }})",
        "failed_body": f"JSON.stringify({{ recipe: '{R}', item: String({dv}.quote_id), reason: 'write failed', "
                       f"detail: 'Decision write failed, not retried; set the quote by hand, then release the key', owner: {OWNER} }})",
    })
    s.flow.append(s.code(s8, code, inputs))
    # The decision summary reads only the rule, the webhook and the quote, none of which a route
    # writes, so Make computes it once before the router instead of once on each route.
    code, inputs = rule(N8N.DECISION_SUMMARY_JS, {
        s8: "{{" + f"{s.ref(s8)}.result" + "}}", "Read the quote (decision)": data("Read the quote (decision)"),
    }, trigger=trig, bodies={
        "done_body": "JSON.stringify({ status: 'done', result: out.decision })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {dv}.quote_id + ':' + {dq}.revision, decision: out.decision, rules: out.rules, approved_by: out.approver }})",
    })
    s.flow.append(s.code("Decision summary", code, inputs))
    key_q = "decision%3A{{encodeURL(1.quote_id)}}%3A{{encodeURL(1.revision)}}"
    failed = lambda step: s.write_failed(step, key_q, out(s8, "failed_body"))  # noqa: E731

    def close(tag: str):
        return [s.finish_key(f"Mark decision key done ({tag})", key_q, out("Decision summary", "done_body")),
                s.decision_log(f"Step 8: Log approver, time and version ({tag})", out("Decision summary", "log_body"))]

    def write(name, method, url, body):
        return s.http(name, method, url, body=body, parse=False, onerror=failed(name))

    outcome = out(s8, "outcome")
    s.flow.append(s.router("Step 8: Outcome", [
        (s.when("outcome is approve", outcome, "approve"),
         [write("Step 8: Unlock sending", "PATCH", quote_url, out(s8, "unlock_body"))] + close("approve")),
        (s.when("outcome is reject", outcome, "reject"),
         [write("Step 8: Return with the comment", "PATCH", quote_url, out(s8, "return_body"))] + close("reject")),
        (s.when("outcome is back", outcome, "back"),
         [write("Step 8: Send back to R5.3", "PATCH", quote_url, out(s8, "back_body")),
          write("Step 8: Tell the salesperson", "POST", cfg("messaging_url") + "/messages", out(s8, "salesperson_message"))] + close("back")),
        (s.when("outcome is refuse", outcome, "refuse"),
         [s.exception("Exception queue: decision not accepted", out(s8, "refused_body"))] + close("refuse")),
    ]))
    return s


def deadlines() -> Scenario:
    s = Scenario(R, "R5.4 Route quote approval: deadline check, every hour", "schedule", test_key=H, schedule="every hour")
    cfg, out = start(s, None)
    read = s.http("Read quotes awaiting approval", "GET", cfg("crm_url") + "/quotes", query={"_wrap": "1", "status": "awaiting approval"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    s7 = "Step 7: Rule: deadline passed?"
    cl = "$('Config').first().json.checklist"
    code, inputs = rule(N8N.DEADLINE_JS, {
        "Config": "{{" + f"{s.ref('Config')}.result" + "}}",
        "Read quotes awaiting approval": "{{" + f"{s.ref('Read quotes awaiting approval')}.data" + "}}",
    }, many=True, bodies={
        "quote_q": "encodeURIComponent(out.quote_id)",
        "remind_message": f"JSON.stringify({{ to: out.approver, subject: 'Reminder: approve quote ' + out.quote_id, text: 'The response deadline has passed. ' + {cl} }})",
        "deputy_message": f"JSON.stringify({{ to: out.deputy, subject: 'Please approve quote ' + out.quote_id + ' as deputy', text: 'The approver has not decided by twice the deadline. ' + {cl} }})",
        "escalation_body": "JSON.stringify({ escalation: out.stage })",
        "ben_message": f"JSON.stringify({{ to: {OWNER}, subject: 'Quote ' + out.quote_id + ' returned: no decision', "
                       "text: 'No decision by three times the deadline; the quote is returned, locked.' })",
        "failed_body": f"JSON.stringify({{ recipe: '{R}', item: String(out.quote_id), reason: 'deadline action failed', "
                       f"detail: 'A reminder, deputy request or return failed, not retried; act on the quote by hand', owner: {OWNER} }})",
    })
    s.flow.append(s.code(s7, code, inputs))
    s.flow.append(s.iterator("Each quote past a deadline", "{{" + f"{s.ref(s7)}.result.items" + "}}"))
    it = s.ref("Each quote past a deadline")
    f = lambda k: "{{" + f"{it}.{k}" + "}}"  # noqa: E731
    msg = cfg("messaging_url") + "/messages"
    quote_url = cfg("crm_url") + "/quotes/" + f("quote_q")

    def write(name, method, url, body):
        """Deadline writes never retry; a failure goes to the exception queue and ends this quote's bundle."""
        return s.http(name, method, url, body=body, parse=False,
                      onerror=[s.exception(f"{name}: exception queue", f("failed_body")), s.ignore()])

    action = f("action")
    s.flow.append(s.router("Step 7: Action", [
        (s.when("action is remind", action, "remind"),
         [write("Step 7: Remind the approver", "POST", msg, f("remind_message")),
          write("Step 7: Record the escalation (remind)", "PATCH", quote_url, f("escalation_body"))]),
        (s.when("action is deputy", action, "deputy"),
         [write("Step 7: Ask the deputy", "POST", msg, f("deputy_message")),
          write("Step 7: Record the escalation (deputy)", "PATCH", quote_url, f("escalation_body"))]),
        (s.when("action is return", action, "return"),
         [write("Step 7: Return the quote, locked", "PATCH", quote_url,
                '{"status": "returned", "locked": true, "escalation": 3, "return_reason": "no decision by three times the deadline"}'),
          write("Step 7: Tell Ben", "POST", msg, f("ben_message"))]),
    ]))
    return s


def backstop() -> Scenario:
    s = Scenario(R, "R5.4 Route quote approval: weekly backstop", "schedule", test_key=WK, schedule="every Monday at 07:00")
    cfg, out = start(s, None)
    read = s.http("Read quotes sent", "GET", cfg("crm_url") + "/quotes", query={"_wrap": "1", "status": "sent"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    rb = "Rule: sent without approval?"
    code, inputs = rule(N8N.BACKSTOP_JS, {
        "Config": "{{" + f"{s.ref('Config')}.result" + "}}", "Read quotes sent": "{{" + f"{s.ref('Read quotes sent')}.data" + "}}",
    }, many=True, bodies={
        "exception_body": f"JSON.stringify({{ recipe: '{R}', item: String(out.quote_id), reason: 'quote sent unapproved', "
                          f"detail: 'Quote ' + out.quote_id + ' revision ' + out.revision + ' was sent without approval of that revision', owner: {OWNER} }})",
        "ben_message": f"JSON.stringify({{ to: {OWNER}, subject: 'Quote sent without approval', text: 'Quote ' + out.quote_id + ' was sent unapproved; call the customer.' }})",
    })
    s.flow.append(s.code(rb, code, inputs))
    s.flow.append(s.iterator("Each quote sent unapproved", "{{" + f"{s.ref(rb)}.result.items" + "}}"))
    it = s.ref("Each quote sent unapproved")
    s.flow.append(s.exception("Exception queue: sent unapproved", "{{" + f"{it}.exception_body" + "}}"))
    s.flow.append(s.http("Backstop: Tell Ben", "POST", cfg("messaging_url") + "/messages", body="{{" + f"{it}.ben_message" + "}}", parse=False))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R5.4/make/, scenario)."""
    return [("blueprint.json", routing()), ("decision.blueprint.json", decision()),
            ("deadlines.blueprint.json", deadlines()), ("backstop.blueprint.json", backstop())]
