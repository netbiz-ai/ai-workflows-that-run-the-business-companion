"""R15.1 Draft campaign copy from approved product facts and check every claim, as Make scenarios.

Source: book Chapter 15, recipe R15.1, build steps 1 to 10, Table 15.1 and the failure table
(recipes/R15.1/build-spec.md); AI steps: recipes/R15.1/prompts/draft-copy.md (step 4) and
recipes/R15.1/prompts/list-claims.md (step 5, rerun by step 9). The rules are the n8n build's
own JavaScript (tools/builds/r15_1.py), run through n8n_rule.
Five scenarios, because a Make scenario has one trigger: Ben approves a brief (webhook,
blueprint.json, steps 1 to 8), a named approver signs (webhook, approver-signs.blueprint.json,
step 8), Ben approves a version (webhook, ben-approves.blueprint.json, step 9), the sending tool
checks a version before a send (webhook, before-send.blueprint.json, step 9) and each morning
(schedule, every day at 07:00, each-morning.blueprint.json, step 10). n8n's "Which trigger?"
switch only asked which trigger ran, so it is not built.

Where the Make build differs from the n8n canvas, and why:
- n8n's version loop (split in batches) becomes an iterator, one bundle per channel version.
  n8n loops back from "Retry the AI steps" and "Step 7: Redraft once" to "Step 4: Attempt"; a
  Make scenario cannot loop back, so a Repeater runs steps 4 to 7 up to four times for each
  version (the first try, two retries for a bad AI output and one redraft), one pass after
  another. A scenario variable holds the attempt's counters, read by "Step 4: Attempt" in place
  of n8n's Code node; each pass sets it to the next attempt's counters, or to "done" once step 7
  decides, and a pass that reads "done" does nothing.
- n8n's "Step 7: Rule: what next?" and "Version result" run inside the rule before them ("Step 4:
  Rule: tagged draft?" for a draft that failed, "Step 6: Rules: tags, listing and scan" otherwise),
  and "Step 4: AI error" and "Step 5: AI error" run inside those rules (on_ai_error), because Make
  branches never meet again; "Step 2: Back to Ben" runs inside the step 2 rule for the same reason.
  Each route repeats the version's closing steps, with the route in the step's name.
- n8n marks the key done once, after every version ("All versions"). Make's routes do not meet
  after the iterator, so each version marks the key done itself, and only while no write has
  marked it failed (the table API's status=neq.failed filter): a failed write still leaves the
  key failed, as n8n's "Any write failed?" does.
- n8n's Crypto nodes are Make's sha256() mapping over the same text, handed to the rule as the
  fingerprint node's answer, so no step is spent on them.
- The rules after n8n's IF nodes ("Record it?", "Tell someone?", "Ben may approve?", "Step 10:
  Hold it?") are routers; each route repeats the decision log.
- A failed write records "write failed" without the HTTP error text, which Make's error route
  does not hand to a later body.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R15.1"
N8N = n8n_build(R)
T1, T8, T9, TS, T10 = N8N.T1, N8N.T8, N8N.T9, N8N.TS, N8N.T10
VER, ATT, TAGGED, VR = N8N.VER, N8N.ATT, N8N.TAGGED, N8N.VR
STEP2, STEP3, STEP6 = "Step 2: Rule: claims current?", "Step 3: Load only those claims and prices", "Step 6: Rules: tags, listing and scan"
CALL4, CALL5 = "Step 4: AI call", "Step 5: AI call"
ATTEMPTS = 4  # the first try, two retries for a bad AI output, one redraft
CONFIG = {
    "briefs_url": "https://<your brief list API>",
    "claims_url": "https://<your claims list API>",
    "prices_url": "https://<your CRM price list API>",
    "style_sheet_url": "https://<your style sheet API>",
    "drafts_url": "https://<your drafts and claims report API>",
    "messaging_url": "https://<your messaging API>",
    "approvers": {"price": "<your price approver>", "time": "<your delivery and installation approver>",
                  "warranty": "<your warranty approver>", "comparison": "<your comparison approver>",
                  "environmental": "<your environmental claim approver>"},
    "final_approver": "<your campaign owner>",
    "ai_owner": "<your workflow builder>",
    "stand_in_namer": "<your workflow owner>",
    "signoff_wait_days": 2,
    "scan_words": ["free", "warranty", "guarantee", "best", "today", "tonight", "tomorrow", "day", "days", "week", "weeks",
                   "weekend", "month", "hour", "hours", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
    "prompt_version": "<your prompt version>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
# n8n's AI-error nodes ("Step 4: AI error", "Step 5: AI error" and "Step 9: Rerun AI error").
AI_ERROR_JS = ("return [{ json: { result: 'ai_error', problem: 'AI call failed after two retries: ' + "
               "(($json.error && $json.error.message) || 'no answer') } }];")
RERUN_AI_ERROR_JS = ("return [{ json: { problem: 'AI call failed after two retries: ' + "
                     "(($json.error && $json.error.message) || 'no answer') } }];")
CFG = "$('Config').first().json"
B1 = f"$('{T1}').first().json.body"
BRIEF = "$('Read the brief').first().json"
KEY = f"{B1}.brief_id + ':' + {BRIEF}.version"
V = f"$('{VER}').first().json"


def part(js: str) -> str:
    """One n8n Code node's JavaScript as a function of $json, for a Code step that runs several in turn."""
    return "(($json) => {\n" + js.strip() + "\n})"


