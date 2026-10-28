"""R4.4 Summarize a long thread for a handoff or escalation, as a Make scenario.

Source: book Chapter 4, recipe R4.4, build steps 1 to 6 (recipes/R4.4/build-spec.md);
AI step: recipes/R4.4/prompts/summarize-thread.md. The rules are the n8n build's own JavaScript
(tools/builds/r4_4.py), run through n8n_rule.
Differences from the n8n build, all forced by Make:
- n8n's "Step 5: AI error" node runs inside "Step 5: Rule: fields, links, nothing restricted?"
  (on_ai_error), because Make branches never meet again.
- Each branch of "Passed?" repeats the closing steps (mark the key done, decision log).
- The bodies that name the ticket read the webhook's fields, which a Make mapping cannot pass
  whole: trigger_body() passes them one by one and the prelude rebuilds n8n's
  $('Step 1: R4.2 escalation').first().json.body before the rule runs.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R4.4"
N8N = n8n_build(R)
T, POINTER = N8N.T, N8N.POINTER
MASK = "Step 3: Rule: mask restricted fields"
FETCH = "Step 3: Fetch the thread"
CHECK = "Step 5: Rule: fields, links, nothing restricted?"
# The n8n build's "Step 5: AI error" node, unchanged.
AI_ERROR_JS = ("return [{ json: { pass: false, problem: 'AI error after one retry', "
               "rules: { masked: $('Step 3: Rule: mask restricted fields').first().json.masked, ai: 'error' } } }];")
CONFIG = {
    "helpdesk_url": "https://<your helpdesk API>",
    "restricted_fields": ["<your restricted-field list, such as access_code>"],
    "detector_words": ["code", "gate", "keypad"],
    "detector_window": 20,
    "detector_allowed_labels": ["order"],
    "exception_owner": "<your workflow owner>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
FIELDS = ("escalation_id", "ticket_id")
EV = f"$('{T}').first().json.body"
KEY = f"String({EV}.escalation_id)"
CFG = "$('Config').first().json"
RESULT = "(out.pass ? 'summary posted' : 'pointer note posted')"


def trigger_body(webhook_id: int) -> tuple[str, dict[str, str]]:
    """(prelude, inputs): the webhook's fields, rebuilt as n8n's $('<trigger>').first().json.body."""
    inputs = {f"t_{f}": "{{" + f"{webhook_id}.{f}" + "}}" for f in FIELDS}
    body = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in FIELDS)
    prelude = (f"// The webhook's fields, as the rule reads them in n8n: $('{T}').first().json.body.\n"
               f"DATA[{json.dumps(T)}] = [{{ json: {{ body: {{ {body} }} }} }}];")
    return prelude, inputs


def build() -> list[tuple[str, Scenario]]:
    s = Scenario(R, "R4.4 Summarize a long thread for a handoff or escalation", "webhook", test_key="r4-4-escalation")
    s.flow.append(s.webhook(T))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    reserve = s.reserve_key("Step 2: Reserve key", "{{1.escalation_id}}")
    reserve["filter"] = s.continue_unless_stopped()
    s.flow.append(reserve)
    fetch = s.http(FETCH, "GET", cfg("helpdesk_url") + "/threads/{{encodeURL(1.ticket_id)}}")
    fetch["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: this escalation was summarized before
    s.flow.append(fetch)
    key_q = "{{encodeURL(1.escalation_id)}}"
    sources = {"Config": "{{" + f"{c}.result" + "}}", FETCH: "{{" + f"{s.ref(FETCH)}.data" + "}}"}

    # Step 3: mask restricted fields before the AI sees anything.
    code, inputs = n8n_rule(N8N.MASK_JS, sources)
    s.flow.append(s.code(MASK, code, inputs))
    sources[MASK] = "{{" + f"{s.ref(MASK)}.result" + "}}"

    # Step 4: the AI drafts the four fields; steps 5 and 6 decide what is posted.
    s.flow += s.ai_step("Step 4", ROOT / "recipes/R4.4/prompts/summarize-thread.md",
                        f"{{ thread: $('{MASK}').first().json.thread }}", sources, max_tokens=4096, tries=2)
    call = s.ref("Step 4: AI call")
    prelude, extra = trigger_body(1)
    code, inputs = n8n_rule(N8N.CHECK_JS, {**sources, "Step 4: AI call": "{{" + f"{call}.data" + "}}"}, prelude=prelude,
                            ai_status="{{" + f"{call}.statusCode" + "}}", on_ai_error=AI_ERROR_JS, bodies={
        "summary_body": f"JSON.stringify({{ ticket_id: {EV}.ticket_id, internal: true, text: out.note }})",
        "pointer_body": f"JSON.stringify({{ ticket_id: {EV}.ticket_id, internal: true, text: {POINTER!r} }})",
        "done_body": f"JSON.stringify({{ status: 'done', result: {RESULT} }})",
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.ticket_id, decision: {RESULT}, "
                     f"rules: Object.assign({{ escalation_id: {KEY} }}, out.rules, out.pass ? {{}} : {{ problem: out.problem, pointer_note: {POINTER!r} }}) }})"),
        "failed_key_body": "JSON.stringify({ status: 'failed', result: 'note write failed' })",
        "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.ticket_id, reason: 'write failed', "
                        f"detail: 'Note write failed, never retried; the receiver reads the thread', owner: {CFG}.exception_owner }})"),
    })
    s.flow.append(s.code(CHECK, code, {**extra, **inputs}))
    k = s.ref(CHECK)
    out = lambda f: "{{" + f"{k}.result.{f}" + "}}"  # noqa: E731
    notes = cfg("helpdesk_url") + "/notes"

    def failed(step: str) -> list[dict]:
        """The note write's error route: mark the key failed, add the exception row, end the run."""
        return [s.finish_key(f"{step}: mark key failed", key_q, out("failed_key_body")),
                s.exception(f"{step}: exception queue", out("failed_body")), s.ignore()]

    def post(tag: str, step: str, body: str) -> list[dict]:
        """Step 6: one internal note atop the thread, never a reply; then close the key and log."""
        return [s.http(step, "POST", notes, body=out(body), parse=False, onerror=failed(step)),
                s.finish_key(f"Mark key done ({tag})", key_q, out("done_body")),
                s.decision_log(f"Decision log ({tag})", out("log_body"))]

    s.flow.append(s.router("Passed?", [
        (s.when("summary passed", out("pass"), "true"), post("summary", "Step 6: Post the summary note", "summary_body")),
        (s.when("summary failed", out("pass"), "true", "text:notequal"), post("pointer", "Step 6: Post the pointer note", "pointer_body")),
    ]))
    return [("blueprint.json", s)]
