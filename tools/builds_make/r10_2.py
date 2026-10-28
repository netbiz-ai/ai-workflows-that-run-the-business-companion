"""R10.2 Send delivery confirmations and handle reschedule replies, as Make scenarios.

Source: book Chapter 10, recipe R10.2, build steps 1 to 12 (recipes/R10.2/build-spec.md);
AI step: recipes/R10.2/prompts/label-reply.md. Step 4 uses R10.1's step 4 masking rule. The rules
are the n8n build's own JavaScript (tools/builds/r10_2.py), run through n8n_rule.
Four scenarios, because a Make scenario has one trigger: a slot set or changed (webhook, step 1,
blueprint.json), the afternoon reminders (schedule, every day at 15:00, step 2), a customer reply
(webhook, steps 3 to 10) and the hourly no-pick check (schedule, every hour, step 12). n8n's
"Start" switch, which only asked which trigger ran, is dropped. Only a dispatcher changes the
schedule; nothing here writes to it.
Differences from the n8n build, all forced by Make:
- The rules read the trigger's body as n8n's $('Config').first().json.body (n8n's Config node
  keeps the incoming fields). A Make webhook step's output cannot be mapped whole, so its fields
  are passed one by one and the prelude adds that body to Config before the rule runs.
- The two custom SQL reads of the decision log are table-API reads, with what SQL did in the
  query done in the prelude: "Read the open slot offer" reads the job's latest "slots offered" row
  and keeps it only if it is under pick_hours old (the latest row is the only one SQL could
  return); "Step 12: Read offers with no pick" reads R10.2's rows and keeps each offer older than
  pick_hours with no later row for its job.
- "Step 10: Read open slots in the zone" is tried three times, as n8n's read is, with R7.1's
  three_tries(): each try's error route holds the next try and a Resume handler; the third try
  hands on whatever came back, so a failed lookup reaches the step 10 rule as an error body, as
  n8n's continue-on-error output does. "Read the job" likewise reads its own status (a missing job
  is no valid job reference) and retries only a failed connection.
- The step 8 rule reads the AI call's reply or error body itself, as in n8n, where both of the
  call's outputs go to it; so it needs no separate AI-error code.
- The "Action" switch becomes a router after each rule, and each route repeats the closing steps
  (mark the key done, decision log), with the route in the step's name.
- A message that was not delivered becomes a dispatcher task whose reason says "send error": a
  Code-built body cannot see Make's error message, which n8n puts there. The key log's failure
  result is "write failed" for the same reason.
- The reply scenario processes replies one at a time, in the order they arrive (Make's
  sequential processing): a slot pick must be read after the offer it answers is logged, which
  n8n's single queue gives without a setting.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402
from r7_1 import three_tries  # noqa: E402

R = "R10.2"
N8N = n8n_build(R)
S1, S2, S3, S12 = N8N.S1, N8N.S2, N8N.S3, N8N.S12
MASK, RULE6, RULE8, RULE10 = N8N.MASK, N8N.RULE6, N8N.RULE8, N8N.RULE10
OFFER = "Read the open slot offer"
NOPICK = "Step 12: Read offers with no pick"
CALL = "Step 7: AI call"
CONFIG = {
    "scheduling_url": "https://<your scheduling system API>",
    "messaging_url": "https://<your messaging API>",
    "tasks_url": "https://<your dispatcher task API>",
    "helpdesk_url": "https://<your helpdesk API>",
    "dispatch_queue": "<your dispatcher queue>",
    "confirmation_template": "<your confirmation template; the workflow fills {date}, {window} and {prep}>",
    "reminder_template": "<your reminder template; the workflow fills {date} and {window}>",
    "slot_request_template": "{slots}\nReply 1, 2 or 3 within 24 hours and a dispatcher will confirm your new time; until then your booking stays as it is.",
    "preparation_notes": "<your preparation notes>",
    "urgent_words": ["leak", "smoke", "injured", "damaged"],
    "day_words": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                  "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun",
                  "today", "tomorrow", "tonight", "weekend", "morning", "afternoon", "evening", "noon", "midday",
                  "january", "february", "march", "april", "may", "june", "july", "august", "september",
                  "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept",
                  "oct", "nov", "dec"],
    "max_slots": 3,
    "pick_hours": 24,
    "masking_list": ["code", "gate", "keypad", "PIN", "key safe"],
    "address_words": ["<your floor, unit and street words, such as floor, unit, apartment, street, road>"],
    "mask_token": "<your mask token>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
REPLY = ("message_id", "job_ref", "from", "text")
CFG = "$('Config').first().json"
EV = f"{CFG}.body"
# The reply scenario's closing bodies, for one route's rule output `out`.
CLOSE = {
    "done_body": "JSON.stringify({ status: 'done', result: out.outcome })",
    "log_body": (f"JSON.stringify({{ recipe: '{R}', item: String({EV}.job_ref), decision: out.outcome, "
                 f"rules: {{ message: {EV}.message_id, intent: out.label || null, reason: out.reason || null, slots: out.slots || [] }} }})"),
    "failed_key_body": "JSON.stringify({ status: 'failed', result: 'write failed' })",
    "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: String({EV}.job_ref), reason: 'write failed', "
                    f"detail: 'Reply ' + {EV}.message_id + ': ' + out.action + ' write failed; the dispatcher phones the customer', "
                    f"owner: {CFG}.dispatch_queue }})"),
}


class InOrder(Scenario):
    """A webhook scenario that handles one run at a time, in arrival order (see the docstring)."""
    def blueprint(self) -> dict:
        bp = super().blueprint()
        bp["metadata"]["scenario"]["sequential"] = True
        return bp


def rule(js: str, sources: dict[str, str], fields: tuple[str, ...] = (), prelude: str = "", **kw) -> tuple[str, dict[str, str]]:
    """n8n_rule, with the webhook's fields added to Config as n8n's $('Config').first().json.body."""
    if fields:
        body = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in fields)
        prelude = ("// The webhook's fields, kept on Config as n8n's Config node keeps them: $('Config').first().json.body.\n"
                   f"DATA['Config'] = [{{ json: Object.assign({{}}, DATA['Config'][0].json, {{ body: {{ {body} }} }}) }}];\n" + prelude)
    code, inputs = n8n_rule(js, sources, prelude=prelude, **kw)
    return code, {**{f"t_{f}": "{{1." + f + "}}" for f in fields}, **inputs}


def start(s: Scenario, trigger: str | None):
    if trigger:
        s.flow.append(s.webhook(trigger))
    s.flow.append(s.config(CONFIG))
    s.flow += s.stop_flag()
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    return cfg, "{{" + f"{c}.result" + "}}"


def not_delivered(s: Scenario, name: str, body: str) -> list[dict]:
    """A send's error route: a dispatcher task to phone the customer (its own failure stops the run)."""
    return [s.http(name, "POST", "{{" + f"{s.ref('Config')}.result.tasks_url" + "}}/tasks", body=body, parse=False), s.ignore()]


