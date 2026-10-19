"""R13.3 Turn a resolved ticket into a draft knowledge article for the owner to approve.

Source: book Chapter 13, recipe R13.3, build steps 1 to 11 and its failure table (recipes/R13.3/build-spec.md);
AI step: recipes/R13.3/prompts/draft-article.md.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

T = "Step 1: Ticket resolved with the reusable tag"
D = "Step 10: Nadia approves or discards"
W = "Failure table: Each week"
TK = "$('Read the ticket').first().json"
KEY = f"{TK}.id + ':' + {TK}.resolved_at"
DEV = f"$('{D}').first().json.body"
DR = "$('Read the draft').first().json"
DKEY = f"{DEV}.draft_id + ':' + {DEV}.decision"
CFG = "$('Config').first().json"

# Step 3's replacement and step 4's check, shared with step 6's rerun.
PII_JS = r"""
const esc = s => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
// The customer's own details, each with its label; a phone matches with any spacing.
function customerValues(t) {
  const c = t.customer || {};
  const out = [];
  // Most specific first, so a name inside an email address is replaced with the address.
  if (c.email) out.push([c.email, '[customer email]']);
  if (c.address) { out.push([c.address, '[customer address]']); out.push([String(c.address).split(',')[0], '[customer address]']); }
  if (c.name) out.push([c.name, '[customer name]']);
  if (t.order_number) out.push([t.order_number, '[order number]']);
  if (c.name) for (const part of String(c.name).split(/\s+/)) if (part.length >= 3) out.push([part, '[customer name]']);
  const res = out.map(([v, label]) => [new RegExp(esc(v), 'gi'), label]);
  if (c.phone) res.unshift([new RegExp(String(c.phone).replace(/\D/g, '').split('').join('[\\s().-]*'), 'g'), '[customer phone]']);
  return res;
}
function personalData(text, t, cfg) {
  const found = [];
  for (const p of cfg.personal_data_patterns) if (new RegExp(p.pattern, 'i').test(text)) found.push(p.name);
  for (const [re, label] of customerValues(t)) { re.lastIndex = 0; if (re.test(text)) found.push(label); }
  return [...new Set(found)];
}
"""

STEP3_JS = PII_JS + r"""
// Step 3: drop the access-code field; replace the customer's name, email, phone, address and order number with labels.
// Step 4: if such patterns remain, the ticket goes to the article owner with no AI call.
const cfg = $('Config').first().json;
const t = Object.assign({}, $('Read the ticket').first().json);
delete t[cfg.access_code_field];  // never read, never sent
const label = s => customerValues(t).reduce((acc, [re, l]) => acc.replace(re, l), String(s || ''));
const subject = label(t.subject);
const ticket_text = (t.conversation || []).map(m => `${m.from}: ${label(m.text)}`).concat(t.resolution ? [`Resolution: ${label(t.resolution)}`] : []).join('\n');
const remaining = personalData(subject + '\n' + ticket_text, t, cfg);
return [{ json: { clean: remaining.length === 0, remaining, subject, ticket_text } }];
"""

RULES_JS = AI_PARSE_JS + PII_JS + r"""
// Steps 6 to 9: the rules decide what the draft holds; nothing is published here.
const cfg = $('Config').first().json;
const t = $('Read the ticket').first().json;
const FIELDS = ['title', 'question', 'answer', 'steps', 'policy_claims'];
const p = parseAi($('Step 5: AI call').first().json, FIELDS);
const fail = (reason, problem) => [{ json: { route: 'set_aside', reason, detail: problem } }];
// Step 6: anything outside the fields fails; step 4's check reruns, and a match discards the draft.
if (!p.ok) return fail('draft failed the field check', p.problem);
const d = p.value;
if (Object.keys(d).some(k => !FIELDS.includes(k))) return fail('draft failed the field check', 'field outside the schema');
if (['title', 'question', 'answer'].some(k => typeof d[k] !== 'string') || ['steps', 'policy_claims'].some(k => !Array.isArray(d[k]) || d[k].some(x => typeof x !== 'string')))
  return fail('draft failed the field check', 'field of the wrong type');
const all = [d.title, d.question, d.answer, ...d.steps, ...d.policy_claims].join('\n');
const pii = personalData(all, t, cfg);
if (pii.length) return [{ json: { route: 'discard', reason: 'draft discarded: personal data', detail: pii.join(', ') } }];

