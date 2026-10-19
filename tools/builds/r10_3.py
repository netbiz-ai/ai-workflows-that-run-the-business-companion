"""R10.3 Prepare tomorrow's dispatch briefing, read-only.

Source: book Chapter 10, recipe R10.3, build steps 1 to 11 (recipes/R10.3/build-spec.md);
AI step: recipes/R10.3/prompts/briefing-notes.md. Step 6 uses R10.1's step 4 masking rule.
Step 11 is the lead dispatcher's: nothing in this workflow writes to the schedule.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from wf import AI_PARSE_JS, V, Workflow, ai_step  # noqa: E402
from r10_1 import MASK_JS  # noqa: E402

T1 = "Step 1: Each working afternoon"
T2 = "Step 1: Second start"
RULE2 = "Step 2: Rule: no briefing yet, under the caps?"
TABLE = "Step 5: Rule: copy the briefing table"
MASK = "Step 6: Rule: mask codes in notes and messages"
CHECK = "Step 8: Rules: check the AI text"
SOURCES = {
    "work orders": "Step 4: Read work orders",
    "crew schedule": "Step 4: Read crew schedule",
    "helpdesk messages": "Step 4: Read helpdesk messages",
    "overdue work": "Step 4: Read overdue work",
    "stock exceptions": "Step 4: Read stock exceptions",
}
SOURCES_JS = "const SOURCES = " + str(SOURCES).replace("'", '"') + ";\n"

STEP2_JS = r"""
// Step 2: no full briefing posted today, starts under two, AI spend under its caps; otherwise stop.
// "Under its caps": this month's spend leaves room for one more run at the run cap.
const cfg = $('Config').first().json;
const today = new Date().toISOString().slice(0, 10);
const days = $('Read the budget table').first().json.items || [];
const row = Object.assign({ id: today, starts: 0, full_briefing_posted: false, ai_spend: 0 }, days.find(d => d.id === today) || {});
const month = days.filter(d => String(d.id).startsWith(today.slice(0, 7))).reduce((s, d) => s + Number(d.ai_spend || 0), 0);
const capped = month + cfg.run_cap_usd > cfg.monthly_cap_usd;
const reason = row.full_briefing_posted ? 'full briefing already posted today'
  : Number(row.starts) >= cfg.max_starts ? `already ${row.starts} starts today`
  : capped ? `AI spend this month $${month.toFixed(2)}: no room for a run at the $${cfg.run_cap_usd} run cap under the $${cfg.monthly_cap_usd} monthly cap` : null;
return [{ json: { run: !reason, capped: !row.full_briefing_posted && capped, reason, today, row, month_spend: month,
                  start: Number(row.starts) + 1 } }];
"""

STEP5_JS = SOURCES_JS + r"""
// Step 5: copy job IDs, times, crews and addresses into the briefing table by rule; the AI never writes them.
const unavailable = [];
const got = {};
for (const [k, n] of Object.entries(SOURCES)) {
  const j = $(n).first().json;
  if (j.error !== undefined || !Array.isArray(j.items)) { unavailable.push(k); got[k] = []; } else got[k] = j.items;
}
const crewDown = unavailable.includes('crew schedule');
const crewBy = Object.fromEntries(got['crew schedule'].map(a => [String(a.job_id), a.crew]));
const table = got['work orders'].map(o => ({ job_id: String(o.id), time: String(o.window || ''),
  crew: crewBy[String(o.id)] || (crewDown ? 'not available' : 'unassigned'), address: String(o.address || '') }))
  .sort((a, b) => (a.time + a.job_id).localeCompare(b.time + b.job_id));
