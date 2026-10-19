"""R9.2 Answer policy questions from approved sources and hand off to HR.

Source: book Chapter 9, recipe R9.2, build steps 1 to 7 (recipes/R9.2/build-spec.md);
AI step: recipes/R9.2/prompts/answer-policy-question.md.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

RID = "R9.2"
T = "Step 1: Question asked"
Q = f"$('{T}').first().json.body"
KEY = f"{Q}.message_id"
CFG = "$('Config').first().json"

SENSITIVE_JS = rf"""
// Step 2: a match on HR's list of personal phrasings never reaches the AI.
const cfg = {CFG};
const text = String({Q}.text || '').toLowerCase().replace(/\s+/g, ' ');
const phrase = (cfg.sensitive_phrases || []).find(p => text.includes(String(p).toLowerCase()));
return [{{ json: {{ sensitive: !!phrase }} }}];
"""

RETRIEVE_JS = rf"""
// Step 3: passages from current approved documents only (approved status, in effect today).
const cfg = {CFG};
const today = new Date().toISOString().slice(0, 10);
const docs = ($('Step 3: Read current approved documents').first().json.items || [])
  .filter(d => d.status === cfg.approved_status && String(d.effective_date || '9999').slice(0, 10) <= today);
const STOP = new Set(('about after all also and any are because been before but can could did does for from get give got had has have how '
  + 'into its just like many more much must not our out over shall should some than that the their them then there these they this '
  + 'those through under until upon very was way well were what when where which while who why will with would you your').split(' '));
