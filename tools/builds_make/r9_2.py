"""R9.2 Answer policy questions from approved sources and hand off to HR, as a Make scenario.

Source: book Chapter 9, recipe R9.2, build steps 1 to 7 (recipes/R9.2/build-spec.md);
AI step: recipes/R9.2/prompts/answer-policy-question.md. The rules are the n8n build's own
JavaScript (tools/builds/r9_2.py), run through n8n_rule.

Differences from the n8n build, all forced by Make:
- The rules read the question as n8n's $('Step 1: Question asked').first().json.body. A Make
  webhook's output cannot be mapped whole, so each body field is its own input and the
  adapter rebuilds the body (with_body()); the AI request step gets the same.
- The n8n AI call tries three times (mk's ai_step, tries=3): each try's error route holds the
  next try, and Make's Resume handler hands the last answer on.
- n8n's "Step 5: Why: AI error" node runs inside "Step 5: Rule: use the answer?" (on_ai_error),
  and returns ok: false so the router sends it to the handoff, because Make branches never meet.
- The three "Why" nodes (sensitive, no source, AI error) feed one "Hand off: reply and reason"
  node in n8n. Make's routes never meet again, so the handoff (the same JavaScript) and its
  closing steps are built once per route, with the route in the step's name; the two constant
  "Why" nodes become the handoff step's fixed input.
- A failed reply, handoff or log write marks the key failed and adds the "reply not sent" row
  through each write's own error route (write_failed), where n8n joins them into one node.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R9.2"
N8N = n8n_build(R)
T = N8N.T
FIELDS = ("message_id", "asker", "text")
CONFIG = {
    "policies_url": "https://<your policy folder API>",
    "messaging_url": "https://<your intake channel or messaging API>",
    "restricted_log_url": "https://<your restricted log API>",
    "gap_log_url": "https://<your gap log API>",
    "approved_status": "<the status your policy folder gives a current approved document>",
    "sensitive_phrases": ["<your list of personal phrasings, such as my pay>"],
    "fixed_reply": "<your fixed reply, naming your HR owner and who to ask if it concerns them>",
    "no_source_reply": "No source: no current approved policy answers this. Your question has gone to <your HR owner>.",
    "handoff_reply": "Your question has gone to <your HR owner>, who will answer you.",
    "closing_line": "For your own situation, ask <your HR owner>.",
    "hr_owner": "<your HR owner>",
    "min_matching_words": 2,
    "max_passages": 3,
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
Q = f"$('{T}').first().json.body"
CFG = "$('Config').first().json"
TODAY = "new Date().toISOString().slice(0, 10)"
AI_ERROR_JS = "return [{ json: { ok: false, why: 'AI error after retries' } }];"
# A reply, handoff or log write failed: never retried (n8n's "Exception queue: reply not sent").
FAILED = (f"JSON.stringify({{ recipe: '{R}', item: {Q}.message_id, reason: 'reply not sent', "
          f"detail: 'A reply, handoff or log write failed, never retried; answer the asker from the intake channel', owner: {CFG}.hr_owner }})")


def with_body(m: dict) -> dict:
    """Give a Code step n8n's $('<trigger>').first().json.body, from the webhook's fields one by one."""
    pairs = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in FIELDS)
    shim = f"// The webhook's fields, as the rule reads them in n8n.\nDATA[{json.dumps(T)}] = [{{ json: {{ body: {{ {pairs} }} }} }}];\n"
    m["mapper"]["codeEditorJavascript"] = m["mapper"]["codeEditorJavascript"].replace("const BODIES = ", shim + "const BODIES = ", 1)
    m["mapper"]["input"] += [{"name": f"t_{f}", "value": "{{1." + f + "}}"} for f in FIELDS]
    return m




def build() -> list[tuple[str, Scenario]]:
    s = Scenario(R, "R9.2 Answer policy questions from approved sources", "webhook", test_key="r9-2-question")
    s.flow.append(s.webhook(T))  # your intake channel calls this for each question: {message_id, asker, text}
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    res = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    config = "{{" + f"{c}.result" + "}}"
    s.flow += s.stop_flag()
    key_q = "{{encodeURL(1.message_id)}}"
    msg = cfg("messaging_url") + "/messages"

    # ---- Step 1: duplicate key, the message ID ------------------------------------------
    reserve = s.reserve_key("Step 1: Reserve key", "{{1.message_id}}")
    reserve["filter"] = s.continue_unless_stopped()
    s.flow.append(reserve)

    def rule(name: str, js: str, sources: dict, **kw) -> dict:
        code, inputs = n8n_rule(js, sources, **kw)
        return with_body(s.code(name, code, inputs))

    def handoff(tag: str, why_node: str, why_expr: str, rules_js: str) -> list[dict]:
        """Every handoff: the asker gets a reply naming HR, HR gets the text, the exception queue and
        the decision log get the ID only. why_node is the n8n node the handoff reads $json from."""
        name = f"Hand off: reply and reason ({tag})"
        step = rule(name, N8N.HANDOFF_JS, {"Config": config, why_node: why_expr}, bodies={
            "reply_body": f"JSON.stringify({{ to: {Q}.asker, in_reply_to: {Q}.message_id, text: out.reply }})",
            "aisha_body": (f"JSON.stringify({{ to: {CFG}.hr_owner, subject: 'Policy question handed off (' + out.why + '): ' + {Q}.message_id, "
                           f"text: 'From ' + {Q}.asker + ':\\n' + {Q}.text }})"),
            "exception_body": f"JSON.stringify({{ recipe: '{R}', item: {Q}.message_id, reason: 'handed off', detail: out.why, owner: {CFG}.hr_owner }})",
            "done_body": "JSON.stringify({ status: 'done', result: 'handed off: ' + out.why })",
            "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {Q}.message_id, decision: 'handed off: ' + out.why, "
                         f"rules: Object.assign({{ why: out.why }}, {rules_js}) }})"),
            "failed_body": FAILED,
        })
        h = lambda f: res(name, f)  # noqa: E731
        failed = lambda step_name: s.write_failed(step_name, key_q, h("failed_body"))  # noqa: E731
        reply, aisha = f"Hand off: Reply to the asker ({tag})", f"Hand off: Pass the text to Aisha ({tag})"
        return [step,
                s.http(reply, "POST", msg, body=h("reply_body"), parse=False, onerror=failed(reply)),
                s.http(aisha, "POST", msg, body=h("aisha_body"), parse=False, onerror=failed(aisha)),  # the text goes to HR only
                s.exception(f"Hand off: Exception queue ({tag})", h("exception_body")),
                s.finish_key(f"Mark key done: handed off ({tag})", key_q, h("done_body")),
                s.decision_log(f"Step 7: Decision log: handed off ({tag})", h("log_body"))]

    # ---- Step 2: a match on HR's list of personal phrasings never reaches the AI -------------
    sens = rule("Step 2: Rule: sensitive phrasing?", N8N.SENSITIVE_JS, {"Config": config})
    sens["filter"] = s.is_new_key("Step 1: Reserve key")  # a copy stops here: this message was handled before
    s.flow.append(sens)
    sensitive = res("Step 2: Rule: sensitive phrasing?", "sensitive")

    # ---- Step 3: retrieve from current approved documents only ----------------------------
    docs = "Step 3: Read current approved documents"
    read = s.http(docs, "GET", cfg("policies_url") + "/documents", query={"_wrap": "1", "status": cfg("approved_status")})
    ret = "Step 3: Rule: retrieve passages"
    retrieve = rule(ret, N8N.RETRIEVE_JS, {"Config": config, docs: data(docs)}, bodies={
        "gap_body": f"JSON.stringify({{ message_id: {Q}.message_id, date: {TODAY}, outcome: 'no source' }})",  # the ID only
        "failed_body": FAILED,
    })
    gap = s.http("Step 3: Log a gap", "POST", cfg("gap_log_url") + "/gaps", body=res(ret, "gap_body"), parse=False,
                 onerror=s.write_failed("Step 3: Log a gap", key_q, res(ret, "failed_body")))
    no_source = [gap] + handoff("no source", "Step 3: Why: no source", '{"why": "no source"}', "{}")

    # ---- Steps 4 and 5: AI answers in fixed fields; a rule decides --------------------------
    vars_js = (f"{{ passages: $('{ret}').first().json.passages"
               f".map(p => 'Document: ' + p.document + '\\n' + p.text).join('\\n\\n'), question: {Q}.text }}")
    ai = s.ai_step("Step 4", ROOT / "recipes/R9.2/prompts/answer-policy-question.md", vars_js,
                   {"Config": config, ret: "{{" + f"{s.ref(ret)}.result" + "}}"}, max_tokens=600, tries=3)
    with_body(ai[0])
    call = s.ref("Step 4: AI call")
    chk = "Step 5: Rule: use the answer?"
    ans = "out"
    check = rule(chk, N8N.CHECK_JS, {"Config": config, ret: "{{" + f"{s.ref(ret)}.result" + "}}", "Step 4: AI call": "{{" + f"{call}.data" + "}}"},
                 ai_status="{{" + f"{call}.statusCode" + "}}", on_ai_error=AI_ERROR_JS, bodies={
        "send_body": (f"JSON.stringify({{ to: {Q}.asker, in_reply_to: {Q}.message_id, "
                      f"text: '\"' + {ans}.quote + '\"\\n' + {ans}.document + ': ' + {ans}.link + '\\n' + {CFG}.closing_line }})"),
        # Answered questions only; keep 30 days (governance card, Logging).
        "restricted_body": (f"JSON.stringify({{ message_id: {Q}.message_id, date: {TODAY}, question: {Q}.text, "
                            f"document: {ans}.document, quote: {ans}.quote }})"),
        "done_body": "JSON.stringify({ status: 'done', result: 'answered' })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {Q}.message_id, decision: 'answered', rules: {ans}.rules }})",
        "failed_body": FAILED,
    })
    a = lambda f: res(chk, f)  # noqa: E731
    send, log = "Step 6: Send the quote and link", "Step 7: Restricted log"
    answered = [
        s.http(send, "POST", msg, body=a("send_body"), parse=False, onerror=s.write_failed(send, key_q, a("failed_body"))),
        s.http(log, "POST", cfg("restricted_log_url") + "/entries", body=a("restricted_body"), parse=False,
               onerror=s.write_failed(log, key_q, a("failed_body"))),
        s.finish_key("Mark key done: answered", key_q, a("done_body")),
        s.decision_log("Step 7: Decision log: answered", a("log_body")),
    ]
    answer_path = ai + [check, s.router("Answer passes?", [
        (s.when("answer passes", a("ok"), "true"), answered),
        (s.when("answer fails", a("ok"), "true", "text:notequal"),
         handoff("answer failed", chk, "{{" + f"{s.ref(chk)}.result" + "}}", f"$('{chk}').first().json.rules || {{}}")),
    ])]

    s.flow.append(s.router("Sensitive?", [
        (s.when("sensitive phrasing", sensitive, "true"),
         handoff("sensitive", "Step 2: Why: sensitive", '{"why": "sensitive phrase"}', "{}")),
        (s.when("not sensitive", sensitive, "true", "text:notequal"), [read, retrieve, s.router("Source found?", [
            (s.when("no source", res(ret, "found"), "true", "text:notequal"), no_source),
            (s.when("source found", res(ret, "found"), "true"), answer_path),
        ])]),
    ]))
    return [("blueprint.json", s)]
