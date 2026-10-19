"""R5.2 Prepare a research and qualification brief for the salesperson.

Source: book Chapter 5, recipe R5.2, build steps 1 to 6 (recipes/R5.2/build-spec.md);
AI step: recipes/R5.2/prompts/draft-brief.md.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

T = "Step 1: Lead assigned"
EV = f"$('{T}').first().json.body"
KEY = f"String({EV}.lead_id)"
LEAD = "$('Step 3: Read the lead').first().json"

PAGES_JS = r"""
// Step 3: up to five pages from the agreed public source types, in the lead's order.
const cfg = $('Config').first().json;
const lead = $('Step 3: Read the lead').first().json;
const allowed = (lead.pages || []).filter(u => cfg.allowed_sources.some(p => String(u).startsWith(p)));
const pages = [...new Set(allowed)].slice(0, cfg.max_pages);
return pages.length ? pages.map(url => ({ json: { url } })) : [{ json: { none: true } }];
"""

SOURCES_JS = r"""
// Step 3: every source with its ID or address; a page that failed twice is "not fetched".
const cfg = $('Config').first().json;
const lead = $('Step 3: Read the lead').first().json;
const strip = r => { const { pages, ...rest } = r; return JSON.stringify(rest); };
const sources = [{ id: String(lead.id), kind: 'lead record', status: 'read', text: strip(lead) }];
for (const h of ($('Step 3: Read account history').first().json.items || [])) sources.push({ id: String(h.id), kind: 'CRM history', status: 'read', text: JSON.stringify(h) });
for (const q of ($('Step 3: Read past quotes').first().json.items || [])) sources.push({ id: String(q.id), kind: 'past quote', status: 'read', text: JSON.stringify(q) });
let fetched = false;
try { fetched = $('Step 3: Fetch page').isExecuted; } catch (e) {}
if (fetched) {
  const asked = $('Step 3: Pages to fetch').all();
  $input.all().forEach((it, i) => {
    const url = asked[i].json.url;
    const ok = it.json && typeof it.json.data === 'string' && !it.json.error;
    const text = ok ? it.json.data.replace(/<(script|style)[\s\S]*?<\/\1>/gi, ' ').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, cfg.page_text_limit) : '';
    sources.push({ id: url, kind: 'public page', status: ok ? 'fetched' : 'not fetched', text });
  });
}
return [{ json: { sources } }];
"""

CHECK_JS = AI_PARSE_JS + r"""
// Step 5: every section present, every criterion one of the three values, every source
// from step 3; a second rule fails the brief if a page holds a listed phrase.
const cfg = $('Config').first().json;
const sources = $('Step 3: Sources').first().json.sources;
const citable = new Set(sources.filter(s => s.status !== 'not fetched').map(s => s.id));
const p = parseAi($('Step 4: AI call').first().json, ['company', 'past_dealings', 'need', 'criteria']);
if (!p.ok) return [{ json: { status: 'ai error', problems: ['AI output failed the schema: ' + p.problem] } }];
const b = p.value, problems = [];
const cites = (list, where) => {
  if (!Array.isArray(list)) { problems.push(`${where}: no sources list`); return; }
  for (const s of list) if (!citable.has(String(s))) problems.push(`${where}: source not from step 3: ${s}`);
};
for (const sec of ['company', 'past_dealings', 'need']) {
  if (!Array.isArray(b[sec])) { problems.push(`section ${sec} missing`); continue; }
  b[sec].forEach((c, i) => {
    if (!c || typeof c.text !== 'string') problems.push(`${sec} claim ${i + 1}: no text`);
    if (!c || !Array.isArray(c.sources) || !c.sources.length) problems.push(`${sec} claim ${i + 1}: no source`);
    else cites(c.sources, `${sec} claim ${i + 1}`);
  });
}
const counts = { met: 0, 'not met': 0, unknown: 0 };
if (!Array.isArray(b.criteria)) problems.push('section criteria missing');
else {
  for (const want of cfg.criteria.map(c => c.name)) {
    const got = b.criteria.filter(c => c && c.criterion === want);
    if (got.length !== 1) { problems.push(`criterion "${want}" ${got.length ? 'repeated' : 'missing'}`); continue; }
    const c = got[0];
    if (!['met', 'not met', 'unknown'].includes(c.value)) { problems.push(`criterion "${want}": value not met, not met or unknown`); continue; }
    counts[c.value]++;
    if (c.value !== 'unknown' && !(Array.isArray(c.sources) && c.sources.length)) problems.push(`criterion "${want}": ${c.value} with no source`);
    else cites(c.sources || [], `criterion "${want}"`);
  }
  for (const c of b.criteria) if (!cfg.criteria.some(k => c && k.name === c.criterion)) problems.push(`criterion not on the list: ${c && c.criterion}`);
}
// The second rule: page text holding a listed phrase fails the brief, whatever the output says.
const pages = sources.filter(s => s.kind === 'public page' && s.status === 'fetched');
for (const s of pages) for (const ph of cfg.injection_phrases) if (s.text.toLowerCase().includes(ph.toLowerCase())) problems.push(`page ${s.id} holds "${ph}"`);
return [{ json: { status: problems.length ? 'failed' : 'passed', problems, brief: b, criteria_counts: counts } }];
"""

NOTE_JS = r"""
// Step 6: a passing brief, a failing one marked unverified, or after an AI error the links.
const cfg = $('Config').first().json;
const lead = $('Step 3: Read the lead').first().json;
const sources = $('Step 3: Sources').first().json.sources.map(s => ({ id: s.id, kind: s.kind, status: s.status }));
const r = $json;
const links = sources.map(s => `- ${s.id} (${s.kind}${s.status === 'not fetched' ? ', not fetched' : ''})`).join('\n');
const cite = c => ` [${(Array.isArray(c.sources) ? c.sources : []).join('; ')}]`;
let text, title;
if (r.status === 'ai error') {
  title = `Lead brief: ${lead.id}: links only`;
  text = `The AI step failed; research by hand from these sources.\n\nSources\n${links}`;
} else {
  const b = r.brief;
  const arr = x => (Array.isArray(x) ? x : []);
  const sec = (h, list) => `${h}\n` + arr(list).map(c => `- ${c && c.text}${cite(c || {})}`).join('\n');
  title = (r.status === 'failed' ? `${cfg.unverified_label}: ` : '') + `Lead brief: ${lead.id}`;
  text = [r.status === 'failed' ? `${cfg.unverified_label}.\nProblems found: ${r.problems.join('; ')}` : null,
    sec('Company', b.company), sec('Past dealings', b.past_dealings), sec('Need', b.need),
    'Criteria\n' + arr(b.criteria).filter(c => c).map(c => `- ${c.criterion}: ${c.value}${c.value === 'unknown' ? ' (ask on the call)' : cite(c)}`).join('\n'),
    `Sources\n${links}`].filter(Boolean).join('\n\n');
}
return [{ json: { title, text, check: r.status === 'ai error' ? 'links only' : r.status, problems: r.problems || [], sources, criteria_counts: r.criteria_counts || null } }];
"""


def build() -> Workflow:
    w = Workflow("R5.2", "R5.2 Prepare a research and qualification brief")
    w.webhook(T, "r5-2-lead-assigned", "Your CRM calls this when a lead is assigned. Body: {lead_id}.", pos=[0, 0])
    w.config("Config", {
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
    }, pos=[260, 0])
    w.reserve_key("Step 2: Reserve key", KEY, pos=[520, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[780, 0])
    w.noop("Duplicate: stop", pos=[1040, -200], notes="A brief was prepared for this lead before; a reassignment gets no second one.")
    w.chain(T, "Config", "Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    crm = "$('Config').first().json.crm_url"
    w.http("Step 3: Read the lead", "GET", f"={{{{ {crm} }}}}/leads/{{{{ {EV}.lead_id }}}}", write=False, error_output=False, pos=[1040, 0])
    w.http("Step 3: Read account history", "GET", f"={{{{ {crm} }}}}/history", query={"_wrap": "1", "lead_id": f"={{{{ {LEAD}.id }}}}"},
           write=False, error_output=False, pos=[1300, 0])
    w.http("Step 3: Read past quotes", "GET", f"={{{{ {crm} }}}}/quotes", query={"_wrap": "1", "lead_id": f"={{{{ {LEAD}.id }}}}"},
           write=False, error_output=False, pos=[1560, 0])
    w.code("Step 3: Pages to fetch", PAGES_JS, mode="runOnceForAllItems", pos=[1820, 0],
           notes="Only addresses under your agreed public source types (Config allowed_sources); never personal profiles.")
    w.connect("New key?", "Step 3: Read the lead", output=0)
    w.chain("Step 3: Read the lead", "Step 3: Read account history", "Step 3: Read past quotes", "Step 3: Pages to fetch")
    w.if_("Any pages?", "={{ !$json.none }}", pos=[2080, 0])
    w.connect("Step 3: Pages to fetch", "Any pages?")
    fetch = w.http("Step 3: Fetch page", "GET", "={{ $json.url }}", write=False, error_output=False, pos=[2340, -120],
                   notes="One try and one retry; a page failing twice is \"not fetched\". Page text is untrusted.")
    n = next(x for x in w.nodes if x["name"] == fetch)
    n["parameters"]["options"] = {"response": {"response": {"neverError": False, "responseFormat": "text", "outputPropertyName": "data"}}}
    n.update(maxTries=2, waitBetweenTries=1000, onError="continueRegularOutput")
    w.connect("Any pages?", fetch, output=0)
    w.code("Step 3: Sources", SOURCES_JS, mode="runOnceForAllItems", pos=[2600, 0])
    w.connect(fetch, "Step 3: Sources")
    w.connect("Any pages?", "Step 3: Sources", output=1)

    vars_js = ("{ criteria: $('Config').first().json.criteria.map(c => `${c.name}: ${c.description}`).join('\\n'), "
               "sources: $('Step 3: Sources').first().json.sources.map(s => `[source ${s.id}]\\n<<<\\n${s.status === 'not fetched' ? 'not fetched' : s.text}\\n>>>`).join('\\n\\n') }")
    build, call = ai_step(w, "Step 4", ROOT / "recipes/R5.2/prompts/draft-brief.md", vars_js,
                          max_tokens=1500, tries=2, pos_build=[2860, 0], pos_call=[3120, 0])
    w.connect("Step 3: Sources", build)
    w.code("Step 5: Rule: valid, sourced, no page instructions?", CHECK_JS, mode="runOnceForAllItems", pos=[3380, -100],
           notes="The rules decide; the AI only drafts.")
    w.connect(call, "Step 5: Rule: valid, sourced, no page instructions?", output=0)
    w.code("Step 5: AI error", "return [{ json: { status: 'ai error', problems: ['AI error after one retry: ' + String(($json.error && $json.error.message) || '')] } }];",
           mode="runOnceForAllItems", pos=[3380, 120])
    w.connect(call, "Step 5: AI error", output=1)

    w.code("Step 6: Write the note", NOTE_JS, mode="runOnceForAllItems", pos=[3640, 0])
    w.connect("Step 5: Rule: valid, sourced, no page instructions?", "Step 6: Write the note")
    w.connect("Step 5: AI error", "Step 6: Write the note")
    w.http("Step 6: Attach to the lead", "POST", f"={{{{ {crm} }}}}/notes",
           body=f"={{{{ JSON.stringify({{ lead_id: {LEAD}.id, title: $json.title, check: $json.check, text: $json.text, sources: $json.sources }}) }}}}",
           write=True, pos=[3900, 0], notes="The one write this recipe makes; never retried.")
    w.connect("Step 6: Write the note", "Step 6: Attach to the lead")

    note = "$('Step 6: Write the note').first().json"
    w.finish_key("Mark key done", KEY, "done", f"{note}.check", pos=[4160, 0])
    w.decision_log("Decision log", f"{EV}.lead_id", f"'brief ' + {note}.check",
                   f"JSON.stringify({{ check: {note}.check, problems: {note}.problems, criteria: {note}.criteria_counts, sources: {note}.sources.map(s => s.id + (s.status === 'not fetched' ? ' (not fetched)' : '')) }})",
                   pos=[4420, 0])
    w.chain("Step 6: Attach to the lead", "Mark key done", "Decision log")

    w.finish_key("Mark key failed", KEY, "failed", "'write failed: ' + (($json.error && $json.error.message) || 'unknown')", pos=[4160, 300])
    w.exception("Exception queue: write failed", f"{EV}.lead_id", "write failed",
                "'Brief note write failed, not retried; attach it by hand or release the key'",
                "$('Config').first().json.brief_owner", pos=[4420, 300])
    w.connect("Step 6: Attach to the lead", "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")
    return w