def then(fn: str, node: str | None, js: str) -> str:
    """Prelude: fn(out) runs a later n8n node's JavaScript on this rule's result (once), with
    $(node) answering that result, as the n8n node after this one reads it."""
    give = f"DATA[{json.dumps(node)}] = [{{ json: out }}], " if node else ""
    return (f"let __{fn}_done;\n"
            f"const {fn} = (out) => __{fn}_done || (__{fn}_done = ({give}one({part(js)}(out))[0] || {{}}));\n")


# Step 7 and "Version result" after a rule that may decide the attempt: the next attempt's counters
# (n8n's "Retry the AI steps" and "Step 7: Redraft once"), or "done" and the version's closing bodies.
CONCLUDE_JS = then("__next", None, N8N.NEXT_JS) + then("__result", None, N8N.VR_JS) + r"""
let __closing;
const __close = (out) => __closing || (__closing = (() => {
  const n = __next(out);
  if (n.route === 'retry') return { route: n.route, attempt: JSON.stringify({ redrafts: n.redrafts, bad_outputs: n.bad_outputs + 1 }) };
  if (n.route === 'redraft') return { route: n.route, attempt: JSON.stringify({ redrafts: n.redrafts + 1, bad_outputs: n.bad_outputs }) };
  const r = __result(n);
  const cfg = $('Config').first().json, v = $('Version').first().json;
  return { route: n.route, attempt: 'done', stored: r.version !== null, version_id_q: encodeURIComponent(v.version_id),
    version_body: JSON.stringify(r.version), report_body: JSON.stringify(r.report), message_body: JSON.stringify(r.message),
    exception_body: r.exception ? JSON.stringify({ recipe: 'R15.1', item: v.version_id, reason: 'AI error', detail: r.exception.detail, owner: cfg.ai_owner }) : '',
    log_body: JSON.stringify({ recipe: 'R15.1', item: v.version_id, decision: r.decision, rules: r.rules }),
    failed_body: JSON.stringify({ recipe: 'R15.1', item: v.version_id, reason: 'write failed',
      detail: 'Draft, claims report or message write failed; never retried', owner: cfg.ai_owner }) };
})());
"""
CLOSE_FIELDS = ("route", "attempt", "stored", "version_id_q", "version_body", "report_body", "message_body",
                "exception_body", "log_body", "failed_body")




def rule(js: str, sources: dict[str, str], trigger: str | None = None, fields: tuple[str, ...] = (), prelude: str = "", **kw):
    """n8n_rule, plus the webhook's fields as n8n gives them ($('Trigger').first().json.body).
    A Make mapping cannot pass the whole webhook bundle, so each field is its own input."""
    if not trigger:
        return n8n_rule(js, sources, prelude=prelude, **kw)
    inputs = {f"t_{f}": "{{1." + f + "}}" for f in fields}
    body = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in fields)
    pre = (f"// The webhook's fields, as the rule reads them in n8n: $('{trigger}').first().json.body.\n"
           f"DATA[{json.dumps(trigger)}] = [{{ json: {{ body: {{ {body} }} }} }}];\n")
    code, rest = n8n_rule(js, sources, prelude=pre + prelude, **kw)
    return code, {**inputs, **rest}


