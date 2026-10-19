"""R15.1 Draft campaign copy from approved product facts and check every claim.

Source: book Chapter 15, recipe R15.1, build steps 1 to 10, Table 15.1 and the failure table
(recipes/R15.1/build-spec.md); AI steps: recipes/R15.1/prompts/draft-copy.md (step 4) and
recipes/R15.1/prompts/list-claims.md (step 5, rerun by step 9).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

T1 = "Step 1: Brief approved"
T8 = "Step 8: Approver signs"
T9 = "Step 9: Ben approves"
TS = "Step 9: Before a send"
T10 = "Step 10: Each morning"
TRIGGERS = [T1, T8, T9, TS, T10]
LOOP = "Run once per channel version"
VER = "Version"
ATT = "Step 4: Attempt"
TAGGED = "Step 4: Rule: tagged draft?"
NEXT = "Step 7: Rule: what next?"
VR = "Version result"

CFG = "$('Config').first().json"
B1 = f"$('{T1}').first().json.body"
BRIEF = "$('Read the brief').first().json"
KEY = f"{B1}.brief_id + ':' + {BRIEF}.version"

COMMON_JS = r"""
// Claim types are those of Table 15.1: price, time, warranty, comparison, environmental, other.
const typesOf = c => (Array.isArray(c.types) ? c.types : String(c.types || c.type || 'other').split(/\s*[,;]\s*/)).filter(Boolean);
const ms = d => (d ? Date.parse(d) : 0) || 0;
const overlap = (s, e, spans) => spans.some(([a, b]) => s < b && e > a);
// Step 6's scan: digits, "$" and the scan words (Config), found anywhere in the text.
function scan(text, words) {
  const hits = [];
  for (const m of text.matchAll(/\d+|\$/g)) hits.push({ word: m[0], start: m.index, end: m.index + m[0].length });
  for (const w of words) {
    const re = new RegExp('\\b' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b', 'gi');
    for (const m of text.matchAll(re)) hits.push({ word: m[0], start: m.index, end: m.index + m[0].length });
  }
  return hits;
}
const LISTED_TYPES = ['price', 'time', 'warranty', 'comparison', 'quantity', 'environmental'];
// The listing call's reply: every entry a quote and one of the listed types, each quote found in the text.
function readListing(reply, text) {
  const p = parseAi(reply, ['claims']);
  if (!p.ok) return { ok: false, problem: 'listing: ' + p.problem };
  const list = p.value.claims;
  if (!Array.isArray(list) || list.some(c => !c || typeof c.quote !== 'string' || !c.quote || !LISTED_TYPES.includes(c.type)))
    return { ok: false, problem: 'listing: claims do not match the schema' };
  const found = [];
  for (const c of list) {
    let i = text.indexOf(c.quote);
    if (i < 0) return { ok: false, problem: `listing: "${c.quote}" is not in the copy` };
    while (i >= 0) { found.push({ quote: c.quote, type: c.type, start: i, end: i + c.quote.length }); i = text.indexOf(c.quote, i + 1); }
  }
  return { ok: true, list, found };
}
// Step 6 and step 7: what the listing and the scan find outside the approved spans.
function check(text, spans, found, cfg) {
  const problems = [], flagged = [];
  const untagged = found.filter(f => !overlap(f.start, f.end, spans));
  for (const u of untagged) {
    const who = cfg.approvers[u.type];
    if (who) flagged.push({ quote: u.quote, type: u.type, approver: who });
    else problems.push(`untagged ${u.type} claim "${u.quote}" has no named approver`);
  }
  const covered = spans.concat(untagged.map(u => [u.start, u.end]));
  for (const h of scan(text, cfg.scan_words)) {
    if (!overlap(h.start, h.end, covered)) problems.push(`untagged "${h.word}" in "${text.slice(Math.max(0, h.start - 25), h.end + 25).trim()}"`);
  }
  return { problems: [...new Set(problems)], flagged: flagged.filter((f, i) => flagged.findIndex(g => g.quote === f.quote) === i) };
}
"""

STEP2_JS = COMMON_JS + r"""
// Step 2: every claim exists, is unexpired, and was confirmed by its owner since its source or row
// last changed; a delivery or installation promise needs R15.2's "cleared". No AI call before this passes.
const brief = $('Read the brief').first().json;
const claims = Object.fromEntries(($('Read the claims list').first().json.items || []).map(c => [c.id, c]));
const prices = Object.fromEntries(($('Read the price list').first().json.items || []).map(p => [p.id, p]));
const today = new Date().toISOString().slice(0, 10);
const problems = [];
if (!(brief.claim_ids || []).length) problems.push('the brief names no claims');
if (!(brief.channels || []).length) problems.push('the brief names no channels');
for (const id of brief.claim_ids || []) {
  const c = claims[id];
  if (!c) { problems.push(`${id} is not on the claims list`); continue; }
  if (c.expiry && String(c.expiry).slice(0, 10) < today) problems.push(`${id} "${c.wording}" expired on ${String(c.expiry).slice(0, 10)}`);
  const rows = (c.price_ids || []).map(p => prices[p]);
  if (rows.some(r => !r)) problems.push(`${id}: a price row is missing from the price list`);
  const changed = Math.max(ms(c.source_changed), ms(c.row_changed), ...rows.filter(Boolean).map(r => ms(r.changed)));
  if (!c.last_confirmed || ms(c.last_confirmed) < changed) problems.push(`${id} not confirmed by its owner since its source or row last changed`);
  if (typesOf(c).includes('time') && brief.capacity !== 'cleared') problems.push(`${id} promises a delivery or installation time without R15.2's "cleared"`);
}
return [{ json: { ok: !problems.length, problems } }];
"""

BACK_JS = r"""
// Step 2 failed: the brief returns to Ben with the reasons.
const cfg = $('Config').first().json;
const brief = $('Read the brief').first().json;
const r = $('Step 2: Rule: claims current?').first().json;
return [{ json: {
  report: { brief_id: brief.id, brief_version: brief.version, step: 2, result: 'returned to Ben', rule_results: { problems: r.problems },
            prompt_version: cfg.prompt_version, at: new Date().toISOString() },
  message: { to: [cfg.final_approver], subject: `Brief ${brief.id} returned: claims not current`, text: r.problems.join('; ') } } }];
"""

VERSIONS_JS = COMMON_JS + r"""
// Step 3: only the brief's claims, their price rows and the style sheet; one item per channel version.
const brief = $('Read the brief').first().json;
const all = Object.fromEntries(($('Read the claims list').first().json.items || []).map(c => [c.id, c]));
const allPrices = Object.fromEntries(($('Read the price list').first().json.items || []).map(p => [p.id, p]));
const claims = brief.claim_ids.map(id => all[id]).map(c => ({ id: c.id, wording: c.wording, types: typesOf(c), price_ids: c.price_ids || [] }));
const priceIds = [...new Set(claims.flatMap(c => c.price_ids))];
const prices = priceIds.map(id => allPrices[id]).map(p => ({ id: p.id, product: p.product, price: String(p.price) }));
const style = $('Step 3: Read the style sheet').first().json.text || '';
return brief.channels.map(ch => ({ json: { version_id: `${brief.id}-${ch}`, brief_id: brief.id, brief_version: brief.version,
  channel: ch, claims, prices, style } }));
"""

ATTEMPT_JS = r"""
// Counts a redraft (step 7, once) and a bad AI output (retried twice, then Owen).
return [{ json: { redrafts: $json.redrafts || 0, bad_outputs: $json.bad_outputs || 0 } }];
"""

TAGGED_JS = AI_PARSE_JS + r"""
// Step 4's reply: the copy, its tags, and the untagged text step 5 reads.
const v = $('Version').first().json;
const p = parseAi($json, ['copy']);
if (!p.ok || typeof p.value.copy !== 'string' || !p.value.copy.trim())
  return [{ json: { result: 'bad_output', problem: 'draft: ' + (p.problem || 'copy is empty') } }];
const copy = p.value.copy;
const claims = Object.fromEntries(v.claims.map(c => [c.id, c]));
const prices = Object.fromEntries(v.prices.map(r => [r.id, r]));
let untagged = '', last = 0, segStart = 0;
const tags = [];
for (const m of copy.matchAll(/\s*\[(P:[^\]\s]+|C[\w.-]*)\]/g)) {
  untagged += copy.slice(last, m.index);
  last = m.index + m[0].length;
  const isPrice = m[1].startsWith('P:');
  const id = isPrice ? m[1].slice(2) : m[1];
  const row = isPrice ? prices[id] : claims[id];
  const expected = row ? (isPrice ? String(row.price) : String(row.wording)) : null;
  const end = untagged.length;
  const ok = !!expected && untagged.toLowerCase().endsWith(expected.toLowerCase());
  // The span a tag covers: its approved words, or back to the last tag or sentence break when they differ.
  const start = ok ? end - expected.length
    : Math.max(segStart, ...['.', '!', '?', '\n'].map(ch => untagged.lastIndexOf(ch, end - 1) + 1));
  tags.push({ tag: m[1], kind: isPrice ? 'price' : 'claim', id, known: !!row, ok, expected, found: untagged.slice(start, end).trim(), start, end });
  segStart = end;
}
untagged += copy.slice(last);
if (!tags.length) return [{ json: { result: 'bad_output', problem: 'draft has no tags to check' } }];
return [{ json: { result: 'drafted', copy, untagged, tags } }];
"""

STEP6_JS = AI_PARSE_JS + COMMON_JS + r"""
// Step 6: each tag keeps the approved wording or price; each listed claim matches a tag;
// the scan finds nothing untagged. Step 7's routing of an untagged claim follows.
const cfg = $('Config').first().json;
const d = $('Step 4: Rule: tagged draft?').first().json;
const l = readListing($json, d.untagged);
if (!l.ok) return [{ json: { result: 'bad_output', problem: l.problem } }];
const problems = d.tags.filter(t => !t.known).map(t => `[${t.tag}] is not a loaded claim or price row`)
  .concat(d.tags.filter(t => t.known && !t.ok).map(t => `[${t.tag}] reads "${t.found}", not "${t.expected}"`));
