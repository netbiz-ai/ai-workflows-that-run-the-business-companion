"""R6.2 Remind the owner and draft a follow-up when a quote goes quiet, as a Make scenario.

Source: book Chapter 6, recipe R6.2, Table 6.2 and build steps 1 to 8 (recipes/R6.2/build-spec.md);
AI step: recipes/R6.2/prompts/draft-follow-up.md. The rules are the n8n build's own JavaScript
(tools/builds/r6_2.py), run through n8n_rule.
One scenario, on a schedule: Monday to Friday at 07:00, before the trade desk opens (set the
scenario's time zone in Make, or the run moves at each daylight-saving change).
The rules use plain Date in UTC, which Make's Code app has, so no shim is needed.

Where the Make build differs from the n8n canvas, and why:
- Step 3 returns one item per quote that gets something today; an iterator runs the rest of the
  scenario once per quote, as n8n runs its per-item nodes.
- The new-key check and n8n's "Which row?" switch are one router: each route's filter asks for a
  new key and the row. Branches never meet again, so each route repeats the closing steps.
- Step 6 tries the AI call three times (book). mk.ai_step tries twice, so the second try's error
  route holds a third, and Make's Resume handler hands its answer back.
- n8n's "Step 7: AI error", "Step 7: Rule: check the draft" and "Step 8: Fill the quote reference"
  run in one Code step, in the same order, because each Code step costs credits.
"""

import copy
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R6.2"
N8N = n8n_build(R)
T, SORT, CFG, Q = N8N.T, N8N.SORT, N8N.CFG, f"$('{N8N.SORT}').item.json"
STEP5 = "Step 5: Rule: the reminder, no draft"
AI_ERROR_JS = "return { json: { draft: null, check: 'dropped: AI error after three retries' } };"
CONFIG = {
    "crm_url": "https://<your CRM API>",
    "messaging_url": "https://<your Teams messaging API>",
    "window_working_days": 5,
    "gap_days": 3,
    "reminder_limit": 3,
    "never_say": ["discount", "price match", "free"],
    "max_draft_words": 120,
    "sales_lead": "<your sales lead>",
    "covers": {"<an absent salesperson>": "<their cover>"},
    "task_source": "R6.2 quiet-quote reminder",
    "crm_admin": "<your CRM admin>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
# The closing bodies of steps 5 and 8 (out: that step's result).
CLOSE = {
    "task_body": "JSON.stringify(out.task_body)",
    "post_body": "JSON.stringify({ to: out.to, subject: out.subject, text: out.text, draft: out.draft || null })",
    "done_body": "JSON.stringify({ status: 'done', result: out.decision })",
    "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {Q}.quote_id, decision: out.decision, "
                 f"rules: Object.assign({{ revision: {Q}.revision, reminder: {Q}.reminder }}, out.rules) }})"),
}


def brace_safe(js: str) -> str:
    """Make reads {{ in a Code step's script as a mapping; inside these rules' string literals it is
    written \\u007b{, which JavaScript reads back as the same text."""
    return re.sub(r"\{(?=\{)", r"\\u007b", js)


def part(js: str) -> str:
    """One n8n Code node's JavaScript as a function of $json, for a Code step that runs several in turn."""
    return "(($json) => {\n" + js.strip() + "\n})"


def resume(s: Scenario, after: dict) -> dict:
    """Make's Resume handler: the failed step's output becomes this later try's answer."""
    return {"id": s._id(f"_resume{s._next}"), "module": "builtin:Resume", "version": 1, "parameters": {},
            "mapper": {k: "{{" + f"{after['id']}.{k}" + "}}" for k in ("statusCode", "data", "headers")},
            "metadata": {"designer": {}}}


def third_try(s: Scenario, call: dict) -> None:
    """Give mk.ai_step's two tries a third: the second try's error route holds it."""
    second = call["onerror"][0]
    third = copy.deepcopy(second)
    name = second["metadata"]["designer"]["name"].replace("second try", "third try")
    third["id"] = s._id(name)
    third["metadata"]["designer"]["name"] = name
    second["mapper"]["stopOnHttpError"] = True
    second["onerror"] = [third, resume(s, third)]


