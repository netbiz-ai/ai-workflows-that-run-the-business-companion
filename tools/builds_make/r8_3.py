"""R8.3 Take in a dispute and brief the account owner, as Make scenarios.

Source: book Chapter 8, recipe R8.3, build steps 1 to 11 and Table 8.2 (recipes/R8.3/build-spec.md);
AI step: recipes/R8.3/prompts/extract-reply.md. The rules are the n8n build's own JavaScript
(tools/builds/r8_3.py), run through n8n_rule.
Three scenarios, because a Make scenario has one trigger: a new message in the AR mailbox
(webhook, blueprint.json, steps 1 to 8), the morning mailbox check (schedule, every day at
06:00, before R8.1 runs, morning-check.blueprint.json, step 1) and the owner confirming the
invoices a briefed reply covers (webhook, confirm.blueprint.json, step 9). n8n's "Owner
confirmation?" and "Morning check?" nodes only asked which trigger ran, so they are not built.

Differences from the n8n build, all forced by Make:
- The mailbox reads try three times, as n8n's do (with_tries), and the step after each sees the
  last try's status: n8n's error output from "Read the message" (to "Exception queue: mailbox
  error") is the "Message read?" route, and n8n's "Mailbox access lost" no-op is the filter on
  "Step 1: Write the check time". "Step 9: Read the pause" tries three times the same way; a
  pause it cannot read reaches the step 9 rule as no pause, as n8n's output 0 is then empty.
- "Step 1: Log the check time" does not stop on an HTTP error, as n8n sends both its outputs on.
  The check time is Make's formatDate(now) in UTC, where n8n writes $now.toISO().
- The step 4 AI call tries four times, as the n8n build's does (tries=4). n8n's "Step 5: AI
  error", "Step 5: Rule: check the AI output" and "Step 6: Rule: legal threat or safety?" run in
  one Code step, in the same order, because each Code step costs credits; so do "Step 8: Write
  the brief" and "Outcome for the logs". The outcome of the unmatched, escalated and failed-check
  routes is n8n's "Outcome for the logs" run inside the rule before them.
- Branches never meet again after a router, so each route carries its own closing steps (mark
  the key done, decision log), and steps 8 run once after "Step 7: Add a note to the open
  dispute" and once after "Step 7: Log the reply on the pause", with the route in each name.
- "Step 7: Rule: already in dispute?" returns one item per open dispute it names; an iterator
  adds each note, and an aggregator gathers them back for step 8, which runs only when a note
  was added, as n8n's step 8 runs only on the notes that were written.
- n8n's custom SQL becomes table-API reads: R8.1's key log through PostgREST's or= filter on
  each invoice's keys (n8n's split_part on the key), sorted and joined by the step 8 rule as the
  SQL does; the brief through a decision_log read of the newest "briefed" row and its category.
- One rule passes its result to the next as JSON text, so empty values and lists reach the next
  rule exactly as the n8n rule returned them. The rules read the webhook as n8n's
  $('<trigger>').first().json.body, rebuilt from the webhook's fields (trigger_body()).
- Make starts the owner-confirms scenario as soon as its webhook arrives, even while the same
  message's intake still runs in the other scenario, so its brief may not be logged yet. Step 9
  first reads the message's key: until that intake is done or failed, it waits 30 seconds once
  (Make's Sleep step) before reading the brief. Branches never meet again, so step 9 is built
  for both routes, "after waiting" and "intake finished".
- Step 9 pauses each confirmed invoice through an iterator; the aggregator after it outputs once
  even when every write failed, so "Step 9: Narrow the whole-account pause" is filtered on at
  least one invoice paused, as n8n's runs only on a written one.
- Mark key failed records "write failed" without the HTTP error text, which Make's error route
  does not hand to a later body.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R8.3"
N8N = n8n_build(R)
T, MC, CF = N8N.T, N8N.MC, N8N.CF
READ, OUTSIDE, MATCH = "Read the message", "Step 1: Rule: outside message, not an automatic reply?", "Step 2: Rule: match the account"
ACCOUNTS, EXPORT, CALL = "Step 2: Read CRM accounts", "Step 2: Read today's export", "Step 4: AI call"
CHECK, R6 = "Step 5: Rule: check the AI output", "Step 6: Rule: legal threat or safety?"
CHECK6 = "Steps 5 and 6: Rule: check the AI output, legal threat or safety?"
DISPUTES, ALREADY, NOTE = "Step 7: Read open disputes on the account", "Step 7: Rule: already in dispute?", "Step 7: Add a note to the open dispute"
SENT, BRIEF = "Step 8: Read reminders sent (R8.1 key log)", "Step 8: Write the brief"
KEYS = "R8.1 key log rows"  # the table-API read's rows, before step 8's rule joins them as n8n's SQL does
BRIEF_READ, PAUSE_READ, NARROW = "Step 9: Read the brief", "Step 9: Read the pause", "Step 9: Rule: briefed, paused, invoices named?"
CONFIG = {
    "mail_url": "https://<your AR mailbox API>",
    "sharepoint_url": "https://<your SharePoint lists API>",
    "crm_url": "https://<your CRM API>",
    "messaging_url": "https://<your Teams or messaging API>",
    "ar_lead": "<your AR lead, who works the unlinked queue>",
    "own_domains": ["<your company's email domain>"],
    "invoice_number_pattern": "<your invoice-number pattern, as a regular expression>",
    "escalation_keywords": ["<your R4.2 safety and legal keyword list>"],
    "summary_max_words": 80,
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
AI_ERROR_JS = "return [{ json: { check_ok: false, problem: 'AI error after three retries' } }];"  # n8n's "Step 5: AI error"
CFG = "$('Config').first().json"
EV = f"$('{T}').first().json.body"
CB = f"$('{CF}').first().json.body"
AS_JSON = "JSON.stringify(out)"  # a rule's whole result, for the next rule


def part(js: str) -> str:
    """One n8n Code node's JavaScript as a function, for a Code step that runs several in turn."""
    return "(() => {\n" + js.strip() + "\n})"