const words = s => (String(s).toLowerCase().match(/[a-z0-9]+/g) || []).filter(w => w.length > 2 && !STOP.has(w)).map(w => w.replace(/s$/, ''));
const asked = new Set(words({Q}.text));
const passages = [];
for (const d of docs) {{
  for (const text of String(d.text || '').split(/\n\s*\n/).map(s => s.trim()).filter(Boolean)) {{
    const score = new Set(words(text).filter(w => asked.has(w))).size;
    if (score >= cfg.min_matching_words) passages.push({{ document: d.name, link: d.link, text, score }});
  }}
}}
passages.sort((a, b) => b.score - a.score);
const top = passages.slice(0, cfg.max_passages);
return [{{ json: {{ found: top.length > 0, passages: top }} }}];
"""

CHECK_JS = AI_PARSE_JS + rf"""
// Step 5: citations retrieved, quote word for word, every number in the quote, about_asker is no.
const passages = $('Step 3: Rule: retrieve passages').first().json.passages;
const p = parseAi($('Step 4: AI call').first().json, ['answer', 'document', 'quote', 'about_asker'], {{ about_asker: ['yes', 'no'] }});
if (!p.ok) return [{{ json: {{ ok: false, why: 'AI output failed the check: ' + p.problem }} }}];
const ai = p.value;
const norm = s => String(s || '').replace(/\s+/g, ' ').trim();
const NUM = /\d+(?:[.,]\d+)?|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|half|quarter)\b/g;
const nums = s => String(s || '').toLowerCase().match(NUM) || [];
const cited = passages.filter(x => x.document === ai.document);
const rules = {{ document: ai.document || '', about_asker: ai.about_asker }};
let why = '';
if (!norm(ai.quote) || !norm(ai.document)) why = 'no answer in the passages';
else if (!cited.length) why = 'cited document not retrieved';
else if (!cited.some(x => norm(x.text).includes(norm(ai.quote)))) why = 'quote not word for word';
else if (nums(ai.answer).some(n => !nums(ai.quote).includes(n))) why = 'number not in the quote';
else if (ai.about_asker !== 'no') why = 'about the asker';
if (why) return [{{ json: {{ ok: false, why, rules }} }}];
return [{{ json: {{ ok: true, document: cited[0].document, link: cited[0].link, quote: norm(ai.quote), rules }} }}];
"""

HANDOFF_JS = rf"""
// Every handoff: the asker gets a reply naming HR, and HR gets the text (never the log).
const cfg = {CFG};
const why = $json.why;
const reply = why === 'sensitive phrase' ? cfg.fixed_reply : why === 'no source' ? cfg.no_source_reply : cfg.handoff_reply;
return {{ json: {{ why, reply }} }};
"""


def build() -> Workflow:
    w = Workflow(RID, "R9.2 Answer policy questions from approved sources")
    w.webhook(T, "r9-2-question", "Your intake channel calls this for each question. Body: {message_id, asker, text}; the channel knows who asks.", pos=[0, 0])
    w.config("Config", {
        "policies_url": "https://<your policy folder API>",
        "messaging_url": "https://<your intake channel or messaging API>",
        "restricted_log_url": "https://<your restricted log API>",
        "gap_log_url": "https://<your gap log API>",
        "approved_status": "<the status your policy folder gives a current approved document>",
        "sensitive_phrases": ["<your list of personal phrasings, such as my pay>"],
        "fixed_reply": "<your fixed reply, naming your HR owner and who to ask if it concerns them>",
        "no_source_reply": "No source: no current approved policy answers this. Your question has gone to <your HR owner>.",
        "handoff_reply": "Your question has gone to <your HR owner>, who will answer you.",
        "closing_line": "For your own situation, ask <your HR owner>.",
        "hr_owner": "<your HR owner>",
        "min_matching_words": 2,
        "max_passages": 3,
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 0])
    w.reserve_key("Step 1: Reserve key", KEY, pos=[520, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[780, 0])
    w.noop("Duplicate: stop", pos=[1040, -200], notes="This message was handled before.")
    w.chain(T, "Config", "Step 1: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    cfg = "$('Config').item.json"
    msg = f"={{{{ {cfg}.messaging_url }}}}/messages"

    # ---- Step 2: sensitive screen ----------------------------------------------
    w.code("Step 2: Rule: sensitive phrasing?", SENSITIVE_JS, mode="runOnceForAllItems", pos=[1040, 0])
    w.if_("Sensitive?", "={{ $json.sensitive }}", pos=[1300, 0])
    w.connect("New key?", "Step 2: Rule: sensitive phrasing?", output=0)
    w.connect("Step 2: Rule: sensitive phrasing?", "Sensitive?")
    w.code("Step 2: Why: sensitive", "return [{ json: { why: 'sensitive phrase' } }];", mode="runOnceForAllItems", pos=[1560, -160])
    w.connect("Sensitive?", "Step 2: Why: sensitive", output=0)

    # ---- Step 3: retrieve from current approved documents --------------------------
    w.http("Step 3: Read current approved documents", "GET", f"={{{{ {cfg}.policies_url }}}}/documents",
           query={"_wrap": "1", "status": f"={{{{ {cfg}.approved_status }}}}"}, write=False, error_output=False, pos=[1560, 120])
    w.code("Step 3: Rule: retrieve passages", RETRIEVE_JS, mode="runOnceForAllItems", pos=[1820, 120])
    w.if_("Source found?", "={{ $json.found }}", pos=[2080, 120])
    w.connect("Sensitive?", "Step 3: Read current approved documents", output=1)
    w.chain("Step 3: Read current approved documents", "Step 3: Rule: retrieve passages", "Source found?")
    w.http("Step 3: Log a gap", "POST", f"={{{{ {cfg}.gap_log_url }}}}/gaps",
           body=f"={{{{ JSON.stringify({{ message_id: {Q}.message_id, date: new Date().toISOString().slice(0, 10), outcome: 'no source' }}) }}}}",
           write=True, pos=[2340, -40], notes="The gap log holds the message ID only; the text goes to HR.")
    w.code("Step 3: Why: no source", "return [{ json: { why: 'no source' } }];", mode="runOnceForAllItems", pos=[2600, -40])
    w.connect("Source found?", "Step 3: Log a gap", output=1)
    w.connect("Step 3: Log a gap", "Step 3: Why: no source")

    # ---- Steps 4 and 5: AI answers in fixed fields; a rule decides --------------
    vars_js = (f"{{ passages: $('Step 3: Rule: retrieve passages').first().json.passages"
               f".map(p => 'Document: ' + p.document + '\\n' + p.text).join('\\n\\n'), question: {Q}.text }}")
    build, call = ai_step(w, "Step 4", ROOT / "recipes/R9.2/prompts/answer-policy-question.md", vars_js,
                          max_tokens=600, tries=3, pos_build=[2340, 240], pos_call=[2600, 240])
    w.connect("Source found?", build, output=0)
    w.code("Step 5: Rule: use the answer?", CHECK_JS, mode="runOnceForAllItems", pos=[2860, 240], notes="The rule decides, not the AI.")
    w.connect(call, "Step 5: Rule: use the answer?", output=0)
    w.code("Step 5: Why: AI error", "return [{ json: { why: 'AI error after retries' } }];", mode="runOnceForAllItems", pos=[2860, 440])
    w.connect(call, "Step 5: Why: AI error", output=1)
    w.if_("Answer passes?", "={{ $json.ok }}", pos=[3120, 240])
    w.connect("Step 5: Rule: use the answer?", "Answer passes?")

    # ---- Steps 6 and 7: send the quote and link; log ---------------------------
    ans = "$('Step 5: Rule: use the answer?').item.json"
    w.http("Step 6: Send the quote and link", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {Q}.asker, in_reply_to: {Q}.message_id, "
                f"text: '\"' + {ans}.quote + '\"\\n' + {ans}.document + ': ' + {ans}.link + '\\n' + {CFG}.closing_line }}) }}}}",
           write=True, pos=[3380, 160])
    w.http("Step 7: Restricted log", "POST", f"={{{{ {cfg}.restricted_log_url }}}}/entries",
           body=f"={{{{ JSON.stringify({{ message_id: {Q}.message_id, date: new Date().toISOString().slice(0, 10), question: {Q}.text, "
                f"document: {ans}.document, quote: {ans}.quote }}) }}}}",
           write=True, pos=[3640, 160], notes="Answered questions only; keep 30 days (governance card, Logging).")
    w.finish_key("Mark key done: answered", KEY, "done", "'answered'", pos=[3900, 160])
    w.decision_log("Step 7: Decision log: answered", f"{Q}.message_id", "'answered'", f"JSON.stringify({ans}.rules)", pos=[4160, 160])
    w.connect("Answer passes?", "Step 6: Send the quote and link", output=0)
    w.chain("Step 6: Send the quote and link", "Step 7: Restricted log", "Mark key done: answered", "Step 7: Decision log: answered")

    # ---- every handoff: reply, text to HR, exception queue by ID, log by ID ----------
    w.code("Hand off: reply and reason", HANDOFF_JS, pos=[3380, 560])
    for n in ["Step 2: Why: sensitive", "Step 3: Why: no source", "Step 5: Why: AI error"]:
        w.connect(n, "Hand off: reply and reason")
    w.connect("Answer passes?", "Hand off: reply and reason", output=1)
    ho = "$('Hand off: reply and reason').item.json"
    w.http("Hand off: Reply to the asker", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {Q}.asker, in_reply_to: {Q}.message_id, text: $json.reply }}) }}}}", write=True, pos=[3640, 560])
    w.http("Hand off: Pass the text to Aisha", "POST", msg,
           body=f"={{{{ JSON.stringify({{ to: {CFG}.hr_owner, subject: 'Policy question handed off (' + {ho}.why + '): ' + {Q}.message_id, "
                f"text: 'From ' + {Q}.asker + ':\\n' + {Q}.text }}) }}}}",
           write=True, pos=[3900, 560], notes="The text goes to HR only, never to a log.")
    w.exception("Hand off: Exception queue", f"{Q}.message_id", "handed off", f"{ho}.why", f"{CFG}.hr_owner", pos=[4160, 560])
    w.finish_key("Mark key done: handed off", KEY, "done", f"'handed off: ' + {ho}.why", pos=[4420, 560])
    w.decision_log("Step 7: Decision log: handed off", f"{Q}.message_id", f"'handed off: ' + {ho}.why",
                   f"JSON.stringify(Object.assign({{ why: {ho}.why }}, $('Answer passes?').isExecuted ? $('Step 5: Rule: use the answer?').first().json.rules || {{}} : {{}}))",
                   pos=[4680, 560])
    w.chain("Hand off: reply and reason", "Hand off: Reply to the asker", "Hand off: Pass the text to Aisha", "Hand off: Exception queue",
            "Mark key done: handed off", "Step 7: Decision log: handed off")

    # ---- a send or log write fails: never retried ----------------------------------
    w.finish_key("Mark key failed", KEY, "failed", "'write failed: ' + (($json.error && $json.error.message) || 'unknown')", pos=[3900, 900])
    w.exception("Exception queue: reply not sent", f"{Q}.message_id", "reply not sent",
                "'A reply, handoff or log write failed, never retried; answer the asker from the intake channel'", f"{CFG}.hr_owner", pos=[4160, 900])
    for n in ["Step 3: Log a gap", "Step 6: Send the quote and link", "Step 7: Restricted log",
              "Hand off: Reply to the asker", "Hand off: Pass the text to Aisha"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: reply not sent")
    return w
