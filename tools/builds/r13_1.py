"""R13.1 Answer staff questions from approved sources, with citations and a refusal path.

Source: book Chapter 13, recipe R13.1, build steps 1 to 13 and Table 13.2 (recipes/R13.1/build-spec.md);
AI step: recipes/R13.1/prompts/answer.md.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

T = "Step 1: Staff question"
EV = f"$('{T}').first().json.body"
KEY = f"{EV}.message_id"
OUT = "$('Outcome').item.json"

# Shared by every rule node that builds a reply: one outcome shape for Table 13.2.
HELPERS_JS = r"""
const cfg = $('Config').first().json;
const ev = $('Step 1: Staff question').first().json.body;
const regList = (n) => { try { return $(n).first().json.items || []; } catch (e) { return []; } };
const register = Object.fromEntries(regList('Read the source register').map(r => [String(r.id), r]));
const outcome = (o) => [{ json: Object.assign({ route: 'done', reply: null, gap: null, forward_to_hr: false, rules: {} }, o) }];
// "I don't know", with the topic's owner (or the fallback owner), and a logged gap (steps 6, 7 and 10).
const gap = (reason, topSource, extra) => {
  const s = topSource && register[String(topSource)];
  const topic = s ? s.title : 'no source';
  const owner = s ? s.owner : cfg.gap_owner;
  const name = s ? (s.owner_name || s.owner) : cfg.gap_owner;
  return outcome({ outcome: 'gap', reply: `I don't know. Ask ${name}` + (s ? `, who owns the ${topic}.` : '.'),
                   decision: 'gap: ' + reason, gap: { topic, owner }, rules: Object.assign({ topic, owner, reason }, extra || {}) });
};
const dontKnow = (decision, extra) => outcome({ outcome: 'refused', reply: "I don't know.", decision, rules: extra || {} });
"""

STEP3_JS = r"""
// Step 3: personal HR questions get R9.2's fixed reply and go to HR; price questions get the price-list link.
// Table 13.2: a "wrong" reply to an answer logs a gap.
const cfg = $('Config').first().json;
const ev = $('Step 1: Staff question').first().json.body;
const text = String(ev.text || '').toLowerCase();
const has = list => (list || []).some(p => p && text.includes(String(p).toLowerCase()));
if (ev.reply_to && text.replace(/[^a-z]/g, '') === 'wrong') return [{ json: { route: 'wrong' } }];
if (has(cfg.hr_phrases)) return [{ json: { route: 'hr' } }];
if (has(cfg.price_phrases)) return [{ json: { route: 'price' } }];
return [{ json: { route: 'search' } }];
"""

HR_JS = HELPERS_JS + r"""
// Logged as ID and outcome only (governance card, Logging).
return outcome({ outcome: 'hr', reply: cfg.hr_fixed_reply, decision: 'personal HR question: fixed reply, passed to HR', forward_to_hr: true });
"""

PRICE_JS = HELPERS_JS + r"""
return outcome({ outcome: 'price', reply: `Prices are never quoted here; see the price list: ${cfg.price_list_link}`, decision: 'routed to price list' });
"""

WRONG_JS = HELPERS_JS + r"""
const found = $('Read the answer\'s decision log').first().json;
const owner = found.owner || cfg.gap_owner;
const topic = found.topic || 'unknown topic';
return outcome({ outcome: 'wrong', decision: 'gap: reported wrong', gap: { topic: `reported wrong (answer to ${ev.reply_to}): ${topic}`, owner },
                 rules: { topic, owner, answer_to: ev.reply_to } });
"""

STEP6_JS = HELPERS_JS + r"""
// Step 6: keep the five best passages at or above the relevance threshold; log every score for retuning.
const hits = ($('Step 5: Search current, in-date passages').first().json.items || []).slice()
  .sort((a, b) => Number(b.score) - Number(a.score));
