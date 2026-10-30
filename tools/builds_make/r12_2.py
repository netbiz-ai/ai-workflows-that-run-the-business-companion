"""R12.2 Draft the weekly briefing narrative with a link behind every figure, as Make scenarios.

Source: book Chapter 12, recipe R12.2, build steps 1 to 14 (recipes/R12.2/build-spec.md);
AI step: recipes/R12.2/prompts/draft-narrative.md. The rules are the n8n build's own JavaScript
(tools/builds/r12_2.py), run through n8n_rule.
Five scenarios, because a Make scenario has one trigger:
- a table version written (webhook, blueprint.json) and Friday 14:00 (schedule, every Friday at
  14:00, friday-1400.blueprint.json) both draft, steps 1 to 11 and 14;
- a sentence approved or deleted (webhook, verify.blueprint.json), step 12;
- Friday 16:00 (schedule, every Friday at 16:00, friday-1600.blueprint.json) and Friday 16:45
  (schedule, every Friday at 16:45, friday-1645.blueprint.json), step 13.

Where the Make build differs from the n8n canvas, and why:
- n8n's "Which event?" Code node and "Event" switch only ask which trigger ran. Each scenario
  has one trigger, so they are gone (AGENTS.md: drop the nodes that only ask which trigger ran);
  the rules that read "Which event?" get its answer, the event and the webhook body, from the
  scenario itself (event()), because a Make webhook step's output cannot be mapped whole.
- The rules use Luxon's $now; Make's Code app has no Luxon and runs in UTC, so a small shim
  answers weekday, set() and comparison the same way for the tests' UTC times (NOW_SHIM).
- The step 5 AI call tries three times, as the n8n build's does (tries=3), with the second and
  third tries in nested error routes (mk's ai_step, tries=3). n8n's "Step 11: AI
  error" node runs inside the steps 6 to 9 rule (on_ai_error), and "Step 14: Too late to draft"
  is the fixed answer that rule's node gives, passed to the draft record as data, because Make
  branches never meet again.
- Branches never meet again after a router, so steps 4 to 12 are built once for each answer to
  "Any held back?" and "Too late?", and each route carries its own draft record, saves and
  closing steps (mark the key done, decision log), with the route in the step's name. A failed
  draft, and a draft too late, always has no narrative and a passing one never does, so n8n's
  "No narrative?" check is the route itself.
- Mark key failed records "write failed" without the HTTP error text, which Make's error route
  does not hand to a later body.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R12.2"
N8N = n8n_build(R)
FRI, WRITTEN, VERIFY, FOUR, LATE = N8N.FRI, N8N.WRITTEN, N8N.VERIFY, N8N.FOUR, N8N.LATE
VERSION, WHEN = "Step 1: Which version?", "Steps 1 and 14: Draft now?"
HOLD, INPUT = "Step 3: Rule: hold back commentary naming a listed person", "Step 4: Build the input"
CHECK, LINKS, DRAFT = "Steps 6 to 9: Rule: check numbers, causes and missing measures", "Step 10: Insert the source links", "The week's draft record"
CONFIG = {
    "table_url": "https://<your weekly table API>",
    "commentary_url": "https://<your owner commentary list API>",
    "customers_url": "https://<your customer list API>",
    "staff_url": "https://<your staff list API>",
    "alert_log_url": "https://<your R12.3 alert log API>",
    "drafts_url": "https://<your draft list API>",
    "preread_url": "https://<your pre-read API>",
    "messaging_url": "https://<your messaging API>",
    "draft_weekday": 5,
    "draft_from": "14:00",
    "first_draft_until": "15:30",
    "must_mention_change_above": {"<measure>": "<your stated size>"},
    "banned_causes": ["because", "<your banned-cause words>"],
    "banned_cause_list_version": "<your list version>",
    "prompt_version": "<your prompt version>",
    "verifier": "<your verifier>",
    "backup_verifier": "<your backup verifier>",
    "verifier_own_measures": ["<measures your verifier owns>"],
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
AI_ERROR_JS = ("return [{ json: { pass: false, reason: 'AI error after two retries', "
               "problems: [String(($json.error && $json.error.message) || '')] } }];")
TOO_LATE = {"pass": False, "reason": "newer table version after Friday 16:00", "problems": []}  # n8n's "Step 14: Too late to draft"
# Luxon's $now, for the steps 1 and 14 rule: weekday (1 is Monday), set() and comparison, in UTC.
NOW_SHIM = r"""
// Make's Code app has no Luxon: $now answers weekday, set() and comparison as Luxon does, in UTC.
const __now = d => ({ valueOf: () => d.getTime(), get weekday() { return d.getUTCDay() || 7; },
  set: o => { const x = new Date(d.getTime()); x.setUTCHours('hour' in o ? o.hour : x.getUTCHours(), 'minute' in o ? o.minute : x.getUTCMinutes(),
    'second' in o ? o.second : x.getUTCSeconds(), 'millisecond' in o ? o.millisecond : x.getUTCMilliseconds()); return __now(x); } });