def nd_task(kind: str) -> str:
    return (f"JSON.stringify({{ id: 'ND-' + out.job + '-{kind.lower()}', to: {CFG}.dispatch_queue, job: out.job, "
            f"type: 'message not delivered', reason: '{kind} not delivered: send error. Phone the customer.' }})")


def slot_set() -> Scenario:
    s = Scenario(R, "R10.2 Delivery confirmations and reschedule replies: slot set or changed", "webhook", test_key="r10-2-slot")
    cfg, cfg_all = start(s, S1)
    # Step 1: the confirmation, with date, window and preparation notes, on the customer's channel.
    read = s.http("Step 1: Read the job", "GET", cfg("scheduling_url") + "/work_orders/{{encodeURL(1.job_id)}}")
    read["filter"] = s.continue_unless_stopped()
    code, inputs = n8n_rule(N8N.CONFIRM_JS, {"Config": cfg_all, "Step 1: Read the job": "{{" + f"{read['id']}.data" + "}}"},
                            bodies={"message_body": "JSON.stringify(out.message)", "nd_body": nd_task("Confirmation")})
    fill = s.code("Step 1: Fill the confirmation", code, inputs)
    f = lambda k: "{{" + f"{fill['id']}.result.{k}" + "}}"  # noqa: E731
    s.flow += [read, fill, s.http("Step 1: Send the confirmation", "POST", cfg("messaging_url") + "/messages", body=f("message_body"),
                                  parse=False, onerror=not_delivered(s, "Step 1: Not delivered: dispatcher phones", f("nd_body")))]
    return s


