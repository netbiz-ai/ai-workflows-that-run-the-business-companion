"""R5.1 Capture inquiries from web, email and phone notes into one lead record.

Source: book Chapter 5, recipe R5.1, build steps 1 to 6 (recipes/R5.1/build-spec.md);
AI step: recipes/R5.1/prompts/extract-inquiry.md (emails and phone notes only).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

FORM = "Step 1: Web form"
EMAIL = "Step 1: Inquiry email"
NOTE = "Step 1: Phone note"
SRC = "Step 1: Channel and source ID"
S = f"$('{SRC}').first().json"
KEY = f"{S}.channel + ':' + {S}.source_id"
R4 = "Step 4: Rule: complete trade inquiry?"
R5 = "Step 5: Rule: how many CRM matches?"

SOURCE_JS = r"""
// Step 1: one shape for all three channels; the duplicate key is the channel's own ID (step 2).
const pick = n => { try { return $(n).isExecuted ? $(n).first().json.body || {} : null; } catch (e) { return null; } };
const form = pick('Step 1: Web form'), email = pick('Step 1: Inquiry email'), note = pick('Step 1: Phone note');
if (form) return [{ json: { channel: 'web form', source_id: String(form.submission_id), form } }];
if (email) return [{ json: { channel: 'email', source_id: String(email.message_id) } }];
return [{ json: { channel: 'phone note', source_id: String(note.note_id) } }];
"""

RULE4_JS = AI_PARSE_JS + r"""
// Step 4: name or company, one contact route and the need present; email well-formed;
// phone digits only; label one of the two. Web forms skip the AI step (step 3).
const src = $('Step 1: Channel and source ID').first().json;
const FIELDS = ['name', 'company', 'email', 'phone', 'need', 'label'];
let f;
if (src.channel === 'web form') {
  const b = src.form;
  // A form is a trade inquiry by design; its phone field is free text, so drop the
  // same separators the AI step is told to drop before the digits-only rule.
  f = { name: b.name || '', company: b.company || '', email: b.email || '', need: b.need || '',
        phone: String(b.phone || '').replace(/[\s\-().+]/g, ''), label: 'trade inquiry' };
} else {
  const p = parseAi($('Step 3: AI call').first().json, FIELDS, { label: ['trade inquiry', 'not an inquiry'] });
  if (!p.ok) return [{ json: { route: 'exception', detail: 'AI output failed the check: ' + p.problem, rules: { ai: 'failed the check' } } }];
  f = p.value;
  const bad = FIELDS.filter(k => typeof f[k] !== 'string');
  if (bad.length) return [{ json: { route: 'exception', detail: 'AI output failed the check: not text: ' + bad.join(', '), rules: { ai: 'failed the check' } } }];
}
f = Object.fromEntries(FIELDS.map(k => [k, String(f[k]).trim()]));
const emailOk = !f.email || /^[^\s@<>(),;:]+@[^\s@<>(),;:]+\.[A-Za-z]{2,}$/.test(f.email);
const phoneOk = !f.phone || /^\d+$/.test(f.phone);
const rules = { label: f.label, who: !!(f.name || f.company), contact: !!(f.email || f.phone), need: !!f.need, email_ok: emailOk, phone_ok: phoneOk };
if (f.label === 'not an inquiry') return [{ json: { route: 'not inquiry', fields: f, rules } }];
const missing = [];
if (!rules.who) missing.push('name or company');
if (!rules.contact) missing.push('email or phone');
if (!rules.need) missing.push('need');
if (!emailOk) missing.push('well-formed email');
if (!phoneOk) missing.push('digits-only phone');
if (missing.length) return [{ json: { route: 'exception', detail: 'Missing or malformed: ' + missing.join(', '), rules } }];
return [{ json: { route: 'search', fields: f, rules } }];
"""

RULE5_JS = r"""
// Step 5: email first, then phone, then company. One match: activity; none: new lead;
// several, or a company-name match alone: Ben chooses. A "not an inquiry" from a
// sender the CRM does not know goes to the shared inbox (step 4).
const r4 = $('Step 4: Rule: complete trade inquiry?').first().json;
const f = r4.fields;
const byEmail = f.email ? ($('Step 5: Search CRM by email').first().json.items || []) : [];
const byPhone = f.phone ? ($('Step 5: Search CRM by phone').first().json.items || []) : [];
const byCompany = f.company ? ($('Step 5: Search CRM by company').first().json.items || []) : [];
const rules = Object.assign({}, r4.rules, { email_matches: byEmail.length, phone_matches: byPhone.length, company_matches: byCompany.length });
if (r4.route === 'not inquiry') {
  const known = byEmail.length + byPhone.length > 0;
  return [{ json: { action: known ? 'known contact' : 'shared inbox', match: known ? 'known sender' : 'unknown sender', rules } }];
}
const first = byEmail.length ? ['email', byEmail] : byPhone.length ? ['phone', byPhone] : byCompany.length ? ['company', byCompany] : ['none', []];
const [on, hits] = first;
if (on === 'none') return [{ json: { action: 'create', match: 'none', rules } }];
if (hits.length === 1 && on !== 'company') return [{ json: { action: 'activity', match: 'one by ' + on, lead_id: hits[0].id, rules } }];
const why = on === 'company' ? 'company-name match only' : `${hits.length} records match the ${on}`;
return [{ json: { action: 'ben', match: why, candidates: hits.map(h => h.id), rules } }];
"""

SUMMARY_JS = r"""
// Step 6: what the run did, for the decision log: IDs and the match, never the body.
const ran = n => { try { return $(n).isExecuted; } catch (e) { return false; } };
const r4 = ran('Step 4: Rule: complete trade inquiry?') ? $('Step 4: Rule: complete trade inquiry?').first().json : null;
const r5 = ran('Step 5: Rule: how many CRM matches?') ? $('Step 5: Rule: how many CRM matches?').first().json : null;
const src = $('Step 1: Channel and source ID').first().json;
let decision, lead = null;
if (ran('Step 4: AI error')) decision = 'exception queue: AI error after one retry';
else if (r5 && r5.action === 'create') { decision = 'new lead'; lead = $('Step 5: Create stamped lead').first().json.id; }
else if (r5 && r5.action === 'activity') { decision = 'activity on existing lead'; lead = r5.lead_id; }
else if (r5 && r5.action === 'ben') decision = 'queued for the match reviewer';
else if (r5 && r5.action === 'shared inbox') decision = 'not an inquiry: shared inbox';
else if (r5 && r5.action === 'known contact') decision = 'not an inquiry from a known contact: exception queue';
else decision = 'exception queue: incomplete';
const rules = Object.assign({ channel: src.channel, source_id: src.source_id, match: r5 ? r5.match : null, lead_id: lead },
  (r5 || r4 || {}).rules || {});
