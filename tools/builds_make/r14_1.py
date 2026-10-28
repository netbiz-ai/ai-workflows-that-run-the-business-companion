"""R14.1 Turn a transcript into a draft action list for the chair to verify, as Make scenarios.

Source: book Chapter 14, recipe R14.1, build steps 1 to 9 (recipes/R14.1/build-spec.md);
AI step: recipes/R14.1/prompts/propose-actions.md. The rules are the n8n build's own JavaScript
(tools/builds/r14_1.py), run through n8n_rule.
Two scenarios, because a Make scenario has one trigger: a transcript saved (webhook, steps 1 to 7
and 9) and the morning expiry check (schedule, every day at 07:00, step 8). Each passes its own
trigger name in executed=, so n8n's "Morning expiry?" If node, which only asked which trigger
ran, is dropped.
Differences from the n8n build, all forced by Make:
- The AI call is tried three times, as in n8n (step 9: "after two retries"), with R7.1's
  three_tries(): each try's error route holds the next try and a Resume handler that hands its
  response back. n8n's "Step 9: AI error" node runs inside "Step 6: Rules: check the items"
  (on_ai_error), because Make branches never meet again.
- Each branch repeats the closing steps (mark the key done, decision log), with the branch in the
  step's name; the bodies use the branch's own rule output where n8n reads whichever of step 6 or
  step 9 ran.
- Step 7's rows are one bundle each (an iterator over "Step 7: Rows to write"), written by one step
  whose method (PUT for an item, DELETE for a row of an untouched earlier draft) is mapped from the
  row, as in n8n; n8n's "Anything to write?" If node is that step's filter. An aggregator gathers
  the rows back before "Step 7: One message", as n8n's runOnceForAllItems node does.
- Step 8's "One message" reads the expired drafts through an aggregator; n8n's paired-item lookup
  $('Step 8: Rule: past the deadline?').itemMatching(i) is written .all()[i], which is the same
  item here because the aggregator keeps the rule's order. Make's aggregator outputs once even when
  nothing expired, so the step's filter stops the run on an empty list, as n8n's empty output does.
- The rules read the webhook body as n8n's $('Step 1: Transcript saved').first().json.body; a Make
  webhook step's output cannot be mapped whole, so its fields are passed one by one and the
  prelude rebuilds that body before the rule runs.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402
from r7_1 import three_tries  # noqa: E402

R = "R14.1"
N8N = n8n_build(R)
T, M = N8N.T, N8N.M
REGISTER = "Step 1: Read the register"
REGISTERED = "Step 1: Rule: registered series?"
DRAFT = "Step 2: Read the current draft"
STARTED = "Step 2: Rule: has the chair started?"
MEETING = "Step 3: Read the meeting"
SCOPE = "Step 3: Rule: in scope?"
ATTENDEES = "Step 4: Read attendees"
TRANSCRIPT = "Read the transcript"
CALL = "Step 5: AI call"
CHECK = "Step 6: Rules: check the items"
ROWS = "Step 7: Rows to write"
EXPIRE = "Step 8: Rule: past the deadline?"
# The n8n build's "Step 9: AI error" node, unchanged.
AI_ERROR_JS = ("return [{ json: { ok: false, reason: 'AI error after two retries', "
               "detail: String(($json.error && $json.error.message) || '') } }];")
CONFIG = {
    "register_url": "https://<your meeting register API>",
    "calendar_url": "https://<your calendar API>",
    "transcripts_url": "https://<your transcription API>",
    "actions_url": "https://<your action list API>",
    "messaging_url": "https://<your messaging API>",
    "transcript_link": "https://<your transcript viewer>/{transcript_id}?t={time_stamp}",
    "action_list_link": "https://<your action list>?occurrence={occurrence_id}",
    "out_of_scope_titles": ["HR", "disciplinary", "negotiation"],
    "max_items_per_line": 2,
    "working_weekdays": [1, 2, 3, 4, 5],
    "holidays": ["<your holiday dates, YYYY-MM-DD>"],
    "register_owner": "<your register owner>",
    "exception_owner": "<your workflow editor>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
FIELDS = ("series_id", "occurrence_id", "transcript_id")
EV = f"$('{T}').first().json.body"
CFG = "$('Config').first().json"
SERIES = f"$('{REGISTERED}').first().json.series"
# The key log's failure and the write-failed row, the same on every branch.
FAILED = {
    "failed_key_body": "JSON.stringify({ status: 'failed', result: 'write failed' })",
    "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.occurrence_id, reason: 'write failed', "
                    "detail: 'An action-list write or message failed; never retried. Check the draft, then release the key.', "
                    f"owner: {CFG}.exception_owner }})"),
}


def closing(outcome: str, rules: str) -> dict[str, str]:
    """The bodies that mark the key done and log the decision, for one branch's outcome."""
    return {"done_body": f"JSON.stringify({{ status: 'done', result: {outcome} }})",
            "log_body": f"JSON.stringify({{ recipe: '{R}', item: {EV}.occurrence_id, decision: {outcome}, rules: {rules} }})",
            **FAILED}