def afternoon() -> Scenario:
    s = Scenario(R, "R10.2 Delivery confirmations and reschedule replies: afternoon reminders", "schedule", test_key=S2,
                 schedule="every day at 15:00")
    cfg, cfg_all = start(s, None)
    # Step 2: one reminder for each of tomorrow's jobs (tomorrow in UTC, as in n8n).
    read = s.http("Step 2: Read tomorrow's jobs", "GET", cfg("scheduling_url") + "/work_orders",
                  query={"_wrap": "1", "slot_date": '{{formatDate(addDays(now; 1); "YYYY-MM-DD"; "UTC")}}'})
    read["filter"] = s.continue_unless_stopped()
    code, inputs = n8n_rule(N8N.REMIND_JS, {"Config": cfg_all, "Step 2: Read tomorrow's jobs": "{{" + f"{read['id']}.data" + "}}"},
                            many=True, executed=(S2,), bodies={"message_body": "JSON.stringify(out.message)", "nd_body": nd_task("Reminder")})
    fill = s.code("Step 2: Fill a reminder per job", code, inputs)
    each = s.iterator("Step 2: Each reminder", "{{" + f"{fill['id']}.result.items" + "}}")
    it = lambda k: "{{" + f"{each['id']}.{k}" + "}}"  # noqa: E731
    s.flow += [read, fill, each, s.http("Step 2: Send the reminder", "POST", cfg("messaging_url") + "/messages", body=it("message_body"),
                                        parse=False, onerror=not_delivered(s, "Step 2: Not delivered: dispatcher phones", it("nd_body")))]
    return s