const c = check(d.untagged, d.tags.map(t => [t.start, t.end]), l.found, cfg);
problems.push(...c.problems);
return [{ json: { result: problems.length ? 'fail' : 'pass', problems, flagged: c.flagged, listing: l.list } }];
"""

NEXT_JS = r"""
// Step 7 and the failure table: a failure is redrafted once, then goes to Ben;
// an AI error or a reply that fails its schema is retried twice, then Owen is told.
const a = $('Step 4: Attempt').first().json;
const r = $json;
let route;
if (r.result === 'ai_error') route = 'owen';
else if (r.result === 'bad_output') route = a.bad_outputs < 2 ? 'retry' : 'owen';
else if (r.result === 'fail') route = a.redrafts < 1 ? 'redraft' : 'ben';
else route = 'signoff';
return [{ json: Object.assign({}, r, { route, redrafts: a.redrafts, bad_outputs: a.bad_outputs }) }];
"""

VR_JS = r"""
// What the version's run leaves: the version record, its claims report row, one message, and
// for an AI error the exception queue. Step 8: each named approver signs; a two-type claim goes to both.
const cfg = $('Config').first().json;
const v = $('Version').first().json;
const n = $json;
const now = new Date().toISOString();
const report = { version_id: v.version_id, brief_id: v.brief_id, brief_version: v.brief_version, channel: v.channel, step: '4 to 8',
  prompt_version: cfg.prompt_version, redrafts: n.redrafts, retries: n.bad_outputs, at: now };
if (n.route === 'owen') {
  report.result = 'AI error; Owen told';
  report.rule_results = { problem: n.problem };
  return [{ json: { version: null, report, decision: 'AI error; Owen told', rules: { problem: n.problem, retries: n.bad_outputs },
    exception: { detail: `${v.version_id}: ${n.problem}` },
    message: { to: [cfg.ai_owner], subject: `Campaign copy ${v.version_id}: AI step failed`, text: `${n.problem}. Retried; the version was not drafted.` } } }];
}
const d = $('Step 4: Rule: tagged draft?').first().json;
report.ai_outputs = { draft: d.copy, listing: n.listing };
report.rule_results = { tags: d.tags.map(t => ({ tag: t.tag, ok: t.ok })), problems: n.problems, flagged: n.flagged };
const version = { id: v.version_id, brief_id: v.brief_id, brief_version: v.brief_version, channel: v.channel,
  copy: d.copy, text: d.untagged, claims: v.claims, prices: v.prices, created: now, prompt_version: cfg.prompt_version };
