"""R13.3 Turn a resolved ticket into a draft knowledge article for the owner to approve, as Make scenarios.

Source: book Chapter 13, recipe R13.3, build steps 1 to 11 and its failure table (recipes/R13.3/build-spec.md);
AI step: recipes/R13.3/prompts/draft-article.md. The rules are the n8n build's own JavaScript
(tools/builds/r13_3.py), run through n8n_rule. The AI only drafts; the rules check the draft and
the article owner approves it. Nothing is published without that approval.
Three scenarios, because a Make scenario has one trigger: a ticket resolved with the reusable tag
(webhook, steps 1 to 10, blueprint.json), the article owner's decision (webhook, steps 10 and 11,
decision.blueprint.json) and the failure table's weekly count of old drafts (schedule, every Monday
at 08:00, weekly.blueprint.json). n8n's "Weekly count?" and "Draft decision?" nodes only asked which
trigger ran, so they are not built.

Differences from the n8n build, all forced by Make:
- n8n's "Step 1: Resolved with the tag?" node is the key reservation's filter (status resolved and
  the tag in the ticket's tags, by Make's contains()), so an untagged ticket ends the run before
  step 2, as in n8n.
- n8n's "Step 4: Set aside, no AI call" node runs inside the steps 3 and 4 rule, and "Step 5: AI
  error" inside the steps 6 to 9 rule (on_ai_error), because Make branches never meet again; so
  "Step 9: Read published articles" also runs after an AI error (a read; nothing changes). n8n's
  "Outcome" node only joined those branches, so it is not built: each route repeats the closing
  steps (mark the key done, decision log), with the route in the step's name.
- Make mappings cannot escape text for JSON, so the rules build every body; the draft and article
  IDs, which only the draft and article writes return, go into them through Make's replace() over
  a marker (@@draft_id@@, @@article_id@@), so the bodies hold the same values as n8n's.
- Mark key failed records "write failed" without the HTTP error text, which Make's error route
  does not hand to a later body.
- The step 10 decision log is a table-API write with approved_by, where n8n writes it in SQL.
- The webhook's fields are passed one by one and rebuilt as n8n's $('<trigger>').first().json.body,
  because a Make webhook's output cannot be mapped whole.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R13.3"
N8N = n8n_build(R)
T, D, W = N8N.T, N8N.D, N8N.W
S34 = "Steps 3 and 4: Rule: replace customer details, then check none remain"
RULES, CALL, ARTICLES = "Rules: steps 6 to 9", "Step 5: AI call", "Step 9: Read published articles"
DECIDE = "Step 10: Rule: approved by the owner, every claim worded?"
CONFIG = {
    "helpdesk_url": "https://<your helpdesk API>",
    "drafts_url": "https://<your drafts area API, read only by the article owner's team>",
    "kb_url": "https://<your knowledge base API>",
    "register_url": "https://<your source register API>",
    "messaging_url": "https://<your messaging API>",
    "reusable_tag": "reusable",
    "access_code_field": "<your restricted access-code field>",
    "personal_data_patterns": [
        {"name": "email", "pattern": "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}"},
        {"name": "phone", "pattern": "(?<![\\d])\\+?(?:\\d[\\s().-]?){8,13}\\d(?![\\d])"},
        {"name": "order number", "pattern": "<your order-number pattern>"},
    ],
    "article_template": "<your article template>",
    "price_list_link": "https://<your price list in the CRM>",
    "policy_figures": ["<your owner-approved policy figures, from R13.1's list>"],
    "policy_topics": [
        {"keywords": ["warranty", "guarantee"], "source": "<your returns and warranty source>", "owner": "<its owner>"},
        {"keywords": ["return", "refund", "exchange"], "source": "<your returns and warranty source>", "owner": "<its owner>"},
        {"keywords": ["delivery", "deliver"], "source": "<your delivery source>", "owner": "<its owner>"},
    ],
    "title_match": "<your title-match threshold, 0 to 1>",
    "article_owner": "<your knowledge-article owner>",
    "article_audience": ["<your customer service group>"],
    "article_review_days": "<your review period for articles, in days>",
    "expiry_after_review_days": 30,
    "old_draft_days": 14,
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
CFG = "$('Config').first().json"
TK = "$('Read the ticket').first().json"
DEV = f"$('{D}').first().json.body"
DR = "$('Read the draft').first().json"
DID, AID = "@@draft_id@@", "@@article_id@@"  # filled in by replace() from the draft and article writes
# n8n's "Step 4: Set aside, no AI call" and "Step 5: AI error" nodes.
SET_ASIDE_JS = f"return [{{ json: {{ route: 'set_aside', reason: 'personal data remains', detail: $('{S34}').first().json.remaining.join(', ') }} }}];"
AI_ERROR_JS = ("return [{ json: { route: 'set_aside', reason: 'AI error after two retries', "
               "detail: String(($json.error && $json.error.message) || '') } }];")
TICKET_FAILED = (f"JSON.stringify({{ recipe: '{R}', item: {TK}.id, reason: 'write failed', "
                 f"detail: 'Draft write or message failed; check the drafts area, never retried', owner: {CFG}.article_owner }})")


def body_prelude(trigger: str, fields: tuple[str, ...]) -> tuple[str, dict[str, str]]:
    """The webhook's fields rebuilt as n8n's $('<trigger>').first().json.body, and their inputs."""
    body = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in fields)
    prelude = (f"// The webhook's fields, as the rule reads them in n8n: $('{trigger}').first().json.body.\n"
               f"DATA[{json.dumps(trigger)}] = [{{ json: {{ body: {{ {body} }} }} }}];")
    return prelude, {f"t_{f}": "{{1." + f + "}}" for f in fields}


def closing_bodies() -> dict[str, str]:
    """n8n's exception, "Mark key done" and "Decision log" values for one outcome (out)."""
    return {
        "route": "out.route",
        "exception_body": (f"['set_aside', 'discard'].includes(out.route) ? JSON.stringify({{ recipe: '{R}', item: {TK}.id, "
                           "reason: out.route === 'discard' ? 'draft discarded' : 'set aside', "
                           f"detail: out.reason + ': ' + out.detail, owner: {CFG}.article_owner }}) : null"),
        "done_body": f"JSON.stringify({{ status: 'done', result: out.route === 'draft' ? 'draft {DID}' : out.reason }})",
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {TK}.id, "
                     "decision: out.route === 'draft' ? out.draft.kind + ' draft' : out.route === 'discard' ? 'draft discarded' : 'set aside: ' + out.reason, "
                     f"rules: out.route === 'draft' ? Object.assign({{ draft_id: '{DID}', held_for: out.owners }}, out.draft.checks) "
                     ": { check: out.reason, detail: out.detail } })"),
        "failed_body": TICKET_FAILED,
    }


