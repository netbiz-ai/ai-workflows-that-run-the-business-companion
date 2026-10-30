"""R4.3 Draft a reply from approved sources for a person to edit and send, as Make scenarios.

Source: book Chapter 4, recipe R4.3, build steps 1 to 8 (recipes/R4.3/build-spec.md);
AI step: recipes/R4.3/prompts/draft-reply.md. The rules are the n8n build's own JavaScript
(tools/builds/r4_3.py), run through n8n_rule.
Two scenarios, because a Make scenario has one trigger: a ticket entering a draft queue
(webhook, blueprint.json), steps 1 to 7, and a reply posted (webhook, reply-posted.blueprint.json),
step 8. The draft is only ever an internal note; nothing in either scenario can send to a customer.

Where the Make build differs from the n8n canvas, and why:
- n8n's step 3 loops back from "Step 3: Wait, then recheck" to the R4.2 log read. A Make
  scenario cannot loop back, so a Repeater runs the check up to r42_rechecks + 1 times, one
  bundle after another, with a Sleep step (Make's longest is 300 seconds, the default recheck)
  on the "wait" route. A scenario variable, set right after each check, holds whether the
  check decided (escalated, cleared or flagged), and the next pass's read is filtered on it,
  so the passes after a decision do nothing. The Repeater's number is n8n's $runIndex + 1.
- n8n's custom SQL on R4.2's log is a table-API read of R4.2's rows for the ticket; the
  rule step works out "escalated" and "logged" from them before n8n's rule runs.
- n8n reads the article and the order each behind its own IF node, and the paths meet again.
  Make's routes never meet, so "Step 4: Rule: which sources?" lists the reads its queue needs,
  an iterator runs one HTTP read per source (two tries, as the n8n reads have), and an
  aggregator hands every answer to "Step 4: Rule: sources found?"; with no read needed it
  hands on an empty list. n8n's "Step 4: Lookup failed" node runs at the top of that rule,
  for a read that still failed after its second try, and "Step 7: AI error" runs inside the
  claim check (on_ai_error).
- n8n's "Step 7: No draft: flag the ticket" Code node only lays out the reason; its fields are
  built in the bodies of the rule before each flag, so Make runs one Code step fewer. Branches
  never meet again, so each route repeats the flag steps and the closing steps (mark the key
  done, decision log), with the route in the step's name.
- n8n's custom SQL in step 8 is a table-API read of the latest "draft saved" row for the ticket.
- Mark key failed records "write failed", and the draft's decision log takes the saved note's
  ID from the note write's answer between two Code-built halves of its body.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R4.3"
N8N = n8n_build(R)
T, RP = N8N.T, N8N.R
CONFIG = {
    "helpdesk_url": "https://<your helpdesk API>",
    "articles_url": "https://<your knowledge base API>",
    "orders_url": "https://<your order system API>",
    "draft_queues": [
        {"queue": "<your warranty queue>", "article_topic": "warranty", "order": False},
        {"queue": "<your returns queue>", "article_topic": "returns", "order": True},
        {"queue": "<your delivery queue>", "article_topic": None, "order": True},
    ],
    "r42_recheck_seconds": 300,
    "r42_rechecks": 3,
    "commitment_words": ["free", "refund", "replace", "credit", "visit"],
    "claim_words": ["<your policy words, such as warranty, return, price>"],
    "edited_min_share": 0.5,
    "flag_owner": "<your draft owner>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
CFG = "$('Config').first().json"
EV = f"$('{T}').first().json.body"
RV = f"$('{RP}').first().json.body"
LOG, CHECK, PLAN, FOUND = ("Step 3: Read R4.2's log", "Step 3: Rule: escalated, cleared or not logged?",
                           "Step 4: Rule: which sources?", "Step 4: Rule: sources found?")
READS, CLAIM, OUTCOME = "Step 4: Sources read", "Step 6: Rule: claim check", "Step 8: Rule: unchanged, edited or discarded?"
DECIDED = "r42_decided"  # the scenario variable: has step 3 decided in this run?
AI_ERROR_JS = ("return [{ json: { pass: false, reason: 'AI error', "
               "detail: String(($json.error && $json.error.message) || '') + ' (after one retry)' } }];")  # n8n's "Step 7: AI error"

# Step 3: n8n's SQL answer (escalated, logged) from R4.2's rows for the ticket, and n8n's $runIndex.
R42_PRELUDE = r"""
// n8n's custom SQL on R4.2's decision log, from the table read of R4.2's rows for this ticket:
// escalated = a row with a level; logged = a row for this message.
const __raw = DATA["Step 3: Read R4.2's log"][0].json;
const __rows = Array.isArray(__raw) ? __raw : (__raw && typeof __raw === 'object' ? Object.values(__raw) : []);
const __mid = $('Step 1: Ticket enters a draft queue').first().json.body.message_id;
const __rules = r => (typeof r.rules === 'string' ? JSON.parse(r.rules) : r.rules) || {};
DATA["Step 3: Read R4.2's log"] = [{ json: {
  escalated: __rows.some(r => 'level' in __rules(r)), logged: __rows.some(r => __rules(r).message_id === __mid) } }];
