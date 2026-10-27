"""R4.1 Classify and route every incoming message to the right queue, as a Make scenario.

Source: book Chapter 4, recipe R4.1, build steps 1 to 6 (recipes/R4.1/build-spec.md);
AI step: recipes/R4.1/prompts/classify.md. The rules are the n8n build's own JavaScript
(tools/builds/r4_1.py), run through n8n_rule.
Differences from the n8n build, both forced by Make: n8n's "Step 5: AI error" node runs
inside "Step 5: Rule: use the category?" (on_ai_error), because Make branches never meet
again; and each branch repeats the closing steps (mark the key done, decision log).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R4.1"
N8N = n8n_build(R)
AI_ERROR_JS = "return [{ json: { route: 'exception', reason: 'AI error after one retry', detail: String(($json.error && $json.error.message) || '') } }];"
CONFIG = {
    "helpdesk_url": "https://<your helpdesk API>",
    "categories": [
        {"name": "<category>", "queue": "<its queue>", "owner": "<its owner>", "description": "<what belongs here>",
         "examples": ["<example 1>", "<example 2>", "<example 3>"]}
    ],
    "covered_languages": ["en"],
    "low_priority_queue": "<your low-priority queue>",
    "triage_queue": "<your manual triage queue>",
    "triage_lead": "<your triage lead>",
    "bulk_senders": ["<noreply@your-suppliers.example>"],
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
TICKET = "$('Read the message').first().json"
FAILED = (f"JSON.stringify({{ recipe: '{R}', item: {TICKET}.id, reason: 'write failed', "
          "detail: 'Routing write failed; check the ticket, never retried', owner: $('Config').first().json.triage_lead })")


def build() -> list[tuple[str, Scenario]]:
    s = Scenario(R, "R4.1 Classify and route every incoming message", "webhook", test_key="r4-1-new-message")
    s.flow.append(s.webhook("Step 1: New message"))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    read = s.http("Read the message", "GET", cfg("helpdesk_url") + "/tickets/{{encodeURL(1.ticket_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    s.flow.append(s.reserve_key("Step 2: Reserve key", "{{1.ticket_id}}:{{1.message_id}}"))
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    key_q = "{{encodeURL(1.ticket_id)}}%3A{{encodeURL(1.message_id)}}"
    url = cfg("helpdesk_url") + "/tickets/{{encodeURL(1.ticket_id)}}"
    sources = {"Config": "{{" + f"{c}.result" + "}}", "Read the message": data("Read the message")}

    code, inputs = n8n_rule(N8N.SENDER_JS, sources, bodies={
        "low_body": "JSON.stringify({ queue: $('Config').first().json.low_priority_queue })",
        "done_body": "JSON.stringify({ status: 'done', result: 'routed' })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {TICKET}.id, decision: 'low priority (automatic sender)', rules: {{ sender: 'automatic' }} }})",
        "failed_body": FAILED,
    })
    sender = s.code("Step 3: Rule: automatic sender?", code, inputs)
    sender["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: this message was routed before
    s.flow.append(sender)
    sn = s.ref("Step 3: Rule: automatic sender?")
    snd = lambda f: "{{" + f"{sn}.result.{f}" + "}}"  # noqa: E731
    failed = lambda step, body: s.write_failed(step, key_q, body)  # noqa: E731

    automatic = [
        s.http("Step 3: Set low-priority queue", "PATCH", url, body=snd("low_body"), parse=False,
               onerror=failed("Step 3: Set low-priority queue", snd("failed_body"))),
        s.finish_key("Mark key done (automatic sender)", key_q, snd("done_body")),
        s.decision_log("Step 6: Decision log (automatic sender)", snd("log_body")),
    ]

    vars_js = ("{ category_list: $('Config').first().json.categories.map(c => `${c.name}: ${c.description}; ${c.examples.join('; ')}`).join('\\n'), "
               f"subject: {TICKET}.subject, body: {TICKET}.body }}")
    ai = s.ai_step("Step 4", ROOT / "recipes/R4.1/prompts/classify.md", vars_js, sources, max_tokens=100, tries=2)
    call = s.ref("Step 4: AI call")
    code, inputs = n8n_rule(N8N.DECIDE_JS, {**sources, "Step 4: AI call": "{{" + f"{call}.data" + "}}"},
                            ai_status="{{" + f"{call}.statusCode" + "}}", on_ai_error=AI_ERROR_JS, bodies={
        "set_body": "JSON.stringify({ category: out.category, queue: out.queue })",
        "triage_body": "JSON.stringify({ queue: $('Config').first().json.triage_queue })",
        "exception_body": (f"JSON.stringify({{ recipe: '{R}', item: {TICKET}.id, reason: 'needs manual triage', "
                           "detail: out.reason + ': ' + (out.detail || ''), owner: $('Config').first().json.triage_lead })"),
        "done_body": "JSON.stringify({ status: 'done', result: 'routed' })",
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {TICKET}.id, "
                     "decision: out.route === 'set' ? 'set ' + out.category : 'manual triage: ' + out.reason, "
                     "rules: out.rules || { ai: 'error' } })"),
        "failed_body": FAILED,
    })
    decide = s.code("Step 5: Rule: use the category?", code, inputs)
    d = s.ref("Step 5: Rule: use the category?")
    dec = lambda f: "{{" + f"{d}.result.{f}" + "}}"  # noqa: E731
    set_it = s.router("Set it?", [
        (s.when("route is set", dec("route"), "set"), [
            s.http("Step 5: Set category and queue", "PATCH", url, body=dec("set_body"), parse=False,
                   onerror=failed("Step 5: Set category and queue", dec("failed_body"))),
            s.finish_key("Mark key done (category set)", key_q, dec("done_body")),
            s.decision_log("Step 6: Decision log (category set)", dec("log_body")),
        ]),
        (s.when("route is exception", dec("route"), "exception"), [
            s.http("Step 5: Move to manual triage", "PATCH", url, body=dec("triage_body"), parse=False,
                   onerror=failed("Step 5: Move to manual triage", dec("failed_body"))),
            s.exception("Exception queue: triage lead sorts it", dec("exception_body")),
            s.finish_key("Mark key done (manual triage)", key_q, dec("done_body")),
            s.decision_log("Step 6: Decision log (manual triage)", dec("log_body")),
        ]),
    ])
    s.flow.append(s.router("Automatic?", [
        (s.when("automatic sender", snd("automatic"), "true"), automatic),
        (s.when("not automatic", snd("automatic"), "true", "text:notequal"), ai + [decide, set_it]),
    ]))
    return [("blueprint.json", s)]
