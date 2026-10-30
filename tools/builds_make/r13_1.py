"""R13.1 Answer staff questions from approved sources, with citations and a refusal path, as a Make scenario.

Source: book Chapter 13, recipe R13.1, build steps 1 to 13 and Table 13.2 (recipes/R13.1/build-spec.md);
AI step: recipes/R13.1/prompts/answer.md. The rules are the n8n build's own JavaScript
(tools/builds/r13_1.py), run through n8n_rule.
Differences from the n8n build, all forced by Make:
- n8n's paths all meet again at "Outcome" before one closing run (reply, pass to HR, gap row,
  mark the key done, decision log). Make's routes never meet, so each route carries its own
  closing steps, with the route in each step's name. Where a route's outcome always has a reply,
  never has one, or always logs a gap, n8n's "Reply to send?", "HR question?" and "Gap?" checks
  are settled by the route itself; only the steps 9 to 12 rule can end with or without a gap, so
  that route keeps "Gap?" as a router.
- n8n's "Step 13: AI error" node takes the AI call's error output. In Make the AI call tries
  three times (mk.ai_step tries=3, each failed try handing over in its error route), and
  "Step 8: AI answered?" routes on the last try's status: 200 goes on to step 11's read and the
  rules, anything else to "Step 13: AI error", a Code step running n8n's node (on_ai_error).
- n8n's custom SQL for the answer a "wrong" reply points at is a table-API read of that
  answer's latest R13.1 decision-log row; the rule's prelude takes its owner and topic.
- Step 7's live sharing reads run once per document through an iterator, and an aggregator
  hands every answer to "Step 7: Rule: drop documents the asker cannot open", as n8n's .all().
- Step 5's audience is the asker followed by their groups, joined with commas as in n8n
  (merge and join), and the as-of date is today in UTC, as n8n's toISOString().
- One rule passes its result to the next as JSON text, so empty values and lists reach the next
  rule exactly as the n8n rule returned them. The step 8 request reads the question from step 7's
  rule, which hands on the webhook's body, because a Make webhook cannot be mapped whole.
- Mark key failed records "write failed" without the HTTP error text, which Make's error route
  does not hand to a later body.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R13.1"
N8N = n8n_build(R)
T = N8N.T
FIELDS = ("message_id", "conversation_id", "asker", "text", "reply_to")
CONFIG = {
    "chat_url": "https://<your staff chat API>",
    "directory_url": "https://<your directory API>",
    "index_url": "https://<your answer index API>",
    "documents_url": "https://<your document home API>",
    "register_url": "https://<your source register API>",
    "hr_phrases": ["<your personal HR phrasings, such as \"my pay\">"],
    "hr_fixed_reply": "<R9.2's fixed reply, naming who to ask>",
    "hr_contact": "<your HR manager>",
    "price_phrases": ["<your price phrasings, such as \"how much is\">"],
    "price_list_link": "https://<your price list in the CRM>",
    "policy_figures": ["<your owner-approved policy figures, such as the meal allowance>"],
    "relevance_threshold": "<your threshold, tuned on last month's questions>",
    "max_passages": 5,
    "gap_owner": "<your fallback topic owner>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
CFG = "$('Config').first().json"
EV = f"$('{T}').first().json.body"
S3, S6, S7 = "Step 3: Rules: HR, price or 'wrong'?", "Step 6: Rule: above the relevance threshold?", "Step 7: Rule: drop documents the asker cannot open"
HR, PRICE, WRONG = "Step 3: R9.2's fixed reply", "Step 3: Price-list link", "Table 13.2: 'wrong' logs a gap"
FILES, SHARING, SHARED = "Step 7: Documents to check", "Step 7: Read live sharing", "Step 7: Sharing read"
RULES, AI_ERROR, CALL = "Rules: steps 9 to 12", "Step 13: AI error", "Step 8: AI call"
LOG = "Read the answer's decision log"
GROUPS, SEARCH, REG, REG2 = ("Step 4: Read the asker's groups", "Step 5: Search current, in-date passages",
                             "Read the source register", "Step 11: Read the source register again")
AS_JSON = "JSON.stringify(out)"  # a rule's whole result, for the next rule

# n8n's custom SQL: the owner and topic of the latest R13.1 decision for the answer the asker says is wrong.
LOG_PRELUDE = r"""
// n8n's custom SQL, from the table read of the answer's latest R13.1 decision-log row.
const __raw = DATA["Read the answer's decision log"][0].json;
const __rows = Array.isArray(__raw) ? __raw : (__raw && typeof __raw === 'object' ? Object.values(__raw) : []);
const __rules = r => (r && (typeof r.rules === 'string' ? JSON.parse(r.rules) : r.rules)) || {};
const __last = __rules(__rows[0]);
DATA["Read the answer's decision log"] = [{ json: { owner: __last.owner || null, topic: __last.topic || null } }];
"""


def trigger_body() -> tuple[str, dict[str, str]]:
    """(prelude, inputs): the webhook's fields, rebuilt as n8n's $('<trigger>').first().json.body."""
    inputs = {f"t_{f}": "{{1." + f + "}}" for f in FIELDS}
    body = ", ".join(f"{json.dumps(f)}: input.t_{f}" for f in FIELDS)
    prelude = (f"// The webhook's fields, as the rule reads them in n8n: $('{T}').first().json.body.\n"
               f"DATA[{json.dumps(T)}] = [{{ json: {{ body: {{ {body} }} }} }}];")
    return prelude, inputs


def rule(js: str, sources: dict[str, str], prelude: str = "", **kw) -> tuple[str, dict[str, str]]:
    """n8n_rule, with the scenario's webhook body added."""
    pre, inputs = trigger_body()
    code, rest = n8n_rule(js, sources, prelude=pre + "\n" + prelude, **kw)
    return code, {**inputs, **rest}