// Step 7: a currency amount becomes the price-list link.
const MONEY = /[$€£]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:usd|eur|gbp|dollars?|euros?|pounds?)\b/gi;
const priced = [];
const price = s => s.replace(MONEY, m => { priced.push(m); return `[price: see ${cfg.price_list_link}]`; });
const draft = { title: price(d.title), question: price(d.question), answer: price(d.answer), steps: d.steps.map(price), policy_claims: d.policy_claims.map(price) };

// Step 8: a figure off the policy-figures list, or any warranty, returns or delivery sentence, is marked "needs source".
const N = '(?:\\d+(?:\\.\\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fourteen|thirty|sixty|ninety)';
const FIGURE = new RegExp(`\\b${N}[\\s-](?:day|week|month|year)s?\\b|\\b\\d+(?:\\.\\d+)?\\s?%`, 'gi');
const listed = (cfg.policy_figures || []).map(f => String(f).toLowerCase());
const sentences = [
  ...draft.answer.split(/(?<=[.!?])\s+/).filter(Boolean).map(text => ({ field: 'answer', text })),
  ...draft.steps.map(text => ({ field: 'steps', text })),
  ...draft.policy_claims.map(text => ({ field: 'policy_claims', text })),
];
const claims = [];
for (const s of sentences) {
  const low = s.text.toLowerCase();
  const off = (s.text.match(FIGURE) || []).filter(f => !listed.some(l => l.includes(f.toLowerCase().replace('-', ' ')) || l.includes(f.toLowerCase())));
  const topic = cfg.policy_topics.find(pt => pt.keywords.some(k => low.includes(String(k).toLowerCase())));
  if (off.length || topic) {
    claims.push({ field: s.field, text: s.text, needs_source: true, owner: topic ? topic.owner : cfg.article_owner,
                  source: topic ? topic.source : null, reason: [topic ? `${topic.keywords[0]} statement` : null, off.length ? `figure off the list: ${off.join(', ')}` : null].filter(Boolean).join('; '),
                  worded_by: null });
  } else if (s.field === 'policy_claims') {
    claims.push({ field: s.field, text: s.text, needs_source: false, owner: null, source: null, reason: null, worded_by: null });
  }
}

// Step 9: a close title match makes the draft a suggested update.
const words = s => new Set(String(s).toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(x => x.length >= 3));
const sim = (a, b) => { const A = words(a), B = words(b); const i = [...A].filter(x => B.has(x)).length; return A.size + B.size ? i / (A.size + B.size - i) : 0; };
const threshold = Number(cfg.title_match);  // an unfilled placeholder is NaN: every draft is new
const best = ($('Step 9: Read published articles').first().json.items || [])
  .map(a => ({ id: a.id, title: a.title, score: sim(draft.title, a.title) })).sort((a, b) => b.score - a.score)[0];
const update = best && best.score >= threshold ? best : null;

const needs = claims.filter(c => c.needs_source);
return [{ json: {
  route: 'draft',
  draft: Object.assign(draft, {
    ticket_id: t.id, kind: update ? 'suggested update' : 'new', updates_article: update ? update.id : null,
    claims, status: 'awaiting approval', created: new Date().toISOString().slice(0, 10),
    checks: { fields: 'passed', personal_data: 'passed', prices_linked: priced.length, needs_source: needs.length, title_match: best ? best.score : 0 } }),
  owners: [...new Set(needs.map(c => c.owner))],
} }];
"""

DECIDE_JS = r"""
// Step 10: only the article owner approves or discards; every "needs source" claim must be worded by its source's owner first.
const cfg = $('Config').first().json;
const ev = $('Step 10: Nadia approves or discards').first().json.body;
const d = $('Read the draft').first().json;
const blocked = reason => [{ json: { outcome: 'refuse', reason } }];
if (String(ev.by).toLowerCase() !== String(cfg.article_owner).toLowerCase()) return blocked(`decision by ${ev.by}, not the article owner`);
if (d.status !== 'awaiting approval') return blocked(`draft is ${d.status}`);
if (ev.decision === 'discard') return [{ json: { outcome: 'discard' } }];
if (ev.decision !== 'approve') return blocked(`unknown decision ${ev.decision}`);
const unworded = (d.claims || []).filter(c => c.needs_source && (!c.worded_by || String(c.worded_by).toLowerCase() !== String(c.owner).toLowerCase()));
if (unworded.length) return blocked(`needs source, not yet worded by ${[...new Set(unworded.map(c => c.owner))].join(', ')}`);
// Step 11: the register needs review and expiry dates, or R13.2 withdraws the article.
const DAY = 86400000, today = new Date(new Date().toISOString().slice(0, 10) + 'T00:00:00Z');
const review = Number(cfg.article_review_days);
const review_date = Number.isFinite(review) ? new Date(today.getTime() + review * DAY).toISOString().slice(0, 10) : null;
const expiry_date = review_date ? new Date(today.getTime() + (review + cfg.expiry_after_review_days) * DAY).toISOString().slice(0, 10) : null;
const article = { title: d.title, question: d.question, answer: d.answer, steps: d.steps,
                  policy_statements: (d.claims || []).filter(c => c.field === 'policy_claims' || c.needs_source).map(c => c.text),
                  source_ticket: d.ticket_id, owner: cfg.article_owner };
