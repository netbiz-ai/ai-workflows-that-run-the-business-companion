"""R8.3 Take in a dispute and brief the account owner.

Source: book Chapter 8, recipe R8.3, build steps 1 to 11 and Table 8.2 (recipes/R8.3/build-spec.md);
AI step: recipes/R8.3/prompts/extract-reply.md.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, V, Workflow, ai_step  # noqa: E402

T = "Step 1: New message in the AR mailbox"
MC = "Step 1: Morning mailbox check"
CF = "Step 9: Owner confirms the invoices"
EV = f"$('{T}').item.json.body"
CB = f"$('{CF}').item.json.body"
CFG = "$('Config').first().json"
MSG = "$('Read the message').item.json"
MATCH = "$('Step 2: Rule: match the account').item.json"
R6 = "$('Step 6: Rule: legal threat or safety?').item.json"
OUT = "$('Outcome for the logs').item.json"
NAR = "$('Step 9: Rule: briefed, paused, invoices named?').item.json"
PAUSE_ID = f"'pause-' + {EV}.message_id"

OUTSIDE_JS = r"""
// Step 1: only outside messages, and never automatic replies.
const cfg = $('Config').first().json;
const m = $('Read the message').first().json;
const h = Object.fromEntries(Object.entries(m.headers || {}).map(([k, v]) => [k.toLowerCase(), String(v).toLowerCase()]));
const from = String(m.from || '').toLowerCase().trim();
const auto = ['auto-replied', 'auto-generated'].includes(h['auto-submitted'])
  || ['bulk', 'list', 'junk', 'auto_reply'].includes(h['precedence'])
  || 'x-autoreply' in h || 'x-autorespond' in h;
const inside = (cfg.own_domains || []).some(d => from.endsWith('@' + String(d).toLowerCase().replace(/^@/, '')));
return [{ json: { outside: !!from && !auto && !inside, automatic: auto, inside } }];
"""

MATCH_JS = r"""
// Step 2: the sender to a CRM account; failing that, an invoice number to the export, then the domain to the CRM.
const cfg = $('Config').first().json;
const m = $('Read the message').first().json;
const accounts = $('Step 2: Read CRM accounts').first().json.items || [];
const rows = $("Step 2: Read today's export").first().json.rows || [];
const from = String(m.from || '').toLowerCase().trim();
const email = a => String(a.contact_email || '').toLowerCase();
let acc = accounts.find(a => email(a) === from || (a.contacts || []).map(c => String(c).toLowerCase()).includes(from));
let how = acc ? 'sender' : null;
if (!acc) {
  let re;
  try { re = new RegExp(cfg.invoice_number_pattern, 'g'); } catch (e) { re = null; }
  const found = re ? [...new Set((String(m.subject || '') + '\n' + String(m.body || '')).match(re) || [])] : [];
  const ids = [...new Set(rows.filter(r => found.includes(String(r.invoice))).map(r => String(r.account)))];
  if (ids.length === 1) { acc = accounts.find(a => String(a.id) === ids[0]) || { id: ids[0] }; how = 'invoice number'; }
}
if (!acc) {
  const domain = from.split('@')[1] || '';
  const hits = domain ? accounts.filter(a => email(a).endsWith('@' + domain)) : [];
  if (hits.length === 1) { acc = hits[0]; how = 'domain'; }
}
if (!acc) return [{ json: { matched: false } }];
return [{ json: { matched: true, how, account: String(acc.id), account_name: acc.name || String(acc.id), owner: acc.owner || '' } }];
"""

CHECK_JS = AI_PARSE_JS + r"""
// Step 5: the category is listed, each invoice is open on this account, and no amount exceeds its invoice.
const cfg = $('Config').first().json;
const a = $('Step 2: Rule: match the account').first().json;
const rows = $("Step 2: Read today's export").first().json.rows || [];
const FIELDS = ['category', 'promise_date', 'invoice_numbers', 'amounts_questioned', 'summary'];
const CATS = ['dispute', 'says paid', 'promise to pay', 'question', 'other'];
const fail = problem => [{ json: { check_ok: false, problem } }];
const p = parseAi($('Step 4: AI call').first().json, FIELDS, { category: CATS });
if (!p.ok) return fail('AI output failed the check: ' + p.problem);
const v = p.value;
const extra = Object.keys(v).filter(k => !FIELDS.includes(k));
if (extra.length) return fail('AI output failed the check: unexpected field ' + extra[0]);
if (v.promise_date !== null && !(typeof v.promise_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v.promise_date))) return fail('AI output failed the check: promise_date');
if (!Array.isArray(v.invoice_numbers) || v.invoice_numbers.some(x => typeof x !== 'string')) return fail('AI output failed the check: invoice_numbers');
if (!Array.isArray(v.amounts_questioned) || v.amounts_questioned.some(q => !q || typeof q !== 'object'
    || typeof q.invoice_number !== 'string' || typeof q.amount !== 'number' || !(q.amount > 0)
    || Object.keys(q).some(k => !['invoice_number', 'amount'].includes(k)))) return fail('AI output failed the check: amounts_questioned');