const $now = __now(new Date());
"""
# JavaScript shorthands for the bodies, as in the n8n build.
CFG = "$('Config').first().json"
W = f"$('{WHEN}').first().json"
HELD = ("JSON.stringify({ to: $('Config').first().json.verifier, subject: 'Held-back commentary, week ' + "
        f"{W}.week, text: out.held.map(c => c.measure + ' (' + c.owner + '): ' + c.text).join('\\n') }})")


def event(name: str, fields: tuple[str, ...] = ()) -> tuple[str, dict[str, str]]:
    """(prelude, inputs): n8n's "Which event?" answer for this scenario: the event and the webhook body."""
    inputs = {f"t_{f}": "{{1." + f + "}}" for f in fields}
    body = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in fields)
    prelude = f"// n8n's \"Which event?\": this scenario's trigger, and its body.\nDATA['Which event?'] = [{{ json: {{ event: '{name}', body: {{ {body} }} }} }}];"
    return prelude, inputs


def rule(js: str, sources: dict[str, str], ev: tuple[str, dict[str, str]] | None = None, prelude: str = "", **kw):
    """n8n_rule, with this scenario's "Which event?" answer when the rule reads it."""
    if not ev:
        return n8n_rule(js, sources, prelude=prelude, **kw)
    code, inputs = n8n_rule(js, sources, prelude=ev[0] + "\n" + prelude, **kw)
    return code, {**ev[1], **inputs}


def start(s: Scenario, trigger: str | None):
    if trigger:
        s.flow.append(s.webhook(trigger))
    s.flow.append(s.config(CONFIG))
    s.flow += s.stop_flag()
    c = s.ref("Config")
    return (lambda f: "{{" + f"{c}.result.{f}" + "}}"), "{{" + f"{c}.result" + "}}"


def exc(item: str, detail: str) -> str:
    return f"JSON.stringify({{ recipe: '{R}', item: {item}, reason: 'write failed', detail: '{detail}', owner: {CFG}.verifier }})"