const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
return [{ json: { tomorrow, table, unavailable } }];
"""

STEP6_JS = MASK_JS + SOURCES_JS + r"""
// Step 6: mask codes in notes and messages before the AI step or the post.
const cfg = $('Config').first().json;
const items = n => { const j = $(n).first().json; return Array.isArray(j.items) ? j.items : []; };
const m = t => maskCodes(t, cfg).text;
const { table, unavailable } = $('""" + TABLE + r"""').first().json;
const orders = Object.fromEntries(items(SOURCES['work orders']).map(o => [String(o.id), o]));
const of = (n, id) => items(n).filter(x => String(x.job_id) === id);
const jobs = table.map(r => ({
  job_id: r.job_id,
  notes: m((orders[r.job_id] || {}).notes || ''),
  messages: of(SOURCES['helpdesk messages'], r.job_id).map(t => m(`${t.subject || ''}: ${t.body || ''}`)),
  overdue: of(SOURCES['overdue work'], r.job_id).map(x => m(x.description || '')),
  stock: of(SOURCES['stock exceptions'], r.job_id).map(x => m(`${x.item || ''}: ${x.issue || ''}`)),
}));
const list = a => (a.length ? a.join(' | ') : 'none');
const text = jobs.map(j => `${j.job_id}\n  notes: ${j.notes || 'none'}\n  open messages: ${list(j.messages)}\n  overdue work: ${list(j.overdue)}\n  stock exceptions: ${list(j.stock)}`).join('\n');
return [{ json: { jobs_text: text, unavailable_sources: unavailable.length ? unavailable.join(', ') : 'none' } }];
"""

CHECK_JS = AI_PARSE_JS + MASK_JS + r"""
// Step 8: every source reached, the job list not empty; every job ID once, none new; no table time
// or address, and nothing maskable, in the AI text. Step 9 posts the briefing, or the raw list as "partial".
const cfg = $('Config').first().json;
const s2 = $('""" + RULE2 + r"""').first().json;
const { tomorrow, table, unavailable } = $('""" + TABLE + r"""').first().json;
const reply = $input.first().json;
const reasons = [];
if (unavailable.length) reasons.push('not available: ' + unavailable.join(', '));
if (!table.length) reasons.push('job list empty');
let ai = null;
if (reply.error || !reply.content) reasons.push('AI error');
else {
  const p = parseAi(reply, ['notes', 'risks']);
  if (!p.ok) reasons.push('AI output failed the check: ' + p.problem);
  else if (!Array.isArray(p.value.notes) || !Array.isArray(p.value.risks)
           || p.value.notes.some(n => !n || typeof n.job_id !== 'string' || typeof n.note !== 'string')
           || p.value.risks.some(r => typeof r !== 'string')) reasons.push('AI output failed the check: wrong shape');
  else ai = p.value;
}
if (ai) {
  const ids = table.map(r => r.job_id);
  const seen = {};
  for (const n of ai.notes) seen[n.job_id] = (seen[n.job_id] || 0) + 1;
  const missing = ids.filter(id => !seen[id]), twice = ids.filter(id => seen[id] > 1), extra = Object.keys(seen).filter(id => !ids.includes(id));
  if (missing.length) reasons.push('no note for ' + missing.join(', '));
  if (twice.length) reasons.push('more than one note for ' + twice.join(', '));
  if (extra.length) reasons.push('new job ID ' + extra.join(', '));
  const long = ai.notes.filter(n => n.note.trim().split(/\s+/).filter(Boolean).length > cfg.note_max_words).map(n => n.job_id);
  if (long.length) reasons.push(`note over ${cfg.note_max_words} words for ` + long.join(', '));
  const all = ai.notes.map(n => n.note).concat(ai.risks).join('\n');
  const lo = all.toLowerCase();
  const times = [...new Set(table.flatMap(r => [r.time, ...r.time.split(/[-\u2013]/)]).map(t => t.trim()).filter(t => t.length >= 3))];
  if (times.some(t => lo.includes(t.toLowerCase()))) reasons.push('a table time in the AI text');
  if (table.some(r => r.address.trim() && lo.includes(r.address.trim().toLowerCase()))) reasons.push('a table address in the AI text');
  if (maskCodes(all, cfg).masked) reasons.push('maskable text in the AI text');
}
const pass = reasons.length === 0;
const u = (reply && reply.usage) || {};
const geo = cfg.ai_inference_geo === 'us' ? cfg.ai_us_only_multiplier : 1;
const cost = ((Number(u.input_tokens || 0) * cfg.ai_price_input_per_mtok + Number(u.output_tokens || 0) * cfg.ai_price_output_per_mtok) / 1e6) * geo;
const rows = table.map(r => `${r.job_id} | ${r.time} | ${r.crew} | ${r.address}`);
const head = ['Job | Time | Crew | Address', ...rows];
let text;
if (pass) {
  text = [`Full dispatch briefing for ${tomorrow} (${table.length} jobs)`, '', ...head, '',
    'Notes (unchecked):', ...ids_in_order(), '', 'Risks (unchecked):', ...(ai.risks.length ? ai.risks.map(r => '- ' + r) : ['- none listed'])].join('\n');
} else {
  const retry = s2.start < cfg.max_starts ? 'the second start will try again' : 'no further start today';
  text = [`Partial dispatch briefing for ${tomorrow}: raw job list from what was reached; ${retry}.`,
    'Sources not available: ' + (unavailable.length ? unavailable.join(', ') : 'none'),
    'Why partial: ' + reasons.join('; '), '', ...(rows.length ? head : ['No jobs reached.'])].join('\n');
}
function ids_in_order() { const by = Object.fromEntries(ai.notes.map(n => [n.job_id, n.note])); return table.map(r => `${r.job_id}: ${by[r.job_id]}`); }
return [{ json: { pass, reasons, cost: Math.round(cost * 1e6) / 1e6,
  post: { id: `briefing-${s2.today}-${s2.start}`, channel: cfg.dispatch_channel, kind: pass ? 'full' : 'partial', text } } }];
