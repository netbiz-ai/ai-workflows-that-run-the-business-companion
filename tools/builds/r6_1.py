"""R6.1 Log emails and meeting notes to the right account and deal.

Source: book Chapter 6, recipe R6.1, build steps 1 to 8 (recipes/R6.1/build-spec.md);
AI steps: recipes/R6.1/prompts/choose-deal.md (step 5, only for several open deals)
and recipes/R6.1/prompts/summarize.md (step 6).

Two triggers, one per event the book names: an email marked into a "CRM" folder
and a saved meeting note. Both are read, reduced to one item, and keyed on the
email's Internet Message-ID header (the same in every mailbox) or the note ID.
Every outcome is logged: an item that is not loggable, an item queued for a
person, or an activity written with the owner's draft. Table 6.1 holds: the
workflow writes the activity, link and last-contact date; the summary and any
next-step date wait in a draft the owner accepts; no deal field is ever written.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

TE = "Step 1: Email marked"
TN = "Step 1: Note saved"
CFG = "$('Config').first().json"
ITEM = "$('Step 1: The item').first().json"
KEY = f"{ITEM}.key"
ACCOUNT = "$('CRM: Read the account').first().json"
CHECKED = "$('Step 7: Rule: deal open, summary within length?').first().json"

ITEM_JS = r"""
// Step 1: one item, whichever trigger fired. A sent email is one whose sender is the mailbox it was marked in.
const lc = s => String(s || '').trim().toLowerCase();
if ($('Step 1: Read the email').isExecuted) {
  const m = $('Step 1: Read the email').first().json;
  const sent = lc(m.from) === lc(m.mailbox);
  return [{ json: { kind: sent ? 'sent email' : 'received email', key: m.internet_message_id, id: m.id,
    from: lc(m.from), recipients: [...(m.to || []), ...(m.cc || [])].map(lc),
    subject: m.subject || '', body: m.body || '', date: String(m.date || '').slice(0, 10), link: m.link } }];
}
const n = $('Step 1: Read the note').first().json;
return [{ json: { kind: 'meeting note', key: 'note:' + n.id, id: n.id, customer: lc(n.customer_email),
  subject: n.title || '', body: n.text || '', date: String(n.date || '').slice(0, 10), link: n.link } }];
"""

ADDRESS_JS = r"""
// Step 3: a received email's sender, a sent one's external recipient, a note's fixed field.
// None, or never-log listed: stop. Several external recipients: exception queue.
const cfg = $('Config').first().json;
const it = $('Step 1: The item').first().json;
const lc = s => String(s || '').trim().toLowerCase();
const never = a => cfg.never_log.map(lc).some(n => n.startsWith('@') ? a.endsWith(n) : a === n);
const all = [...new Set((it.kind === 'received email' ? [it.from] : it.kind === 'sent email' ? it.recipients : [it.customer]).map(lc).filter(Boolean))];
const external = all.filter(a => !never(a));
if (!all.length) return [{ json: { outcome: 'stop', code: 'no customer address' } }];
if (!external.length) return [{ json: { outcome: 'stop', code: it.kind === 'sent email' ? 'no external recipient' : 'never-log listed' } }];
if (external.length > 1) return [{ json: { outcome: 'exception', code: 'several external recipients', detail: `${external.length} external recipients` } }];
return [{ json: { outcome: 'ok', address: external[0] } }];
"""

ACCOUNT_JS = r"""
// Step 4: the full address, never the domain; unless exactly one account matches, queue the item.
const contacts = $input.first().json.items || [];
const accounts = [...new Set(contacts.map(c => c.account_id).filter(Boolean))];
if (accounts.length === 1) return [{ json: { one: true, account_id: accounts[0] } }];
return [{ json: { one: false, code: accounts.length ? 'several accounts match' : 'no account matches',
  detail: accounts.length ? accounts.join(', ') : '' } }];
