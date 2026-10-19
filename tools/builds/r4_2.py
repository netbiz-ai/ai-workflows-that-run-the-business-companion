"""R4.2 Escalate complaints, safety issues and legal threats to a person at once.

Source: book Chapter 4, recipe R4.2, build steps 1 to 6 (recipes/R4.2/build-spec.md);
AI step: recipes/R4.2/prompts/rate-risk.md.

The clock (steps 5 and 6) lives in the decision log: every notice is a row with
"clock": "running", and a check every five minutes reads the latest row per
ticket. The person notified taking the ticket stops the clock; a passed limit
notifies the next person (owner, then backup, then the final contact) on a fresh
clock. The book's n8n note puts Retry On Fail on the notice steps only, so the
text and call nodes retry and the AI call does not.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, V, Workflow, ai_step  # noqa: E402

T = "Step 1: New message"
CLOCK = "Step 6: Every 5 minutes: check the clock"
EV = f"$('{T}').item.json.body"
KEY = f"{EV}.ticket_id + ':' + {EV}.message_id"
CFG = "$('Config').first().json"

KEYWORD_JS = r"""
// Step 3: a listed keyword, or an attachment with almost no text, escalates at once (no AI call).
const cfg = $('Config').first().json;
const t = $('Read the message').first().json;
const text = `${t.subject || ''}\n${t.body || ''}`.toLowerCase();
const hit = cfg.keywords.find(k => text.includes(String(k).toLowerCase()));
const chars = String(t.body || '').trim().length;
const attachment = (t.attachments || []).length > 0 && chars < cfg.min_text_chars;
const fired = hit ? `keyword: ${hit}` : attachment ? 'attachment with almost no text' : '';
return [{ json: { fired, rules: { keyword: hit || 'none', attachment: attachment ? 'almost no text' : 'no' } } }];
"""

RATE_JS = AI_PARSE_JS + r"""
// Step 4: the message stays in its queue only if all three answers are exactly "no".
const yn = ['yes', 'no'];
const p = parseAi($('Step 4: AI call').first().json, ['complaint', 'safety', 'legal'], { complaint: yn, safety: yn, legal: yn });
const base = $('Step 3: Rule: keyword or near-empty attachment?').first().json.rules;
if (!p.ok) return [{ json: { escalate: true, fired: `AI output failed the check (${p.problem})`, rules: Object.assign({}, base, { ai: p.problem }) } }];
const ai = { complaint: p.value.complaint, safety: p.value.safety, legal: p.value.legal };
const yes = Object.keys(ai).filter(k => ai[k] === 'yes');
return [{ json: { escalate: yes.length > 0, fired: yes.length ? `AI: ${yes.join(', ')}` : '', rules: Object.assign({}, base, { ai }) } }];
"""

AI_ERROR_JS = r"""
// Step 4: an AI error escalates; it never routes (Figure 4.2).
const base = $('Step 3: Rule: keyword or near-empty attachment?').first().json.rules;
const detail = String(($json.error && $json.error.message) || 'AI call failed');
return [{ json: { escalate: true, fired: 'AI error', detail, rules: Object.assign({}, base, { ai: 'error' }) } }];
"""

OWNER_JS = r"""
// Step 5: pick the owner on duty when the message arrived; opening hours and out of hours each name an owner and a backup.
const cfg = $('Config').first().json;
const t = $('Read the message').first().json;
const ev = $('Step 1: New message').first().json.body;
const at = new Date(t.received_at || Date.now());
const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: cfg.timezone, weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
  .formatToParts(at).map(p => [p.type, p.value]));
const hhmm = `${parts.hour}:${parts.minute}`;
const open = cfg.opening_hours.days.includes(parts.weekday) && hhmm >= cfg.opening_hours.start && hhmm < cfg.opening_hours.end;
const rota = open ? 'in_hours' : 'out_of_hours';
const person = cfg[rota].owner;
const fired = $input.first().json.fired;
return [{ json: { ticket_id: ev.ticket_id, message_id: ev.message_id, level: 'owner', rota, person, limit_min: cfg[rota].limit_min,
  fired, notified: [person.helpdesk_user], rules: $input.first().json.rules } }];
