"""R4.4 Summarize a long thread for a handoff or escalation.

Source: book Chapter 4, recipe R4.4, build steps 1 to 6 (recipes/R4.4/build-spec.md);
AI step: recipes/R4.4/prompts/summarize-thread.md.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

T = "Step 1: R4.2 escalation"
EV = f"$('{T}').item.json.body"
KEY = f"String({EV}.escalation_id)"
CFG = "$('Config').first().json"
POINTER = "Summary failed: read the thread"

MASK_JS = r"""
// Step 3: mask restricted fields before the AI sees the thread. Every value held in a
// restricted field (on the thread or a message) is dropped and masked wherever it appears.
const cfg = $('Config').first().json;
const th = $('Step 3: Fetch the thread').first().json;
const msgs = th.messages || [];
const values = [];
for (const rec of [th, ...msgs]) for (const f of cfg.restricted_fields) {
  const v = rec[f];
  if (v !== undefined && v !== null && String(v).trim()) values.push(String(v).trim());
}
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
let masked = 0;
const mask = text => values.reduce((t, v) => t.replace(new RegExp(esc(v), 'g'), () => { masked++; return '[restricted]'; }), String(text || ''));
const thread = msgs.map(m => `${m.link}\nFrom: ${m.from}\nSent: ${m.sent_at}\n${mask(m.body)}`).join('\n\n');
return [{ json: { thread, links: msgs.map(m => m.link), messages: msgs.length, masked } }];
"""

CHECK_JS = AI_PARSE_JS + r"""
// Step 5: all four fields present, every link points into the thread, and no restricted data,
// with a broader detector than step 3: digits near code, gate or keypad.
const cfg = $('Config').first().json;
const m = $('Step 3: Rule: mask restricted fields').first().json;
const th = $('Step 3: Fetch the thread').first().json;
const FIELDS = ['request', 'promises_made', 'open_items', 'next_step'];
const fail = (problem, rules) => [{ json: { pass: false, problem, rules: Object.assign({ masked: m.masked }, rules || {}) } }];
const p = parseAi($('Step 4: AI call').first().json, FIELDS);
if (!p.ok) return fail('AI output failed the check', { fields: p.problem });
const s = p.value;
const missing = FIELDS.filter(f => !s[f] || typeof s[f].text !== 'string' || !s[f].text.trim() || !Array.isArray(s[f].links) || !s[f].links.length);
if (missing.length) return fail('field missing', { fields: `missing or empty: ${missing.join(', ')}` });
const known = new Set(m.links);
const stray = FIELDS.filter(f => s[f].links.some(l => !known.has(l)));
if (stray.length) return fail('link outside the thread', { fields: 'passed', links: `not in the thread: ${stray.join(', ')}` });
const text = FIELDS.map(f => s[f].text).join('\n');
// A number the summary labels as an order (or other allowed) number is not restricted data.
const labels = cfg.detector_allowed_labels.join('|');
const scan = labels ? text.replace(new RegExp(`\\b(${labels})\\s*(?:number|no\\.?|#)?\\s*\\d+`, 'gi'), '$1 [number]') : text;
const values = [];
for (const rec of [th, ...(th.messages || [])]) for (const f of cfg.restricted_fields) if (rec[f]) values.push(String(rec[f]).trim());
const w = cfg.detector_window, words = cfg.detector_words.join('|');
const near = new RegExp(`(?:${words})[^\\n]{0,${w}}\\d{3,}|\\d{3,}[^\\n]{0,${w}}(?:${words})`, 'i');
if (values.some(v => text.includes(v)) || near.test(scan)) return fail('restricted data', { fields: 'passed', links: 'passed', restricted: 'found' });
const label = { request: 'Request', promises_made: 'Promises made', open_items: 'Open items', next_step: 'Next step' };
const note = ['Summary (AI-drafted from the thread; check each line against its links)']
  .concat(FIELDS.map(f => `${label[f]}: ${s[f].text.trim()} (${s[f].links.join(', ')})`)).join('\n');
