"""R6.3 Find likely duplicate accounts and queue them for a person to merge.

Source: book Chapter 6, recipe R6.3, Table 6.3 and build steps 1 to 10
(recipes/R6.3/build-spec.md); AI step: recipes/R6.3/prompts/explain-match.md.

Weekly: the export is checked (step 2), every account's Table 6.3 signals are
normalized (step 3), accounts sharing any signal are grouped and paired, and a
pair with one strong or two weaker signals qualifies (step 4). A pair on the
suppression list stays dropped while every signal field of both accounts is as it
was at the rejection (step 5). The key log holds a pair while it waits (step 6).
The AI only explains the match; a reason naming any other field is dropped and
the pair queues with signals alone (step 7). A person merges or rejects every
pair; the merge queue's form calls step 10, which logs the decision, puts a
rejection on the suppression list and releases the pair's key. The workflow has
no merge, delete or edit call on any account.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, V, Workflow, ai_step  # noqa: E402

T = "Step 1: Weekly duplicate check"
TD = "Step 10: Decision recorded"
CFG = "$('Config').first().json"
PAIRS = "Step 5: Rule: drop suppressed pairs"
P = f"$('{PAIRS}').item.json"
DEC = f"$('{TD}').first().json.body"

CHECK_EXPORT_JS = r"""
// Step 2: stop if the export changed format or shrank sharply.
const cfg = $('Config').first().json;
const a = $('Step 2: Export accounts').first().json;
const c = $('Step 2: Export contacts').first().json;
const problems = [];
if (!Array.isArray(a.items) || !Array.isArray(c.items)) problems.push('export changed format: no list of records');
else {
  const bad = (rows, fields) => rows.filter(r => !r || typeof r !== 'object' || fields.some(f => !(f in r)));
  const badA = bad(a.items, cfg.account_fields), badC = bad(c.items, cfg.contact_fields);
  if (badA.length) problems.push(`export changed format: ${badA.length} account record(s) without ${cfg.account_fields.join(', ')}`);
  if (badC.length) problems.push(`export changed format: ${badC.length} contact record(s) without ${cfg.contact_fields.join(', ')}`);
  const floor = cfg.expected_accounts * (1 - cfg.max_shrink_pct / 100);
  if (a.items.length < floor) problems.push(`export shrank: ${a.items.length} accounts, expected about ${cfg.expected_accounts}`);
}
return [{ json: { ok: problems.length === 0, problem: problems.join('; ') } }];
"""

NORMALIZE_JS = r"""
// Step 3: normalize each signal as Table 6.3 shows.
const cfg = $('Config').first().json;
const accounts = $('Step 2: Export accounts').first().json.items;
const contacts = $('Step 2: Export contacts').first().json.items;
const excluded = new Set(cfg.excluded_domains.map(d => String(d).toLowerCase()));
const suffixes = new Set(cfg.name_suffixes.map(s => String(s).toLowerCase()));
const abbr = cfg.address_abbreviations || {};
const text = v => (v === null || v === undefined) ? '' : String(v);
const words = v => text(v).toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/).filter(Boolean);
const phone = v => {
  const s = text(v).trim(), d = s.replace(/\D/g, '');
  if (!d) return '';
  if (s.startsWith('+')) return d;
  if (s.startsWith('00')) return d.slice(2);
  return String(cfg.default_country_code) + d.replace(/^0/, '');
};
const domain = e => { const m = text(e).toLowerCase().trim().match(/@([^@\s]+)$/); return m && !excluded.has(m[1]) ? m[1] : ''; };
const out = accounts.map(acc => {
  const mine = contacts.filter(c => c.account_id === acc.id);
  return {
    id: acc.id,
    raw: { tax_id: text(acc.tax_id), phone: text(acc.phone), billing_address: text(acc.billing_address),
           name: text(acc.name), emails: [acc.email, ...mine.map(c => c.email)].map(text).filter(Boolean) },
    signals: {
      tax_id: text(acc.tax_id).replace(/\D/g, ''),
      phone: phone(acc.phone),
      billing_address: words(acc.billing_address).map(w => abbr[w] || w).join(' '),
      email_domain: [...new Set([acc.email, ...mine.map(c => c.email)].map(domain).filter(Boolean))].sort(),
      name: words(acc.name).filter(w => !suffixes.has(w)).join(' '),
    },
    record: Object.assign({}, acc, { contacts: mine }),
  };
});
return [{ json: { accounts: out } }];
"""

PAIR_JS = r"""
// Step 4: group accounts sharing any signal, compare within groups; one strong or two weaker signals queue the pair.
const accounts = $input.first().json.accounts;
const STRONG = ['tax_id', 'phone'], WEAK = ['billing_address', 'email_domain', 'name'];
const groups = {};
for (const a of accounts) {
  for (const s of [...STRONG, ...WEAK]) {
    const vals = s === 'email_domain' ? a.signals[s] : [a.signals[s]];
    for (const v of vals) if (v) (groups[`${s}=${v}`] = groups[`${s}=${v}`] || []).push(a);
  }
}
const seen = new Set(), pairs = [];
for (const members of Object.values(groups)) {
  for (let i = 0; i < members.length; i++) for (let j = i + 1; j < members.length; j++) {
    const [a, b] = [members[i], members[j]].sort((x, y) => (x.id < y.id ? -1 : 1));
    const id = `${a.id}:${b.id}`;
    if (a.id === b.id || seen.has(id)) continue;
    seen.add(id);
    const matched = [];
    for (const s of [...STRONG, ...WEAK]) {
      const hit = s === 'email_domain' ? a.signals[s].some(d => b.signals[s].includes(d)) : a.signals[s] && a.signals[s] === b.signals[s];
      if (hit) matched.push(s);
    }
    const strong = matched.filter(s => STRONG.includes(s)).length, weak = matched.filter(s => WEAK.includes(s)).length;
    if (strong >= 1 || weak >= 2) pairs.push({ pair_id: id, a, b, matched });
  }
}
return [{ json: { pairs } }];
"""

SUPPRESS_JS = r"""
// Step 5: drop suppressed pairs unless a signal field has changed since the rejection; a new activity does not count.
const pairs = $('Step 4: Rule: group and pair').first().json.pairs;
const suppressed = Object.fromEntries(($('Read the suppression list').first().json.items || []).map(s => [s.id, s]));
const canon = v => Array.isArray(v) ? `[${v.map(canon).join(',')}]`
  : v && typeof v === 'object' ? `{${Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canon(v[k])).join(',')}}` : JSON.stringify(v);