def draft(trigger: str, test_key: str, name: str, ev_name: str, fields: tuple[str, ...], schedule: str | None) -> Scenario:
    """Steps 1 to 11 and 14, for a table version written or Friday 14:00."""
    s = Scenario(R, f"R12.2 Draft the weekly briefing narrative: {name}", "schedule" if schedule else "webhook",
                 test_key=test_key, schedule=schedule)
    cfg, cfg_all = start(s, None if schedule else trigger)
    ev = event(ev_name, fields)
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    out = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    result = lambda n: "{{" + f"{s.ref(n)}.result" + "}}"  # noqa: E731

    # ---- step 1: which version; steps 1 and 14: draft now, or too late ---------------------------
    versions = s.http("Read versions", "GET", cfg("table_url") + "/versions", query={"_wrap": "1"})
    versions["filter"] = s.continue_unless_stopped()
    s.flow.append(versions)
    code, inputs = rule(N8N.VERSION_JS, {"Read versions": data("Read versions")}, ev)
    s.flow.append(s.code(VERSION, code, inputs))
    week_draft = s.http("Read the week's draft", "GET", cfg("drafts_url") + "/drafts", query={"_wrap": "1", "week": out(VERSION, "week")})
    week_draft["filter"] = s.when("a written version", out(VERSION, "version"), "", "exist")
    s.flow.append(week_draft)
    code, inputs = rule(N8N.WHEN_JS, {"Config": cfg_all, VERSION: result(VERSION), "Read the week's draft": data("Read the week's draft")},
                        ev, prelude=NOW_SHIM, bodies={
        "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: out.key }})",
        "key_q": "encodeURIComponent(out.key || '')",
        "failed_body": exc("out.key", "A briefing write failed; check the draft and pre-read before any rerun"),
    })
    s.flow.append(s.code(WHEN, code, inputs))
    reserve = s.rpc("Step 2: Reserve key", "reserve_key", out(WHEN, "reserve_body"))
    reserve["filter"] = s.when("draft now or too late", out(WHEN, "action"), "", "exist")  # "wait" ends the run here
    s.flow.append(reserve)
    key_q = out(WHEN, "key_q")
    failed = lambda step: s.write_failed(step, key_q, out(WHEN, "failed_body"))  # noqa: E731

    # ---- step 3: the table, the commentary and the lists ------------------------------------------
    reads = [("Read the table", cfg("table_url") + "/weekly_table", {"_wrap": "1", "version": out(WHEN, "version")}),
             ("Read the commentary", cfg("commentary_url") + "/commentary", {"_wrap": "1", "week": out(WHEN, "week")}),
             ("Read the customer list", cfg("customers_url") + "/customers", {"_wrap": "1"}),
             ("Read the staff list", cfg("staff_url") + "/staff", {"_wrap": "1"}),
             ("Read the alert log", cfg("alert_log_url") + "/alerts", {"_wrap": "1", "week": out(WHEN, "week")})]
    for i, (n, url, q) in enumerate(reads):
        m = s.http(n, "GET", url, query=q)
        if i == 0:
            m["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: this week and version were drafted
        s.flow.append(m)
    code, inputs = n8n_rule(N8N.HOLD_JS, {"Config": cfg_all, WHEN: result(WHEN),
                                          **{n: data(n) for n in ("Read the customer list", "Read the staff list", "Read the commentary")}},
                            bodies={"any_held": "out.held.length > 0", "held_message": HELD})
    s.flow.append(s.code(HOLD, code, inputs))
    sources = {"Config": cfg_all, WHEN: result(WHEN), "Read the table": data("Read the table"), HOLD: result(HOLD)}

    def closing(tag: str, rec: str, publish: bool) -> list[dict]:
        """Save the draft; with no narrative, publish the table and commentary; then the key and the log."""
        flow = [s.http(f"Step 12: Save the draft for the verifier ({tag})", "PUT", cfg("drafts_url") + "/drafts/" + out(rec, "week_q"),
                       body=out(rec, "draft_body"), parse=False, onerror=failed(f"Step 12: Save the draft for the verifier ({tag})"))]
        if publish:
            name = f"Step 11: Publish table and commentary, no narrative ({tag})"
            flow.append(s.http(name, "PUT", cfg("preread_url") + "/pre_reads/" + out(rec, "week_q"), body=out(rec, "preread_body"),
                               parse=False, onerror=failed(name)))
        return flow + [s.finish_key(f"Mark key done ({tag})", key_q, out(rec, "done_body")),
                       s.decision_log(f"Decision log ({tag})", out(rec, "log_body"))]

    def record(tag: str, src_name: str, src_expr: str) -> dict:
        """n8n's "The week's draft record", run on the answer from src_name (passed, failed or too late)."""
        rec = "out.draft"
        code, inputs = n8n_rule(N8N.DRAFT_JS, {**sources, src_name: src_expr}, input_node=src_name, bodies={
            "draft_body": "JSON.stringify(out.draft)",
            "preread_body": "JSON.stringify(out.preread)",
            "week_q": "encodeURIComponent(out.draft.week)",
            "done_body": f"JSON.stringify({{ status: 'done', result: {rec}.stage }})",
            "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {W}.key, decision: {rec}.stage + ({rec}.reason ? ': ' + {rec}.reason : ''), "
                         f"rules: {{ superseded: {rec}.superseded, problems: {rec}.problems, sentences: {rec}.sentences.map(s => s.text), "
                         f"held_back: {rec}.held_back, model: {rec}.model, prompt_version: {rec}.prompt_version, "
                         f"banned_cause_list_version: {rec}.banned_cause_list_version }} }})"),
        })
        return s.code(f"{DRAFT} ({tag})", code, inputs)

    def steps_4_to_12(tag: str) -> list[dict]:
        """Step 14 (too late) or steps 4 to 10, then the draft record and its saves."""
        late_tag, pass_tag, fail_tag = f"{tag}, too late", f"{tag}, passed", f"{tag}, no narrative"
        late = record(late_tag, "Step 14: Too late to draft", json.dumps(TOO_LATE))
        too_late = [late] + closing(late_tag, late["metadata"]["designer"]["name"], True)

        inp = f"{INPUT} ({tag})"
        code, inputs = n8n_rule(N8N.INPUT_JS, {**sources, "Read the alert log": data("Read the alert log")})
        build_input = s.code(inp, code, inputs)
        vars_js = ("{ week: $('Step 4: Build the input').first().json.week, table_version: $('Step 4: Build the input').first().json.version, "
                   "table_rows: $('Step 4: Build the input').first().json.table_rows, must_mention_list: $('Step 4: Build the input').first().json.must_mention_list, "
                   "banned_cause_list: $('Step 4: Build the input').first().json.banned_cause_list, commentary: $('Step 4: Build the input').first().json.commentary_text }")
        step = f"Step 5 ({tag})"
        ai = s.ai_step(step, ROOT / "recipes/R12.2/prompts/draft-narrative.md", vars_js,
                       {"Config": cfg_all, INPUT: result(inp)}, max_tokens=1500, tries=3)
        call = s.ref(f"{step}: AI call")
        code, inputs = n8n_rule(N8N.CHECK_JS, {"Config": cfg_all, INPUT: result(inp), "Step 5: AI call": "{{" + f"{call}.data" + "}}"},
                                ai_status="{{" + f"{call}.statusCode" + "}}", on_ai_error=AI_ERROR_JS)
        check = s.code(f"{CHECK} ({tag})", code, inputs)
        ck = f"{CHECK} ({tag})"
        code, inputs = n8n_rule(N8N.LINKS_JS, {INPUT: result(inp), CHECK: result(ck)}, input_node=CHECK)
        links = s.code(f"{LINKS} ({tag})", code, inputs)
        passed = record(pass_tag, LINKS, result(f"{LINKS} ({tag})"))
        no_narrative = record(fail_tag, CHECK, result(ck))
        drafted = [build_input] + ai + [check, s.router(f"Draft passed? ({tag})", [
            (s.when("pass", out(ck, "pass"), "true"),
             [links, passed] + closing(pass_tag, passed["metadata"]["designer"]["name"], False)),
            (s.when("no narrative", out(ck, "pass"), "true", "text:notequal"),
             [no_narrative] + closing(fail_tag, no_narrative["metadata"]["designer"]["name"], True)),
        ])]
        action = out(WHEN, "action")
        return [s.router(f"Too late? ({tag})", [(s.when("too late", action, "late"), too_late),
                                                (s.when("draft", action, "late", "text:notequal"), drafted)])]

    send = "Step 3: Send held-back commentary to the verifier"
    held = [s.http(send, "POST", cfg("messaging_url") + "/messages", body=out(HOLD, "held_message"), parse=False, onerror=failed(send))]
    s.flow.append(s.router("Any held back?", [
        (s.when("held back", out(HOLD, "any_held"), "true"), held + steps_4_to_12("held back")),
        (s.when("none held back", out(HOLD, "any_held"), "true", "text:notequal"), steps_4_to_12("none held back")),
    ]))
    return s


