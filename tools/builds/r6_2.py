"""R6.2 Remind the owner and draft a follow-up when a quote goes quiet.

Source: book Chapter 6, recipe R6.2, Table 6.2 and build steps 1 to 8
(recipes/R6.2/build-spec.md); AI step: recipes/R6.2/prompts/draft-follow-up.md.

Each working morning, every "sent" quote is sorted by Table 6.2, first fitting
row from the top. The reminder history is the CRM tasks this workflow created
(source = Config task_source), one per reminder, on the quote and revision: their
count is the reminder number and the newest one's date starts the gap. Rows 4 to
6 each task the owner (or their cover) and post the reminder in Teams; only row 6
gets an AI draft, and a draft that fails step 7 is dropped, never the reminder.
Nothing goes to a customer.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, V, Workflow, ai_step  # noqa: E402

T = "Step 1: Quiet-quote check each working day"
CFG = "$('Config').first().json"
SORT = "Step 3: Rule: sort by Table 6.2"
Q = f"$('{SORT}').item.json"

SORT_JS = r"""
// Step 3: Table 6.2, the first row that fits, read from the top, decides. Rows 1 and 3 get nothing and stop here.
const cfg = $('Config').first().json;
const quotes = $('Step 2: CRM: List sent quotes').first().json.items || [];
const flagged = new Set(($('CRM: Read account flags').first().json.items || []).filter(a => a.dispute === true).map(a => a.id));
const tasks = $('CRM: Read reminder tasks').first().json.items || [];
const day = s => new Date(String(s).slice(0, 10) + 'T00:00:00Z');
const today = day(new Date().toISOString());
const working = (a, b) => { let n = 0; for (let x = new Date(a.getTime() + 86400000); x <= b; x = new Date(x.getTime() + 86400000)) if (x.getUTCDay() % 6 !== 0) n++; return n; };
const out = [];
for (const q of quotes) {
  if (q.status !== 'sent') continue;
  const last = [q.sent_date, q.last_activity_date].filter(Boolean).sort().pop();
  const quiet = working(day(last), today);
  const mine = tasks.filter(t => t.quote_id === q.id && String(t.revision) === String(q.revision));
  const sent = mine.length;
  const newest = mine.map(t => t.created).filter(Boolean).sort().pop();
  const since = newest ? Math.round((today - day(newest)) / 86400000) : null;
  const left = q.valid_until ? (day(q.valid_until) < today ? -1 : working(today, day(q.valid_until))) : null;
  const rules = { quiet_working_days: quiet, reminders_sent: sent, days_since_reminder: since, working_days_to_expiry: left };
  let row;
  if (quiet < cfg.window_working_days || (since !== null && since < cfg.gap_days)) continue;  // row 1: nothing today
  if (flagged.has(q.account_id)) row = 'dispute';                                             // row 2
  else if (sent >= cfg.reminder_limit) continue;                                              // row 3: Ben reviews it at the pipeline meeting
  else if (left !== null && left <= cfg.window_working_days) row = 'expiry';                 // row 4
  else if (sent === cfg.reminder_limit - 1) row = 'last';                                     // row 5
  else row = 'due';                                                                           // row 6
  const reminder = sent + 1;
  out.push({ json: {
    row, quote_id: q.id, quote_ref: q.ref, revision: q.revision, reminder, valid_until: q.valid_until || null,
    key: row === 'dispute' ? `${q.id}:dispute` : `${q.id}:${q.revision}:${reminder}`,
    owner: q.owner, to: (cfg.covers || {})[q.owner] || q.owner, account_id: q.account_id,
    description: q.description || '', summary: q.last_activity_summary || '', rules: Object.assign(rules, { row }) },
    pairedItem: { item: 0 } });
}
return out;
"""

STEP5_JS = r"""
// Step 5: the dispute, expiry and last-reminder rows, now, without a draft.
const cfg = $('Config').first().json;
const q = $('Step 3: Rule: sort by Table 6.2').item.json;
const today = new Date().toISOString().slice(0, 10);
if (q.row === 'dispute') {
  return { json: { task: false, to: cfg.sales_lead, subject: `Quote ${q.quote_ref}: account flagged for a dispute`,
    text: `No reminder goes to the owner while account ${q.account_id} is flagged for a dispute or complaint. You are told once.`,
    decision: 'no reminder; sales lead told (dispute)', rules: q.rules } };
}
const title = q.row === 'expiry'
  ? `Requote before following up (R5.3): quote ${q.quote_ref} expires ${q.valid_until}`
  : `Call, or mark the quote lost: quote ${q.quote_ref}, last allowed reminder`;