def rule(js: str, sources: dict[str, str], **kw) -> tuple[str, dict[str, str]]:
    """n8n_rule, plus the webhook's fields rebuilt as n8n's $('Step 1: Transcript saved').first().json.body."""
    body = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in FIELDS)
    prelude = (f"// The webhook's fields, as the rule reads them in n8n: $('{T}').first().json.body.\n"
               f"DATA[{json.dumps(T)}] = [{{ json: {{ body: {{ {body} }} }} }}];")
    code, inputs = n8n_rule(js, sources, prelude=prelude, executed=(T,), **kw)
    return code, {**{f"t_{f}": "{{1." + f + "}}" for f in FIELDS}, **inputs}


def transcript_saved() -> Scenario:
    s = Scenario(R, "R14.1 Turn a transcript into a draft action list: transcript saved", "webhook", test_key="r14-1-transcript-saved")
    s.flow.append(s.webhook(T))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    res = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    key_q = "{{encodeURL(1.occurrence_id)}}"
    msg = cfg("messaging_url") + "/messages"
    sources = {"Config": "{{" + f"{c}.result" + "}}"}

    def write(name: str, url: str, body: str, step: str) -> dict:
        """A write: never retried; a failure marks the key failed and adds the exception row."""
        return s.http(name, "POST", url, body=res(step, body), parse=False,
                      onerror=[s.finish_key(f"{name}: mark key failed", key_q, res(step, "failed_key_body")),
                               s.exception(f"{name}: exception queue", res(step, "failed_body")), s.ignore()])

    def close(tag: str, step: str) -> list[dict]:
        return [s.finish_key(f"Mark key done ({tag})", key_q, res(step, "done_body")),
                s.decision_log(f"Decision log ({tag})", res(step, "log_body"))]

    # Step 1: only a registered series goes on; anything else stops, no AI call.
    read = s.http(REGISTER, "GET", cfg("register_url") + "/series", query={"_wrap": "1", "id": "{{1.series_id}}"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    code, inputs = n8n_rule(N8N.REGISTERED_JS, {REGISTER: data(REGISTER)})
    s.flow.append(s.code(REGISTERED, code, inputs))
    sources[REGISTERED] = "{{" + f"{s.ref(REGISTERED)}.result" + "}}"

    # Step 2: the duplicate key, the occurrence; a draft the chair has started is kept.
    reserve = s.reserve_key("Step 2: Reserve key", "{{1.occurrence_id}}")
    reserve["filter"] = s.when("registered series", res(REGISTERED, "registered"), "true")  # not registered: stop
    s.flow.append(reserve)
    draft = s.http(DRAFT, "GET", cfg("actions_url") + "/items", query={"_wrap": "1", "occurrence_id": "{{1.occurrence_id}}"})
    draft["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here
    s.flow.append(draft)
    code, inputs = n8n_rule(N8N.DRAFT_JS, {DRAFT: data(DRAFT)})
    s.flow.append(s.code(STARTED, code, inputs))

    # Step 3: the register's flag plus a title check; a match stops before the AI.
    meeting = s.http(MEETING, "GET", cfg("calendar_url") + "/occurrences/{{encodeURL(1.occurrence_id)}}")
    meeting["filter"] = s.when("chair has not started", res(STARTED, "started"), "true", "text:notequal")  # draft kept: stop
    s.flow.append(meeting)
    sources[MEETING] = data(MEETING)
    outcome = "'out of scope: no AI call'"
    code, inputs = rule(N8N.SCOPE_JS, sources, bodies={
        "exception_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.occurrence_id, reason: 'out of scope', "
                           f"detail: 'No AI call: ' + out.reason + '; the chair deletes the transcript', owner: {SERIES}.chair }})"),
        "chair_message": (f"JSON.stringify({{ to: [{SERIES}.chair], subject: 'Transcript out of scope: ' + {SERIES}.name, "
                          "text: 'This meeting is out of scope for action lists (' + out.reason + '). No AI call was made. "
                          f"Please delete transcript ' + {EV}.transcript_id + ' today.' }})"),
        **closing(outcome, "{ scope: out.reason }"),
    })
    s.flow.append(s.code(SCOPE, code, inputs))
    out_of_scope = [s.exception("Step 3: Exception queue: out of scope", res(SCOPE, "exception_body")),
                    write("Step 3: Tell the chair to delete the transcript", msg, "chair_message", SCOPE)] + close("out of scope", SCOPE)

    # Steps 4 and 5: attendees from the meeting, never the transcript; the AI proposes, three tries.
    in_scope = [s.http(ATTENDEES, "GET", cfg("calendar_url") + "/attendees", query={"_wrap": "1", "occurrence_id": "{{1.occurrence_id}}"}),
                s.http(TRANSCRIPT, "GET", cfg("transcripts_url") + "/transcripts/{{encodeURL(1.transcript_id)}}")]
    sources.update({ATTENDEES: data(ATTENDEES), TRANSCRIPT: data(TRANSCRIPT)})
    vars_js = (f"{{ series: $('{REGISTERED}').first().json.series.name, "
               f"transcript: ($('{TRANSCRIPT}').first().json.lines || []).map(l => `${{l.time_stamp}} ${{l.speaker}}: ${{l.text}}`).join('\\n') }}")
    ai = s.ai_step("Step 5", ROOT / "recipes/R14.1/prompts/propose-actions.md", vars_js, sources, max_tokens=2048, tries=1)
    three_tries(s, ai[1])
    in_scope += ai

    # Steps 6 and 9: the rules decide what is written; a failed check or an AI error goes to the chair.
    call = ai[1]["id"]
    outcome = "(out.ok ? 'proposed ' + out.items.length + ' item(s)' : 'chair writes the list: ' + out.reason)"
    code, inputs = rule(N8N.CHECK_JS, {**sources, CALL: "{{" + f"{call}.data" + "}}"},
                        ai_status="{{" + f"{call}.statusCode" + "}}", on_ai_error=AI_ERROR_JS, bodies={
        "exception_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.occurrence_id, reason: 'chair writes the list from the read-back', "
                           f"detail: out.reason + ': ' + (out.detail || ''), owner: {SERIES}.chair }})"),
        "readback_message": (f"JSON.stringify({{ to: [{SERIES}.chair, {SERIES}.backup], subject: 'No draft action list: ' + {SERIES}.name, "
                             "text: 'No draft could be proposed for this meeting (' + out.reason + '). Please write the action list from the read-back.' })"),
        **closing(outcome, "out.rules || { ai: out.reason }"),
    })
    in_scope.append(s.code(CHECK, code, inputs))
    readback = [s.exception("Step 9: Exception queue: chair writes the list", res(CHECK, "exception_body")),
                write("Step 9: Tell the chair to use the read-back", msg, "readback_message", CHECK)] + close("read-back", CHECK)

    # Step 7: each item as "proposed", linked to its line; rows of an untouched earlier draft go.
    code, inputs = n8n_rule(N8N.OPS_JS, {CHECK: "{{" + f"{s.ref(CHECK)}.result" + "}}", STARTED: "{{" + f"{s.ref(STARTED)}.result" + "}}"},
                            many=True, bodies={"method": "String(out.op).toLowerCase()", "id_q": "encodeURIComponent(out.id || '')",
                                               "row_body": "JSON.stringify(out.body || {})"})
    rows = s.code(ROWS, code, inputs)
    each = s.iterator("Step 7: Each row", "{{" + f"{rows['id']}.result.items" + "}}")
    it = lambda f: "{{" + f"{each['id']}.{f}" + "}}"  # noqa: E731
    put = s.http("Step 7: Write proposed items", "PUT", cfg("actions_url") + "/items/" + it("id_q"), body=it("row_body"), parse=False,
                 onerror=[s.finish_key("Step 7: Write proposed items: mark key failed", key_q, res(CHECK, "failed_key_body")),
                          s.exception("Step 7: Write proposed items: exception queue", res(CHECK, "failed_body")), s.ignore()])
    put["mapper"]["method"] = it("method")  # PUT an item, DELETE a row of the earlier draft
    put["filter"] = s.when("anything to write", it("op"), "none", "text:notequal")
    gathered = s.aggregator("Step 7: Rows written", "Step 7: Each row", {"id": it("id")})
    outcome = f"'proposed ' + $('{CHECK}').first().json.items.length + ' item(s)'"
    code, inputs = rule(N8N.COLLECT_JS, {**sources, CHECK: "{{" + f"{s.ref(CHECK)}.result" + "}}"}, bodies={
        "chair_message": (f"JSON.stringify({{ to: [{SERIES}.chair, {SERIES}.backup], subject: 'Draft action list to verify: ' + {SERIES}.name, "
                          "text: out.items + ' proposed item(s), ' + out.flagged + ' flagged. Verify by the end of ' + out.verify_by + ': ' + "
                          f"{CFG}.action_list_link.replace('{{occurrence_id}}', encodeURIComponent({EV}.occurrence_id)) }})"),
        **closing(outcome, f"$('{CHECK}').first().json.rules"),
    })
    one = s.code("Step 7: One message", code, inputs)
    proposed = [rows, each, put, gathered, one,
                write("Step 7: Send the chair and backup the link", msg, "chair_message", "Step 7: One message")] + close("proposed", "Step 7: One message")

    in_scope.append(s.router("Items pass the check?", [
        (s.when("items pass", res(CHECK, "ok"), "true"), proposed),
        (s.when("chair writes the list", res(CHECK, "ok"), "true", "text:notequal"), readback),
    ]))
    s.flow.append(s.router("In scope?", [
        (s.when("in scope", res(SCOPE, "in_scope"), "true"), in_scope),
        (s.when("out of scope", res(SCOPE, "in_scope"), "true", "text:notequal"), out_of_scope),
    ]))
    return s


def each_morning() -> Scenario:
    s = Scenario(R, "R14.1 Turn a transcript into a draft action list: morning expiry", "schedule", test_key=M,
                 schedule="every day at 07:00")
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()

    # Step 8: a draft still unverified after its deadline (the end of the next working day) expires.
    read = s.http("Step 8: Read proposed items", "GET", cfg("actions_url") + "/items", query={"_wrap": "1", "status": "proposed"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    code, inputs = n8n_rule(N8N.EXPIRE_JS, {"Config": "{{" + f"{c}.result" + "}}", "Step 8: Read proposed items": "{{" + f"{read['id']}.data" + "}}"},
                            many=True, executed=(M,), bodies={
        "id_q": "encodeURIComponent(out.id)",
        "expired_body": "JSON.stringify({ status: 'expired' })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: out.id, decision: 'expired unverified', rules: {{ occurrence: out.occurrence_id, series: out.series_id }} }})",
        "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: out.id, reason: 'write failed', detail: 'Expiry write failed; never retried', "
                        f"owner: {CFG}.exception_owner }})"),
    })
    s.flow.append(s.code(EXPIRE, code, inputs))
    each = s.iterator("Step 8: Each expired draft", "{{" + f"{s.ref(EXPIRE)}.result.items" + "}}")
    it = lambda f: "{{" + f"{each['id']}.{f}" + "}}"  # noqa: E731
    s.flow += [each,
               s.http("Step 8: Mark expired", "PATCH", cfg("actions_url") + "/items/" + it("id_q"), body=it("expired_body"), parse=False,
                      onerror=[s.exception("Step 8: Exception queue: write failed", it("failed_body")), s.ignore()]),
               s.decision_log("Step 8: Decision log", it("log_body"))]
    gathered = s.aggregator("Step 8: Expired drafts", "Step 8: Each expired draft",
                            {"id": it("id"), "occurrence_id": it("occurrence_id"), "series_id": it("series_id")})
    s.flow.append(gathered)
    js = N8N.EXPIRED_LIST_JS.replace(f"$('{EXPIRE}').itemMatching(i)", f"$('{EXPIRE}').all()[i]")
    assert js != N8N.EXPIRED_LIST_JS
    agg = "{{" + f"{gathered['id']}.array" + "}}"
    code, inputs = n8n_rule(js, {"Config": "{{" + f"{c}.result" + "}}", EXPIRE: agg, "Step 8: Expired drafts": agg},
                            items=(EXPIRE, "Step 8: Expired drafts"), executed=(M,), bodies={
        "owner_message": (f"JSON.stringify({{ to: [{CFG}.register_owner], subject: out.count + ' draft action list(s) expired unverified', "
                          "text: 'The chair or backup types these actions in: ' + out.lists.join('; ') })"),
        "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: 'expiry ' + new Date().toISOString().slice(0, 10), reason: 'write failed', "
                        "detail: 'Message to the register owner failed; never retried: ' + out.lists.join('; '), "
                        f"owner: {CFG}.exception_owner }})"),
    })
    one = s.code("Step 8: One message", code, inputs)
    one["filter"] = s.when("a draft expired", "{{length(" + f"{gathered['id']}.array" + ")}}", "0", "number:greater")
    o = one["id"]
    s.flow += [one, s.http("Step 8: Tell the register owner", "POST", cfg("messaging_url") + "/messages",
                           body="{{" + f"{o}.result.owner_message" + "}}", parse=False,
                           onerror=[s.exception("Step 8: Exception queue: message failed", "{{" + f"{o}.result.failed_body" + "}}"), s.ignore()])]
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R14.1/make/, scenario)."""
    return [("blueprint.json", transcript_saved()), ("morning.blueprint.json", each_morning())]
