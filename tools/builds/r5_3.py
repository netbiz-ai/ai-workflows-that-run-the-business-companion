"""R5.3 Draft a quote from the current price table only.

Source: book Chapter 5, recipe R5.3, build steps 1 to 8 (recipes/R5.3/build-spec.md);
AI step: recipes/R5.3/prompts/draft-quote-text.md. The failure table's "warning a
week ahead" runs each morning.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

T = "Step 1: Ready to quote"
M = "Each morning: price list expiry warning"
EV = f"$('{T}').first().json.body"
KEY = f"{EV}.opportunity_id + ':' + {EV}.revision"
OPP = "$('Read the opportunity').first().json"
PRICE = "Step 4: Price each line"
CHECK = "Step 7: Rule: placeholders filled, no other number?"

IN_DATE_JS = r"""
// Step 3: the price list and the terms library must both be in date (valid through valid_until).
const today = new Date().toISOString().slice(0, 10);
const list = $('Read the price list').first().json;
const terms = $('Read the terms library').first().json;
const expired = [];
if (!list.valid_until || list.valid_until < today) expired.push(`price list ${list.version || ''} valid until ${list.valid_until || 'not set'}`);
if (!terms.valid_until || terms.valid_until < today) expired.push(`terms library ${terms.version || ''} valid until ${terms.valid_until || 'not set'}`);
return [{ json: { in_date: expired.length === 0, expired } }];
"""

PRICE_JS = r"""
// Step 4: unit price times quantity, less discount, rounded once to the cent; the total sums
// the rounded lines. Tax-exclusive, single currency; an off-list code stays unpriced.
const cfg = $('Config').first().json;
const opp = $('Read the opportunity').first().json;
const list = $('Read the price list').first().json;
const byCode = Object.fromEntries((list.items || []).map(i => [i.code, i]));
const money = c => { const s = (Math.abs(c) / 100).toFixed(2).split('.'); return (c < 0 ? '-' : '') + cfg.currency_symbol + s[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '.' + s[1]; };
const lines = [], fill = {}, names = [], offList = [];
(opp.lines || []).forEach((l, i) => {
  const n = l.line || i + 1, p = byCode[l.code];
  const qty = Number(l.quantity), disc = Number(l.discount_pct || 0);
  const keys = ['unit', 'qty', 'discount', 'total'].concat(l.years ? ['years'] : []).map(k => `line_${n}_${k}`);
  names.push(...keys);
  if (!p) {
    offList.push(n);
    lines.push({ line: n, code: l.code, name: l.name || l.code, quantity: qty, discount_pct: disc, years: l.years || null, off_list: true, unit_price: null, line_total: null });
    return;
  }
  // Exact arithmetic: price in ten-thousandths, discount in hundredths of a percent, one half-up rounding.
  const u = BigInt(Math.round(Number(p.unit_price) * 10000)), d = BigInt(Math.round(disc * 100));
  const totalCents = Number((u * BigInt(qty) * (10000n - d) + 500000n) / 1000000n);
  lines.push({ line: n, code: l.code, name: p.name, quantity: qty, discount_pct: disc, years: l.years || null, off_list: false,
               total_cents: totalCents, unit_price: Number(p.unit_price), line_total: totalCents / 100 });
  const up = String(Number(p.unit_price)).split('.');
  fill[`line_${n}_unit`] = cfg.currency_symbol + up[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '.' + ((up[1] || '') + '00').slice(0, Math.max(2, (up[1] || '').length));
  fill[`line_${n}_qty`] = String(qty);
  fill[`line_${n}_discount`] = `${disc}%`;
  fill[`line_${n}_total`] = money(totalCents);
  if (l.years) fill[`line_${n}_years`] = String(l.years);
});
const totalCents = lines.filter(l => !l.off_list).reduce((s, l) => s + l.total_cents, 0);
names.push('quote_total');
fill.quote_total = money(totalCents);
const unfillable = offList.flatMap(n => names.filter(k => k.startsWith(`line_${n}_`)));
return [{ json: { lines, total_cents: totalCents, total: totalCents / 100, fill, placeholders: names, unfillable, off_list_lines: offList,
                  price_list_version: list.version } }];
"""

FILL_JS = AI_PARSE_JS + r"""
// Step 6: fill every placeholder from step 4; an off-list line's stay unfilled.
const pr = $('Step 4: Price each line').first().json;
const p = parseAi($('Step 5: AI call').first().json, ['cover_note', 'scope']);
if (!p.ok || typeof p.value.cover_note !== 'string' || typeof p.value.scope !== 'string') {
  return [{ json: { route: 'ai error', reason: 'AI output failed the schema: ' + (p.ok ? 'fields not text' : p.problem) } }];
}
const raw = { cover_note: p.value.cover_note, scope: p.value.scope };
const put = s => s.replace(/\{\{\s*(\w+)\s*\}\}/g, (m, k) => (k in pr.fill ? pr.fill[k] : m));
return [{ json: { route: 'check', raw, filled: { cover_note: put(raw.cover_note), scope: put(raw.scope) } } }];
"""

CHECK_JS = r"""
// Step 7: every placeholder filled except an off-list line's, the lines add up to the total,
// and no number appears that a placeholder did not supply, in digits or in words.
const cfg = $('Config').first().json;
const pr = $('Step 4: Price each line').first().json;
const f = $json;
if (f.route === 'ai error') return [{ json: { pass: false, reason: f.reason } }];
const problems = [];
const text = f.raw.cover_note + '\n' + f.raw.scope;
const used = [...text.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map(m => m[1]);
for (const k of used) if (!pr.placeholders.includes(k)) problems.push(`unknown placeholder ${k}`);
const left = [...(f.filled.cover_note + '\n' + f.filled.scope).matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map(m => m[1]);
for (const k of left) if (pr.placeholders.includes(k) && !pr.unfillable.includes(k)) problems.push(`placeholder ${k} not filled`);
const bare = text.replace(/\{\{\s*\w+\s*\}\}/g, ' ');
const digits = bare.match(/\d[\d,.]*/g);
if (digits) problems.push(`number no placeholder supplied: ${digits.join(', ')}`);
const words = cfg.number_words.filter(w => new RegExp(`\\b${w}\\b`, 'i').test(bare));
if (words.length) problems.push(`number in words: ${words.join(', ')}`);
const sum = pr.lines.filter(l => !l.off_list).reduce((s, l) => s + l.total_cents, 0);
if (sum !== pr.total_cents) problems.push('lines do not add up to the total');
return [{ json: { pass: problems.length === 0, reason: problems.join('; ') } }];
"""

TERMS_JS = r"""
// Step 8: the approved terms go in after the check, since their numbers would fail it.
const terms = $('Read the terms library').first().json;
const pr = $('Step 4: Price each line').first().json;
const opp = $('Read the opportunity').first().json;
const f = $('Step 6: Fill every placeholder').first().json.filled;
return [{ json: { draft: {
  opportunity_id: opp.id, revision: opp.revision, status: 'awaiting approval', salesperson: opp.salesperson || null,
  customer_name: opp.customer_name, price_list_version: pr.price_list_version, terms_version: terms.version,
  lines: pr.lines.map(({ total_cents, ...l }) => l), total: pr.total, tax: 'exclusive',
  off_list_lines: pr.off_list_lines, cover_note: f.cover_note, scope: f.scope, terms: terms.terms || [] } } }];
"""

EXPIRY_JS = r"""
// Failure table: warn the price list owner a week before the list expires.
const cfg = $('Config').first().json;
const list = $('Read the price list (morning)').first().json;
const today = new Date(new Date().toISOString().slice(0, 10) + 'T00:00:00Z');
const until = list.valid_until ? new Date(list.valid_until + 'T00:00:00Z') : null;
const days = until ? Math.round((until - today) / 86400000) : -1;
if (days > cfg.expiry_warning_days) return [];
return [{ json: { version: list.version, valid_until: list.valid_until || 'not set', days } }];
"""

SUMMARY_JS = r"""
// What the run decided, for the decision log: quote ID, price list version, check result.
const ran = n => { try { return $(n).isExecuted; } catch (e) { return false; } };
const pr = ran('Step 4: Price each line') ? $('Step 4: Price each line').first().json : null;
const chk = ran('Step 7: Rule: placeholders filled, no other number?') ? $('Step 7: Rule: placeholders filled, no other number?').first().json : null;
let decision, quote = null;
if (ran('Step 8: Save the draft for R5.4')) { decision = 'draft saved'; quote = $('Step 8: Save the draft for R5.4').first().json.id; }
else if (chk) decision = 'no draft: ' + chk.reason;
else decision = 'stopped: ' + $('Step 3: Rule: prices and terms in date?').first().json.expired.join('; ');
return [{ json: { decision, rules: { quote_id: quote, price_list_version: pr ? pr.price_list_version : null,
  check: chk ? (chk.pass ? 'passed' : 'failed') : 'not run', off_list_lines: pr ? pr.off_list_lines : [], total: pr ? pr.total : null } } }];
"""


def build() -> Workflow:
    w = Workflow("R5.3", "R5.3 Draft a quote from the current price table only")
    w.webhook(T, "r5-3-ready-to-quote", "Your CRM calls this when an opportunity is marked \"ready to quote\". Body: {opportunity_id, revision}.", pos=[0, 0])
    w.schedule(M, 7, "The failure table's warning a week ahead of the price list's expiry.", pos=[0, 600])
    w.config("Config", {
        "crm_url": "https://<your CRM API>",
        "terms_url": "https://<your approved terms library API>",
        "messaging_url": "https://<your messaging API>",
        "currency_symbol": "$",
        "expiry_warning_days": 7,
        "number_words": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
                         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
                         "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million", "billion",
                         "dozen", "half", "once", "twice"],
        "sales_lead": "<your sales lead, who prices off-list lines>",
        "price_list_owner": "<your price list owner>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 300])
    w.connect(T, "Config")
    w.connect(M, "Config")
    w.if_("Morning check?", f"={{{{ $('{M}').isExecuted }}}}", pos=[520, 300])
    w.connect("Config", "Morning check?")
    cfg = "$('Config').first().json"

    # ---- quote path ---------------------------------------------------------------
    w.reserve_key("Step 2: Reserve key", KEY, pos=[780, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1040, 0])
    w.noop("Duplicate: stop", pos=[1300, -200], notes="This opportunity revision was drafted before.")
    w.connect("Morning check?", "Step 2: Reserve key", output=1)
    w.chain("Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)
    w.http("Read the opportunity", "GET", f"={{{{ {cfg}.crm_url }}}}/opportunities/{{{{ {EV}.opportunity_id }}}}", write=False, pos=[1300, 0])
    w.http("Read the price list", "GET", f"={{{{ {cfg}.crm_url }}}}/price_lists/current", write=False, pos=[1560, 0])
    w.http("Read the terms library", "GET", f"={{{{ {cfg}.terms_url }}}}/libraries/current", write=False, pos=[1820, 0])
    w.connect("New key?", "Read the opportunity", output=0)
    w.chain("Read the opportunity", "Read the price list", "Read the terms library")

    w.code("Step 3: Rule: prices and terms in date?", IN_DATE_JS, mode="runOnceForAllItems", pos=[2080, 0])
    w.connect("Read the terms library", "Step 3: Rule: prices and terms in date?")
    w.if_("In date?", "={{ $json.in_date }}", pos=[2340, 0])
    w.connect("Step 3: Rule: prices and terms in date?", "In date?")
    w.http("Step 3: Tell Ben and Aisha", "POST", f"={{{{ {cfg}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: [{cfg}.sales_lead, {cfg}.price_list_owner], subject: 'Quote stopped: price list or terms expired', text: 'Opportunity ' + {EV}.opportunity_id + ' was not drafted: ' + $json.expired.join('; ') }}) }}}}",
           write=True, pos=[2600, 240])
    w.pg("Step 3: Release the key", "DELETE FROM key_log WHERE recipe = $1 AND key = $2 RETURNING key",
         args=['"R5.3"', KEY], pos=[2860, 240],
         notes="Stopped before any draft, so marking ready again after a new list is published drafts it.")
    w.connect("In date?", "Step 3: Tell Ben and Aisha", output=1)
    w.connect("Step 3: Tell Ben and Aisha", "Step 3: Release the key")

    w.code(PRICE, PRICE_JS, mode="runOnceForAllItems", pos=[2600, 0], notes="Fixed rule; the AI never sees a price.")
    w.connect("In date?", PRICE, output=0)
    w.if_("Off-list line?", "={{ $json.off_list_lines.length > 0 }}", pos=[2860, 0])
    w.connect(PRICE, "Off-list line?")
    w.exception("Step 4: Flag off-list line for Ben", f"{EV}.opportunity_id", "off-list line",
                f"'Unpriced off-list line(s) ' + $('{PRICE}').first().json.off_list_lines.join(', ') + '; price before R5.4 routes it'",
                f"{cfg}.sales_lead", pos=[3120, -160])
    w.connect("Off-list line?", "Step 4: Flag off-list line for Ben", output=0)

    pr = f"$('{PRICE}').first().json"
    vars_js = (f"{{ customer_name: {OPP}.customer_name, need: {OPP}.need || '', "
               f"line_list: {pr}.lines.map(l => `${{l.line}}: ${{l.name}}`).join('\\n'), "
               f"placeholder_list: {pr}.placeholders.map(k => '{{{{' + k + '}}}}').join('\\n') }}")
    build, call = ai_step(w, "Step 5", ROOT / "recipes/R5.3/prompts/draft-quote-text.md", vars_js,
                          max_tokens=800, tries=2, pos_build=[3380, 0], pos_call=[3640, 0])
    w.connect("Off-list line?", build, output=1)
    w.connect("Step 4: Flag off-list line for Ben", build)

    w.code("Step 6: Fill every placeholder", FILL_JS, mode="runOnceForAllItems", pos=[3900, -100])
    w.connect(call, "Step 6: Fill every placeholder", output=0)
    w.code("Step 5: AI error", "return [{ json: { route: 'ai error', reason: 'AI error after one retry: ' + String(($json.error && $json.error.message) || '') } }];",
           mode="runOnceForAllItems", pos=[3900, 120])
    w.connect(call, "Step 5: AI error", output=1)
    w.code(CHECK, CHECK_JS, mode="runOnceForAllItems", pos=[4160, 0], notes="The rule decides; any number no placeholder supplied fails the draft.")
    w.connect("Step 6: Fill every placeholder", CHECK)
    w.connect("Step 5: AI error", CHECK)
    w.if_("Draft passes?", "={{ $json.pass }}", pos=[4420, 0])
    w.connect(CHECK, "Draft passes?")

    w.code("Step 8: Add the approved terms", TERMS_JS, mode="runOnceForAllItems", pos=[4680, -120])
    w.http("Step 8: Save the draft for R5.4", "POST", f"={{{{ {cfg}.crm_url }}}}/quotes",
           body="={{ JSON.stringify($json.draft) }}", write=True, pos=[4940, -120],
           notes="Stamped with the price list version; \"awaiting approval\" starts R5.4.")
    w.connect("Draft passes?", "Step 8: Add the approved terms", output=0)
    w.connect("Step 8: Add the approved terms", "Step 8: Save the draft for R5.4")
    w.http("Step 8: Flag the opportunity", "PATCH", f"={{{{ {cfg}.crm_url }}}}/opportunities/{{{{ {EV}.opportunity_id }}}}",
           body="={{ JSON.stringify({ quote_flag: 'No draft: ' + $json.reason }) }}", write=True, pos=[4680, 160])
    w.exception("Exception queue: no draft", f"{EV}.opportunity_id", "no draft", f"$('{CHECK}').first().json.reason",
                f"{cfg}.sales_lead", pos=[4940, 160])
    w.connect("Draft passes?", "Step 8: Flag the opportunity", output=1)
    w.connect("Step 8: Flag the opportunity", "Exception queue: no draft")

    w.code("Run summary", SUMMARY_JS, mode="runOnceForAllItems", pos=[5200, 0])
    for n in ["Step 8: Save the draft for R5.4", "Exception queue: no draft", "Step 3: Release the key"]:
        w.connect(n, "Run summary")
    w.if_("Key kept?", "={{ !$('Step 3: Release the key').isExecuted }}", pos=[5460, 0])
    w.finish_key("Mark key done", KEY, "done", "$('Run summary').first().json.decision", pos=[5720, -100])
    w.decision_log("Decision log", f"{EV}.opportunity_id + ':' + {EV}.revision", "$('Run summary').first().json.decision",
                   "JSON.stringify($('Run summary').first().json.rules)", pos=[5980, 0])
    w.chain("Run summary", "Key kept?", "Mark key done", "Decision log")
    w.connect("Key kept?", "Decision log", output=1)

    w.finish_key("Mark key failed", KEY, "failed", "'failed: ' + (($json.error && $json.error.message) || 'unknown')", pos=[5200, 500])
    w.exception("Exception queue: write or read failed", f"{EV}.opportunity_id", "write or read failed",
                "'A CRM read failed after three tries, or a write failed and was not retried; quote by hand, then release the key'",
                f"{cfg}.sales_lead", pos=[5460, 500])
    for n in ["Read the opportunity", "Read the price list", "Read the terms library", "Step 3: Tell Ben and Aisha",
              "Step 8: Save the draft for R5.4", "Step 8: Flag the opportunity"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write or read failed")

    # ---- morning expiry warning ------------------------------------------------------
    w.http("Read the price list (morning)", "GET", f"={{{{ {cfg}.crm_url }}}}/price_lists/current",
           write=False, error_output=False, pos=[780, 600])
    w.code("Rule: expiring within a week?", EXPIRY_JS, mode="runOnceForAllItems", pos=[1040, 600])
    w.http("Tell the price list owner", "POST", f"={{{{ {cfg}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: {cfg}.price_list_owner, subject: 'Price list ' + $json.version + ' expires ' + $json.valid_until, text: 'Publish a new price list; quotes stop drafting once it expires.' }}) }}}}",
           write=True, error_output=False, pos=[1300, 600])
    w.connect("Morning check?", "Read the price list (morning)", output=0)
    w.chain("Read the price list (morning)", "Rule: expiring within a week?", "Tell the price list owner")
    return w
