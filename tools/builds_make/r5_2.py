"""R5.2 Prepare a research and qualification brief for the salesperson, as a Make scenario.

Source: book Chapter 5, recipe R5.2, build steps 1 to 6 (recipes/R5.2/build-spec.md);
AI step: recipes/R5.2/prompts/draft-brief.md. The rules are the n8n build's own JavaScript
(tools/builds/r5_2.py), run through n8n_rule.
One scenario: the lead assigned to a salesperson (webhook).

Where the Make build differs from the n8n canvas, and why:
- Step 3's page fetch runs once per page, as n8n's per-item HTTP node does: an iterator over the
  pages to fetch, then an aggregator gathers each page's answer for "Step 3: Sources", which reads
  them as n8n's $input.all(). A lead with no allowed page sends no bundle to the fetch, and the
  aggregator then passes an empty list on, so "Step 3: Sources" lists the CRM records only, as in n8n.
- Each page is tried twice, as n8n's maxTries 2: the first try's error route holds the second,
  and Make's Resume handler hands its answer back. A page that fails twice reaches the rules with
  its HTTP status, which the adapter turns into n8n's error item ("not fetched").
- n8n's "Step 5: AI error" node, step 5's rule and step 6's note run in one Code step, in the
  same order, because Make branches never meet again and each Code step costs credits.
- The rules read the webhook body as n8n's $('Step 1: Lead assigned').first().json.body; a Make
  webhook's output cannot be mapped whole, so the adapter rebuilds it from the lead_id field.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "make"))
from mk import Scenario, n8n_build, n8n_rule  # noqa: E402

R = "R5.2"
N8N = n8n_build(R)
T, EV, LEAD = N8N.T, N8N.EV, N8N.LEAD
CHECK = "Step 5: Rule: valid, sourced, no page instructions?"
FETCH = "Step 3: Fetch page"
AI_ERROR_JS = ("return [{ json: { status: 'ai error', problems: ['AI error after one retry: ' + "
               "String(($json.error && $json.error.message) || '')] } }];")
CONFIG = {
    "crm_url": "https://<your CRM API>",
    "criteria": [{"name": "<criterion>", "description": "<what a source must say for it to be met>"}],
    "allowed_sources": ["https://<an agreed public source type, such as your city's planning notices>/"],
    "max_pages": 5,
    "page_text_limit": 6000,
    "injection_phrases": ["ignore your", "ignore previous", "ignore all previous", "disregard your", "new instructions"],
    "unverified_label": "Unverified: check sources",
    "brief_owner": "<your sales lead>",
    "ai_model": "claude-haiku-5-5",
    "ai_inference_geo": "us",
    "ai_url": "https://api.anthropic.com/v1/messages",
}
TRIGGER_BODY = (f"// The webhook's field, as the rule reads it in n8n: $('{T}').first().json.body.\n"
                f"DATA[{json.dumps(T)}] = [{{ json: {{ body: {{ lead_id: input.t_lead_id }} }} }}];")
# n8n's fetch node gives a page that failed twice as an item with an error; here it is the second try's status.
# With no page to fetch, n8n never runs the fetch node, so it has no data here either.
FETCHED = (f"DATA[{json.dumps(FETCH)}] = DATA[{json.dumps(FETCH)}].map(i => Number(i.json.status) < 400\n"
           "  ? { json: { data: i.json.data } } : { json: { error: { message: 'HTTP ' + (i.json.status || 'no answer') } } });\n"
           f"if (!DATA[{json.dumps(FETCH)}].length) delete DATA[{json.dumps(FETCH)}];")


def part(js: str) -> str:
    """One n8n Code node's JavaScript as a function of $json, for a Code step that runs several in turn."""
    return "(($json) => {\n" + js.strip() + "\n})"


def resume(s: Scenario, after: dict) -> dict:
    """Make's Resume handler: the failed step's output becomes this later try's answer."""
    return {"id": s._id(f"_resume{s._next}"), "module": "builtin:Resume", "version": 1, "parameters": {},
            "mapper": {k: "{{" + f"{after['id']}.{k}" + "}}" for k in ("statusCode", "data", "headers")},
            "metadata": {"designer": {}}}