def exc(item: str, reason: str, detail: str) -> str:
    """An exception-queue row, as n8n's w.exception() writes it."""
    return f"JSON.stringify({{ recipe: '{R}', item: {item}, reason: '{reason}', detail: {detail}, owner: {CFG}.ar_lead }})"


def log(decision: str, rules: str) -> str:
    return f"JSON.stringify({{ recipe: '{R}', item: {EV}.message_id, decision: {decision}, rules: {rules} }})"


WRITE_FAILED = exc(f"{EV}.message_id", "write failed", "'A dispute-list or message write failed; check the account, never retried'")
# n8n's "Outcome for the logs", run inside a rule: __outcome(node, result) gives it that rule's result first.
OUTCOME_HELPER = ("const __outcome = (node, r) => { if (node) DATA[node] = [{ json: r }]; return one(" + part(N8N.OUTCOME_JS) + "())[0]; };\n")


def closing_bodies(when: str, node: str) -> dict[str, str]:
    """The key-log and decision-log bodies from n8n's "Outcome for the logs", for the routes `when` is true on."""
    o = f"__outcome({node!r}, out)"
    return {"done_body": f"{when} ? JSON.stringify({{ status: 'done', result: {o}.decision }}) : null",
            "log_body": f"{when} ? {log(o + '.decision', o + '.rules')} : null"}


def trigger_body(trigger: str, fields: tuple[str, ...], lists: tuple[str, ...] = ()) -> tuple[str, dict[str, str]]:
    """(prelude, inputs): the webhook's fields, rebuilt as n8n's $('<trigger>').first().json.body.
    A list field may reach the step as a list, as JSON text, as text joined by commas (Make's
    text form of a list) or as an object, its elements as text or as one-field collections; the rule
    gets a list of the values."""
    inputs = {f"t_{f}": "{{1." + f + "}}" for f in fields}
    body = ", ".join(f"{json.dumps(f)}: " + (f"__list(input.t_{f})" if f in lists else f"input.t_{f}") for f in fields)
    prelude = (f"// The webhook's fields, as the rule reads them in n8n: $('{trigger}').first().json.body.\n"
               "const __list = v => {\n"
               "  if (typeof v === 'string') { let p; try { p = JSON.parse(v); } catch (e) { p = null; }\n"
               "    v = p && typeof p === 'object' ? p : v.split(',').map(x => x.trim()).filter(Boolean); }\n"
               "  if (typeof v === 'number') v = [String(v)];\n"
               "  const list = Array.isArray(v) ? v : v && typeof v === 'object' ? Object.values(v) : [];\n"
               "  return list.map(x => (x && typeof x === 'object' ? Object.values(x)[0] : x)); };\n"
               f"DATA[{json.dumps(trigger)}] = [{{ json: {{ body: {{ {body} }} }} }}];")
    return prelude, inputs