// n8n's $runIndex: this is the Repeater's pass number, counting from 1.
const $runIndex = Number(input.t_check) - 1;
"""

# Step 4: the aggregator's answers, as the n8n build's two reads pass them on.
READS_PRELUDE = r"""
// The reads the queue needed, as n8n's "Step 4: Read the approved articles" and "Step 4: Read the order".
const __asRead = d => (typeof d === 'string' ? JSON.parse(d) : d);
for (const r of DATA['Step 4: Sources read'].map(i => i.json)) {
  if (Number(r.status) !== 200) continue;
  DATA[r.kind === 'article' ? 'Step 4: Read the approved articles' : 'Step 4: Read the order'] = [{ json: __asRead(r.data) }];
}
"""
LOOKUP_JS = r"""
// Step 4: Lookup failed (n8n build): a read that still fails after one retry; a person writes the reply.
const __failed = $('Step 4: Sources read').all().map(i => i.json).find(r => Number(r.status) !== 200);
if (__failed) return [{ json: { found: false, reason: 'lookup failed', detail: `the ${__failed.kind} read returned ${__failed.status || 'no answer'} (after one retry)` } }];
"""




def trigger_body(trigger: str, fields: tuple[str, ...]) -> tuple[str, dict[str, str]]:
    """(prelude, inputs): the webhook's fields, rebuilt as n8n's $('<trigger>').first().json.body."""
    inputs = {f"t_{f}": "{{1." + f + "}}" for f in fields}
    body = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in fields)
    prelude = (f"// The webhook's fields, as the rule reads them in n8n: $('{trigger}').first().json.body.\n"
               f"DATA[{json.dumps(trigger)}] = [{{ json: {{ body: {{ {body} }} }} }}];")
    return prelude, inputs


def rule(js: str, sources: dict[str, str], trigger: str = T, fields: tuple[str, ...] = ("ticket_id", "message_id"),
         prelude: str = "", extra: dict[str, str] | None = None, **kw) -> tuple[str, dict[str, str]]:
    """n8n_rule, with the scenario's webhook body (and any extra inputs) added."""
    pre, inputs = trigger_body(trigger, fields)
    code, rest = n8n_rule(js, sources, prelude=pre + "\n" + prelude, **kw)
    return code, {**inputs, **(extra or {}), **rest}


FAILED = (f"JSON.stringify({{ recipe: '{R}', item: {EV}.ticket_id, reason: 'write failed', "
          f"detail: 'Note write failed, never retried; a person writes the reply', owner: {CFG}.flag_owner }})")