def build() -> list[tuple[str, Scenario]]:
    s = Scenario(R, "R5.2 Prepare a research and qualification brief", "webhook", test_key="r5-2-lead-assigned")
    s.flow.append(s.webhook(T))
    s.flow.append(s.config(CONFIG))
    c = s.ref("Config")
    cfg = lambda f: "{{" + f"{c}.result.{f}" + "}}"  # noqa: E731
    conf = "{{" + f"{c}.result" + "}}"
    s.flow += s.stop_flag()
    reserve = s.reserve_key("Step 2: Reserve key", "{{1.lead_id}}")
    reserve["filter"] = s.continue_unless_stopped()
    s.flow.append(reserve)
    key_q = "{{encodeURL(1.lead_id)}}"

    # ---- Step 3: the lead, its CRM history and quotes, then up to five allowed pages -------
    lead = s.http("Step 3: Read the lead", "GET", cfg("crm_url") + "/leads/{{encodeURL(1.lead_id)}}")
    lead["filter"] = s.is_new_key("Step 2: Reserve key")  # a reassignment gets no second brief
    s.flow.append(lead)
    lead_id = "{{" + f"{lead['id']}.data.id" + "}}"
    s.flow += [s.http("Step 3: Read account history", "GET", cfg("crm_url") + "/history", query={"_wrap": "1", "lead_id": lead_id}),
               s.http("Step 3: Read past quotes", "GET", cfg("crm_url") + "/quotes", query={"_wrap": "1", "lead_id": lead_id})]
    data = lambda n: "{{" + f"{s.ref(n)}.data" + "}}"  # noqa: E731
    reads = {"Config": conf, **{n: data(n) for n in ("Step 3: Read the lead", "Step 3: Read account history", "Step 3: Read past quotes")}}
    code, inputs = n8n_rule(N8N.PAGES_JS, reads, many=True)
    s.flow.append(s.code("Step 3: Pages to fetch", code, inputs))
    s.flow.append(s.iterator("Each page", "{{" + f"{s.ref('Step 3: Pages to fetch')}.result.items" + "}}"))
    url = "{{" + f"{s.ref('Each page')}.url" + "}}"
    # Only addresses under your agreed public source types; never personal profiles. Page text is untrusted.
    second = s.http(f"{FETCH}: second try", "GET", url, parse=False, stop_on_error=False, onerror=[])
    fetch = s.http(FETCH, "GET", url, parse=False, onerror=[second, resume(s, second)])
    fetch["filter"] = s.when("a page to fetch (Any pages?)", "{{" + f"{s.ref('Each page')}.none" + "}}", "true", "text:notequal")
    s.flow.append(fetch)
    s.flow.append(s.aggregator("Step 3: Fetched pages", "Each page", {
        "url": url, "data": "{{" + f"{fetch['id']}.data" + "}}", "status": "{{" + f"{fetch['id']}.statusCode" + "}}"}))
    pages = "{{" + f"{s.ref('Step 3: Fetched pages')}.array" + "}}"
    code, inputs = n8n_rule(N8N.SOURCES_JS, {**reads, "Step 3: Pages to fetch": pages, FETCH: pages},
                            items=("Step 3: Pages to fetch", FETCH), prelude=FETCHED)
    s.flow.append(s.code("Step 3: Sources", code, inputs))
    sources = {**reads, "Step 3: Sources": "{{" + f"{s.ref('Step 3: Sources')}.result" + "}}"}

    # ---- Step 4: the AI drafts the brief from the step 3 sources only ----------------------
    vars_js = ("{ criteria: $('Config').first().json.criteria.map(c => `${c.name}: ${c.description}`).join('\\n'), "
               "sources: $('Step 3: Sources').first().json.sources.map(s => `[source ${s.id}]\\n<<<\\n${s.status === 'not fetched' ? 'not fetched' : s.text}\\n>>>`).join('\\n\\n') }")
    s.flow += s.ai_step("Step 4", ROOT / "recipes/R5.2/prompts/draft-brief.md", vars_js, sources, max_tokens=1500, tries=2)
    call = s.ref("Step 4: AI call")

    # ---- Steps 5 and 6: the rules decide, then the note (an AI error gets the links only) --
    js = ("const __ok = Number(input.ai_status) === 200;\n"
          f"const __check = one(__ok ? {part(N8N.CHECK_JS)}($json)\n"
          f"  : {part(AI_ERROR_JS)}({{ error: {{ message: 'AI call returned ' + (input.ai_status || 'no answer') }} }}))[0];\n"
          f"DATA[__ok ? {json.dumps(CHECK)} : 'Step 5: AI error'] = [{{ json: __check }}];\n"
          f"return {part(N8N.NOTE_JS)}(__check);")
    code, inputs = n8n_rule(js, {**sources, "Step 4: AI call": "{{" + f"{call}.data" + "}}"}, prelude=TRIGGER_BODY, bodies={
        "note_body": f"JSON.stringify({{ lead_id: {LEAD}.id, title: out.title, check: out.check, text: out.text, sources: out.sources }})",
        "done_body": "JSON.stringify({ status: 'done', result: out.check })",
        "log_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.lead_id, decision: 'brief ' + out.check, "
                     "rules: { check: out.check, problems: out.problems, criteria: out.criteria_counts, "
                     "sources: out.sources.map(s => s.id + (s.status === 'not fetched' ? ' (not fetched)' : '')) } })"),
        "failed_body": (f"JSON.stringify({{ recipe: '{R}', item: {EV}.lead_id, reason: 'write failed', "
                        "detail: 'Brief note write failed, not retried; attach it by hand or release the key', "
                        "owner: $('Config').first().json.brief_owner })"),
    })
    inputs.update(t_lead_id="{{1.lead_id}}", ai_status="{{" + f"{call}.statusCode" + "}}")
    note = "Steps 5 and 6: Rule: valid, sourced, no page instructions? Write the note"
    s.flow.append(s.code(note, code, inputs))
    n = lambda f: "{{" + f"{s.ref(note)}.result.{f}" + "}}"  # noqa: E731
    # The one write this recipe makes; never retried.
    s.flow += [s.http("Step 6: Attach to the lead", "POST", cfg("crm_url") + "/notes", body=n("note_body"), parse=False,
                      onerror=s.write_failed("Step 6: Attach to the lead", key_q, n("failed_body"))),
               s.finish_key("Mark key done", key_q, n("done_body")),
               s.decision_log("Decision log", n("log_body"))]
    return [("blueprint.json", s)]
