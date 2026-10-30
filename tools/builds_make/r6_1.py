"""R6.1 Log emails and meeting notes to the right account and deal, as Make scenarios.

Source: book Chapter 6, recipe R6.1, build steps 1 to 8 (recipes/R6.1/build-spec.md);
AI steps: recipes/R6.1/prompts/choose-deal.md (step 5, only for several open deals) and
recipes/R6.1/prompts/summarize.md (step 6). The rules are the n8n build's own JavaScript
(tools/builds/r6_1.py), run through n8n_rule.
Two scenarios, because a Make scenario has one trigger: an email marked into a "CRM" folder
(blueprint.json) and a saved meeting note (note.blueprint.json), both webhooks. Each reads its
own source, so the n8n "Email?" switch is gone; "Step 1: The item" is the same rule in both.

Where the Make build differs from the n8n canvas, and why:
- Both AI steps try three times, as the n8n build's AI calls do (tries=3): the second try runs
  in the first call's error route and the third in the second's, and Make's Resume handler hands
  the answer back up (mk's ai_step, tries=3).
- n8n's "Step 5: AI error" and "Step 6: AI error" nodes run inside the rule after each call
  (on_ai_error), because Make branches never meet again.
- n8n gathers every outcome into "Unmatched: reason" and "Result" before marking the key done
  and logging. Make's routes never meet again, so each route ends with its own exception row
  (for an unmatched item), mark key done and decision log, with the route in the step's name.
  The two pass-through Code nodes are not separate steps: the rule that decides each route
  builds those bodies, with the same text and rules the n8n nodes give.
- Steps 6 to 8 follow two routes, one deal or none read from the CRM and a deal the step 5 AI
  named, so they are built twice; the rule sees the step 5 rule only on the AI route, as in n8n.
- The activity's ID is known only after the write, so the draft body carries a placeholder that
  the mapping replaces with that ID (ACTIVITY_ID).
- Mark key failed records "write failed" without the HTTP error text, which Make's error route
  does not hand to a later body.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R6.1"
N8N = n8n_build(R)
TE, TN = N8N.TE, N8N.TN
ITEM_STEP, ADDRESS, ACCOUNT_RULE = "Step 1: The item", "Step 3: Rule: customer address", "Step 4: Rule: exactly one account?"
DEALS, CHOOSE, CHECK = "Step 5: Rule: how many open deals?", "Step 5: Rule: deal named or unclear?", "Step 7: Rule: deal open, summary within length?"
ACCOUNT_READ = "CRM: Read the account"
CONFIG = {
    "mail_url": "https://<your mail API>",
    "notes_url": "https://<your meeting notes API>",
    "crm_url": "https://<your CRM API>",
    "never_log": ["@<your company domain>", "<a staff private address>"],
    "max_summary_sentences": 3,
    "queue_owner": "<the person who checks the unmatched queue daily>",
    "crm_admin": "<your CRM admin>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
AI_ERROR_JS = ("return [{{ json: {{ route: 'exception', code: 'AI error', detail: 'step {n}: ' + "
               "String(($json.error && $json.error.message) || '') }} }}];")
ACTIVITY_ID = "__ACTIVITY_ID__"  # replaced in the mapping by the CRM's ID for the activity just written
# JavaScript shorthands for the bodies, as in the n8n build.
CFG = "$('Config').first().json"
ITEM = f"$('{ITEM_STEP}').first().json"
ACCOUNT = f"$('{ACCOUNT_READ}').first().json"
STEP4_ACCOUNT = f"($('{ACCOUNT_RULE}').isExecuted ? $('{ACCOUNT_RULE}').first().json.account_id || null : null)"


def unmatched(acct: str = "null") -> dict[str, str]:
    """Bodies for an item queued for a person: n8n's "Unmatched: reason", exception row and "Result"."""
    decision = "'queued: ' + out.code"
    return {
        "unmatched_body": (f"JSON.stringify({{ recipe: '{R}', item: {ITEM}.key, reason: 'unmatched', "
                           f"detail: out.code + (out.detail ? ': ' + out.detail : ''), owner: {CFG}.queue_owner }})"),
        "queued_done": f"JSON.stringify({{ status: 'done', result: {decision} }})",
        "queued_log": f"JSON.stringify({{ recipe: '{R}', item: {ITEM}.key, decision: {decision}, rules: {{ account: {acct}, reason: out.code }} }})",
    }