const threshold = Number(cfg.relevance_threshold);  // an unfilled placeholder is NaN, so nothing passes
const scores = hits.map(h => ({ id: h.id, score: h.score }));
const kept = hits.filter(h => Number(h.score) >= threshold).slice(0, cfg.max_passages);
if (!kept.length) return gap('no passage above the threshold', hits[0] && hits[0].source, { scores });
return [{ json: { route: 'continue', kept, scores } }];
"""

FILES_JS = r"""
// Step 7: one live sharing read per retrieved document.
const kept = $('Step 6: Rule: above the relevance threshold?').first().json.kept;
return [...new Set(kept.map(p => String(p.file_id)))].map(file_id => ({ json: { file_id } }));
"""

STEP7_JS = HELPERS_JS + r"""
// Step 7: drop any retrieved document the asker cannot open now; if none remain, reply as in step 6.
const s6 = $('Step 6: Rule: above the relevance threshold?').first().json;
const groups = $('Step 4: Read the asker\'s groups').first().json.groups || [];
const allowed = new Set([String(ev.asker).toLowerCase(), ...groups.map(g => String(g).toLowerCase())]);
const open = new Set($('Step 7: Read live sharing').all().map(i => i.json)
  .filter(f => (f.shared_with || []).some(a => allowed.has(String(a).toLowerCase()))).map(f => String(f.id)));
const passages = s6.kept.filter(p => open.has(String(p.file_id)));
const dropped = s6.kept.filter(p => !open.has(String(p.file_id))).map(p => p.id);
if (!passages.length) return gap('no retrieved document open to the asker', s6.kept[0].source, { scores: s6.scores, dropped });
return [{ json: { route: 'continue', passages, dropped, scores: s6.scores } }];
"""

RULES_JS = AI_PARSE_JS + HELPERS_JS + r"""
// Steps 9 to 12: the rules decide whether the AI's draft is sent; one failing sentence fails the answer.
const s7 = $('Step 7: Rule: drop documents the asker cannot open').first().json;
const passages = Object.fromEntries(s7.passages.map(p => [String(p.id), p]));
const now = Object.fromEntries(($('Step 11: Read the source register again').first().json.items || []).map(r => [String(r.id), r]));
const base = { sources: [...new Set(s7.passages.map(p => p.source))], passages: Object.keys(passages), scores: s7.scores, dropped: s7.dropped };
const failed = reason => dontKnow('check failed: ' + reason, Object.assign({ check: reason }, base));

// Step 8's fixed fields: sentences with passage IDs, conflict and not_answered, and nothing else.
const p = parseAi($('Step 8: AI call').first().json, ['sentences', 'conflict', 'not_answered']);
if (!p.ok) return failed(p.problem);
const out = p.value;
if (Object.keys(out).some(k => !['sentences', 'conflict', 'not_answered'].includes(k))) return failed('output outside the fields');
if (!Array.isArray(out.sentences) || typeof out.conflict !== 'boolean' || typeof out.not_answered !== 'boolean') return failed('output outside the fields');
for (const s of out.sentences) {
  if (!s || typeof s !== 'object' || typeof s.text !== 'string' || !Array.isArray(s.passage_ids)
      || Object.keys(s).some(k => !['text', 'passage_ids'].includes(k))) return failed('output outside the fields');
}

// Step 9: citation rules. Numbers and dates must be in a cited passage, quotes word for word,
// and a currency amount not on the policy-figures list sends the price-list link instead.
const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const DATE = /\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:,?\s+(\d{4}))?\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b|\b(\d{4})-(\d{2})-(\d{2})\b/gi;
const dates = t => [...String(t).matchAll(DATE)].map(m => m[7]
  ? { y: m[7], md: `${Number(m[8])}-${Number(m[9])}` }
  : m[2] ? { y: m[3] || null, md: `${MONTHS.indexOf(m[2].toLowerCase()) + 1}-${Number(m[1])}` }
         : { y: m[6] || null, md: `${MONTHS.indexOf(m[4].toLowerCase()) + 1}-${Number(m[5])}` });
const numbers = t => (String(t).match(/\d+(?:[.,]\d+)*/g) || []).map(n => n.replace(/,/g, ''));
const MONEY = /[$€£]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:usd|eur|gbp|dollars?|euros?|pounds?)\b/gi;
const money = t => (String(t).match(MONEY) || []).map(a => a.toLowerCase().replace(/[\s,]/g, ''));
const listed = new Set((cfg.policy_figures || []).flatMap(money));

