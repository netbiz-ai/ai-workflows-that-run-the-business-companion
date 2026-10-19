"""R4.3 Draft a reply from approved sources for a person to edit and send.

Source: book Chapter 4, recipe R4.3, build steps 1 to 8 (recipes/R4.3/build-spec.md);
AI step: recipes/R4.3/prompts/draft-reply.md.

Step 3 reads R4.2's decision log (the companion's R4.2 build writes one row per
message, with the message ID in its rules, and one row per notice). The draft is
only ever an internal note; nothing in this workflow can send to a customer.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, _uid, ai_step  # noqa: E402

T = "Step 1: Ticket enters a draft queue"
R = "Step 8: Reply posted"
EV = f"$('{T}').first().json.body"
KEY = f"{EV}.ticket_id + ':' + {EV}.message_id"
CFG = "$('Config').first().json"
TK = "$('Read the ticket').first().json"

R42_SQL = (
    "SELECT coalesce(bool_or(rules ? 'level'), false) AS escalated, "
    "coalesce(bool_or(rules->>'message_id' = $2), false) AS logged "
    "FROM decision_log WHERE recipe = 'R4.2' AND item = $1"
)

R42_JS = r"""
// Step 3: stop if R4.2 escalated the ticket; if R4.2 has not logged this message yet,
// recheck up to the set number of times, then flag it for a person.
const cfg = $('Config').first().json;
const r = $input.first().json;
const checks = $runIndex + 1;
const state = r.escalated ? 'escalated' : r.logged ? 'clear' : checks > cfg.r42_rechecks ? 'flag' : 'wait';
return [{ json: { state, checks, reason: 'R4.2 has not logged it', detail: `not in R4.2's log after ${checks - 1} rechecks` } }];
"""

SOURCES_PLAN_JS = r"""
// Step 4: which sources this queue may draft from (Table 4.1).
const cfg = $('Config').first().json;
const t = $('Read the ticket').first().json;
const q = cfg.draft_queues.find(d => d.queue === t.queue);
if (!q) return [{ json: { listed: false, needs_article: false, needs_order: false } }];
return [{ json: { listed: true, queue: q.queue, topic: q.article_topic || '', needs_article: !!q.article_topic,
  needs_order: !!q.order && !!t.order_id, order_missing: !!q.order && !t.order_id } }];
"""

SOURCES_JS = r"""
// Step 4: with no current approved article (or no order where the queue drafts from one), flag "no source" and stop.
const cfg = $('Config').first().json;
const plan = $('Step 4: Rule: which sources?').first().json;
const today = new Date().toISOString().slice(0, 10);
if (!plan.listed) return [{ json: { found: false, reason: 'no source', detail: 'not a draft queue in Table 4.1' } }];
const sources = [];
if (plan.needs_article) {
  const all = $('Step 4: Read the approved articles').isExecuted ? ($('Step 4: Read the approved articles').first().json.items || []) : [];
  const current = all.filter(a => a.status === 'approved' && (!a.review_date || a.review_date >= today));
  if (!current.length) return [{ json: { found: false, reason: 'no source', detail: all.length ? 'article past its review date' : 'no approved article for the topic' } }];
  const a = current[0];
  sources.push({ id: a.id, kind: 'article', text: `${a.title || ''}\n${a.text || ''}`.trim() });
}
if (plan.order_missing) return [{ json: { found: false, reason: 'no source', detail: 'no order on the ticket' } }];
if (plan.needs_order) {
  const o = $('Step 4: Read the order').first().json;
  sources.push({ id: o.id, kind: 'order', text: Object.entries(o).filter(([k]) => k !== 'id').map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join('\n') });
}
if (!sources.length) return [{ json: { found: false, reason: 'no source', detail: 'no source for this queue' } }];
return [{ json: { found: true, sources, sources_text: sources.map(s => `[${s.id}]\n${s.text}`).join('\n\n') } }];
"""

CLAIM_JS = AI_PARSE_JS + r"""
// Step 6: each sentence or question stating a policy, price, date, duration, amount or commitment
// cites a retrieved source; its amounts, dates and durations appear in that source; a commitment
// word fails unless that source contains it. The rules test form, not meaning.
const cfg = $('Config').first().json;
const src = $('Step 4: Rule: sources found?').first().json.sources;
const p = parseAi($('Step 5: AI call').first().json, ['draft']);
if (!p.ok || typeof p.value.draft !== 'string' || !p.value.draft.trim())
  return [{ json: { pass: false, reason: 'claim check failed', detail: p.ok ? 'empty draft' : p.problem, rules: { claim_check: p.ok ? 'empty draft' : p.problem } } }];
