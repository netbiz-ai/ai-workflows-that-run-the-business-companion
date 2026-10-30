"""R7.1 Extract supplier invoice fields into a structured record, as a Make scenario.

Source: book Chapter 7, recipe R7.1, build steps 1 to 6 (recipes/R7.1/build-spec.md);
AI step: recipes/R7.1/prompts/extract-invoice.md. The rules are the n8n build's own JavaScript
(tools/builds/r7_1.py), run through n8n_rule. Nothing the AI extracts is saved as "ready"
until every rule passes; anything else is saved "flagged" and added to R7.4's queue.
Differences from the n8n build, all forced by Make:
- The mailbox read and the AI call are tried three times, as in n8n (the book's failure table:
  "fails three retries"). Make allows one error handler per step and its Retry handler has no
  fallback route, so each try's error route holds the next try and a Resume handler that hands
  that try's response back (mk's with_tries()): one step's output is the first answer that came back, and after the
  third failed read the route adds the "mailbox error" row for Aisha and ends the run.
- n8n's "Step 3: AI error" node runs inside "Step 4: Rule: checks" (on_ai_error), because Make
  branches never meet again; so the supplier list is also read when the AI call failed, a read
  whose result that path ignores.
- n8n's "Step 6: Record to save" node only merges the paths into one save; Make branches never
  meet again, so each path (not a PDF or image, no duplicate key, a new key, a credit note)
  repeats the closing steps: save the record, add a flagged one to the R7.4 queue, mark the key
  done, decision log, with the path in the step's name. The rules' bodies give every path the
  same record shape, as "Record to save" does.
- The R7.4 queue item names the saved record's ID, which only the save returns: the rule builds
  the body with an __INVOICE_ID__ marker and the queue step maps replace(...) of that marker
  with the save's ID. The ID is the review list's own record ID, so no text is spliced.
- The key log's failure result is "write failed" without the platform's error message, which a
  Code-built body cannot see.
- The rules read the webhook body as n8n's $('Step 1: New attachment').first().json.body; a Make
  webhook step's output cannot be mapped whole, so its fields are passed one by one and the
  prelude rebuilds that body before the rule runs.
- n8n's $now.toISODate() in the queue item is the UTC date here (Make Code runs in UTC).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R7.1"
N8N = n8n_build(R)
T = N8N.T
READ = "Step 1: Read the attachment"
FILE = "Step 2: Rule: PDF or image?"
BUILD = "Step 3: Build the AI request"
ATTACH = "Step 3: Attach the document"
CALL = "Step 3: AI call"
SUPPLIERS = "Step 4: Read supplier list"
CHECKS = "Step 4: Rule: checks"
SETTLES = "Step 6: Read the item it settles"
SETTLE = "Step 6: Rule: join the item it settles"
CONFIG = {
    "mailbox_url": "https://<your AP mailbox API>",
    "review_url": "https://<your review list API>",
    "suppliers_url": "https://<your supplier list API>",
    "queue_url": "https://<your R7.4 queue list API>",
    "file_types": ["application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"],
    "required_fields": ["supplier", "invoice_number", "invoice_date", "type", "lines", "total"],
    "max_age_days": 60,
    "sum_tolerance": 0.01,
    "ap_reviewer": "<your AP reviewer>",
    "workflow_owner": "<your workflow owner>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
FIELDS = ("message_id", "attachment_id")
EV = f"$('{T}').first().json.body"
CFG = "$('Config').first().json"
INVOICE_ID = "__INVOICE_ID__"
# What each path's rule hands its closing steps: the n8n build's "Record to save" shape
# { record, key, decision, rules }, written out as the request bodies Make maps whole.
CLOSE_BODIES = {
    "flagged": "out.record.status === 'flagged' ? 'yes' : 'no'",
    "key_q": "encodeURIComponent(out.key || '')",
    "save_body": "JSON.stringify(out.record)",
    "queue_body": (f"JSON.stringify({{ invoice_id: '{INVOICE_ID}', supplier: out.record.supplier, supplier_id: out.record.supplier_id, "
                   "reason_code: out.record.reason_code, details: out.record.reasons.join('; '), "
                   "raised_by: 'R7.1', raised_at: new Date().toISOString().slice(0, 10), status: 'open' })"),
    "done_body": "JSON.stringify({ status: 'done', result: out.record.status })",
    "log_body": f"JSON.stringify({{ recipe: '{R}', item: {EV}.attachment_id, decision: out.decision, rules: out.rules }})",
    "failed_key_body": "JSON.stringify({ status: 'failed', result: 'write failed' })",
    "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.attachment_id, reason: 'write failed', "
                    f"detail: 'Record save or queue write failed, never retried; save it by hand or close the key', owner: {CFG}.workflow_owner }})"),
}


def rule(js: str, sources: dict[str, str], **kw) -> tuple[str, dict[str, str]]:
    """n8n_rule, plus the webhook's fields rebuilt as n8n's $('Step 1: New attachment').first().json.body."""
    body = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in FIELDS)
    prelude = (f"// The webhook's fields, as the rule reads them in n8n: $('{T}').first().json.body.\n"
               f"DATA[{json.dumps(T)}] = [{{ json: {{ body: {{ {body} }} }} }}];")
    code, inputs = n8n_rule(js, sources, prelude=prelude, **kw)
    return code, {**{f"t_{f}": "{{1." + f + "}}" for f in FIELDS}, **inputs}






def both(label: str, *conds: tuple[str, str, str]) -> dict:
    """A route filter that needs every condition: (a, b, operator)."""
    return {"name": label, "conditions": [[{"a": a, "b": b, "o": o} for a, b, o in conds]]}


def build() -> list[tuple[str, Scenario]]:
    s = Scenario(R, "R7.1 Extract supplier invoice fields into a structured record", "webhook", test_key="r7-1-attachment")
    s.flow.append(s.webhook(T))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    res = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()

    # Step 1: read the attachment, three tries; then the AP reviewer keys it by hand.
    read = s.http(READ, "GET", cfg("mailbox_url") + "/attachments/{{encodeURL(1.attachment_id)}}", onerror=[])
    read["filter"] = s.continue_unless_stopped()
    s.with_tries(read, 3, onerror=[
        s.exception("Exception queue: mailbox error",
                    '{"recipe": "' + R + '", "item": "{{1.attachment_id}}", "reason": "mailbox error", '
                    '"detail": "Attachment could not be read after three tries; key it by hand", "owner": "' + cfg("ap_reviewer") + '"}'),
        s.ignore()])
    s.flow.append(read)
    sources = {"Config": "{{" + f"{c}.result" + "}}", READ: "{{" + f"{read['id']}.data" + "}}"}

    def close(tag: str, step: str) -> list[dict]:
        """Step 6 for one path: save the record "ready" or "flagged"; a flagged one joins R7.4's queue."""
        out = lambda f: res(step, f)  # noqa: E731
        failed = lambda name: [s.finish_key(f"{name}: mark key failed", out("key_q"), out("failed_key_body")),  # noqa: E731
                               s.exception(f"{name}: exception queue", out("failed_body")), s.ignore()]
        save_name = f"Step 6: Save the record ({tag})"
        save = s.http(save_name, "POST", cfg("review_url") + "/records", body=out("save_body"), onerror=failed(save_name))
        queue_name = f"Step 6: Add to the R7.4 queue ({tag})"
        queue = s.http(queue_name, "POST", cfg("queue_url") + "/items",
                       body="{{replace(" + f"{s.ref(step)}.result.queue_body; \"{INVOICE_ID}\"; {save['id']}.data.id" + ")}}",
                       parse=False, onerror=failed(queue_name))
        return [save, s.router(f"Flagged? ({tag})", [
            (s.when("flagged", out("flagged"), "yes"), [
                queue,
                s.finish_key(f"Mark key done ({tag}, flagged)", out("key_q"), out("done_body")),
                s.decision_log(f"Decision log ({tag}, flagged)", out("log_body"))]),
            (s.when("ready", out("flagged"), "yes", "text:notequal"), [
                s.finish_key(f"Mark key done ({tag}, ready)", out("key_q"), out("done_body")),
                s.decision_log(f"Decision log ({tag}, ready)", out("log_body"))]),
        ])]

    # Step 2: only a PDF or an image goes to the AI step.
    code, inputs = n8n_rule(N8N.FILE_JS, sources)
    s.flow.append(s.code(FILE, code, inputs))
    file_ok = res(FILE, "pdf_or_image")
    code, inputs = rule(N8N.NOT_FILE_JS, {**sources, FILE: "{{" + f"{s.ref(FILE)}.result" + "}}"}, bodies=CLOSE_BODIES)
    not_file = [s.code("Step 2: Needs a person", code, inputs)]
    not_file += close("not a PDF or image", "Step 2: Needs a person")

    # Step 3: the AI reads the document itself, beside the prompt's text; three tries.
    ai = s.ai_step("Step 3", ROOT / "recipes/R7.1/prompts/extract-invoice.md",
                   f"{{ document: $('{READ}').first().json.filename }}", sources, max_tokens=4096, tries=1)
    build_, call = ai
    code, inputs = n8n_rule(N8N.ATTACH_JS, {READ: sources[READ], BUILD: "{{" + f"{build_['id']}.result" + "}}"},
                            bodies={"request_body": "JSON.stringify(out.request)"})
    attach = s.code(ATTACH, code, inputs)
    call["mapper"]["jsonStringBodyContent"] = "{{" + f"{attach['id']}.result.request_body" + "}}"
    s.with_tries(call, 3)
    suppliers = s.http(SUPPLIERS, "GET", cfg("suppliers_url") + "/suppliers", query={"_wrap": "1"})

    # Step 4: the rules decide, not the AI; an AI error after three tries is flagged for a person.
    code, inputs = rule(N8N.RULES_JS, {**sources, CALL: "{{" + f"{call['id']}.data" + "}}", SUPPLIERS: "{{" + f"{suppliers['id']}.data" + "}}"},
                        ai_status="{{" + f"{call['id']}.statusCode" + "}}", on_ai_error=N8N.AI_ERROR_JS, bodies={
        **CLOSE_BODIES,
        "has_key": "out.key ? 'yes' : 'no'",
        "credit_note": "out.record.type === 'credit note' ? 'yes' : 'no'",
        "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: out.key }})",
        "dup_log_body": f"JSON.stringify({{ recipe: '{R}', item: {EV}.attachment_id, decision: 'duplicate: stopped', rules: {{ key: out.key, duplicate: true }} }})",
    })
    checks = s.code(CHECKS, code, inputs)
    chk = lambda f: res(CHECKS, f)  # noqa: E731

    # Step 6: a credit note joins the item it settles: the supplier's invoice on the same order.
    settles = s.http(SETTLES, "GET", cfg("review_url") + "/records",
                     query={"_wrap": "1", "supplier_id": chk("record.supplier_id"), "order_number": chk("record.order_number")})
    code, inputs = rule(N8N.SETTLE_JS, {"Config": sources["Config"], CHECKS: "{{" + f"{checks['id']}.result" + "}}", SETTLES: "{{" + f"{settles['id']}.data" + "}}"},
                        bodies=CLOSE_BODIES)
    settle = s.code(SETTLE, code, inputs)

    # Step 5: the duplicate key, supplier ID plus invoice number; a copy is logged and stops.
    reserve = s.rpc("Step 5: Reserve key", "reserve_key", chk("reserve_body"))
    new = "{{" + f"{reserve['id']}.data" + "}}"
    keyed = [reserve, s.router("New key?", [
        (s.when("a copy", new, "true", "text:notequal"), [s.decision_log("Step 5: Log duplicate", chk("dup_log_body"))]),
        (both("new key, not a credit note", (new, "true", "text:equal"), (chk("credit_note"), "yes", "text:notequal")),
         close("new key", CHECKS)),
        (both("new key, a credit note", (new, "true", "text:equal"), (chk("credit_note"), "yes", "text:equal")),
         [settles, settle] + close("credit note", SETTLE)),
    ])]
    to_ai = [build_, attach, call, suppliers, checks, s.router("Duplicate key known?", [
        (s.when("no key: flagged anyway", chk("has_key"), "yes", "text:notequal"), close("no key", CHECKS)),
        (s.when("key known", chk("has_key"), "yes"), keyed),
    ])]
    s.flow.append(s.router("PDF or image?", [
        (s.when("not a PDF or image", file_ok, "true", "text:notequal"), not_file),
        (s.when("PDF or image", file_ok, "true"), to_ai),
    ]))
    return [("blueprint.json", s)]