def scenario(trigger: str, test_key: str, field: str, read: str, url_field: str, path: str) -> Scenario:
    kind = "email marked" if trigger == TE else "note saved"
    s = Scenario(R, f"R6.1 Log emails and meeting notes to the right account and deal: {kind}", "webhook", test_key=test_key)
    s.flow.append(s.webhook(trigger))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    cfg_all = "{{" + f"{c}.result" + "}}"
    s.flow += s.stop_flag()
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    out = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    result = lambda n: "{{" + f"{s.ref(n)}.result" + "}}"  # noqa: E731

    # ---- step 1: read the email or note, reduce it to one item; step 2: the key -----------------
    rd = s.http(read, "GET", cfg(url_field) + path + "{{encodeURL(1." + field + ")}}")
    rd["filter"] = s.continue_unless_stopped()
    s.flow.append(rd)
    code, inputs = n8n_rule(N8N.ITEM_JS, {"Config": cfg_all, read: data(read)}, bodies={
        "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: out.key }})",
        "key_q": "encodeURIComponent(out.key)",
        "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: out.key, reason: 'write failed', "
                        f"detail: 'CRM write failed; check the CRM, then release or close the key', owner: {CFG}.crm_admin }})"),
    })
    s.flow.append(s.code(ITEM_STEP, code, inputs))
    sources = {"Config": cfg_all, ITEM_STEP: result(ITEM_STEP)}
    key_q = out(ITEM_STEP, "key_q")
    s.flow.append(s.rpc("Step 2: Reserve key", "reserve_key", out(ITEM_STEP, "reserve_body")))

    def closing(tag: str, rule: str, done: str, log: str) -> list[dict]:
        return [s.finish_key(f"Mark key done ({tag})", key_q, out(rule, done)),
                s.decision_log(f"Decision log ({tag})", out(rule, log))]

    def queued(tag: str, rule: str) -> list[dict]:
        """An item queued for a person: the exception row, then the key and the decision log."""
        return [s.exception(f"Exception queue: unmatched ({tag})", out(rule, "unmatched_body"))] + closing(tag, rule, "queued_done", "queued_log")

    # ---- step 3: the customer's address ------------------------------------------------------------
    code, inputs = n8n_rule(N8N.ADDRESS_JS, sources, bodies={
        **unmatched(),
        "stop_done": "JSON.stringify({ status: 'done', result: 'not logged: ' + out.code })",
        "stop_log": f"JSON.stringify({{ recipe: '{R}', item: {ITEM}.key, decision: 'not logged: ' + out.code, rules: {{ reason: out.code }} }})",
    })
    address = s.code(ADDRESS, code, inputs)
    address["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: logged before, from another mailbox
    s.flow.append(address)

    # ---- step 4: the full address, never the domain ------------------------------------------------
    search = s.http("Step 4: CRM: Search by full address", "GET", cfg("crm_url") + "/contacts",
                    query={"_wrap": "1", "email": out(ADDRESS, "address")})
    code, inputs = n8n_rule(N8N.ACCOUNT_JS, {**sources, "Step 4: CRM: Search by full address": data("Step 4: CRM: Search by full address")},
                            bodies=unmatched("out.account_id || null"))
    account_rule = s.code(ACCOUNT_RULE, code, inputs)
    sources[ACCOUNT_RULE] = result(ACCOUNT_RULE)

    # ---- step 5: the open deals --------------------------------------------------------------------
    account = s.http(ACCOUNT_READ, "GET", cfg("crm_url") + "/accounts/{{encodeURL(" + f"{s.ref(ACCOUNT_RULE)}.result.account_id" + ")}}")
    sources[ACCOUNT_READ] = data(ACCOUNT_READ)
    deals_read = s.http("Step 5: CRM: Read open deals", "GET", cfg("crm_url") + "/deals",
                        query={"_wrap": "1", "account_id": "{{" + f"{s.ref(ACCOUNT_READ)}.data.id" + "}}", "status": "open"})
    code, inputs = n8n_rule(N8N.DEALS_JS, {**sources, "Step 5: CRM: Read open deals": data("Step 5: CRM: Read open deals")})
    deals = s.code(DEALS, code, inputs)
    sources[DEALS] = result(DEALS)

    def steps_6_to_8(tag: str, chose: bool) -> list[dict]:
        """Step 6 summarizes, step 7 checks, step 8 writes. tag names this route's copy of the steps."""
        sfx = f" ({tag})" if tag else ""
        src = dict(sources) if chose else {k: v for k, v in sources.items() if k != CHOOSE}
        sum_js = f"{{ message_type: {ITEM}.kind, message_date: {ITEM}.date, subject: {ITEM}.subject, body: {ITEM}.body }}"
        step = "Step 6" + sfx
        ai = s.ai_step(step, ROOT / "recipes/R6.1/prompts/summarize.md", sum_js, {"Config": cfg_all, ITEM_STEP: result(ITEM_STEP)},
                       max_tokens=400, tries=3)
        call = s.ref(f"{step}: AI call")
        code, inputs = n8n_rule(N8N.CHECK_JS, {**src, "Step 6: AI call": "{{" + f"{call}.data" + "}}"},
                                ai_status="{{" + f"{call}.statusCode" + "}}", on_ai_error=AI_ERROR_JS.format(n=6), bodies={
            **unmatched(STEP4_ACCOUNT),
            "activity_body": (f"JSON.stringify({{ account_id: {ACCOUNT}.id, deal_id: out.deal_id, type: {ITEM}.kind, "
                              f"date: {ITEM}.date, link: {ITEM}.link, message_id: {ITEM}.key }})"),
            "contact_body": f"JSON.stringify({{ last_contact: [{ACCOUNT}.last_contact, {ITEM}.date].filter(Boolean).sort().pop() }})",
            "draft_body": (f"JSON.stringify({{ activity_id: '{ACTIVITY_ID}', account_id: {ACCOUNT}.id, deal_id: out.deal_id, owner: {ACCOUNT}.owner, "
                           "summary: out.summary, next_step_date: out.next_step_date, ai_chosen_deal: out.ai_chosen_deal, status: 'waiting for owner' })"),
            "logged_done": "JSON.stringify({ status: 'done', result: out.deal_id ? 'logged to deal ' + out.deal_id : 'logged at account level' })",
            "logged_log": (f"JSON.stringify({{ recipe: '{R}', item: {ITEM}.key, decision: out.deal_id ? 'logged to deal ' + out.deal_id : 'logged at account level', "
                           "rules: out.rules })"),
        })
        check = CHECK + sfx
        rule = s.code(check, code, inputs)
        ck = s.ref(check)
        crm = cfg("crm_url")
        failed = lambda name: s.write_failed(name, key_q, out(ITEM_STEP, "failed_body"))  # noqa: E731
        act = "Step 8: CRM: Write the activity and link" + sfx
        write_act = s.http(act, "POST", crm + "/activities", body=out(check, "activity_body"), onerror=failed(act))
        contact = "Step 8: CRM: Set last-contact date" + sfx
        draft = "Step 8: CRM: Draft for the owner" + sfx
        draft_body = "{{replace(" + f"{ck}.result.draft_body" + '; "' + ACTIVITY_ID + '"; ' + f"{s.ref(act)}.data.id" + ")}}"
        log = [write_act,
               s.http(contact, "PATCH", crm + "/accounts/{{encodeURL(" + f"{s.ref(ACCOUNT_READ)}.data.id" + ")}}", body=out(check, "contact_body"),
                      parse=False, onerror=failed(contact)),
               s.http(draft, "POST", crm + "/drafts", body=draft_body, parse=False, onerror=failed(draft))]
        log += closing("logged" + (f", {tag}" if tag else ""), check, "logged_done", "logged_log")
        route = out(check, "route")
        return ai + [rule, s.router("Log it?" + sfx, [
            (s.when("route is log", route, "log"), log),
            (s.when("route is exception", route, "log", "text:notequal"), queued("step 7" + (f", {tag}" if tag else ""), check)),
        ])]

    # ---- step 5 with several open deals: the AI names one, or "unclear" ------------------------------
    deals_js = (f"{{ open_deals: $('{DEALS}').first().json.deals"
                ".map(d => `${d.id}: ${d.name}; ${d.quote_ref || 'no quote reference'}`).join('\\n'), "
                f"subject: {ITEM}.subject, body: {ITEM}.body }}")
    choose_ai = s.ai_step("Step 5", ROOT / "recipes/R6.1/prompts/choose-deal.md", deals_js,
                          {"Config": cfg_all, ITEM_STEP: result(ITEM_STEP), DEALS: result(DEALS)}, max_tokens=50, tries=3)
    call5 = s.ref("Step 5: AI call")
    code, inputs = n8n_rule(N8N.CHOOSE_JS, {**sources, "Step 5: AI call": "{{" + f"{call5}.data" + "}}"},
                            ai_status="{{" + f"{call5}.statusCode" + "}}", on_ai_error=AI_ERROR_JS.format(n=5),
                            bodies=unmatched(STEP4_ACCOUNT))
    choose = s.code(CHOOSE, code, inputs)
    sources[CHOOSE] = result(CHOOSE)
    named = out(CHOOSE, "route")
    several = choose_ai + [choose, s.router("Deal named?", [
        (s.when("deal named", named, "ok"), steps_6_to_8("AI-chosen deal", True)),
        (s.when("unclear or AI error", named, "ok", "text:notequal"), queued("step 5", CHOOSE)),
    ])]
    open_route = out(DEALS, "route")
    open_deals = s.router("Step 5: Open deals", [
        (s.when("none or one", open_route, "several", "text:notequal"), steps_6_to_8("", False)),
        (s.when("several", open_route, "several"), several),
    ])

    one = out(ACCOUNT_RULE, "one")
    step4 = [search, account_rule, s.router("One account?", [
        (s.when("one account", one, "true"), [account, deals_read, deals, open_deals]),
        (s.when("not one account", one, "true", "text:notequal"), queued("step 4", ACCOUNT_RULE)),
    ])]
    outcome = out(ADDRESS, "outcome")
    s.flow.append(s.router("Step 3: Loggable?", [
        (s.when("outcome is ok", outcome, "ok"), step4),
        (s.when("outcome is stop", outcome, "stop"), closing("not logged", ADDRESS, "stop_done", "stop_log")),
        (s.when("outcome is exception", outcome, "exception"), queued("step 3", ADDRESS)),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R6.1/make/, scenario)."""
    return [("blueprint.json", scenario(TE, "r6-1-email-marked", "message_id", "Step 1: Read the email", "mail_url", "/messages/")),
            ("note.blueprint.json", scenario(TN, "r6-1-note-saved", "note_id", "Step 1: Read the note", "notes_url", "/notes/"))]