return [{ json: { outcome: d.kind === 'suggested update' && d.updates_article ? 'publish_update' : 'publish_new', article, review_date, expiry_date } }];
"""

WEEKLY_JS = r"""
// Failure table: a weekly count of drafts over 14 days old, for the article owner to clear.
const cfg = $('Config').first().json;
const cutoff = new Date(Date.now() - cfg.old_draft_days * 86400000).toISOString().slice(0, 10);
const old = ($('Read drafts awaiting approval').first().json.items || []).filter(d => String(d.created) < cutoff);
return [{ json: { count: old.length, ids: old.map(d => d.id) } }];
"""


def build() -> Workflow:
    w = Workflow("R13.3", "R13.3 Turn a resolved ticket into a draft knowledge article")
    w.webhook(T, "r13-3-ticket-resolved",
              "Your helpdesk calls this when a ticket is resolved with the \"reusable\" tag (filter on the tag in the helpdesk). Body: {ticket_id}.",
              pos=[0, 0])
    w.webhook(D, "r13-3-draft-decision",
              "Your drafts area calls this when the article owner approves or discards a draft. Body: {draft_id, decision: approve | discard, by}.",
              pos=[0, 900])
    w.node(W, "n8n-nodes-base.scheduleTrigger", 1.2,
           {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1, "triggerAtDay": [1], "triggerAtHour": 8}]}},
           pos=[0, 1400], notes="Weekly, Monday 08:00: the count of old drafts in the failure table.")
    w.config("Config", {
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
    }, pos=[260, 700])
    for trig in (T, D, W):
        w.connect(trig, "Config")
    w.if_("Weekly count?", f"={{{{ $('{W}').isExecuted }}}}", pos=[520, 700])
    w.if_("Draft decision?", f"={{{{ $('{D}').isExecuted }}}}", pos=[780, 700])
    w.connect("Config", "Weekly count?")
    w.connect("Weekly count?", "Draft decision?", output=1)

    msgs = f"={{{{ {CFG}.messaging_url }}}}/messages"
    owner = f"{CFG}.article_owner"

    # ---- ticket path: steps 1 to 10 -------------------------------------------
    w.http("Read the ticket", "GET", f"={{{{ {CFG}.helpdesk_url }}}}/tickets/{{{{ $('{T}').first().json.body.ticket_id }}}}",
           write=False, error_output=False, pos=[1040, 0])
    w.if_("Step 1: Resolved with the tag?",
          f"={{{{ $json.status === 'resolved' && ($json.tags || []).includes({CFG}.reusable_tag) }}}}", pos=[1300, 0])
    w.noop("Not resolved and tagged: stop", pos=[1560, -200])
    w.reserve_key("Step 2: Reserve key", KEY, pos=[1560, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1820, 0])
    w.noop("Duplicate: stop", pos=[2080, -200], notes="This resolution was drafted before.")
    w.connect("Draft decision?", "Read the ticket", output=1)
    w.connect("Read the ticket", "Step 1: Resolved with the tag?")
    w.connect("Step 1: Resolved with the tag?", "Step 2: Reserve key", output=0)
    w.connect("Step 1: Resolved with the tag?", "Not resolved and tagged: stop", output=1)
    w.connect("Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    w.code("Steps 3 and 4: Rule: replace customer details, then check none remain", STEP3_JS, mode="runOnceForAllItems", pos=[2080, 0],
           notes="The access-code field is dropped here and never read again.")
    w.if_("Step 4: None remain?", "={{ $json.clean }}", pos=[2340, 0])
    w.connect("New key?", "Steps 3 and 4: Rule: replace customer details, then check none remain", output=0)
    w.connect("Steps 3 and 4: Rule: replace customer details, then check none remain", "Step 4: None remain?")
    s3 = "$('Steps 3 and 4: Rule: replace customer details, then check none remain').first().json"
    w.code("Step 4: Set aside, no AI call", f"return [{{ json: {{ route: 'set_aside', reason: 'personal data remains', detail: {s3}.remaining.join(', ') }} }}];",
           mode="runOnceForAllItems", pos=[2600, 240])
    w.connect("Step 4: None remain?", "Step 4: Set aside, no AI call", output=1)

    vars_js = f"{{ article_template: {CFG}.article_template, subject: {s3}.subject, ticket_text: {s3}.ticket_text }}"
    build_, call = ai_step(w, "Step 5", ROOT / "recipes/R13.3/prompts/draft-article.md", vars_js,
                           max_tokens=1200, tries=3, pos_build=[2600, 0], pos_call=[2860, 0])
    w.connect("Step 4: None remain?", build_, output=0)
    w.http("Step 9: Read published articles", "GET", f"={{{{ {CFG}.kb_url }}}}/articles", query={"_wrap": "1"},
           write=False, error_output=False, pos=[3120, 0])
    w.connect(call, "Step 9: Read published articles", output=0)
    w.code("Rules: steps 6 to 9", RULES_JS, mode="runOnceForAllItems", pos=[3380, 0], notes="The rules decide, not the AI.")
    w.connect("Step 9: Read published articles", "Rules: steps 6 to 9")
    w.code("Step 5: AI error", "return [{ json: { route: 'set_aside', reason: 'AI error after two retries', detail: String(($json.error && $json.error.message) || '') } }];",
           mode="runOnceForAllItems", pos=[3380, 240])
    w.connect(call, "Step 5: AI error", output=1)

    w.code("Outcome", "return { json: $json };", pos=[3640, 120])
    for n in ["Rules: steps 6 to 9", "Step 5: AI error", "Step 4: Set aside, no AI call"]:
        w.connect(n, "Outcome")
    OUT = "$('Outcome').item.json"
    w.switch("Draft or exception?", "={{ $json.route }}", ["draft", "set_aside", "discard"], pos=[3900, 120])
    w.connect("Outcome", "Draft or exception?")

    w.http("Step 10: Write the draft for the article owner", "POST", f"={{{{ {CFG}.drafts_url }}}}/drafts",
           body=f"={{{{ JSON.stringify({OUT}.draft) }}}}", write=True, pos=[4160, -120], notes="Never published from here.")
    did = "$('Step 10: Write the draft for the article owner').item.json.id"
    w.http("Step 10: Tell the article owner", "POST", msgs,
           body=f"={{{{ JSON.stringify({{ to: {owner}, subject: ({OUT}.draft.kind === 'suggested update' ? 'Suggested update: ' : 'Draft article: ') + {OUT}.draft.title, "
                f"text: 'Draft ' + {did} + ' from ticket ' + {OUT}.draft.ticket_id + ' waits for you to edit and approve or discard.' + "
                f"({OUT}.owners.length ? ' Held for the source owner: ' + {OUT}.owners.join(', ') + '.' : '') }}) }}}}",
           write=True, pos=[4420, -120])
    w.if_("Needs source?", f"={{{{ {OUT}.owners.length ? 'yes' : '' }}}}", op="notEmpty", pos=[4680, -120])
    w.http("Step 10: Ask the source owners to word the claims", "POST", msgs,
           body=f"={{{{ JSON.stringify({{ to: {OUT}.owners, subject: 'Needs source: draft ' + {did}, "
                f"text: 'Please word these claims from your source before the article is published: ' + "
                f"{OUT}.draft.claims.filter(c => c.needs_source).map(c => c.text).join(' | ') }}) }}}}",
           write=True, pos=[4940, -240])
    w.chain(f"Step 10: Write the draft for the article owner", "Step 10: Tell the article owner", "Needs source?")
    w.connect("Needs source?", "Step 10: Ask the source owners to word the claims", output=0)
    w.connect("Draft or exception?", "Step 10: Write the draft for the article owner", output=0)

    w.exception("Exception queue: set aside for the article owner", f"{TK}.id", "set aside",
                f"{OUT}.reason + ': ' + {OUT}.detail", owner, pos=[4160, 160])
    w.exception("Step 6: Exception queue: draft discarded", f"{TK}.id", "draft discarded",
                f"{OUT}.reason + ': ' + {OUT}.detail", owner, pos=[4160, 360])
    w.connect("Draft or exception?", "Exception queue: set aside for the article owner", output=1)
    w.connect("Draft or exception?", "Step 6: Exception queue: draft discarded", output=2)

    w.finish_key("Mark key done", KEY, "done", f"{OUT}.route === 'draft' ? 'draft ' + {did} : {OUT}.reason", pos=[5200, 0])
    w.decision_log("Decision log", f"{TK}.id",
                   f"{OUT}.route === 'draft' ? {OUT}.draft.kind + ' draft' : {OUT}.route === 'discard' ? 'draft discarded' : 'set aside: ' + {OUT}.reason",
                   f"JSON.stringify({OUT}.route === 'draft' ? Object.assign({{ draft_id: {did}, held_for: {OUT}.owners }}, {OUT}.draft.checks) : {{ check: {OUT}.reason, detail: {OUT}.detail }})",
                   pos=[5460, 0])
    for n in ["Step 10: Ask the source owners to word the claims", "Exception queue: set aside for the article owner",
              "Step 6: Exception queue: draft discarded"]:
        w.connect(n, "Mark key done")
    w.connect("Needs source?", "Mark key done", output=1)
    w.connect("Mark key done", "Decision log")

    w.finish_key("Mark key failed", KEY, "failed", "'write failed: ' + ($json.error && $json.error.message || 'unknown')", pos=[5200, 480])
    w.exception("Exception queue: write failed", f"{TK}.id", "write failed",
                "'Draft write or message failed; check the drafts area, never retried'", owner, pos=[5460, 480])
    for n in ["Step 10: Write the draft for the article owner", "Step 10: Tell the article owner",
              "Step 10: Ask the source owners to word the claims"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- decision path: steps 10 and 11 ---------------------------------------
    w.http("Read the draft", "GET", f"={{{{ {CFG}.drafts_url }}}}/drafts/{{{{ {DEV}.draft_id }}}}",
           write=False, error_output=False, pos=[1040, 900])
    w.reserve_key("Step 10: Reserve key", DKEY, pos=[1300, 900])
    w.if_("Step 10: New key?", "={{ $json.is_new }}", pos=[1560, 900])
    w.noop("Step 10: Duplicate: stop", pos=[1820, 1100], notes="This decision was handled before.")
    w.code("Step 10: Rule: approved by the owner, every claim worded?", DECIDE_JS, mode="runOnceForAllItems", pos=[1820, 900])
    w.connect("Draft decision?", "Read the draft", output=0)
    w.chain("Read the draft", "Step 10: Reserve key", "Step 10: New key?")
    w.connect("Step 10: New key?", "Step 10: Duplicate: stop", output=1)
    w.connect("Step 10: New key?", "Step 10: Rule: approved by the owner, every claim worded?", output=0)
    w.switch("Decision", "={{ $json.outcome }}", ["publish_new", "publish_update", "discard", "refuse"], pos=[2080, 900])
    w.connect("Step 10: Rule: approved by the owner, every claim worded?", "Decision")

    DEC = "$('Step 10: Rule: approved by the owner, every claim worded?').first().json"
    durl = f"={{{{ {CFG}.drafts_url }}}}/drafts/{{{{ {DEV}.draft_id }}}}"
    w.http("Step 11: Publish the article", "POST", f"={{{{ {CFG}.kb_url }}}}/articles",
           body=f"={{{{ JSON.stringify({DEC}.article) }}}}", write=True, pos=[2340, 700])
    art = "$('Step 11: Publish the article').item.json"
    w.http("Step 11: Register the article", "POST", f"={{{{ {CFG}.register_url }}}}/sources",
           body=f"={{{{ JSON.stringify({{ id: 'KB-' + {art}.id, title: {art}.title, owner: {owner}, delegate: null, audience: {CFG}.article_audience, "
                f"review_date: {DEC}.review_date, expiry_date: {DEC}.expiry_date, status: 'current', version: '1.0', "
                f"link: {CFG}.kb_url + '/articles/' + {art}.id, kb_article: {art}.id }}) }}}}",
           write=True, pos=[2600, 700], notes="With the article owner as owner and dates, so R13.2 watches it.")
    w.chain("Step 11: Publish the article", "Step 11: Register the article")
    w.http("Step 11: Publish the suggested update", "PATCH", f"={{{{ {CFG}.kb_url }}}}/articles/{{{{ {DR}.updates_article }}}}",
           body=f"={{{{ JSON.stringify({DEC}.article) }}}}", write=True, pos=[2340, 860],
           notes="The article is already registered; R13.2 keeps watching it.")
    w.http("Step 11: Set the draft published", "PATCH", durl,
           body="={{ JSON.stringify({ status: 'published' }) }}", write=True, pos=[2860, 780])
    w.connect("Step 11: Register the article", "Step 11: Set the draft published")
    w.connect("Step 11: Publish the suggested update", "Step 11: Set the draft published")
    w.http("Step 10: Set the draft discarded", "PATCH", durl,
           body="={{ JSON.stringify({ status: 'discarded' }) }}", write=True, pos=[2340, 1020])
    w.exception("Step 10: Exception queue: approval blocked", f"{DEV}.draft_id", "approval blocked",
                f"{DEC}.reason", owner, pos=[2340, 1180])
    for i, n in enumerate(["Step 11: Publish the article", "Step 11: Publish the suggested update",
                           "Step 10: Set the draft discarded", "Step 10: Exception queue: approval blocked"]):
        w.connect("Decision", n, output=i)

    w.finish_key("Step 10: Mark key done", DKEY, "done", f"{DEC}.outcome", pos=[3120, 900])
    w.pg("Step 10: Decision log",
         "INSERT INTO decision_log (recipe, item, decision, rules, approved_by) VALUES ($1, $2, $3, $4::jsonb, $5) RETURNING id",
         args=['"R13.3"', f"{DEV}.draft_id", f"{DEC}.outcome === 'refuse' ? 'approval blocked' : {DEC}.outcome.replace('_', ' ')",
               f"JSON.stringify({{ ticket: {DR}.ticket_id, reason: {DEC}.reason || null }})",
               f"{DEC}.outcome === 'refuse' ? null : {DEV}.by"],
         pos=[3380, 900], notes="Decision log: the draft, the decision and who approved it.")
    for n in ["Step 11: Set the draft published", "Step 10: Set the draft discarded", "Step 10: Exception queue: approval blocked"]:
        w.connect(n, "Step 10: Mark key done")
    w.connect("Step 10: Mark key done", "Step 10: Decision log")
    w.finish_key("Step 10: Mark key failed", DKEY, "failed", "'write failed: ' + ($json.error && $json.error.message || 'unknown')", pos=[3120, 1180])
    w.exception("Step 10: Exception queue: write failed", f"{DEV}.draft_id", "write failed",
                "'Publishing or registering failed part way; check the knowledge base and register, never retried'", owner, pos=[3380, 1180])
    for n in ["Step 11: Publish the article", "Step 11: Register the article", "Step 11: Publish the suggested update",
              "Step 11: Set the draft published", "Step 10: Set the draft discarded"]:
        w.connect(n, "Step 10: Mark key failed", output=1)
    w.connect("Step 10: Mark key failed", "Step 10: Exception queue: write failed")

    # ---- failure table: drafts pile up -----------------------------------------
    w.http("Read drafts awaiting approval", "GET", f"={{{{ {CFG}.drafts_url }}}}/drafts",
           query={"_wrap": "1", "status": "awaiting approval"}, write=False, error_output=False, pos=[780, 1400])
    w.code("Rule: drafts over 14 days old", WEEKLY_JS, mode="runOnceForAllItems", pos=[1040, 1400])
    w.if_("Any old drafts?", "={{ $json.count > 0 }}", pos=[1300, 1400])
    w.http("Tell the article owner to clear them", "POST", msgs,
           body=f"={{{{ JSON.stringify({{ to: {owner}, subject: $json.count + ' drafts waiting over ' + {CFG}.old_draft_days + ' days', text: 'Approve or discard: ' + $json.ids.join(', ') }}) }}}}",
           write=True, error_output=False, pos=[1560, 1300])
    w.connect("Weekly count?", "Read drafts awaiting approval", output=0)
    w.chain("Read drafts awaiting approval", "Rule: drafts over 14 days old", "Any old drafts?")
    w.connect("Any old drafts?", "Tell the article owner to clear them", output=0)
    return w