const checks = [];
let price = false;
for (const s of out.sentences) {
  if (!s.passage_ids.length) return failed('uncited sentence');
  const cited = s.passage_ids.map(id => passages[String(id)]);
  if (cited.some(c => !c)) return failed('cites a passage that was not retrieved');
  if (money(s.text).some(a => !listed.has(a))) { price = true; continue; }
  const texts = cited.map(c => String(c.text));
  const have = new Set(texts.flatMap(numbers).concat(cited.flatMap(c => numbers(c.effective))));
  const haveDates = texts.flatMap(dates).concat(cited.flatMap(c => dates(c.effective)));
  for (const d of dates(s.text)) {
    if (!haveDates.some(h => h.md === d.md && (!d.y || !h.y || h.y === d.y))) return failed('unsupported date');
  }
  if (numbers(String(s.text).replace(DATE, ' ')).some(n => !have.has(n))) return failed('unsupported number');
  for (const q of String(s.text).matchAll(/"([^"]+)"|“([^”]+)”/g)) {
    if (!texts.some(t => t.includes(q[1] || q[2]))) return failed('misquote');
  }
  checks.push({ sentence: checks.length + 1, passages: s.passage_ids });
}
if (price) return outcome({ outcome: 'price', reply: `Prices are never quoted here; see the price list: ${cfg.price_list_link}`,
                            decision: 'routed to price list', rules: Object.assign({ check: 'currency amount not on the policy-figures list' }, base) });

// Step 10: a conflict names both sources and their owners; "not answered" goes as step 6.
if (out.conflict) {
  const named = base.sources.map(id => register[id] || now[id] || { title: id, owner: cfg.gap_owner });
  return outcome({ outcome: 'conflict', decision: 'conflict',
    reply: 'The sources disagree, so there is no answer: ' + named.map(s => `${s.title} (owner: ${s.owner_name || s.owner})`).join(' and ') + '. Ask the owners which applies.',
    rules: Object.assign({ owner: named[0].owner, topic: named.map(s => s.title).join(' / ') }, base) });
}
if (out.not_answered || !out.sentences.length) return gap('not answered', s7.passages[0].source, base);

// Step 11: a source withdrawn since step 5 fails the answer.
const citedSources = [...new Set(out.sentences.flatMap(s => s.passage_ids.map(id => String(passages[String(id)].source))))];
if (citedSources.some(id => !now[id] || now[id].status !== 'current')) return dontKnow('withdrawn since the search', Object.assign({ check: 'source withdrawn' }, base));

// Step 12: add each citation's title, date and link, and the deciding owner.
const srcs = citedSources.map(id => now[id]);
const owners = [...new Set(srcs.map(s => s.owner_name || s.owner))].join(' or ');
const rules = Object.assign({ owner: srcs[0].owner, topic: srcs.map(s => s.title).join(' / '), checks }, base);
if (srcs.some(s => s.safety_critical)) {
  return outcome({ outcome: 'answered, link only', decision: 'answered, link only', rules,
    reply: srcs.map(s => `See ${s.title}: ${s.link} (owner: ${s.owner_name || s.owner}).`).join('\n') });
}
const cites = citedSources.map(id => {
  const eff = [...new Set(s7.passages.filter(p => String(p.source) === id).map(p => p.effective))].join(', ');
  return `- ${now[id].title}, ${eff}: ${now[id].link}`;
});
return outcome({ outcome: 'answered', decision: 'answered', rules,
  reply: out.sentences.map(s => s.text).join(' ') + '\n\nSources:\n' + cites.join('\n') + `\n\n${owners} decides your case; reply 'wrong' if this is.` });
