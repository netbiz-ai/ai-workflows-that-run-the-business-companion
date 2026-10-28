"""R5.3 Draft a quote from the current price table only, as Make scenarios.

Source: book Chapter 5, recipe R5.3, build steps 1 to 8 (recipes/R5.3/build-spec.md);
AI step: recipes/R5.3/prompts/draft-quote-text.md. The rules are the n8n build's own
JavaScript (tools/builds/r5_3.py), run through n8n_rule.
Two scenarios, because a Make scenario has one trigger: the opportunity marked "ready to
quote" (webhook) and the failure table's price list expiry warning (schedule, every day at 07:00).
The rules use plain Date in UTC, which Make's Code app has, so no shim is needed.

Where the Make build differs from the n8n canvas, and why:
- The three CRM reads try three times and then hand the run to the exception queue, as n8n's
  retries and error output do. Make's Retry handler has no fallback, so each read's error
  route holds the next try, and Make's Resume handler hands a later try's answer back.
- Step 5's AI error (n8n's "Step 5: AI error" node), steps 6 and 7, and step 8's terms or the
  no-draft summary run in one Code step, in the same order as the n8n nodes, because Make
  branches never meet again and each Code step costs credits.
- The run summary for a stopped quote is worked out in step 3's Code step, and for a quote with
  no draft in the step above; only a saved draft has its own "Run summary" step, since it needs
  the new quote's ID. Each route repeats the closing steps (mark the key done, decision log).
- "Step 3: Release the key" calls the table API's release_key function, since the table API
  has no right to delete rows.
- The off-list flag is a router's first route: Make runs it, then the AI route, for the same quote.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R5.3"
N8N = n8n_build(R)
T, M, PRICE, CHECK = N8N.T, N8N.M, N8N.PRICE, N8N.CHECK
IN_DATE = "Step 3: Rule: prices and terms in date?"
FILL = "Step 6: Fill every placeholder"
AI_ERROR = "Step 5: AI error"
TERMS = "Step 8: Add the approved terms"
SAVE = "Step 8: Save the draft for R5.4"
AI_ERROR_JS = ("return [{ json: { route: 'ai error', reason: 'AI error after one retry: ' + "
               "String(($json.error && $json.error.message) || '') } }];")
CONFIG = {
    "crm_url": "https://<your CRM API>",
    "terms_url": "https://<your approved terms library API>",
    "messaging_url": "https://<your messaging API>",
    "currency_symbol": "$",
    "expiry_warning_days": 7,
    "number_words": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
                     "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
                     "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million", "billion",
                     "dozen", "half", "once", "twice"],
    "sales_lead": "<your sales lead, who prices off-list lines>",
    "price_list_owner": "<your price list owner>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
CFG = "$('Config').first().json"
EV = N8N.EV
ITEM = f"{EV}.opportunity_id + ':' + {EV}.revision"
FIELDS = ("opportunity_id", "revision")


def brace_safe(js: str) -> str:
    """Make reads {{ in a Code step's script as a mapping; inside these rules' string literals it is
    written \\u007b{, which JavaScript reads back as the same text."""
    return re.sub(r"\{(?=\{)", r"\\u007b", js)


def part(js: str) -> str:
    """One n8n Code node's JavaScript as a function of $json, for a Code step that runs several in turn."""
    return "(($json) => {\n" + js.strip() + "\n})"


def rule(js: str, sources: dict[str, str], **kw) -> tuple[str, dict[str, str]]:
    """n8n_rule, with the webhook's fields given to the rule as n8n's $('Step 1: Ready to quote').first().json.body."""
    body = ", ".join(f"{f}: input.t_{f}" for f in FIELDS)
    prelude = f"// The webhook's fields, as the rule reads them in n8n.\nDATA[{json.dumps(T)}] = [{{ json: {{ body: {{ {body} }} }} }}];"
    code, inputs = n8n_rule(brace_safe(js), sources, prelude=prelude, **kw)
    return code, {**{f"t_{f}": "{{1." + f + "}}" for f in FIELDS}, **inputs}


def resume(s: Scenario, after: dict) -> dict:
    """Make's Resume handler: the failed step's output becomes this later try's answer."""
    return {"id": s._id(f"_resume{s._next}"), "module": "builtin:Resume", "version": 1, "parameters": {},
            "mapper": {k: "{{" + f"{after['id']}.{k}" + "}}" for k in ("statusCode", "data", "headers")},
            "metadata": {"designer": {}}}


def read3(s: Scenario, name: str, url: str, failed: list[dict]) -> dict:
    """A CRM read with n8n's three tries and error output: each try's error route holds the next,
    and the third's error route is the exception queue."""
    third = s.http(f"{name}: third try", "GET", url, onerror=failed)
    second = s.http(f"{name}: second try", "GET", url, onerror=[third, resume(s, third)])
    return s.http(name, "GET", url, onerror=[second, resume(s, second)])


def quote() -> Scenario:
    s = Scenario(R, "R5.3 Draft a quote from the current price table only", "webhook", test_key="r5-3-ready-to-quote")
    s.flow.append(s.webhook(T))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    conf = "{{" + f"{c}.result" + "}}"
    s.flow += s.stop_flag()
    reserve = s.reserve_key("Step 2: Reserve key", "{{1.opportunity_id}}:{{1.revision}}")
    reserve["filter"] = s.continue_unless_stopped()
    s.flow.append(reserve)
    key_q = "{{encodeURL(1.opportunity_id)}}%3A{{encodeURL(1.revision)}}"
    # n8n's "Mark key failed" and "Exception queue: write or read failed", for every read and write.
    exc = ('{"recipe": "' + R + '", "item": "{{1.opportunity_id}}", "reason": "write or read failed", '
           '"detail": "A CRM read failed after three tries, or a write failed and was not retried; quote by hand, then release the key", '
           '"owner": "' + cfg("sales_lead") + '"}')
    failed = lambda step: s.write_failed(step, key_q, exc)  # noqa: E731

    opp = read3(s, "Read the opportunity", cfg("crm_url") + "/opportunities/{{encodeURL(1.opportunity_id)}}", failed("Read the opportunity"))
    opp["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: this revision was drafted before
    s.flow += [opp,
               read3(s, "Read the price list", cfg("crm_url") + "/price_lists/current", failed("Read the price list")),
               read3(s, "Read the terms library", cfg("terms_url") + "/libraries/current", failed("Read the terms library"))]
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    result = lambda n: "{{" + f"{s.ref(n)}.result" + "}}"  # noqa: E731
    reads = {"Config": conf, "Read the opportunity": data("Read the opportunity"),
             "Read the price list": data("Read the price list"), "Read the terms library": data("Read the terms library")}

    # ---- Step 3: both in date, or stop with the run summary for the log ------------------
    js = (f"const __in = one({part(N8N.IN_DATE_JS)}($json))[0];\n"
          f"DATA[{json.dumps(IN_DATE)}] = [{{ json: __in }}];\n"
          "// n8n's \"Run summary\" node for a stopped quote.\n"
          f"const __sum = one({part(N8N.SUMMARY_JS)}($json))[0];\n"
          "return [{ json: Object.assign({}, __in, { summary: __sum }) }];")
    code, inputs = rule(js, reads, bodies={
        "message": (f"JSON.stringify({{ to: [{CFG}.sales_lead, {CFG}.price_list_owner], subject: 'Quote stopped: price list or terms expired', "
                    f"text: 'Opportunity ' + {EV}.opportunity_id + ' was not drafted: ' + out.expired.join('; ') }})"),
        "release_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: {N8N.KEY} }})",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {ITEM}, decision: out.summary.decision, rules: out.summary.rules }})",
    })
    s.flow.append(s.code(IN_DATE, code, inputs))
    ind = lambda f: "{{" + f"{s.ref(IN_DATE)}.result.{f}" + "}}"  # noqa: E731
    stopped = [
        s.http("Step 3: Tell Ben and Aisha", "POST", cfg("messaging_url") + "/messages", body=ind("message"), parse=False,
               onerror=failed("Step 3: Tell Ben and Aisha")),
        # Stopped before any draft, so marking ready again after a new list is published drafts it.
        s.release_key("Step 3: Release the key", ind("release_body")),
        s.decision_log("Decision log (stopped)", ind("log_body")),
    ]

    # ---- Step 4: price each line; an off-list line is flagged for Ben ---------------------
    priced = {**reads, IN_DATE: result(IN_DATE)}
    code, inputs = rule(N8N.PRICE_JS, priced, bodies={
        "off_list": "out.off_list_lines.length > 0",
        "flag_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.opportunity_id, reason: 'off-list line', "
                      f"detail: 'Unpriced off-list line(s) ' + out.off_list_lines.join(', ') + '; price before R5.4 routes it', owner: {CFG}.sales_lead }})"),
    })
    price = s.code(PRICE, code, inputs)
    pr = lambda f: "{{" + f"{s.ref(PRICE)}.result.{f}" + "}}"  # noqa: E731
    flag = s.exception("Step 4: Flag off-list line for Ben", pr("flag_body"))

    # ---- Step 5: the AI writes the text, with placeholders for every number ---------------
    opp_j, pr_j = N8N.OPP, f"$('{PRICE}').first().json"
    vars_js = (f"{{ customer_name: {opp_j}.customer_name, need: {opp_j}.need || '', "
               f"line_list: {pr_j}.lines.map(l => `${{l.line}}: ${{l.name}}`).join('\\n'), "
               f"placeholder_list: {pr_j}.placeholders.map(k => '{{{{' + k + '}}}}').join('\\n') }}")
    ai_sources = {**priced, PRICE: result(PRICE)}
    ai = s.ai_step("Step 5", ROOT / "recipes/R5.3/prompts/draft-quote-text.md", brace_safe(vars_js), ai_sources,
                   max_tokens=800, tries=2)
    call = s.ref("Step 5: AI call")

    # ---- Steps 6 to 8: fill, check, then the terms (or the no-draft summary) --------------
    js = ("const __step = (f, j) => one(f(j))[0] || {};\n"
          "const __ok = Number(input.ai_status) === 200;\n"
          f"const __fill = __ok ? __step({part(N8N.FILL_JS)}, $json)\n"
          f"  : __step({part(AI_ERROR_JS)}, {{ error: {{ message: 'AI call returned ' + (input.ai_status || 'no answer') }} }});\n"
          f"DATA[__ok ? {json.dumps(FILL)} : {json.dumps(AI_ERROR)}] = [{{ json: __fill }}];\n"
          f"const __check = __step({part(N8N.CHECK_JS)}, __fill);\n"
          f"DATA[{json.dumps(CHECK)}] = [{{ json: __check }}];\n"
          f"const __terms = __check.pass ? __step({part(N8N.TERMS_JS)}, __check) : null;\n"
          "// n8n's \"Run summary\" node for a quote with no draft.\n"
          f"const __sum = __check.pass ? null : __step({part(N8N.SUMMARY_JS)}, __check);\n"
          "return [{ json: { pass: __check.pass, reason: __check.reason, draft: __terms ? __terms.draft : null, summary: __sum } }];")
    code, inputs = rule(js, {**ai_sources, "Step 5: AI call": "{{" + f"{call}.data" + "}}"}, bodies={
        "draft_body": "JSON.stringify(out.draft)",
        "flag_body": "JSON.stringify({ quote_flag: 'No draft: ' + out.reason })",
        "exception_body": f"JSON.stringify({{ recipe: '{R}', item: {EV}.opportunity_id, reason: 'no draft', detail: out.reason, owner: {CFG}.sales_lead }})",
        "done_body": "out.summary ? JSON.stringify({ status: 'done', result: out.summary.decision }) : null",
        "log_body": f"out.summary ? JSON.stringify({{ recipe: '{R}', item: {ITEM}, decision: out.summary.decision, rules: out.summary.rules }}) : null",
    })
    inputs["ai_status"] = "{{" + f"{call}.statusCode" + "}}"
    checked = s.code("Steps 6 to 8: Fill, check, add the terms", code, inputs)
    ck_name = "Steps 6 to 8: Fill, check, add the terms"
    ck = lambda f: "{{" + f"{s.ref(ck_name)}.result.{f}" + "}}"  # noqa: E731

    save = s.http(SAVE, "POST", cfg("crm_url") + "/quotes", body=ck("draft_body"), onerror=failed(SAVE))
    code, inputs = rule(N8N.SUMMARY_JS, {PRICE: result(PRICE), CHECK: result(ck_name), SAVE: data(SAVE)}, bodies={
        "done_body": "JSON.stringify({ status: 'done', result: out.decision })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {ITEM}, decision: out.decision, rules: out.rules }})",
    })
    summary = s.code("Run summary", code, inputs)
    sm = lambda f: "{{" + f"{s.ref('Run summary')}.result.{f}" + "}}"  # noqa: E731
    saved = [save, summary,
             s.finish_key("Mark key done (draft saved)", key_q, sm("done_body")),
             s.decision_log("Decision log (draft saved)", sm("log_body"))]
    no_draft = [
        s.http("Step 8: Flag the opportunity", "PATCH", cfg("crm_url") + "/opportunities/{{encodeURL(1.opportunity_id)}}",
               body=ck("flag_body"), parse=False, onerror=failed("Step 8: Flag the opportunity")),
        s.exception("Exception queue: no draft", ck("exception_body")),
        s.finish_key("Mark key done (no draft)", key_q, ck("done_body")),
        s.decision_log("Decision log (no draft)", ck("log_body")),
    ]
    passes = s.router("Draft passes?", [
        (s.when("draft passes", ck("pass"), "true"), saved),
        (s.when("draft fails", ck("pass"), "true", "text:notequal"), no_draft),
    ])
    in_date = s.router("Off-list line?", [
        (s.when("off-list line", pr("off_list"), "true"), [flag]),
        (None, ai + [checked, passes]),
    ])
    s.flow.append(s.router("In date?", [
        (s.when("in date", ind("in_date"), "true"), [price, in_date]),
        (s.when("expired", ind("in_date"), "true", "text:notequal"), stopped),
    ]))
    return s