def flag_bodies() -> dict[str, str]:
    """n8n's "Step 7: No draft: flag the ticket" and the steps after it, from the rule's out."""
    reason = "(out.reason || 'no draft')"
    return {
        "flag_note_body": (f"JSON.stringify({{ ticket_id: {EV}.ticket_id, message_id: {EV}.message_id, internal: true, kind: 'flag', "
                           f"text: 'No AI draft (' + {reason} + '): write this reply yourself.' }})"),
        "flag_exception_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.ticket_id, reason: 'no draft', "
                                f"detail: {reason} + ': ' + (out.detail || ''), owner: {CFG}.flag_owner }})"),
        "flag_done_body": f"JSON.stringify({{ status: 'done', result: 'flagged: ' + {reason} }})",
        "flag_log_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.ticket_id, decision: 'no draft: ' + {reason}, "
                          f"rules: Object.assign({{ message_id: {EV}.message_id, detail: out.detail || '' }}, out.rules || {{}}) }})"),
        "failed_body": FAILED,
    }


# The draft's decision log, with the saved note's ID put in between the two halves by Make.
SAVED_LOG = (f"JSON.stringify({{ recipe: '{R}', item: {EV}.ticket_id, decision: 'draft saved', "
             f"rules: Object.assign({{ message_id: {EV}.message_id, note_id: '__NOTE_ID__' }}, out.rules) }})")