def rule(js: str, sources: dict[str, str], trigger: tuple[str, tuple[str, ...], tuple[str, ...]], prelude: str = "", **kw):
    """n8n_rule, with the scenario's webhook body, which every rule here may read."""
    tp, extra = trigger_body(*trigger)
    code, inputs = n8n_rule(js, sources, prelude=tp + "\n" + prelude, **kw)
    return code, {**extra, **inputs}


def start(s: Scenario, trigger: str | None):
    if trigger:
        s.flow.append(s.webhook(trigger))
    s.flow.append(s.config(CONFIG))
    s.flow += s.stop_flag()
    c = s.ref("Config")
    return (lambda f: "{{" + f"{c}.result.{f}" + "}}"), "{{" + f"{c}.result" + "}}"


def new_message() -> Scenario:
    """Steps 1 to 8 for each new message in the AR mailbox."""
    s = Scenario(R, "R8.3 Take in a dispute and brief the account owner", "webhook", test_key="r8-3-new-message")
    cfg, cfg_all = start(s, T)
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    out = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    trig = (T, ("message_id",), ())
    msg_q = "{{encodeURL(1.message_id)}}"
    status_url = cfg("sharepoint_url") + "/status/mailbox-check"
    status_body = '{"id": "mailbox-check", "last_check": "{{formatDate(now; "YYYY-MM-DDTHH:mm:ss.SSSZ"; "UTC")}}"}'

    # ---- steps 1 and 2: the message, three tries ---------------------------------------------------------
    read = s.with_tries(s.http(READ, "GET", cfg("mail_url") + "/messages/" + msg_q, onerror=[]), 3)
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    status = "{{" + f"{s.ref(READ)}.statusCode" + "}}"
    mailbox_error = s.exception("Exception queue: mailbox error",
                                '{"recipe": "' + R + '", "item": "{{1.message_id}}", "reason": "unlinked item", '
                                '"detail": "Mailbox error after three tries; link it from the AR mailbox", "owner": "' + cfg("ar_lead") + '"}')

    log_check = s.http("Step 1: Log the check time", "PUT", status_url, body=status_body, parse=False, stop_on_error=False)
    sources = {"Config": cfg_all, READ: data(READ)}
    code, inputs = rule(N8N.OUTSIDE_JS, sources, trig)
    outside = s.code(OUTSIDE, code, inputs)
    reserve = s.reserve_key("Step 2: Reserve key", "{{1.message_id}}")
    reserve["filter"] = s.when("outside, not automatic", out(OUTSIDE, "outside"), "true")  # anything else ends here
    accounts = s.http(ACCOUNTS, "GET", cfg("crm_url") + "/accounts", query={"_wrap": "1"})
    accounts["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: one dispute, one brief
    export = s.http(EXPORT, "GET", cfg("sharepoint_url") + "/exports/open-invoices")

    code, inputs = rule(N8N.MATCH_JS, {**sources, ACCOUNTS: data(ACCOUNTS), EXPORT: data(EXPORT)}, trig,
                        prelude=OUTCOME_HELPER, bodies={
        "as_json": AS_JSON,
        "pause_body": (f"out.matched ? JSON.stringify({{ id: 'pause-' + {EV}.message_id, account: out.account, invoice: null, status: 'open', "
                       f"kind: 'reply received', set_by: 'R8.3', why: 'reply received', message_id: {EV}.message_id, "
                       "paused_at: new Date().toISOString(), until: null }) : null"),
        "exception_body": exc(f"{EV}.message_id", "unlinked item", "'No account matched the sender, an invoice number or the domain'"),
        "failed_body": WRITE_FAILED,
        **closing_bodies("!out.matched", MATCH),
    })
    match = s.code(MATCH, code, inputs)
    m = lambda f: out(MATCH, f)  # noqa: E731
    failed = lambda step: s.write_failed(step, msg_q, m("failed_body"))  # noqa: E731

    def closing(tag: str, step: str) -> list[dict]:
        """Mark the key done and log the decision, from the outcome the rule `step` worked out."""
        return [s.finish_key(f"Mark key done ({tag})", msg_q, out(step, "done_body")),
                s.decision_log(f"Decision log ({tag})", out(step, "log_body"))]

    unmatched = [s.exception("Exception queue: unmatched", m("exception_body")), *closing("unmatched", MATCH)]

    # ---- step 3: pause before the AI reads ---------------------------------------------------------------
    pause = s.http("Step 3: Write a whole-account pause", "PUT", cfg("sharepoint_url") + "/disputes/pause-" + msg_q,
                   body=m("pause_body"), parse=False, onerror=failed("Step 3: Write a whole-account pause"))

    # ---- steps 4 to 6 ---------------------------------------------------------------------------------------
    vars_js = f"{{ subject: $('{READ}').item.json.subject, body: $('{READ}').item.json.body }}"
    ai = s.ai_step("Step 4", ROOT / "recipes/R8.3/prompts/extract-reply.md", vars_js, sources, max_tokens=600, tries=4)
    call = s.ref(CALL)
    base = {**sources, MATCH: m("as_json"), EXPORT: data(EXPORT)}
    js = ("const __ok = Number(input.ai_status) === 200;\n"
          f"const __c = one(__ok ? {part(N8N.CHECK_JS)}() : {part(AI_ERROR_JS)}())[0];\n"
          f"return (($input) => {{\n{N8N.ESCALATE_JS.strip()}\n}})({{ first: () => ({{ json: __c }}), all: () => [{{ json: __c }}] }});")
    r6 = "out"
    code, inputs = rule(js, {**base, CALL: "{{" + f"{call}.data" + "}}"}, trig, prelude=OUTCOME_HELPER, bodies={
        "as_json": AS_JSON,
        "escalate_body": (f"JSON.stringify({{ to: [{CFG}.ar_lead, $('{MATCH}').first().json.owner], "
                          f"subject: 'Escalated as R4.2: reply from ' + $('{MATCH}').first().json.account_name, "
                          f"text: 'Matched the R4.2 rules (' + {r6}.keywords.join(', ') + '). The whole account stays paused. Message: ' + "
                          f"($('{READ}').first().json.web_link || $('{READ}').first().json.id) }})"),
        "exception_body": exc(f"{EV}.message_id", "unlinked item", f"{r6}.problem"),
        "reply_body": f"JSON.stringify({{ ai_category: {r6}.category, invoices_named: {r6}.invoices }})",
        # n8n's step 8 SQL reads R8.1's keys whose part before ':' is one of these invoices.
        "sent_filter": ("'(' + ((out.brief_invoices || []).map(n => 'key.like.\"' + String(n).replace(/[\"\\\\]/g, '\\\\$&') + ':*\"')"
                        ".join(',') || 'key.is.null') + ')'"),
        **closing_bodies("out.route !== 'brief'", R6),
    })
    inputs["ai_status"] = "{{" + f"{call}.statusCode" + "}}"
    check = s.code(CHECK6, code, inputs)
    c6 = lambda f: out(CHECK6, f)  # noqa: E731

    escalate = [s.http("Step 6: Escalate to Aisha and the owner", "POST", cfg("messaging_url") + "/messages", body=c6("escalate_body"),
                       parse=False, onerror=failed("Step 6: Escalate to Aisha and the owner")),
                *closing("escalated", CHECK6)]
    queue = [s.exception("Exception queue: fails the check", c6("exception_body")), *closing("fails the check", CHECK6)]

    # ---- steps 7 and 8 ---------------------------------------------------------------------------------------
    disputes = s.http(DISPUTES, "GET", cfg("sharepoint_url") + "/disputes",
                      query={"_wrap": "1", "status": "open", "account": "{{" + f"{s.ref(MATCH)}.result.account" + "}}"})
    code, inputs = rule(N8N.ALREADY_JS, {READ: data(READ), R6: c6("as_json"), DISPUTES: data(DISPUTES)}, trig, many=True, bodies={
        "as_json": AS_JSON,
        "id_q": "encodeURIComponent(out.dispute_id || '')",
        "note_body": (f"out.already ? JSON.stringify({{ notes: out.notes.concat([{{ message_id: {EV}.message_id, "
                      f"added: new Date().toISOString(), ai_category: $('{R6}').first().json.category }}]) }}) : null"),
    })
    already = s.code(ALREADY, code, inputs)

    def step8(tag: str, noted: bool) -> list[dict]:
        """Step 8 and the closing steps: R8.1's reminders sent, the brief, the owner told."""
        sent = s.http(f"{SENT} ({tag})", "GET", s.table("/key_log"),
                      query={"recipe": "eq.R8.1", "or": c6("sent_filter"), "select": "key", "order": "key"})
        prelude = (OUTCOME_HELPER + f"DATA[{SENT!r}] = [{{ json: {{ sent: $({KEYS!r}).all().map(i => String(i.json.key)).sort().join(', ') }} }}];\n")
        js = (f"const __brief = one({part(N8N.BRIEF_JS)}())[0];\n"
              f"DATA[{BRIEF!r}] = [{{ json: __brief }}];\n"
              "const __o = __outcome(null);\n"
              "return [{ json: Object.assign({}, __brief, { decision: __o.decision, rules: __o.rules }) }];")
        srcs = {**base, R6: c6("as_json"), KEYS: data(f"{SENT} ({tag})")}
        if noted:
            srcs[ALREADY] = "{{" + f"{s.ref(ALREADY)}.result.items[1].as_json" + "}}"
        code, inputs = rule(js, srcs, trig, prelude=prelude, items=(KEYS,), input_node="Config",
                            executed=(NOTE,) if noted else (), bodies={
            "brief_body": "JSON.stringify({ to: out.to, subject: out.subject, text: out.text })",
            "done_body": "JSON.stringify({ status: 'done', result: out.decision })",
            "log_body": log("out.decision", "out.rules"),
        })
        brief = s.code(f"{BRIEF} ({tag})", code, inputs)
        send = f"Step 8: Brief the account owner ({tag})"
        return [sent, brief,
                s.http(send, "POST", cfg("messaging_url") + "/messages", body=out(f"{BRIEF} ({tag})", "brief_body"), parse=False,
                       onerror=failed(send)),
                *closing(f"briefed, {tag}", f"{BRIEF} ({tag})")]

    each = s.iterator("Each open dispute named", "{{" + f"{s.ref(ALREADY)}.result.items" + "}}")
    it = s.ref("Each open dispute named")
    note = s.http(NOTE, "PATCH", cfg("sharepoint_url") + "/disputes/{{" + f"{it}.id_q" + "}}", body="{{" + f"{it}.note_body" + "}}",
                  parse=False, onerror=failed(NOTE))
    notes = s.aggregator("Notes added", "Each open dispute named", {"id_q": "{{" + f"{it}.id_q" + "}}"})
    noted = step8("note added", True)
    noted[0]["filter"] = {"name": "a note was added", "conditions": [[{"a": "{{length(" + f"{s.ref('Notes added')}.array" + ")}}",
                                                                      "b": "0", "o": "number:greater"}]]}
    reply = "Step 7: Log the reply on the pause"
    on_pause = [s.http(reply, "PATCH", cfg("sharepoint_url") + "/disputes/pause-" + msg_q, body=c6("reply_body"), parse=False,
                       onerror=failed(reply))] + step8("reply logged", False)
    brief = [disputes, already, s.router("Already in dispute?", [
        (s.when("already in dispute", "{{" + f"{s.ref(ALREADY)}.result.items[1].already" + "}}", "true"), [each, note, notes] + noted),
        (s.when("not in dispute", "{{" + f"{s.ref(ALREADY)}.result.items[1].already" + "}}", "true", "text:notequal"), on_pause),
    ])]

    route = c6("route")
    matched = [pause] + ai + [check, s.router("Route", [
        (s.when("brief", route, "brief"), brief),
        (s.when("escalate", route, "escalate"), escalate),
        (s.when("queue", route, "queue"), queue),
    ])]
    ok = m("matched")
    intake = [log_check, outside, reserve, accounts, export, match, s.router("Matched?", [
        (s.when("matched", ok, "true"), matched),
        (s.when("not matched", ok, "true", "text:notequal"), unmatched),
    ])]
    s.flow.append(s.router("Message read?", [
        (s.when("message read", status, "200"), intake),
        (s.when("mailbox error after three tries", status, "200", "text:notequal"), [mailbox_error]),
    ]))
    return s


def morning_check() -> Scenario:
    """Step 1: a quiet morning still logs a check; a lost connection leaves the status list stale."""
    s = Scenario(R, "R8.3 Take in a dispute: morning mailbox check", "schedule", test_key=MC,
                 schedule="every day at 06:00, before R8.1 runs")
    cfg, _ = start(s, None)
    check = s.with_tries(s.http("Step 1: Check the mailbox", "GET", cfg("mail_url") + "/messages", query={"_wrap": "1"}, onerror=[]), 3)
    check["filter"] = s.continue_unless_stopped()
    s.flow.append(check)
    exc_body = ('{"recipe": "' + R + '", "item": "mailbox-check", "reason": "write failed", '
                '"detail": "The mailbox check time was not written; R8.1 will hold", "owner": "' + cfg("ar_lead") + '"}')
    write = s.http("Step 1: Write the check time", "PUT", cfg("sharepoint_url") + "/status/mailbox-check",
                   body='{"id": "mailbox-check", "last_check": "{{formatDate(now; "YYYY-MM-DDTHH:mm:ss.SSSZ"; "UTC")}}"}', parse=False,
                   onerror=[s.exception("Exception queue: status write failed", exc_body), s.ignore()])
    # n8n's "Mailbox access lost: the status list goes stale": R8.1 sends nothing until Owen restores access.
    write["filter"] = s.when("mailbox reached", "{{" + f"{s.ref('Step 1: Check the mailbox')}.statusCode" + "}}", "200")
    s.flow.append(write)
    return s


def owner_confirms() -> Scenario:
    """Step 9: only a briefed reply with its whole-account pause still open narrows, to the invoices the owner names."""
    s = Scenario(R, "R8.3 Take in a dispute: owner confirms the invoices", "webhook", test_key="r8-3-owner-confirms")
    cfg, cfg_all = start(s, CF)
    key = s.http("Step 9: Read the message's key", "GET", s.table("/key_log"),
                 query={"recipe": f"eq.{R}", "key": "eq.{{1.message_id}}", "select": "status"})
    key["filter"] = s.continue_unless_stopped()
    s.flow.append(key)
    status = "{{" + f"{key['id']}.data[1].status" + "}}"

    def step9(tag: str) -> list[dict]:
        """Read the brief and the pause, then narrow the pause or log why not."""
        read = s.http(f"{BRIEF_READ} ({tag})", "GET", s.table("/decision_log"),
                      query={"recipe": f"eq.{R}", "item": "eq.{{1.message_id}}", "decision": "like.briefed*",
                             "select": "decision,category:rules->>category", "order": "id.desc", "limit": "1"})
        pause = s.with_tries(s.http(f"{PAUSE_READ} ({tag})", "GET", cfg("sharepoint_url") + "/disputes/pause-{{encodeURL(1.message_id)}}",
                                    onerror=[]), 3)
        b, p = s.ref(f"{BRIEF_READ} ({tag})"), s.ref(f"{PAUSE_READ} ({tag})")
        trig = (CF, ("message_id", "invoices", "by", "until"), ("invoices",))
        nar = "out"
        prelude = (f"if (Number(input.pause_status) !== 200) DATA[{PAUSE_READ!r}] = [];  // no pause read: n8n's output 0 is empty\n"
                   f"// n8n's SQL gives one row or an empty item; the table API gives a list of at most one row.\n"
                   f"DATA[{BRIEF_READ!r}] = DATA[{BRIEF_READ!r}].map(i => ({{ json: Array.isArray(i.json) ? (i.json[0] || {{}}) : (i.json || {{}}) }}));\n")
        code, inputs = rule(N8N.NARROW_JS, {"Config": cfg_all, BRIEF_READ: "{{" + f"{b}.data" + "}}",
                                            PAUSE_READ: "{{" + f"{p}.data" + "}}"}, trig, prelude=prelude, many=True, bodies={
            "id_q": "out.refused ? '' : encodeURIComponent(out.id)",
            "pause_body": (f"out.refused ? null : JSON.stringify({{ id: {nar}.id, invoice: {nar}.invoice, account: {nar}.account, status: 'open', "
                           f"kind: {nar}.kind, set_by: {nar}.by, why: 'reply ' + {nar}.message_id + ', confirmed by the owner', "
                           f"message_id: {nar}.message_id, until: {nar}.until }})"),
            "narrow_body": (f"out.refused ? null : JSON.stringify({{ status: 'narrowed', narrowed_by: {nar}.by, "
                            f"narrowed_at: new Date().toISOString(), covers: {nar}.invoices }})"),
            "narrowed_log": (f"out.refused ? null : JSON.stringify({{ recipe: '{R}', item: {nar}.message_id, "
                             f"decision: 'pause narrowed to ' + {nar}.invoices.join(', '), "
                             f"rules: {{ by: {nar}.by, invoices: {nar}.invoices, kind: {nar}.kind, until: {nar}.until }} }})"),
            "not_narrowed_log": (f"JSON.stringify({{ recipe: '{R}', item: String({CB}.message_id), decision: 'pause not narrowed: ' + {nar}.reason, "
                                 f"rules: {{ by: {CB}.by || null }} }})"),
            "failed_body": exc(f"String({CB}.message_id)", "write failed", "'Narrowing the pause failed; the whole-account pause stays until it is fixed'"),
        })
        inputs["pause_status"] = "{{" + f"{p}.statusCode" + "}}"
        flow = [read, pause, s.code(f"{NARROW} ({tag})", code, inputs)]
        n = s.ref(f"{NARROW} ({tag})")
        first = lambda f: "{{" + f"{n}.result.items[1].{f}" + "}}"  # noqa: E731
        each = s.iterator(f"Each confirmed invoice ({tag})", "{{" + f"{n}.result.items" + "}}")
        it = s.ref(f"Each confirmed invoice ({tag})")
        on_fail = lambda step, body: [s.exception(f"{step}: exception queue", body), s.ignore()]  # noqa: E731
        put = f"Step 9: Pause the confirmed invoices ({tag})"
        narrow = f"Step 9: Narrow the whole-account pause ({tag})"
        paused = s.aggregator(f"Invoices paused ({tag})", f"Each confirmed invoice ({tag})", {"id_q": "{{" + f"{it}.id_q" + "}}"})
        narrow_it = s.http(narrow, "PATCH", cfg("sharepoint_url") + "/disputes/pause-{{encodeURL(1.message_id)}}", body=first("narrow_body"),
                           parse=False, onerror=on_fail(narrow, first("failed_body")))
        count = "{{length(" + f"{paused['id']}.array" + ")}}"
        narrow_it["filter"] = {"name": "an invoice was paused", "conditions": [[{"a": count, "b": "0", "o": "number:greater"}]]}
        yes = [each,
               s.http(put, "PUT", cfg("sharepoint_url") + "/disputes/{{" + f"{it}.id_q" + "}}", body="{{" + f"{it}.pause_body" + "}}",
                      parse=False, onerror=on_fail(put, "{{" + f"{it}.failed_body" + "}}")),
               paused, narrow_it,
               s.decision_log(f"Step 9: Decision log: narrowed ({tag})", first("narrowed_log"))]
        no = [s.decision_log(f"Step 9: Decision log: not narrowed ({tag})", first("not_narrowed_log"))]
        refused = first("refused")
        return flow + [s.router(f"Narrow it? ({tag})", [
            (s.when("narrow it", refused, "false"), yes),
            (s.when("refused", refused, "false", "text:notequal"), no),
        ])]

    # Make starts this scenario as soon as the owner confirms, even while the same message's intake is
    # still running in the other scenario; until that intake has finished, wait once for its brief.
    running = {"name": "intake not finished", "conditions": [[{"a": status, "b": "done", "o": "text:notequal"},
                                                               {"a": status, "b": "failed", "o": "text:notequal"}]]}
    finished = {"name": "intake finished", "conditions": [[{"a": status, "b": "done", "o": "text:equal"}],
                                                          [{"a": status, "b": "failed", "o": "text:equal"}]]}
    wait = s.sleep("Wait for the intake to finish", "30")
    s.flow.append(s.router("Intake finished?", [(running, [wait] + step9("after waiting")), (finished, step9("intake finished"))]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R8.3/make/, scenario)."""
    return [("blueprint.json", new_message()), ("morning-check.blueprint.json", morning_check()),
            ("confirm.blueprint.json", owner_confirms())]