if (n.route === 'ben') {
  Object.assign(version, { status: 'returned to Ben', problems: n.problems });
  report.result = 'returned to Ben after one redraft';
  return [{ json: { version, report, decision: 'returned to Ben after one redraft', rules: { problems: n.problems }, exception: null,
    message: { to: [cfg.final_approver], subject: `Campaign copy ${v.version_id} returned`, text: n.problems.join('; ') } } }];
}
const approvals = {};
const add = (who, what) => { const a = approvals[who] = approvals[who] || { claims: [], status: 'open' }; if (!a.claims.includes(what)) a.claims.push(what); };
const claims = Object.fromEntries(v.claims.map(c => [c.id, c]));
for (const t of d.tags) {
  const types = t.kind === 'price' ? ['price'] : claims[t.id].types;
  for (const ty of types) if (cfg.approvers[ty]) add(cfg.approvers[ty], `[${t.tag}]`);
}
for (const f of n.flagged) add(f.approver, `untagged ${f.type}: "${f.quote}"`);
const who = Object.keys(approvals);
Object.assign(version, { status: who.length ? 'waiting for sign-off' : 'waiting for Ben', approvals, flagged: n.flagged, signoff_requested: now });
report.result = version.status;
const text = who.length ? who.map(w => `${w}: ${approvals[w].claims.join(', ')}`).join('\n') + '\n\n' + d.untagged
                        : 'No claim needs a named approver; read the final copy and approve.\n\n' + d.untagged;
return [{ json: { version, report, decision: version.status, rules: { tags: d.tags.length, flagged: n.flagged.length, approvers: who.length }, exception: null,
  message: { to: who.length ? who : [cfg.final_approver], subject: `Campaign copy ${v.version_id}: ${who.length ? 'sign-off' : 'final read'} needed`, text } } }];
"""

SIGN_JS = r"""
// Step 8: a named approver signs or strikes; when every one has signed, Ben is asked (step 9).
const cfg = $('Config').first().json;
const b = $('Step 8: Approver signs').first().json.body;
const v = $json;
const a = JSON.parse(JSON.stringify(v.approvals || {}));
if (v.status !== 'waiting for sign-off' || !a[b.approver]) {
  return [{ json: { version_id: v.id, record: false, message: null,
    decision: 'sign-off ignored: ' + (!a[b.approver] ? 'not a named approver for this version' : 'version is ' + v.status) } }];
}
a[b.approver].status = b.decision === 'struck' ? 'struck' : 'signed';
a[b.approver].at = new Date().toISOString();
let status = 'waiting for sign-off', message = null;
if (b.decision === 'struck') {
  status = 'returned to Ben';
  message = { to: [cfg.final_approver], subject: `Campaign copy ${v.id} returned`, text: `${b.approver} struck: ${a[b.approver].claims.join(', ')}` };
} else if (Object.values(a).every(x => x.status === 'signed')) {
  status = 'waiting for Ben';
  message = { to: [cfg.final_approver], subject: `Campaign copy ${v.id}: every approver signed`, text: 'Read the final copy and approve.\n\n' + v.text };
}
return [{ json: { version_id: v.id, record: true, body: { approvals: a, status }, message, decision: `${b.approver} ${a[b.approver].status}; ${status}` } }];
"""

BEN_JS = r"""
// Step 9: Ben approves only a version every named approver has signed.
const v = $json;
const ok = v.status === 'waiting for Ben';
return [{ json: { version_id: v.id, ok, text: v.text, decision: ok ? 'approved by Ben' : `Ben's approval not recorded: version is ${v.status}` } }];
"""

SEND_JS = r"""
// Step 9: before a send, the text's fingerprint must match the one stored at Ben's approval.
const v = $('Read the version to send').first().json;
const fp = $json.fingerprint;
const now = new Date().toISOString();
if (v.status !== 'approved; ready to send') {
  return [{ json: { route: 'stop', version_id: v.id, body: { send_check: 'stopped: version not approved', send_checked_at: now },
    message: { to: [$('Config').first().json.final_approver], subject: `Send of ${v.id} stopped`, text: `The version is ${v.status}, not approved.` },
    decision: 'send stopped: not approved' } }];
}
if (fp === v.fingerprint) {
  return [{ json: { route: 'pass', version_id: v.id, body: { send_check: 'passed', send_checked_at: now }, decision: 'send check passed' } }];
}
return [{ json: { route: 'changed', version_id: v.id,
  body: { status: 'stopped: text changed', send_check: 'stopped: fingerprint changed', send_checked_at: now, changed_fingerprint: fp },
  message: { to: [$('Config').first().json.final_approver], subject: `Send of ${v.id} stopped: the text changed`,
             text: 'The text to send differs from the approved text; steps 5 and 6 run again on it.' },
  decision: 'send stopped: text changed' } }];