if (typeof v.summary !== 'string' || v.summary.trim().split(/\s+/).filter(Boolean).length > cfg.summary_max_words) return fail('AI output failed the check: summary');
const open = Object.fromEntries(rows.filter(r => String(r.account) === a.account && Number(r.open_amount) > 0).map(r => [String(r.invoice), r]));
const named = [...new Set([...v.invoice_numbers, ...v.amounts_questioned.map(q => q.invoice_number)])];
const notOpen = named.filter(n => !open[n]);
if (notOpen.length) return fail('invoice not open on this account: ' + notOpen.join(', '));
const over = v.amounts_questioned.filter(q => q.amount > Number(open[q.invoice_number].amount));
if (over.length) return fail('amount questioned exceeds its invoice: ' + over.map(q => q.invoice_number).join(', '));
return [{ json: { check_ok: true, category: v.category, promise_date: v.promise_date, invoices: named,
  brief_invoices: named.length ? named : Object.keys(open), amounts_questioned: v.amounts_questioned, summary: v.summary } }];
"""

ESCALATE_JS = r"""
// Step 6: R4.2's keyword rule for legal threats and safety, on the message itself, whatever the AI returned.
const cfg = $('Config').first().json;
const m = $('Read the message').first().json;
const c = $input.first().json;
const text = (String(m.subject || '') + '\n' + String(m.body || '')).toLowerCase();
const keywords = (cfg.escalation_keywords || []).filter(k => k && text.includes(String(k).toLowerCase()));
const route = keywords.length ? 'escalate' : c.check_ok ? 'brief' : 'queue';
return [{ json: Object.assign({}, c, { keywords, route }) }];
"""

ALREADY_JS = r"""
// Step 7: a message on an invoice already in dispute adds a note to that dispute, not a new dispute.
const r = $('Step 6: Rule: legal threat or safety?').first().json;
const msg = $('Read the message').first().json.id;
const open = ($('Step 7: Read open disputes on the account').first().json.items || [])
  .filter(d => d.invoice && d.id !== 'pause-' + msg);