const draft = p.value.draft.trim();
const byId = Object.fromEntries(src.map(s => [s.id, s.text.toLowerCase()]));
const commit = cfg.commitment_words.map(w => w.toLowerCase());
const NUMW = '(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fourteen|fifteen|twenty|thirty|forty|sixty|ninety|hundred)';
const UNIT = '(?:working |business |calendar )?(?:hour|day|week|month|year)s?';
const DAYS = '(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|may|june|july|august|september|october|november|december)';
const units = draft.match(/[^.?!\n]+(?:[.?!]+|$)(?:\s*\[[^\]\n]+\])*/g) || [];
const problems = [];
const cited = new Set();
units.forEach((u, i) => {
  const ids = [...u.matchAll(/\[([^\]\n]+)\]/g)].map(m => m[1].trim());
  const body = u.replace(/\[[^\]\n]+\]/g, ' ').toLowerCase();
  const tokens = [];
  for (const m of body.matchAll(/[$€£]?\d(?:[\d,.:\/-]*\d)?%?/g)) tokens.push(m[0]);
  for (const m of body.matchAll(new RegExp(`\\b${NUMW}\\s+${UNIT}\\b`, 'g'))) tokens.push(m[0]);
  for (const m of body.matchAll(new RegExp(`\\b${DAYS}\\b`, 'g'))) tokens.push(m[0]);
  const commits = commit.filter(w => new RegExp(`\\b${w}`).test(body));
  const policy = cfg.claim_words.some(w => new RegExp(`\\b${w.toLowerCase()}`).test(body));
  if (!tokens.length && !commits.length && !policy) return;
  const n = `sentence ${i + 1}`;
  // A GAP sentence says the sources do not answer, so it cites nothing; it may still offer nothing.
  if (/\bGAP\b/.test(u) && !ids.length) { for (const w of commits) problems.push(`${n}: commitment word "${w}" in a GAP sentence`); return; }
  if (!ids.length) { problems.push(`${n}: no source cited`); return; }
  const unknown = ids.filter(id => !(id in byId));
  if (unknown.length) { problems.push(`${n}: cites a source not retrieved (${unknown.join(', ')})`); return; }
  ids.forEach(id => cited.add(id));
  const text = ids.map(id => byId[id]).join('\n');
  for (const t of tokens) if (!text.includes(t)) problems.push(`${n}: "${t}" is not in the cited source`);
  for (const w of commits) if (!text.includes(w)) problems.push(`${n}: commitment word "${w}" is not in the cited source`);
});
if (problems.length) return [{ json: { pass: false, reason: 'claim check failed', detail: problems.join('; '), rules: { claim_check: problems } } }];
const used = src.filter(s => cited.has(s.id)).map(s => s.id);
const note = `${draft}\n\nSources: ${(used.length ? used : src.map(s => s.id)).join(', ')}`;
return [{ json: { pass: true, note, rules: { claim_check: 'passed', sources: src.map(s => s.id), gap: /\bGAP\b/.test(draft) } } }];
"""

FLAG_JS = r"""
// Step 7: no draft; a person writes the reply. Every reason comes here.
return $input.all().map(i => ({ json: { reason: i.json.reason || 'no draft', detail: i.json.detail || '', rules: i.json.rules || {} } }));
"""

OUTCOME_JS = r"""
// Step 8: compare the posted reply with the saved draft: unchanged, edited or discarded.
const cfg = $('Config').first().json;
const norm = s => String(s || '').replace(/\n\nSources:.*$/s, '').replace(/\[[^\]\n]+\]/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
const draft = norm($('Step 8: Read the draft note').first().json.text);
const reply = norm($('Step 8: Read the reply').first().json.text);
const words = draft.split(' ').filter(Boolean);
const inReply = new Set(reply.split(' '));
const share = words.length ? words.filter(w => inReply.has(w)).length / words.length : 0;
const outcome = draft === reply ? 'unchanged' : share >= cfg.edited_min_share ? 'edited' : 'discarded';
return [{ json: { outcome, share: Math.round(share * 100) / 100 } }];
"""


def _tries(w: Workflow, name: str, tries: int) -> None:
    """Lookups in R4.3 fail after one retry (book failure table)."""
    for n in w.nodes:
        if n["name"] == name:
            n.update(retryOnFail=tries > 1, maxTries=tries)


def build() -> Workflow:
    w = Workflow("R4.3", "R4.3 Draft a reply from approved sources")
    w.webhook(T, "r4-3-draft-queue",
              "Your helpdesk calls this when a ticket enters a draft queue (Table 4.1). Body: {ticket_id, message_id}.", pos=[0, 0])
    w.webhook(R, "r4-3-reply-posted",
              "Your helpdesk calls this when a reply is posted on a ticket. Body: {ticket_id, reply_id}.", pos=[0, 1100])
    w.config("Config", {
        "helpdesk_url": "https://<your helpdesk API>",
        "articles_url": "https://<your knowledge base API>",
        "orders_url": "https://<your order system API>",
        "draft_queues": [
            {"queue": "<your warranty queue>", "article_topic": "warranty", "order": False},
            {"queue": "<your returns queue>", "article_topic": "returns", "order": True},
            {"queue": "<your delivery queue>", "article_topic": None, "order": True},
        ],
        "r42_recheck_seconds": 300,
        "r42_rechecks": 3,
        "commitment_words": ["free", "refund", "replace", "credit", "visit"],
        "claim_words": ["<your policy words, such as warranty, return, price>"],
        "edited_min_share": 0.5,
        "flag_owner": "<your draft owner>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 550])
    w.connect(T, "Config")
    w.connect(R, "Config")
    w.if_("Reply posted?", f"={{{{ $('{R}').isExecuted }}}}", pos=[520, 550])
    w.connect("Config", "Reply posted?")

    # ---- steps 1 to 3 -------------------------------------------------------------
    w.http("Read the ticket", "GET", f"={{{{ {CFG}.helpdesk_url }}}}/tickets/{{{{ {EV}.ticket_id }}}}",
           write=False, error_output=False, pos=[780, 0])
    w.connect("Reply posted?", "Read the ticket", output=1)
    w.reserve_key("Step 2: Reserve key", KEY, pos=[1040, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1300, 0], notes="One draft per message.")
    w.noop("Duplicate: stop", pos=[1560, -200], notes="A draft was already made for this message.")
    w.chain("Read the ticket", "Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    w.pg("Step 3: Read R4.2's log", R42_SQL, args=[f"{EV}.ticket_id", f"{EV}.message_id"], pos=[1560, 0],
         notes="R4.2's decision log: has it escalated the ticket, and has it logged this message?")
    w.connect("New key?", "Step 3: Read R4.2's log", output=0)
    w.code("Step 3: Rule: escalated, cleared or not logged?", R42_JS, mode="runOnceForAllItems", pos=[1820, 0])
    w.connect("Step 3: Read R4.2's log", "Step 3: Rule: escalated, cleared or not logged?")
    w.switch("R4.2 state", "={{ $json.state }}", ["escalated", "clear", "wait", "flag"], pos=[2080, 0])
    w.connect("Step 3: Rule: escalated, cleared or not logged?", "R4.2 state")
    w.node("Step 3: Wait, then recheck", "n8n-nodes-base.wait", 1.1,
           {"resume": "timeInterval", "amount": f"={{{{ {CFG}.r42_recheck_seconds }}}}", "unit": "seconds"},
           pos=[2080, -260], webhookId=_uid("R4.3/step-3-wait"), notes="Five minutes by default (Config).")
    w.connect("R4.2 state", "Step 3: Wait, then recheck", output=2)
    w.connect("Step 3: Wait, then recheck", "Step 3: Read R4.2's log")
    w.finish_key("Mark key done: escalated", KEY, "done", "'escalated by R4.2; no draft'", pos=[2340, -200])
    w.decision_log("Decision log: escalated", f"{EV}.ticket_id", "'no draft: escalated by R4.2'",
                   f"JSON.stringify({{ message_id: {EV}.message_id, r42: 'escalated' }})", pos=[2600, -200])
    w.connect("R4.2 state", "Mark key done: escalated", output=0)
    w.connect("Mark key done: escalated", "Decision log: escalated")

    # ---- step 4 -----------------------------------------------------------------------
    w.code("Step 4: Rule: which sources?", SOURCES_PLAN_JS, mode="runOnceForAllItems", pos=[2340, 0])
    w.connect("R4.2 state", "Step 4: Rule: which sources?", output=1)
    w.if_("Article needed?", "={{ $json.needs_article }}", pos=[2600, 0])
    w.connect("Step 4: Rule: which sources?", "Article needed?")
    w.http("Step 4: Read the approved articles", "GET", f"={{{{ {CFG}.articles_url }}}}/articles",
           query={"_wrap": "1", "topic": "={{ $('Step 4: Rule: which sources?').first().json.topic }}", "status": "approved"},
           write=False, pos=[2860, -120])
    _tries(w, "Step 4: Read the approved articles", 2)
    w.connect("Article needed?", "Step 4: Read the approved articles", output=0)
    w.if_("Order needed?", "={{ $('Step 4: Rule: which sources?').first().json.needs_order }}", pos=[3120, 0])
    w.connect("Step 4: Read the approved articles", "Order needed?", output=0)
    w.connect("Article needed?", "Order needed?", output=1)
    w.http("Step 4: Read the order", "GET", f"={{{{ {CFG}.orders_url }}}}/orders/{{{{ {TK}.order_id }}}}",
           write=False, pos=[3380, -120])
    _tries(w, "Step 4: Read the order", 2)
    w.connect("Order needed?", "Step 4: Read the order", output=0)
    w.code("Step 4: Rule: sources found?", SOURCES_JS, mode="runOnceForAllItems", pos=[3640, 0])
    w.connect("Step 4: Read the order", "Step 4: Rule: sources found?", output=0)
    w.connect("Order needed?", "Step 4: Rule: sources found?", output=1)
    w.code("Step 4: Lookup failed",
           "return [{ json: { reason: 'lookup failed', detail: String(($json.error && $json.error.message) || '') + ' (after one retry)' } }];",
           mode="runOnceForAllItems", pos=[3640, 300])
    w.connect("Step 4: Read the approved articles", "Step 4: Lookup failed", output=1)
    w.connect("Step 4: Read the order", "Step 4: Lookup failed", output=1)
    w.if_("Sources found?", "={{ $json.found }}", pos=[3900, 0])
    w.connect("Step 4: Rule: sources found?", "Sources found?")

    # ---- steps 5 to 7 -----------------------------------------------------------------
    vars_js = (f"{{ sources: $('Step 4: Rule: sources found?').first().json.sources_text, "
               f"subject: {TK}.subject, body: {TK}.body }}")
    build, call = ai_step(w, "Step 5", ROOT / "recipes/R4.3/prompts/draft-reply.md", vars_js,
                          max_tokens=4096, tries=2, pos_build=[4160, 0], pos_call=[4420, 0])
    w.connect("Sources found?", build, output=0)
    w.code("Step 6: Rule: claim check", CLAIM_JS, mode="runOnceForAllItems", pos=[4680, 0],
           notes="The rules test form, not meaning; the sender still checks what each sentence promises.")
    w.connect(call, "Step 6: Rule: claim check", output=0)
    w.code("Step 7: AI error",
           "return [{ json: { pass: false, reason: 'AI error', detail: String(($json.error && $json.error.message) || '') + ' (after one retry)' } }];",
           mode="runOnceForAllItems", pos=[4680, 300])
    w.connect(call, "Step 7: AI error", output=1)
    w.if_("Claims check out?", "={{ $json.pass }}", pos=[4940, 0])
    w.connect("Step 6: Rule: claim check", "Claims check out?")

    notes = f"={{{{ {CFG}.helpdesk_url }}}}/notes"
    w.http("Step 7: Save the draft as an internal note", "POST", notes,
           body=f"={{{{ JSON.stringify({{ ticket_id: {EV}.ticket_id, message_id: {EV}.message_id, internal: true, kind: 'draft', text: $json.note }}) }}}}",
           write=True, pos=[5200, -120], notes="Internal only; a person edits and sends every reply.")
    w.connect("Claims check out?", "Step 7: Save the draft as an internal note", output=0)
    w.finish_key("Mark key done: draft saved", KEY, "done", "'draft saved'", pos=[5460, -120])
    w.decision_log("Decision log: draft saved", f"{EV}.ticket_id", "'draft saved'",
                   f"JSON.stringify(Object.assign({{ message_id: {EV}.message_id, note_id: $('Step 7: Save the draft as an internal note').first().json.id }}, "
                   f"$('Step 6: Rule: claim check').first().json.rules))", pos=[5720, -120])
    w.chain("Step 7: Save the draft as an internal note", "Mark key done: draft saved", "Decision log: draft saved")

    w.code("Step 7: No draft: flag the ticket", FLAG_JS, mode="runOnceForAllItems", pos=[5200, 360])
    for src, out in [("R4.2 state", 3), ("Sources found?", 1), ("Step 4: Lookup failed", 0),
                     ("Claims check out?", 1), ("Step 7: AI error", 0)]:
        w.connect(src, "Step 7: No draft: flag the ticket", output=out)
    flag = "$('Step 7: No draft: flag the ticket').first().json"
    w.http("Step 7: Post the flag note", "POST", notes,
           body=f"={{{{ JSON.stringify({{ ticket_id: {EV}.ticket_id, message_id: {EV}.message_id, internal: true, kind: 'flag', "
                f"text: 'No AI draft (' + {flag}.reason + '): write this reply yourself.' }}) }}}}",
           write=True, pos=[5460, 360])
    w.exception("Exception queue: no draft", f"{EV}.ticket_id", "no draft",
                f"{flag}.reason + ': ' + {flag}.detail", f"{CFG}.flag_owner", pos=[5720, 360])
    w.finish_key("Mark key done: flagged", KEY, "done", f"'flagged: ' + {flag}.reason", pos=[5980, 360])
    w.decision_log("Decision log: flagged", f"{EV}.ticket_id", f"'no draft: ' + {flag}.reason",
                   f"JSON.stringify(Object.assign({{ message_id: {EV}.message_id, detail: {flag}.detail }}, {flag}.rules))", pos=[6240, 360])
    w.chain("Step 7: No draft: flag the ticket", "Step 7: Post the flag note", "Exception queue: no draft",
            "Mark key done: flagged", "Decision log: flagged")

    w.finish_key("Mark key failed", KEY, "failed", "'note write failed'", pos=[5980, 700])
    w.exception("Exception queue: write failed", f"{EV}.ticket_id", "write failed",
                "'Note write failed, never retried; a person writes the reply'", f"{CFG}.flag_owner", pos=[6240, 700])
    for n in ["Step 7: Save the draft as an internal note", "Step 7: Post the flag note"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- step 8 -------------------------------------------------------------------------
    RV = f"$('{R}').first().json.body"
    w.reserve_key("Step 8: Reserve key", f"'reply:' + {RV}.reply_id", pos=[780, 1100])
    w.if_("New reply?", "={{ $json.is_new }}", pos=[1040, 1100])
    w.connect("Reply posted?", "Step 8: Reserve key", output=0)
    w.connect("Step 8: Reserve key", "New reply?")
    w.pg("Step 8: Find the draft", "SELECT rules->>'note_id' AS note_id FROM decision_log "
         "WHERE recipe = 'R4.3' AND item = $1 AND decision = 'draft saved' ORDER BY id DESC LIMIT 1",
         args=[f"{RV}.ticket_id"], pos=[1300, 1100])
    w.connect("New reply?", "Step 8: Find the draft", output=0)
    w.if_("Was there a draft?", "={{ $json.note_id }}", op="notEmpty", pos=[1560, 1100])
    w.connect("Step 8: Find the draft", "Was there a draft?")
    w.http("Step 8: Read the draft note", "GET", f"={{{{ {CFG}.helpdesk_url }}}}/notes/{{{{ $json.note_id }}}}",
           write=False, error_output=False, pos=[1820, 1100])
    w.http("Step 8: Read the reply", "GET", f"={{{{ {CFG}.helpdesk_url }}}}/replies/{{{{ {RV}.reply_id }}}}",
           write=False, error_output=False, pos=[2080, 1100])
    w.code("Step 8: Rule: unchanged, edited or discarded?", OUTCOME_JS, mode="runOnceForAllItems", pos=[2340, 1100])
    w.decision_log("Step 8: Decision log: draft outcome", f"{RV}.ticket_id", "'draft ' + $json.outcome",
                   f"JSON.stringify({{ reply_id: {RV}.reply_id, note_id: $('Was there a draft?').first().json.note_id, words_kept: $json.share }})",
                   pos=[2600, 1100])
    w.connect("Was there a draft?", "Step 8: Read the draft note", output=0)
    w.chain("Step 8: Read the draft note", "Step 8: Read the reply", "Step 8: Rule: unchanged, edited or discarded?",
            "Step 8: Decision log: draft outcome")
    w.finish_key("Step 8: Mark key done", f"'reply:' + {RV}.reply_id", "done", "'outcome logged'", pos=[2860, 1100])
    w.connect("Step 8: Decision log: draft outcome", "Step 8: Mark key done")
    w.finish_key("Step 8: Mark key done: no draft", f"'reply:' + {RV}.reply_id", "done", "'no draft to compare'", pos=[1820, 1300])
    w.connect("Was there a draft?", "Step 8: Mark key done: no draft", output=1)
    return w