def customer_reply() -> Scenario:
    s = InOrder(R, "R10.2 Delivery confirmations and reschedule replies: customer reply", "webhook", test_key="r10-2-reply")
    cfg, cfg_all = start(s, S3)
    res = lambda n, k: "{{" + f"{s.ref(n)}.result.{k}" + "}}"  # noqa: E731
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    key_q = "{{encodeURL(1.message_id)}}"

    def write(name: str, url: str, body: str, step: str) -> dict:
        """A write: never retried; a failure marks the key failed and adds the exception row."""
        return s.http(name, "POST", url, body=res(step, body), parse=False,
                      onerror=[s.finish_key(f"{name}: mark key failed", key_q, res(step, "failed_key_body")),
                               s.exception(f"{name}: exception queue", res(step, "failed_body")), s.ignore()])

    def close(tag: str, step: str) -> list[dict]:
        return [s.finish_key(f"Mark key done ({tag})", key_q, res(step, "done_body")),
                s.decision_log(f"Decision log ({tag})", res(step, "log_body"))]

    tasks, tickets, msg = cfg("tasks_url") + "/tasks", cfg("helpdesk_url") + "/tickets", cfg("messaging_url") + "/messages"

    def task(tag: str, step: str) -> list[dict]:
        """Steps 6, 8, 9 and 10: a dispatcher task with the masked reply."""
        return [write(f"Dispatcher task ({tag})", tasks, "task_body", step)] + close(tag, step)

    # Step 3: the duplicate key, the message ID; a copy stops.
    reserve = s.reserve_key("Step 3: Reserve key", "{{1.message_id}}")
    reserve["filter"] = s.continue_unless_stopped()
    s.flow.append(reserve)
    sources = {"Config": cfg_all}
    # Step 4: mask codes before anything reads or logs the reply.
    code, inputs = rule(N8N.STEP4_JS, sources, REPLY)
    mask = s.code(MASK, code, inputs)
    mask["filter"] = s.is_new_key("Step 3: Reserve key")  # this reply was handled before
    s.flow.append(mask)
    sources[MASK] = "{{" + f"{mask['id']}.result" + "}}"

    # Step 5: an urgent word goes to a dispatcher at once and to R4.2 (a helpdesk ticket).
    code, inputs = rule(N8N.STEP5_JS, sources, REPLY, bodies={
        **CLOSE, "task_body": "JSON.stringify(out.task)", "ticket_body": "JSON.stringify(out.ticket)"})
    s.flow.append(s.code("Step 5: Rule: urgent words?", code, inputs))
    urgent = [write("Step 5: Dispatcher task at once", tasks, "task_body", "Step 5: Rule: urgent words?"),
              write("Step 5: To R4.2 (helpdesk ticket)", tickets, "ticket_body", "Step 5: Rule: urgent words?")] + close("urgent", "Step 5: Rule: urgent words?")

    # Step 6: a slot pick or a trade reply goes to a dispatcher; anything else to the AI.
    job = s.http("Read the job", "GET", cfg("scheduling_url") + "/work_orders/{{encodeURL(1.job_ref)}}", stop_on_error=False)
    offer = s.http(OFFER, "GET", s.table("/decision_log"), query={
        "recipe": f"eq.{R}", "item": "eq.{{1.job_ref}}", "decision": "eq.slots offered", "order": "id.desc", "limit": "1"})
    offer_shim = (f"// {OFFER}: the latest offer for the job, kept only if under pick_hours old (n8n's SQL), or {{}} for none.\n"
                  f"{{ const rows = DATA[{json.dumps(OFFER)}][0].json; const row = Array.isArray(rows) ? rows[0] : null;\n"
                  "  const fresh = row && Date.now() - new Date(row.decided_at).getTime() < Number(DATA['Config'][0].json.pick_hours) * 3600000;\n"
                  f"  DATA[{json.dumps(OFFER)}] = [{{ json: fresh ? row : {{}} }}]; }}")
    code, inputs = rule(N8N.STEP6_JS, {**sources, "Read the job": "{{" + f"{job['id']}.data" + "}}", OFFER: "{{" + f"{offer['id']}.data" + "}}"},
                        REPLY, prelude=offer_shim, bodies={**CLOSE, "task_body": "JSON.stringify(out.task)"})
    step6 = s.code(RULE6, code, inputs)

    # Steps 7 to 9: the AI labels the reply; the rules decide what happens.
    vars_js = f"{{ masked_reply: $('{MASK}').first().json.masked, mask_token: $('Config').first().json.mask_token }}"
    ai = s.ai_step("Step 7", ROOT / "recipes/R10.2/prompts/label-reply.md", vars_js, sources, max_tokens=50, tries=2)
    code, inputs = rule(N8N.STEP8_JS, {**sources, RULE6: "{{" + f"{step6['id']}.result" + "}}", CALL: "{{" + f"{ai[1]['id']}.data" + "}}"},
                        REPLY, input_node=CALL, bodies={**CLOSE, "task_body": "JSON.stringify(out.task)", "ticket_body": "JSON.stringify(out.ticket)"})
    step8 = s.code(RULE8, code, inputs)

    # Step 10: up to three open slots in the zone; a failed lookup, or none open, is a dispatcher task.
    slots = s.http("Step 10: Read open slots in the zone", "GET", cfg("scheduling_url") + "/slots", onerror=[],
                   query={"_wrap": "1", "zone": res(RULE8, "job.zone"), "status": "open"})
    three_tries(s, slots)
    code, inputs = rule(N8N.STEP10_JS, {**sources, RULE8: "{{" + f"{step8['id']}.result" + "}}",
                                        "Step 10: Read open slots in the zone": "{{" + f"{slots['id']}.data" + "}}"},
                        REPLY, bodies={**CLOSE, "task_body": "JSON.stringify(out.task)", "message_body": "JSON.stringify(out.message)"})
    step10 = s.code(RULE10, code, inputs)
    act = lambda n, a: s.when(f"action is {a}", res(n, "action"), a)  # noqa: E731
    reschedule = [slots, step10, s.router("Offer or task? (step 10)", [
        (act(RULE10, "offer"), [write("Step 10: Send the slot request", msg, "message_body", RULE10)] + close("slots offered", RULE10)),
        (act(RULE10, "task"), task("step 10", RULE10)),
    ])]
    to_ai = ai + [step8, s.router("Action (step 8)", [
        (act(RULE8, "task"), task("step 8", RULE8)),
        (act(RULE8, "inbox"), [write("Step 9: To the service inbox (R4.1)", tickets, "ticket_body", RULE8)] + close("service inbox", RULE8)),
        (act(RULE8, "log"), close("confirmed", RULE8)),
        (act(RULE8, "reschedule"), reschedule),
    ])]
    not_urgent = [job, offer, step6, s.router("To the AI?", [
        (act(RULE6, "task"), task("step 6", RULE6)),
        (act(RULE6, "ai"), to_ai),
    ])]
    s.flow.append(s.router("Urgent?", [
        (act("Step 5: Rule: urgent words?", "urgent"), urgent),
        (s.when("not urgent", res("Step 5: Rule: urgent words?", "action"), "urgent", "text:notequal"), not_urgent),
    ]))
    return s


