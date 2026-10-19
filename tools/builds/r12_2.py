"""R12.2 Draft the weekly briefing narrative with a link behind every figure.

Source: book Chapter 12, recipe R12.2, build steps 1 to 14 (recipes/R12.2/build-spec.md);
AI step: recipes/R12.2/prompts/draft-narrative.md.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, V, Workflow, ai_step  # noqa: E402

FRI = "Step 1: Friday 14:00"
WRITTEN = "Step 1: Table version written"
VERIFY = "Step 12: Sentence approved or deleted"
FOUR = "Step 13: Friday 16:00"
LATE = "Step 13: Friday 16:45"

EVENT_JS = f"""
// Which trigger started this run.
const ran = n => {{ try {{ return $(n).isExecuted; }} catch (e) {{ return false; }} }};
const event = ran({FRI!r}) ? 'friday' : ran({WRITTEN!r}) ? 'written' : ran({VERIFY!r}) ? 'verify' : ran({FOUR!r}) ? 'four' : 'late';
const body = event === 'written' ? $({WRITTEN!r}).first().json.body : event === 'verify' ? $({VERIFY!r}).first().json.body : {{}};
return [{{ json: {{ event, body }} }}];
"""

VERSION_JS = r"""
// Step 1: the table version to draft: at Friday 14:00 the current one; on a write, the version written.
const ev = $('Which event?').first().json;
const versions = ($('Read versions').first().json.items || []).filter(v => v.status === 'written');
const seq = v => Number(String(v.id).replace(/\D/g, '')) || 0;
const v = ev.event === 'friday' ? versions.sort((a, b) => seq(a) - seq(b)).pop() : versions.find(x => x.id === ev.body.version);
return v ? [{ json: { version: v.id, week: v.week } }] : [];
"""

WHEN_JS = r"""
// Steps 1 and 14: draft now, or too late.
// No draft yet this week: Friday 14:00 drafts; a table first written later drafts only up to the first-draft limit.
// A draft exists: a newer version is drafted again until Friday 16:00 closes the week, then gets no narrative.
const cfg = $('Config').first().json;
const ev = $('Which event?').first().json.event;
const v = $('Step 1: Which version?').first().json;
const d = ($('Read the week\'s draft').first().json.items || [])[0] || null;
const seq = id => Number(String(id).replace(/\D/g, '')) || 0;
const at = t => { const [h, m] = String(t).split(':').map(Number); return $now.set({ hour: h, minute: m || 0, second: 0, millisecond: 0 }); };
let action;
if (!d) {
  const inWindow = $now.weekday === cfg.draft_weekday && $now >= at(cfg.draft_from) && $now <= at(cfg.first_draft_until);
  action = ev === 'friday' || inWindow ? 'draft' : 'wait';
} else if (seq(v.version) < seq(d.version)) {
  action = 'wait';
} else {
  action = d.closed && d.version !== v.version ? 'late' : 'draft';
}
if (action === 'wait') return [];
return [{ json: { action, version: v.version, week: v.week, key: `${v.week}:${v.version}`, previous: d } }];
"""

HOLD_JS = r"""
// Step 3: hold back commentary naming anyone on the customer or staff lists, for the verifier to read.
const names = [...($('Read the customer list').first().json.items || []), ...($('Read the staff list').first().json.items || [])]
  .map(p => String(p.name || '').trim()).filter(n => n.length > 1);
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const named = t => names.find(n => new RegExp(`(^|[^\\p{L}])${esc(n)}($|[^\\p{L}])`, 'iu').test(t));
const all = $('Read the commentary').first().json.items || [];
const kept = [], held = [];
for (const c of all) {
  const who = named(String(c.text || ''));
  (who ? held : kept).push(who ? Object.assign({}, c, { names: who }) : c);
}
return [{ json: { kept, held } }];
"""

INPUT_JS = r"""
// Step 4: the input, from the table and the remaining commentary only: no source export, no links.
const cfg = $('Config').first().json;
const when = $('Steps 1 and 14: Draft now?').first().json;
const rows = $('Read the table').first().json.items || [];
const kept = $('Step 3: Rule: hold back commentary naming a listed person').first().json.kept;
const crossings = ($('Read the alert log').first().json.items || []).filter(a => a.outcome === 'past the line').map(a => a.measure);
const OK = ['fresh', 'manual'];
const show = x => (x === null || x === undefined ? 'blank' : String(x));
// The must-mention list: every R12.3 crossing, every change above its stated size, and (Table 12.2)
// every measure neither fresh nor manual, which may appear only as "missing this week".
const must = rows.filter(r => {
  const size = Number((cfg.must_mention_change_above || {})[r.measure]);
  return crossings.includes(r.measure)
    || (OK.includes(r.status) && typeof r.change === 'number' && !Number.isNaN(size) && Math.abs(r.change) > size)
    || ['stale', 'format changed', 'does not reconcile'].includes(r.status);
}).map(r => r.measure);
return [{ json: {
  week: when.week, version: when.version, rows, must, commentary: kept,
  table_rows: rows.map(r => `${r.measure} | ${show(r.value)} | ${show(r.change)} | ${r.status}`).join('\n'),
  must_mention_list: must.join('\n'),
  banned_cause_list: cfg.banned_causes.join(', '),
  commentary_text: kept.map(c => `${c.measure} | ${c.owner} | ${String(c.text).replace(/\s+/g, ' ')}`).join('\n'),
} }];
"""

CHECK_JS = AI_PARSE_JS + r"""
// Steps 6 to 9: the rules decide whether the draft is used; the AI never does.
const cfg = $('Config').first().json;
const inp = $('Step 4: Build the input').first().json;
const rows = inp.rows;
const OK = ['fresh', 'manual'];
const fail = (reason, problems) => [{ json: { pass: false, reason, problems } }];