def start(s: Scenario, trigger: str | None):
    """The trigger, Config and the stop flag; returns (cfg(field), the whole Config, data(step), out(step, field))."""
    if trigger:
        s.flow.append(s.webhook(trigger))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    s.flow += s.stop_flag()
    return ((lambda f: "{{" + f"{c}.result.{f}" + "}}"), "{{" + f"{c}.result" + "}}",
            (lambda n: "{{" + f"{s.ref(n)}.data" + "}}"), (lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"))


def write_failed_bodies(item: str) -> dict[str, str]:
    """n8n's "Write failed" and its exception row, for a write outside the version loop."""
    return {"failed_body": (f"JSON.stringify({{ recipe: '{R}', item: String({item}), reason: 'write failed', "
                            f"detail: 'write failed; never retried', owner: {CFG}.ai_owner }})")}


def on_fail(s: Scenario, step: str, body: str) -> list[dict]:
    """The error route of a write outside the version loop: the exception row, then the Skip handler."""
    return [s.exception(f"{step}: exception queue", body), s.ignore()]


def brief() -> Scenario:
    """Steps 1 to 8 for a brief Ben marks approved: the claims check, then each channel version."""
    s = Scenario(R, "R15.1 Draft campaign copy and check every claim: brief approved", "webhook", test_key="r15-1-brief-approved")
    cfg, conf, data, out = start(s, T1)
    trig = {"trigger": T1, "fields": ("brief_id",)}

    # ---- steps 1 and 2: the brief, the duplicate check, the claims ------------------------------------
    read = s.http("Read the brief", "GET", cfg("briefs_url") + "/briefs/{{encodeURL(1.brief_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    s.flow.append(s.reserve_key("Reserve key", "{{1.brief_id}}:{{" + f"{s.ref('Read the brief')}.data.version" + "}}"))
    claims = s.http("Read the claims list", "GET", cfg("claims_url") + "/claims", query={"_wrap": "1"})
    claims["filter"] = s.is_new_key("Reserve key")  # a copy stops here: this brief version was drafted before
    s.flow.append(claims)
    s.flow.append(s.http("Read the price list", "GET", cfg("prices_url") + "/prices", query={"_wrap": "1"}))
    reads = {"Config": conf, "Read the brief": data("Read the brief"), "Read the claims list": data("Read the claims list"),
             "Read the price list": data("Read the price list")}
    code, inputs = rule(N8N.STEP2_JS, reads, **trig, prelude=then("__back", STEP2, N8N.BACK_JS), bodies={
        "key_q": f"encodeURIComponent({KEY})",
        "report_body": "out.ok ? '' : JSON.stringify(__back(out).report)",
        "message_body": "out.ok ? '' : JSON.stringify(__back(out).message)",
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {B1}.brief_id, decision: 'returned to Ben: claims not current', "
                     "rules: { problems: out.problems } })"),
        "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: {B1}.brief_id, reason: 'write failed', "
                        f"detail: 'Claims report or message to Ben failed; never retried', owner: {CFG}.ai_owner }})"),
    })
    s.flow.append(s.code(STEP2, code, inputs))
    key_q = out(STEP2, "key_q")

    def step2_write(step: str, url: str, body: str) -> dict:
        return s.http(step, "POST", url, body=body, parse=False, onerror=s.write_failed(step, key_q, out(STEP2, "failed_body")))

    back = [step2_write("Step 2: Claims report", cfg("drafts_url") + "/report", out(STEP2, "report_body")),
            step2_write("Step 2: Tell Ben", cfg("messaging_url") + "/messages", out(STEP2, "message_body")),
            s.finish_key("Step 2: Mark key done", key_q, '{"status": "done", "result": "returned to Ben"}'),
            s.decision_log("Step 2: Decision log", out(STEP2, "log_body"))]

    # ---- step 3: only those claims and prices, one bundle per channel version ---------------------------
    style = s.http("Step 3: Read the style sheet", "GET", cfg("style_sheet_url"))
    code, inputs = n8n_rule(N8N.VERSIONS_JS, {**reads, "Step 3: Read the style sheet": data("Step 3: Read the style sheet")},
                            many=True, bodies={"as_json": "JSON.stringify(out)"})
    versions = s.code(STEP3, code, inputs)
    each = s.iterator(N8N.LOOP, out(STEP3, "items"))
    version = "{{" + f"{s.ref(N8N.LOOP)}.as_json" + "}}"
    first = s.set_var("Version: first attempt", "attempt", '{"redrafts": 0, "bad_outputs": 0}')
    passes = s.repeater("Steps 4 to 7: Up to four attempts", str(ATTEMPTS))
    attempt = s.get_var(ATT, "attempt")
    att = "{{" + f"{s.ref(ATT)}.attempt" + "}}"
    base = {"Config": conf, VER: version, ATT: att}

    # ---- step 4: draft from the claims list only -------------------------------------------------------
    vars4 = (f"{{ channel: {V}.channel, claims: {V}.claims.map(c => `${{c.id}} | ${{c.wording}} | ${{c.types.join(', ')}}`).join('\\n'), "
             f"price_rows: {V}.prices.map(p => `${{p.id}} | ${{p.product}} | ${{p.price}}`).join('\\n') || '(none)', style_sheet: {V}.style }}")
    ai4 = s.ai_step("Step 4", ROOT / "recipes/R15.1/prompts/draft-copy.md", vars4, {"Config": conf, VER: version}, max_tokens=4096, tries=3)
    ai4[0]["filter"] = s.when("not decided yet", att, "done", "text:notequal")  # a pass after step 7 decided does nothing
    close_bodies = {f: f"__close(out).{f}" for f in CLOSE_FIELDS}
    code, inputs = n8n_rule(N8N.TAGGED_JS, {**base, CALL4: "{{" + f"{s.ref(CALL4)}.data" + "}}"},
                            ai_status="{{" + f"{s.ref(CALL4)}.statusCode" + "}}", on_ai_error=AI_ERROR_JS,
                            prelude=CONCLUDE_JS, bodies={
        "as_json": "JSON.stringify(out)",
        **{f: f"out.result === 'drafted' ? '' : __close(out).{f}" for f in CLOSE_FIELDS},
    })
    tagged = s.code(TAGGED, code, inputs)

    def closing(tag: str, src: str) -> list[dict]:
        """"Version result"'s writes: the version (when there is one), the claims report, the exception
        row for an AI error, the message, the decision log, then the key."""
        o = lambda f: out(src, f)  # noqa: E731
        failed = lambda step: s.write_failed(step, key_q, o("failed_body"))  # noqa: E731

        def write(step: str, method: str, url: str, body: str) -> dict:
            return s.http(f"{step} ({tag})", method, url, body=body, parse=False, onerror=failed(f"{step} ({tag})"))
        stored = tag == "version"
        flow = [write("Store the version", "PUT", cfg("drafts_url") + "/versions/" + o("version_id_q"), o("version_body"))] if stored else []
        flow.append(write("Claims report", "POST", cfg("drafts_url") + "/report", o("report_body")))
        if not stored:
            flow.append(s.exception(f"Exception queue: AI error ({tag})", o("exception_body")))
        flow += [write("Tell the approvers, Ben or Owen", "POST", cfg("messaging_url") + "/messages", o("message_body")),
                 s.decision_log(f"Decision log: version ({tag})", o("log_body")),
                 s.finish_key(f"Mark key done ({tag})", key_q + "&status=neq.failed", '{"status": "done", "result": "drafted"}')]
        return flow

    def decided(src: str, stored: str | None = None) -> dict:
        conds = [{"a": out(src, "attempt"), "b": "done", "o": "text:equal"}]
        if stored:
            conds.append({"a": out(src, "stored"), "b": "true", "o": "text:equal" if stored == "yes" else "text:notequal"})
        return {"name": "step 7 decided" + (f", {'a version' if stored == 'yes' else 'no version'}" if stored else ""),
                "conditions": [conds]}

    # ---- steps 5 and 6: list the claims in the untagged copy; the rules check every one ----------------
    ai5 = s.ai_step("Step 5", ROOT / "recipes/R15.1/prompts/list-claims.md", f"{{ untagged_copy: $('{TAGGED}').first().json.untagged }}",
                    {"Config": conf, TAGGED: out(TAGGED, "as_json")}, max_tokens=4096, tries=3)
    code, inputs = n8n_rule(N8N.STEP6_JS, {**base, TAGGED: out(TAGGED, "as_json"), CALL5: "{{" + f"{s.ref(CALL5)}.data" + "}}"},
                            ai_status="{{" + f"{s.ref(CALL5)}.statusCode" + "}}", on_ai_error=AI_ERROR_JS,
                            prelude=CONCLUDE_JS, bodies=close_bodies)
    step6 = s.code(STEP6, code, inputs)
    checked = ai5 + [step6, s.set_var("Step 7: Next attempt (after step 6)", "attempt", out(STEP6, "attempt")),
                     s.router("Store a version?", [(decided(STEP6, "yes"), closing("version", STEP6)),
                                                   (decided(STEP6, "no"), closing("AI error after step 5", STEP6))])]
    not_drafted = [s.set_var("Step 7: Next attempt (after step 4)", "attempt", out(TAGGED, "attempt"))]
    not_drafted += closing("AI error after step 4", TAGGED)
    not_drafted[1]["filter"] = decided(TAGGED)
    drafted = out(TAGGED, "result")
    loop = [style, versions, each, first, passes, attempt] + ai4 + [tagged, s.router("Drafted?", [
        (s.when("drafted", drafted, "drafted"), checked),
        (s.when("no draft", drafted, "drafted", "text:notequal"), not_drafted),
    ])]
    ok = out(STEP2, "ok")
    s.flow.append(s.router("Claims current?", [(s.when("claims current", ok, "true"), loop),
                                               (s.when("claims not current", ok, "true", "text:notequal"), back)]))
    return s


def tail(s: Scenario, prefix: str, cfg, src: str, out, *, record: bool | None = None, after_message: list[dict] = ()) -> list[dict]:
    """n8n's tail(): the version's update, the message when there is one, then the decision log.
    record: the rule's "record" answer decides whether the version is updated (n8n's "Record it?")."""
    o = lambda f: out(src, f)  # noqa: E731
    fail = o("failed_body")
    log = lambda tag: s.decision_log(f"{prefix}: Decision log ({tag})", o("log_body"))  # noqa: E731
    update = s.http(f"{prefix}: Update the version", "PATCH", cfg("drafts_url") + "/versions/" + o("id_q"), body=o("patch_body"),
                    parse=False, onerror=on_fail(s, f"{prefix}: Update the version", fail))
    message = s.http(f"{prefix}: Message", "POST", cfg("messaging_url") + "/messages", body=o("message_body"), parse=False,
                     onerror=on_fail(s, f"{prefix}: Message", fail))
    has = o("has_message")
    flow = [update, s.router(f"{prefix}: Tell someone?", [
        (s.when("a message", has, "true"), [message, log("message"), *after_message]),
        (s.when("no message", has, "true", "text:notequal"), [log("no message")]),
    ])]
    if record is None:
        return flow
    return [s.router(f"{prefix}: Record it?", [(s.when("record it", o("record"), "true"), flow),
                                               (s.when("not recorded", o("record"), "true", "text:notequal"), [log("not recorded")])])]


def tail_bodies(item: str) -> dict[str, str]:
    return {"id_q": "encodeURIComponent(out.version_id)", "patch_body": "JSON.stringify(out.body)",
            "has_message": "!!out.message", "message_body": "out.message ? JSON.stringify(out.message) : ''",
            "log_body": f"JSON.stringify({{ recipe: '{R}', item: out.version_id, decision: out.decision, rules: {{}} }})",
            **write_failed_bodies(item)}


def version_read(s: Scenario, cfg, name: str) -> dict:
    read = s.http(name, "GET", cfg("drafts_url") + "/versions/{{encodeURL(1.version_id)}}")
    read["filter"] = s.continue_unless_stopped()
    return read


def approver_signs() -> Scenario:
    """Step 8: a named approver signs or strikes; when every one has signed, Ben is asked."""
    s = Scenario(R, "R15.1 Draft campaign copy and check every claim: approver signs", "webhook", test_key="r15-1-sign")
    cfg, conf, data, out = start(s, T8)
    s.flow.append(version_read(s, cfg, "Read the version to sign"))
    name = "Step 8: Rule: record the sign-off"
    code, inputs = rule(N8N.SIGN_JS, {"Config": conf, "Read the version to sign": data("Read the version to sign")},
                        T8, ("version_id", "approver", "decision"), bodies=tail_bodies(f"$('{T8}').first().json.body.version_id"))
    s.flow.append(s.code(name, code, inputs))
    s.flow += tail(s, "Step 8", cfg, name, out, record=True)
    return s


def ben_approves() -> Scenario:
    """Step 9: Ben approves a version every named approver signed; the text is stored with its fingerprint."""
    s = Scenario(R, "R15.1 Draft campaign copy and check every claim: Ben approves", "webhook", test_key="r15-1-ben-approves")
    cfg, conf, data, out = start(s, T9)
    read = "Read the version Ben approves"
    s.flow.append(version_read(s, cfg, read))
    fp = "Step 9: Fingerprint the approved text"
    name = "Step 9: Rule: every approver signed?"
    code, inputs = rule(N8N.BEN_JS, {"Config": conf, fp: '{"fingerprint": "{{sha256(' + f"{s.ref(read)}.data.text" + ')}}"}',
                                     read: data(read)}, T9, ("version_id",), bodies={
        "id_q": "encodeURIComponent(out.version_id)",
        "store_body": (f"JSON.stringify({{ status: 'approved; ready to send', fingerprint: $('{fp}').first().json.fingerprint, "
                       "approved_at: new Date().toISOString() })"),
        "report_body": (f"JSON.stringify({{ version_id: out.version_id, step: 9, result: 'approved by Ben', "
                        f"fingerprint: $('{fp}').first().json.fingerprint, approvals: $('{read}').first().json.approvals, "
                        "at: new Date().toISOString() })"),
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: out.version_id, decision: out.decision, rules: {{}} }})",
        **write_failed_bodies(f"$('{T9}').first().json.body.version_id"),
    })
    s.flow.append(s.code(name, code, inputs))
    o = lambda f: out(name, f)  # noqa: E731
    fail = o("failed_body")
    store = s.http("Step 9: Store the approved text", "PATCH", cfg("drafts_url") + "/versions/" + o("id_q"), body=o("store_body"),
                   parse=False, onerror=on_fail(s, "Step 9: Store the approved text", fail))
    report = s.http("Step 9: Claims report", "POST", cfg("drafts_url") + "/report", body=o("report_body"), parse=False,
                    onerror=on_fail(s, "Step 9: Claims report", fail))
    s.flow.append(s.router("Ben may approve?", [
        (s.when("every approver signed", o("ok"), "true"), [store, report, s.decision_log("Step 9: Decision log (approved)", o("log_body"))]),
        (s.when("not ready for Ben", o("ok"), "true", "text:notequal"), [s.decision_log("Step 9: Decision log (not approved)", o("log_body"))]),
    ]))
    return s