const hits = open.filter(d => r.invoices.includes(String(d.invoice)));
const already = r.invoices.length > 0 && r.invoices.every(n => hits.some(d => String(d.invoice) === n));
if (!already) return [{ json: { already: false, dispute_ids: [] }, pairedItem: 0 }];
return hits.map(d => ({ json: { already: true, dispute_id: d.id, notes: d.notes || [], dispute_ids: hits.map(x => x.id) }, pairedItem: 0 }));
"""

BRIEF_JS = r"""
// Step 8: amount, due date and reminders sent, from the export and R8.1's key log; the AI output, labeled as AI; a message link.
const cfg = $('Config').first().json;
const m = $('Read the message').first().json;
const a = $('Step 2: Rule: match the account').first().json;
const r = $('Step 6: Rule: legal threat or safety?').first().json;
const rows = $("Step 2: Read today's export").first().json.rows || [];
const sent = String($('Step 8: Read reminders sent (R8.1 key log)').first().json.sent || '').split(', ').filter(Boolean);
const to = r.category === 'says paid' ? [a.owner, cfg.ar_lead] : [a.owner];
const lines = r.brief_invoices.map(n => {
  const row = rows.find(x => String(x.invoice) === n) || {};
  const stages = sent.filter(k => k.split(':')[0] === n).map(k => k.split(':').slice(1).join(':'));
  return `Invoice ${n}: amount ${row.amount}, open ${row.open_amount}, due ${row.due_date}; reminders sent: ${stages.join(', ') || 'none'}`;
});
const text = [
  `Reply from ${m.from} on ${a.account_name} (${a.account}), matched by ${a.how}. The whole account's reminders are paused.`,
  '',
  ...lines,
  '',
  'AI output (labeled as AI; check it against the message before acting):',
  `Category: ${r.category}` + (r.promise_date ? `, promised for ${r.promise_date}` : ''),
  `Amounts questioned: ${r.amounts_questioned.map(q => q.invoice_number + ': ' + q.amount).join(', ') || 'none'}`,
  `Summary: ${r.summary}`,
  '',
  `Message: ${m.web_link || m.id}`,
  'Confirm which invoices this reply covers; only then does the pause narrow. You decide and write any reply; a credit note goes to Aisha.',
].join('\n');
return [{ json: { to, subject: `Reply from ${a.account_name}: ${r.category} (AI)`, text } }];
"""

OUTCOME_JS = r"""
// What the decision log records: the message ID, category, invoices and outcome; never the message.
const E = n => $(n).isExecuted;
const a = $('Step 2: Rule: match the account').first().json;
if (!a.matched) return [{ json: { decision: 'unlinked: no account matched', rules: { match: 'none' } } }];
const r = $('Step 6: Rule: legal threat or safety?').first().json;
const rules = { match: a.how, account: a.account, category: r.category || null, invoices: r.invoices || [],
  check: r.check_ok ? 'passed' : r.problem, escalation: r.keywords };
if (r.route === 'escalate') return [{ json: { decision: 'escalated as R4.2', rules } }];
if (r.route === 'queue') return [{ json: { decision: 'unlinked: fails the check', rules } }];
const n = E('Step 7: Add a note to the open dispute') ? $('Step 7: Rule: already in dispute?').first().json.dispute_ids : [];
rules.brief_to = $('Step 8: Write the brief').first().json.to;
if (n.length) rules.note_added_to = n;
return [{ json: { decision: 'briefed: ' + r.category, rules } }];
"""

NARROW_JS = r"""
// Step 9: only a briefed reply with its whole-account pause still open narrows, to the invoices the owner names.
const b = $('Step 9: Owner confirms the invoices').first().json.body;
const brief = $('Step 9: Read the brief').first().json;
const p = $('Step 9: Read the pause').all(0);
const pause = p.length ? p[0].json : null;
const invoices = Array.isArray(b.invoices) ? b.invoices.map(String).filter(Boolean) : [];
const refuse = reason => [{ json: { refused: true, reason }, pairedItem: 0 }];
if (!brief || !brief.decision) return refuse('no brief for this message');
if (!pause || pause.status !== 'open') return refuse('no open whole-account pause');
if (!invoices.length) return refuse('no invoices confirmed');
return invoices.map(n => ({ json: { refused: false, id: n + '-' + b.message_id, invoice: n, account: pause.account,
  kind: brief.category, message_id: b.message_id, by: b.by || null, until: b.until || null, invoices }, pairedItem: 0 }));