"""


def read_once(w: Workflow, name: str, url: str, query: dict, pos) -> str:
    """Step 4: one read, a time limit, no retry; a failure flows on as an error item ("not available")."""
    w.http(name, "GET", url, query=query, write=True, error_output=False, pos=pos)  # write=True only turns retries off
    n = w.nodes[-1]
    n["onError"] = "continueRegularOutput"
    n["parameters"]["options"]["timeout"] = "={{ $('Config').item.json.source_timeout_ms }}"
    return name


def build() -> Workflow:
    w = Workflow("R10.3", "R10.3 Prepare tomorrow's dispatch briefing, read-only")
    for name, hour, pos, note in ((T1, 15, [0, 0], "Each working afternoon at the time Tom sets."),
                                  (T2, 17, [0, 200], "The second start, later the same afternoon.")):
        w.node(name, "n8n-nodes-base.scheduleTrigger", V["schedule"],
               {"rule": {"interval": [{"field": "cronExpression", "expression": f"0 {hour} * * 1-5"}]}}, pos=pos, notes=note)
    cfg = "$('Config').item.json"
    w.config("Config", {
        "scheduling_url": "https://<your scheduling system API, read-only, no restricted fields>",
        "crews_url": "https://<your crew schedule API, read-only>",
        "helpdesk_url": "https://<your helpdesk API, read-only>",
        "overdue_url": "https://<your overdue-work list API, read-only>",
        "stock_url": "https://<your stock-exception list API, read-only>",
        "budget_url": "https://<your budget table API>",
        "messaging_url": "https://<your messaging API>",
        "dispatch_channel": "<your dispatch channel>",
        "systems_owner": "<your systems owner>",
        "max_starts": 2,
        "run_cap_usd": 3,
        "monthly_cap_usd": 70,
        "source_timeout_ms": 10000,
        "note_max_words": 25,
        "ai_price_input_per_mtok": 0.10,
        "ai_price_output_per_mtok": 0.50,
        "ai_us_only_multiplier": 1.1,
        "masking_list": ["code", "gate", "keypad", "PIN", "key safe"],
        "address_words": ["<your floor, unit and street words, such as floor, unit, apartment, street, road>"],
        "mask_token": "<your mask token>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 100])
    w.connect(T1, "Config")
    w.connect(T2, "Config")

    # ---- steps 2 and 3: the budget table, before anything else ------------------
    w.http("Read the budget table", "GET", f"={{{{ {cfg}.budget_url }}}}/days", query={"_wrap": "1"},
           write=False, error_output=False, pos=[520, 100], notes="If the budget table cannot be read, nothing runs.")
    w.code(RULE2, STEP2_JS, mode="runOnceForAllItems", pos=[780, 100])
    w.if_("Run?", "={{ $json.run }}", pos=[1040, 100])
    w.if_("Capped?", "={{ $json.capped }}", pos=[1300, 300])
    w.http("Step 2: Alert Owen", "POST", f"={{{{ {cfg}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: {cfg}.systems_owner, subject: 'R10.3 stopped: AI cap', text: $json.reason + '. Find the cause before raising any cap.' }}) }}}}",
           write=True, error_output=False, pos=[1560, 240])
    w.noop("Stop", pos=[1560, 400], notes="Already posted today, or two starts used.")
    w.chain("Config", "Read the budget table", RULE2, "Run?")
    w.connect("Run?", "Capped?", output=1)
    w.connect("Capped?", "Step 2: Alert Owen", output=0)
    w.connect("Capped?", "Stop", output=1)
    day_url = f"={{{{ {cfg}.budget_url }}}}/days/{{{{ $('{RULE2}').item.json.today }}}}"
    w.http("Step 3: Add one to today's starts", "PUT", day_url,
           body=f"={{{{ JSON.stringify(Object.assign({{}}, $('{RULE2}').item.json.row, {{ starts: $('{RULE2}').item.json.start }})) }}}}",
           write=True, pos=[1300, 0])
    w.connect("Run?", "Step 3: Add one to today's starts", output=0)

    # ---- step 4: each source once ------------------------------------------------
    tomorrow = "={{ new Date(Date.now() + 86400000).toISOString().slice(0, 10) }}"
    reads = [
        (SOURCES["work orders"], f"={{{{ {cfg}.scheduling_url }}}}/work_orders", {"_wrap": "1", "slot_date": tomorrow}),
        (SOURCES["crew schedule"], f"={{{{ {cfg}.crews_url }}}}/assignments", {"_wrap": "1", "date": tomorrow}),
        (SOURCES["helpdesk messages"], f"={{{{ {cfg}.helpdesk_url }}}}/tickets", {"_wrap": "1", "status": "open"}),
        (SOURCES["overdue work"], f"={{{{ {cfg}.overdue_url }}}}/items", {"_wrap": "1"}),
        (SOURCES["stock exceptions"], f"={{{{ {cfg}.stock_url }}}}/exceptions", {"_wrap": "1"}),
    ]
    prev = "Step 3: Add one to today's starts"
    for i, (name, url, q) in enumerate(reads):
        read_once(w, name, url, q, pos=[1560 + 260 * i, 0])
        w.connect(prev, name)
        prev = name
    w.code(TABLE, STEP5_JS, mode="runOnceForAllItems", pos=[2860, 0])
    w.code(MASK, STEP6_JS, mode="runOnceForAllItems", pos=[3120, 0])
    w.chain(prev, TABLE, MASK)

    # ---- step 7: one AI call, no retry ------------------------------------------
    vars_js = (f"{{ mask_token: $('Config').first().json.mask_token, unavailable_sources: $('{MASK}').first().json.unavailable_sources, "
               f"jobs: $('{MASK}').first().json.jobs_text }}")
    build_, call = ai_step(w, "Step 7", ROOT / "recipes/R10.3/prompts/briefing-notes.md", vars_js,
                           max_tokens=2000, tries=1, pos_build=[3380, 0], pos_call=[3640, 0])
    w.connect(MASK, build_)
    w.code(CHECK, CHECK_JS, mode="runOnceForAllItems", pos=[3900, 0],
           notes="The rules decide what is posted; an AI error posts the raw list, headed \"partial\".")
    w.connect(call, CHECK, output=0)
    w.connect(call, CHECK, output=1)
    w.if_("Pass?", "={{ $json.pass }}", pos=[4160, 0])
    w.connect(CHECK, "Pass?")

    # ---- steps 9 and 10 -------------------------------------------------------------
    post_url = f"={{{{ {cfg}.messaging_url }}}}/messages"
    w.http("Step 9: Post the briefing", "POST", post_url, body="={{ JSON.stringify($json.post) }}", write=True, pos=[4420, -120])
    w.http("Step 9: Mark full briefing posted", "PATCH", day_url, body="={{ JSON.stringify({ full_briefing_posted: true }) }}",
           write=True, pos=[4680, -120])
    w.http("Step 9: Post the partial list", "POST", post_url, body="={{ JSON.stringify($json.post) }}", write=True, pos=[4420, 120],
           notes="The second start retries; nothing retries a source in a loop.")
    w.http("Step 10: Record AI spend", "PATCH", day_url,
           body=f"={{{{ JSON.stringify({{ ai_spend: Math.round((Number($('{RULE2}').item.json.row.ai_spend || 0) + $('{CHECK}').item.json.cost) * 1e6) / 1e6 }}) }}}}",
           write=True, pos=[4940, 0])
    w.connect("Pass?", "Step 9: Post the briefing", output=0)
    w.connect("Pass?", "Step 9: Post the partial list", output=1)
    w.chain("Step 9: Post the briefing", "Step 9: Mark full briefing posted", "Step 10: Record AI spend")
    w.connect("Step 9: Post the partial list", "Step 10: Record AI spend")

    w.exception("Exception queue: write failed", f"'briefing ' + $('{RULE2}').item.json.today", "write failed",
                "'A budget-table write or the post failed: ' + (($json.error && $json.error.message) || 'unknown')",
                f"{cfg}.systems_owner", pos=[4940, 360])
    for n in ["Step 3: Add one to today's starts", "Step 9: Post the briefing", "Step 9: Mark full briefing posted",
              "Step 9: Post the partial list", "Step 10: Record AI spend"]:
        w.connect(n, "Exception queue: write failed", output=1)
    return w