def verify() -> Scenario:
    """Step 12: the verifier approves or deletes each sentence."""
    s = Scenario(R, "R12.2 Draft the weekly briefing narrative: sentence approved or deleted", "webhook", test_key="r12-2-verify")
    cfg, cfg_all = start(s, VERIFY)
    read = s.http("Read the draft", "GET", cfg("drafts_url") + "/drafts", query={"_wrap": "1", "week": "{{1.week}}"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    v = "out"
    code, inputs = rule(N8N.VERIFY_JS, {"Config": cfg_all, "Read the draft": "{{" + f"{s.ref('Read the draft')}.data" + "}}"},
                        event("verify", ("week", "sentence", "action", "by")), bodies={
        "week_q": "encodeURIComponent(out.week || '')",
        "patch_body": "JSON.stringify(out.patch)",
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {v}.week + ':' + {v}.version + ':sentence ' + {v}.n, "
                     f"decision: {v}.decision + ' by ' + {v}.by, rules: {{ sentence: {v}.n }} }})"),
        "preread_body": "JSON.stringify(out.preread)",
        "failed_body": exc("'verify'", "A verification or publication write failed; check the draft and pre-read"),
    })
    name = "Step 12: Rule: may this person decide this sentence?"
    s.flow.append(s.code(name, code, inputs))
    n = s.ref(name)
    out = lambda f: "{{" + f"{n}.result.{f}" + "}}"  # noqa: E731
    on_fail = lambda step: [s.exception(f"{step}: exception queue", out("failed_body")), s.ignore()]  # noqa: E731
    rec = s.http("Step 12: Record the decision", "PATCH", cfg("drafts_url") + "/drafts/" + out("week_q"), body=out("patch_body"),
                 parse=False, onerror=on_fail("Step 12: Record the decision"))
    rec["filter"] = s.when("this person may decide it", out("n"), "", "exist")  # anyone else, or a decided sentence, ends here
    s.flow.append(rec)
    s.flow.append(s.decision_log("Step 12: Log the decision", out("log_body")))
    pub = s.http("Step 12: Publish the verified briefing", "PUT", cfg("preread_url") + "/pre_reads/" + out("week_q"), body=out("preread_body"),
                 parse=False, onerror=on_fail("Step 12: Publish the verified briefing"))
    pub["filter"] = s.when("all sentences decided", out("complete"), "true")
    s.flow.append(pub)
    return s


def friday(trigger: str, schedule: str) -> Scenario:
    """Step 13: Friday 16:00 closes the week and asks the backup verifier; 16:45 publishes without a narrative."""
    s = Scenario(R, f"R12.2 Draft the weekly briefing narrative: {trigger.split(': ', 1)[1]}", "schedule", test_key=trigger, schedule=schedule)
    cfg, cfg_all = start(s, None)
    drafts = cfg("drafts_url") + "/drafts"
    at_four = trigger == FOUR
    read_name = "Read open drafts" if at_four else "Read drafts with the backup verifier"
    read = s.http(read_name, "GET", drafts, query={"_wrap": "1"} if at_four else {"_wrap": "1", "stage": "backup"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    bodies = {"week_q": "encodeURIComponent(out.week)",
              "failed_body": exc("'four'" if at_four else "'late'", "A verification or publication write failed; check the draft and pre-read")}
    if at_four:
        bodies.update(patch_body="JSON.stringify(out.patch)",
                      ask_body=(f"JSON.stringify({{ to: {CFG}.backup_verifier, subject: 'Verify the weekly narrative by 16:45', "
                                "text: 'Week ' + out.week + ': the narrative is not yet verified.' })"))
        js, name = N8N.FOUR_JS, "Step 13: Rule: not verified by 16:00"
    else:
        bodies.update(preread_body="JSON.stringify(out.preread)")
        js, name = N8N.LATE_JS, "Step 13: Rule: not verified by 16:45"
    code, inputs = n8n_rule(js, {"Config": cfg_all, read_name: "{{" + f"{s.ref(read_name)}.data" + "}}"}, many=True, bodies=bodies)
    s.flow.append(s.code(name, code, inputs))
    s.flow.append(s.iterator("Each draft", "{{" + f"{s.ref(name)}.result.items" + "}}"))
    it = s.ref("Each draft")
    f = lambda k: "{{" + f"{it}.{k}" + "}}"  # noqa: E731

    def write(step: str, method: str, url: str, body: str) -> dict:
        return s.http(step, method, url, body=body, parse=False, onerror=[s.exception(f"{step}: exception queue", f("failed_body")), s.ignore()])

    if at_four:
        s.flow.append(write("Step 13: Close the week to new drafts", "PATCH", drafts + "/" + f("week_q"), f("patch_body")))
        ask = write("Step 13: Ask the backup verifier", "POST", cfg("messaging_url") + "/messages", f("ask_body"))
        ask["filter"] = s.when("backup verifier needed", f("notify"), "true")
        s.flow.append(ask)
    else:
        s.flow.append(write("Step 11: Publish table and commentary, not verified", "PUT", cfg("preread_url") + "/pre_reads/" + f("week_q"),
                            f("preread_body")))
        s.flow.append(write("Step 13: Mark the draft not verified", "PATCH", drafts + "/" + f("week_q"), '{"stage": "not verified"}'))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R12.2/make/, scenario)."""
    return [("blueprint.json", draft(WRITTEN, "r12-2-table-written", "table version written", "written", ("version",), None)),
            ("friday-1400.blueprint.json", draft(FRI, FRI, "Friday 14:00", "friday", (), "every Friday at 14:00")),
            ("verify.blueprint.json", verify()),
            ("friday-1600.blueprint.json", friday(FOUR, "every Friday at 16:00")),
            ("friday-1645.blueprint.json", friday(LATE, "every Friday at 16:45"))]