// Step 6: schema: sentences, each with its text and numbers, each number tagged with measure and field.
const p = parseAi($('Step 5: AI call').first().json, ['sentences']);
if (!p.ok) return fail('schema', [p.problem]);
const out = p.value;
const exact = (o, keys) => o && typeof o === 'object' && !Array.isArray(o) && Object.keys(o).sort().join() === [...keys].sort().join();
if (!exact(out, ['sentences']) || !Array.isArray(out.sentences)) return fail('schema', ['reply has fields other than sentences']);
const measures = rows.map(r => r.measure);
for (const s of out.sentences) {
  if (!exact(s, ['text', 'numbers']) || typeof s.text !== 'string' || !Array.isArray(s.numbers)) return fail('schema', ['a sentence is not {text, numbers}']);
  for (const n of s.numbers) {
    if (!exact(n, ['number', 'measure', 'field']) || typeof n.number !== 'string' || !measures.includes(n.measure) || !['value', 'change'].includes(n.field)) {
      return fail('schema', [`a number is not tagged with a table measure and value or change: ${JSON.stringify(n)}`]);
    }
  }
}

// Step 7: numbers, with word-numbers converted, in the order they appear.
const UNITS = { zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12,
  thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19,
  twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90 };
const SCALES = { hundred: 100, thousand: 1000, million: 1000000 };
const COMPUTED = /\b(half|halves|halved|third|thirds|quarter|quarters|double|doubled|twice|triple|tripled|percent|per cent)\b|%/i;
function numbersIn(text) {
  const tokens = String(text).match(/[+-]?\d[\d,]*(?:\.\d+)?|[A-Za-z]+(?:-[A-Za-z]+)*/g) || [];
  const found = [];
  let cur = null;
  const flush = () => { if (cur) { found.push(cur.total + cur.part); cur = null; } };
  for (const tok of tokens) {
    if (/^[+-]?\d/.test(tok)) { flush(); found.push(Number(tok.replace(/,/g, ''))); continue; }
    const words = tok.toLowerCase().split('-');
    if (words.every(w => w in UNITS || w in SCALES)) {
      cur = cur || { total: 0, part: 0 };
      for (const w of words) {
        if (w in UNITS) cur.part += UNITS[w];
        else if (w === 'hundred') cur.part = (cur.part || 1) * 100;
        else { cur.total += (cur.part || 1) * SCALES[w]; cur.part = 0; }
      }
    } else if (!(cur && tok.toLowerCase() === 'and')) flush();
  }
  flush();
  return found;
}
const row = m => rows.find(r => r.measure === m);
// A sentence is about every measure it tags or names.
const about = s => [...new Set([...s.numbers.map(n => n.measure), ...measures.filter(m => s.text.toLowerCase().includes(m.toLowerCase()))])];
const RISE = /\b(rose|rise|rises|risen|rising)\b/i, FALL = /\b(fell|fall|falls|fallen|falling)\b/i;
const problems = [];
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
out.sentences.forEach((s, i) => {
  const where = `sentence ${i + 1}`;
  if (COMPUTED.test(s.text)) problems.push(`${where}: a computed figure ("${s.text.match(COMPUTED)[0]}")`);
  const seen = numbersIn(s.text);
  if (seen.length !== s.numbers.length) problems.push(`${where}: ${seen.length} numbers in the text, ${s.numbers.length} tagged`);
  s.numbers.forEach((n, k) => {
    const want = numbersIn(n.number)[0];
    const r = row(n.measure);
    const field = r[n.field];
    if (want === undefined || seen[k] !== want) problems.push(`${where}: "${n.number}" is not the number in the text`);
    else if (typeof field !== 'number') problems.push(`${where}: ${n.measure} has no ${n.field} in the table`);
    else if (n.field === 'value' ? want !== field : (Math.abs(want) !== Math.abs(field) || (/^[+-]/.test(n.number.trim()) && Math.sign(want) !== Math.sign(field)))) {
      problems.push(`${where}: ${n.number} is not the ${n.field} of ${n.measure} (${field})`);
    }
  });
  for (const m of about(s)) {
    const r = row(m);
    if (RISE.test(s.text) && !(typeof r.change === 'number' && r.change > 0)) problems.push(`${where}: direction check: "rose" but the change for ${m} is ${r.change}`);
    if (FALL.test(s.text) && !(typeof r.change === 'number' && r.change < 0)) problems.push(`${where}: direction check: "fell" but the change for ${m} is ${r.change}`);
    // Step 8: a banned-cause word passes only with the owner named and their commentary quoted word for word.
    const banned = cfg.banned_causes.find(b => new RegExp(`\\b${esc(b)}\\b`, 'i').test(s.text));
    if (banned) {
      const c = inp.commentary.find(x => x.measure === m);
      const quotes = (s.text.match(/["“][^"”]+["”]/g) || []).map(q => q.slice(1, -1).trim()).filter(Boolean);
      const owner = c && String(c.owner || '');
      const named = owner && [owner, owner.split(' ')[0]].some(o => new RegExp(`\\b${esc(o)}\\b`, 'i').test(s.text));
      if (!c || !named || !quotes.some(q => String(c.text).includes(q))) problems.push(`${where}: cause rule: "${banned}" without the owner's commentary quoted word for word`);
    }
    // Step 9: a measure neither fresh nor manual appears only as "missing this week".
    if (!OK.includes(r.status) && (s.numbers.length || seen.length || !/missing this week/i.test(s.text))) {
      problems.push(`${where}: ${m} is ${r.status} and may appear only as "missing this week"`);
    }
  }
});
for (const m of inp.must) if (!out.sentences.some(s => about(s).includes(m))) problems.push(`no sentence for must-mention measure ${m}`);
if (problems.length) {
  const kinds = [['direction check', x => x.includes('direction check')], ['cause rule', x => x.includes('cause rule')],
    ['missing-measure rule', x => x.includes('missing this week') || x.includes('must-mention')],
    ['number rule', x => !/direction check|cause rule|missing this week|must-mention/.test(x)]];
  return fail(kinds.filter(([, f]) => problems.some(f)).map(([k]) => k).join(', '), problems);
}
return [{ json: { pass: true, sentences: out.sentences.map(s => Object.assign({}, s, { measures: about(s) })) } }];
"""

LINKS_JS = r"""
// Step 10: the workflow, not the AI, puts the source link after every figure.
const rows = $('Step 4: Build the input').first().json.rows;
const sentences = $json.sentences.map((s, i) => {
  let text = s.text, from = 0;
  for (const n of s.numbers) {
    const link = (rows.find(r => r.measure === n.measure) || {}).source_link;
    const at = text.indexOf(n.number, from);
    if (at < 0 || !link) continue;
    const insert = ` [source](${link})`;
    text = text.slice(0, at + n.number.length) + insert + text.slice(at + n.number.length);
    from = at + n.number.length + insert.length;
  }
  return { n: i + 1, text: s.text, linked: text, measures: s.measures, decision: null, by: null };
});
return { json: { pass: true, sentences } };
"""

DRAFT_JS = r"""
// The week's draft record: the single place the verifier works, and what steps 13 and 14 read.
const cfg = $('Config').first().json;
const w = $('Steps 1 and 14: Draft now?').first().json;
const rows = $('Read the table').first().json.items || [];
const kept = $('Step 3: Rule: hold back commentary naming a listed person').first().json.kept;
const r = $json;
const prev = w.previous;
const superseded = prev && prev.version !== w.version ? [...(prev.superseded || []), prev.version] : (prev && prev.superseded) || [];
const draft = {
  id: w.week, week: w.week, version: w.version, superseded, closed: !!(prev && prev.closed),
  stage: r.pass ? 'to verify' : 'no narrative', reason: r.pass ? null : r.reason, problems: r.problems || [],
  sentences: r.pass ? r.sentences : [], table: rows.map(x => ({ measure: x.measure, value: x.value, change: x.change, status: x.status, source_link: x.source_link })),
  commentary: kept, held_back: $('Step 3: Rule: hold back commentary naming a listed person').first().json.held.length,
  model: cfg.ai_model, prompt_version: cfg.prompt_version, banned_cause_list_version: cfg.banned_cause_list_version,
};
return { json: { draft, preread: { id: w.week, week: w.week, version: w.version, table: draft.table, commentary: draft.commentary,
  narrative: null, note: 'no narrative this week', reason: draft.reason } } };
"""

VERIFY_JS = r"""
// Step 12: the verifier approves or deletes each sentence; the backup verifier takes the verifier's own
// measures, and every sentence once Friday 16:00 has passed.
const cfg = $('Config').first().json;
const b = $('Which event?').first().json.body;
const d = ($('Read the draft').first().json.items || [])[0];
if (!d || !['to verify', 'backup'].includes(d.stage) || !['approve', 'delete'].includes(b.action)) return [];
const s = d.sentences.find(x => x.n === Number(b.sentence));
if (!s || s.decision) return [];
const own = s.measures.some(m => cfg.verifier_own_measures.includes(m));
const allowed = d.stage === 'backup' ? b.by === cfg.backup_verifier : (own ? b.by === cfg.backup_verifier : b.by === cfg.verifier);
if (!allowed) return [];
const sentences = d.sentences.map(x => x.n === s.n ? Object.assign({}, x, { decision: b.action === 'approve' ? 'approved' : 'deleted', by: b.by }) : x);
const complete = sentences.every(x => x.decision);
const narrative = sentences.filter(x => x.decision === 'approved').map(x => x.linked);
return [{ json: { week: d.week, version: d.version, n: s.n, decision: b.action === 'approve' ? 'approved' : 'deleted', by: b.by, complete,
  patch: { sentences, stage: complete ? 'published' : d.stage },
  preread: { id: d.week, week: d.week, version: d.version, table: d.table, commentary: d.commentary,
             narrative: narrative.length ? narrative : null, note: narrative.length ? 'verified' : 'no narrative this week' } } }];
"""

FOUR_JS = r"""
// Step 13 at 16:00: close the week to new drafts (step 14); a draft not yet verified goes to the backup verifier.
const drafts = ($('Read open drafts').first().json.items || []).filter(d => d.closed !== true);
return drafts.map(d => ({ json: { week: d.week, notify: d.stage === 'to verify',
  patch: { closed: true, stage: d.stage === 'to verify' ? 'backup' : d.stage } } }));
"""

LATE_JS = r"""
// Step 13 at 16:45: a draft still not verified is left out; step 11 runs, marked "not verified".
const drafts = ($('Read drafts with the backup verifier').first().json.items || []).filter(d => d.stage === 'backup');
return drafts.map(d => ({ json: { week: d.week, preread: { id: d.week, week: d.week, version: d.version, table: d.table, commentary: d.commentary,
  narrative: null, note: 'no narrative this week (not verified)', reason: 'not verified' } } }));
"""


def schedule(w, name, day, hour, minute, notes, pos):
    w.node(name, "n8n-nodes-base.scheduleTrigger", V["schedule"],
           {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1, "triggerAtDay": [day], "triggerAtHour": hour, "triggerAtMinute": minute}]}},
           pos=pos, notes=notes)


def build() -> Workflow:
    w = Workflow("R12.2", "R12.2 Draft the weekly briefing narrative with a link behind every figure")
    schedule(w, FRI, 5, 14, 0, "Friday 2 p.m., when owner commentary closes.", [0, 0])
    w.webhook(WRITTEN, "r12-2-table-written",
              "Your weekly table calls this when R12.1 marks a version written. Body: {version}.", pos=[0, 200])
    w.webhook(VERIFY, "r12-2-verify",
              "Your draft list calls this when the verifier approves or deletes a sentence. Body: {week, sentence, action: approve|delete, by}.", pos=[0, 400])
    schedule(w, FOUR, 5, 16, 0, "Friday 4 p.m.: not verified goes to the backup verifier; a newer table gets no narrative.", [0, 600])
    schedule(w, LATE, 5, 16, 45, "Friday 4:45 p.m.: still not verified, the briefing goes out without a narrative.", [0, 800])
    w.config("Config", {
        "table_url": "https://<your weekly table API>",
        "commentary_url": "https://<your owner commentary list API>",
        "customers_url": "https://<your customer list API>",
        "staff_url": "https://<your staff list API>",
        "alert_log_url": "https://<your R12.3 alert log API>",
        "drafts_url": "https://<your draft list API>",
        "preread_url": "https://<your pre-read API>",
        "messaging_url": "https://<your messaging API>",
        "draft_weekday": 5,
        "draft_from": "14:00",
        "first_draft_until": "15:30",
        "must_mention_change_above": {"<measure>": "<your stated size>"},
        "banned_causes": ["because", "<your banned-cause words>"],
        "banned_cause_list_version": "<your list version>",
        "prompt_version": "<your prompt version>",
        "verifier": "<your verifier>",
        "backup_verifier": "<your backup verifier>",
        "verifier_own_measures": ["<measures your verifier owns>"],
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 400])
    for t in (FRI, WRITTEN, VERIFY, FOUR, LATE):
        w.connect(t, "Config")
    w.code("Which event?", EVENT_JS, mode="runOnceForAllItems", pos=[520, 400])
    w.switch("Event", "={{ $json.event }}", ["friday", "written", "verify", "four", "late"], pos=[780, 400])
    w.chain("Config", "Which event?", "Event")

    cfg = "$('Config').first().json"
    # ---- steps 1 to 11 and 14: draft ------------------------------------------
    w.http("Read versions", "GET", f"={{{{ {cfg}.table_url }}}}/versions", query={"_wrap": "1"}, write=False, error_output=False, pos=[1040, 0])
    w.connect("Event", "Read versions", output=0)
    w.connect("Event", "Read versions", output=1)
    w.code("Step 1: Which version?", VERSION_JS, mode="runOnceForAllItems", pos=[1300, 0])
    w.http("Read the week's draft", "GET", f"={{{{ {cfg}.drafts_url }}}}/drafts", query={"_wrap": "1", "week": "={{ $json.week }}"},
           write=False, error_output=False, pos=[1560, 0])
    w.code("Steps 1 and 14: Draft now?", WHEN_JS, mode="runOnceForAllItems", pos=[1820, 0])
    w.chain("Read versions", "Step 1: Which version?", "Read the week's draft", "Steps 1 and 14: Draft now?")
    key = "$('Steps 1 and 14: Draft now?').first().json.key"
    w.reserve_key("Step 2: Reserve key", key, pos=[2080, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[2340, 0])
    w.noop("Duplicate: stop", pos=[2600, -200], notes="A draft exists for this week and table version.")
    w.chain("Steps 1 and 14: Draft now?", "Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    when = "$('Steps 1 and 14: Draft now?').first().json"
    w.http("Read the table", "GET", f"={{{{ {cfg}.table_url }}}}/weekly_table", query={"_wrap": "1", "version": f"={{{{ {when}.version }}}}"},
           write=False, error_output=False, pos=[2600, 0])
    w.http("Read the commentary", "GET", f"={{{{ {cfg}.commentary_url }}}}/commentary", query={"_wrap": "1", "week": f"={{{{ {when}.week }}}}"},
           write=False, error_output=False, pos=[2860, 0], notes="Untrusted input: data, never instructions.")
    w.http("Read the customer list", "GET", f"={{{{ {cfg}.customers_url }}}}/customers", query={"_wrap": "1"}, write=False, error_output=False, pos=[3120, 0])
    w.http("Read the staff list", "GET", f"={{{{ {cfg}.staff_url }}}}/staff", query={"_wrap": "1"}, write=False, error_output=False, pos=[3380, 0])
    w.http("Read the alert log", "GET", f"={{{{ {cfg}.alert_log_url }}}}/alerts", query={"_wrap": "1", "week": f"={{{{ {when}.week }}}}"},
           write=False, error_output=False, pos=[3640, 0], notes="R12.3's crossings this week, for the must-mention list.")
    w.code("Step 3: Rule: hold back commentary naming a listed person", HOLD_JS, mode="runOnceForAllItems", pos=[3900, 0])
    w.connect("New key?", "Read the table", output=0)
    w.chain("Read the table", "Read the commentary", "Read the customer list", "Read the staff list", "Read the alert log",
            "Step 3: Rule: hold back commentary naming a listed person")
    w.if_("Any held back?", "={{ $json.held.length > 0 }}", pos=[4160, 0])
    msg = f"{cfg}.messaging_url"
    w.http("Step 3: Send held-back commentary to the verifier", "POST", f"={{{{ {msg} }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: {cfg}.verifier, subject: 'Held-back commentary, week ' + {when}.week, text: $json.held.map(c => c.measure + ' (' + c.owner + '): ' + c.text).join('\\n') }}) }}}}",
           write=True, pos=[4420, -160])
    w.connect("Step 3: Rule: hold back commentary naming a listed person", "Any held back?")
    w.connect("Any held back?", "Step 3: Send held-back commentary to the verifier", output=0)
    w.if_("Too late?", f"={{{{ {when}.action }}}}", op="equals", right="late", pos=[4680, 0],
          notes="Step 14: a newer table version after Friday 16:00 gets no narrative.")
    w.connect("Any held back?", "Too late?", output=1)
    w.connect("Step 3: Send held-back commentary to the verifier", "Too late?", output=0)

    w.code("Step 4: Build the input", INPUT_JS, mode="runOnceForAllItems", pos=[4940, 0])
    w.connect("Too late?", "Step 4: Build the input", output=1)
    vars_js = ("{ week: $('Step 4: Build the input').first().json.week, table_version: $('Step 4: Build the input').first().json.version, "
               "table_rows: $('Step 4: Build the input').first().json.table_rows, must_mention_list: $('Step 4: Build the input').first().json.must_mention_list, "
               "banned_cause_list: $('Step 4: Build the input').first().json.banned_cause_list, commentary: $('Step 4: Build the input').first().json.commentary_text }")
    build, call = ai_step(w, "Step 5", ROOT / "recipes/R12.2/prompts/draft-narrative.md", vars_js,
                          max_tokens=1500, tries=3, pos_build=[5200, 0], pos_call=[5460, 0])
    w.connect("Step 4: Build the input", build)
    w.code("Steps 6 to 9: Rule: check numbers, causes and missing measures", CHECK_JS, mode="runOnceForAllItems", pos=[5720, 0],
           notes="The rules decide, not the AI. A cause without a banned word passes; catching it is the verifier's job.")
    w.connect(call, "Steps 6 to 9: Rule: check numbers, causes and missing measures", output=0)
    w.code("Step 11: AI error", "return [{ json: { pass: false, reason: 'AI error after two retries', problems: [String(($json.error && $json.error.message) || '')] } }];",
           mode="runOnceForAllItems", pos=[5720, 200])
    w.connect(call, "Step 11: AI error", output=1)
    w.code("Step 14: Too late to draft", "return [{ json: { pass: false, reason: 'newer table version after Friday 16:00', problems: [] } }];",
           mode="runOnceForAllItems", pos=[5720, 400])
    w.connect("Too late?", "Step 14: Too late to draft", output=0)
    w.if_("Draft passed?", "={{ $json.pass }}", pos=[5980, 0])
    for n in ["Steps 6 to 9: Rule: check numbers, causes and missing measures", "Step 11: AI error", "Step 14: Too late to draft"]:
        w.connect(n, "Draft passed?")
    w.code("Step 10: Insert the source links", LINKS_JS, pos=[6240, -120])
    w.connect("Draft passed?", "Step 10: Insert the source links", output=0)
    w.code("The week's draft record", DRAFT_JS, pos=[6500, 0])
    w.connect("Step 10: Insert the source links", "The week's draft record")
    w.connect("Draft passed?", "The week's draft record", output=1)

    drafts = f"{cfg}.drafts_url"
    w.http("Step 12: Save the draft for the verifier", "PUT", f"={{{{ {drafts} }}}}/drafts/{{{{ $json.draft.week }}}}",
           body="={{ JSON.stringify($json.draft) }}", write=True, pos=[6760, 0],
           notes="A passing draft waits for the verifier; a failing one is kept, with its reason, so a newer version can supersede it.")
    w.connect("The week's draft record", "Step 12: Save the draft for the verifier")
    w.if_("No narrative?", "={{ $('The week\\'s draft record').item.json.draft.stage }}", op="equals", right="no narrative", pos=[7020, 0])
    w.http("Step 11: Publish table and commentary, no narrative", "PUT", f"={{{{ {cfg}.preread_url }}}}/pre_reads/{{{{ $('The week\\'s draft record').item.json.preread.week }}}}",
           body="={{ JSON.stringify($('The week\\'s draft record').item.json.preread) }}", write=True, pos=[7280, 120])
    w.chain("Step 12: Save the draft for the verifier", "No narrative?")
    w.connect("No narrative?", "Step 11: Publish table and commentary, no narrative", output=0)

    rec = "$('The week\\'s draft record').first().json.draft"
    w.finish_key("Mark key done", key, "done", f"{rec}.stage", pos=[7540, 0])
    w.decision_log("Decision log", key, f"{rec}.stage + ({rec}.reason ? ': ' + {rec}.reason : '')",
                   f"JSON.stringify({{ superseded: {rec}.superseded, problems: {rec}.problems, sentences: {rec}.sentences.map(s => s.text), held_back: {rec}.held_back, model: {rec}.model, prompt_version: {rec}.prompt_version, banned_cause_list_version: {rec}.banned_cause_list_version }})",
                   pos=[7800, 0])
    w.connect("No narrative?", "Mark key done", output=1)
    w.connect("Step 11: Publish table and commentary, no narrative", "Mark key done")
    w.connect("Mark key done", "Decision log")

    w.finish_key("Mark key failed", key, "failed", "'write failed: ' + ($json.error && $json.error.message || 'unknown')", pos=[7540, 400])
    w.exception("Exception queue: write failed", key, "write failed",
                "'A briefing write failed; check the draft and pre-read before any rerun'", f"{cfg}.verifier", pos=[7800, 400])
    for n in ["Step 3: Send held-back commentary to the verifier", "Step 12: Save the draft for the verifier",
              "Step 11: Publish table and commentary, no narrative"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- step 12: the verifier decides each sentence -------------------------
    body = "$('Which event?').first().json.body"
    w.http("Read the draft", "GET", f"={{{{ {drafts} }}}}/drafts", query={"_wrap": "1", "week": f"={{{{ {body}.week }}}}"},
           write=False, error_output=False, pos=[1040, 600])
    w.code("Step 12: Rule: may this person decide this sentence?", VERIFY_JS, mode="runOnceForAllItems", pos=[1300, 600])
    w.http("Step 12: Record the decision", "PATCH", f"={{{{ {drafts} }}}}/drafts/{{{{ $json.week }}}}",
           body="={{ JSON.stringify($json.patch) }}", write=True, pos=[1560, 600])
    v = "$('Step 12: Rule: may this person decide this sentence?').first().json"
    w.decision_log("Step 12: Log the decision", f"{v}.week + ':' + {v}.version + ':sentence ' + {v}.n", f"{v}.decision + ' by ' + {v}.by",
                   f"JSON.stringify({{ sentence: {v}.n }})", pos=[1820, 600])
    w.if_("All sentences decided?", f"={{{{ {v}.complete }}}}", pos=[2080, 600])
    w.http("Step 12: Publish the verified briefing", "PUT", f"={{{{ {cfg}.preread_url }}}}/pre_reads/{{{{ {v}.week }}}}",
           body=f"={{{{ JSON.stringify({v}.preread) }}}}", write=True, pos=[2340, 600])
    w.connect("Event", "Read the draft", output=2)
    w.chain("Read the draft", "Step 12: Rule: may this person decide this sentence?", "Step 12: Record the decision",
            "Step 12: Log the decision", "All sentences decided?")
    w.connect("All sentences decided?", "Step 12: Publish the verified briefing", output=0)

    # ---- step 13: Friday 16:00 and 16:45 --------------------------------------
    w.http("Read open drafts", "GET", f"={{{{ {drafts} }}}}/drafts", query={"_wrap": "1"}, write=False, error_output=False, pos=[1040, 900])
    w.code("Step 13: Rule: not verified by 16:00", FOUR_JS, mode="runOnceForAllItems", pos=[1300, 900])
    w.http("Step 13: Close the week to new drafts", "PATCH", f"={{{{ {drafts} }}}}/drafts/{{{{ $json.week }}}}",
           body="={{ JSON.stringify($json.patch) }}", write=True, pos=[1560, 900])
    w.if_("Backup verifier needed?", "={{ $('Step 13: Rule: not verified by 16:00').item.json.notify }}", pos=[1820, 900])
    w.http("Step 13: Ask the backup verifier", "POST", f"={{{{ {msg} }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: {cfg}.backup_verifier, subject: 'Verify the weekly narrative by 16:45', text: 'Week ' + $('Step 13: Rule: not verified by 16:00').item.json.week + ': the narrative is not yet verified.' }}) }}}}",
           write=True, pos=[2080, 900])
    w.connect("Event", "Read open drafts", output=3)
    w.chain("Read open drafts", "Step 13: Rule: not verified by 16:00", "Step 13: Close the week to new drafts", "Backup verifier needed?")
    w.connect("Backup verifier needed?", "Step 13: Ask the backup verifier", output=0)

    w.http("Read drafts with the backup verifier", "GET", f"={{{{ {drafts} }}}}/drafts", query={"_wrap": "1", "stage": "backup"},
           write=False, error_output=False, pos=[1040, 1100])
    w.code("Step 13: Rule: not verified by 16:45", LATE_JS, mode="runOnceForAllItems", pos=[1300, 1100])
    w.http("Step 11: Publish table and commentary, not verified", "PUT", f"={{{{ {cfg}.preread_url }}}}/pre_reads/{{{{ $json.week }}}}",
           body="={{ JSON.stringify($json.preread) }}", write=True, pos=[1560, 1100])
    w.http("Step 13: Mark the draft not verified", "PATCH", f"={{{{ {drafts} }}}}/drafts/{{{{ $('Step 13: Rule: not verified by 16:45').item.json.week }}}}",
           body="={{ JSON.stringify({ stage: 'not verified' }) }}", write=True, pos=[1820, 1100])
    w.connect("Event", "Read drafts with the backup verifier", output=4)
    w.chain("Read drafts with the backup verifier", "Step 13: Rule: not verified by 16:45", "Step 11: Publish table and commentary, not verified",
            "Step 13: Mark the draft not verified")

    w.exception("Exception queue: verification write failed", "$('Which event?').first().json.event", "write failed",
                "'A verification or publication write failed; check the draft and pre-read'", f"{cfg}.verifier", pos=[2600, 1000])
    for n in ["Step 12: Record the decision", "Step 12: Publish the verified briefing", "Step 13: Close the week to new drafts",
              "Step 13: Ask the backup verifier", "Step 11: Publish table and commentary, not verified", "Step 13: Mark the draft not verified"]:
        w.connect(n, "Exception queue: verification write failed", output=1)
    return w