def expiry_warning() -> Scenario:
    s = Scenario(R, "R5.3 Draft a quote: price list expiry warning", "schedule", test_key=M, schedule="every day at 07:00")
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    s.flow += s.stop_flag()
    read = s.http("Read the price list (morning)", "GET", "{{" + f"{c}.result.crm_url" + "}}/price_lists/current")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    code, inputs = n8n_rule(N8N.EXPIRY_JS, {"Config": "{{" + f"{c}.result" + "}}",
                                            "Read the price list (morning)": "{{" + f"{read['id']}.data" + "}}"}, bodies={
        "message": (f"JSON.stringify({{ to: {CFG}.price_list_owner, subject: 'Price list ' + out.version + ' expires ' + out.valid_until, "
                    "text: 'Publish a new price list; quotes stop drafting once it expires.' })"),
    })
    rule_step = s.code("Rule: expiring within a week?", code, inputs)
    s.flow.append(rule_step)
    tell = s.http("Tell the price list owner", "POST", "{{" + f"{c}.result.messaging_url" + "}}/messages",
                  body="{{" + f"{rule_step['id']}.result.message" + "}}", parse=False)
    tell["filter"] = s.when("expiring within a week", "{{" + f"{rule_step['id']}.result.valid_until" + "}}", "", "exist")
    s.flow.append(tell)
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R5.3/make/, scenario)."""
    return [("blueprint.json", quote()), ("expiry-warning.blueprint.json", expiry_warning())]