def ticket() -> Scenario:
    s = Scenario(R, "R13.3 Turn a resolved ticket into a draft knowledge article", "webhook", test_key="r13-3-ticket-resolved")
    s.flow.append(s.webhook(T))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    cfg_all = "{{" + f"{c}.result" + "}}"
    out = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()

    # Steps 1 and 2: the ticket, resolved with the reusable tag, and its key (ticket and resolution time).
    read = s.http("Read the ticket", "GET", cfg("helpdesk_url") + "/tickets/{{encodeURL(1.ticket_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    rd = read["id"]
    reserve = s.reserve_key("Step 2: Reserve key", f"{{{{{rd}.data.id}}}}:{{{{{rd}.data.resolved_at}}}}")
    reserve["filter"] = {"name": "Step 1: resolved with the tag", "conditions": [[
        {"a": f"{{{{{rd}.data.status}}}}", "b": "resolved", "o": "text:equal"},
        {"a": f"{{{{contains({rd}.data.tags; {c}.result.reusable_tag)}}}}", "b": "true", "o": "text:equal"}]]}
    s.flow.append(reserve)
    key_q = f"{{{{encodeURL({rd}.data.id)}}}}%3A{{{{encodeURL({rd}.data.resolved_at)}}}}"
    ticket_src = {"Config": cfg_all, "Read the ticket": f"{{{{{rd}.data}}}}"}

    # Steps 3 and 4: replace the customer's details; if any remain, set the ticket aside with no AI call.
    js = (f"const r = one((() => {{\n{N8N.STEP3_JS.strip()}\n}})())[0];\n"
          f"DATA[{json.dumps(S34)}] = [{{ json: r }}];\n"
          f"if (r.clean) return [{{ json: Object.assign({{ route: 'clean' }}, r) }}];\n"
          f"return [{{ json: Object.assign({{}}, r, one((() => {{ {SET_ASIDE_JS} }})())[0]) }}];")
    code, inputs = n8n_rule(js, ticket_src, bodies=closing_bodies())
    step34 = s.code(S34, code, inputs)
    step34["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: this resolution was drafted before
    s.flow.append(step34)
    failed = lambda step, rule: s.write_failed(step, key_q, out(rule, "failed_body"))  # noqa: E731

    def closing(tag: str, rule: str, draft_write: dict | None = None) -> list[dict]:
        """Mark the key done and log the decision; on the draft route the draft's ID fills the marker."""
        fill = (lambda f: "{{" + f"replace({s.ref(rule)}.result.{f}; \"{DID}\"; {draft_write['id']}.data.id)" + "}}") if draft_write \
            else (lambda f: out(rule, f))
        return [s.finish_key(f"Mark key done ({tag})", key_q, fill("done_body")),
                s.decision_log(f"Decision log ({tag})", fill("log_body"))]

    set_aside = [s.exception("Exception queue: set aside for the article owner (personal data remains)", out(S34, "exception_body"))]
    set_aside += closing("personal data remains", S34)

    # Step 5: the AI drafts the article from the cleaned text, three tries.
    s3 = f"$('{S34}').first().json"
    vars_js = f"{{ article_template: {CFG}.article_template, subject: {s3}.subject, ticket_text: {s3}.ticket_text }}"
    ai = s.ai_step("Step 5", ROOT / "recipes/R13.3/prompts/draft-article.md", vars_js,
                   {"Config": cfg_all, S34: "{{" + f"{step34['id']}.result" + "}}"}, max_tokens=1200, tries=3)
    call = s.ref(CALL)
    articles = s.http(ARTICLES, "GET", cfg("kb_url") + "/articles", query={"_wrap": "1"})

    # Steps 6 to 9: the rules decide what the draft holds; nothing is published here.
    code, inputs = n8n_rule(N8N.RULES_JS, {**ticket_src, CALL: "{{" + f"{call}.data" + "}}",
                                           ARTICLES: "{{" + f"{articles['id']}.data" + "}}"},
                            ai_status="{{" + f"{call}.statusCode" + "}}", on_ai_error=AI_ERROR_JS, bodies={
        **closing_bodies(),
        "draft_body": "out.route === 'draft' ? JSON.stringify(out.draft) : null",
        "needs_source": "out.route === 'draft' && out.owners.length ? 'yes' : 'no'",
        "tell_body": (f"out.route === 'draft' ? JSON.stringify({{ to: {CFG}.article_owner, "
                      "subject: (out.draft.kind === 'suggested update' ? 'Suggested update: ' : 'Draft article: ') + out.draft.title, "
                      f"text: 'Draft {DID} from ticket ' + out.draft.ticket_id + ' waits for you to edit and approve or discard.' + "
                      "(out.owners.length ? ' Held for the source owner: ' + out.owners.join(', ') + '.' : '') }) : null"),
        "ask_body": (f"out.route === 'draft' ? JSON.stringify({{ to: out.owners, subject: 'Needs source: draft {DID}', "
                     "text: 'Please word these claims from your source before the article is published: ' + "
                     "out.draft.claims.filter(c => c.needs_source).map(c => c.text).join(' | ') }) : null"),
    })
    rules = s.code(RULES, code, inputs)

    # Step 10: the draft goes to the article owner; "needs source" claims go to their source's owner.
    write_name = "Step 10: Write the draft for the article owner"
    write = s.http(write_name, "POST", cfg("drafts_url") + "/drafts", body=out(RULES, "draft_body"),
                   onerror=failed(write_name, RULES))
    filled = lambda f: "{{" + f"replace({rules['id']}.result.{f}; \"{DID}\"; {write['id']}.data.id)" + "}}"  # noqa: E731
    tell_name, ask_name = "Step 10: Tell the article owner", "Step 10: Ask the source owners to word the claims"
    tell = s.http(tell_name, "POST", cfg("messaging_url") + "/messages", body=filled("tell_body"), parse=False,
                  onerror=failed(tell_name, RULES))
    ask = s.http(ask_name, "POST", cfg("messaging_url") + "/messages", body=filled("ask_body"), parse=False,
                 onerror=failed(ask_name, RULES))
    needs = out(RULES, "needs_source")
    drafted = [write, tell, s.router("Needs source?", [
        (s.when("needs source", needs, "yes"), [ask] + closing("draft, needs source", RULES, write)),
        (s.when("no claim needs a source", needs, "yes", "text:notequal"), closing("draft", RULES, write)),
    ])]
    route = out(RULES, "route")
    checked = [s.router("Draft or exception?", [
        (s.when("draft", route, "draft"), drafted),
        (s.when("set aside", route, "set_aside"),
         [s.exception("Exception queue: set aside for the article owner (draft checks)", out(RULES, "exception_body"))]
         + closing("set aside", RULES)),
        (s.when("discard", route, "discard"),
         [s.exception("Step 6: Exception queue: draft discarded", out(RULES, "exception_body"))] + closing("draft discarded", RULES)),
    ])]
    clean = out(S34, "route")
    s.flow.append(s.router("Step 4: None remain?", [
        (s.when("none remain", clean, "clean"), ai + [articles, rules] + checked),
        (s.when("personal data remains", clean, "clean", "text:notequal"), set_aside),
    ]))
    return s


def decision() -> Scenario:
    s = Scenario(R, "R13.3 Draft decided: publish it, or discard it", "webhook", test_key="r13-3-draft-decision")
    s.flow.append(s.webhook(D))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()

    # Step 10: the draft, and the decision's key (draft and decision).
    read = s.http("Read the draft", "GET", cfg("drafts_url") + "/drafts/{{encodeURL(1.draft_id)}}")
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    s.flow.append(s.reserve_key("Step 10: Reserve key", "{{1.draft_id}}:{{1.decision}}"))
    key_q = "{{encodeURL(1.draft_id)}}%3A{{encodeURL(1.decision)}}"
    dec = "out"
    prelude, ev_inputs = body_prelude(D, ("draft_id", "decision", "by"))
    code, inputs = n8n_rule(N8N.DECIDE_JS, {"Config": "{{" + f"{c}.result" + "}}", "Read the draft": "{{" + f"{read['id']}.data" + "}}"},
                            prelude=prelude, bodies={
        "article_body": f"{dec}.article ? JSON.stringify({dec}.article) : null",
        "register_body": (f"{dec}.article ? JSON.stringify({{ id: 'KB-{AID}', title: {dec}.article.title, owner: {CFG}.article_owner, "
                          f"delegate: null, audience: {CFG}.article_audience, review_date: {dec}.review_date, expiry_date: {dec}.expiry_date, "
                          f"status: 'current', version: '1.0', link: {CFG}.kb_url + '/articles/{AID}', kb_article: '{AID}' }}) : null"),
        "blocked_body": (f"{dec}.outcome === 'refuse' ? JSON.stringify({{ recipe: '{R}', item: {DEV}.draft_id, reason: 'approval blocked', "
                         f"detail: {dec}.reason, owner: {CFG}.article_owner }}) : null"),
        "done_body": f"JSON.stringify({{ status: 'done', result: {dec}.outcome }})",
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {DEV}.draft_id, "
                     f"decision: {dec}.outcome === 'refuse' ? 'approval blocked' : {dec}.outcome.replace('_', ' '), "
                     f"rules: {{ ticket: {DR}.ticket_id, reason: {dec}.reason || null }}, "
                     f"approved_by: {dec}.outcome === 'refuse' ? null : {DEV}.by }})"),
        "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: {DEV}.draft_id, reason: 'write failed', "
                        "detail: 'Publishing or registering failed part way; check the knowledge base and register, never retried', "
                        f"owner: {CFG}.article_owner }})"),
    })
    rule = s.code(DECIDE, code, {**ev_inputs, **inputs})
    rule["filter"] = s.is_new_key("Step 10: Reserve key")  # a copy stops here: this decision was handled before
    s.flow.append(rule)
    out = lambda f: "{{" + f"{rule['id']}.result.{f}" + "}}"  # noqa: E731

    def write(name: str, method: str, url: str, body: str, parse: bool = False) -> dict:
        return s.http(name, method, url, body=body, parse=parse, onerror=s.write_failed(name, key_q, out("failed_body")))

    def closing(tag: str) -> list[dict]:
        return [s.finish_key(f"Step 10: Mark key done ({tag})", key_q, out("done_body")),
                s.decision_log(f"Step 10: Decision log ({tag})", out("log_body"))]

    # Step 11: publish, register with review and expiry dates (so R13.2 watches it), and close the draft.
    draft_url = cfg("drafts_url") + "/drafts/{{encodeURL(1.draft_id)}}"
    publish = write("Step 11: Publish the article", "POST", cfg("kb_url") + "/articles", out("article_body"), parse=True)
    register = write("Step 11: Register the article", "POST", cfg("register_url") + "/sources",
                     "{{" + f"replace({rule['id']}.result.register_body; \"{AID}\"; {publish['id']}.data.id)" + "}}")
    published = '{"status": "published"}'
    new = [publish, register, write("Step 11: Set the draft published (new article)", "PATCH", draft_url, published)] + closing("published new")
    update = [write("Step 11: Publish the suggested update", "PATCH",
                    cfg("kb_url") + "/articles/{{encodeURL(" + f"{read['id']}.data.updates_article" + ")}}", out("article_body")),
              write("Step 11: Set the draft published (suggested update)", "PATCH", draft_url, published)] + closing("published update")
    discard = [write("Step 10: Set the draft discarded", "PATCH", draft_url, '{"status": "discarded"}')] + closing("discarded")
    refuse = [s.exception("Step 10: Exception queue: approval blocked", out("blocked_body"))] + closing("approval blocked")
    outcome = out("outcome")
    s.flow.append(s.router("Decision", [
        (s.when("publish new", outcome, "publish_new"), new),
        (s.when("publish update", outcome, "publish_update"), update),
        (s.when("discard", outcome, "discard"), discard),
        (s.when("refuse", outcome, "refuse"), refuse),
    ]))
    return s