return [{ json: { pass: true, note, rules: { masked: m.masked, fields: 'passed', links: 'passed', restricted: 'none found' } } }];
"""


def build() -> Workflow:
    w = Workflow("R4.4", "R4.4 Summarize a long thread for a handoff or escalation")
    w.webhook(T, "r4-4-escalation",
              "Called on each R4.2 escalation (for example by a helpdesk rule on R4.2's priority raise). Body: {escalation_id, ticket_id}; R4.2's escalation ID is its key, ticket ID plus message ID.",
              pos=[0, 0])
    w.config("Config", {
        "helpdesk_url": "https://<your helpdesk API>",
        "restricted_fields": ["<your restricted-field list, such as access_code>"],
        "detector_words": ["code", "gate", "keypad"],
        "detector_window": 20,
        "detector_allowed_labels": ["order"],
        "exception_owner": "<your workflow owner>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 0])
    w.reserve_key("Step 2: Reserve key", KEY, pos=[520, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[780, 0])
    w.noop("Duplicate: stop", pos=[1040, -200], notes="This escalation was summarized before.")
    w.chain(T, "Config", "Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    w.http("Step 3: Fetch the thread", "GET", f"={{{{ {CFG}.helpdesk_url }}}}/threads/{{{{ {EV}.ticket_id }}}}",
           write=False, error_output=False, pos=[1040, 0], notes="The thread with each message's link.")
    w.code("Step 3: Rule: mask restricted fields", MASK_JS, mode="runOnceForAllItems", pos=[1300, 0],
           notes="Runs before the AI sees anything.")
    w.connect("New key?", "Step 3: Fetch the thread", output=0)
    w.connect("Step 3: Fetch the thread", "Step 3: Rule: mask restricted fields")

    build, call = ai_step(w, "Step 4", ROOT / "recipes/R4.4/prompts/summarize-thread.md",
                          "{ thread: $('Step 3: Rule: mask restricted fields').first().json.thread }",
                          max_tokens=4096, tries=2, pos_build=[1560, 0], pos_call=[1820, 0])
    w.connect("Step 3: Rule: mask restricted fields", build)
    w.code("Step 5: Rule: fields, links, nothing restricted?", CHECK_JS, mode="runOnceForAllItems", pos=[2080, 0],
           notes="The rule decides whether the summary is posted, not the AI.")
    w.connect(call, "Step 5: Rule: fields, links, nothing restricted?", output=0)
    w.code("Step 5: AI error",
           "return [{ json: { pass: false, problem: 'AI error after one retry', rules: { masked: $('Step 3: Rule: mask restricted fields').first().json.masked, ai: 'error' } } }];",
           mode="runOnceForAllItems", pos=[2080, 200])
    w.connect(call, "Step 5: AI error", output=1)
    w.if_("Passed?", "={{ $json.pass }}", pos=[2340, 0])
    w.connect("Step 5: Rule: fields, links, nothing restricted?", "Passed?")
    w.connect("Step 5: AI error", "Passed?")

    notes = f"={{{{ {CFG}.helpdesk_url }}}}/notes"
    w.http("Step 6: Post the summary note", "POST", notes,
           body=f"={{{{ JSON.stringify({{ ticket_id: {EV}.ticket_id, internal: true, text: $json.note }}) }}}}",
           write=True, pos=[2600, -120], notes="An internal note atop the thread; never a reply.")
    w.http("Step 6: Post the pointer note", "POST", notes,
           body=f"={{{{ JSON.stringify({{ ticket_id: {EV}.ticket_id, internal: true, text: {POINTER!r} }}) }}}}",
           write=True, pos=[2600, 120])
    w.connect("Passed?", "Step 6: Post the summary note", output=0)
    w.connect("Passed?", "Step 6: Post the pointer note", output=1)

    result = "$('Passed?').item.json.pass ? 'summary posted' : 'pointer note posted'"
    w.finish_key("Mark key done", KEY, "done", result, pos=[2860, 0])
    w.decision_log("Decision log", f"{EV}.ticket_id", result,
                   f"JSON.stringify(Object.assign({{ escalation_id: {KEY} }}, $('Passed?').item.json.rules, "
                   f"$('Passed?').item.json.pass ? {{}} : {{ problem: $('Passed?').item.json.problem, pointer_note: {POINTER!r} }}))",
                   pos=[3120, 0])
    for n in ["Step 6: Post the summary note", "Step 6: Post the pointer note"]:
        w.connect(n, "Mark key done")
    w.connect("Mark key done", "Decision log")

    w.finish_key("Mark key failed", KEY, "failed", "'note write failed'", pos=[2860, 360])
    w.exception("Exception queue: write failed", f"{EV}.ticket_id", "write failed",
                "'Note write failed, never retried; the receiver reads the thread'", f"{CFG}.exception_owner", pos=[3120, 360])
    for n in ["Step 6: Post the summary note", "Step 6: Post the pointer note"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")
    return w
