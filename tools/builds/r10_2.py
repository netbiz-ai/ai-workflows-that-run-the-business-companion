"""R10.2 Send delivery confirmations and handle reschedule replies.

Source: book Chapter 10, recipe R10.2, build steps 1 to 12 (recipes/R10.2/build-spec.md);
AI step: recipes/R10.2/prompts/label-reply.md. Step 4 uses R10.1's step 4 masking rule.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from wf import AI_PARSE_JS, V, Workflow, ai_step  # noqa: E402
from r10_1 import MASK_JS  # noqa: E402

S1 = "Step 1: Slot set or changed"
S2 = "Step 2: Each afternoon"
S3 = "Step 3: Customer reply"
S12 = "Step 12: Every hour"
EV = "$('Config').item.json.body"
MASK = "Step 4: Rule: mask codes in the reply"
RULE6 = "Step 6: Rule: slot pick or trade reply?"
RULE8 = "Steps 8 and 9: Rules: label, job and route"
RULE10 = "Step 10: Rule: up to three open slots"
ACTION = "Action"

COMMON_JS = r"""
const cfg = $('Config').first().json;
const ev = cfg.body;
const fill = (tpl, vals) => String(tpl).replace(/\{(\w+)\}/g, (m, k) => (k in vals ? String(vals[k]) : m));
const contact = c => (c && (c.channel === 'email' ? c.email : c.phone)) || null;
const task = (type, reason, extra = {}) => ({ id: 'T-' + ev.message_id, to: cfg.dispatch_queue, job: ev.job_ref, type, reason,
  reply: $('""" + MASK + r"""').first().json.masked, ...extra });
"""

CONFIRM_JS = r"""
// Step 1: the confirmation, with date, window and preparation notes, on the customer's preferred channel.
const cfg = $('Config').first().json;
const fill = (tpl, vals) => String(tpl).replace(/\{(\w+)\}/g, (m, k) => (k in vals ? String(vals[k]) : m));
const job = $('Step 1: Read the job').first().json;
const c = job.customer || {};
return [{ json: { job: job.id, message: { to: c.channel === 'email' ? c.email : c.phone, channel: c.channel, job: job.id, template: 'confirmation',
  text: fill(cfg.confirmation_template, { date: job.slot_date, window: job.window, prep: cfg.preparation_notes }) } } }];
"""

REMIND_JS = r"""
// Step 2: one reminder for each of tomorrow's jobs.
const cfg = $('Config').first().json;
const fill = (tpl, vals) => String(tpl).replace(/\{(\w+)\}/g, (m, k) => (k in vals ? String(vals[k]) : m));
return ($('Step 2: Read tomorrow\'s jobs').first().json.items || []).map(job => {
  const c = job.customer || {};
  return { json: { job: job.id, message: { id: 'R-' + job.id + '-' + job.slot_date, to: c.channel === 'email' ? c.email : c.phone, channel: c.channel,
    job: job.id, template: 'reminder', text: fill(cfg.reminder_template, { date: job.slot_date, window: job.window }) } } };
});
"""

STEP4_JS = MASK_JS + r"""
// Step 4: mask codes before anything reads or logs the reply.
const cfg = $('Config').first().json;
return [{ json: { masked: maskCodes(cfg.body.text, cfg).text } }];
"""

STEP5_JS = COMMON_JS + r"""
// Step 5: an urgent word goes to a dispatcher at once and to R4.2 (a helpdesk ticket, which R4.2 watches).
const masked = $('""" + MASK + r"""').first().json.masked;
const hit = (cfg.urgent_words || []).filter(u => new RegExp('\\b' + String(u).toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).test(masked.toLowerCase()));
if (!hit.length) return [{ json: { action: 'continue' } }];
return [{ json: { action: 'urgent', outcome: 'urgent: dispatcher at once and R4.2', reason: 'urgent word: ' + hit.join(', '),
  task: task('urgent', 'Urgent words in the reply: ' + hit.join(', ') + '. Call the customer now.'),
  ticket: { subject: 'Urgent customer reply on job ' + ev.job_ref, body: masked, from: ev.from, job: ev.job_ref, source: 'R10.2' } } }];
