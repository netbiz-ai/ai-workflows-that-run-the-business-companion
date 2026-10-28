"""R5.1 Capture inquiries from web, email and phone notes into one lead record, as Make scenarios.

Source: book Chapter 5, recipe R5.1, build steps 1 to 6 (recipes/R5.1/build-spec.md);
AI step: recipes/R5.1/prompts/extract-inquiry.md (emails and phone notes only). The rules are
the n8n build's own JavaScript (tools/builds/r5_1.py), run through n8n_rule.
Three scenarios, because a Make scenario has one trigger: the web form (blueprint.json), the
inquiry email (email.blueprint.json) and the phone note (phone-note.blueprint.json), all webhooks.

Where the Make build differs from the n8n canvas, and why:
- Make's webhook step has no "body" wrapper, so "Step 1: Channel and source ID" receives the
  body's fields one by one and gives the rule the body it reads (trigger_body()). Each scenario
  has its own trigger, so the n8n "Channel" switch is gone: the form scenario goes straight to
  step 4, the email and note scenarios read their source and run the AI step.
- n8n's "Step 4: AI error" node runs inside "Step 4: Rule: complete trade inquiry?"
  (on_ai_error), because Make branches never meet again. The run summary on that route gives
  the rule's AI-error answer to the summary as "Step 4: AI error", so the decision log says
  what n8n's does.
- Branches never meet again after a router, so each route repeats the run summary and the
  closing steps (mark the key done, decision log), with the route in the step's name.
- The created lead's ID is known only after the create, so the attach body carries a
  placeholder that the mapping replaces with that ID (LEAD_ID).
- Mark key failed records "write failed" without the HTTP error text, which Make's error route
  does not hand to a later body.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R5.1"
N8N = n8n_build(R)
FORM, EMAIL, NOTE, SRC, R4, R5 = N8N.FORM, N8N.EMAIL, N8N.NOTE, N8N.SRC, N8N.R4, N8N.R5
CONFIG = {
    "crm_url": "https://<your CRM API>",
    "mailbox_url": "https://<your inquiry mailbox API>",
    "notes_url": "https://<your phone-note form API>",
    "messaging_url": "https://<your messaging API>",
    "new_lead_status": "new, unassigned",
    "shared_inbox": "<your shared inbox>",
    "queue_checker": "<your exception queue checker>",
    "match_reviewer": "<your sales lead>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
AI_ERROR_JS = ("return [{ json: { route: 'exception', detail: 'AI error after one retry: ' + "
               "String(($json.error && $json.error.message) || ''), rules: { ai: 'error' } } }];")
LEAD_ID = "__LEAD_ID__"  # replaced in the mapping by the CRM's ID for the lead just created
# JavaScript shorthands for the bodies, as in the n8n build.
CFG = "$('Config').first().json"
S = f"$('{SRC}').first().json"
ITEM = f"{S}.channel + ':' + {S}.source_id"
F = f"$('{R4}').first().json.fields"
R5J = f"$('{R5}').first().json"


def exc(reason: str, detail: str, owner: str) -> str:
    """An exception-queue body: the item is the channel and source ID, as in the n8n build."""
    return f"JSON.stringify({{ recipe: '{R}', item: {ITEM}, reason: '{reason}', detail: {detail}, owner: {CFG}.{owner} }})"


def trigger_body(trigger: str, fields: tuple[str, ...]) -> tuple[str, dict[str, str]]:
    """(prelude, inputs): the webhook's fields, rebuilt as n8n's $('<trigger>').first().json.body."""
    inputs = {f"t_{f}": "{{1." + f + "}}" for f in fields}
    body = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in fields)
    prelude = (f"// The webhook's fields, as the rule reads them in n8n: $('{trigger}').first().json.body.\n"
               f"DATA[{json.dumps(trigger)}] = [{{ json: {{ body: {{ {body} }} }} }}];")
    return prelude, inputs


# The run summary on the exception route: an AI error reaches it as n8n's "Step 4: AI error" node.
AI_ERROR_AS_NODE = (f"if (DATA[{json.dumps(R4)}] && ((DATA[{json.dumps(R4)}][0].json || {{}}).rules || {{}}).ai === 'error') {{\n"
                    f"  DATA['Step 4: AI error'] = DATA[{json.dumps(R4)}]; delete DATA[{json.dumps(R4)}];\n}}")


def scenario(trigger: str, test_key: str, fields: tuple[str, ...], read: tuple[str, str, str] | None) -> Scenario:
    """read: (step name, Config URL field, path) for the email and the phone note; None for the form."""
    s = Scenario(R, f"R5.1 Capture inquiries into one lead record: {trigger.split(': ', 1)[1].lower()}", "webhook",
                 test_key=test_key)
    s.flow.append(s.webhook(trigger))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    cfg_all = "{{" + f"{c}.result" + "}}"
    s.flow += s.stop_flag()

    # ---- step 1: one shape for every channel; step 2: the duplicate key ---------------------
    prelude, extra = trigger_body(trigger, fields)
    code, inputs = n8n_rule(N8N.SOURCE_JS, {"Config": cfg_all}, prelude=prelude, bodies={
        "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: out.channel + ':' + out.source_id }})",
        "key_q": "encodeURIComponent(out.channel + ':' + out.source_id)",
        "source_q": "encodeURIComponent(out.source_id)",
    })
    src = s.code(SRC, code, {**extra, **inputs})
    src["filter"] = s.continue_unless_stopped()
    s.flow.append(src)
    sr = s.ref(SRC)
    src_out = lambda f: "{{" + f"{sr}.result.{f}" + "}}"  # noqa: E731
    sources = {"Config": cfg_all, SRC: "{{" + f"{sr}.result" + "}}"}
    s.flow.append(s.rpc("Step 2: Reserve key", "reserve_key", src_out("reserve_body")))
    new_key = s.is_new_key("Step 2: Reserve key")  # a copy stops here: this source was captured before
    key_q = src_out("key_q")
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731

    # ---- step 3: the AI step, for emails and phone notes only --------------------------------
    rule4_sources = dict(sources)
    ai = {}
    if read:
        name, url_field, path = read
        rd = s.http(name, "GET", cfg(url_field) + path + src_out("source_q"))
        rd["filter"] = new_key
        s.flow.append(rd)
        sources[name] = data(name)
        vars_js = ("{ channel: $('Step 1: Channel and source ID').first().json.channel, sender: $json.from || '', "
                   "subject: $json.subject || '', text: $json.body || $json.text || '' }")
        s.flow += s.ai_step("Step 3", ROOT / "recipes/R5.1/prompts/extract-inquiry.md", vars_js, sources, max_tokens=400, tries=2)
        call = s.ref("Step 3: AI call")
        rule4_sources["Step 3: AI call"] = "{{" + f"{call}.data" + "}}"
        ai = {"ai_status": "{{" + f"{call}.statusCode" + "}}", "on_ai_error": AI_ERROR_JS}

    # ---- step 4: the rules check the fields --------------------------------------------------
    code, inputs = n8n_rule(N8N.RULE4_JS, rule4_sources, input_node=SRC, **ai, bodies={
        "incomplete_body": exc("incomplete inquiry", "out.detail", "queue_checker"),
        "failed_body": exc("write failed", "'CRM write failed, not retried; check the CRM, then release or close the key'", "match_reviewer"),
    })
    rule4 = s.code(R4, code, inputs)
    if not read:
        rule4["filter"] = new_key
    s.flow.append(rule4)
    r4 = s.ref(R4)
    r4_out = lambda f: "{{" + f"{r4}.result.{f}" + "}}"  # noqa: E731
    sources[R4] = "{{" + f"{r4}.result" + "}}"
    failed = lambda step: s.write_failed(step, key_q, r4_out("failed_body"))  # noqa: E731

    def close(tag: str, extra_sources: dict[str, str] | None = None, prelude: str = "", ran=(SRC, R4, R5)) -> list[dict]:
        """The run summary (the n8n build's own), then mark the key done and log the run.
        ran: the rules this route passed, which the summary reads."""
        summary_sources = {k: sources[k] for k in ran}
        code, inputs = n8n_rule(N8N.SUMMARY_JS, {**summary_sources, **(extra_sources or {})}, input_node=SRC, prelude=prelude, bodies={
            "done_body": "JSON.stringify({ status: 'done', result: out.decision })",
            "log_body": f"JSON.stringify({{ recipe: '{R}', item: {ITEM}, decision: out.decision, rules: out.rules }})",
        })
        name = f"Run summary ({tag})"
        step = s.code(name, code, inputs)
        n = s.ref(name)
        return [step,
                s.finish_key(f"Mark key done ({tag})", key_q, "{{" + f"{n}.result.done_body" + "}}"),
                s.decision_log(f"Step 6: Decision log ({tag})", "{{" + f"{n}.result.log_body" + "}}")]

    # ---- step 5: search the CRM by email, then phone, then company ----------------------------
    crm = cfg("crm_url")
    searches = []
    for field in ("email", "phone", "company"):
        name = f"Step 5: Search CRM by {field}"
        searches.append(s.http(name, "GET", crm + "/leads", query={"_wrap": "1", field: r4_out(f"fields.{field}")}))
        sources[name] = data(name)
    source_expr = (f"({S}.channel === 'web form' ? {S}.form : {S}.channel === 'email' ? $('Read the email').first().json "
                   f": $('Read the phone note').first().json)")
    code, inputs = n8n_rule(N8N.RULE5_JS, sources, input_node=R4, bodies={
        "activity_body": f"JSON.stringify({{ lead_id: out.lead_id, source_id: {S}.source_id, channel: {S}.channel, need: {F}.need }})",
        "create_body": (f"JSON.stringify({{ name: {F}.name, company: {F}.company, email: {F}.email, phone: {F}.phone, need: {F}.need, "
                        f"source_id: {S}.source_id, channel: {S}.channel }})"),
        "attach_body": (f"JSON.stringify({{ record_id: out.action === 'create' ? '{LEAD_ID}' : out.lead_id, source_id: {S}.source_id, "
                        f"channel: {S}.channel, source: {source_expr} }})"),
        "status_body": f"JSON.stringify({{ status: {CFG}.new_lead_status }})",
        "ben_body": exc("CRM match unclear", "out.match + ': ' + (out.candidates || []).join(', ')", "match_reviewer"),
        "inbox_body": (f"JSON.stringify({{ to: {CFG}.shared_inbox, subject: 'Not an inquiry: ' + {S}.channel + ' ' + {S}.source_id, "
                       f"source_id: {S}.source_id, channel: {S}.channel }})"),
        "known_body": exc("not an inquiry from a known contact", "out.match", "queue_checker"),
    })
    rule5 = s.code(R5, code, inputs)
    r5 = s.ref(R5)
    r5_out = lambda f: "{{" + f"{r5}.result.{f}" + "}}"  # noqa: E731
    sources[R5] = "{{" + f"{r5}.result" + "}}"

    def write(name: str, method: str, url: str, body: str, parse: bool = False) -> dict:
        return s.http(name, method, url, body=body, parse=parse, onerror=failed(name))

    # ---- step 6: attach the source, set "new, unassigned", log the run ----------------------
    activity = [write("Step 5: Add stamped activity", "POST", crm + "/activities", r5_out("activity_body")),
                write("Step 6: Attach the source (activity)", "POST", crm + "/attachments", r5_out("attach_body"))]
    activity += close("activity")
    create = write("Step 5: Create stamped lead", "POST", crm + "/leads", r5_out("create_body"), parse=True)
    lead_id = f"{s.ref('Step 5: Create stamped lead')}.data.id"
    created = [create,
               write("Step 6: Attach the source (new lead)", "POST", crm + "/attachments",
                     "{{replace(" + f"{r5}.result.attach_body" + '; "' + LEAD_ID + '"; ' + lead_id + ")}}"),
               write("Step 6: Set new, unassigned", "PATCH", crm + "/leads/{{encodeURL(" + lead_id + ")}}", r5_out("status_body"))]
    created += close("new lead", {"Step 5: Create stamped lead": "{{" + f"{s.ref('Step 5: Create stamped lead')}.data" + "}}"})
    ben = [s.exception("Exception queue: Ben chooses the record", r5_out("ben_body"))] + close("Ben chooses")
    inbox = [write("Step 4: Send to the shared inbox", "POST", cfg("messaging_url") + "/messages", r5_out("inbox_body"))]
    inbox += close("shared inbox")
    known = [s.exception("Exception queue: not an inquiry, known contact", r5_out("known_body"))] + close("known contact")
    action = lambda a: s.when(f"action is {a}", r5_out("action"), a)  # noqa: E731
    match = s.router("Step 5: Match", [(action("activity"), activity), (action("create"), created), (action("ben"), ben),
                                       (action("shared inbox"), inbox), (action("known contact"), known)])

    incomplete = [s.exception("Exception queue: incomplete inquiry", r4_out("incomplete_body"))]
    incomplete += close("incomplete", prelude=AI_ERROR_AS_NODE, ran=(SRC, R4))
    s.flow.append(s.router("Step 4: Route", [
        (s.when("route is search or not inquiry", r4_out("route"), "exception", "text:notequal"), searches + [rule5, match]),
        (s.when("route is exception", r4_out("route"), "exception"), incomplete),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R5.1/make/, scenario)."""
    return [
        ("blueprint.json", scenario(FORM, "r5-1-web-form", ("submission_id", "name", "company", "email", "phone", "need"), None)),
        ("email.blueprint.json", scenario(EMAIL, "r5-1-inquiry-email", ("message_id",), ("Read the email", "mailbox_url", "/messages/"))),
        ("phone-note.blueprint.json", scenario(NOTE, "r5-1-phone-note", ("note_id",), ("Read the phone note", "notes_url", "/notes/"))),
    ]