"""

AI_ERROR_JS = HELPERS_JS + r"""
// Step 13: an AI error after two retries gets "I don't know", reason logged.
return dontKnow('error: AI call failed after two retries', { error: String(($json.error && $json.error.message) || 'unknown') });
"""


def build() -> Workflow:
    w = Workflow("R13.1", "R13.1 Answer staff questions from approved sources")
    w.webhook(T, "r13-1-question",
              "Your staff chat calls this for each message to the assistant. Body: {message_id, conversation_id, asker, text, reply_to}; "
              "asker is the channel's signed-in sender, never anything typed in the message.", pos=[0, 0])
    w.config("Config", {
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
    }, pos=[260, 0])
    w.reserve_key("Step 2: Reserve key", KEY, pos=[520, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[780, 0])
    w.noop("Duplicate: stop", pos=[1040, -200], notes="This message was answered before.")
    w.chain(T, "Config", "Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    w.code("Step 3: Rules: HR, price or 'wrong'?", STEP3_JS, mode="runOnceForAllItems", pos=[1040, 0])
    w.switch("Step 3: Route", "={{ $json.route }}", ["hr", "price", "wrong", "search"], pos=[1300, 0])
    w.connect("New key?", "Step 3: Rules: HR, price or 'wrong'?", output=0)
    w.connect("Step 3: Rules: HR, price or 'wrong'?", "Step 3: Route")
    w.code("Step 3: R9.2's fixed reply", HR_JS, mode="runOnceForAllItems", pos=[1560, -480])
    w.code("Step 3: Price-list link", PRICE_JS, mode="runOnceForAllItems", pos=[1560, -320])
    w.pg("Read the answer's decision log",
         "SELECT (SELECT rules->>'owner' FROM decision_log WHERE recipe = 'R13.1' AND item = $1 ORDER BY id DESC LIMIT 1) AS owner, "
         "(SELECT rules->>'topic' FROM decision_log WHERE recipe = 'R13.1' AND item = $1 ORDER BY id DESC LIMIT 1) AS topic",
         args=[f"{EV}.reply_to"], pos=[1560, -160], notes="Who owns the answer the asker says is wrong.")
    w.code("Table 13.2: 'wrong' logs a gap", WRONG_JS, mode="runOnceForAllItems", pos=[1820, -160])
    w.connect("Step 3: Route", "Step 3: R9.2's fixed reply", output=0)
    w.connect("Step 3: Route", "Step 3: Price-list link", output=1)
    w.connect("Step 3: Route", "Read the answer's decision log", output=2)
    w.connect("Read the answer's decision log", "Table 13.2: 'wrong' logs a gap")

    cfg = "$('Config').first().json"
    w.http("Step 4: Read the asker's groups", "GET", f"={{{{ {cfg}.directory_url }}}}/users/{{{{ {EV}.asker }}}}",
           write=False, error_output=False, pos=[1560, 160], notes="Read-only directory access.")
    w.http("Step 5: Search current, in-date passages", "GET", f"={{{{ {cfg}.index_url }}}}/search",
           query={"_wrap": "1", "q": f"={{{{ {EV}.text }}}}", "status": "current",
                  "as_of": "={{ new Date().toISOString().slice(0, 10) }}",
                  "audience": f"={{{{ [{EV}.asker].concat($('Step 4: Read the asker\\'s groups').first().json.groups || []).join(',') }}}}"},
           write=False, error_output=False, pos=[1820, 160],
           notes="The index filters on audience, status and dates inside the query, before ranking.")
    w.http("Read the source register", "GET", f"={{{{ {cfg}.register_url }}}}/sources", query={"_wrap": "1"},
           write=False, error_output=False, pos=[2080, 160], notes="Owners, titles and links for each source.")
    w.code("Step 6: Rule: above the relevance threshold?", STEP6_JS, mode="runOnceForAllItems", pos=[2340, 160])
    w.if_("Any above the threshold?", "={{ $json.route }}", op="equals", right="continue", pos=[2600, 160])
    w.connect("Step 3: Route", "Step 4: Read the asker's groups", output=3)
    w.chain("Step 4: Read the asker's groups", "Step 5: Search current, in-date passages", "Read the source register",
            "Step 6: Rule: above the relevance threshold?", "Any above the threshold?")

    w.code("Step 7: Documents to check", FILES_JS, mode="runOnceForAllItems", pos=[2860, 160])
    w.http("Step 7: Read live sharing", "GET", f"={{{{ {cfg}.documents_url }}}}/files/{{{{ $json.file_id }}}}",
           write=False, error_output=False, pos=[3120, 160], notes="Who can open the document now, not the index's stored copy.")
    w.code("Step 7: Rule: drop documents the asker cannot open", STEP7_JS, mode="runOnceForAllItems", pos=[3380, 160])
    w.if_("Any left?", "={{ $json.route }}", op="equals", right="continue", pos=[3640, 160])
    w.connect("Any above the threshold?", "Step 7: Documents to check", output=0)
    w.chain("Step 7: Documents to check", "Step 7: Read live sharing", "Step 7: Rule: drop documents the asker cannot open", "Any left?")

    s7 = "$('Step 7: Rule: drop documents the asker cannot open').first().json"
    reg = "Object.fromEntries(($('Read the source register').first().json.items || []).map(r => [String(r.id), r]))"
    vars_js = (f"(() => {{ const reg = {reg}; return {{ question: {EV}.text, passages: {s7}.passages.map(p => "
               "`[${p.id}] ${(reg[String(p.source)] || {}).title || p.source} (effective ${p.effective})\\n<<<\\n${p.text}\\n>>>`).join('\\n\\n') }; })()")
    build_, call = ai_step(w, "Step 8", ROOT / "recipes/R13.1/prompts/answer.md", vars_js,
                           max_tokens=600, tries=3, pos_build=[3900, 160], pos_call=[4160, 160])
    w.connect("Any left?", build_, output=0)
    w.http("Step 11: Read the source register again", "GET", f"={{{{ {cfg}.register_url }}}}/sources", query={"_wrap": "1"},
           write=False, error_output=False, pos=[4420, 160], notes="Read after the AI step, so a source withdrawn since step 5 is caught.")
    w.connect(call, "Step 11: Read the source register again", output=0)
    w.code("Rules: steps 9 to 12", RULES_JS, mode="runOnceForAllItems", pos=[4680, 160], notes="The rules decide, not the AI.")
    w.connect("Step 11: Read the source register again", "Rules: steps 9 to 12")
    w.code("Step 13: AI error", AI_ERROR_JS, mode="runOnceForAllItems", pos=[4680, 400])
    w.connect(call, "Step 13: AI error", output=1)

    # ---- one outcome, one reply (Table 13.2) ----------------------------------
    w.code("Outcome", "return { json: $json };", pos=[4940, 0], notes="Every path's reply and log entry, as Table 13.2 sets them.")
    for n in ["Step 3: R9.2's fixed reply", "Step 3: Price-list link", "Table 13.2: 'wrong' logs a gap",
              "Rules: steps 9 to 12", "Step 13: AI error"]:
        w.connect(n, "Outcome")
    w.connect("Any above the threshold?", "Outcome", output=1)
    w.connect("Any left?", "Outcome", output=1)
    w.if_("Reply to send?", f"={{{{ {OUT}.reply || '' }}}}", op="notEmpty", pos=[5200, 0])
    w.connect("Outcome", "Reply to send?")
    w.http("Steps 12 and 13: Reply to the asker", "POST", f"={{{{ {cfg}.chat_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ conversation_id: {EV}.conversation_id, reply_to: {EV}.message_id, to: {EV}.asker, text: {OUT}.reply }}) }}}}",
           write=True, pos=[5460, -120])
    w.connect("Reply to send?", "Steps 12 and 13: Reply to the asker", output=0)
    w.if_("HR question?", f"={{{{ {OUT}.forward_to_hr }}}}", pos=[5720, 0])
    w.connect("Steps 12 and 13: Reply to the asker", "HR question?")
    w.connect("Reply to send?", "HR question?", output=1)
    w.http("Step 3: Pass the question to HR", "POST", f"={{{{ {cfg}.chat_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: {cfg}.hr_contact, subject: 'Personal HR question from ' + {EV}.asker, text: {EV}.text }}) }}}}",
           write=True, pos=[5980, -120])
    w.connect("HR question?", "Step 3: Pass the question to HR", output=0)
    w.if_("Gap?", f"={{{{ {OUT}.gap ? 'yes' : '' }}}}", op="notEmpty", pos=[6240, 0])
    w.connect("Step 3: Pass the question to HR", "Gap?")
    w.connect("HR question?", "Gap?", output=1)
    w.exception("Exception queue: gap", KEY, "gap", f"{OUT}.gap.topic", f"{OUT}.gap.owner", pos=[6500, -120])
    w.connect("Gap?", "Exception queue: gap", output=0)

    w.finish_key("Mark key done", KEY, "done", f"{OUT}.outcome", pos=[6760, 0])
    w.decision_log("Decision log", KEY, f"{OUT}.decision", f"JSON.stringify({OUT}.rules)", pos=[7020, 0])
    w.connect("Exception queue: gap", "Mark key done")
    w.connect("Gap?", "Mark key done", output=1)
    w.connect("Mark key done", "Decision log")

    w.finish_key("Mark key failed", KEY, "failed", "'write failed: ' + ($json.error && $json.error.message || 'unknown')", pos=[6760, 400])
    w.exception("Exception queue: write failed", KEY, "write failed",
                "'Reply or hand-off failed; check the conversation, never retried'", f"{cfg}.gap_owner", pos=[7020, 400])
    w.connect("Steps 12 and 13: Reply to the asker", "Mark key failed", output=1)
    w.connect("Step 3: Pass the question to HR", "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")
    return w