"""

STEP6_JS = COMMON_JS + r"""
// Step 6: a 1, 2 or 3 answering a slot request is a pick for the dispatcher; any other trade reply goes to a dispatcher at once.
const masked = $('""" + MASK + r"""').first().json.masked;
const job = $('Read the job').first().json;
const valid = !job.error && String(job.id) === String(ev.job_ref);
const row = $('Read the open slot offer').first().json;
const offer = row && row.rules ? (typeof row.rules === 'string' ? JSON.parse(row.rules) : row.rules) : null;
const m = masked.match(/^\s*([123])\s*[.!]?\s*$/);
const slot = m && offer && (offer.slots || [])[Number(m[1]) - 1];
const base = { valid, job: valid ? job : null };
if (slot) {
  return [{ json: { ...base, action: 'task', outcome: 'slot pick to dispatcher', reason: 'picked ' + m[1],
    task: task('slot pick', `Customer picked slot ${m[1]}: ${slot.date} ${slot.window}. Book it, or phone if it has gone.`, { slot: slot.id }) } }];
}
if (valid && job.source === 'trade') {
  return [{ json: { ...base, action: 'task', outcome: 'trade reply to dispatcher', reason: 'trade account',
    task: task('trade reply', 'Trade account reply: deal with it now.') } }];
}
return [{ json: { ...base, action: 'ai' } }];
"""

STEP8_JS = AI_PARSE_JS + COMMON_JS + r"""
// Step 8: an allowed label and a valid job reference; otherwise a dispatcher task.
// Step 9: confirm is logged only on a plain yes naming no day, date or time; question or other
// goes to the service inbox (R4.1, a helpdesk ticket); anything else is a dispatcher task.
const masked = $('""" + MASK + r"""').first().json.masked;
const s6 = $('""" + RULE6 + r"""').first().json;
const reply = $input.first().json;
let label = null, problem = null;
if (reply.error || !reply.content) problem = 'AI error after retries';
else {
  const p = parseAi(reply, ['label'], { label: ['confirm', 'reschedule', 'cancel', 'question', 'other'] });
  if (p.ok) label = p.value.label; else problem = 'AI output failed the check: ' + p.problem;
}
if (!problem && !s6.valid) problem = 'no valid job reference';
const out = (o) => [{ json: { valid: s6.valid, job: s6.job, label, ...o } }];
if (problem) return out({ action: 'task', outcome: 'dispatcher task', reason: problem, task: task('reply', problem + '. Read the reply and deal with it.') });
function namesDayDateTime(t) {
  const lo = t.toLowerCase();
  if (lo.split(/[^a-z]+/).filter(Boolean).some(w => (cfg.day_words || []).includes(w))) return true;
  return /\b\d{1,2}[\/.-]\d{1,2}([\/.-]\d{2,4})?\b/.test(lo) || /\b\d{1,2}(:\d{2})?\s*(am|pm)\b/.test(lo)
    || /\b\d{1,2}:\d{2}\b/.test(lo) || /\b\d{1,2}(st|nd|rd|th)\b/.test(lo);
}
if (label === 'confirm') {
  if (!namesDayDateTime(masked)) return out({ action: 'log', outcome: 'confirmed', reason: 'plain yes' });
  return out({ action: 'task', outcome: 'dispatcher task', reason: 'confirm names a day, date or time',
    task: task('reply', 'The customer confirms but names a day, date or time. Check the booking.') });
}
if (label === 'question' || label === 'other') {
  return out({ action: 'inbox', outcome: 'service inbox', reason: label,
    ticket: { subject: 'Customer reply on job ' + ev.job_ref, body: masked, from: ev.from, job: ev.job_ref, source: 'R10.2' } });
}
if (label === 'reschedule') return out({ action: 'reschedule' });
return out({ action: 'task', outcome: 'dispatcher task', reason: label, task: task('reply', `The customer asks to ${label}. Nothing has been changed.`) });
"""

STEP10_JS = COMMON_JS + r"""
// Step 10: up to three open slots in the zone; a failed lookup, or none open, is a dispatcher task.
const s8 = $('""" + RULE8 + r"""').first().json;
const job = s8.job;
const res = $input.first().json;
if (res.error) return [{ json: { action: 'task', label: 'reschedule', outcome: 'dispatcher task', reason: 'slot lookup failed',
  task: task('reply', 'The customer asks to reschedule; the slot lookup failed. Phone the customer.') } }];
