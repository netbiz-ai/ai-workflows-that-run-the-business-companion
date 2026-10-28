"""R4.2 Escalate complaints, safety issues and legal threats to a person at once, as Make scenarios.

Source: book Chapter 4, recipe R4.2, build steps 1 to 6 (recipes/R4.2/build-spec.md);
AI step: recipes/R4.2/prompts/rate-risk.md. The rules are the n8n build's own JavaScript
(tools/builds/r4_2.py), run through n8n_rule.
Two scenarios, because a Make scenario has one trigger: a new message (webhook, steps 1 to 5)
and the clock (schedule, every 5 minutes, step 6). n8n's "Clock check?" node only asked which
trigger ran, so it is not built. The clock lives in the decision log, as in n8n: every notice
is a row with "clock": "running", and the check reads the latest row per ticket.

Differences from the n8n build, all forced by Make:
- "Read running clocks" is SQL in n8n (the latest notice per ticket, its age in minutes). Here
  it is a table-API read of the decision log and a small Code step, "Running clocks: latest per
  ticket", doing the same; an age below zero (Make's clock a little behind the database's)
  counts as zero. The clock check then runs once per running clock (iterator), so
  "Step 6: Rule: taken or late?" sees that clock and its ticket.
- n8n's "Step 4: AI error" node runs inside "Step 4: Rule: all three no?" (on_ai_error); the
  classifier-unavailable row is the first route of "Escalate?", which then escalates as well.
- Make branches never meet again, so step 5 (who to notify, raise the priority) is built twice,
  once after the keyword rule and once after the AI, and the notice steps three times (those two
  and the clock), each named for its route. n8n's "Notice to send" node only chose between
  them, so it is not built; the notice bodies come from the rule before.
- The priority write never retries, and its failure still sends the notices (book): it keeps
  its HTTP status (stopOnHttpError off), and a router marks the key failed with the exception
  row, or the key done, then always goes on to the notices.
- The notice steps retry three times (book, n8n note): with_tries() makes each try's error
  route the next try, and Make's Resume handler hands the last answer on; a router adds the
  "notice failed" row after a third failure and always goes on, as n8n's error output does.
- The rules read the webhook as n8n's $('Step 1: New message').first().json.body; a Make
  webhook's output cannot be mapped whole, so each field is its own input (with_body()).
"""

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R4.2"
N8N = n8n_build(R)
T, CLOCK = N8N.T, N8N.CLOCK
FIELDS = ("ticket_id", "message_id")
CONFIG = {
    "helpdesk_url": "https://<your helpdesk API>",
    "phone_url": "https://<your text and call service API>",
    "ticket_link": "https://<your helpdesk>/tickets/",
    "keywords": ["<your safety and legal keywords>"],
    "min_text_chars": 20,
    "escalation_priority": "<your highest priority>",
    "timezone": "<your time zone, such as Europe/London>",
    "opening_hours": {"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "start": "<HH:MM>", "end": "<HH:MM>"},
    "in_hours": {"owner": {"name": "<your owner in opening hours>", "phone": "<their phone>", "helpdesk_user": "<their helpdesk user>"},
                 "backup": {"name": "<your backup in opening hours>", "phone": "<their phone>", "helpdesk_user": "<their helpdesk user>"},
                 "limit_min": 15},
    "out_of_hours": {"owner": {"name": "<your on-call phone holder>", "phone": "<your on-call phone>", "helpdesk_user": "<their helpdesk user>"},
                     "backup": {"name": "<your out-of-hours backup>", "phone": "<their phone>", "helpdesk_user": "<their helpdesk user>"},
                     "limit_min": 30},
    "final_contact": {"name": "<your workflow owner>", "phone": "<their phone>", "helpdesk_user": "<their helpdesk user>"},
    "triage_lead": "<your triage lead>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
EV = f"$('{T}').first().json.body"
CFG = "$('Config').first().json"
STEP3 = "Step 3: Rule: keyword or near-empty attachment?"
STEP4 = "Step 4: Rule: all three no?"

# n8n's "Read running clocks" SQL: the latest notice per ticket whose clock is still running.
RUNNING_JS = r"""
// The latest decision-log row with a clock, per ticket (rows come newest first); keep those still running.
const latest = new Map();
for (const r of $('Read running clocks').all().map(i => i.json)) {
  if (r && r.rules && 'clock' in r.rules && !latest.has(r.item)) latest.set(r.item, r);
}
return [...latest.values()].filter(r => r.rules.clock === 'running').map(r => ({ json: { item: r.item, rules: r.rules,
  minutes: Math.max(0, (Date.now() - Date.parse(r.decided_at)) / 60000) } }));
"""


def notice_bodies(out: str) -> dict:
    """Bodies for the notice steps, from a step 5 or step 6 result (out: person, level, ...).
    A result that sends no notice (an acknowledgment, or nothing to do) gets none."""
    guard = lambda js: f"({out}.person ? {js} : null)"  # noqa: E731
    exc = lambda what: guard(f"JSON.stringify({{ recipe: '{R}', item: {out}.ticket_id, reason: 'notice failed', "  # noqa: E731
                             f"detail: '{what} to ' + {out}.person.name + ' failed after three tries', owner: {CFG}.triage_lead }})")
    return {
        # The text carries only a link, and the call no content.
        "text_body": guard(f"JSON.stringify({{ to: {out}.person.phone, text: 'Escalated ticket: ' + {CFG}.ticket_link + {out}.ticket_id }})"),
        "call_body": guard(f"JSON.stringify({{ to: {out}.person.phone, say: 'An escalated ticket needs you now. The link is in your texts.' }})"),
        "text_failed_body": exc("Text"),
        "call_failed_body": exc("Call"),
        "notice_log_body": guard(
            f"JSON.stringify({{ recipe: '{R}', item: {out}.ticket_id, decision: 'escalated: ' + {out}.level + ' notified', "
            f"rules: Object.assign({{}}, {out}.rules, {{ message_id: {out}.message_id, fired: {out}.fired, level: {out}.level, "
            f"person: {out}.person.name, rota: {out}.rota, limit_min: {out}.limit_min, notified: {out}.notified, "
            f"clock: {out}.level === 'final' ? 'ended' : 'running' }}) }})"),
    }


def with_body(m: dict) -> dict:
    """Give a Code step n8n's $('<trigger>').first().json.body, from the webhook's fields one by one."""
    pairs = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in FIELDS)
    shim = f"// The webhook's fields, as the rule reads them in n8n.\nDATA[{json.dumps(T)}] = [{{ json: {{ body: {{ {pairs} }} }} }}];\n"
    m["mapper"]["codeEditorJavascript"] = m["mapper"]["codeEditorJavascript"].replace("const BODIES = ", shim + "const BODIES = ", 1)
    m["mapper"]["input"] += [{"name": f"t_{f}", "value": "{{1." + f + "}}"} for f in FIELDS]
    return m


def with_tries(s: Scenario, m: dict, n: int) -> dict:
    """Make an HTTP step try up to n times: each failed try hands over to the next in its error
    route, and Make's Resume handler passes that try's response on as the step's own output, so
    the step after it sees the last answer (a non-2xx status if every try failed)."""
    ordinal = {2: "second", 3: "third"}
    calls = [m]
    for k in range(2, n + 1):
        name = f"{m['metadata']['designer']['name']}, {ordinal[k]} try"
        c = copy.deepcopy(calls[-1])
        c.pop("onerror", None)
        c["id"] = s._id(name)
        c["metadata"]["designer"]["name"] = name
        calls.append(c)
    for i, c in enumerate(calls):
        c["mapper"]["stopOnHttpError"] = i < len(calls) - 1
    for i in range(len(calls) - 2, -1, -1):
        nxt = calls[i + 1]
        resume = {"id": s._id(f"_resume{s._next}"), "module": "builtin:Resume", "version": 1, "parameters": {},
                  "mapper": {k: "{{" + f"{nxt['id']}.{k}" + "}}" for k in ("statusCode", "data", "headers")},
                  "metadata": {"designer": {}}}
        calls[i]["onerror"] = [nxt, resume]
    return m


def failed_status(s: Scenario, step: str) -> tuple[dict, dict]:
    """(failed, ok) filters on an HTTP step's own status."""
    st = "{{" + f"{s.ref(step)}.statusCode" + "}}"
    return s.when("failed", st, "300", "number:greaterorequal"), s.when("succeeded", st, "300", "number:less")


def notices(s: Scenario, tag: str, b, cfg) -> list[dict]:
    """Steps 5 and 6: text, then call, the person; then log the notice, which starts the clock.
    A notice that fails after three tries adds an exception row, and the run goes on."""
    phone = cfg("phone_url")
    text, call = f"Step 5 and 6: Text the person ({tag})", f"Step 5 and 6: Call the person ({tag})"
    t = with_tries(s, s.http(text, "POST", phone + "/texts", body=b("text_body"), parse=False), 3)
    c = with_tries(s, s.http(call, "POST", phone + "/calls", body=b("call_body"), parse=False), 3)
    log = s.decision_log(f"Step 5 and 6: Log the notice; start the clock ({tag})", b("notice_log_body"))
    t_fail, _ = failed_status(s, text)
    c_fail, _ = failed_status(s, call)
    return [t, s.router(f"Text sent? ({tag})", [
        (t_fail, [s.exception(f"Exception queue: text failed ({tag})", b("text_failed_body"))]),
        (None, [c, s.router(f"Call made? ({tag})", [
            (c_fail, [s.exception(f"Exception queue: call failed ({tag})", b("call_failed_body"))]),
            (None, [log]),
        ])]),
    ])]


def new_message() -> Scenario:
    s = Scenario(R, "R4.2 Escalate complaints, safety issues and legal threats", "webhook", test_key="r4-2-new-message")
    # Your helpdesk calls this for each new message, directly, so R4.1 being off never stops escalation: {ticket_id, message_id}.
    s.flow.append(s.webhook(T))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    res = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    config = "{{" + f"{c}.result" + "}}"
    s.flow += s.stop_flag()
    url = cfg("helpdesk_url") + "/tickets/{{encodeURL(1.ticket_id)}}"
    read = s.http("Read the message", "GET", url)
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    # The key is ticket plus message, so a new message on an escalated ticket is rechecked.
    s.flow.append(s.reserve_key("Step 2: Reserve key", "{{1.ticket_id}}:{{1.message_id}}"))
    key_q = "{{encodeURL(1.ticket_id)}}%3A{{encodeURL(1.message_id)}}"
    msg = {"Config": config, "Read the message": "{{" + f"{s.ref('Read the message')}.data" + "}}"}

    def rule(name: str, js: str, sources: dict, **kw) -> dict:
        code, inputs = n8n_rule(js, sources, **kw)
        return with_body(s.code(name, code, inputs))

    # ---- Step 3: a listed keyword, or an attachment with almost no text, escalates at once ----
    kw = rule(STEP3, N8N.KEYWORD_JS, msg, bodies={"at_once": "out.fired ? 'yes' : 'no'"})
    kw["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: this message was checked before
    s.flow.append(kw)
    step3 = "{{" + f"{s.ref(STEP3)}.result" + "}}"

    def escalate(tag: str, why_node: str, why_expr: str) -> list[dict]:
        """Step 5: pick the owner on duty, raise the priority, notify. why_node is the n8n node the
        owner rule reads $input from (the keyword rule's result or the AI rule's)."""
        name = f"Step 5: Rule: who to notify ({tag})"
        owner = rule(name, N8N.OWNER_JS, {**msg, why_node: why_expr}, bodies={
            "priority_body": f"JSON.stringify({{ priority: {CFG}.escalation_priority }})",
            "done_body": "JSON.stringify({ status: 'done', result: 'escalated' })",
            "failed_key_body": "JSON.stringify({ status: 'failed', result: 'priority write failed' })",
            "priority_failed_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.ticket_id, reason: 'write failed', "
                                     f"detail: 'Priority write failed, never retried; the notices still go out', owner: {CFG}.triage_lead }})"),
            **notice_bodies("out"),
        })
        b = lambda f: res(name, f)  # noqa: E731
        raise_ = f"Step 5: Raise the priority ({tag})"
        prio = s.http(raise_, "PATCH", url, body=b("priority_body"), parse=False)
        prio["mapper"]["stopOnHttpError"] = False  # a write: never retried; its status decides the route below
        fail, ok = failed_status(s, raise_)
        return [owner, prio, s.router(f"Priority written? ({tag})", [
            (fail, [s.finish_key(f"Mark key failed ({tag})", key_q, b("failed_key_body")),
                    s.exception(f"Exception queue: priority write failed ({tag})", b("priority_failed_body"))]),
            (ok, [s.finish_key(f"Mark key done ({tag})", key_q, b("done_body"))]),
            (None, notices(s, tag, b, cfg)),  # the notices go out either way
        ])]

    # ---- Step 4: the AI rates the risk; the rule decides, and any yes, other value or error escalates
    m = "$('Read the message').item.json"
    ai = s.ai_step("Step 4", ROOT / "recipes/R4.2/prompts/rate-risk.md", f"{{ subject: {m}.subject, body: {m}.body }}",
                   msg, max_tokens=100, tries=1)  # the book's n8n note retries the notice steps only, not the AI call
    call = s.ref("Step 4: AI call")
    rate = rule(STEP4, N8N.RATE_JS, {**msg, STEP3: step3, "Step 4: AI call": "{{" + f"{call}.data" + "}}"},
                ai_status="{{" + f"{call}.statusCode" + "}}", on_ai_error=N8N.AI_ERROR_JS, bodies={
        "escalate_flag": "out.escalate ? 'yes' : 'no'",
        "ai_error": "out.fired === 'AI error' ? 'yes' : 'no'",
        "unavailable_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.ticket_id, reason: 'classifier unavailable', "
                             f"detail: 'AI error; the message escalated anyway: ' + out.detail, owner: {CFG}.triage_lead }})"),
        "done_body": "JSON.stringify({ status: 'done', result: 'no escalation' })",
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.ticket_id, decision: 'no escalation', "
                     f"rules: Object.assign({{ message_id: {EV}.message_id }}, out.rules) }})"),
    })
    r4 = lambda f: res(STEP4, f)  # noqa: E731
    after_ai = ai + [rate, s.router("Escalate?", [
        # An AI error escalates; it never routes (Figure 4.2). The row comes first, then the escalation.
        (s.when("AI error", r4("ai_error"), "yes"), [s.exception("Exception queue: classifier unavailable", r4("unavailable_body"))]),
        (s.when("escalate", r4("escalate_flag"), "yes"), escalate("after the AI", "Escalate?", "{{" + f"{s.ref(STEP4)}.result" + "}}")),
        (s.when("all three no", r4("escalate_flag"), "no"),
         [s.finish_key("Mark key done: stays in its queue", key_q, r4("done_body")),
          s.decision_log("Decision log: no escalation", r4("log_body"))]),
    ])]

    s.flow.append(s.router("Escalate at once?", [
        (s.when("keyword or near-empty attachment", res(STEP3, "at_once"), "yes"), escalate("at once", "Escalate at once?", step3)),
        (s.when("neither", res(STEP3, "at_once"), "no"), after_ai),
    ]))
    return s