def every_hour() -> Scenario:
    s = Scenario(R, "R10.2 Delivery confirmations and reschedule replies: no pick in 24 hours", "schedule", test_key=S12,
                 schedule="every hour")
    cfg, cfg_all = start(s, None)
    # Step 12: slot requests with no pick in 24 hours go to a dispatcher, once each.
    read = s.http(NOPICK, "GET", s.table("/decision_log"), query={"recipe": f"eq.{R}", "select": "id,item,decision,decided_at", "order": "id.asc"})
    read["filter"] = s.continue_unless_stopped()
    shim = (f"// {NOPICK}: each offer older than pick_hours with no later row for its job (n8n's SQL).\n"
            f"{{ const rows = DATA[{json.dumps(NOPICK)}].map(i => i.json); const cutoff = Date.now() - Number(DATA['Config'][0].json.pick_hours) * 3600000;\n"
            "  DATA[" + json.dumps(NOPICK) + "] = rows.filter(o => o.decision === 'slots offered' && new Date(o.decided_at).getTime() <= cutoff\n"
            "    && !rows.some(p => p.item === o.item && p.id > o.id)).map(o => ({ json: { id: o.id, item: o.item } }));\n"
            "  // None waiting: one empty row, as n8n's Postgres node gives (alwaysOutputData); the rule drops it.\n"
            "  if (!DATA[" + json.dumps(NOPICK) + "].length) DATA[" + json.dumps(NOPICK) + "] = [{ json: {} }]; }")
    code, inputs = n8n_rule(N8N.NOPICK_JS, {"Config": cfg_all, NOPICK: "{{" + f"{read['id']}.data" + "}}"}, items=(NOPICK,), many=True,
                            executed=(S12,), prelude=shim, bodies={
        "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: 'no pick:' + out.offer }})",
        "task_body": (f"JSON.stringify({{ id: 'NP-' + out.offer, to: {CFG}.dispatch_queue, job: out.job, type: 'no pick', "
                      "reason: 'No pick in 24 hours: decide whether to phone.' })"),
    })
    rule_ = s.code("Step 12: Rule: offers still waiting", code, inputs)
    each = s.iterator("Step 12: Each offer waiting", "{{" + f"{rule_['id']}.result.items" + "}}")
    it = lambda k: "{{" + f"{each['id']}.{k}" + "}}"  # noqa: E731
    reserve = s.rpc("Step 12: Reserve key", "reserve_key", it("reserve_body"))
    phone = s.http("Step 12: Dispatcher decides whether to phone", "POST", cfg("tasks_url") + "/tasks", body=it("task_body"), parse=False)
    phone["filter"] = s.is_new_key("Step 12: Reserve key")  # tasked before: stop
    s.flow += [read, rule_, each, reserve, phone]
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R10.2/make/, scenario)."""
    return [("blueprint.json", slot_set()), ("reminders.blueprint.json", afternoon()),
            ("reply.blueprint.json", customer_reply()), ("no-pick.blueprint.json", every_hour())]