return { json: { task: true, to: q.to, subject: title, text: title,
  task_body: { source: cfg.task_source, quote_id: q.quote_id, revision: q.revision, reminder: q.reminder, owner: q.to, title, created: today, due: today },
  decision: q.row === 'expiry' ? `reminder ${q.reminder}, no draft: requote` : `reminder ${q.reminder}, no draft: call or mark lost`,
  rules: q.rules } };
"""

CHECK_JS = AI_PARSE_JS + r"""
// Step 7, as in Example 5.2: placeholder present, length within limit, no listed phrase,
// no number (digits or words) not copied from the description. A failure drops the draft, not the reminder.
const cfg = $('Config').first().json;
const q = $('Step 3: Rule: sort by Table 6.2').item.json;
const p = parseAi($json, ['draft']);
if (!p.ok || typeof p.value.draft !== 'string') return { json: { draft: null, check: `dropped: ${p.ok ? 'draft is not a string' : p.problem}` } };
const draft = p.value.draft.trim();
const fails = [];
if (!draft.includes('{{quote_ref}}')) fails.push('placeholder missing');
const words = draft.split(/\s+/).filter(Boolean).length;
if (words > cfg.max_draft_words) fails.push(`${words} words`);
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const phrase = cfg.never_say.find(ph => new RegExp(`\\b${esc(String(ph).toLowerCase())}\\b`).test(draft.toLowerCase()));
if (phrase) fails.push(`never-say phrase: ${phrase}`);
const NUMBER_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve',
  'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen', 'twenty', 'thirty', 'forty', 'fifty',
  'sixty', 'seventy', 'eighty', 'ninety', 'hundred', 'thousand', 'million', 'billion', 'dozen', 'half', 'quarter'];
const desc = String(q.description).toLowerCase();
const descNumbers = new Set(desc.match(/\d+(?:[.,]\d+)*/g) || []);
const descWords = new Set(desc.match(/[a-z]+/g) || []);
const body = draft.replace(/\{\{quote_ref\}\}/g, ' ').toLowerCase();
const stray = [...(body.match(/\d+(?:[.,]\d+)*/g) || []).filter(n => !descNumbers.has(n)),
               ...(body.match(/[a-z]+/g) || []).filter(w => NUMBER_WORDS.includes(w) && !descWords.has(w))];
if (stray.length) fails.push(`number not in the description: ${[...new Set(stray)].join(', ')}`);
if (fails.length) return { json: { draft: null, check: `dropped: ${fails.join('; ')}` } };
return { json: { draft, check: 'passed' } };
"""

STEP8_JS = r"""
// Step 8: fill {{quote_ref}}, then task the owner or their cover and post the reminder and any draft in Teams.
const cfg = $('Config').first().json;
const q = $('Step 3: Rule: sort by Table 6.2').item.json;
const today = new Date().toISOString().slice(0, 10);
const draft = $json.draft ? $json.draft.split('{{quote_ref}}').join(q.quote_ref) : null;
const title = `Follow up quote ${q.quote_ref}`;
return { json: { to: q.to, subject: `Quote ${q.quote_ref} has gone quiet`,
  text: draft ? `${title}: a draft follow-up is below to send, rewrite or ignore.` : `${title}.`, draft,
  task_body: { source: cfg.task_source, quote_id: q.quote_id, revision: q.revision, reminder: q.reminder, owner: q.to, title, created: today, due: today },
  decision: `reminder ${q.reminder}, ${draft ? 'with draft' : 'without draft'}`,
  rules: Object.assign({}, q.rules, { draft_check: $json.check }) } };