const slots = (res.items || []).filter(s => s.status === 'open' && s.zone === job.zone && s.id !== job.slot_id)
  .sort((a, b) => (a.date + ' ' + a.window).localeCompare(b.date + ' ' + b.window)).slice(0, cfg.max_slots);
if (!slots.length) return [{ json: { action: 'task', label: 'reschedule', outcome: 'dispatcher task', reason: 'no open slot in the zone',
  task: task('reply', 'The customer asks to reschedule; no open slot in the zone. Phone the customer.') } }];
const list = slots.map((s, i) => `${i + 1}. ${s.date} ${s.window}`).join('\n');
const c = job.customer || {};
return [{ json: { action: 'offer', label: 'reschedule', outcome: 'slots offered', reason: slots.length + ' slots',
  slots: slots.map((s, i) => ({ n: i + 1, id: s.id, date: s.date, window: s.window })),
  message: { id: 'O-' + ev.message_id, to: contact(c), channel: c.channel, job: job.id, template: 'slot request',
             text: fill(cfg.slot_request_template, { slots: list }) } } }];
"""

NOPICK_JS = r"""
// Step 12: offers with no reply in 24 hours.
return $input.all().filter(i => i.json.id).map(i => ({ json: { offer: String(i.json.id), job: i.json.item } }));
"""


def build() -> Workflow:
    w = Workflow("R10.2", "R10.2 Send delivery confirmations and handle reschedule replies")
    w.webhook(S1, "r10-2-slot", "Your scheduling system calls this when a slot is set or changed. Body: {job_id}.", pos=[0, -300])
    w.schedule(S2, 15, "Each afternoon: reminders for tomorrow's jobs.", pos=[0, -100])
    w.webhook(S3, "r10-2-reply", "Your reply channel calls this for each customer reply. Body: {message_id, job_ref, from, text}.", pos=[0, 100])
    w.node(S12, "n8n-nodes-base.scheduleTrigger", V["schedule"], {"rule": {"interval": [{"field": "hours", "hoursInterval": 1}]}},
           pos=[0, 300], notes="Step 12: slot requests with no pick in 24 hours go to a dispatcher.")
    w.config("Config", {
        "scheduling_url": "https://<your scheduling system API>",
        "messaging_url": "https://<your messaging API>",
        "tasks_url": "https://<your dispatcher task API>",
        "helpdesk_url": "https://<your helpdesk API>",
        "dispatch_queue": "<your dispatcher queue>",
        "confirmation_template": "<your confirmation template; the workflow fills {date}, {window} and {prep}>",
        "reminder_template": "<your reminder template; the workflow fills {date} and {window}>",
        "slot_request_template": "{slots}\nReply 1, 2 or 3 within 24 hours and a dispatcher will confirm your new time; until then your booking stays as it is.",
        "preparation_notes": "<your preparation notes>",
        "urgent_words": ["leak", "smoke", "injured", "damaged"],
        "day_words": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                      "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun",
                      "today", "tomorrow", "tonight", "weekend", "morning", "afternoon", "evening", "noon", "midday",
                      "january", "february", "march", "april", "may", "june", "july", "august", "september",
                      "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept",
                      "oct", "nov", "dec"],
        "max_slots": 3,
        "pick_hours": 24,
        "masking_list": ["code", "gate", "keypad", "PIN", "key safe"],
        "address_words": ["<your floor, unit and street words, such as floor, unit, apartment, street, road>"],
        "mask_token": "<your mask token>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 0])
    for t in (S1, S2, S3, S12):
        w.connect(t, "Config")
    w.switch("Start", f"={{{{ $('{S1}').isExecuted ? 'slot' : $('{S2}').isExecuted ? 'afternoon' : $('{S3}').isExecuted ? 'reply' : 'no pick' }}}}",
             ["slot", "afternoon", "reply", "no pick"], pos=[520, 0])
    w.connect("Config", "Start")
    cfg = "$('Config').item.json"

    # ---- step 1: confirmation -------------------------------------------------
    w.http("Step 1: Read the job", "GET", f"={{{{ {cfg}.scheduling_url }}}}/work_orders/{{{{ {EV}.job_id }}}}",
           write=False, error_output=False, pos=[780, -500])
    w.code("Step 1: Fill the confirmation", CONFIRM_JS, mode="runOnceForAllItems", pos=[1040, -500])
    w.http("Step 1: Send the confirmation", "POST", f"={{{{ {cfg}.messaging_url }}}}/messages",
           body="={{ JSON.stringify($json.message) }}", write=True, pos=[1300, -500])
    w.http("Step 1: Not delivered: dispatcher phones", "POST", f"={{{{ {cfg}.tasks_url }}}}/tasks",
           body=f"={{{{ JSON.stringify({{ id: 'ND-' + $('Step 1: Fill the confirmation').item.json.job + '-confirmation', to: {cfg}.dispatch_queue, job: $('Step 1: Fill the confirmation').item.json.job, type: 'message not delivered', reason: 'Confirmation not delivered: ' + (($json.error && $json.error.message) || 'send error') + '. Phone the customer.' }}) }}}}",
           write=True, error_output=False, pos=[1560, -400])
    w.connect("Start", "Step 1: Read the job", output=0)
    w.chain("Step 1: Read the job", "Step 1: Fill the confirmation", "Step 1: Send the confirmation")
    w.connect("Step 1: Send the confirmation", "Step 1: Not delivered: dispatcher phones", output=1)

    # ---- step 2: reminders ------------------------------------------------------
    w.http("Step 2: Read tomorrow's jobs", "GET", f"={{{{ {cfg}.scheduling_url }}}}/work_orders",
           query={"_wrap": "1", "slot_date": "={{ new Date(Date.now() + 86400000).toISOString().slice(0, 10) }}"},
           write=False, error_output=False, pos=[780, -250])
    w.code("Step 2: Fill a reminder per job", REMIND_JS, mode="runOnceForAllItems", pos=[1040, -250])
    w.http("Step 2: Send the reminder", "POST", f"={{{{ {cfg}.messaging_url }}}}/messages",
           body="={{ JSON.stringify($json.message) }}", write=True, pos=[1300, -250])
    w.http("Step 2: Not delivered: dispatcher phones", "POST", f"={{{{ {cfg}.tasks_url }}}}/tasks",
           body=f"={{{{ JSON.stringify({{ id: 'ND-' + $('Step 2: Fill a reminder per job').item.json.job + '-reminder', to: {cfg}.dispatch_queue, job: $('Step 2: Fill a reminder per job').item.json.job, type: 'message not delivered', reason: 'Reminder not delivered: ' + (($json.error && $json.error.message) || 'send error') + '. Phone the customer.' }}) }}}}",
           write=True, error_output=False, pos=[1560, -150])
    w.connect("Start", "Step 2: Read tomorrow's jobs", output=1)
    w.chain("Step 2: Read tomorrow's jobs", "Step 2: Fill a reminder per job", "Step 2: Send the reminder")
    w.connect("Step 2: Send the reminder", "Step 2: Not delivered: dispatcher phones", output=1)

    # ---- steps 3 to 10: a customer reply ---------------------------------------
    KEY = f"String({EV}.message_id)"
    w.reserve_key("Step 3: Reserve key", KEY, pos=[780, 100])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1040, 100])
    w.noop("Duplicate: stop", pos=[1300, -20], notes="This reply was handled before.")
    w.connect("Start", "Step 3: Reserve key", output=2)
    w.connect("Step 3: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)
    w.code(MASK, STEP4_JS, mode="runOnceForAllItems", pos=[1300, 100], notes="Nothing reads or logs the reply before this.")
    w.connect("New key?", MASK, output=0)
    w.code("Step 5: Rule: urgent words?", STEP5_JS, mode="runOnceForAllItems", pos=[1560, 100])
    w.if_("Urgent?", "={{ $json.action }}", op="equals", right="urgent", pos=[1820, 100])
    w.chain(MASK, "Step 5: Rule: urgent words?", "Urgent?")

    w.http("Read the job", "GET", f"={{{{ {cfg}.scheduling_url }}}}/work_orders/{{{{ {EV}.job_ref }}}}",
           write=False, error_output=False, pos=[2080, 220], notes="A missing job comes through as an error: no valid job reference.")
    w.nodes[-1]["onError"] = "continueRegularOutput"
    w.pg("Read the open slot offer",
         "SELECT rules FROM decision_log WHERE recipe = 'R10.2' AND item = $1 AND decision = 'slots offered' "
         "AND decided_at > now() - make_interval(hours => $2::int) ORDER BY id DESC LIMIT 1",
         args=[f"String({EV}.job_ref)", f"{cfg}.pick_hours"], pos=[2340, 220])
    w.code(RULE6, STEP6_JS, mode="runOnceForAllItems", pos=[2600, 220])
    w.if_("To the AI?", "={{ $json.action }}", op="equals", right="ai", pos=[2860, 220])
    w.connect("Urgent?", "Read the job", output=1)
    w.chain("Read the job", "Read the open slot offer", RULE6, "To the AI?")

    vars_js = f"{{ masked_reply: $('{MASK}').first().json.masked, mask_token: $('Config').first().json.mask_token }}"
    build_, call = ai_step(w, "Step 7", ROOT / "recipes/R10.2/prompts/label-reply.md", vars_js,
                           max_tokens=50, tries=2, pos_build=[3120, 340], pos_call=[3380, 340])
    w.connect("To the AI?", build_, output=0)
    w.code(RULE8, STEP8_JS, mode="runOnceForAllItems", pos=[3640, 340],
           notes="The rules decide, not the AI; an AI error becomes a dispatcher task with the reply.")
    w.connect(call, RULE8, output=0)
    w.connect(call, RULE8, output=1)
    w.if_("Reschedule?", "={{ $json.action }}", op="equals", right="reschedule", pos=[3900, 340])
    w.connect(RULE8, "Reschedule?")
    w.http("Step 10: Read open slots in the zone", "GET", f"={{{{ {cfg}.scheduling_url }}}}/slots",
           query={"_wrap": "1", "zone": f"={{{{ $('{RULE8}').item.json.job.zone }}}}", "status": "open"},
           write=False, error_output=False, pos=[4160, 460])
    w.nodes[-1]["onError"] = "continueRegularOutput"
    w.code(RULE10, STEP10_JS, mode="runOnceForAllItems", pos=[4420, 460])
    w.connect("Reschedule?", "Step 10: Read open slots in the zone", output=0)
    w.connect("Step 10: Read open slots in the zone", RULE10)

    w.switch(ACTION, "={{ $json.action }}", ["urgent", "task", "inbox", "offer", "log"], pos=[4680, 100],
             notes="Only a dispatcher changes the schedule; nothing here writes to it.")
    for n, o in (("Urgent?", 0), ("To the AI?", 1), ("Reschedule?", 1), (RULE10, 0)):
        w.connect(n, ACTION, output=o)
    act = f"$('{ACTION}').item.json"
    w.http("Step 5: Dispatcher task at once", "POST", f"={{{{ {cfg}.tasks_url }}}}/tasks",
           body="={{ JSON.stringify($json.task) }}", write=True, pos=[4940, -100])
    w.http("Step 5: To R4.2 (helpdesk ticket)", "POST", f"={{{{ {cfg}.helpdesk_url }}}}/tickets",
           body=f"={{{{ JSON.stringify({act}.ticket) }}}}", write=True, pos=[5200, -100])
    w.connect(ACTION, "Step 5: Dispatcher task at once", output=0)
    w.connect("Step 5: Dispatcher task at once", "Step 5: To R4.2 (helpdesk ticket)")
    w.http("Dispatcher task", "POST", f"={{{{ {cfg}.tasks_url }}}}/tasks",
           body="={{ JSON.stringify($json.task) }}", write=True, pos=[4940, 60],
           notes="Steps 6, 8, 9 and 10: a dispatcher task with the masked reply.")
    w.http("Step 9: To the service inbox (R4.1)", "POST", f"={{{{ {cfg}.helpdesk_url }}}}/tickets",
           body="={{ JSON.stringify($json.ticket) }}", write=True, pos=[4940, 220])
    w.http("Step 10: Send the slot request", "POST", f"={{{{ {cfg}.messaging_url }}}}/messages",
           body="={{ JSON.stringify($json.message) }}", write=True, pos=[4940, 380],
           notes="A request only: the booking stays as it is until a dispatcher confirms.")
    w.connect(ACTION, "Dispatcher task", output=1)
    w.connect(ACTION, "Step 9: To the service inbox (R4.1)", output=2)
    w.connect(ACTION, "Step 10: Send the slot request", output=3)

    w.finish_key("Mark key done", KEY, "done", f"{act}.outcome", pos=[5460, 100])
    w.decision_log("Decision log", f"String({EV}.job_ref)", f"{act}.outcome",
                   f"JSON.stringify({{ message: {EV}.message_id, intent: {act}.label || null, reason: {act}.reason || null, slots: {act}.slots || [] }})",
                   pos=[5720, 100])
    for n in ["Step 5: To R4.2 (helpdesk ticket)", "Dispatcher task", "Step 9: To the service inbox (R4.1)", "Step 10: Send the slot request"]:
        w.connect(n, "Mark key done")
    w.connect(ACTION, "Mark key done", output=4)
    w.connect("Mark key done", "Decision log")

    w.finish_key("Mark key failed", KEY, "failed", "'write failed: ' + (($json.error && $json.error.message) || 'unknown')", pos=[5460, 560])
    w.exception("Exception queue: write failed", f"String({EV}.job_ref)", "write failed",
                f"'Reply ' + {EV}.message_id + ': ' + {act}.action + ' write failed; the dispatcher phones the customer'",
                f"{cfg}.dispatch_queue", pos=[5720, 560])
    for n in ["Step 5: Dispatcher task at once", "Step 5: To R4.2 (helpdesk ticket)", "Dispatcher task",
              "Step 9: To the service inbox (R4.1)", "Step 10: Send the slot request"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- step 12: no pick in 24 hours -----------------------------------------
    w.pg("Step 12: Read offers with no pick",
         "SELECT o.id, o.item FROM decision_log o WHERE o.recipe = 'R10.2' AND o.decision = 'slots offered' "
         "AND o.decided_at <= now() - make_interval(hours => $1::int) "
         "AND NOT EXISTS (SELECT 1 FROM decision_log p WHERE p.recipe = o.recipe AND p.item = o.item AND p.id > o.id)",
         args=[f"{cfg}.pick_hours"], pos=[780, 700])
    w.code("Step 12: Rule: offers still waiting", NOPICK_JS, mode="runOnceForAllItems", pos=[1040, 700])
    w.reserve_key("Step 12: Reserve key", "'no pick:' + $json.offer", pos=[1300, 700])
    w.if_("Not tasked before?", "={{ $json.is_new }}", pos=[1560, 700])
    w.http("Step 12: Dispatcher decides whether to phone", "POST", f"={{{{ {cfg}.tasks_url }}}}/tasks",
           body=f"={{{{ JSON.stringify({{ id: 'NP-' + $('Step 12: Rule: offers still waiting').item.json.offer, to: {cfg}.dispatch_queue, job: $('Step 12: Rule: offers still waiting').item.json.job, type: 'no pick', reason: 'No pick in 24 hours: decide whether to phone.' }}) }}}}",
           write=True, error_output=False, pos=[1820, 700])
    w.connect("Start", "Step 12: Read offers with no pick", output=3)
    w.chain("Step 12: Read offers with no pick", "Step 12: Rule: offers still waiting", "Step 12: Reserve key", "Not tasked before?")
    w.connect("Not tasked before?", "Step 12: Dispatcher decides whether to phone", output=0)
    return w