def before_send() -> Scenario:
    """Step 9: before a send, a changed fingerprint stops it and reruns steps 5 and 6 on the new text."""
    s = Scenario(R, "R15.1 Draft campaign copy and check every claim: before a send", "webhook", test_key="r15-1-before-send")
    cfg, conf, data, out = start(s, TS)
    read = "Read the version to send"
    s.flow.append(version_read(s, cfg, read))
    fp = "Step 9: Fingerprint the text to send"
    name = "Step 9: Rule: same fingerprint?"
    trig = (TS, ("version_id", "text"))
    code, inputs = rule(N8N.SEND_JS, {"Config": conf, read: data(read), fp: '{"fingerprint": "{{sha256(1.text)}}"}'}, *trig, bodies={
        **tail_bodies(f"$('{TS}').first().json.body.version_id"),
        "changed": "out.route === 'changed'",
        "trigger_json": f"JSON.stringify($('{TS}').first().json)",
    })
    s.flow.append(s.code(name, code, inputs))
    sent = {"Config": conf, read: data(read), TS: out(name, "trigger_json")}

    # ---- steps 5 and 6 again, on the changed text ------------------------------------------------------
    step = "Step 9: Rerun step 5"
    ai = s.ai_step(step, ROOT / "recipes/R15.1/prompts/list-claims.md", f"{{ untagged_copy: $('{TS}').first().json.body.text }}",
                   sent, max_tokens=4096, tries=3)
    ai[0]["filter"] = s.when("text changed", out(name, "changed"), "true")
    rc = "Step 9: Rerun step 6"
    call = s.ref(f"{step}: AI call")
    vid = f"$('{TS}').first().json.body.version_id"
    code, inputs = n8n_rule(N8N.RECHECK_JS, {**sent, f"{step}: AI call": "{{" + f"{call}.data" + "}}"},
                            ai_status="{{" + f"{call}.statusCode" + "}}", on_ai_error=RERUN_AI_ERROR_JS, bodies={
        **tail_bodies(vid),
        "done": "out.route === 'done'",
        "report_body": "out.report ? JSON.stringify(out.report) : ''",
        "exception_body": (f"JSON.stringify({{ recipe: '{R}', item: {vid}, reason: 'AI error', "
                           f"detail: 'Send check rerun: ' + out.problem + '; the send stays stopped', owner: {CFG}.ai_owner }})"),
        "owen_body": (f"JSON.stringify({{ to: [{CFG}.ai_owner], subject: 'Send check for ' + {vid} + ': AI step failed', "
                      "text: out.problem + '. The send stays stopped.' })"),
    })
    recheck = s.code(rc, code, inputs)
    o = lambda f: out(rc, f)  # noqa: E731
    fail = o("failed_body")

    def write(step_: str, method: str, url: str, body: str) -> dict:
        return s.http(step_, method, url, body=body, parse=False, onerror=on_fail(s, step_, fail))
    checked = [write("Rerun: Claims report", "POST", cfg("drafts_url") + "/report", o("report_body")),
               write("Rerun: Update the version", "PATCH", cfg("drafts_url") + "/versions/" + o("id_q"), o("patch_body")),
               write("Rerun: Message", "POST", cfg("messaging_url") + "/messages", o("message_body")),
               s.decision_log("Rerun: Decision log", o("log_body"))]
    failed = [s.exception("Exception queue: rerun AI error", o("exception_body")),
              write("Rerun: Tell Owen", "POST", cfg("messaging_url") + "/messages", o("owen_body"))]
    rerun = ai + [recheck, s.router("Rerun checked?", [(s.when("checked", o("done"), "true"), checked),
                                                       (s.when("AI error or bad output", o("done"), "true", "text:notequal"), failed)])]
    s.flow += tail(s, "Send check", cfg, name, out, after_message=rerun)
    return s


