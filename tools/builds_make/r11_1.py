"""R11.1 Collect supplier quotes into one normalized comparison, as Make scenarios.

Source: book Chapter 11, recipe R11.1, build steps 1 to 12 (recipes/R11.1/build-spec.md);
AI step: recipes/R11.1/prompts/extract-quote.md. The rules are the n8n build's own JavaScript
(tools/builds/r11_1.py), run through n8n_rule.
Two scenarios, because a Make scenario has one trigger: a new quotes-mailbox message (webhook,
blueprint.json, steps 1 to 11) and each shift (schedule, every day at 07:00,
shift.blueprint.json, step 12). n8n's "Each shift?" node only asked which trigger ran, so it is
not built.

Differences from the n8n build, all forced by Make:
- n8n's "Step 2: Fingerprint the attachment" (Crypto node) is Make's sha256() mapping over the
  same text, so no step is spent on it; the rules that read the fingerprint get it as an input.
- The step 4 AI call tries four times, as the n8n build's does: mk.ai_step makes three tries,
  and fourth_try() adds the fourth in the third try's error route, handed on by Make's Resume
  handler like the others. n8n's "Step 11: AI error" node runs inside the step 5 rule
  (on_ai_error), because Make branches never meet again.
- Branches never meet again after a router, so steps 5 to 10 are built once for the response
  table (step 3) and once for the AI step (step 4), with the branch in each step's name, and each
  route carries its own closing steps (mark the key done, decision log).
- One rule passes its result to the next as JSON text, so empty values and lists reach the next
  rule exactly as the n8n rule returned them.
- Steps 10 and 9 write one row at a time through an iterator; an aggregator gathers the rows
  back for n8n's "All rows written?" and "Superseded marked". A failed write's error route marks
  the key failed and adds the exception-queue row, then the Skip handler ends that row; the other
  rows still run, as n8n's error output lets them, and "All rows written?" then ends the run.
- Mark key failed records "write failed" without the HTTP error text, which Make's error route
  does not hand to a later body.
"""

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R11.1"
N8N = n8n_build(R)
T, S = N8N.T, N8N.S
S1, S3, S5, S69 = N8N.S1, N8N.S3, N8N.S5, N8N.S69
FPN, CALL, WRITE, WRITTEN = "Step 2: Fingerprint the attachment", "Step 4: AI call", "Step 10: Write one row per line", "All rows written?"
CONFIG = {
    "mailbox_url": "https://<your quotes mailbox API>",
    "vendors_url": "https://<your vendor-record export API>",
    "sheet_url": "https://<your comparison sheet API>",
    "messaging_url": "https://<your messaging API>",
    "response_table_marker": {"cell": "<cell holding the response table's title>", "text": "<your response table title>"},
    "response_table_cells": {"supplier": "<cell>", "quote_number": "<cell>", "quote_date": "<cell>", "valid_until": "<cell>",
                             "currency": "<cell>", "freight": "<cell>", "subtotal": "<cell>"},
    "response_table_lines": {"first_row": "<first line row>",
                             "columns": {"description": "<column>", "quantity": "<column>", "unit": "<column>",
                                         "unit_price": "<column>", "line_total": "<column>"}},
    "delivery_terms": ["<your delivery terms that include freight>"],
    "sheet_currency": ["<your sheet currency, as quotes print it>"],
    "unit_table": [{"unit": "<unit as quoted>", "base_unit": "<base unit>", "factor": 1}],
    "margin_working_days": 5,
    "price_off_pct": 30,
    "stockroom_lead": "<your stockroom lead>",
    "editor": "<your workflow editor>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
AI_ERROR_JS = "return [{ json: { ok: false, problem: 'AI error after three retries: ' + String(($json.error && $json.error.message) || '') } }];"
CFG = "$('Config').first().json"
MSG = "$('Read the message').first().json"
FP = f"$('{FPN}').first().json.fingerprint"
AS_JSON = "JSON.stringify(out)"  # a rule's whole result, for the next rule
WRITE_FAILED = (f"JSON.stringify({{ recipe: '{R}', item: {MSG}.id, reason: 'write failed', "
                f"detail: 'Comparison sheet write failed; check the sheet before redoing it, never retried', owner: {CFG}.editor }})")


def rule(js: str, sources: dict[str, str], fp: str | None = None, prelude: str = "", **kw):
    """n8n_rule, with the attachment's fingerprint (n8n's Crypto node) given as an input."""
    if fp is None:
        return n8n_rule(js, sources, prelude=prelude, **kw)
    code, inputs = n8n_rule(js, sources, prelude=f"DATA[{FPN!r}] = [{{ json: {{ fingerprint: input.fp }} }}];\n" + prelude, **kw)
    return code, {"fp": fp, **inputs}


def fourth_try(s: Scenario, call: dict) -> None:
    """Give a three-try AI call (mk.ai_step tries=3) its fourth try, in the third try's error route."""
    third = call["onerror"][0]["onerror"][0]
    name = third["metadata"]["designer"]["name"].replace("third try", "fourth try")
    fourth = copy.deepcopy(third)
    fourth["id"] = s._id(name)
    fourth["metadata"]["designer"]["name"] = name
    third["mapper"]["stopOnHttpError"] = True
    resume = {"id": s._id(f"_resume{s._next}"), "module": "builtin:Resume", "version": 1, "parameters": {},
              "mapper": {k: "{{" + f"{fourth['id']}.{k}" + "}}" for k in ("statusCode", "data", "headers")},
              "metadata": {"designer": {}}}
    third["onerror"] = [fourth, resume]


def quotes() -> Scenario:
    s = Scenario(R, "R11.1 Collect supplier quotes into one normalized comparison", "webhook", test_key="r11-1-new-quote-message")
    s.flow.append(s.webhook(T))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    cfg_all = "{{" + f"{c}.result" + "}}"
    out = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    s.flow += s.stop_flag()

    # ---- step 1: the message and its attachment ------------------------------------------------------
    read = s.http("Read the message", "GET", cfg("mailbox_url") + "/messages/{{encodeURL(1.message_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    msg = data("Read the message")
    code, inputs = rule(N8N.READABLE_JS, {"Config": cfg_all, "Read the message": msg}, bodies={
        "as_json": AS_JSON,
        "exception_body": (f"JSON.stringify({{ recipe: '{R}', item: {MSG}.id, reason: 'no readable attachment', "
                           f"detail: out.detail, owner: {CFG}.stockroom_lead }})"),
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {MSG}.id, decision: 'exception queue: ' + out.detail, "
                     f"rules: {{ attachments: ({MSG}.attachments || []).length }} }})"),
    })
    s.flow.append(s.code(S1, code, inputs))
    s1 = out(S1, "as_json")
    fp = "{{sha256(" + f"{s.ref(S1)}.result.content" + ")}}"  # step 2: SHA-256 of the attachment, as n8n's Crypto node
    base = {"Config": cfg_all, "Read the message": msg, S1: s1}
    failed = lambda step, body: s.write_failed(step, fp, body)  # noqa: E731

    def tail(tag: str, sources: dict[str, str], **ai) -> list[dict]:
        """Steps 5 to 10 and 11 on the answer from step 3 (the response table) or step 4 (the AI)."""
        n5, n69, nw = f"{S5} ({tag})", f"{S69} ({tag})", f"{WRITTEN} ({tag})"
        code, inputs = rule(N8N.STEP5_JS, sources, fp, **ai, bodies={
            "as_json": AS_JSON,
            "quote_number": "out.ok ? out.quote.quote_number.value : ''",
            "exception_body": (f"JSON.stringify({{ recipe: '{R}', item: {MSG}.id, reason: 'needs manual entry', "
                               f"detail: out.problem + ' (' + $('{S1}').first().json.name + ')', owner: {CFG}.stockroom_lead }})"),
            "done_body": "JSON.stringify({ status: 'done', result: 'exception queue: ' + out.problem })",
            "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {MSG}.id, decision: 'manual entry: ' + out.problem, "
                         f"rules: {{ fingerprint: {FP}, step5: 'failed' }} }})"),
        })
        step5 = s.code(n5, code, inputs)

        manual = [s.exception(f"Step 11: Exception queue: manual entry ({tag})", out(n5, "exception_body")),
                  s.finish_key(f"Mark key done: manual entry ({tag})", fp, out(n5, "done_body")),
                  s.decision_log(f"Decision log: manual entry ({tag})", out(n5, "log_body"))]

        reads = [s.http(f"Read vendor records ({tag})", "GET", cfg("vendors_url") + "/records", query={"_wrap": "1"}),
                 s.http(f"Read last prices paid ({tag})", "GET", cfg("vendors_url") + "/last_prices", query={"_wrap": "1"}),
                 s.http(f"Read rows with this quote number ({tag})", "GET", cfg("sheet_url") + "/rows",
                        query={"_wrap": "1", "quote_number": out(n5, "quote_number")})]
        code, inputs = rule(N8N.STEPS_6_9_JS, {
            **base, S5: out(n5, "as_json"),
            **{n: data(f"{n} ({tag})") for n in ("Read vendor records", "Read last prices paid", "Read rows with this quote number")},
        }, fp, many=True, bodies={
            "as_json": AS_JSON,
            "row_body": "JSON.stringify(Object.fromEntries(Object.entries(out).filter(([k]) => k !== 'supersedes')))",
            "failed_body": WRITE_FAILED,
        })
        rules = s.code(n69, code, inputs)
        each = s.iterator(f"Each row ({tag})", out(n69, "items"))
        it = s.ref(f"Each row ({tag})")
        write = s.http(f"{WRITE} ({tag})", "POST", cfg("sheet_url") + "/rows", body="{{" + f"{it}.row_body" + "}}",
                       parse=False, onerror=failed(f"{WRITE} ({tag})", "{{" + f"{it}.failed_body" + "}}"))
        gathered = s.aggregator(f"Rows written ({tag})", f"Each row ({tag})", {"line": "{{" + f"{it}.line" + "}}"})
        # n8n's "All rows written?" reads every planned row; each comes back whole from its JSON text.
        code, inputs = rule(N8N.WRITTEN_JS, {
            **base, S69: out(n69, "items"), WRITE: "{{" + f"{s.ref(f'Rows written ({tag})')}.array" + "}}",
        }, fp, items=(S69, WRITE), input_node=WRITE,
            prelude=f"DATA[{S69!r}] = DATA[{S69!r}].map(i => ({{ json: JSON.parse(i.json.as_json) }}));", bodies={
            "revision": "(out.supersedes || []).length > 0",
            "older": (f"(out.supersedes || []).map(id => ({{ id_q: encodeURIComponent(id), "
                      f"patch_body: JSON.stringify({{ status: 'superseded', superseded_by: {FP} }}) }}))"),
            "done_body": "JSON.stringify({ status: 'done', result: 'rows written: ' + out.rows })",
            "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {MSG}.id, decision: 'rows written: ' + out.rows, "
                         f"rules: {{ fingerprint: {FP}, source: out.source, flags: out.flags, superseded: out.supersedes }} }})"),
            "failed_body": WRITE_FAILED,
        })
        written = s.code(nw, code, inputs)
        all_written = {"a": out(nw, "rows"), "b": "", "o": "exist"}  # fewer rows written than planned ends the run here

        def closing(t: str) -> list[dict]:
            return [s.finish_key(f"Mark key done ({tag}, {t})", fp, out(nw, "done_body")),
                    s.decision_log(f"Decision log ({tag}, {t})", out(nw, "log_body"))]

        older = s.iterator(f"Older rows ({tag})", out(nw, "older"))
        ol = s.ref(f"Older rows ({tag})")
        mark = f"Step 9: Mark the older revision superseded ({tag})"
        revision = [older,
                    s.http(mark, "PATCH", cfg("sheet_url") + "/rows/{{" + f"{ol}.id_q" + "}}", body="{{" + f"{ol}.patch_body" + "}}",
                           parse=False, onerror=failed(mark, out(nw, "failed_body"))),
                    s.aggregator(f"Superseded marked ({tag})", f"Older rows ({tag})", {"id_q": "{{" + f"{ol}.id_q" + "}}"})]
        revision += closing("revision")
        rev = out(nw, "revision")
        passed = reads + [rules, each, write, gathered, written, s.router(f"Revision? ({tag})", [
            ({"name": "a revision", "conditions": [[all_written, {"a": rev, "b": "true", "o": "text:equal"}]]}, revision),
            ({"name": "no revision", "conditions": [[all_written, {"a": rev, "b": "true", "o": "text:notequal"}]]}, closing("no revision")),
        ])]
        ok = out(n5, "ok")
        return [step5, s.router(f"Step 5 passed? ({tag})", [
            (s.when("step 5 passed", ok, "true"), passed),
            (s.when("step 5 failed", ok, "true", "text:notequal"), manual),
        ])]

    # ---- step 2: the duplicate check ---------------------------------------------------------------------
    reserve = s.reserve_key("Step 2: Reserve key", fp)
    new_key = s.is_new_key("Step 2: Reserve key")["conditions"][0][0]  # a copy stops here: this attachment was read before

    # ---- step 3: the response table, read cell by cell -----------------------------------------------
    code, inputs = rule(N8N.TABLE_JS, base, bodies={"as_json": AS_JSON})
    table = [s.code(S3, code, inputs)]
    table += tail("response table", {**base, S3: out(S3, "as_json")})

    # ---- step 4: the AI step ---------------------------------------------------------------------------
    vars_js = ("{ quote_pages: $('" + S1 + "').first().json.attachment.pages"
               ".map((p, i) => `--- page ${i + 1} ---\\n${p}`).join('\\n') }")
    ai = s.ai_step("Step 4", ROOT / "recipes/R11.1/prompts/extract-quote.md", vars_js, base, max_tokens=2048, tries=3)
    fourth_try(s, ai[1])
    call = s.ref(CALL)
    ai += tail("AI", {**base, CALL: "{{" + f"{call}.data" + "}}"},
               ai_status="{{" + f"{call}.statusCode" + "}}", on_ai_error=AI_ERROR_JS)

    # ---- step 3: which reader ----------------------------------------------------------------------------
    kind = out(S1, "kind")
    readable = [reserve, s.router("Step 3: Rule: response table?", [
        ({"name": "new key, response table", "conditions": [[new_key, {"a": kind, "b": "table", "o": "text:equal"}]]}, table),
        ({"name": "new key, not a response table", "conditions": [[new_key, {"a": kind, "b": "table", "o": "text:notequal"}]]}, ai),
    ])]
    not_read = [s.exception("Step 1: Exception queue: no readable attachment", out(S1, "exception_body")),
                s.decision_log("Decision log: not read", out(S1, "log_body"))]
    r = out(S1, "readable")
    s.flow.append(s.router("Readable?", [(s.when("readable", r, "true"), readable),
                                         (s.when("not readable", r, "true", "text:notequal"), not_read)]))
    return s