def clock_check() -> Scenario:
    s = Scenario(R, "R4.2 Escalate: check the clock", "schedule", test_key=CLOCK, schedule="every 5 minutes")
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    read = s.http("Read running clocks", "GET", s.table("/decision_log"),
                  query={"recipe": f"eq.{R}", "select": "id,item,rules,decided_at", "order": "id.desc"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    rn = "Running clocks: latest per ticket"
    code, inputs = n8n_rule(RUNNING_JS, {"Config": "{{" + f"{c}.result" + "}}", "Read running clocks": "{{" + f"{s.ref('Read running clocks')}.data" + "}}"},
                            items=("Read running clocks",), input_node="Config", many=True, bodies={"clock": "JSON.stringify(out)"})
    s.flow.append(s.code(rn, code, inputs))
    s.flow.append(s.iterator("Any clock running?", "{{" + f"{s.ref(rn)}.result.items" + "}}"))
    it = s.ref("Any clock running?")
    s.flow.append(s.http("Read the ticket's assignee", "GET", cfg("helpdesk_url") + "/tickets/{{encodeURL(" + f"{it}.item" + ")}}"))
    tn = "Step 6: Rule: taken or late?"
    # Only the person notified taking the ticket stops the clock; a passed limit notifies the next person.
    code, inputs = n8n_rule(N8N.CLOCK_JS, {
        "Config": "{{" + f"{c}.result" + "}}", "Any clock running?": "{{" + f"{it}.clock" + "}}",
        "Read the ticket's assignee": "{{" + f"{s.ref("Read the ticket's assignee")}.data" + "}}",
    }, bodies={
        "ack_log_body": (f"JSON.stringify({{ recipe: '{R}', item: out.ticket_id, decision: 'acknowledged by ' + out.by, "
                         "rules: { message_id: out.message_id, level: out.level, by: out.by, minutes: out.minutes, clock: 'stopped' } })"),
        **notice_bodies("out"),
    })
    s.flow.append(s.code(tn, code, inputs))
    b = lambda f: "{{" + f"{s.ref(tn)}.result.{f}" + "}}"  # noqa: E731
    s.flow.append(s.router("Taken or late", [
        (s.when("ack", b("action"), "ack"), [s.decision_log("Step 6: Log the acknowledgment; stop the clock", b("ack_log_body"))]),
        (s.when("notify", b("action"), "notify"), notices(s, "next person", b, cfg)),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R4.2/make/, scenario)."""
    return [("blueprint.json", new_message()), ("clock.blueprint.json", clock_check())]