# Table 13.2's closing writes, from an outcome rule's out (n8n's "Outcome" node).
OUTCOME_BODIES = {
    "reply_body": (f"JSON.stringify({{ conversation_id: {EV}.conversation_id, reply_to: {EV}.message_id, "
                   f"to: {EV}.asker, text: out.reply }})"),
    "hr_body": (f"JSON.stringify({{ to: {CFG}.hr_contact, subject: 'Personal HR question from ' + {EV}.asker, "
                f"text: {EV}.text }})"),
    "has_gap": "!!out.gap",
    "gap_body": (f"out.gap ? JSON.stringify({{ recipe: '{R}', item: {EV}.message_id, reason: 'gap', "
                 "detail: out.gap.topic, owner: out.gap.owner }) : null"),
    "done_body": "JSON.stringify({ status: 'done', result: out.outcome })",
    "log_body": f"JSON.stringify({{ recipe: '{R}', item: {EV}.message_id, decision: out.decision, rules: out.rules }})",
    "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.message_id, reason: 'write failed', "
                    f"detail: 'Reply or hand-off failed; check the conversation, never retried', owner: {CFG}.gap_owner }})"),
}


def answer() -> Scenario:
    s = Scenario(R, "R13.1 Answer staff questions from approved sources", "webhook", test_key="r13-1-question")
    s.flow.append(s.webhook(T))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    conf = "{{" + f"{c}.result" + "}}"
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    out = lambda n, f: "{{" + f"{s.ref(n)}.result.{f}" + "}}"  # noqa: E731
    s.flow += s.stop_flag()
    key_q = "{{encodeURL(1.message_id)}}"
    messages = cfg("chat_url") + "/messages"

    def closing(tag: str, rule_name: str, *, reply: bool = True, hr: bool = False, gap: bool | None = False) -> list[dict]:
        """Table 13.2's closing steps for one route: the reply, the hand-off to HR, the gap row,
        mark the key done, the decision log. gap None: the rule decides (n8n's "Gap?")."""
        o = lambda f: out(rule_name, f)  # noqa: E731
        steps = []
        if reply:
            name = f"Steps 12 and 13: Reply to the asker ({tag})"
            steps.append(s.http(name, "POST", messages, body=o("reply_body"), parse=False,
                                onerror=s.write_failed(name, key_q, o("failed_body"))))
        if hr:
            name = f"Step 3: Pass the question to HR ({tag})"
            steps.append(s.http(name, "POST", messages, body=o("hr_body"), parse=False,
                                onerror=s.write_failed(name, key_q, o("failed_body"))))

        def done(t: str) -> list[dict]:
            return [s.finish_key(f"Mark key done ({t})", key_q, o("done_body")),
                    s.decision_log(f"Decision log ({t})", o("log_body"))]
        gap_row = lambda t: s.exception(f"Exception queue: gap ({t})", o("gap_body"))  # noqa: E731
        if gap is None:
            steps.append(s.router(f"Gap? ({tag})", [
                (s.when("a gap", o("has_gap"), "true"), [gap_row(f"{tag}, gap")] + done(f"{tag}, gap")),
                (s.when("no gap", o("has_gap"), "true", "text:notequal"), done(f"{tag}, no gap")),
            ]))
        else:
            steps += ([gap_row(tag)] if gap else []) + done(tag)
        return steps

    # ---- steps 2 and 3 ------------------------------------------------------------------------------
    reserve = s.reserve_key("Step 2: Reserve key", "{{1.message_id}}")
    reserve["filter"] = s.continue_unless_stopped()
    s.flow.append(reserve)
    code, inputs = rule(N8N.STEP3_JS, {"Config": conf})
    step3 = s.code(S3, code, inputs)
    step3["filter"] = s.is_new_key("Step 2: Reserve key")  # a copy stops here: this message was answered before
    s.flow.append(step3)

    def outcome_rule(name: str, js: str, sources: dict[str, str], **kw) -> dict:
        code, inputs = rule(js, {"Config": conf, **sources}, bodies={**OUTCOME_BODIES, **kw.pop("bodies", {})}, **kw)
        return s.code(name, code, inputs)

    hr = [outcome_rule(HR, N8N.HR_JS, {})] + closing("HR", HR, hr=True)
    price = [outcome_rule(PRICE, N8N.PRICE_JS, {})] + closing("price", PRICE)
    read_log = s.http(LOG, "GET", s.table(f"/decision_log?recipe=eq.{R}&item=eq.{{{{encodeURL(1.reply_to)}}}}&order=id.desc&limit=1"))
    wrong = [read_log, outcome_rule(WRONG, N8N.WRONG_JS, {LOG: data(LOG)}, prelude=LOG_PRELUDE)]
    wrong += closing("reported wrong", WRONG, reply=False, gap=True)

    # ---- steps 4 to 6 ---------------------------------------------------------------------------------
    groups = s.http(GROUPS, "GET", cfg("directory_url") + "/users/{{encodeURL(1.asker)}}")
    g = s.ref(GROUPS)
    search = s.http(SEARCH, "GET", cfg("index_url") + "/search", query={
        "_wrap": "1", "q": "{{1.text}}", "status": "current", "as_of": '{{formatDate(now; "YYYY-MM-DD"; "UTC")}}',
        "audience": "{{" + f'join(merge(split(1.asker; ","); {g}.data.groups); ",")' + "}}"})
    register = s.http(REG, "GET", cfg("register_url") + "/sources", query={"_wrap": "1"})
    step6 = outcome_rule(S6, N8N.STEP6_JS, {REG: data(REG), SEARCH: data(SEARCH)}, input_node=SEARCH,
                         bodies={"as_json": AS_JSON})
    s6 = out(S6, "as_json")

    # ---- step 7 ---------------------------------------------------------------------------------------
    code, inputs = n8n_rule(N8N.FILES_JS, {S6: s6}, many=True)
    files = s.code(FILES, code, inputs)
    each = s.iterator("Step 7: Each document", out(FILES, "items"))
    sharing = s.http(SHARING, "GET", cfg("documents_url") + "/files/{{" + f"encodeURL({s.ref('Step 7: Each document')}.file_id)" + "}}")
    sh = s.ref(SHARING)
    gathered = s.aggregator(SHARED, "Step 7: Each document", {"id": "{{" + f"{sh}.data.id" + "}}",
                                                              "shared_with": "{{" + f"{sh}.data.shared_with" + "}}"})
    step7 = outcome_rule(S7, N8N.STEP7_JS, {REG: data(REG), S6: s6, GROUPS: data(GROUPS),
                                            SHARING: "{{" + f"{s.ref(SHARED)}.array" + "}}"},
                         items=(SHARING,), input_node=S6,
                         bodies={"as_json": AS_JSON, "trigger_json": f"JSON.stringify({{ body: {EV} }})"})
    s7 = out(S7, "as_json")

    # ---- steps 8 to 13 --------------------------------------------------------------------------------
    s7_js = f"$('{S7}').first().json"
    reg_js = f"Object.fromEntries(($('{REG}').first().json.items || []).map(r => [String(r.id), r]))"
    vars_js = (f"(() => {{ const reg = {reg_js}; return {{ question: {EV}.text, passages: {s7_js}.passages.map(p => "
               "`[${p.id}] ${(reg[String(p.source)] || {}).title || p.source} (effective ${p.effective})\\n<<<\\n${p.text}\\n>>>`).join('\\n\\n') }; })()")
    ai = s.ai_step("Step 8", ROOT / "recipes/R13.1/prompts/answer.md", vars_js,
                   {"Config": conf, REG: data(REG), S7: s7, T: out(S7, "trigger_json")}, max_tokens=600, tries=3)
    call = "{{" + f"{s.ref(CALL)}.statusCode" + "}}"
    again = s.http(REG2, "GET", cfg("register_url") + "/sources", query={"_wrap": "1"})
    rules = outcome_rule(RULES, N8N.RULES_JS, {REG: data(REG), S7: s7, REG2: data(REG2), CALL: "{{" + f"{s.ref(CALL)}.data" + "}}"},
                         input_node=REG2)
    # n8n's "Step 13: AI error" node, as the AI-error code of a Code step that only runs after a failed call.
    ai_error = outcome_rule(AI_ERROR, "return [];", {CALL: "{{" + f"{s.ref(CALL)}.data" + "}}"},
                            ai_status=call, on_ai_error=N8N.AI_ERROR_JS)
    drafted = ai + [s.router("Step 8: AI answered?", [
        (s.when("the AI answered", call, "200"), [again, rules] + closing("rules", RULES, gap=None)),
        (s.when("AI error after two retries", call, "200", "text:notequal"), [ai_error] + closing("AI error", AI_ERROR)),
    ])]
    left = out(S7, "route")
    open_docs = [files, each, sharing, gathered, step7, s.router("Any left?", [
        (s.when("documents left", left, "continue"), drafted),
        (s.when("none open to the asker", left, "continue", "text:notequal"), closing("none open", S7, gap=True)),
    ])]
    above = out(S6, "route")
    searched = [groups, search, register, step6, s.router("Any above the threshold?", [
        (s.when("passages above the threshold", above, "continue"), open_docs),
        (s.when("none above the threshold", above, "continue", "text:notequal"), closing("below the threshold", S6, gap=True)),
    ])]

    route = out(S3, "route")
    s.flow.append(s.router("Step 3: Route", [
        (s.when("hr", route, "hr"), hr),
        (s.when("price", route, "price"), price),
        (s.when("wrong", route, "wrong"), wrong),
        (s.when("search", route, "search"), searched),
    ]))
    return s


def build() -> list[tuple[str, Scenario]]:
    """(reader file name under recipes/R13.1/make/, scenario)."""
    return [("blueprint.json", answer())]