"""

RECHECK_JS = AI_PARSE_JS + COMMON_JS + r"""
// Step 9: steps 5 and 6 again on the changed text, with the version's approved wordings and prices as the spans.
const cfg = $('Config').first().json;
const v = $('Read the version to send').first().json;
const text = $('Step 9: Before a send').first().json.body.text || '';
const l = readListing($json, text);
if (!l.ok) return [{ json: { route: 'ai', problem: l.problem } }];
const spans = [];
for (const s of [...v.claims.map(c => c.wording), ...v.prices.map(p => p.price)]) {
  const low = text.toLowerCase(), q = String(s).toLowerCase();
  for (let i = low.indexOf(q); i >= 0; i = low.indexOf(q, i + 1)) spans.push([i, i + q.length]);
}
const c = check(text, spans, l.found, cfg);
const problems = c.problems.concat(c.flagged.map(f => `untagged ${f.type} claim "${f.quote}" for ${f.approver}`));
const now = new Date().toISOString();
const passed = !problems.length;
return [{ json: { route: 'done', version_id: v.id,
  body: passed ? { status: 'waiting for Ben', text, send_check: 'changed text passed steps 5 and 6', send_checked_at: now }
               : { send_check: 'changed text failed steps 5 and 6', send_problems: problems, send_checked_at: now },
  message: { to: [cfg.final_approver], subject: `Changed text for ${v.id}: ${passed ? 'passed; approve again' : 'unapproved claims'}`,
             text: passed ? text : problems.join('; ') },
  report: { version_id: v.id, step: 9, result: passed ? 'changed text passed' : 'changed text failed', ai_outputs: { listing: l.list },
            rule_results: { problems }, prompt_version: cfg.prompt_version, at: now },
  decision: passed ? 'changed text passed; back to Ben' : 'changed text failed; send stays stopped' } }];