def draft_queue() -> Scenario:
    """Steps 1 to 7: a ticket enters a draft queue."""
    s = Scenario(R, "R4.3 Draft a reply from approved sources", "webhook", test_key="r4-3-draft-queue")
    s.flow.append(s.webhook(T))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    conf = "{{" + f"{c}.result" + "}}"
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    out = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    result = lambda n: "{{" + f"{s.ref(n)}.result" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    key_q = "{{encodeURL(1.ticket_id)}}%3A{{encodeURL(1.message_id)}}"
    notes = cfg("helpdesk_url") + "/notes"

    def flag(tag: str, rule_name: str) -> list[dict]:
        """Step 7, no draft: the flag note, the exception row, then mark the key done and log it."""
        o = lambda f: out(rule_name, f)  # noqa: E731
        note = f"Step 7: Post the flag note ({tag})"
        return [s.http(note, "POST", notes, body=o("flag_note_body"), parse=False,
                       onerror=s.write_failed(note, key_q, o("failed_body"))),
                s.exception(f"Exception queue: no draft ({tag})", o("flag_exception_body")),
                s.finish_key(f"Mark key done: flagged ({tag})", key_q, o("flag_done_body")),
                s.decision_log(f"Decision log: flagged ({tag})", o("flag_log_body"))]

    # ---- steps 1 to 3 -----------------------------------------------------------------------
    ticket = s.http("Read the ticket", "GET", cfg("helpdesk_url") + "/tickets/{{encodeURL(1.ticket_id)}}")
    ticket["filter"] = s.continue_unless_stopped()
    s.flow.append(ticket)
    s.flow.append(s.reserve_key("Step 2: Reserve key", "{{1.ticket_id}}:{{1.message_id}}"))
    start = s.set_var("Step 3: Not decided yet", DECIDED, "false")
    start["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: a draft was made for this message
    s.flow.append(start)
    s.flow.append(s.repeater("Step 3: Check, then recheck", "{{" + f"{c}.result.r42_rechecks + 1" + "}}"))
    s.flow.append(s.get_var("Step 3: Decided yet?", DECIDED))
    read = s.http(LOG, "GET", s.table("/decision_log?recipe=eq.R4.2&item=eq.{{encodeURL(1.ticket_id)}}"))
    read["filter"] = s.when("not decided yet", "{{" + f"{s.ref('Step 3: Decided yet?')}.{DECIDED}" + "}}", "true", "text:notequal")
    s.flow.append(read)
    code, inputs = rule(N8N.R42_JS, {"Config": conf, LOG: data(LOG)}, prelude=R42_PRELUDE,
                        extra={"t_check": "{{" + f"{s.ref('Step 3: Check, then recheck')}.i" + "}}"}, bodies={
        "decided": "out.state !== 'wait'",
        "escalated_done_body": "JSON.stringify({ status: 'done', result: 'escalated by R4.2; no draft' })",
        "escalated_log_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.ticket_id, decision: 'no draft: escalated by R4.2', "
                               f"rules: {{ message_id: {EV}.message_id, r42: 'escalated' }} }})"),
        **flag_bodies(),
    })
    s.flow.append(s.code(CHECK, code, inputs))
    s.flow.append(s.set_var("Step 3: Record the check", DECIDED, out(CHECK, "decided")))
    state = out(CHECK, "state")

    # ---- step 4 ----------------------------------------------------------------------------------
    tk = "$('Read the ticket').first().json"
    code, inputs = rule(N8N.SOURCES_PLAN_JS, {"Config": conf, "Read the ticket": data("Read the ticket")}, bodies={
        "reads": (f"[out.needs_article && {{ kind: 'article', url: {CFG}.articles_url + '/articles?_wrap=1&status=approved&topic=' "
                  f"+ encodeURIComponent(out.topic) }}, out.needs_order && {{ kind: 'order', url: {CFG}.orders_url + '/orders/' "
                  f"+ encodeURIComponent({tk}.order_id) }}].filter(Boolean)"),
    })
    plan = s.code(PLAN, code, inputs)
    each = s.iterator("Step 4: Each source to read", out(PLAN, "reads"))
    get = s.with_tries(s.http("Step 4: Read the approved articles and the order", "GET",
                              "{{" + f"{s.ref('Step 4: Each source to read')}.url" + "}}"), 2)
    g = s.ref("Step 4: Read the approved articles and the order")
    gathered = s.aggregator(READS, "Step 4: Each source to read", {
        "kind": "{{" + f"{s.ref('Step 4: Each source to read')}.kind" + "}}",
        "status": "{{" + f"{g}.statusCode" + "}}", "data": "{{" + f"{g}.data" + "}}"})
    code, inputs = rule(LOOKUP_JS + N8N.SOURCES_JS, {"Config": conf, PLAN: result(PLAN), READS: "{{" + f"{s.ref(READS)}.array" + "}}"},
                        items=(READS,), input_node=PLAN, prelude=READS_PRELUDE, bodies=flag_bodies())
    found = s.code(FOUND, code, inputs)

    # ---- steps 5 to 7 ----------------------------------------------------------------------------
    vars_js = (f"{{ sources: $('{FOUND}').first().json.sources_text, "
               f"subject: {tk}.subject, body: {tk}.body }}")
    ai = s.ai_step("Step 5", ROOT / "recipes/R4.3/prompts/draft-reply.md", vars_js,
                   {"Config": conf, FOUND: result(FOUND), "Read the ticket": data("Read the ticket")}, max_tokens=4096, tries=2)
    call = s.ref("Step 5: AI call")
    code, inputs = rule(N8N.CLAIM_JS, {"Config": conf, FOUND: result(FOUND), "Step 5: AI call": "{{" + f"{call}.data" + "}}"},
                        ai_status="{{" + f"{call}.statusCode" + "}}", on_ai_error=AI_ERROR_JS, bodies={
        "note_body": (f"JSON.stringify({{ ticket_id: {EV}.ticket_id, message_id: {EV}.message_id, internal: true, kind: 'draft', "
                      "text: out.note })"),
        "saved_log_head": f"{SAVED_LOG}.split('__NOTE_ID__')[0]",
        "saved_log_tail": f"{SAVED_LOG}.split('__NOTE_ID__')[1]",
        **flag_bodies(),
    })
    claim = s.code(CLAIM, code, inputs)
    save = "Step 7: Save the draft as an internal note"
    saved = [s.http(save, "POST", notes, body=out(CLAIM, "note_body"), onerror=s.write_failed(save, key_q, out(CLAIM, "failed_body"))),
             s.finish_key("Mark key done: draft saved", key_q, '{"status": "done", "result": "draft saved"}'),
             s.decision_log("Decision log: draft saved",
                            out(CLAIM, "saved_log_head") + "{{" + f"{s.ref(save)}.data.id" + "}}" + out(CLAIM, "saved_log_tail"))]
    passed = out(CLAIM, "pass")
    drafted = ai + [claim, s.router("Claims check out?", [
        (s.when("claims check out", passed, "true"), saved),
        (s.when("claim check failed or AI error", passed, "true", "text:notequal"), flag("no draft", CLAIM)),
    ])]
    is_found = out(FOUND, "found")
    clear = [plan, each, get, gathered, found, s.router("Sources found?", [
        (s.when("sources found", is_found, "true"), drafted),
        (s.when("no source, or a lookup failed", is_found, "true", "text:notequal"), flag("no source", FOUND)),
    ])]

    escalated = [s.finish_key("Mark key done: escalated", key_q, out(CHECK, "escalated_done_body")),
                 s.decision_log("Decision log: escalated", out(CHECK, "escalated_log_body"))]
    wait = [s.sleep("Step 3: Wait, then recheck", cfg("r42_recheck_seconds"))]
    s.flow.append(s.router("R4.2 state", [
        (s.when("escalated", state, "escalated"), escalated),
        (s.when("clear", state, "clear"), clear),
        (s.when("wait", state, "wait"), wait),
        (s.when("flag", state, "flag"), flag("R4.2 has not logged it", CHECK)),
    ]))
    return s


