"""R6.3 Find likely duplicate accounts and queue them for a person to merge, as Make scenarios.

Source: book Chapter 6, recipe R6.3, Table 6.3 and build steps 1 to 10 (recipes/R6.3/build-spec.md);
AI step: recipes/R6.3/prompts/explain-match.md (step 7). The rules are the n8n build's own
JavaScript (tools/builds/r6_3.py), run through n8n_rule.
Two scenarios, because a Make scenario has one trigger: the weekly duplicate check (schedule,
every Sunday at 02:00, outside trading hours, blueprint.json; set the scenario's time zone in
Make) and the merger's decision from the merge queue's form (webhook, decision.blueprint.json).
n8n's "Decision recorded?" node only asked which trigger ran, so it is not built.

Where the Make build differs from the n8n canvas, and why:
- The export reads try three times, as n8n's do (with_tries), so the step after each sees the
  last try's status. n8n sends a failed read to "Step 2: Export failed"; Make's routes never meet
  again, so a failed account export is its own route ("Accounts exported?") with its own
  exception row and message, whose text names the status Make returns. A failed contacts export
  is answered inside "Step 2: Rule: export full and unchanged?", ahead of the rule, with the
  same "export failed" problem n8n's node gives.
- Step 5 returns one item per pair; an iterator runs steps 6 to 10 once per pair, as n8n runs
  its per-item nodes. n8n's "New key?" and "Waiting: skip" are the filter on the step 7 AI
  request: a pair already waiting stops there.
- The step 7 AI call tries three times, as the n8n build's does (tries=3). n8n's "Step 7: AI
  error", "Step 7: Rule: names only matched signals?" and "Step 8: Rule: who confirms first?"
  run in one Code step, in the same order, because each Code step costs credits.
- n8n builds the step 9 and step 10 bodies in expressions; Make mappings cannot serialise a
  collection, so the rule before each write builds them with JSON.stringify. The decision
  scenario has no rule before its writes, so "Step 10: Build the bodies" does that.
- n8n's "Rejected?" branches join again at "Step 10: Release the key"; Make's do not, so each
  route releases the key and logs the decision, with the route in the step's name. The release
  is the table API's release_key function (n8n's DELETE on the key log).
- Mark key failed records "write failed" without the HTTP error text, which Make's error route
  does not hand to a later body.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R6.3"
N8N = n8n_build(R)
T, TD, PAIRS = N8N.T, N8N.TD, N8N.PAIRS
NORMALIZE, PAIR, CHECK_EXPORT = "Step 3: Rule: normalize signals", "Step 4: Rule: group and pair", "Step 2: Rule: export full and unchanged?"
ACCOUNTS, CONTACTS, SUPPRESSIONS = "Step 2: Export accounts", "Step 2: Export contacts", "Read the suppression list"
EXPLAIN = "Steps 7 and 8: Rule: names only matched signals, who confirms first?"
READ_PAIR = "Step 10: Queue: Read the pair"
DECISION_FIELDS = ("pair_id", "decision", "by")
CONFIG = {
    "export_url": "https://<your CRM export API>",
    "queue_url": "https://<your merge queue and suppression list API>",
    "messaging_url": "https://<your messaging API>",
    "account_fields": ["id", "name", "phone", "tax_id", "billing_address", "email", "open_quotes", "credit_terms", "links"],
    "contact_fields": ["id", "account_id", "email"],
    "expected_accounts": 400,
    "max_shrink_pct": 20,
    "excluded_domains": ["<your webmail and shared domains>"],
    "default_country_code": "<your country calling code, digits only>",
    "name_suffixes": ["inc", "llc", "ltd"],
    "address_abbreviations": {"street": "st", "avenue": "ave", "road": "rd", "drive": "dr", "boulevard": "blvd", "suite": "ste"},
    "signal_terms": {"tax_id": ["tax"], "phone": ["phone", "telephone"], "billing_address": ["address"],
                     "email_domain": ["domain", "email"], "name": ["name"]},
    "other_field_terms": ["<your CRM's other field names>"],
    "open_quote_confirmer": "<your sales lead>",
    "credit_terms_confirmer": "<your finance lead>",
    "merger": "<your named merger>",
    "export_owner": "<the person who fixes the export>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
AI_ERROR_JS = "return { json: { reason: null, reason_check: 'AI error after three retries' } };"  # n8n's "Step 7: AI error"
# The contacts export failed after three tries: n8n's "Step 2: Export failed" answer, ahead of the rule.
CONTACTS_FAILED_JS = ("if (Number(input.contacts_status) !== 200) return [{ json: { ok: false, "
                      "problem: 'export failed: contacts export returned ' + (input.contacts_status || 'no answer') } }];")
CFG = "$('Config').first().json"
P = f"$('{PAIRS}').item.json"
DEC = f"$('{TD}').first().json.body"
SUBJECT = "R6.3 duplicate run stopped: export check failed"


def brace_safe(js: str) -> str:
    """Make reads {{ in a Code step's script as a mapping; inside a string literal it is written
    \\u007b{, which JavaScript reads back as the same text."""
    return re.sub(r"\{(?=\{)", r"\\u007b", js)


def part(js: str) -> str:
    """One n8n Code node's JavaScript as a function of $json, for a Code step that runs several in turn."""
    return "(($json) => {\n" + js.strip() + "\n})"


def weekly() -> Scenario:
    """Steps 1 to 10 for every pair: the export, the rules, the AI's reason and the queue."""
    s = Scenario(R, "R6.3 Find likely duplicate accounts: weekly check", "schedule", test_key=T,
                 schedule="every Sunday at 02:00, outside trading hours")
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    conf = "{{" + f"{c}.result" + "}}"
    s.flow += s.stop_flag()
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    out = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    result = lambda n: "{{" + f"{s.ref(n)}.result" + "}}"  # noqa: E731

    # ---- step 2: the export, three tries each ---------------------------------------------------
    accounts = s.with_tries(s.http(ACCOUNTS, "GET", cfg("export_url") + "/accounts", query={"_wrap": "1"}, onerror=[]), 3)
    accounts["filter"] = s.continue_unless_stopped()
    s.flow.append(accounts)
    contacts = s.with_tries(s.http(CONTACTS, "GET", cfg("export_url") + "/contacts", query={"_wrap": "1"}, onerror=[]), 3)
    acc_status = "{{" + f"{s.ref(ACCOUNTS)}.statusCode" + "}}"

    code, inputs = n8n_rule(CONTACTS_FAILED_JS + "\n" + N8N.CHECK_EXPORT_JS, {"Config": conf, ACCOUNTS: data(ACCOUNTS), CONTACTS: data(CONTACTS)},
                            bodies={
        "exception_body": (f"JSON.stringify({{ recipe: '{R}', item: 'export ' + new Date().toISOString().slice(0, 10), "
                           f"reason: 'export check failed', detail: out.problem, owner: {CFG}.export_owner }})"),
        "message_body": f"JSON.stringify({{ to: {CFG}.export_owner, subject: '{SUBJECT}', text: out.problem }})",
    })
    inputs["contacts_status"] = "{{" + f"{s.ref(CONTACTS)}.statusCode" + "}}"
    check = s.code(CHECK_EXPORT, code, inputs)

    def stopped(tag: str, exc_body: str, msg_body: str) -> list[dict]:
        """The export stopped the run: the exception row, then the message to the export owner."""
        return [s.exception(f"Exception queue: export stopped the run ({tag})", exc_body),
                s.http(f"Step 2: Tell the export owner ({tag})", "POST", cfg("messaging_url") + "/messages", body=msg_body, parse=False)]

    # ---- steps 3 to 5: rules choose every pair --------------------------------------------------------
    code, inputs = n8n_rule(N8N.NORMALIZE_JS, {"Config": conf, ACCOUNTS: data(ACCOUNTS), CONTACTS: data(CONTACTS)})
    normalize = s.code(NORMALIZE, code, inputs)
    code, inputs = n8n_rule(N8N.PAIR_JS, {NORMALIZE: result(NORMALIZE)})
    pair = s.code(PAIR, code, inputs)
    suppressions = s.http(SUPPRESSIONS, "GET", cfg("queue_url") + "/suppressions", query={"_wrap": "1"})
    code, inputs = n8n_rule(N8N.SUPPRESS_JS, {"Config": conf, PAIR: result(PAIR), SUPPRESSIONS: data(SUPPRESSIONS)}, many=True, bodies={
        "self": "JSON.stringify(out)",
        "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: out.pair_id }})",
        "key_q": "encodeURIComponent(out.pair_id)",
        "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: out.pair_id, reason: 'write failed', "
                        f"detail: 'Queue write failed; check the queue, then release the key', owner: {CFG}.merger }})"),
    })
    suppress = s.code(PAIRS, code, inputs)
    each = s.iterator("Each pair", out(PAIRS, "items"))
    q = lambda f: "{{" + f"{each['id']}.{f}" + "}}"  # noqa: E731

    # ---- step 6: the key log holds a waiting pair --------------------------------------------------------
    reserve = s.rpc("Step 6: Reserve key", "reserve_key", q("reserve_body"))
    sources = {"Config": conf, PAIRS: q("self")}

    # ---- step 7: the AI only explains; step 8: who confirms first -------------------------------------------
    ai = s.ai_step("Step 7", ROOT / "recipes/R6.3/prompts/explain-match.md", f"{{ matched_fields: {P}.matched_fields }}",
                   sources, max_tokens=150, tries=3)
    ai[0]["filter"] = s.is_new_key("Step 6: Reserve key")  # a copy stops here: n8n's "Waiting: skip"
    call = s.ref("Step 7: AI call")
    js = ("const __ok = Number(input.ai_status) === 200;\n"
          f"const __reason = one(__ok ? {part(N8N.EXPLAIN_JS)}($json) : {part(AI_ERROR_JS)}({{}}))[0];\n"
          f"return {part(N8N.CONFIRM_JS)}(__reason);")
    s8 = "out"
    code, inputs = n8n_rule(brace_safe(js), {**sources, "Step 7: AI call": "{{" + f"{call}.data" + "}}"}, bodies={
        "queue_body": (f"JSON.stringify({{ id: {P}.pair_id, accounts: [{P}.a, {P}.b], records: {P}.records, signals: {P}.signals, "
                       f"matched_fields: {P}.matched_fields, reason: {s8}.reason, reason_check: {s8}.reason_check, "
                       f"confirm_first: {s8}.confirm_first, merger: {CFG}.merger, snapshot: {P}.snapshot, status: 'waiting', "
                       "queued: new Date().toISOString().slice(0, 10) })"),
        "done_body": "JSON.stringify({ status: 'done', result: 'queued; waiting for the merger' })",
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {P}.pair_id, decision: 'queued', rules: {{ signals: {P}.signals, "
                     f"suppression: {P}.suppression, reason_check: {s8}.reason_check, confirm_first: {s8}.confirm_first }} }})"),
    })
    inputs["ai_status"] = "{{" + f"{call}.statusCode" + "}}"
    explain = s.code(EXPLAIN, code, inputs)

    # ---- steps 9 and 10: the queue, with both records, then the key and the log ---------------------------
    name = "Step 9: Queue the pair with both records"
    queue = s.http(name, "POST", cfg("queue_url") + "/pairs", body=out(EXPLAIN, "queue_body"), parse=False,
                   onerror=s.write_failed(name, q("key_q"), q("failed_body")))
    per_pair = [reserve] + ai + [explain, queue,
                                 s.finish_key("Mark key done", q("key_q"), out(EXPLAIN, "done_body")),
                                 s.decision_log("Step 10: Decision log: queued", out(EXPLAIN, "log_body"))]

    ok = out(CHECK_EXPORT, "ok")
    read = [contacts, check, s.router("Export OK?", [
        (s.when("export full and unchanged", ok, "true"), [normalize, pair, suppressions, suppress, each] + per_pair),
        (s.when("export short or changed", ok, "true", "text:notequal"),
         stopped("export check", out(CHECK_EXPORT, "exception_body"), out(CHECK_EXPORT, "message_body"))),
    ])]
    # The account export failed after three tries: n8n's "Step 2: Export failed". Only IDs, the status and fixed text.
    problem = "export failed: accounts export returned " + acc_status
    failed = stopped("accounts export failed",
                     '{"recipe": "' + R + '", "item": "export {{formatDate(now; "YYYY-MM-DD"; "UTC")}}", "reason": "export check failed", '
                     '"detail": "' + problem + '", "owner": "' + cfg("export_owner") + '"}',
                     '{"to": "' + cfg("export_owner") + '", "subject": "' + SUBJECT + '", "text": "' + problem + '"}')
    s.flow.append(s.router("Accounts exported?", [
        (s.when("accounts read", acc_status, "200"), read),
        (s.when("accounts export failed", acc_status, "200", "text:notequal"), failed),
    ]))
    return s


def decision() -> Scenario:
    """Step 10: the merger records "merge" or "reject"; a rejection goes on the suppression list."""
    s = Scenario(R, "R6.3 Find likely duplicate accounts: decision recorded", "webhook", test_key="r6-3-decision")
    s.flow.append(s.webhook(TD))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    read = s.http(READ_PAIR, "GET", cfg("queue_url") + "/pairs/{{encodeURL(1.pair_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)

    # n8n's expressions on the webhook body, as bodies; the webhook's fields rebuild that body.
    pair = f"$('{READ_PAIR}').first().json"
    prelude = (f"// The webhook's fields, as n8n reads them: $('{TD}').first().json.body.\n"
               f"DATA[{json.dumps(TD)}] = [{{ json: {{ body: {{ " + ", ".join(f"{f}: input.t_{f}" for f in DECISION_FIELDS) + " } } }];")
    code, inputs = n8n_rule("return [{ json: {} }];", {"Config": "{{" + f"{c}.result" + "}}", READ_PAIR: "{{" + f"{s.ref(READ_PAIR)}.data" + "}}"},
                            prelude=prelude, bodies={
        "suppression_body": (f"JSON.stringify({{ pair: {pair}.accounts, signals: {pair}.signals, snapshot: {pair}.snapshot, "
                             f"rejected_by: {DEC}.by, rejected: new Date().toISOString().slice(0, 10) }})"),
        "release_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: {DEC}.pair_id }})",
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {DEC}.pair_id, decision: {DEC}.decision + ' by ' + {DEC}.by, "
                     f"rules: {{ signals: {pair}.signals, confirm_first: {pair}.confirm_first || [], by: {DEC}.by }} }})"),
        "exception_body": (f"JSON.stringify({{ recipe: '{R}', item: {DEC}.pair_id, reason: 'write failed', "
                           f"detail: 'Suppression write failed; the rejected pair may be queued again', owner: {CFG}.merger }})"),
    })
    inputs = {**{f"t_{f}": "{{1." + f + "}}" for f in DECISION_FIELDS}, **inputs}
    bodies = "Step 10: Build the bodies"
    s.flow.append(s.code(bodies, code, inputs))
    b = lambda f: "{{" + f"{s.ref(bodies)}.result.{f}" + "}}"  # noqa: E731

    def close(tag: str) -> list[dict]:
        """The pair no longer waits: a merged pair is gone, a rejected one is held by the suppression list."""
        return [s.release_key(f"Step 10: Release the key ({tag})", b("release_body")),
                s.decision_log(f"Step 10: Decision log ({tag})", b("log_body"))]

    name = "Step 10: Suppression list: Add the pair"
    suppress = s.http(name, "PUT", cfg("queue_url") + "/suppressions/{{encodeURL(1.pair_id)}}", body=b("suppression_body"), parse=False,
                      onerror=[s.exception("Exception queue: suppression write failed", b("exception_body")), s.ignore()])
    s.flow.append(s.router("Rejected?", [
        (s.when("rejected", "{{1.decision}}", "reject"), [suppress] + close("rejected")),
        (s.when("not rejected", "{{1.decision}}", "reject", "text:notequal"), close("not rejected")),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R6.3/make/, scenario)."""
    return [("blueprint.json", weekly()), ("decision.blueprint.json", decision())]