const LABEL = { tax_id: 'tax ID', phone: 'phone', billing_address: 'billing address', email_domain: 'company email domain', name: 'name' };
const out = [];
for (const p of pairs) {
  const snapshot = { a: p.a.signals, b: p.b.signals };
  const s = suppressed[p.pair_id];
  if (s && canon(s.snapshot) === canon(snapshot)) continue;
  const shown = sig => sig === 'email_domain'
    ? p.a.signals.email_domain.filter(d => p.b.signals.email_domain.includes(d)).join(', ')
    : null;
  const lines = p.matched.map(sig => {
    const both = shown(sig);
    return `${LABEL[sig]}: ${both !== null ? both : p.a.raw[sig]} | ${both !== null ? both : p.b.raw[sig]}`;
  });
  out.push({ json: { pair_id: p.pair_id, a: p.a.id, b: p.b.id, signals: p.matched, matched_fields: lines.join('\n'),
    records: [p.a.record, p.b.record], snapshot, suppression: s ? 'lifted: a signal field changed' : 'none' },
    pairedItem: { item: 0 } });
}
return out;
"""

EXPLAIN_JS = AI_PARSE_JS + r"""
// Step 7: keep the reason only if it is one sentence and names no field but the pair's matched signals.
const cfg = $('Config').first().json;
const p = $('Step 5: Rule: drop suppressed pairs').item.json;
const r = parseAi($json, ['reason']);
if (!r.ok || typeof r.value.reason !== 'string' || !r.value.reason.trim()) return { json: { reason: null, reason_check: `dropped: ${r.ok ? 'reason is not a sentence' : r.problem}` } };
const reason = r.value.reason.trim();
const sentences = reason.split(/(?<=[.!?])\s+/).filter(s => s.trim()).length;
const other = [...Object.entries(cfg.signal_terms).filter(([sig]) => !p.signals.includes(sig)).flatMap(([, terms]) => terms), ...cfg.other_field_terms];
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const named = other.filter(t => new RegExp(`\\b${esc(String(t).toLowerCase())}`).test(reason.toLowerCase()));
if (sentences !== 1) return { json: { reason: null, reason_check: `dropped: ${sentences} sentences` } };
if (named.length) return { json: { reason: null, reason_check: `dropped: names ${named.join(', ')}` } };
return { json: { reason, reason_check: 'passed' } };
"""

CONFIRM_JS = r"""
// Step 8: an open quote on either account needs the sales lead's confirmation first; credit terms, the finance lead's.
const cfg = $('Config').first().json;
const p = $('Step 5: Rule: drop suppressed pairs').item.json;
const has = v => Array.isArray(v) ? v.length > 0 : typeof v === 'number' ? v > 0 : !!v;
const confirm = [];
if (p.records.some(r => has(r.open_quotes))) confirm.push(`${cfg.open_quote_confirmer} confirms first`);
if (p.records.some(r => has(r.credit_terms))) confirm.push(`${cfg.credit_terms_confirmer} confirms first`);
return { json: { confirm_first: confirm, reason: $json.reason, reason_check: $json.reason_check } };
"""


def build() -> Workflow:
    w = Workflow("R6.3", "R6.3 Find likely duplicate accounts and queue them for a person to merge")
    w.node(T, "n8n-nodes-base.scheduleTrigger", V["schedule"],
           {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1, "triggerAtDay": [0], "triggerAtHour": 2}]}},
           pos=[0, 0], notes="Sundays at 2:00, outside trading hours. Set the workflow's time zone (Settings).")
    w.webhook(TD, "r6-3-decision", "Your merge queue's form calls this when the merger records \"merge\" or \"reject\". Body: {pair_id, decision, by}.",
              pos=[0, 800])
    w.config("Config", {
        "export_url": "https://<your CRM export API>",
        "queue_url": "https://<your merge queue and suppression list API>",
        "messaging_url": "https://<your messaging API>",
        "account_fields": ["id", "name", "phone", "tax_id", "billing_address", "email", "open_quotes", "credit_terms", "links"],
        "contact_fields": ["id", "account_id", "email"],
        "expected_accounts": 400,
        "max_shrink_pct": 20,
        "excluded_domains": ["<your webmail and shared domains>"],
        "default_country_code": "<your country calling code, digits only>",
        "name_suffixes": ["inc", "llc", "ltd"],
        "address_abbreviations": {"street": "st", "avenue": "ave", "road": "rd", "drive": "dr", "boulevard": "blvd", "suite": "ste"},
        "signal_terms": {"tax_id": ["tax"], "phone": ["phone", "telephone"], "billing_address": ["address"],
                         "email_domain": ["domain", "email"], "name": ["name"]},
        "other_field_terms": ["<your CRM's other field names>"],
        "open_quote_confirmer": "<your sales lead>",
        "credit_terms_confirmer": "<your finance lead>",
        "merger": "<your named merger>",
        "export_owner": "<the person who fixes the export>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 400])
    w.connect(T, "Config")
    w.connect(TD, "Config")
    w.if_("Decision recorded?", f"={{{{ $('{TD}').isExecuted }}}}", pos=[520, 400])
    w.connect("Config", "Decision recorded?")

    # ---- step 2: the export ---------------------------------------------------------
    exp = f"{CFG}.export_url"
    w.http("Step 2: Export accounts", "GET", f"={{{{ {exp} }}}}/accounts", query={"_wrap": "1"}, write=False, pos=[780, 0],
           notes="Store accounts stay out of the export: a person links one to a firm's trade account, keeping both records.")
    w.http("Step 2: Export contacts", "GET", f"={{{{ {exp} }}}}/contacts", query={"_wrap": "1"}, write=False, pos=[1040, 0])
    w.code("Step 2: Rule: export full and unchanged?", CHECK_EXPORT_JS, mode="runOnceForAllItems", pos=[1300, 0])
    w.if_("Export OK?", "={{ $json.ok }}", pos=[1560, 0])
    w.connect("Decision recorded?", "Step 2: Export accounts", output=1)
    w.connect("Step 2: Export accounts", "Step 2: Export contacts", output=0)
    w.chain("Step 2: Export contacts", "Step 2: Rule: export full and unchanged?", "Export OK?")
    w.code("Step 2: Export failed", "return [{ json: { ok: false, problem: 'export failed: ' + String(($json.error && $json.error.message) || 'unknown') } }];",
           mode="runOnceForAllItems", pos=[1560, 240])
    w.connect("Step 2: Export accounts", "Step 2: Export failed", output=1)
    w.connect("Step 2: Export contacts", "Step 2: Export failed", output=1)
    w.exception("Exception queue: export stopped the run", "'export ' + new Date().toISOString().slice(0, 10)", "export check failed",
                "$json.problem", f"{CFG}.export_owner", pos=[1820, 240])
    w.http("Step 2: Tell the export owner", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=(f"={{{{ JSON.stringify({{ to: {CFG}.export_owner, subject: 'R6.3 duplicate run stopped: export check failed', "
                 "text: $('Step 2: Rule: export full and unchanged?').isExecuted && !$('Step 2: Rule: export full and unchanged?').first().json.ok "
                 "? $('Step 2: Rule: export full and unchanged?').first().json.problem : $('Step 2: Export failed').first().json.problem }) }}"),
           write=True, error_output=False, pos=[2080, 240])
    w.connect("Export OK?", "Exception queue: export stopped the run", output=1)
    w.connect("Step 2: Export failed", "Exception queue: export stopped the run")
    w.connect("Exception queue: export stopped the run", "Step 2: Tell the export owner")

    # ---- steps 3 to 6: rules choose every pair ---------------------------------------
    w.code("Step 3: Rule: normalize signals", NORMALIZE_JS, mode="runOnceForAllItems", pos=[1820, 0])
    w.code("Step 4: Rule: group and pair", PAIR_JS, mode="runOnceForAllItems", pos=[2080, 0])
    w.http("Read the suppression list", "GET", f"={{{{ {CFG}.queue_url }}}}/suppressions", query={"_wrap": "1"},
           write=False, error_output=False, pos=[2340, -160])
    w.code(PAIRS, SUPPRESS_JS, mode="runOnceForAllItems", pos=[2600, 0])
    w.connect("Export OK?", "Step 3: Rule: normalize signals", output=0)
    w.chain("Step 3: Rule: normalize signals", "Step 4: Rule: group and pair", "Read the suppression list")
    w.connect("Read the suppression list", PAIRS)
    w.reserve_key("Step 6: Reserve key", "$json.pair_id", pos=[2860, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[3120, 0])
    w.noop("Waiting: skip", pos=[3380, -200], notes="This pair is already in the queue, waiting for the merger.")
    w.chain(PAIRS, "Step 6: Reserve key", "New key?")
    w.connect("New key?", "Waiting: skip", output=1)

    # ---- step 7: the AI only explains -----------------------------------------------------
    b7, c7 = ai_step(w, "Step 7", ROOT / "recipes/R6.3/prompts/explain-match.md", f"{{ matched_fields: {P}.matched_fields }}",
                     max_tokens=150, tries=3, pos_build=[3380, 0], pos_call=[3640, 0])
    w.connect("New key?", b7, output=0)
    w.code("Step 7: Rule: names only matched signals?", EXPLAIN_JS, pos=[3900, -80], notes="Otherwise the pair queues with signals alone.")
    w.code("Step 7: AI error", "return { json: { reason: null, reason_check: 'AI error after three retries' } };", pos=[3900, 120])
    w.connect(c7, "Step 7: Rule: names only matched signals?", output=0)
    w.connect(c7, "Step 7: AI error", output=1)

    # ---- steps 8 and 9: who confirms first, then the queue ----------------------------------
    w.code("Step 8: Rule: who confirms first?", CONFIRM_JS, pos=[4160, 0])
    w.connect("Step 7: Rule: names only matched signals?", "Step 8: Rule: who confirms first?")
    w.connect("Step 7: AI error", "Step 8: Rule: who confirms first?")
    s8 = "$('Step 8: Rule: who confirms first?').item.json"
    w.http("Step 9: Queue the pair with both records", "POST", f"={{{{ {CFG}.queue_url }}}}/pairs",
           body=(f"={{{{ JSON.stringify({{ id: {P}.pair_id, accounts: [{P}.a, {P}.b], records: {P}.records, signals: {P}.signals, "
                 f"matched_fields: {P}.matched_fields, reason: {s8}.reason, reason_check: {s8}.reason_check, "
                 f"confirm_first: {s8}.confirm_first, merger: {CFG}.merger, snapshot: {P}.snapshot, status: 'waiting', "
                 "queued: new Date().toISOString().slice(0, 10) }) }}"),
           write=True, pos=[4420, 0], notes="Both records, exported, so the merger can choose the survivor. A merge is a deletion: the merger uses the CRM's own merge.")
    w.connect("Step 8: Rule: who confirms first?", "Step 9: Queue the pair with both records")
    w.finish_key("Mark key done", f"{P}.pair_id", "done", "'queued; waiting for the merger'", pos=[4680, 0])
    w.decision_log("Step 10: Decision log: queued", f"{P}.pair_id", "'queued'",
                   (f"JSON.stringify({{ signals: {P}.signals, suppression: {P}.suppression, reason_check: {s8}.reason_check, "
                    f"confirm_first: {s8}.confirm_first }})"), pos=[4940, 0])
    w.chain("Step 9: Queue the pair with both records", "Mark key done", "Step 10: Decision log: queued")
    w.finish_key("Mark key failed", f"{P}.pair_id", "failed", "'write failed: ' + ($json.error && $json.error.message || 'unknown')", pos=[4680, 320])
    w.exception("Exception queue: write failed", f"{P}.pair_id", "write failed",
                "'Queue write failed; check the queue, then release the key'", f"{CFG}.merger", pos=[4940, 320])
    w.connect("Step 9: Queue the pair with both records", "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- step 10: the merger's decision ------------------------------------------------------
    w.http("Step 10: Queue: Read the pair", "GET", f"={{{{ {CFG}.queue_url }}}}/pairs/{{{{ {DEC}.pair_id }}}}",
           write=False, error_output=False, pos=[780, 800])
    w.if_("Rejected?", f"={{{{ {DEC}.decision }}}}", op="equals", right="reject", pos=[1040, 800])
    w.connect("Decision recorded?", "Step 10: Queue: Read the pair", output=0)
    w.connect("Step 10: Queue: Read the pair", "Rejected?")
    pair = "$('Step 10: Queue: Read the pair').first().json"
    w.http("Step 10: Suppression list: Add the pair", "PUT", f"={{{{ {CFG}.queue_url }}}}/suppressions/{{{{ {DEC}.pair_id }}}}",
           body=(f"={{{{ JSON.stringify({{ pair: {pair}.accounts, signals: {pair}.signals, snapshot: {pair}.snapshot, "
                 f"rejected_by: {DEC}.by, rejected: new Date().toISOString().slice(0, 10) }}) }}}}"),
           write=True, pos=[1300, 720], notes="The snapshot is every signal field of both accounts at queue time; a change to any of them lifts the suppression.")
    w.connect("Rejected?", "Step 10: Suppression list: Add the pair", output=0)
    w.pg("Step 10: Release the key", "DELETE FROM key_log WHERE recipe = $1 AND key = $2 RETURNING key",
         args=[json.dumps("R6.3"), f"{DEC}.pair_id"], pos=[1560, 800],
         notes="The pair no longer waits: a merged pair is gone, a rejected one is held by the suppression list.")
    w.connect("Step 10: Suppression list: Add the pair", "Step 10: Release the key")
    w.connect("Rejected?", "Step 10: Release the key", output=1)
    w.decision_log("Step 10: Decision log", f"{DEC}.pair_id", f"{DEC}.decision + ' by ' + {DEC}.by",
                   f"JSON.stringify({{ signals: {pair}.signals, confirm_first: {pair}.confirm_first || [], by: {DEC}.by }})", pos=[1820, 800])
    w.connect("Step 10: Release the key", "Step 10: Decision log")
    w.exception("Exception queue: suppression write failed", f"{DEC}.pair_id", "write failed",
                "'Suppression write failed; the rejected pair may be queued again'", f"{CFG}.merger", pos=[1560, 1000])
    w.connect("Step 10: Suppression list: Add the pair", "Exception queue: suppression write failed", output=1)
    return w