"""

DEALS_JS = r"""
// Step 5: with no open deal, log at account level; with one, use it; with several, the AI names one or answers "unclear".
const account = $('CRM: Read the account').first().json;
const deals = ($input.first().json.items || []).filter(d => d.account_id === account.id && d.status === 'open');
const route = deals.length === 0 ? 'none' : deals.length === 1 ? 'one' : 'several';
return [{ json: { route, deal_id: deals.length === 1 ? deals[0].id : null, deals } }];
"""

CHOOSE_JS = AI_PARSE_JS + r"""
// Step 5: "unclear", or output that fails the schema, queues the item; a named deal is checked again in step 7.
const p = parseAi($('Step 5: AI call').first().json, ['deal']);
if (!p.ok) return [{ json: { route: 'exception', code: 'AI output failed the check', detail: `step 5: ${p.problem}` } }];
if (typeof p.value.deal !== 'string' || !p.value.deal) return [{ json: { route: 'exception', code: 'AI output failed the check', detail: 'step 5: deal is not a string' } }];
if (p.value.deal === 'unclear') return [{ json: { route: 'exception', code: 'deal unclear', detail: 'the AI could not name one open deal' } }];
return [{ json: { route: 'ok', deal_id: p.value.deal } }];
"""

CHECK_JS = AI_PARSE_JS + r"""
// Step 7: any deal must be open on this account and the summary within length, or the item is queued.
// A past or impossible next-step date is dropped; the summary is still used.
const cfg = $('Config').first().json;
const account = $('CRM: Read the account').first().json;
const open = $('Step 5: Rule: how many open deals?').first().json;
const aiChose = $('Step 5: Rule: deal named or unclear?').isExecuted;
const dealId = aiChose ? $('Step 5: Rule: deal named or unclear?').first().json.deal_id : open.deal_id;
const p = parseAi($('Step 6: AI call').first().json, ['summary', 'next_step_date']);
if (!p.ok) return [{ json: { route: 'exception', code: 'AI output failed the check', detail: `step 6: ${p.problem}` } }];
const summary = typeof p.value.summary === 'string' ? p.value.summary.trim() : '';
const sentences = summary.split(/(?<=[.!?])\s+/).filter(s => s.trim()).length;
const rules = { account: account.id, deal: dealId || 'account level', ai_chosen_deal: aiChose, sentences };
if (dealId && !open.deals.some(d => d.id === dealId && d.account_id === account.id && d.status === 'open')) {
  return [{ json: { route: 'exception', code: 'deal not open on this account', detail: `the AI named ${dealId}`, rules } }];
}
if (!summary || sentences > cfg.max_summary_sentences) {
  return [{ json: { route: 'exception', code: 'summary over length', detail: `${sentences} sentences`, rules } }];
}
let date = p.value.next_step_date;
const today = new Date().toISOString().slice(0, 10);
if (date !== null) {
  const ok = typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date)
    && new Date(date + 'T00:00:00Z').toISOString().slice(0, 10) === date;
  if (!ok) { rules.date = 'dropped: impossible'; date = null; }
  else if (date < today) { rules.date = 'dropped: past'; date = null; }
  else rules.date = 'kept';
} else rules.date = 'none named';
return [{ json: { route: 'log', deal_id: dealId || null, ai_chosen_deal: aiChose, summary, next_step_date: date, rules } }];
"""

RESULT_JS = r"""
// What happened to the item, for the key log and the decision log (never the body).
const s3 = $('Step 3: Rule: customer address').first().json;
const acct = $('Step 4: Rule: exactly one account?').isExecuted ? $('Step 4: Rule: exactly one account?').first().json.account_id || null : null;
if ($('Step 8: CRM: Draft for the owner').isExecuted) {
  const r = $('Step 7: Rule: deal open, summary within length?').first().json;
  return [{ json: { decision: r.deal_id ? `logged to deal ${r.deal_id}` : 'logged at account level', rules: r.rules } }];
}
if ($('Unmatched: reason').isExecuted) {
  const u = $('Unmatched: reason').first().json;
  return [{ json: { decision: `queued: ${u.code}`, rules: { account: acct, reason: u.code } } }];
}
return [{ json: { decision: `not logged: ${s3.code}`, rules: { reason: s3.code } } }];
"""


def build() -> Workflow:
    w = Workflow("R6.1", "R6.1 Log emails and meeting notes to the right account and deal")
    w.webhook(TE, "r6-1-email-marked",
              "Your mail system calls this when an email lands in a \"CRM\" folder of a sales mailbox or the shared trade mailbox. Body: {message_id} (the mail system's item ID).",
              pos=[0, 0])
    w.webhook(TN, "r6-1-note-saved", "Your notes system calls this when a meeting note is saved. Body: {note_id}.", pos=[0, 240])
    w.config("Config", {
        "mail_url": "https://<your mail API>",
        "notes_url": "https://<your meeting notes API>",
        "crm_url": "https://<your CRM API>",
        "never_log": ["@<your company domain>", "<a staff private address>"],
        "max_summary_sentences": 3,
        "queue_owner": "<the person who checks the unmatched queue daily>",
        "crm_admin": "<your CRM admin>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 120])
    w.connect(TE, "Config")
    w.connect(TN, "Config")
    w.if_("Email?", f"={{{{ $('{TE}').isExecuted }}}}", pos=[520, 120])
    w.connect("Config", "Email?")
    w.http("Step 1: Read the email", "GET", f"={{{{ {CFG}.mail_url }}}}/messages/{{{{ $('{TE}').first().json.body.message_id }}}}",
           write=False, error_output=False, pos=[780, 0])
    w.http("Step 1: Read the note", "GET", f"={{{{ {CFG}.notes_url }}}}/notes/{{{{ $('{TN}').first().json.body.note_id }}}}",
           write=False, error_output=False, pos=[780, 240])
    w.connect("Email?", "Step 1: Read the email", output=0)
    w.connect("Email?", "Step 1: Read the note", output=1)
    w.code("Step 1: The item", ITEM_JS, mode="runOnceForAllItems", pos=[1040, 120])
    w.connect("Step 1: Read the email", "Step 1: The item")
    w.connect("Step 1: Read the note", "Step 1: The item")

    w.reserve_key("Step 2: Reserve key", KEY, pos=[1300, 120])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1560, 120])
    w.noop("Duplicate: stop", pos=[1820, -80], notes="This email or note was logged before (the same Message-ID in another mailbox, or a catch-up run).")
    w.chain("Step 1: The item", "Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    w.code("Step 3: Rule: customer address", ADDRESS_JS, mode="runOnceForAllItems", pos=[1820, 120])
    w.switch("Step 3: Loggable?", "={{ $json.outcome }}", ["ok", "stop", "exception"], pos=[2080, 120])
    w.connect("New key?", "Step 3: Rule: customer address", output=0)
    w.connect("Step 3: Rule: customer address", "Step 3: Loggable?")

    w.http("Step 4: CRM: Search by full address", "GET", f"={{{{ {CFG}.crm_url }}}}/contacts",
           query={"_wrap": "1", "email": "={{ $json.address }}"}, write=False, error_output=False, pos=[2340, 0])
    w.code("Step 4: Rule: exactly one account?", ACCOUNT_JS, mode="runOnceForAllItems", pos=[2600, 0])
    w.if_("One account?", "={{ $json.one }}", pos=[2860, 0])
    w.connect("Step 3: Loggable?", "Step 4: CRM: Search by full address", output=0)
    w.chain("Step 4: CRM: Search by full address", "Step 4: Rule: exactly one account?", "One account?")

    w.http("CRM: Read the account", "GET", f"={{{{ {CFG}.crm_url }}}}/accounts/{{{{ $json.account_id }}}}",
           write=False, error_output=False, pos=[3120, -120], notes="For the account's owner, who gets the draft (Table 6.1: R6.1 routes by it).")
    w.http("Step 5: CRM: Read open deals", "GET", f"={{{{ {CFG}.crm_url }}}}/deals",
           query={"_wrap": "1", "account_id": "={{ $json.id }}", "status": "open"}, write=False, error_output=False, pos=[3380, -120])
    w.code("Step 5: Rule: how many open deals?", DEALS_JS, mode="runOnceForAllItems", pos=[3640, -120])
    w.switch("Step 5: Open deals", "={{ $json.route }}", ["none", "one", "several"], pos=[3900, -120])
    w.connect("One account?", "CRM: Read the account", output=0)
    w.chain("CRM: Read the account", "Step 5: CRM: Read open deals", "Step 5: Rule: how many open deals?", "Step 5: Open deals")

    deals_js = ("{ open_deals: $('Step 5: Rule: how many open deals?').first().json.deals"
                ".map(d => `${d.id}: ${d.name}; ${d.quote_ref || 'no quote reference'}`).join('\\n'), "
                f"subject: {ITEM}.subject, body: {ITEM}.body }}")
    b5, c5 = ai_step(w, "Step 5", ROOT / "recipes/R6.1/prompts/choose-deal.md", deals_js,
                     max_tokens=50, tries=3, pos_build=[4160, -280], pos_call=[4420, -280])
    w.connect("Step 5: Open deals", b5, output=2)
    w.code("Step 5: Rule: deal named or unclear?", CHOOSE_JS, mode="runOnceForAllItems", pos=[4680, -280],
           notes="The rule decides, not the AI: \"unclear\" queues the item.")
    w.code("Step 5: AI error", "return [{ json: { route: 'exception', code: 'AI error', detail: 'step 5: ' + String(($json.error && $json.error.message) || '') } }];",
           mode="runOnceForAllItems", pos=[4680, -80])
    w.connect(c5, "Step 5: Rule: deal named or unclear?", output=0)
    w.connect(c5, "Step 5: AI error", output=1)
    w.if_("Deal named?", "={{ $json.route }}", op="equals", right="ok", pos=[4940, -280])
    w.connect("Step 5: Rule: deal named or unclear?", "Deal named?")
    w.connect("Step 5: AI error", "Deal named?")

    sum_js = (f"{{ message_type: {ITEM}.kind, message_date: {ITEM}.date, subject: {ITEM}.subject, body: {ITEM}.body }}")
    b6, c6 = ai_step(w, "Step 6", ROOT / "recipes/R6.1/prompts/summarize.md", sum_js,
                     max_tokens=400, tries=3, pos_build=[5200, -120], pos_call=[5460, -120])
    w.connect("Step 5: Open deals", b6, output=0)
    w.connect("Step 5: Open deals", b6, output=1)
    w.connect("Deal named?", b6, output=0)
    w.code("Step 7: Rule: deal open, summary within length?", CHECK_JS, mode="runOnceForAllItems", pos=[5720, -120],
           notes="The rule decides, not the AI.")
    w.code("Step 6: AI error", "return [{ json: { route: 'exception', code: 'AI error', detail: 'step 6: ' + String(($json.error && $json.error.message) || '') } }];",
           mode="runOnceForAllItems", pos=[5720, 80])
    w.connect(c6, "Step 7: Rule: deal open, summary within length?", output=0)
    w.connect(c6, "Step 6: AI error", output=1)
    w.if_("Log it?", "={{ $json.route }}", op="equals", right="log", pos=[5980, -120])
    w.connect("Step 7: Rule: deal open, summary within length?", "Log it?")

    # ---- step 8: the writes (never retried) ------------------------------------
    crm = f"{CFG}.crm_url"
    w.http("Step 8: CRM: Write the activity and link", "POST", f"={{{{ {crm} }}}}/activities",
           body=(f"={{{{ JSON.stringify({{ account_id: {ACCOUNT}.id, deal_id: {CHECKED}.deal_id, type: {ITEM}.kind, "
                 f"date: {ITEM}.date, link: {ITEM}.link, message_id: {KEY} }}) }}}}"),
           write=True, pos=[6240, -240], notes="The link only; the full text stays behind the mailbox's permissions.")
    w.http("Step 8: CRM: Set last-contact date", "PATCH", f"={{{{ {crm} }}}}/accounts/{{{{ {ACCOUNT}.id }}}}",
           body=(f"={{{{ JSON.stringify({{ last_contact: [{ACCOUNT}.last_contact, {ITEM}.date].filter(Boolean).sort().pop() }}) }}}}"),
           write=True, pos=[6500, -240], notes="Never moves the date back: a late catch-up item keeps the newer date.")
    w.http("Step 8: CRM: Draft for the owner", "POST", f"={{{{ {crm} }}}}/drafts",
           body=(f"={{{{ JSON.stringify({{ activity_id: $('Step 8: CRM: Write the activity and link').first().json.id, "
                 f"account_id: {ACCOUNT}.id, deal_id: {CHECKED}.deal_id, owner: {ACCOUNT}.owner, "
                 f"summary: {CHECKED}.summary, next_step_date: {CHECKED}.next_step_date, "
                 f"ai_chosen_deal: {CHECKED}.ai_chosen_deal, status: 'waiting for owner' }}) }}}}"),
           write=True, pos=[6760, -240], notes="One click for the owner to accept; an AI-chosen deal is flagged.")
    w.connect("Log it?", "Step 8: CRM: Write the activity and link", output=0)
    w.chain("Step 8: CRM: Write the activity and link", "Step 8: CRM: Set last-contact date", "Step 8: CRM: Draft for the owner")

    # ---- the unmatched queue ---------------------------------------------------------
    w.code("Unmatched: reason", "return [{ json: { code: $json.code, detail: $json.detail || '' } }];",
           mode="runOnceForAllItems", pos=[6240, 240])
    w.exception("Exception queue: unmatched", KEY, "unmatched", "$json.code + ($json.detail ? ': ' + $json.detail : '')",
                f"{CFG}.queue_owner", pos=[6500, 240])
    w.connect("Step 3: Loggable?", "Unmatched: reason", output=2)
    w.connect("One account?", "Unmatched: reason", output=1)
    w.connect("Deal named?", "Unmatched: reason", output=1)
    w.connect("Step 6: AI error", "Unmatched: reason")
    w.connect("Log it?", "Unmatched: reason", output=1)
    w.connect("Unmatched: reason", "Exception queue: unmatched")

    # ---- every outcome is logged ----------------------------------------------------------
    w.code("Result", RESULT_JS, mode="runOnceForAllItems", pos=[7020, 0])
    w.connect("Step 8: CRM: Draft for the owner", "Result")
    w.connect("Exception queue: unmatched", "Result")
    w.connect("Step 3: Loggable?", "Result", output=1)
    w.finish_key("Mark key done", KEY, "done", "$('Result').first().json.decision", pos=[7280, 0])
    w.decision_log("Decision log", KEY, "$('Result').first().json.decision",
                   "JSON.stringify($('Result').first().json.rules)", pos=[7540, 0])
    w.chain("Result", "Mark key done", "Decision log")

    w.finish_key("Mark key failed", KEY, "failed", "'write failed: ' + ($json.error && $json.error.message || 'unknown')", pos=[7020, -480])
    w.exception("Exception queue: write failed", KEY, "write failed",
                "'CRM write failed; check the CRM, then release or close the key'", f"{CFG}.crm_admin", pos=[7280, -480])
    for n in ["Step 8: CRM: Write the activity and link", "Step 8: CRM: Set last-contact date", "Step 8: CRM: Draft for the owner"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")
    return w