"""

MORNING_JS = COMMON_JS + r"""
// Step 10: a changed source or price holds the claim's unsent versions.
// Failure table: a sign-off open two days goes to the person who names a stand-in.
const cfg = $('Config').first().json;
const versions = $('Step 10: Read the versions').first().json.items || [];
const claims = Object.fromEntries(($('Step 10: Read the claims list').first().json.items || []).map(c => [c.id, c]));
const prices = Object.fromEntries(($('Step 10: Read the price list').first().json.items || []).map(p => [p.id, p]));
const today = new Date().toISOString().slice(0, 10);
const out = [];
for (const v of versions) {
  if (v.status === 'sent' || v.status === 'returned to Ben' || String(v.status).startsWith('held')) continue;
  const created = ms(v.created);
  const why = [];
  for (const c of v.claims || []) {
    const cur = claims[c.id];
    if (!cur) why.push(`${c.id} is no longer on the claims list`);
    else if (Math.max(ms(cur.source_changed), ms(cur.row_changed)) > created || cur.wording !== c.wording) why.push(`${c.id}'s source or row changed`);
    else if (cur.expiry && String(cur.expiry).slice(0, 10) < today) why.push(`${c.id} expired`);
  }
  for (const p of v.prices || []) {
    const cur = prices[p.id];
    if (!cur || ms(cur.changed) > created || String(cur.price) !== String(p.price)) why.push(`price ${p.id} changed`);
  }
  if (why.length) {
    out.push({ json: { version_id: v.id, hold: true, body: { status: 'held: source changed', held_reasons: why },
      message: { to: [cfg.final_approver], subject: `Campaign copy ${v.id} held`, text: why.join('; ') }, decision: 'held: ' + why.join('; ') } });
  } else if (v.status === 'waiting for sign-off' && Date.now() - ms(v.signoff_requested || v.created) > cfg.signoff_wait_days * 86400000) {
    const open = Object.entries(v.approvals || {}).filter(([, a]) => a.status === 'open').map(([w]) => w);
    out.push({ json: { version_id: v.id, hold: false, body: null,
      message: { to: [cfg.stand_in_namer], subject: `Sign-off for ${v.id} open ${cfg.signoff_wait_days} days`, text: `Still open: ${open.join(', ')}. Name a stand-in.` },
      decision: 'sign-off open; stand-in requested' } });
  }
}
return out;
"""

WRITE_FAILED_JS = r"""
// A write failed outside the version loop: never retried; the exception queue names the item.
const t = ['Step 8: Approver signs', 'Step 9: Ben approves', 'Step 9: Before a send'].find(n => $(n).isExecuted);
const item = t ? $(t).first().json.body.version_id : 'morning run';
return [{ json: { item: String(item), problem: ($json.error && $json.error.message) || 'write failed' } }];
"""


def build() -> Workflow:
    w = Workflow("R15.1", "R15.1 Draft campaign copy from approved product facts and check every claim")
    w.webhook(T1, "r15-1-brief-approved", "Your brief list calls this when Ben marks a brief \"approved\". Body: {brief_id}.", pos=[0, 0])
    w.webhook(T8, "r15-1-sign", "Each named approver's sign-off. Body: {version_id, approver, decision: \"signed\" or \"struck\"}.", pos=[0, 900])
    w.webhook(T9, "r15-1-ben-approves", "Ben's final approval. Body: {version_id}.", pos=[0, 1200])
    w.webhook(TS, "r15-1-before-send", "Your sending tool calls this before each send, then reads the version's status. Body: {version_id, text}.", pos=[0, 1500])
    w.schedule(T10, 7, "Step 10: each morning.", pos=[0, 1900])
    w.config("Config", {
        "briefs_url": "https://<your brief list API>",
        "claims_url": "https://<your claims list API>",
        "prices_url": "https://<your CRM price list API>",
        "style_sheet_url": "https://<your style sheet API>",
        "drafts_url": "https://<your drafts and claims report API>",
        "messaging_url": "https://<your messaging API>",
        "approvers": {"price": "<your price approver>", "time": "<your delivery and installation approver>",
                      "warranty": "<your warranty approver>", "comparison": "<your comparison approver>",
                      "environmental": "<your environmental claim approver>"},
        "final_approver": "<your campaign owner>",
        "ai_owner": "<your workflow builder>",
        "stand_in_namer": "<your workflow owner>",
        "signoff_wait_days": 2,
        "scan_words": ["free", "warranty", "guarantee", "best", "today", "tonight", "tomorrow", "day", "days", "week", "weeks",
                       "weekend", "month", "hour", "hours", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
        "prompt_version": "<your prompt version>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 900])
    for t in TRIGGERS:
        w.connect(t, "Config")
    which = ("={{ " + " : ".join(f"$('{t}').isExecuted ? '{k}'" for t, k in
                                 [(T1, "brief"), (T8, "sign"), (T9, "approve"), (TS, "send")]) + " : 'morning' }}")
    w.switch("Which trigger?", which, ["brief", "sign", "approve", "send", "morning"], pos=[520, 900])
    w.connect("Config", "Which trigger?")

    # ---- steps 1 to 3 ---------------------------------------------------------
    w.http("Read the brief", "GET", f"={{{{ {CFG}.briefs_url }}}}/briefs/{{{{ {B1}.brief_id }}}}", write=False, error_output=False, pos=[780, 0])
    w.connect("Which trigger?", "Read the brief", output=0)
    w.reserve_key("Reserve key", KEY, pos=[1040, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1300, 0])
    w.noop("Duplicate: stop", pos=[1560, -160], notes="This brief version was drafted before.")
    w.chain("Read the brief", "Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)
    w.http("Read the claims list", "GET", f"={{{{ {CFG}.claims_url }}}}/claims", query={"_wrap": "1"}, write=False, error_output=False, pos=[1560, 0])
    w.http("Read the price list", "GET", f"={{{{ {CFG}.prices_url }}}}/prices", query={"_wrap": "1"}, write=False, error_output=False, pos=[1820, 0])
    w.code("Step 2: Rule: claims current?", STEP2_JS, mode="runOnceForAllItems", pos=[2080, 0])
    w.if_("Claims current?", "={{ $json.ok }}", pos=[2340, 0])
    w.connect("New key?", "Read the claims list", output=0)
    w.chain("Read the claims list", "Read the price list", "Step 2: Rule: claims current?", "Claims current?")

    w.code("Step 2: Back to Ben", BACK_JS, mode="runOnceForAllItems", pos=[2600, -240])
    w.http("Step 2: Claims report", "POST", f"={{{{ {CFG}.drafts_url }}}}/report",
           body="={{ JSON.stringify($('Step 2: Back to Ben').first().json.report) }}", write=True, pos=[2860, -240])
    w.http("Step 2: Tell Ben", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body="={{ JSON.stringify($('Step 2: Back to Ben').first().json.message) }}", write=True, pos=[3120, -240],
           notes="No AI call is made for a brief that fails step 2.")
    w.finish_key("Step 2: Mark key done", KEY, "done", "'returned to Ben'", pos=[3380, -240])
    w.decision_log("Step 2: Decision log", f"{B1}.brief_id", "'returned to Ben: claims not current'",
                   "JSON.stringify({ problems: $('Step 2: Rule: claims current?').first().json.problems })", pos=[3640, -240])
    w.connect("Claims current?", "Step 2: Back to Ben", output=1)
    w.connect("Step 2: Back to Ben", "Step 2: Claims report")
    w.connect("Step 2: Claims report", "Step 2: Tell Ben", output=0)
    w.connect("Step 2: Tell Ben", "Step 2: Mark key done", output=0)
    w.connect("Step 2: Mark key done", "Step 2: Decision log")

    w.http("Step 3: Read the style sheet", "GET", f"={{{{ {CFG}.style_sheet_url }}}}", write=False, error_output=False, pos=[2600, 0])
    w.code("Step 3: Load only those claims and prices", VERSIONS_JS, mode="runOnceForAllItems", pos=[2860, 0],
           notes="No customer data: the workflow never reads a customer list.")
    w.connect("Claims current?", "Step 3: Read the style sheet", output=0)
    w.connect("Step 3: Read the style sheet", "Step 3: Load only those claims and prices")
    w.node(LOOP, "n8n-nodes-base.splitInBatches", 3, {"options": {}}, pos=[3120, 0],
           notes="Step 1: runs once per channel version.")
    w.connect("Step 3: Load only those claims and prices", LOOP)
    w.code(VER, "return [{ json: $input.first().json }];", mode="runOnceForAllItems", pos=[3380, 120])
    w.connect(LOOP, VER, output=1)

    # ---- steps 4 to 7, inside the loop -----------------------------------------
    w.code(ATT, ATTEMPT_JS, mode="runOnceForAllItems", pos=[3640, 120])
    w.connect(VER, ATT)
    v = f"$('{VER}').first().json"
    vars4 = (f"{{ channel: {v}.channel, claims: {v}.claims.map(c => `${{c.id}} | ${{c.wording}} | ${{c.types.join(', ')}}`).join('\\n'), "
             f"price_rows: {v}.prices.map(p => `${{p.id}} | ${{p.product}} | ${{p.price}}`).join('\\n') || '(none)', style_sheet: {v}.style }}")
    b4, c4 = ai_step(w, "Step 4", ROOT / "recipes/R15.1/prompts/draft-copy.md", vars4, max_tokens=4096, tries=3,
                     pos_build=[3900, 120], pos_call=[4160, 120])
    w.connect(ATT, b4)
    w.code(TAGGED, TAGGED_JS, mode="runOnceForAllItems", pos=[4420, 120])
    w.connect(c4, TAGGED, output=0)
    w.if_("Drafted?", "={{ $json.result }}", op="equals", right="drafted", pos=[4680, 120])
    w.connect(TAGGED, "Drafted?")
    b5, c5 = ai_step(w, "Step 5", ROOT / "recipes/R15.1/prompts/list-claims.md",
                     f"{{ untagged_copy: $('{TAGGED}').first().json.untagged }}", max_tokens=4096, tries=3,
                     pos_build=[4940, 40], pos_call=[5200, 40])
    w.connect("Drafted?", b5, output=0)
    w.code("Step 6: Rules: tags, listing and scan", STEP6_JS, mode="runOnceForAllItems", pos=[5460, 40],
           notes="The rules decide, not the AI.")
    w.connect(c5, "Step 6: Rules: tags, listing and scan", output=0)
    ai_err = "return [{ json: { result: 'ai_error', problem: 'AI call failed after two retries: ' + (($json.error && $json.error.message) || 'no answer') } }];"
    w.code("Step 4: AI error", ai_err, mode="runOnceForAllItems", pos=[4420, 320])
    w.code("Step 5: AI error", ai_err, mode="runOnceForAllItems", pos=[5460, 240])
    w.connect(c4, "Step 4: AI error", output=1)
    w.connect(c5, "Step 5: AI error", output=1)

    w.code(NEXT, NEXT_JS, mode="runOnceForAllItems", pos=[5720, 120])
    for n in ["Step 6: Rules: tags, listing and scan", "Step 4: AI error", "Step 5: AI error"]:
        w.connect(n, NEXT)
    w.connect("Drafted?", NEXT, output=1)
    w.switch("Route", "={{ $json.route }}", ["retry", "redraft", "owen", "ben", "signoff"], pos=[5980, 120])
    w.connect(NEXT, "Route")
    w.code("Retry the AI steps", "return [{ json: { redrafts: $json.redrafts, bad_outputs: $json.bad_outputs + 1 } }];",
           mode="runOnceForAllItems", pos=[6240, -160])
    w.code("Step 7: Redraft once", "return [{ json: { redrafts: $json.redrafts + 1, bad_outputs: $json.bad_outputs } }];",
           mode="runOnceForAllItems", pos=[6240, -20], notes="Reruns step 4's prompt once with the same input.")
    w.connect("Route", "Retry the AI steps", output=0)
    w.connect("Route", "Step 7: Redraft once", output=1)
    w.connect("Retry the AI steps", ATT)
    w.connect("Step 7: Redraft once", ATT)
    w.code(VR, VR_JS, mode="runOnceForAllItems", pos=[6240, 220])
    for i in (2, 3, 4):
        w.connect("Route", VR, output=i)

    # ---- the version's record, report and message (steps 7 and 8) ---------------
    r = f"$('{VR}').first().json"
    w.if_("Store a version?", f"={{{{ {r}.version !== null }}}}", pos=[6500, 220])
    w.connect(VR, "Store a version?")
    w.http("Store the version", "PUT", f"={{{{ {CFG}.drafts_url }}}}/versions/{{{{ {r}.version.id }}}}",
           body=f"={{{{ JSON.stringify({r}.version) }}}}", write=True, pos=[6760, 140])
    w.http("Claims report", "POST", f"={{{{ {CFG}.drafts_url }}}}/report", body=f"={{{{ JSON.stringify({r}.report) }}}}",
           write=True, pos=[7020, 220], notes="AI outputs, rule results, prompt version and approvals: kept 13 months.")
    w.connect("Store a version?", "Store the version", output=0)
    w.connect("Store a version?", "Claims report", output=1)
    w.connect("Store the version", "Claims report", output=0)
    w.if_("AI error?", f"={{{{ {r}.exception !== null }}}}", pos=[7280, 220])
    w.connect("Claims report", "AI error?", output=0)
    w.exception("Exception queue: AI error", f"$('{VER}').first().json.version_id", "AI error", f"{r}.exception.detail",
                f"{CFG}.ai_owner", pos=[7540, 140])
    w.http("Tell the approvers, Ben or Owen", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({r}.message) }}}}", write=True, pos=[7800, 220])
    w.connect("AI error?", "Exception queue: AI error", output=0)
    w.connect("AI error?", "Tell the approvers, Ben or Owen", output=1)
    w.connect("Exception queue: AI error", "Tell the approvers, Ben or Owen")
    w.decision_log("Decision log: version", f"$('{VER}').first().json.version_id", f"{r}.decision", f"JSON.stringify({r}.rules)", pos=[8060, 220])
    w.connect("Tell the approvers, Ben or Owen", "Decision log: version", output=0)
    w.code("Version write failed", "return [{ json: { failed: true, problem: ($json.error && $json.error.message) || 'write failed' } }];",
           mode="runOnceForAllItems", pos=[7540, 420])
    for n in ["Store the version", "Claims report", "Tell the approvers, Ben or Owen"]:
        w.connect(n, "Version write failed", output=1)
    w.exception("Exception queue: version write failed", f"$('{VER}').first().json.version_id", "write failed",
                "'Draft, claims report or message write failed: ' + $json.problem + '; never retried'", f"{CFG}.ai_owner", pos=[7800, 420])
    w.connect("Version write failed", "Exception queue: version write failed")
    done = "return [{ json: { version_id: $('Version').first().json.version_id, failed: %s } }];"
    w.code("Version done", done % "false", mode="runOnceForAllItems", pos=[8320, 220])
    w.code("Version done: write failed", done % "true", mode="runOnceForAllItems", pos=[8060, 420])
    w.connect("Decision log: version", "Version done")
    w.connect("Exception queue: version write failed", "Version done: write failed")
    w.connect("Version done", LOOP)
    w.connect("Version done: write failed", LOOP)

    w.code("All versions", "return [{ json: { failed: $input.all().some(i => i.json.failed) } }];", mode="runOnceForAllItems", pos=[3380, -120])
    w.connect(LOOP, "All versions", output=0)
    w.if_("Any write failed?", "={{ $json.failed }}", pos=[3640, -120])
    w.connect("All versions", "Any write failed?")
    w.finish_key("Mark key done", KEY, "done", "'drafted'", pos=[3900, -200])
    w.connect("Any write failed?", "Mark key done", output=1)

    w.finish_key("Mark key failed", KEY, "failed", "'write failed'", pos=[3900, -360])
    w.connect("Any write failed?", "Mark key failed", output=0)
    w.exception("Exception queue: step 2 write failed", f"{B1}.brief_id", "write failed",
                "'Claims report or message to Ben failed; never retried'", f"{CFG}.ai_owner", pos=[3640, -440])
    w.connect("Step 2: Claims report", "Exception queue: step 2 write failed", output=1)
    w.connect("Step 2: Tell Ben", "Exception queue: step 2 write failed", output=1)
    w.connect("Exception queue: step 2 write failed", "Mark key failed")

    # ---- step 8: each named approver signs ---------------------------------------
    w.code("Write failed", WRITE_FAILED_JS, mode="runOnceForAllItems", pos=[3120, 2200])
    w.exception("Exception queue: write failed", "$json.item", "write failed", "$json.problem + '; never retried'", f"{CFG}.ai_owner", pos=[3380, 2200])
    w.connect("Write failed", "Exception queue: write failed")

    def tail(prefix: str, src: str, x: int, y: int, patch_url: str, body_expr: str, msg_expr: str | None, decision_expr: str,
             item_expr: str, record_if: str | None = None) -> None:
        """Optional PATCH of the version, an optional message, then the decision log."""
        log = f"{prefix}: Decision log"
        w.decision_log(log, item_expr, decision_expr, "'{}'", pos=[x + 1040, y])
        nxt = log
        if msg_expr:
            w.if_(f"{prefix}: Tell someone?", f"={{{{ {msg_expr} !== null }}}}", pos=[x + 520, y])
            w.http(f"{prefix}: Message", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
                   body=f"={{{{ JSON.stringify({msg_expr}) }}}}", write=True, pos=[x + 780, y - 80])
            w.connect(f"{prefix}: Tell someone?", f"{prefix}: Message", output=0)
            w.connect(f"{prefix}: Tell someone?", log, output=1)
            w.connect(f"{prefix}: Message", log, output=0)
            w.connect(f"{prefix}: Message", "Write failed", output=1)
            nxt = f"{prefix}: Tell someone?"
        w.http(f"{prefix}: Update the version", "PATCH", patch_url, body=body_expr, write=True, pos=[x + 260, y])
        w.connect(f"{prefix}: Update the version", nxt, output=0)
        w.connect(f"{prefix}: Update the version", "Write failed", output=1)
        if record_if:
            w.if_(f"{prefix}: Record it?", record_if, pos=[x, y + 120])
            w.connect(src, f"{prefix}: Record it?")
            w.connect(f"{prefix}: Record it?", f"{prefix}: Update the version", output=0)
            w.connect(f"{prefix}: Record it?", log, output=1)
        else:
            w.connect(src, f"{prefix}: Update the version")

    w.http("Read the version to sign", "GET", f"={{{{ {CFG}.drafts_url }}}}/versions/{{{{ $('{T8}').first().json.body.version_id }}}}",
           write=False, error_output=False, pos=[780, 900])
    w.code("Step 8: Rule: record the sign-off", SIGN_JS, mode="runOnceForAllItems", pos=[1040, 900])
    w.connect("Which trigger?", "Read the version to sign", output=1)
    w.connect("Read the version to sign", "Step 8: Rule: record the sign-off")
    s8 = "$('Step 8: Rule: record the sign-off').first().json"
    tail("Step 8", "Step 8: Rule: record the sign-off", 1300, 900,
         f"={{{{ {CFG}.drafts_url }}}}/versions/{{{{ {s8}.version_id }}}}", f"={{{{ JSON.stringify({s8}.body) }}}}",
         f"{s8}.message", f"{s8}.decision", f"{s8}.version_id", record_if=f"={{{{ {s8}.record }}}}")

    # ---- step 9: Ben approves; the fingerprint ------------------------------------
    w.http("Read the version Ben approves", "GET", f"={{{{ {CFG}.drafts_url }}}}/versions/{{{{ $('{T9}').first().json.body.version_id }}}}",
           write=False, error_output=False, pos=[780, 1200])
    w.code("Step 9: Rule: every approver signed?", BEN_JS, mode="runOnceForAllItems", pos=[1040, 1200])
    w.connect("Which trigger?", "Read the version Ben approves", output=2)
    w.connect("Read the version Ben approves", "Step 9: Rule: every approver signed?")
    s9 = "$('Step 9: Rule: every approver signed?').first().json"
    w.if_("Ben may approve?", f"={{{{ {s9}.ok }}}}", pos=[1300, 1200])
    w.connect("Step 9: Rule: every approver signed?", "Ben may approve?")
    w.node("Step 9: Fingerprint the approved text", "n8n-nodes-base.crypto", 1,
           {"action": "hash", "type": "SHA256", "value": f"={{{{ {s9}.text }}}}", "dataPropertyName": "fingerprint", "encoding": "hex"},
           pos=[1560, 1120], notes="A SHA-256 hash: it changes if any character does.")
    w.connect("Ben may approve?", "Step 9: Fingerprint the approved text", output=0)
    w.http("Step 9: Store the approved text", "PATCH", f"={{{{ {CFG}.drafts_url }}}}/versions/{{{{ {s9}.version_id }}}}",
           body="={{ JSON.stringify({ status: 'approved; ready to send', fingerprint: $json.fingerprint, approved_at: new Date().toISOString() }) }}",
           write=True, pos=[1820, 1120])
    w.http("Step 9: Claims report", "POST", f"={{{{ {CFG}.drafts_url }}}}/report",
           body=f"={{{{ JSON.stringify({{ version_id: {s9}.version_id, step: 9, result: 'approved by Ben', fingerprint: $('Step 9: Fingerprint the approved text').first().json.fingerprint, approvals: $('Read the version Ben approves').first().json.approvals, at: new Date().toISOString() }}) }}}}",
           write=True, pos=[2080, 1120])
    w.decision_log("Step 9: Decision log", f"{s9}.version_id", f"{s9}.decision", "'{}'", pos=[2340, 1200])
    w.chain("Step 9: Fingerprint the approved text", "Step 9: Store the approved text")
    w.connect("Step 9: Store the approved text", "Step 9: Claims report", output=0)
    w.connect("Step 9: Claims report", "Step 9: Decision log", output=0)
    w.connect("Ben may approve?", "Step 9: Decision log", output=1)
    w.connect("Step 9: Store the approved text", "Write failed", output=1)
    w.connect("Step 9: Claims report", "Write failed", output=1)

    # ---- step 9: before a send ------------------------------------------------------
    w.http("Read the version to send", "GET", f"={{{{ {CFG}.drafts_url }}}}/versions/{{{{ $('{TS}').first().json.body.version_id }}}}",
           write=False, error_output=False, pos=[780, 1500])
    w.connect("Which trigger?", "Read the version to send", output=3)
    w.node("Step 9: Fingerprint the text to send", "n8n-nodes-base.crypto", 1,
           {"action": "hash", "type": "SHA256", "value": f"={{{{ $('{TS}').first().json.body.text }}}}", "dataPropertyName": "fingerprint", "encoding": "hex"},
           pos=[1040, 1500])
    w.code("Step 9: Rule: same fingerprint?", SEND_JS, mode="runOnceForAllItems", pos=[1300, 1500])
    w.chain("Read the version to send", "Step 9: Fingerprint the text to send", "Step 9: Rule: same fingerprint?")
    sf = "$('Step 9: Rule: same fingerprint?').first().json"
    tail("Send check", "Step 9: Rule: same fingerprint?", 1560, 1500,
         f"={{{{ {CFG}.drafts_url }}}}/versions/{{{{ {sf}.version_id }}}}", f"={{{{ JSON.stringify({sf}.body) }}}}",
         f"({sf}.message || null)", f"{sf}.decision", f"{sf}.version_id")
    w.if_("Text changed?", f"={{{{ {sf}.route }}}}", op="equals", right="changed", pos=[2860, 1500])
    w.connect("Send check: Decision log", "Text changed?")
    b9, c9 = ai_step(w, "Step 9: Rerun step 5", ROOT / "recipes/R15.1/prompts/list-claims.md",
                     f"{{ untagged_copy: $('{TS}').first().json.body.text }}", max_tokens=4096, tries=3,
                     pos_build=[3120, 1440], pos_call=[3380, 1440])
    w.connect("Text changed?", b9, output=0)
    w.code("Step 9: Rerun step 6", RECHECK_JS, mode="runOnceForAllItems", pos=[3640, 1440])
    w.connect(c9, "Step 9: Rerun step 6", output=0)
    w.if_("Rerun checked?", "={{ $json.route }}", op="equals", right="done", pos=[3900, 1440])
    w.connect("Step 9: Rerun step 6", "Rerun checked?")
    rc = "$('Step 9: Rerun step 6').first().json"
    w.http("Rerun: Claims report", "POST", f"={{{{ {CFG}.drafts_url }}}}/report", body=f"={{{{ JSON.stringify({rc}.report) }}}}",
           write=True, pos=[4160, 1360])
    w.connect("Rerun checked?", "Rerun: Claims report", output=0)
    w.connect("Rerun: Claims report", "Write failed", output=1)
    tail("Rerun", "Rerun: Claims report", 4420, 1360,
         f"={{{{ {CFG}.drafts_url }}}}/versions/{{{{ {rc}.version_id }}}}", f"={{{{ JSON.stringify({rc}.body) }}}}",
         f"{rc}.message", f"{rc}.decision", f"{rc}.version_id")
    w.code("Step 9: Rerun AI error", "return [{ json: { problem: 'AI call failed after two retries: ' + (($json.error && $json.error.message) || 'no answer') } }];",
           mode="runOnceForAllItems", pos=[3640, 1680])
    w.code("Step 9: Rerun bad output", f"return [{{ json: {{ problem: {rc}.problem }} }}];", mode="runOnceForAllItems", pos=[4160, 1600])
    w.connect(c9, "Step 9: Rerun AI error", output=1)
    w.connect("Rerun checked?", "Step 9: Rerun bad output", output=1)
    w.code("Step 9: Rerun failed", "return [{ json: $json }];", mode="runOnceForAllItems", pos=[4420, 1680])
    w.connect("Step 9: Rerun AI error", "Step 9: Rerun failed")
    w.connect("Step 9: Rerun bad output", "Step 9: Rerun failed")
    rf = "$('Step 9: Rerun failed').first().json"
    w.exception("Exception queue: rerun AI error", f"$('{TS}').first().json.body.version_id", "AI error",
                f"'Send check rerun: ' + {rf}.problem + '; the send stays stopped'", f"{CFG}.ai_owner", pos=[4680, 1680])
    w.http("Rerun: Tell Owen", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: [{CFG}.ai_owner], subject: 'Send check for ' + $('{TS}').first().json.body.version_id + ': AI step failed', text: {rf}.problem + '. The send stays stopped.' }}) }}}}",
           write=True, pos=[4940, 1680])
    w.chain("Step 9: Rerun failed", "Exception queue: rerun AI error", "Rerun: Tell Owen")
    w.connect("Rerun: Tell Owen", "Write failed", output=1)

    # ---- step 10: each morning ----------------------------------------------------------
    w.http("Step 10: Read the versions", "GET", f"={{{{ {CFG}.drafts_url }}}}/versions", query={"_wrap": "1"},
           write=False, error_output=False, pos=[780, 1900])
    w.http("Step 10: Read the claims list", "GET", f"={{{{ {CFG}.claims_url }}}}/claims", query={"_wrap": "1"},
           write=False, error_output=False, pos=[1040, 1900])
    w.http("Step 10: Read the price list", "GET", f"={{{{ {CFG}.prices_url }}}}/prices", query={"_wrap": "1"},
           write=False, error_output=False, pos=[1300, 1900])
    w.code("Step 10: Rule: changed sources and open sign-offs", MORNING_JS, mode="runOnceForAllItems", pos=[1560, 1900])
    w.connect("Which trigger?", "Step 10: Read the versions", output=4)
    w.chain("Step 10: Read the versions", "Step 10: Read the claims list", "Step 10: Read the price list",
            "Step 10: Rule: changed sources and open sign-offs")
    m = "$('Step 10: Rule: changed sources and open sign-offs').item.json"
    w.if_("Step 10: Hold it?", f"={{{{ {m}.hold }}}}", pos=[1820, 1900])
    w.connect("Step 10: Rule: changed sources and open sign-offs", "Step 10: Hold it?")
    w.http("Step 10: Hold the unsent version", "PATCH", f"={{{{ {CFG}.drafts_url }}}}/versions/{{{{ {m}.version_id }}}}",
           body=f"={{{{ JSON.stringify({m}.body) }}}}", write=True, pos=[2080, 1820])
    w.http("Step 10: Tell Ben or Helen", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({m}.message) }}}}", write=True, pos=[2340, 1900])
    w.decision_log("Step 10: Decision log", f"{m}.version_id", f"{m}.decision", "'{}'", pos=[2600, 1900])
    w.connect("Step 10: Hold it?", "Step 10: Hold the unsent version", output=0)
    w.connect("Step 10: Hold it?", "Step 10: Tell Ben or Helen", output=1)
    w.connect("Step 10: Hold the unsent version", "Step 10: Tell Ben or Helen", output=0)
    w.connect("Step 10: Tell Ben or Helen", "Step 10: Decision log", output=0)
    w.connect("Step 10: Hold the unsent version", "Write failed", output=1)
    w.connect("Step 10: Tell Ben or Helen", "Write failed", output=1)
    return w