def each_shift() -> Scenario:
    """Step 12: tell the stockroom lead which AI-filled rows still wait for a check."""
    s = Scenario(R, "R11.1 Collect supplier quotes: each shift", "schedule", test_key=S, schedule="every day at 07:00")
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    read = s.http("Read unchecked AI-filled rows", "GET", cfg("sheet_url") + "/rows",
                  query={"_wrap": "1", "filled_by": "AI", "check_status": "unchecked", "status": "current"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    code, inputs = n8n_rule(N8N.SHIFT_JS, {"Config": "{{" + f"{c}.result" + "}}",
                                           "Read unchecked AI-filled rows": "{{" + f"{s.ref('Read unchecked AI-filled rows')}.data" + "}}"},
                            bodies={"message": (f"out.text ? JSON.stringify({{ to: {CFG}.stockroom_lead, "
                                                "subject: 'Quote rows to check this shift', text: out.text }) : null")})
    s.flow.append(s.code("Rule: unchecked rows?", code, inputs))
    rule_ = s.ref("Rule: unchecked rows?")
    tell = s.http("Step 12: Tell the stockroom lead", "POST", cfg("messaging_url") + "/messages",
                  body="{{" + f"{rule_}.result.message" + "}}", parse=False)
    tell["filter"] = s.when("rows to check", "{{" + f"{rule_}.result.message" + "}}", "", "exist")  # none waiting ends here
    s.flow.append(tell)
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R11.1/make/, scenario)."""
    return [("blueprint.json", quotes()), ("shift.blueprint.json", each_shift())]