def reply_posted() -> Scenario:
    """Step 8: when the reply is posted, log the draft as unchanged, edited or discarded."""
    s = Scenario(R, "R4.3 Draft a reply from approved sources: reply posted", "webhook", test_key="r4-3-reply-posted")
    s.flow.append(s.webhook(RP))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    conf = "{{" + f"{c}.result" + "}}"
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    key_q = "reply%3A{{encodeURL(1.reply_id)}}"
    reserve = s.reserve_key("Step 8: Reserve key", "reply:{{1.reply_id}}")
    reserve["filter"] = s.continue_unless_stopped()
    s.flow.append(reserve)
    find = s.http("Step 8: Find the draft", "GET",
                  s.table(f"/decision_log?recipe=eq.{R}&item=eq.{{{{encodeURL(1.ticket_id)}}}}&decision=eq.draft%20saved&order=id.desc&limit=1"))
    find["filter"] = s.is_new_key("Step 8: Reserve key")  # a copy stops here: this reply was logged before
    s.flow.append(find)
    f = s.ref("Step 8: Find the draft")
    note_id = "{{" + f"{f}.data[1].rules.note_id" + "}}"
    read_note = s.http("Step 8: Read the draft note", "GET", cfg("helpdesk_url") + "/notes/{{" + f"encodeURL({f}.data[1].rules.note_id)" + "}}")
    read_reply = s.http("Step 8: Read the reply", "GET", cfg("helpdesk_url") + "/replies/{{encodeURL(1.reply_id)}}")
    code, inputs = rule(N8N.OUTCOME_JS, {"Config": conf, "Was there a draft?": "{{" + f"{f}.data[1].rules" + "}}",
                                         "Step 8: Read the draft note": data("Step 8: Read the draft note"),
                                         "Step 8: Read the reply": data("Step 8: Read the reply")},
                        trigger=RP, fields=("ticket_id", "reply_id"), bodies={
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {RV}.ticket_id, decision: 'draft ' + out.outcome, "
                     f"rules: {{ reply_id: {RV}.reply_id, note_id: $('Was there a draft?').first().json.note_id, words_kept: out.share }} }})"),
    })
    outcome = s.code(OUTCOME, code, inputs)
    compared = [read_note, read_reply, outcome,
                s.decision_log("Step 8: Decision log: draft outcome", "{{" + f"{s.ref(OUTCOME)}.result.log_body" + "}}"),
                s.finish_key("Step 8: Mark key done", key_q, '{"status": "done", "result": "outcome logged"}')]
    s.flow.append(s.router("Was there a draft?", [
        (s.when("a draft was saved", note_id, "", "exist"), compared),
        (s.when("no draft", note_id, "", "notexist"),
         [s.finish_key("Step 8: Mark key done: no draft", key_q, '{"status": "done", "result": "no draft to compare"}')]),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R4.3/make/, scenario)."""
    return [("blueprint.json", draft_queue()), ("reply-posted.blueprint.json", reply_posted())]
