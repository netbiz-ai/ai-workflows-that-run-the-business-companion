"""R7.4 Run the exception queue with reasons, owners and ageing, as Make scenarios.

Source: book Chapter 7, recipe R7.4, build steps 1 to 8 (recipes/R7.4/build-spec.md);
AI step: recipes/R7.4/prompts/draft-query.md. The AI only drafts; the owner decides. The rules
are the n8n build's own JavaScript (tools/builds/r7_4.py), run through n8n_rule.
Three scenarios, because a Make scenario has one trigger: an item added to the queue (webhook,
steps 1 to 6), an item closed (webhook, step 7) and the morning list (schedule, every working
day, Monday to Friday, at 08:00, step 8). n8n's "Which event?" node only asked which trigger ran,
so it is not built.

Differences from the n8n build, all forced by Make:
- "Step 2: Find the first item" is a table-API read of the key log (n8n runs it as SQL).
- The n8n AI call tries three times (mk's ai_step, tries=3): each try's error route holds the
  next try, and Make's Resume handler hands the last answer on.
- n8n's "Step 5: AI error" node runs inside "Step 5: Rule: check the draft" (on_ai_error), and
  "Step 4: No draft for this code" becomes bodies of "Step 3: Rule: assign the owner": Make
  branches never meet again, so n8n's "Step 5: Draft result" node, which only joins them, is
  not built and each route repeats the Teams post and the closing steps, named for its route.
- "Step 7: Rule: what happens next" reads the closed-item webhook as n8n's body; a Make
  webhook's output cannot be mapped whole, so each field is its own input (with_body()).
- Each write's error route marks the key failed and adds the exception-queue row
  (write_failed); step 7's writes, which have no key, add the exception-queue row only.
- $now.toISODate() in the n8n bodies is the UTC date here, as Make's Code app runs in UTC.
- Step 2's reserve body is written by hand: the key is the invoice ID and the reason code,
  which are IDs and codes from a fixed list, as the key log needs.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R7.4"
N8N = n8n_build(R)
T, C, M = N8N.T, N8N.C, N8N.M
CONFIG = {
    "queue_url": "https://<your queue list API>",
    "review_url": "https://<your review list API>",
    "teams_url": "https://<your Teams messaging API>",
    "approvals_url": "https://<your approval list API>",
    "rematch_url": "https://<your n8n>/webhook/r7-2-ready",
    "reason_owners": {
        "needs a person": "<your AP owner>", "unknown supplier": "<your AP owner>",
        "no PO": "<your purchasing approver>", "no receipt": "<your purchasing approver>",
        "outside tolerance": "<your purchasing approver>", "already invoiced": "<your purchasing approver>",
        "pairing rejected": "<your purchasing approver>",
        "lookup error": "<your workflow owner>", "reservation failed": "<your workflow owner>",
        "supplier on hold": "<your caller>",
    },
    "services_codes": ["no PO", "no receipt"],
    "services_suppliers": ["<your rent, utility and carrier supplier IDs>"],
    "services_owner": "<your finance assistant>",
    "escalation_owner": "<your AP owner>",
    "query_codes": ["<your mismatch and missing-document codes>"],
    "banned_words": ["paid", "<your banned query words>"],
    "aging_limit_days": "<your aging limit, working days>",
    "approval_limit": 10000,
    "approver_to_limit": "<your approver up to the limit>",
    "approver_above": "<your approver above the limit>",
    "approver_own_items": "<who approves the approvers' own items>",
    "workflow_owner": "<your workflow owner>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
CFG = "$('Config').first().json"
ITEM = "$('Step 1: Read the queue item').first().json"
OWN = "$('Step 3: Rule: assign the owner').first().json"
KEY = f"{ITEM}.invoice_id + ':' + {ITEM}.reason_code"
TODAY = "new Date().toISOString().slice(0, 10)"
AI_ERROR_JS = "return [{ json: { draft: null, draft_check: 'dropped: AI error after three tries' } }];"
FAILED = (f"JSON.stringify({{ recipe: '{R}', item: {ITEM}.id, reason: 'write failed', "
          f"detail: 'Queue or Teams write failed, never retried; tell the owner by hand', owner: {CFG}.workflow_owner }})")




def start(s: Scenario, trigger: str | None):
    if trigger:
        s.flow.append(s.webhook(trigger))
    s.flow.append(s.config(CONFIG))
    s.flow += s.stop_flag()
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    res = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    return cfg, res, data, "{{" + f"{c}.result" + "}}"


def item_added() -> Scenario:
    s = Scenario(R, "R7.4 Run the exception queue: item added", "webhook", test_key="r7-4-item")
    cfg, res, data, config = start(s, T)  # your queue list calls this when R7.1, R7.2 or R7.3 adds an item: {item_id}
    items = cfg("queue_url") + "/items/"
    read = s.http("Step 1: Read the queue item", "GET", items + "{{encodeURL(1.item_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    r = s.ref("Step 1: Read the queue item")
    key = "{{" + f"{r}.data.invoice_id" + "}}:{{" + f"{r}.data.reason_code" + "}}"
    key_q = "{{encodeURL(" + f"{r}.data.invoice_id" + ")}}%3A{{encodeURL(" + f"{r}.data.reason_code" + ")}}"
    item_url = items + "{{encodeURL(" + f"{r}.data.id" + ")}}"
    s.flow.append(s.reserve_key("Step 2: Reserve key", key))
    step1 = {"Config": config, "Step 1: Read the queue item": data("Step 1: Read the queue item")}

    # ---- Step 2: a repeat adds a note to the first item for this invoice and reason ---------
    find = s.http("Step 2: Find the first item", "GET", s.table("/key_log"), query={"recipe": f"eq.{R}", "key": "eq." + key, "select": "result"})
    first = s.http("Step 2: Read the first item", "GET", items + "{{encodeURL(" + f"{s.ref('Step 2: Find the first item')}.data[1].result" + ")}}")
    nn = "Step 2: Note for the first item"
    code, inputs = n8n_rule(N8N.NOTE_JS, {**step1, "Step 2: Read the first item": data("Step 2: Read the first item")}, bodies={
        "first_q": "encodeURIComponent(out.first_id)",
        "note_body": "JSON.stringify({ notes: out.notes })",
        "close_body": "JSON.stringify({ status: 'merged', merged_into: out.first_id })",  # one item per invoice and reason
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {ITEM}.id, decision: 'repeat: noted on ' + out.first_id, "
                     f"rules: {{ key: {KEY}, duplicate: true }} }})"),
        "failed_body": FAILED,
    })
    note = s.code(nn, code, inputs)
    n = lambda f: res(nn, f)  # noqa: E731
    failed = lambda step, body: s.write_failed(step, key_q, body)  # noqa: E731
    repeat = [find, first, note,
              s.http("Step 2: Add the note", "PATCH", items + n("first_q"), body=n("note_body"), parse=False,
                     onerror=failed("Step 2: Add the note", n("failed_body"))),
              s.http("Step 2: Close the repeat", "PATCH", item_url, body=n("close_body"), parse=False,
                     onerror=failed("Step 2: Close the repeat", n("failed_body"))),
              s.decision_log("Step 2: Decision log (repeat)", n("log_body"))]

    # ---- Step 3: the reason code's owner -------------------------------------------------
    remember = s.finish_key("Step 2: Remember the first item", key_q,
                            '{"status": "in progress", "result": "{{' + f"{r}.data.id" + '}}"}')
    on = "Step 3: Rule: assign the owner"

    def closing(out: str, tag: str) -> dict:
        """Bodies for step 6 and the closing steps; out is the draft result (draft, draft_check)."""
        return {
            "post_body": (f"JSON.stringify({{ to: {OWN}.owner, item_id: {ITEM}.id, invoice_id: {ITEM}.invoice_id, "
                          f"reason_code: {ITEM}.reason_code, details: {ITEM}.details || '', draft: {out}.draft, draft_check: {out}.draft_check }})"),
            "done_body": f"JSON.stringify({{ status: 'done', result: {ITEM}.id }})",
            "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {ITEM}.id, decision: 'to ' + {OWN}.owner + ({out}.draft ? ', with a draft' : ', no draft'), "
                         f"rules: {{ reason_code: {ITEM}.reason_code, owner: {OWN}.rule, draft: {out}.draft_check }} }})"),
            "failed_body": FAILED,
        }

    # n8n's "Step 4: No draft for this code", for the route without a supplier query.
    no_draft = "({ draft: null, draft_check: 'no query for this reason code' })"
    code, inputs = n8n_rule(N8N.OWNER_JS, step1, input_node="Config", bodies={
        "query_flag": "out.query ? 'yes' : 'no'",
        "owner_body": f"JSON.stringify({{ owner: out.owner, status: 'open', assigned_on: {TODAY} }})",
        **{k: v.replace(OWN, "out") for k, v in closing(no_draft, "no query").items()},
    })
    owner = s.code(on, code, inputs)
    o = lambda f: res(on, f)  # noqa: E731
    set_owner = s.http("Step 3: Set the owner", "PATCH", item_url, body=o("owner_body"), parse=False,
                       onerror=failed("Step 3: Set the owner", o("failed_body")))

    def post_and_close(tag: str, b) -> list[dict]:
        """Step 6: the owner sends, rewrites or ignores the draft; nothing goes to the supplier."""
        post = f"Step 6: Post to the owner in Teams ({tag})"
        return [s.http(post, "POST", cfg("teams_url") + "/messages", body=b("post_body"), parse=False, onerror=failed(post, b("failed_body"))),
                s.finish_key(f"Mark key done ({tag})", key_q, b("done_body")),
                s.decision_log(f"Decision log ({tag})", b("log_body"))]

    # ---- Steps 4 and 5: the AI drafts a query; the rule decides whether the draft is kept ----
    vars_js = ("{ banned_words: $('Config').first().json.banned_words.join(', '), "
               f"invoice_id: {ITEM}.invoice_id, supplier: {ITEM}.supplier || '', reason_code: {ITEM}.reason_code, item_details: {ITEM}.details || '' }}")
    ai = s.ai_step("Step 4", ROOT / "recipes/R7.4/prompts/draft-query.md", vars_js, step1, max_tokens=2048, tries=3)
    call = s.ref("Step 4: AI call")
    ck = "Step 5: Rule: check the draft"
    code, inputs = n8n_rule(N8N.CHECK_JS, {**step1, on: "{{" + f"{s.ref(on)}.result" + "}}", "Step 4: AI call": "{{" + f"{call}.data" + "}}"},
                            ai_status="{{" + f"{call}.statusCode" + "}}", on_ai_error=AI_ERROR_JS, bodies=closing("out", "query"))
    check = s.code(ck, code, inputs)
    query = ai + [check] + post_and_close("with a query", lambda f: res(ck, f))

    s.flow.append(s.router("New key?", [
        (s.when("a repeat (copy)", "{{" + f"{s.ref('Step 2: Reserve key')}.data" + "}}", "false"), repeat),
        (s.is_new_key("Step 2: Reserve key"), [remember, owner, set_owner, s.router("Takes a supplier query?", [
            (s.when("takes a supplier query", o("query_flag"), "yes"), query),
            (s.when("no query for this code", o("query_flag"), "yes", "text:notequal"), post_and_close("no query", o)),
        ])]),
    ]))
    return s


def item_closed() -> Scenario:
    s = Scenario(R, "R7.4 Run the exception queue: item closed", "webhook", test_key="r7-4-closed")
    # Your queue list calls this when an owner closes an item:
    # {item_id, resolution: corrected record | released hold | resolved | rejected, resolved_by, note}.
    cfg, res, data, config = start(s, C)
    read = s.http("Step 7: Read the closed item", "GET", cfg("queue_url") + "/items/{{encodeURL(1.item_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    inv_q = "{{encodeURL(" + f"{s.ref('Step 7: Read the closed item')}.data.invoice_id" + ")}}"
    s.flow.append(s.http("Step 7: Read the invoice record", "GET", cfg("review_url") + "/records/" + inv_q))
    cb = f"$('{C}').first().json.body"
    inv = "$('Step 7: Read the closed item').first().json.invoice_id"
    rn = "Step 7: Rule: what happens next"
    fields = ("item_id", "resolution", "resolved_by", "note")
    code, inputs = n8n_rule(N8N.CLOSE_JS, {
        "Config": config, "Step 7: Read the closed item": data("Step 7: Read the closed item"),
        "Step 7: Read the invoice record": data("Step 7: Read the invoice record"),
    }, prelude=(f"// The webhook's fields, as the rule reads them in n8n.\nDATA[{json.dumps(C)}] = [{{ json: {{ body: {{ "
                + ", ".join(f"{f}: input.t_{f}" for f in fields) + " } } }];"), bodies={
        "rematch_body": f"JSON.stringify({{ record_id: {inv}, resolved_by: {cb}.resolved_by }})",  # starts R7.2 again
        "approval_body": (f"JSON.stringify({{ invoice_id: {inv}, approver: out.approver, total: $('Step 7: Read the invoice record').first().json.total, "
                          f"note: {cb}.note || '', resolved_by: {cb}.resolved_by, status: 'waiting' }})"),  # the approver sees the owner's note
        "reject_body": f"JSON.stringify({{ status: 'rejected', rejected_by: {cb}.resolved_by, note: {cb}.note || '' }})",
        "close_body": f"JSON.stringify({{ status: 'closed', resolution: {cb}.resolution, resolved_by: {cb}.resolved_by, closed_on: {TODAY} }})",
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {cb}.item_id, decision: 'closed: ' + out.route + (out.approver ? ' to ' + out.approver : ''), "
                     "rules: out.rules })"),
        "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: {cb}.item_id, reason: 'write failed', "
                        f"detail: 'Rematch, approval, rejection or close write failed, never retried; finish it by hand', owner: {CFG}.workflow_owner }})"),
    })
    inputs.update({f"t_{f}": "{{1." + f + "}}" for f in fields})
    s.flow.append(s.code(rn, code, inputs))
    o = lambda f: res(rn, f)  # noqa: E731

    def on_fail(step: str) -> list[dict]:
        return [s.exception(f"{step}: exception queue", o("failed_body")), s.ignore()]

    def route(tag: str, name: str, method: str, url: str, body: str) -> list[dict]:
        close = f"Step 7: Close the item ({tag})"
        return [s.http(name, method, url, body=o(body), parse=False, onerror=on_fail(name)),
                s.http(close, "PATCH", cfg("queue_url") + "/items/{{encodeURL(1.item_id)}}", body=o("close_body"), parse=False,
                       onerror=on_fail(close)),
                s.decision_log(f"Step 7: Decision log ({tag})", o("log_body"))]

    s.flow.append(s.router("Next", [
        (s.when("rematch", o("route"), "rematch"), route("rematch", "Step 7: Rematch", "POST", cfg("rematch_url"), "rematch_body")),
        (s.when("approve", o("route"), "approve"),
         route("approve", "Step 7: Send to the payment approver", "PUT", cfg("approvals_url") + "/approvals/" + inv_q, "approval_body")),
        (s.when("reject", o("route"), "reject"),
         route("reject", "Step 7: Reject the invoice", "PATCH", cfg("review_url") + "/records/" + inv_q, "reject_body")),
    ]))
    return s


def morning_list() -> Scenario:
    s = Scenario(R, "R7.4 Run the exception queue: morning list", "schedule", test_key=M,
                 schedule="every working day, Monday to Friday, at 08:00")
    cfg, res, data, config = start(s, None)
    read = s.http("Step 8: Read the open items", "GET", cfg("queue_url") + "/items", query={"_wrap": "1", "status": "open"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    an = "Step 8: Rule: past the aging limit"
    code, inputs = n8n_rule(N8N.AGE_JS, {"Config": config, "Step 8: Read the open items": data("Step 8: Read the open items")}, bodies={
        "post_body": f"JSON.stringify({{ to: {CFG}.escalation_owner, subject: 'Overdue exception items, oldest first', items: out.items, text: out.text }})",
    })
    s.flow.append(s.code(an, code, inputs))
    post = s.http("Step 8: Post overdue items to the escalation owner", "POST", cfg("teams_url") + "/messages",
                  body=res(an, "post_body"), parse=False)
    post["filter"] = s.when("any overdue", res(an, "any"), "true")
    s.flow.append(post)
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R7.4/make/, scenario)."""
    return [("blueprint.json", item_added()), ("closed.blueprint.json", item_closed()), ("morning.blueprint.json", morning_list())]