def build() -> list[tuple[str, Scenario]]:
    s = Scenario(R, "R6.2 Remind the owner and draft a follow-up when a quote goes quiet", "schedule",
                 test_key=T, schedule="Monday to Friday at 07:00")
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    conf = "{{" + f"{c}.result" + "}}"
    s.flow += s.stop_flag()
    crm = cfg("crm_url")
    sent = s.http("Step 2: CRM: List sent quotes", "GET", crm + "/quotes", query={"_wrap": "1", "status": "sent"})
    sent["filter"] = s.continue_unless_stopped()
    s.flow += [sent,
               s.http("CRM: Read account flags", "GET", crm + "/accounts", query={"_wrap": "1"}),
               s.http("CRM: Read reminder tasks", "GET", crm + "/tasks", query={"_wrap": "1", "source": cfg("task_source")})]
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731

    # ---- Step 3: Table 6.2, one item per quote that gets something today ------------------
    names = ("Step 2: CRM: List sent quotes", "CRM: Read account flags", "CRM: Read reminder tasks")
    code, inputs = n8n_rule(N8N.SORT_JS, {"Config": conf, **{n: data(n) for n in names}}, many=True, bodies={
        "self": "JSON.stringify(out)",
        "reserve_body": f"JSON.stringify({{ p_recipe: '{R}', p_key: out.key }})",
        "key_q": "encodeURIComponent(out.key)",
        "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: out.quote_id, reason: 'write failed', "
                        f"detail: 'Task or Teams post failed; check the CRM before anything is redone', owner: {CFG}.crm_admin }})"),
    })
    s.flow.append(s.code(SORT, code, inputs))
    s.flow.append(s.iterator("Each quote", "{{" + f"{s.ref(SORT)}.result.items" + "}}"))
    q = lambda f: "{{" + f"{s.ref('Each quote')}.{f}" + "}}"  # noqa: E731
    # ---- Step 4: one key per quote, revision and reminder (or per dispute notice) ----------
    s.flow.append(s.rpc("Step 4: Reserve key", "reserve_key", q("reserve_body")))
    sources = {"Config": conf, SORT: q("self")}
    failed = lambda step: s.write_failed(step, q("key_q"), q("failed_body"))  # noqa: E731

    def close(step: str, out, tag: str, task: bool) -> list[dict]:
        """Task the owner or cover (unless the row tells the sales lead), post in Teams, mark done, log."""
        flow = [s.http(f"{step}: CRM: Task the owner or cover", "POST", crm + "/tasks", body=out("task_body"), parse=False,
                       onerror=failed(f"{step}: CRM: Task the owner or cover"))] if task else []
        post = f"{step}: Teams: Post the reminder" + (" and any draft" if step == "Step 8" else "") + (f" ({tag})" if tag else "")
        return flow + [s.http(post, "POST", cfg("messaging_url") + "/messages", body=out("post_body"), parse=False, onerror=failed(post)),
                       s.finish_key(f"{step}: Mark key done" + (f" ({tag})" if tag else ""), q("key_q"), out("done_body")),
                       s.decision_log(f"{step}: Decision log" + (f" ({tag})" if tag else ""), out("log_body"))]

    # ---- Step 5: dispute, expiry and last-reminder rows, no draft --------------------------
    code, inputs = n8n_rule(N8N.STEP5_JS, sources, bodies=CLOSE)
    step5 = s.code(STEP5, code, inputs)
    s5 = lambda f: "{{" + f"{s.ref(STEP5)}.result.{f}" + "}}"  # noqa: E731
    no_draft = [step5, s.router("Task?", [
        (s.when("task the owner", s5("task"), "true"), close("Step 5", s5, "task", True)),
        (s.when("tell the sales lead", s5("task"), "true", "text:notequal"), close("Step 5", s5, "sales lead told", False)),
    ])]

    # ---- Steps 6 to 8: the last row, with an AI draft ---------------------------------------
    vars_js = (f"{{ never_say_phrases: {CFG}.never_say.map(p => '\"' + p + '\"').join(', '), "
               f"quote_description: {Q}.description, last_activity_summary: {Q}.summary }}")
    ai = s.ai_step("Step 6", ROOT / "recipes/R6.2/prompts/draft-follow-up.md", vars_js, sources, max_tokens=2048, tries=2)
    third_try(s, ai[1])
    call = s.ref("Step 6: AI call")
    js = ("const __ok = Number(input.ai_status) === 200;\n"
          f"const __check = one(__ok ? {part(N8N.CHECK_JS)}($json) : {part(AI_ERROR_JS)}({{}}))[0];\n"
          f"DATA[__ok ? 'Step 7: Rule: check the draft' : 'Step 7: AI error'] = [{{ json: __check }}];\n"
          f"return {part(N8N.STEP8_JS)}(__check);")
    code, inputs = n8n_rule(brace_safe(js), {**sources, "Step 6: AI call": "{{" + f"{call}.data" + "}}"}, bodies=CLOSE)
    inputs["ai_status"] = "{{" + f"{call}.statusCode" + "}}"
    name = "Steps 7 and 8: Check the draft, fill the quote reference"
    step8 = s.code(name, code, inputs)
    s8 = lambda f: "{{" + f"{s.ref(name)}.result.{f}" + "}}"  # noqa: E731
    with_draft = ai + [step8] + close("Step 8", s8, "", True)

    new = {"a": "{{" + f"{s.ref('Step 4: Reserve key')}.data" + "}}", "b": "true", "o": "text:equal"}

    def row(label: str, op: str) -> dict:
        """A new key (a used one skips: this reminder or dispute notice was sent before), and the row."""
        return {"name": label, "conditions": [[new, {"a": q("row"), "b": "due", "o": op}]]}

    s.flow.append(s.router("Which row?", [(row("new key, row 6 (due)", "text:equal"), with_draft),
                                          (row("new key, dispute, expiry or last reminder", "text:notequal"), no_draft)]))
    return [("blueprint.json", s)]
