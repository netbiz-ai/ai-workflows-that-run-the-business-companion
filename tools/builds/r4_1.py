"""R4.1 Classify and route every incoming message to the right queue.

Source: book Chapter 4, recipe R4.1, build steps 1 to 6 (recipes/R4.1/build-spec.md);
AI step: recipes/R4.1/prompts/classify.md.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

T = "Step 1: New message"
EV = f"$('{T}').item.json.body"
KEY = f"{EV}.ticket_id + ':' + {EV}.message_id"

SENDER_JS = r"""
// Step 3: auto-replies and bulk mail go to the low-priority queue, with no AI call.
const cfg = $('Config').first().json;
const t = $('Read the message').first().json;
const headers = Object.fromEntries(Object.entries(t.headers || {}).map(([k, v]) => [k.toLowerCase(), String(v).toLowerCase()]));
const from = String(t.from || '').toLowerCase();
const auto = ['auto-replied', 'auto-generated'].includes(headers['auto-submitted'])
  || ['bulk', 'list', 'junk'].includes(headers['precedence'])
  || cfg.bulk_senders.some(s => from.endsWith(s.toLowerCase()));
return [{ json: { automatic: auto } }];
"""

DECIDE_JS = AI_PARSE_JS + r"""
// Step 5: use the category only if it is listed exactly, confidence is high and the language is covered.
const cfg = $('Config').first().json;
const p = parseAi($('Step 4: AI call').first().json, ['category', 'confidence', 'language'], { confidence: ['high', 'medium', 'low'] });
if (!p.ok) return [{ json: { route: 'exception', reason: 'AI output failed the check', detail: p.problem } }];
const ai = p.value;
const listed = cfg.categories.find(c => c.name === ai.category);
const covered = cfg.covered_languages.includes(ai.language);
const rules = { listed: !!listed, confidence: ai.confidence, language: ai.language, covered };
if (listed && ai.confidence === 'high' && covered) {
  return [{ json: { route: 'set', category: listed.name, queue: listed.queue, confidence: ai.confidence, rules } }];
}
const reason = !covered ? 'language not covered' : !listed ? 'category not listed' : 'confidence not high';
return [{ json: { route: 'exception', reason, detail: `AI suggested ${ai.category} (${ai.confidence}, ${ai.language})`, rules } }];
"""


def build() -> Workflow:
    w = Workflow("R4.1", "R4.1 Classify and route every incoming message")
    w.webhook(T, "r4-1-new-message", "Your helpdesk calls this for each new message. Body: {ticket_id, message_id}.", pos=[0, 0])
    w.config("Config", {
        "helpdesk_url": "https://<your helpdesk API>",
        "categories": [
            {"name": "<category>", "queue": "<its queue>", "owner": "<its owner>", "description": "<what belongs here>",
             "examples": ["<example 1>", "<example 2>", "<example 3>"]}
        ],
        "covered_languages": ["en"],
        "low_priority_queue": "<your low-priority queue>",
        "triage_queue": "<your manual triage queue>",
        "triage_lead": "<your triage lead>",
        "bulk_senders": ["<noreply@your-suppliers.example>"],
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 0])
    w.http("Read the message", "GET", f"={{{{ $('Config').item.json.helpdesk_url }}}}/tickets/{{{{ {EV}.ticket_id }}}}",
           write=False, error_output=False, pos=[520, 0])
    w.reserve_key("Step 2: Reserve key", KEY, pos=[780, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1040, 0])
    w.noop("Duplicate: stop", pos=[1300, -200], notes="This message was routed before.")
    w.chain(T, "Config", "Read the message", "Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    w.code("Step 3: Rule: automatic sender?", SENDER_JS, mode="runOnceForAllItems", pos=[1300, 0])
    w.if_("Automatic?", "={{ $json.automatic }}", pos=[1560, 0])
    w.connect("New key?", "Step 3: Rule: automatic sender?", output=0)
    w.connect("Step 3: Rule: automatic sender?", "Automatic?")

    ticket = f"$('Read the message').item.json"
    vars_js = ("{ category_list: cfg.categories.map(c => `${c.name}: ${c.description}; ${c.examples.join('; ')}`).join('\\n'), "
               f"subject: {ticket}.subject, body: {ticket}.body }}")
    vars_js = vars_js.replace("cfg.categories", "$('Config').first().json.categories")
    build, call = ai_step(w, "Step 4", ROOT / "recipes/R4.1/prompts/classify.md", vars_js,
                          max_tokens=100, tries=2, pos_build=[1820, 120], pos_call=[2080, 120])
    w.connect("Automatic?", build, output=1)
    w.code("Step 5: Rule: use the category?", DECIDE_JS, mode="runOnceForAllItems", pos=[2340, 120],
           notes="The rule decides, not the AI.")
    w.connect(call, "Step 5: Rule: use the category?", output=0)
    w.code("Step 5: AI error", "return [{ json: { route: 'exception', reason: 'AI error after one retry', detail: String(($json.error && $json.error.message) || '') } }];",
           mode="runOnceForAllItems", pos=[2340, 320])
    w.connect(call, "Step 5: AI error", output=1)
    w.if_("Set it?", "={{ $json.route }}", op="equals", right="set", pos=[2600, 120])
    w.connect("Step 5: Rule: use the category?", "Set it?")
    w.connect("Step 5: AI error", "Set it?")

    url = f"={{{{ $('Config').item.json.helpdesk_url }}}}/tickets/{{{{ {EV}.ticket_id }}}}"
    w.http("Step 3: Set low-priority queue", "PATCH", url,
           body="={{ JSON.stringify({ queue: $('Config').item.json.low_priority_queue }) }}", write=True, pos=[1820, -120])
    w.connect("Automatic?", "Step 3: Set low-priority queue", output=0)
    w.http("Step 5: Set category and queue", "PATCH", url,
           body="={{ JSON.stringify({ category: $json.category, queue: $json.queue }) }}", write=True, pos=[2860, 0])
    w.http("Step 5: Move to manual triage", "PATCH", url,
           body="={{ JSON.stringify({ queue: $('Config').item.json.triage_queue }) }}", write=True, pos=[2860, 240])
    w.exception("Exception queue: triage lead sorts it", f"{EV}.ticket_id", "needs manual triage",
                "$('Set it?').item.json.reason + ': ' + ($('Set it?').item.json.detail || '')",
                "$('Config').item.json.triage_lead", pos=[3120, 240])
    w.connect("Set it?", "Step 5: Set category and queue", output=0)
    w.connect("Set it?", "Step 5: Move to manual triage", output=1)
    w.connect("Step 5: Move to manual triage", "Exception queue: triage lead sorts it")

    w.finish_key("Mark key done", KEY, "done", "'routed'", pos=[3380, 0])
    w.decision_log("Step 6: Decision log", f"{EV}.ticket_id",
                   "$('Automatic?').item.json.automatic ? 'low priority (automatic sender)' : $('Set it?').item.json.route === 'set' ? 'set ' + $('Set it?').item.json.category : 'manual triage: ' + $('Set it?').item.json.reason",
                   "JSON.stringify($('Automatic?').item.json.automatic ? { sender: 'automatic' } : ($('Set it?').item.json.rules || { ai: 'error' }))",
                   pos=[3640, 0])
    for n in ["Step 3: Set low-priority queue", "Step 5: Set category and queue", "Exception queue: triage lead sorts it"]:
        w.connect(n, "Mark key done")
    w.connect("Mark key done", "Step 6: Decision log")

    w.finish_key("Mark key failed", KEY, "failed", "'write failed'", pos=[3380, 480])
    w.exception("Exception queue: write failed", f"{EV}.ticket_id", "write failed",
                "'Routing write failed; check the ticket, never retried'", "$('Config').item.json.triage_lead", pos=[3640, 480])
    for n in ["Step 3: Set low-priority queue", "Step 5: Set category and queue", "Step 5: Move to manual triage"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")
    return w