"""

NOTICE_JS = r"""
// The notice to send: the owner from step 5, or the next person from the step 6 clock check.
if ($('Step 1: New message').isExecuted) return $('Step 5: Rule: who to notify').all().map(i => ({ json: i.json }));
return $input.all().map(i => ({ json: i.json }));
"""

CLOCK_JS = r"""
// Step 6: the person notified taking the ticket stops the clock; a passed limit notifies the next person on a fresh clock.
const cfg = $('Config').first().json;
const clocks = $('Any clock running?').all();
const out = [];
$input.all().forEach((it, i) => {
  const c = clocks[i].json;
  const r = c.rules;
  const t = it.json;
  if (t.assignee && (r.notified || []).includes(t.assignee)) {
    out.push({ json: { action: 'ack', ticket_id: c.item, by: t.assignee, level: r.level, minutes: Math.round(Number(c.minutes)), message_id: r.message_id }, pairedItem: { item: i } });
    return;
  }
  if (Number(c.minutes) < Number(r.limit_min)) return;
  const next = r.level === 'owner' ? { level: 'backup', person: cfg[r.rota].backup } : { level: 'final', person: cfg.final_contact };
  out.push({ json: { action: 'notify', ticket_id: c.item, message_id: r.message_id, level: next.level, rota: r.rota, person: next.person,
    limit_min: cfg[r.rota].limit_min, fired: `${r.level} did not take the ticket within ${r.limit_min} minutes`,
    notified: (r.notified || []).concat([next.person.helpdesk_user]), rules: {} }, pairedItem: { item: i } });
});
return out;
"""

RUNNING_SQL = (
    "SELECT item, rules, extract(epoch FROM now() - decided_at) / 60 AS minutes FROM ("
    "SELECT DISTINCT ON (item) item, rules, decided_at FROM decision_log "
    "WHERE recipe = $1 AND rules ? 'clock' ORDER BY item, id DESC) latest "
    "WHERE rules->>'clock' = 'running'"
)


def build() -> Workflow:
    w = Workflow("R4.2", "R4.2 Escalate complaints, safety issues and legal threats")
    w.webhook(T, "r4-2-new-message",
              "Your helpdesk calls this for each new message, directly, so R4.1 being off never stops escalation. Body: {ticket_id, message_id}.",
              pos=[0, 0])
    w.node(CLOCK, "n8n-nodes-base.scheduleTrigger", V["schedule"],
           {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}}, pos=[0, 900],
           notes="The clock (step 6): checks every running escalation against its acknowledgment limit.")
    w.config("Config", {
        "helpdesk_url": "https://<your helpdesk API>",
        "phone_url": "https://<your text and call service API>",
        "ticket_link": "https://<your helpdesk>/tickets/",
        "keywords": ["<your safety and legal keywords>"],
        "min_text_chars": 20,
        "escalation_priority": "<your highest priority>",
        "timezone": "<your time zone, such as Europe/London>",
        "opening_hours": {"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "start": "<HH:MM>", "end": "<HH:MM>"},
        "in_hours": {"owner": {"name": "<your owner in opening hours>", "phone": "<their phone>", "helpdesk_user": "<their helpdesk user>"},
                     "backup": {"name": "<your backup in opening hours>", "phone": "<their phone>", "helpdesk_user": "<their helpdesk user>"},
                     "limit_min": 15},
        "out_of_hours": {"owner": {"name": "<your on-call phone holder>", "phone": "<your on-call phone>", "helpdesk_user": "<their helpdesk user>"},
                         "backup": {"name": "<your out-of-hours backup>", "phone": "<their phone>", "helpdesk_user": "<their helpdesk user>"},
                         "limit_min": 30},
        "final_contact": {"name": "<your workflow owner>", "phone": "<their phone>", "helpdesk_user": "<their helpdesk user>"},
        "triage_lead": "<your triage lead>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 450])
    w.connect(T, "Config")
    w.connect(CLOCK, "Config")
    w.if_("Clock check?", f"={{{{ $('{CLOCK}').isExecuted }}}}", pos=[520, 450])
    w.connect("Config", "Clock check?")

    # ---- a new message: steps 2 to 5 -------------------------------------------
    w.http("Read the message", "GET", f"={{{{ {CFG}.helpdesk_url }}}}/tickets/{{{{ {EV}.ticket_id }}}}",
           write=False, error_output=False, pos=[780, 0])
    w.connect("Clock check?", "Read the message", output=1)
    w.reserve_key("Step 2: Reserve key", KEY, pos=[1040, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1300, 0],
          notes="The key is ticket plus message, so a new message on an escalated ticket is rechecked.")
    w.noop("Duplicate: stop", pos=[1560, -200], notes="This message was checked before.")
    w.chain("Read the message", "Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    w.code("Step 3: Rule: keyword or near-empty attachment?", KEYWORD_JS, mode="runOnceForAllItems", pos=[1560, 0])
    w.if_("Escalate at once?", "={{ $json.fired }}", op="notEmpty", pos=[1820, 0])
    w.connect("New key?", "Step 3: Rule: keyword or near-empty attachment?", output=0)
    w.connect("Step 3: Rule: keyword or near-empty attachment?", "Escalate at once?")

    msg = "$('Read the message').item.json"
    build, call = ai_step(w, "Step 4", ROOT / "recipes/R4.2/prompts/rate-risk.md",
                          f"{{ subject: {msg}.subject, body: {msg}.body }}",
                          max_tokens=100, tries=1, pos_build=[2080, 160], pos_call=[2340, 160])
    w.connect("Escalate at once?", build, output=1)
    w.code("Step 4: Rule: all three no?", RATE_JS, mode="runOnceForAllItems", pos=[2600, 160],
           notes="The rule decides, not the AI: any yes, other value or error escalates.")
    w.connect(call, "Step 4: Rule: all three no?", output=0)
    w.code("Step 4: AI error", AI_ERROR_JS, mode="runOnceForAllItems", pos=[2600, 360])
    w.connect(call, "Step 4: AI error", output=1)
    w.exception("Exception queue: classifier unavailable", f"{EV}.ticket_id", "classifier unavailable",
                "'AI error; the message escalated anyway: ' + $json.detail", f"{CFG}.triage_lead", pos=[2860, 560])
    w.connect("Step 4: AI error", "Exception queue: classifier unavailable")
    w.if_("Escalate?", "={{ $json.escalate }}", pos=[2860, 160])
    w.connect("Step 4: Rule: all three no?", "Escalate?")
    w.connect("Step 4: AI error", "Escalate?")

    w.finish_key("Mark key done: stays in its queue", KEY, "done", "'no escalation'", pos=[3120, 360])
    w.decision_log("Decision log: no escalation", f"{EV}.ticket_id", "'no escalation'",
                   f"JSON.stringify(Object.assign({{ message_id: {EV}.message_id }}, $('Escalate?').item.json.rules))", pos=[3380, 360])
    w.connect("Escalate?", "Mark key done: stays in its queue", output=1)
    w.connect("Mark key done: stays in its queue", "Decision log: no escalation")

    w.code("Step 5: Rule: who to notify", OWNER_JS, mode="runOnceForAllItems", pos=[3120, 0])
    w.connect("Escalate at once?", "Step 5: Rule: who to notify", output=0)
    w.connect("Escalate?", "Step 5: Rule: who to notify", output=0)
    w.http("Step 5: Raise the priority", "PATCH", f"={{{{ {CFG}.helpdesk_url }}}}/tickets/{{{{ {EV}.ticket_id }}}}",
           body=f"={{{{ JSON.stringify({{ priority: {CFG}.escalation_priority }}) }}}}", write=True, pos=[3380, 0])
    w.connect("Step 5: Rule: who to notify", "Step 5: Raise the priority")
    w.finish_key("Mark key done", KEY, "done", "'escalated'", pos=[3640, 0])
    w.connect("Step 5: Raise the priority", "Mark key done")
    w.finish_key("Mark key failed", KEY, "failed", "'priority write failed'", pos=[3640, 200])
    w.exception("Exception queue: priority write failed", f"{EV}.ticket_id", "write failed",
                "'Priority write failed, never retried; the notices still go out'", f"{CFG}.triage_lead", pos=[3900, 200])
    w.connect("Step 5: Raise the priority", "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: priority write failed")

    # ---- the notice: steps 5 and 6 share it ------------------------------------
    w.code("Notice to send", NOTICE_JS, mode="runOnceForAllItems", pos=[4160, 0])
    w.connect("Mark key done", "Notice to send")
    w.connect("Exception queue: priority write failed", "Notice to send")
    n = "$('Notice to send').item.json"
    phone = f"{CFG}.phone_url"
    w.http("Step 5 and 6: Text the person", "POST", f"={{{{ {phone} }}}}/texts",
           body=f"={{{{ JSON.stringify({{ to: {n}.person.phone, text: 'Escalated ticket: ' + {CFG}.ticket_link + {n}.ticket_id }}) }}}}",
           write=False, pos=[4420, 0], notes="Retry On Fail on the notice steps only (book, n8n note). The text carries only a link.")
    w.exception("Exception queue: text failed", f"{n}.ticket_id", "notice failed",
                f"'Text to ' + {n}.person.name + ' failed after three tries'", f"{CFG}.triage_lead", pos=[4680, 200])
    w.http("Step 5 and 6: Call the person", "POST", f"={{{{ {phone} }}}}/calls",
           body=f"={{{{ JSON.stringify({{ to: {n}.person.phone, say: 'An escalated ticket needs you now. The link is in your texts.' }}) }}}}",
           write=False, pos=[4940, 0], notes="Retry On Fail on the notice steps only (book, n8n note). The call carries no content.")
    w.exception("Exception queue: call failed", f"{n}.ticket_id", "notice failed",
                f"'Call to ' + {n}.person.name + ' failed after three tries'", f"{CFG}.triage_lead", pos=[5200, 200])
    w.decision_log("Step 5 and 6: Log the notice; start the clock", f"{n}.ticket_id",
                   f"'escalated: ' + {n}.level + ' notified'",
                   f"JSON.stringify(Object.assign({{}}, {n}.rules, {{ message_id: {n}.message_id, fired: {n}.fired, level: {n}.level, "
                   f"person: {n}.person.name, rota: {n}.rota, limit_min: {n}.limit_min, notified: {n}.notified, "
                   f"clock: {n}.level === 'final' ? 'ended' : 'running' }}))",
                   pos=[5460, 0])
    w.chain("Notice to send", "Step 5 and 6: Text the person", "Step 5 and 6: Call the person",
            "Step 5 and 6: Log the notice; start the clock")
    w.connect("Step 5 and 6: Text the person", "Exception queue: text failed", output=1)
    w.connect("Exception queue: text failed", "Step 5 and 6: Call the person")
    w.connect("Step 5 and 6: Call the person", "Exception queue: call failed", output=1)
    w.connect("Exception queue: call failed", "Step 5 and 6: Log the notice; start the clock")

    # ---- the clock: step 6 -------------------------------------------------------
    w.pg("Read running clocks", RUNNING_SQL, args=['"R4.2"'], pos=[780, 900],
         notes="The latest notice per ticket whose clock is still running (decision log).")
    w.connect("Clock check?", "Read running clocks", output=0)
    w.if_("Any clock running?", "={{ $json.item }}", op="notEmpty", pos=[1040, 900])
    w.connect("Read running clocks", "Any clock running?")
    w.http("Read the ticket's assignee", "GET", f"={{{{ {CFG}.helpdesk_url }}}}/tickets/{{{{ $json.item }}}}",
           write=False, error_output=False, pos=[1300, 900])
    w.connect("Any clock running?", "Read the ticket's assignee", output=0)
    w.code("Step 6: Rule: taken or late?", CLOCK_JS, mode="runOnceForAllItems", pos=[1560, 900],
           notes="Only the person notified taking the ticket stops the clock.")
    w.connect("Read the ticket's assignee", "Step 6: Rule: taken or late?")
    w.switch("Taken or late", "={{ $json.action }}", ["ack", "notify"], pos=[1820, 900])
    w.connect("Step 6: Rule: taken or late?", "Taken or late")
    w.decision_log("Step 6: Log the acknowledgment; stop the clock", "$json.ticket_id", "'acknowledged by ' + $json.by",
                   "JSON.stringify({ message_id: $json.message_id, level: $json.level, by: $json.by, minutes: $json.minutes, clock: 'stopped' })",
                   pos=[2080, 800])
    w.connect("Taken or late", "Step 6: Log the acknowledgment; stop the clock", output=0)
    w.connect("Taken or late", "Notice to send", output=1)
    return w