def each_morning() -> Scenario:
    """Step 10: a changed source or price holds the claim's unsent versions; a sign-off open two days goes to a person."""
    s = Scenario(R, "R15.1 Draft campaign copy and check every claim: each morning", "schedule", test_key=T10,
                     schedule="every day at 07:00")
    cfg, conf, data, out = start(s, None)
    reads = [("Step 10: Read the versions", cfg("drafts_url") + "/versions"), ("Step 10: Read the claims list", cfg("claims_url") + "/claims"),
             ("Step 10: Read the price list", cfg("prices_url") + "/prices")]
    for i, (n, url) in enumerate(reads):
        m = s.http(n, "GET", url, query={"_wrap": "1"})
        if i == 0:
            m["filter"] = s.continue_unless_stopped()
        s.flow.append(m)
    name = "Step 10: Rule: changed sources and open sign-offs"
    code, inputs = n8n_rule(N8N.MORNING_JS, {"Config": conf, **{n: data(n) for n, _ in reads}}, many=True,
                            bodies={**tail_bodies("'morning run'"), "hold": "out.hold"})
    s.flow.append(s.code(name, code, inputs))
    each = "Step 10: Each version to hold or chase"
    s.flow.append(s.iterator(each, out(name, "items")))
    it = s.ref(each)
    f = lambda k: "{{" + f"{it}.{k}" + "}}"  # noqa: E731

    def write(step: str, method: str, url: str, body: str) -> dict:
        return s.http(step, method, url, body=body, parse=False, onerror=on_fail(s, step, f("failed_body")))
    tell = lambda tag: write(f"Step 10: Tell Ben or Helen ({tag})", "POST", cfg("messaging_url") + "/messages", f("message_body"))  # noqa: E731
    log = lambda tag: s.decision_log(f"Step 10: Decision log ({tag})", f("log_body"))  # noqa: E731
    s.flow.append(s.router("Step 10: Hold it?", [
        (s.when("hold it", f("hold"), "true"),
         [write("Step 10: Hold the unsent version", "PATCH", cfg("drafts_url") + "/versions/" + f("id_q"), f("patch_body")),
          tell("held"), log("held")]),
        (s.when("sign-off open", f("hold"), "true", "text:notequal"), [tell("sign-off open"), log("sign-off open")]),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R15.1/make/, scenario)."""
    return [("blueprint.json", brief()), ("approver-signs.blueprint.json", approver_signs()),
            ("ben-approves.blueprint.json", ben_approves()), ("before-send.blueprint.json", before_send()),
            ("each-morning.blueprint.json", each_morning())]
