"""R15.3 Keep consent and unsubscribes in sync across every list, as Make scenarios: rules only, no AI step.

Source: book Chapter 15, recipe R15.3, build steps 1 to 8 (recipes/R15.3/build-spec.md).
The rules are the n8n build's own JavaScript (tools/builds/r15_3.py), run through n8n_rule.
Five scenarios, because a Make scenario has one trigger: one per consent event (unsubscribe,
opt-in, POS sign-up, helpdesk opt-out tag; webhooks) and the nightly correction (schedule,
every day at 02:00, step 8).

Where Make differs from the n8n canvas, and why:
- Make's webhook step has no "body" wrapper, so the Consent event step receives the body's
  fields one by one and gives the rule the body it reads.
- n8n joins the CRM update and the CRM add back into one path before step 6. Make's routes never
  meet again, so the router runs them in order and the step 6 route starts by reading the key
  log: only an event whose master write marked its key done goes on to the other lists.
- n8n joins five failure outputs (each list read, the list write, the read-back, a read-back that
  differs) into step 7. In Make each would need its own copy of step 7, so step 6's list calls keep
  an HTTP error as their answer (stopOnHttpError off, no retry) and the rule steps send the list
  to step 7 from the status: "list unreachable" from the two finds, "did not confirm" from the
  write and read-back. A list write that fails is still never retried; its read-back runs and
  cannot confirm. Step 7 is built twice, once for each of those two routes.
- The n8n rules that read $('...').itemMatching(i) run once per list here, so a small shim
  answers itemMatching with the list's own item.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R15.3"
N8N = n8n_build(R)
EV, RULES, LISTS, RECS = N8N.EV, N8N.RULES, N8N.LISTS, N8N.RECS
CONFIG = {
    "crm_url": "https://<your CRM API>",
    "lists": [{"name": "<list name>", "url": "https://<its API>", "channel": "<the channel it sends>"}],
    "marketing_channels": ["email", "<your other marketing channels>"],
    "send_status_url": "https://<your send-status record API>",
    "messaging_url": "https://<your messaging API>",
    "consent_owner": "<your systems owner>",
}
CFG = "$('Config').first().json"
E = f"$('{EV}').first().json"
RU = f"$('{RULES}').first().json"
FIELDS = ("event_id", "email", "phone", "channel", "occurred_at", "wording_version")
# Each rule here runs once per list, so the list's own item is the one any index matches.
ITEM_MATCHING = ("Object.defineProperty(Object.prototype, 'itemMatching', "
                 "{ value: function (i) { return this.all()[i] || this.all()[0]; }, configurable: true });")

# The bodies a list item carries into step 6's calls and step 7 (out: one list item, after the rule).
LIST_BODIES = {
    "self": "JSON.stringify(out)",
    "path": "out.problem ? 'did not confirm' : out.record_id === null ? 'not on the list' : 'on the list'",
    "record_q": "encodeURIComponent(out.record_id || '')",
    "list_q": "encodeURIComponent(out.list || '')",
    "apply_body": "JSON.stringify({ marketing_opt_out: out.opt_out })",
    "suppress_body": f"JSON.stringify({{ email: {RU}.email, phone: {RU}.phone, event_id: {E}.event_id, reason: 'marketing opt-out' }})",
    "pause_body": f"JSON.stringify({{ status: 'paused', since: new Date().toISOString(), reason: 'opt-out not confirmed: ' + out.problem, event_id: {E}.event_id }})",
    "log_body": f"JSON.stringify({{ recipe: '{R}', item: {E}.event_id, decision: out.list + ': ' + out.outcome, "
                "rules: { list: out.list, record: out.record_id, opt_out: out.opt_out } })",
}
# Step 7's closing bodies, once the action is known (out: the list item with its action).
ACTION_BODIES = {
    "exception_body": f"JSON.stringify({{ recipe: '{R}', item: {E}.event_id, reason: 'list did not confirm', "
                      f"detail: out.list + ': ' + out.problem + '; ' + out.action, owner: {CFG}.consent_owner }})",
    "message": f"JSON.stringify({{ to: {CFG}.consent_owner, subject: 'Consent change not confirmed on ' + out.list, text: out.problem + '; ' + out.action }})",
    "log_body": f"JSON.stringify({{ recipe: '{R}', item: {E}.event_id, decision: out.list + ': not confirmed; ' + out.action, "
                "rules: { list: out.list, record: out.record_id, problem: out.problem } })",
}


def first_of(cond: str, a: tuple[str, dict], b: tuple[str, dict]) -> tuple[str, dict]:
    """One Code step that runs rule a when cond holds, else rule b.
    Each rule is a whole n8n_rule step body, run in its own function so their names never meet."""
    inputs = dict(b[1])
    for k, v in a[1].items():
        if inputs.get(k, v) != v:
            raise ValueError(f"input {k} differs between the two rules")
        inputs[k] = v
    code = (f"// Two n8n Code nodes in one step: the first when {cond.strip()}, else the second.\n"
            f"if ({cond}) return (() => {{\n{a[0]}\n}})();\n"
            f"return (() => {{\n{b[0]}\n}})();")
    return code, inputs


def step7(s: Scenario, tag: str, item, cfg) -> list[dict]:
    """Step 7 for a list that did not confirm. item(field) maps one field of the list item."""
    def leaf(name: str, action: str) -> list[dict]:
        q = "$('Step 7: An opt-out?').item.json"
        js = f"return {{ json: Object.assign({{}}, {q}, {{ action: {json.dumps(action)} }}) }};"
        code, inputs = n8n_rule(js, {"Config": "{{" + f"{s.ref('Config')}.result" + "}}", EV: "{{" + f"{s.ref(EV)}.result" + "}}",
                                     "Step 7: An opt-out?": item("self")}, bodies=ACTION_BODIES)
        step = s.code(f"{name} ({tag})", code, inputs)
        out = lambda f: "{{" + f"{s.ref(f'{name} ({tag})')}.result.{f}" + "}}"  # noqa: E731
        label = f"{name.replace('Step 7: ', '').lower()}, {tag}"
        return [step,
                s.exception(f"Exception queue: list did not confirm ({label})", out("exception_body")),
                s.http(f"Step 7: Tell Owen ({label})", "POST", cfg("messaging_url") + "/messages", body=out("message"), parse=False),
                s.decision_log(f"Step 7: Decision log ({label})", out("log_body"))]

    # The list's own suppression, which overrides its subscription flag; never retried. If it fails,
    # the send-status record Ben checks before every marketing send marks the list paused; Owen lifts it.
    paused = s.http(f"Step 7: Mark the list paused ({tag})", "PUT", cfg("send_status_url") + "/lists/" + item("list_q"),
                    body=item("pause_body"), parse=False,
                    onerror=leaf("Step 7: Pause failed", "suppression and pause both failed; pause the list by hand") + [s.ignore()])
    suppress = s.http(f"Step 7: Suppress the person on the list ({tag})", "POST", item("url") + "/suppressions",
                      body=item("suppress_body"), parse=False,
                      onerror=[paused] + leaf("Step 7: Paused", "list paused") + [s.ignore()])
    return [s.router(f"Step 7: An opt-out? ({tag})", [
        (s.when("an opt-out", item("opt_out"), "true"), [suppress] + leaf("Step 7: Suppressed", "suppressed on the list")),
        (s.when("an opt-in", item("opt_out"), "true", "text:notequal"),
         leaf("Step 7: Opt-in not confirmed", "opt-in not on this list yet; the nightly check corrects it")),
    ])]


def list_call(s: Scenario, name: str, method: str, url: str, **kw) -> dict:
    """A step 6 list call whose HTTP error is an answer the rules read (no retry, no error route)."""
    m = s.http(name, method, url, onerror=[], **kw)
    m["mapper"]["stopOnHttpError"] = False
    return m


def consent_event(trigger: str, path: str) -> Scenario:
    title = trigger.replace("Step 1: ", "")
    s = Scenario(R, f"R15.3 Keep consent in sync: {title.lower()}" if path != "r15-3-unsubscribe"
                 else "R15.3 Keep consent and unsubscribes in sync across every list", "webhook", test_key=path)
    s.flow.append(s.webhook(trigger))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    conf = "{{" + f"{c}.result" + "}}"
    s.flow += s.stop_flag()

    # Step 1: the webhook's fields, given to the rule as the n8n webhook's body.
    body = ", ".join(f"{f}: input.ev_{f}" for f in FIELDS)
    code, inputs = n8n_rule(N8N.EVENT_JS, {"Config": conf}, executed=(trigger,),
                            prelude=f"DATA[{json.dumps(trigger)}] = [{{ json: {{ body: {{ {body} }} }} }}];",
                            bodies={"reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: out.event_id }})",
                                    "key_q": "encodeURIComponent(out.event_id)"})
    inputs.update({f"ev_{f}": "{{1." + f + "}}" for f in FIELDS})
    ev = s.code(EV, code, inputs)
    ev["filter"] = s.continue_unless_stopped()
    s.flow.append(ev)
    e = lambda f: "{{" + f"{s.ref(EV)}.result.{f}" + "}}"  # noqa: E731
    s.flow.append(s.rpc("Step 2: Reserve key", "reserve_key", e("reserve_body")))
    by_email = s.http("Read the master by email", "GET", cfg("crm_url") + "/contacts", query={"_wrap": "1", "email": e("email")})
    by_email["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: this event was applied before
    s.flow += [by_email, s.http("Read the master by phone", "GET", cfg("crm_url") + "/contacts", query={"_wrap": "1", "phone": e("phone")})]

    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    code, inputs = n8n_rule(N8N.RULES_JS, {
        "Config": conf, EV: "{{" + f"{s.ref(EV)}.result" + "}}",
        "Read the master by email": data("Read the master by email"), "Read the master by phone": data("Read the master by phone"),
    }, bodies={
        "path": "!out.apply ? 'ignored' : out.contact_id !== null ? 'in the master' : 'new to the master'",
        "contact_q": "encodeURIComponent(out.contact_id || '')",
        "master_body": "JSON.stringify({ consent: out.consent })",
        "add_body": f"JSON.stringify({{ email: {E}.email, phone: {E}.phone, consent: out.consent }})",
        "done_body": "JSON.stringify({ status: 'done', result: out.reason })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: {E}.event_id, decision: 'master: ' + out.reason, "
                    f"rules: {{ source: {E}.source, channels: out.channels }} }})",
        "ignored_done_body": "JSON.stringify({ status: 'done', result: 'ignored: ' + out.reason })",
        "ignored_log_body": f"JSON.stringify({{ recipe: '{R}', item: {E}.event_id, decision: 'ignored: ' + out.reason, "
                            f"rules: {{ source: {E}.source, kind: {E}.kind }} }})",
        "failed_body": f"JSON.stringify({{ recipe: '{R}', item: {E}.event_id, reason: 'write failed', "
                       f"detail: 'Master consent write failed; no list was changed; apply it by hand, never retried', owner: {CFG}.consent_owner }})",
        "failed_message": f"JSON.stringify({{ to: {CFG}.consent_owner, subject: 'Consent event ' + {E}.event_id + ' not applied', "
                          "text: 'The master consent write failed; no list was changed.' })",
    })
    s.flow.append(s.code(RULES, code, inputs))
    ru = s.ref(RULES)
    r = lambda f: "{{" + f"{ru}.result.{f}" + "}}"  # noqa: E731
    key_q = e("key_q")

    def master_failed(step: str) -> list[dict]:
        # No list is changed; Owen applies it by hand.
        return [s.finish_key(f"{step}: mark key failed", key_q, '{"status": "failed", "result": "master write failed"}'),
                s.exception(f"{step}: exception queue", r("failed_body")),
                s.http(f"{step}: tell Owen", "POST", cfg("messaging_url") + "/messages", body=r("failed_message"), parse=False),
                s.ignore()]

    def master(tag: str, name: str, method: str, url: str, body: str) -> list[dict]:
        # Step 5: the master consent record, every channel in scope. A write: never retried.
        return [s.http(name, method, url, body=body, parse=False, onerror=master_failed(name)),
                s.finish_key(f"Mark key done ({tag})", key_q, r("done_body")),
                s.decision_log(f"Step 5: Decision log ({tag})", r("log_body"))]

    lists = step6(s, cfg, key_q)
    s.flow.append(s.router("Apply it?", [
        (s.when("ignored", r("path"), "ignored"),
         [s.finish_key("Mark ignored event done", key_q, r("ignored_done_body")),
          s.decision_log("Steps 3 and 4: Decision log", r("ignored_log_body"))]),
        (s.when("in the master already", r("path"), "in the master"),
         master("in the master", "Step 5: Write the change to the CRM", "PATCH", cfg("crm_url") + "/contacts/" + r("contact_q"), r("master_body"))),
        (s.when("new to the master", r("path"), "new to the master"),
         master("added", "Step 5: Add the person to the CRM", "POST", cfg("crm_url") + "/contacts", r("add_body"))),
        (s.when("applied", r("path"), "ignored", "text:notequal"), lists),
    ]))
    return s


def step6(s: Scenario, cfg, key_q: str) -> list[dict]:
    """Step 6, after the master write: every other list in scope, each change read back."""
    conf = "{{" + f"{s.ref('Config')}.result" + "}}"
    evx = "{{" + f"{s.ref(EV)}.result" + "}}"
    rux = "{{" + f"{s.ref(RULES)}.result" + "}}"
    # The routes before this one ran first: a master write that failed marked the key failed, not done.
    gate = s.http("Step 6: Master written?", "GET",
                  s.table(f"/key_log?recipe=eq.{R}&status=eq.done&key=eq.") + key_q)
    code, inputs = n8n_rule(N8N.LISTS_JS, {"Config": conf, RULES: rux}, many=True, bodies={"self": "JSON.stringify(out)"})
    pick = s.code(LISTS, code, inputs)
    pick["filter"] = s.when("master written", "{{length(" + f"{s.ref('Step 6: Master written?')}.data" + ")}}", "0", "number:greater")
    each = s.iterator("Each list", "{{" + f"{s.ref(LISTS)}.result.items" + "}}")
    li = lambda f: "{{" + f"{s.ref('Each list')}.{f}" + "}}"  # noqa: E731
    find_e = list_call(s, "Step 6: Find on the list by email", "GET", li("url") + "/contacts",
                       query={"_wrap": "1", "email": "{{" + f"{s.ref(RULES)}.result.email" + "}}"})
    find_p = list_call(s, "Step 6: Find on the list by phone", "GET", li("url") + "/contacts",
                       query={"_wrap": "1", "phone": "{{" + f"{s.ref(RULES)}.result.phone" + "}}"})
    fe, fp = s.ref("Step 6: Find on the list by email"), s.ref("Step 6: Find on the list by phone")
    common = {LISTS: li("self"), "Step 6: Find on the list by email": "{{" + f"{fe}.data" + "}}", EV: evx, RULES: rux, "Config": conf}
    recs = n8n_rule(N8N.RECS_JS, {**common, "Step 6: Find on the list by phone": "{{" + f"{fp}.data" + "}}"},
                    many=True, bodies=LIST_BODIES, prelude=ITEM_MATCHING)
    gone = n8n_rule(N8N.UNREACHABLE_JS, {**common, "Find failed": "{{" + f"{fe}.statusCode" + "}}/{{" + f"{fp}.statusCode" + "}}"},
                    many=True, bodies=LIST_BODIES, input_node="Find failed",
                    prelude="DATA['Find failed'] = [{ json: { error: { message: 'the list answered HTTP ' + input.in5_Findfailed } } }];")
    code, inputs = first_of("Number(input.email_status) >= 400 || Number(input.phone_status) >= 400", gone, recs)
    inputs.update(email_status="{{" + f"{fe}.statusCode" + "}}", phone_status="{{" + f"{fp}.statusCode" + "}}")
    records = s.code(RECS, code, inputs)
    each_rec = s.iterator("Each record", "{{" + f"{s.ref(RECS)}.result.items" + "}}")
    rec = lambda f: "{{" + f"{s.ref('Each record')}.{f}" + "}}"  # noqa: E731

    # The record's change, then the read-back: the list confirms only if it now holds the change.
    apply_ = list_call(s, "Step 6: Apply it to the list", "PATCH", rec("url") + "/contacts/" + rec("record_q"),
                       body=rec("apply_body"), parse=False)
    back = list_call(s, "Step 6: Read it back", "GET", rec("url") + "/contacts/" + rec("record_q"))
    ap, rb = s.ref("Step 6: Apply it to the list"), s.ref("Step 6: Read it back")
    csrc = {"Step 6: Records to change": rec("self"), EV: evx, RULES: rux, "Config": conf}
    confirm = n8n_rule(N8N.CONFIRM_JS, {**csrc, "Step 6: Read it back": "{{" + f"{rb}.data" + "}}"}, bodies=LIST_BODIES)
    unconf = n8n_rule(N8N.UNCONFIRMED_JS, {**csrc, "Did not confirm": ""}, bodies=LIST_BODIES, input_node="Did not confirm")
    # A write or read-back with an HTTP error, or a read-back that differs: step 7, never retried.
    code = ("const ok = Number(input.apply_status) < 400 && Number(input.read_status) < 400;\n"
            "const confirmed = ok ? (() => {\n" + confirm[0] + "\n})() : null;\n"
            "if (confirmed && confirmed.outcome === 'confirmed') return confirmed;\n"
            "return ((input) => {\n" + unconf[0] + "\n})(Object.assign({}, input, { in4_Didnotconfirm: confirmed || "
            "{ error: { message: 'the list answered HTTP ' + input.apply_status + '/' + input.read_status } } }));")
    inputs = {**confirm[1], **unconf[1], "apply_status": "{{" + f"{ap}.statusCode" + "}}", "read_status": "{{" + f"{rb}.statusCode" + "}}"}
    check = s.code("Step 6: Rule: did the list confirm?", code, inputs)
    ck = lambda f: "{{" + f"{s.ref('Step 6: Rule: did the list confirm?')}.result.{f}" + "}}"  # noqa: E731

    on_list = [apply_, back, check, s.router("Confirmed?", [
        (s.when("confirmed", ck("outcome"), "confirmed"), [s.decision_log("Step 6: Decision log", ck("log_body"))]),
        (s.when("not confirmed", ck("outcome"), "confirmed", "text:notequal"), step7(s, "did not confirm", ck, cfg)),
    ])]
    route = lambda p: s.when(p, rec("path"), p)  # noqa: E731
    return [gate, pick, each, find_e, find_p, records, each_rec, s.router("On the list?", [
        (route("on the list"), on_list),
        (route("not on the list"), [s.decision_log("Step 6: Decision log (not on the list)", rec("log_body"))]),
        (route("did not confirm"), step7(s, "list unreachable", rec, cfg)),
    ])]


def nightly() -> Scenario:
    s = Scenario(R, "R15.3 Keep consent in sync: nightly correction", "schedule", test_key=N8N.N, schedule="every day at 02:00")
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    conf = "{{" + f"{c}.result" + "}}"
    s.flow += s.stop_flag()
    master = s.http("Step 8: Read the master", "GET", cfg("crm_url") + "/contacts", query={"_wrap": "1"})
    master["filter"] = s.continue_unless_stopped()
    s.flow.append(master)
    code, inputs = n8n_rule(N8N.NIGHT_LISTS_JS, {"Config": conf}, many=True, bodies={"self": "JSON.stringify(out)"})
    s.flow.append(s.code("Step 8: Lists to check", code, inputs))
    s.flow.append(s.iterator("Each list", "{{" + f"{s.ref('Step 8: Lists to check')}.result.items" + "}}"))
    li = lambda f: "{{" + f"{s.ref('Each list')}.{f}" + "}}"  # noqa: E731

    def failure(name: str, js: str, sources: dict, tag: str) -> list[dict]:
        """Step 8's failure path: the exception queue holds the list until it is fixed, and Owen is told."""
        code, inputs = n8n_rule(js, {"Config": conf, **sources}, bodies={
            "exception_body": f"JSON.stringify({{ recipe: '{R}', item: out.list, reason: 'nightly check failed', "
                              f"detail: out.problem + '; the list stays held until it is fixed', owner: {CFG}.consent_owner }})",
            "message": f"JSON.stringify({{ to: {CFG}.consent_owner, subject: 'Nightly consent check: ' + out.list, text: out.problem }})",
        })
        step = s.code(name, code, inputs)
        out = lambda f: "{{" + f"{s.ref(name)}.result.{f}" + "}}"  # noqa: E731
        return [step, s.exception(f"Exception queue: list held ({tag})", out("exception_body")),
                s.http(f"Step 8: Tell Owen ({tag})", "POST", cfg("messaging_url") + "/messages", body=out("message"), parse=False),
                s.ignore()]

    # A list that cannot be read: n8n's error output, so no retry here either.
    s.flow.append(s.http("Step 8: Read the list", "GET", li("url") + "/contacts", query={"_wrap": "1"},
                         onerror=failure("Step 8: List still failing", "const l = $('Step 8: Lists to check').item.json;\n"
                                         "return { json: { list: l.list, problem: 'nightly read failed: ' + (($json.error && $json.error.message) || 'no answer') } };",
                                         {"Step 8: Lists to check": li("self")}, "read failed")))
    code, inputs = n8n_rule(N8N.DRIFT_JS, {
        "Step 8: Read the master": "{{" + f"{s.ref('Step 8: Read the master')}.data" + "}}",
        "Step 8: Lists to check": li("self"),
        "Step 8: Read the list": "{{" + f"{s.ref('Step 8: Read the list')}.data" + "}}",
    }, many=True, prelude=ITEM_MATCHING, bodies={
        "self": "JSON.stringify(out)",
        "record_q": "encodeURIComponent(out.record_id)",
        "correct_body": "JSON.stringify({ marketing_opt_out: out.opt_out })",
        "log_body": f"JSON.stringify({{ recipe: '{R}', item: out.list + ':' + out.record_id, decision: 'nightly: ' + out.list + ' corrected to the master', "
                    "rules: { list: out.list, contact: out.contact_id, opt_out: out.opt_out } })",
    })
    s.flow.append(s.code("Step 8: Rule: records that differ", code, inputs))
    s.flow.append(s.iterator("Each record that differs", "{{" + f"{s.ref('Step 8: Rule: records that differ')}.result.items" + "}}"))
    d = lambda f: "{{" + f"{s.ref('Each record that differs')}.{f}" + "}}"  # noqa: E731
    s.flow.append(s.http("Step 8: Correct the list", "PATCH", d("url") + "/contacts/" + d("record_q"), body=d("correct_body"), parse=False,
                         onerror=failure("Step 8: Correction failed",
                                         "const d = $('Step 8: Rule: records that differ').item.json;\n"
                                         "return { json: { list: d.list, problem: 'nightly correction of ' + d.record_id + ' failed' } };",
                                         {"Step 8: Rule: records that differ": d("self")}, "correction failed")))
    s.flow.append(s.decision_log("Step 8: Decision log", d("log_body")))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R15.3/make/, scenario)."""
    files = {"r15-3-unsubscribe": "blueprint.json", "r15-3-opt-in": "opt-in.blueprint.json",
             "r15-3-pos-signup": "pos-signup.blueprint.json", "r15-3-helpdesk-tag": "helpdesk-tag.blueprint.json"}
    return [(files[path], consent_event(name, path)) for name, path, _ in N8N.EVENTS] + [("nightly.blueprint.json", nightly())]