"""


def build() -> Workflow:
    w = Workflow("R6.2", "R6.2 Remind the owner and draft a follow-up when a quote goes quiet")
    w.node(T, "n8n-nodes-base.scheduleTrigger", V["schedule"],
           {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1, "triggerAtDay": [1, 2, 3, 4, 5], "triggerAtHour": 7}]}},
           pos=[0, 0], notes="Monday to Friday at 7:00, before the trade desk opens. Set the workflow's time zone (Settings), or the run moves at each daylight-saving change.")
    w.config("Config", {
        "crm_url": "https://<your CRM API>",
        "messaging_url": "https://<your Teams messaging API>",
        "window_working_days": 5,
        "gap_days": 3,
        "reminder_limit": 3,
        "never_say": ["discount", "price match", "free"],
        "max_draft_words": 120,
        "sales_lead": "<your sales lead>",
        "covers": {"<an absent salesperson>": "<their cover>"},
        "task_source": "R6.2 quiet-quote reminder",
        "crm_admin": "<your CRM admin>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 0])
    crm = f"{CFG}.crm_url"
    w.http("Step 2: CRM: List sent quotes", "GET", f"={{{{ {crm} }}}}/quotes", query={"_wrap": "1", "status": "sent"},
           write=False, error_output=False, pos=[520, 0], notes="Each quote with its revision, sent date, valid-until date, owner and last activity (date and accepted summary, from R6.1).")
    w.http("CRM: Read account flags", "GET", f"={{{{ {crm} }}}}/accounts", query={"_wrap": "1"},
           write=False, error_output=False, pos=[780, 0], notes="The dispute flag, set by hand until R8.3 is built.")
    w.http("CRM: Read reminder tasks", "GET", f"={{{{ {crm} }}}}/tasks", query={"_wrap": "1", "source": f"={{{{ {CFG}.task_source }}}}"},
           write=False, error_output=False, pos=[1040, 0], notes="The reminders this workflow has sent: one task each.")
    w.code(SORT, SORT_JS, mode="runOnceForAllItems", pos=[1300, 0], notes="The rule decides; only the last row reaches step 6.")
    w.chain(T, "Config", "Step 2: CRM: List sent quotes", "CRM: Read account flags", "CRM: Read reminder tasks", SORT)

    w.reserve_key("Step 4: Reserve key", "$json.key", pos=[1560, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1820, 0])
    w.noop("Used: skip", pos=[2080, -200], notes="This reminder, or this dispute notice, was sent before.")
    w.chain(SORT, "Step 4: Reserve key", "New key?")
    w.connect("New key?", "Used: skip", output=1)
    w.switch("Which row?", f"={{{{ {Q}.row }}}}", ["due", "dispute", "expiry", "last"], pos=[2080, 0])
    w.connect("New key?", "Which row?", output=0)

    # ---- step 5: dispute, expiry and last-reminder rows, no draft -------------------
    w.code("Step 5: Rule: the reminder, no draft", STEP5_JS, pos=[2340, 360])
    for i in (1, 2, 3):
        w.connect("Which row?", "Step 5: Rule: the reminder, no draft", output=i)
    w.if_("Task?", "={{ $json.task }}", pos=[2600, 360])
    w.connect("Step 5: Rule: the reminder, no draft", "Task?")
    s5 = "$('Step 5: Rule: the reminder, no draft').item.json"
    w.http("Step 5: CRM: Task the owner or cover", "POST", f"={{{{ {crm} }}}}/tasks",
           body=f"={{{{ JSON.stringify({s5}.task_body) }}}}", write=True, pos=[2860, 280])
    w.http("Step 5: Teams: Post the reminder", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: {s5}.to, subject: {s5}.subject, text: {s5}.text, draft: null }}) }}}}",
           write=True, pos=[3120, 400], notes="The dispute row tells the sales lead once (key: quote ID plus \"dispute\").")
    w.connect("Task?", "Step 5: CRM: Task the owner or cover", output=0)
    w.connect("Task?", "Step 5: Teams: Post the reminder", output=1)
    w.connect("Step 5: CRM: Task the owner or cover", "Step 5: Teams: Post the reminder")
    w.finish_key("Step 5: Mark key done", f"{Q}.key", "done", f"{s5}.decision", pos=[3380, 400])
    w.decision_log("Step 5: Decision log", f"{Q}.quote_id", f"{s5}.decision",
                   f"JSON.stringify(Object.assign({{ revision: {Q}.revision, reminder: {Q}.reminder }}, {s5}.rules))", pos=[3640, 400])
    w.chain("Step 5: Teams: Post the reminder", "Step 5: Mark key done", "Step 5: Decision log")

    # ---- steps 6 to 8: the last row, with an AI draft ---------------------------------
    vars_js = (f"{{ never_say_phrases: {CFG}.never_say.map(p => '\"' + p + '\"').join(', '), "
               f"quote_description: {Q}.description, last_activity_summary: {Q}.summary }}")
    b6, c6 = ai_step(w, "Step 6", ROOT / "recipes/R6.2/prompts/draft-follow-up.md", vars_js,
                     max_tokens=2048, tries=3, pos_build=[2340, 0], pos_call=[2600, 0])
    w.connect("Which row?", b6, output=0)
    w.code("Step 7: Rule: check the draft", CHECK_JS, pos=[2860, -80], notes="The rule decides, not the AI.")
    w.code("Step 7: AI error", "return { json: { draft: null, check: 'dropped: AI error after three retries' } };", pos=[2860, 100])
    w.connect(c6, "Step 7: Rule: check the draft", output=0)
    w.connect(c6, "Step 7: AI error", output=1)
    w.code("Step 8: Fill the quote reference", STEP8_JS, pos=[3120, 0])
    w.connect("Step 7: Rule: check the draft", "Step 8: Fill the quote reference")
    w.connect("Step 7: AI error", "Step 8: Fill the quote reference")
    s8 = "$('Step 8: Fill the quote reference').item.json"
    w.http("Step 8: CRM: Task the owner or cover", "POST", f"={{{{ {crm} }}}}/tasks",
           body=f"={{{{ JSON.stringify({s8}.task_body) }}}}", write=True, pos=[3380, 0])
    w.http("Step 8: Teams: Post the reminder and any draft", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: {s8}.to, subject: {s8}.subject, text: {s8}.text, draft: {s8}.draft }}) }}}}",
           write=True, pos=[3640, 0], notes="To the owner or their cover only; nothing goes to a customer.")
    w.finish_key("Step 8: Mark key done", f"{Q}.key", "done", f"{s8}.decision", pos=[3900, 0])
    w.decision_log("Step 8: Decision log", f"{Q}.quote_id", f"{s8}.decision",
                   f"JSON.stringify(Object.assign({{ revision: {Q}.revision, reminder: {Q}.reminder }}, {s8}.rules))", pos=[4160, 0])
    w.chain("Step 8: Fill the quote reference", "Step 8: CRM: Task the owner or cover", "Step 8: Teams: Post the reminder and any draft",
            "Step 8: Mark key done", "Step 8: Decision log")

    # ---- a failed write is never retried ---------------------------------------------------
    w.finish_key("Mark key failed", f"{Q}.key", "failed", "'write failed: ' + ($json.error && $json.error.message || 'unknown')", pos=[3900, 640])
    w.exception("Exception queue: write failed", f"{Q}.quote_id", "write failed",
                "'Task or Teams post failed; check the CRM before anything is redone'", f"{CFG}.crm_admin", pos=[4160, 640])
    for n in ["Step 5: CRM: Task the owner or cover", "Step 5: Teams: Post the reminder",
              "Step 8: CRM: Task the owner or cover", "Step 8: Teams: Post the reminder and any draft"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")
    return w