def weekly() -> Scenario:
    """The failure table: each week, tell the article owner how many drafts wait over 14 days."""
    s = Scenario(R, "R13.3 Draft knowledge articles: each week", "schedule", test_key=W, schedule="every Monday at 08:00")
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    read = s.http("Read drafts awaiting approval", "GET", cfg("drafts_url") + "/drafts",
                  query={"_wrap": "1", "status": "awaiting approval"})
    read["filter"] = s.continue_unless_stopped()
    s.flow.append(read)
    code, inputs = n8n_rule(N8N.WEEKLY_JS, {"Config": "{{" + f"{c}.result" + "}}", "Read drafts awaiting approval": "{{" + f"{read['id']}.data" + "}}"},
                            bodies={"message": (f"out.count > 0 ? JSON.stringify({{ to: {CFG}.article_owner, "
                                                f"subject: out.count + ' drafts waiting over ' + {CFG}.old_draft_days + ' days', "
                                                "text: 'Approve or discard: ' + out.ids.join(', ') }) : null")})
    rule = s.code("Rule: drafts over 14 days old", code, inputs)
    s.flow.append(rule)
    tell = s.http("Tell the article owner to clear them", "POST", cfg("messaging_url") + "/messages",
                  body="{{" + f"{rule['id']}.result.message" + "}}", parse=False)
    tell["filter"] = s.when("any old drafts", "{{" + f"{rule['id']}.result.message" + "}}", "", "exist")  # none ends here
    s.flow.append(tell)
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R13.3/make/, scenario)."""
    return [("blueprint.json", ticket()), ("decision.blueprint.json", decision()), ("weekly.blueprint.json", weekly())]
