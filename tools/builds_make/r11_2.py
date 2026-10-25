"""R11.2 Block a purchase before the order is placed, as Make scenarios: rules only, no AI step.

Source: book Chapter 11, recipe R11.2, build steps 1 to 11 (recipes/R11.2/build-spec.md).
The rules are the n8n build's own JavaScript (tools/builds/r11_2.py), run through n8n_rule.
Two scenarios, because a Make scenario has one trigger: the request check (webhook) and the
morning backstop (schedule, daily at 07:00).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R11.2"
RULES_JS, BACKSTOP_JS = n8n_build(R).RULES_JS, n8n_build(R).BACKSTOP_JS
CONFIG = {
    "requests_url": "https://<your request list API>",
    "vendors_url": "https://<your vendor-record export API>",
    "policy_url": "https://<your policy list API>",
    "ledger_url": "https://<your accounting platform export API>",
    "messaging_url": "https://<your messaging API>",
    "split_window_days": 14,
    "split_limits": [500, 10000],
    "no_po_limit": 500,
    "margin_working_days": 5,
    "price_drop_pct": 30,
    "price_approver": "<your purchasing approver>",
    "backstop_reviewer": "<your finance reviewer>",
}


def request_check() -> Scenario:
    s = Scenario(R, "R11.2 Block a purchase before the order is placed", "webhook", test_key="r11-2-request")
    s.flow.append(s.webhook("Step 1: Request ready or edited"))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    read = s.http("Read request", "GET", cfg("requests_url") + "/requests/{{encodeURL(1.request_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    s.flow.append(s.reserve_key("Step 2: Reserve key", "{{1.request_id}}:{{1.version}}"))
    rq = s.ref("Read request")
    req = lambda f: "{{" + f"{rq}.data.{f}" + "}}"  # noqa: E731
    supplier = s.http("Read supplier record", "GET", cfg("vendors_url") + "/records/{{encodeURL(" + f"{rq}.data.supplier_id" + ")}}")
    supplier["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: this version was checked before
    s.flow.append(supplier)
    s.flow.append(s.http("Read policy list", "GET", cfg("policy_url") + "/budget_lines/{{encodeURL(" + f"{rq}.data.budget_line" + ")}}"))
    s.flow.append(s.http("Read last prices paid", "GET", cfg("ledger_url") + "/last_prices", query={"_wrap": "1"}))
    s.flow.append(s.http("Read recent requests", "GET", cfg("requests_url") + "/requests",
                         query={"_wrap": "1", "supplier_id": req("supplier_id"), "budget_line": req("budget_line")}))
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    code, inputs = n8n_rule(RULES_JS, {
        "Config": "{{" + f"{c}.result" + "}}",
        "Read request": data("Read request"),
        "Read supplier record": data("Read supplier record"),
        "Read policy list": data("Read policy list"),
        "Read last prices paid": data("Read last prices paid"),
        "Read recent requests": data("Read recent requests"),
    }, bodies={
        "status_body": "JSON.stringify({ status: out.status, total: out.total, reasons: out.reasons })",
        "done_body": "JSON.stringify({ status: 'done', result: out.status })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: $('Read request').first().json.id, decision: out.status, "
                    "rules: Object.assign({}, out.rules, { reasons: out.reasons, total: out.total }) })",
        "failed_body": f"JSON.stringify({{ recipe: '{R}', item: $('Read request').first().json.id, reason: 'write failed', "
                       "detail: 'Status write failed; check the request before releasing the key', owner: $('Config').first().json.price_approver })",
        "requester_message": "JSON.stringify({ to: $('Read request').first().json.requester, "
                             "subject: 'Purchase request ' + $('Read request').first().json.id + ' blocked', "
                             "text: 'Fix and save again: ' + out.reasons.join('; ') })",
        "approver_message": "JSON.stringify({ to: $('Config').first().json.price_approver, "
                            "subject: 'Price check: request ' + $('Read request').first().json.id, text: out.rules.price || '' })",
    })
    s.flow.append(s.code("Rules: steps 3 to 8", code, inputs))
    ru = s.ref("Rules: steps 3 to 8")
    out = lambda f: "{{" + f"{ru}.result.{f}" + "}}"  # noqa: E731
    key_q = "{{encodeURL(1.request_id)}}%3A{{encodeURL(1.version)}}"
    url = cfg("requests_url") + "/requests/{{encodeURL(1.request_id)}}"
    msg = cfg("messaging_url") + "/messages"

    def route(outcome: str, set_status: str, tell: tuple[str, str] | None, tag: str):
        failed = lambda step: s.write_failed(step, key_q, out("failed_body"))  # noqa: E731
        flow = [s.http(set_status, "PATCH", url, body=out("status_body"), parse=False, onerror=failed(set_status))]
        if tell:
            flow.append(s.http(tell[0], "POST", msg, body=out(tell[1]), parse=False, onerror=failed(tell[0])))
        flow.append(s.finish_key(f"Mark key done ({tag})", key_q, out("done_body")))
        flow.append(s.decision_log(f"Decision log ({tag})", out("log_body")))
        return s.when(f"outcome is {outcome}", out("outcome"), outcome), flow

    s.flow.append(s.router("Outcome", [
        route("pass", "Step 9: Set checked; to approval", None, "pass"),
        route("no_po", "Step 4: Set no PO needed", None, "no PO"),
        route("blocked", "Step 10: Set blocked", ("Step 10: Tell the requester", "requester_message"), "blocked"),
        route("price_check", "Step 8: Set waiting for price check", ("Step 8: Tell the price approver", "approver_message"), "price check"),
    ]))
    return s


def morning_backstop() -> Scenario:
    s = Scenario(R, "R11.2 Block a purchase: morning backstop", "schedule", test_key="Step 11: Each morning", schedule="every day at 07:00")
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    pos = s.http("Read yesterday's POs", "GET", cfg("ledger_url") + "/pos", query={"_wrap": "1"})
    pos["filter"] = s.continue_unless_stopped()
    s.flow.append(pos)
    s.flow.append(s.http("Read approved requests", "GET", cfg("requests_url") + "/requests", query={"_wrap": "1", "status": "approved"}))
    code, inputs = n8n_rule(BACKSTOP_JS, {
        "Config": "{{" + f"{c}.result" + "}}",
        "Read yesterday's POs": "{{" + str(s.ref("Read yesterday's POs")) + ".data}}",
        "Read approved requests": "{{" + str(s.ref("Read approved requests")) + ".data}}",
    }, many=True, bodies={
        "exception_body": f"JSON.stringify({{ recipe: '{R}', item: out.po, reason: 'PO without approved request', "
                          "detail: 'PO ' + out.po + ' for ' + out.amount + ' has no approved request', owner: $('Config').first().json.backstop_reviewer })",
        "message": "JSON.stringify({ to: $('Config').first().json.backstop_reviewer, subject: 'PO without an approved request', "
                   "text: 'PO ' + out.po + ' for ' + out.amount })",
    })
    s.flow.append(s.code("Rule: POs with no approved request", code, inputs))
    s.flow.append(s.iterator("Each PO without approval", "{{" + f"{s.ref('Rule: POs with no approved request')}.result.items" + "}}"))
    it = s.ref("Each PO without approval")
    s.flow.append(s.exception("Exception queue: PO without approval", "{{" + f"{it}.exception_body" + "}}"))
    s.flow.append(s.http("Step 11: Tell the finance reviewer", "POST", cfg("messaging_url") + "/messages",
                         body="{{" + f"{it}.message" + "}}", parse=False))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R11.2/make/, scenario)."""
    return [("blueprint.json", request_check()), ("backstop.blueprint.json", morning_backstop())]