"""


def build() -> Workflow:
    w = Workflow("R8.3", "R8.3 Take in a dispute and brief the account owner")
    w.webhook(T, "r8-3-new-message", "Your AR mailbox calls this for each new message. Body: {message_id}.", pos=[0, 0])
    w.node(MC, "n8n-nodes-base.scheduleTrigger", V["schedule"], {"rule": {"interval": [{"triggerAtHour": 6}]}}, pos=[0, -300],
           notes="Checks the mailbox before R8.1 runs, so a quiet morning still logs a check; a lost connection leaves the status list stale.")
    w.webhook(CF, "r8-3-owner-confirms",
              "The account owner confirms which invoices a briefed reply covers. Body: {message_id, invoices, by, until (for a promise to pay)}.",
              pos=[0, 900])
    w.config("Config", {
        "mail_url": "https://<your AR mailbox API>",
        "sharepoint_url": "https://<your SharePoint lists API>",
        "crm_url": "https://<your CRM API>",
        "messaging_url": "https://<your Teams or messaging API>",
        "ar_lead": "<your AR lead, who works the unlinked queue>",
        "own_domains": ["<your company's email domain>"],
        "invoice_number_pattern": "<your invoice-number pattern, as a regular expression>",
        "escalation_keywords": ["<your R4.2 safety and legal keyword list>"],
        "summary_max_words": 80,
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 0])
    for t in (T, MC, CF):
        w.connect(t, "Config")
    w.if_("Owner confirmation?", f"={{{{ $('{CF}').isExecuted }}}}", pos=[520, 0])
    w.if_("Morning check?", f"={{{{ $('{MC}').isExecuted }}}}", pos=[780, 0])
    w.connect("Config", "Owner confirmation?")
    w.connect("Owner confirmation?", "Morning check?", output=1)

    status_body = "={{ JSON.stringify({ id: 'mailbox-check', last_check: $now.toISO() }) }}"
    status_url = f"={{{{ {CFG}.sharepoint_url }}}}/status/mailbox-check"

    # ---- morning check -----------------------------------------------------------------
    w.http("Step 1: Check the mailbox", "GET", f"={{{{ {CFG}.mail_url }}}}/messages", query={"_wrap": "1"},
           write=False, pos=[1040, -300])
    w.noop("Mailbox access lost: the status list goes stale", pos=[1300, -160],
           notes="R8.1 sends nothing until Owen restores access.")
    w.http("Step 1: Write the check time", "PUT", status_url, body=status_body, write=True, pos=[1300, -300])
    w.exception("Exception queue: status write failed", "'mailbox-check'", "write failed",
                "'The mailbox check time was not written; R8.1 will hold'", f"{CFG}.ar_lead", pos=[1560, -300])
    w.connect("Morning check?", "Step 1: Check the mailbox", output=0)
    w.connect("Step 1: Check the mailbox", "Step 1: Write the check time", output=0)
    w.connect("Step 1: Check the mailbox", "Mailbox access lost: the status list goes stale", output=1)
    w.connect("Step 1: Write the check time", "Exception queue: status write failed", output=1)

    # ---- steps 1 and 2: each message ---------------------------------------------------
    w.http("Read the message", "GET", f"={{{{ {CFG}.mail_url }}}}/messages/{{{{ {EV}.message_id }}}}", write=False, pos=[1040, 0])
    w.connect("Morning check?", "Read the message", output=1)
    w.exception("Exception queue: mailbox error", f"{EV}.message_id", "unlinked item",
                "'Mailbox error after three tries; link it from the AR mailbox'", f"{CFG}.ar_lead", pos=[1300, 160])
    w.connect("Read the message", "Exception queue: mailbox error", output=1)
    w.http("Step 1: Log the check time", "PUT", status_url, body=status_body, write=True, pos=[1300, 0],
           notes="A failed status write does not stop the intake; tomorrow's morning check writes it again.")
    w.connect("Read the message", "Step 1: Log the check time", output=0)
    w.code("Step 1: Rule: outside message, not an automatic reply?", OUTSIDE_JS, mode="runOnceForAllItems", pos=[1560, 0])
    for o in (0, 1):
        w.connect("Step 1: Log the check time", "Step 1: Rule: outside message, not an automatic reply?", output=o)
    w.if_("Outside?", "={{ $json.outside }}", pos=[1820, 0])
    w.noop("Skipped: automatic reply or inside sender", pos=[2080, -160])
    w.connect("Step 1: Rule: outside message, not an automatic reply?", "Outside?")
    w.connect("Outside?", "Skipped: automatic reply or inside sender", output=1)

    w.reserve_key("Step 2: Reserve key", f"{EV}.message_id", pos=[2080, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[2340, 0])
    w.noop("Duplicate: stop", pos=[2600, -160], notes="This message ID is logged: one dispute, one brief.")
    w.connect("Outside?", "Step 2: Reserve key", output=0)
    w.connect("Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)
    w.http("Step 2: Read CRM accounts", "GET", f"={{{{ {CFG}.crm_url }}}}/accounts", query={"_wrap": "1"},
           write=False, error_output=False, pos=[2600, 0])
    w.http("Step 2: Read today's export", "GET", f"={{{{ {CFG}.sharepoint_url }}}}/exports/open-invoices",
           write=False, error_output=False, pos=[2860, 0])
    w.code("Step 2: Rule: match the account", MATCH_JS, mode="runOnceForAllItems", pos=[3120, 0])
    w.connect("New key?", "Step 2: Read CRM accounts", output=0)
    w.chain("Step 2: Read CRM accounts", "Step 2: Read today's export", "Step 2: Rule: match the account")
    w.if_("Matched?", "={{ $json.matched }}", pos=[3380, 0])
    w.connect("Step 2: Rule: match the account", "Matched?")
    w.exception("Exception queue: unmatched", f"{EV}.message_id", "unlinked item",
                "'No account matched the sender, an invoice number or the domain'", f"{CFG}.ar_lead", pos=[3640, 200])
    w.connect("Matched?", "Exception queue: unmatched", output=1)

    # ---- step 3: pause before the AI reads ---------------------------------------------
    w.http("Step 3: Write a whole-account pause", "PUT", f"={{{{ {CFG}.sharepoint_url }}}}/disputes/{{{{ {PAUSE_ID} }}}}",
           body=f"={{{{ JSON.stringify({{ id: {PAUSE_ID}, account: {MATCH}.account, invoice: null, status: 'open', kind: 'reply received', set_by: 'R8.3', why: 'reply received', message_id: {EV}.message_id, paused_at: $now.toISO(), until: null }}) }}}}",
           write=True, pos=[3640, 0], notes="R8.1 stops every reminder on the account until a person narrows or ends the pause.")
    w.connect("Matched?", "Step 3: Write a whole-account pause", output=0)

    # ---- steps 4 to 6 ------------------------------------------------------------------------
    vars_js = f"{{ subject: {MSG}.subject, body: {MSG}.body }}"
    build, call = ai_step(w, "Step 4", ROOT / "recipes/R8.3/prompts/extract-reply.md", vars_js,
                          max_tokens=600, tries=4, pos_build=[3900, 0], pos_call=[4160, 0])
    w.connect("Step 3: Write a whole-account pause", build)
    w.code("Step 5: Rule: check the AI output", CHECK_JS, mode="runOnceForAllItems", pos=[4420, 0],
           notes="The rule decides, not the AI.")
    w.connect(call, "Step 5: Rule: check the AI output", output=0)
    w.code("Step 5: AI error", "return [{ json: { check_ok: false, problem: 'AI error after three retries' } }];",
           mode="runOnceForAllItems", pos=[4420, 200])
    w.connect(call, "Step 5: AI error", output=1)
    w.code("Step 6: Rule: legal threat or safety?", ESCALATE_JS, mode="runOnceForAllItems", pos=[4680, 0])
    w.connect("Step 5: Rule: check the AI output", "Step 6: Rule: legal threat or safety?")
    w.connect("Step 5: AI error", "Step 6: Rule: legal threat or safety?")
    w.switch("Route", "={{ $json.route }}", ["brief", "escalate", "queue"], pos=[4940, 0])
    w.connect("Step 6: Rule: legal threat or safety?", "Route")

    w.http("Step 6: Escalate to Aisha and the owner", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: [{CFG}.ar_lead, {MATCH}.owner], subject: 'Escalated as R4.2: reply from ' + {MATCH}.account_name, text: 'Matched the R4.2 rules (' + {R6}.keywords.join(', ') + '). The whole account stays paused. Message: ' + ({MSG}.web_link || {MSG}.id) }}) }}}}",
           write=True, pos=[5200, 200])
    w.connect("Route", "Step 6: Escalate to Aisha and the owner", output=1)
    w.exception("Exception queue: fails the check", f"{EV}.message_id", "unlinked item",
                f"{R6}.problem", f"{CFG}.ar_lead", pos=[5200, 400])
    w.connect("Route", "Exception queue: fails the check", output=2)

    # ---- steps 7 and 8 -----------------------------------------------------------------------
    w.http("Step 7: Read open disputes on the account", "GET", f"={{{{ {CFG}.sharepoint_url }}}}/disputes",
           query={"_wrap": "1", "status": "open", "account": f"={{{{ {MATCH}.account }}}}"},
           write=False, error_output=False, pos=[5200, -160])
    w.code("Step 7: Rule: already in dispute?", ALREADY_JS, mode="runOnceForAllItems", pos=[5460, -160])
    w.if_("Already in dispute?", "={{ $json.already }}", pos=[5720, -160])
    w.connect("Route", "Step 7: Read open disputes on the account", output=0)
    w.chain("Step 7: Read open disputes on the account", "Step 7: Rule: already in dispute?", "Already in dispute?")
    w.http("Step 7: Add a note to the open dispute", "PATCH",
           f"={{{{ {CFG}.sharepoint_url }}}}/disputes/{{{{ $('Step 7: Rule: already in dispute?').item.json.dispute_id }}}}",
           body=f"={{{{ JSON.stringify({{ notes: $('Step 7: Rule: already in dispute?').item.json.notes.concat([{{ message_id: {EV}.message_id, added: $now.toISO(), ai_category: {R6}.category }}]) }}) }}}}",
           write=True, pos=[5980, -300])
    w.http("Step 7: Log the reply on the pause", "PATCH", f"={{{{ {CFG}.sharepoint_url }}}}/disputes/{{{{ {PAUSE_ID} }}}}",
           body=f"={{{{ JSON.stringify({{ ai_category: {R6}.category, invoices_named: {R6}.invoices }}) }}}}",
           write=True, pos=[5980, -100], notes="Still a whole-account pause until the owner confirms (step 9).")
    w.connect("Already in dispute?", "Step 7: Add a note to the open dispute", output=0)
    w.connect("Already in dispute?", "Step 7: Log the reply on the pause", output=1)
    w.pg("Step 8: Read reminders sent (R8.1 key log)",
         "SELECT coalesce(string_agg(key, ', ' ORDER BY key), '') AS sent FROM key_log "
         "WHERE recipe = 'R8.1' AND split_part(key, ':', 1) = ANY(string_to_array($1, ','))",
         args=[f"{R6}.brief_invoices.join(',')"], pos=[6240, -160])
    for n in ("Step 7: Add a note to the open dispute", "Step 7: Log the reply on the pause"):
        w.connect(n, "Step 8: Read reminders sent (R8.1 key log)")
    w.code("Step 8: Write the brief", BRIEF_JS, mode="runOnceForAllItems", pos=[6500, -160])
    w.http("Step 8: Brief the account owner", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body="={{ JSON.stringify({ to: $json.to, subject: $json.subject, text: $json.text }) }}",
           write=True, pos=[6760, -160], notes="And Aisha, for \"says paid\".")
    w.chain("Step 8: Read reminders sent (R8.1 key log)", "Step 8: Write the brief", "Step 8: Brief the account owner")

    # ---- logs ------------------------------------------------------------------------------------
    w.code("Outcome for the logs", OUTCOME_JS, mode="runOnceForAllItems", pos=[7020, 100])
    for n in ("Step 8: Brief the account owner", "Step 6: Escalate to Aisha and the owner", "Exception queue: fails the check",
              "Exception queue: unmatched"):
        w.connect(n, "Outcome for the logs")
    w.finish_key("Mark key done", f"{EV}.message_id", "done", f"{OUT}.decision", pos=[7280, 100])
    w.decision_log("Decision log", f"{EV}.message_id", f"{OUT}.decision", f"JSON.stringify({OUT}.rules)", pos=[7540, 100])
    w.chain("Outcome for the logs", "Mark key done", "Decision log")

    w.finish_key("Mark key failed", f"{EV}.message_id", "failed", "'write failed'", pos=[7020, 500])
    w.exception("Exception queue: write failed", f"{EV}.message_id", "write failed",
                "'A dispute-list or message write failed; check the account, never retried'", f"{CFG}.ar_lead", pos=[7280, 500])
    for n in ("Step 3: Write a whole-account pause", "Step 6: Escalate to Aisha and the owner", "Step 7: Add a note to the open dispute",
              "Step 7: Log the reply on the pause", "Step 8: Brief the account owner"):
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- step 9: the owner confirms; only then does the pause narrow -----------------------
    w.pg("Step 9: Read the brief",
         "SELECT decision, rules->>'category' AS category FROM decision_log "
         "WHERE recipe = 'R8.3' AND item = $1 AND decision LIKE 'briefed%' ORDER BY id DESC LIMIT 1",
         args=[f"String({CB}.message_id)"], pos=[780, 900])
    w.http("Step 9: Read the pause", "GET", f"={{{{ {CFG}.sharepoint_url }}}}/disputes/pause-{{{{ {CB}.message_id }}}}",
           write=False, pos=[1040, 900])
    w.code("Step 9: Rule: briefed, paused, invoices named?", NARROW_JS, mode="runOnceForAllItems", pos=[1300, 900])
    w.connect("Owner confirmation?", "Step 9: Read the brief", output=0)
    w.connect("Step 9: Read the brief", "Step 9: Read the pause")
    for o in (0, 1):
        w.connect("Step 9: Read the pause", "Step 9: Rule: briefed, paused, invoices named?", output=o)
    w.if_("Narrow it?", "={{ $json.refused === false }}", pos=[1560, 900])
    w.connect("Step 9: Rule: briefed, paused, invoices named?", "Narrow it?")
    w.http("Step 9: Pause the confirmed invoices", "PUT", f"={{{{ {CFG}.sharepoint_url }}}}/disputes/{{{{ {NAR}.id }}}}",
           body=f"={{{{ JSON.stringify({{ id: {NAR}.id, invoice: {NAR}.invoice, account: {NAR}.account, status: 'open', kind: {NAR}.kind, set_by: {NAR}.by, why: 'reply ' + {NAR}.message_id + ', confirmed by the owner', message_id: {NAR}.message_id, until: {NAR}.until }}) }}}}",
           write=True, pos=[1820, 800], notes="Table 8.2: each pause ends when a person says so; steps 10 and 11 are people's.")
    w.http("Step 9: Narrow the whole-account pause", "PATCH",
           f"={{{{ {CFG}.sharepoint_url }}}}/disputes/pause-{{{{ {NAR}.message_id }}}}",
           body=f"={{{{ JSON.stringify({{ status: 'narrowed', narrowed_by: {NAR}.by, narrowed_at: $now.toISO(), covers: {NAR}.invoices }}) }}}}",
           write=True, pos=[2080, 800])
    next(n for n in w.nodes if n["name"] == "Step 9: Narrow the whole-account pause")["executeOnce"] = True
    w.decision_log("Step 9: Decision log: narrowed", f"{NAR}.message_id", f"'pause narrowed to ' + {NAR}.invoices.join(', ')",
                   f"JSON.stringify({{ by: {NAR}.by, invoices: {NAR}.invoices, kind: {NAR}.kind, until: {NAR}.until }})", pos=[2340, 800])
    w.connect("Narrow it?", "Step 9: Pause the confirmed invoices", output=0)
    w.chain("Step 9: Pause the confirmed invoices", "Step 9: Narrow the whole-account pause", "Step 9: Decision log: narrowed")
    w.decision_log("Step 9: Decision log: not narrowed", f"String({CB}.message_id)", f"'pause not narrowed: ' + {NAR}.reason",
                   f"JSON.stringify({{ by: {CB}.by || null }})", pos=[1820, 1060])
    w.connect("Narrow it?", "Step 9: Decision log: not narrowed", output=1)
    w.exception("Exception queue: step 9 write failed", f"String({CB}.message_id)", "write failed",
                "'Narrowing the pause failed; the whole-account pause stays until it is fixed'", f"{CFG}.ar_lead", pos=[2340, 1060])
    for n in ("Step 9: Pause the confirmed invoices", "Step 9: Narrow the whole-account pause"):
        w.connect(n, "Exception queue: step 9 write failed", output=1)
    return w