return [{ json: { decision, rules } }];
"""


def build() -> Workflow:
    w = Workflow("R5.1", "R5.1 Capture inquiries into one lead record")
    w.webhook(FORM, "r5-1-web-form", "Your form tool calls this for each submission. Body: {submission_id, name, company, email, phone, need}.", pos=[0, -200])
    w.webhook(EMAIL, "r5-1-inquiry-email", "Your inquiry mailbox calls this for each new message. Body: {message_id}.", pos=[0, 0])
    w.webhook(NOTE, "r5-1-phone-note", "Your phone-note form calls this for each saved note. Body: {note_id}.", pos=[0, 200])
    w.config("Config", {
        "crm_url": "https://<your CRM API>",
        "mailbox_url": "https://<your inquiry mailbox API>",
        "notes_url": "https://<your phone-note form API>",
        "messaging_url": "https://<your messaging API>",
        "new_lead_status": "new, unassigned",
        "shared_inbox": "<your shared inbox>",
        "queue_checker": "<your exception queue checker>",
        "match_reviewer": "<your sales lead>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 0])
    for t in (FORM, EMAIL, NOTE):
        w.connect(t, "Config")
    w.code(SRC, SOURCE_JS, mode="runOnceForAllItems", pos=[520, 0])
    w.reserve_key("Step 2: Reserve key", KEY, pos=[780, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1040, 0])
    w.noop("Duplicate: stop", pos=[1300, -240], notes="Key already logged (copy counted): this source was captured before.")
    w.chain("Config", SRC, "Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    w.switch("Channel", f"={{{{ {S}.channel }}}}", ["web form", "email", "phone note"], pos=[1300, 0])
    w.connect("New key?", "Channel", output=0)
    w.http("Read the email", "GET", f"={{{{ $('Config').first().json.mailbox_url }}}}/messages/{{{{ {S}.source_id }}}}",
           write=False, error_output=False, pos=[1560, 0])
    w.http("Read the phone note", "GET", f"={{{{ $('Config').first().json.notes_url }}}}/notes/{{{{ {S}.source_id }}}}",
           write=False, error_output=False, pos=[1560, 200])
    w.connect("Channel", "Read the email", output=1)
    w.connect("Channel", "Read the phone note", output=2)

    vars_js = ("{ channel: $('Step 1: Channel and source ID').first().json.channel, sender: $json.from || '', "
               "subject: $json.subject || '', text: $json.body || $json.text || '' }")
    build, call = ai_step(w, "Step 3", ROOT / "recipes/R5.1/prompts/extract-inquiry.md", vars_js,
                          max_tokens=400, tries=2, pos_build=[1820, 100], pos_call=[2080, 100])
    w.connect("Read the email", build)
    w.connect("Read the phone note", build)

    w.code(R4, RULE4_JS, mode="runOnceForAllItems", pos=[2340, -100], notes="The rule decides, not the AI.")
    w.connect("Channel", R4, output=0)
    w.connect(call, R4, output=0)
    w.code("Step 4: AI error", "return [{ json: { route: 'exception', detail: 'AI error after one retry: ' + String(($json.error && $json.error.message) || ''), rules: { ai: 'error' } } }];",
           mode="runOnceForAllItems", pos=[2340, 200])
    w.connect(call, "Step 4: AI error", output=1)
    w.switch("Step 4: Route", "={{ $json.route }}", ["search", "not inquiry", "exception"], pos=[2600, 0])
    w.connect(R4, "Step 4: Route")
    w.connect("Step 4: AI error", "Step 4: Route")

    f = f"$('{R4}').first().json.fields"
    crm = "$('Config').first().json.crm_url"
    w.http("Step 5: Search CRM by email", "GET", f"={{{{ {crm} }}}}/leads", query={"_wrap": "1", "email": f"={{{{ {f}.email }}}}"},
           write=False, error_output=False, pos=[2860, -100])
    w.http("Step 5: Search CRM by phone", "GET", f"={{{{ {crm} }}}}/leads", query={"_wrap": "1", "phone": f"={{{{ {f}.phone }}}}"},
           write=False, error_output=False, pos=[3120, -100])
    w.http("Step 5: Search CRM by company", "GET", f"={{{{ {crm} }}}}/leads", query={"_wrap": "1", "company": f"={{{{ {f}.company }}}}"},
           write=False, error_output=False, pos=[3380, -100])
    w.code(R5, RULE5_JS, mode="runOnceForAllItems", pos=[3640, -100])
    w.connect("Step 4: Route", "Step 5: Search CRM by email", output=0)
    w.connect("Step 4: Route", "Step 5: Search CRM by email", output=1)
    w.chain("Step 5: Search CRM by email", "Step 5: Search CRM by phone", "Step 5: Search CRM by company", R5)

    src = f"{S}.source_id"
    w.exception("Exception queue: incomplete inquiry", f"{S}.channel + ':' + {src}", "incomplete inquiry",
                "$json.detail", "$('Config').first().json.queue_checker", pos=[2860, 300])
    w.connect("Step 4: Route", "Exception queue: incomplete inquiry", output=2)

    w.switch("Step 5: Match", "={{ $json.action }}", ["activity", "create", "ben", "shared inbox", "known contact"], pos=[3900, -100])
    w.connect(R5, "Step 5: Match")
    r5 = f"$('{R5}').first().json"
    w.http("Step 5: Add stamped activity", "POST", f"={{{{ {crm} }}}}/activities",
           body=f"={{{{ JSON.stringify({{ lead_id: {r5}.lead_id, source_id: {src}, channel: {S}.channel, need: {f}.need }}) }}}}",
           write=True, pos=[4160, -400])
    w.http("Step 5: Create stamped lead", "POST", f"={{{{ {crm} }}}}/leads",
           body=f"={{{{ JSON.stringify({{ name: {f}.name, company: {f}.company, email: {f}.email, phone: {f}.phone, need: {f}.need, source_id: {src}, channel: {S}.channel }}) }}}}",
           write=True, pos=[4160, -240])
    w.exception("Exception queue: Ben chooses the record", f"{S}.channel + ':' + {src}", "CRM match unclear",
                f"{r5}.match + ': ' + ({r5}.candidates || []).join(', ')", "$('Config').first().json.match_reviewer", pos=[4160, -80])
    w.http("Step 4: Send to the shared inbox", "POST", "={{ $('Config').first().json.messaging_url }}/messages",
           body=f"={{{{ JSON.stringify({{ to: $('Config').first().json.shared_inbox, subject: 'Not an inquiry: ' + {S}.channel + ' ' + {src}, source_id: {src}, channel: {S}.channel }}) }}}}",
           write=True, pos=[4160, 80])
    w.exception("Exception queue: not an inquiry, known contact", f"{S}.channel + ':' + {src}", "not an inquiry from a known contact",
                f"{r5}.match", "$('Config').first().json.queue_checker", pos=[4160, 240])
    for i, n in enumerate(["Step 5: Add stamped activity", "Step 5: Create stamped lead", "Exception queue: Ben chooses the record",
                           "Step 4: Send to the shared inbox", "Exception queue: not an inquiry, known contact"]):
        w.connect("Step 5: Match", n, output=i)

    created = "$('Step 5: Create stamped lead')"
    lead_expr = f"({created}.isExecuted ? {created}.first().json.id : {r5}.lead_id)"
    source_expr = (f"({S}.channel === 'web form' ? {S}.form : {S}.channel === 'email' ? $('Read the email').first().json "
                   f": $('Read the phone note').first().json)")
    w.http("Step 6: Attach the source", "POST", f"={{{{ {crm} }}}}/attachments",
           body=f"={{{{ JSON.stringify({{ record_id: {lead_expr}, source_id: {src}, channel: {S}.channel, source: {source_expr} }}) }}}}",
           write=True, pos=[4420, -320])
    w.connect("Step 5: Add stamped activity", "Step 6: Attach the source")
    w.connect("Step 5: Create stamped lead", "Step 6: Attach the source")
    w.if_("New lead?", f"={{{{ {created}.isExecuted }}}}", pos=[4680, -320])
    w.connect("Step 6: Attach the source", "New lead?")
    w.http("Step 6: Set new, unassigned", "PATCH", f"={{{{ {crm} }}}}/leads/{{{{ {created}.first().json.id }}}}",
           body="={{ JSON.stringify({ status: $('Config').first().json.new_lead_status }) }}", write=True, pos=[4940, -400])
    w.connect("New lead?", "Step 6: Set new, unassigned", output=0)

    w.code("Run summary", SUMMARY_JS, mode="runOnceForAllItems", pos=[5200, -100])
    for n in ["Step 6: Set new, unassigned", "Exception queue: Ben chooses the record", "Step 4: Send to the shared inbox",
              "Exception queue: not an inquiry, known contact", "Exception queue: incomplete inquiry"]:
        w.connect(n, "Run summary")
    w.connect("New lead?", "Run summary", output=1)
    w.finish_key("Mark key done", KEY, "done", "$json.decision", pos=[5460, -100])
    w.decision_log("Step 6: Decision log", f"{S}.channel + ':' + {src}", "$('Run summary').first().json.decision",
                   "JSON.stringify($('Run summary').first().json.rules)", pos=[5720, -100])
    w.chain("Run summary", "Mark key done", "Step 6: Decision log")

    w.finish_key("Mark key failed", KEY, "failed", "'write failed: ' + (($json.error && $json.error.message) || 'unknown')", pos=[5200, 400])
    w.exception("Exception queue: write failed", f"{S}.channel + ':' + {src}", "write failed",
                "'CRM write failed, not retried; check the CRM, then release or close the key'",
                "$('Config').first().json.match_reviewer", pos=[5460, 400])
    for n in ["Step 5: Add stamped activity", "Step 5: Create stamped lead", "Step 4: Send to the shared inbox",
              "Step 6: Attach the source", "Step 6: Set new, unassigned"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")
    return w
