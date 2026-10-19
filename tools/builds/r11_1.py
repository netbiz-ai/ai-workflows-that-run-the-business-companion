"""R11.1 Collect supplier quotes into one normalized comparison.

Source: book Chapter 11, recipe R11.1, build steps 1 to 12 (recipes/R11.1/build-spec.md);
AI step: recipes/R11.1/prompts/extract-quote.md.

Two events, both through one Config node:
- Step 1: the quotes mailbox calls a webhook for each new message.
- Step 12: each shift, the stockroom lead is told which AI-filled rows still wait for a check.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

T = "Step 1: New quotes-mailbox message"
S = "Step 12: Each shift"
CFG = "$('Config').first().json"
MSG = "$('Read the message').first().json"
FP = "$('Step 2: Fingerprint the attachment').first().json.fingerprint"
S1 = "Step 1: Rule: readable attachment?"
S3 = "Step 3: Read the response table cell by cell"
S5 = "Step 5: Rules: schema, totals, values on page"
S69 = "Rules: steps 6 to 9"

HELPERS_JS = r"""
const norm = s => String(s == null ? '' : s).toLowerCase().replace(/\s+/g, ' ').trim();
// An amount as printed: "$1,150.00", "1.150,00" or "11,50"; NaN if it holds no number.
const num = s => {
  let t = String(s == null ? '' : s).replace(/[^\d.,-]/g, '');
  if (!/\d/.test(t)) return NaN;
  const c = t.lastIndexOf(','), d = t.lastIndexOf('.');
  if (c > d) t = (d === -1 && t.length - c - 1 === 3) ? t.replace(/,/g, '') : t.replace(/\./g, '').replace(',', '.');
  else t = t.replace(/,/g, '');
  return Number(t);
};
const cents = x => Math.round(x * 100) / 100;
"""

READABLE_JS = r"""
// Step 1: no attachment, or only a scan, goes to the exception queue.
const cfg = $('Config').first().json;
const m = $('Read the message').first().json;
const atts = m.attachments || [];
const mark = cfg.response_table_marker || {};
const isTable = a => !!a.cells && String(a.cells[mark.cell] == null ? '' : a.cells[mark.cell]).trim() === String(mark.text).trim();
const hasText = a => Array.isArray(a.pages) && a.pages.some(p => String(p || '').trim());
const table = atts.find(isTable);
const pick = table || atts.find(hasText);
if (!pick) return [{ json: { readable: false, detail: atts.length ? 'only a scan: no attachment has a text layer' : 'no attachment' } }];
return [{ json: { readable: true, kind: table ? 'table' : 'text', name: pick.name, attachment: pick,
  content: pick.contentBytes || JSON.stringify(pick.cells || pick.pages) } }];
"""

TABLE_JS = r"""
// Step 3: the response table is read cell by cell, at the cells Config names; no AI.
const cfg = $('Config').first().json;
const a = $('Step 1: Rule: readable attachment?').first().json.attachment;
const cells = a.cells || {};
const cell = ref => String(cells[ref] == null ? '' : cells[ref]).trim();
const field = ref => { const value = cell(ref); return { value, page: value ? 1 : null }; };
const quote = {};
for (const [k, ref] of Object.entries(cfg.response_table_cells)) quote[k] = field(ref);
const L = cfg.response_table_lines;
const first = Number(L.first_row);
quote.lines = [];
for (let r = first; Number.isInteger(first) && r < first + 500 && cell(L.columns.description + r); r++) {
  const line = {};
  for (const [k, col] of Object.entries(L.columns)) line[k] = field(col + r);
  quote.lines.push(line);
}
// The whole sheet is one "page" for the checks that follow.
return [{ json: { source: 'response table', quote, pages: [Object.values(cells).join('\n')] } }];
"""

STEP5_JS = AI_PARSE_JS + HELPERS_JS + r"""
// Step 5: the schema matches; the lines add to the subtotal to the cent; every value is on its page.
const HEADER = ['supplier', 'quote_number', 'quote_date', 'valid_until', 'currency', 'freight', 'subtotal'];
const LINE = ['description', 'quantity', 'unit', 'unit_price', 'line_total'];
const fail = problem => [{ json: { ok: false, problem } }];
let quote, pages, source;
if ($('Step 3: Read the response table cell by cell').isExecuted) {
  const t = $('Step 3: Read the response table cell by cell').first().json;
  quote = t.quote; pages = t.pages; source = t.source;
} else {
  const p = parseAi($('Step 4: AI call').first().json, [...HEADER, 'lines']);
  if (!p.ok) return fail(p.problem);
  quote = p.value; source = 'AI';
  pages = $('Step 1: Rule: readable attachment?').first().json.attachment.pages;
}
const extra = Object.keys(quote).filter(k => ![...HEADER, 'lines'].includes(k));
if (extra.length) return fail(`unexpected field ${extra[0]}`);
const checkField = (f, name) => {
  if (!f || typeof f !== 'object' || Array.isArray(f)) return `${name} is not an object`;
  if (Object.keys(f).some(k => !['value', 'page'].includes(k))) return `${name} has an unexpected key`;
  if (typeof f.value !== 'string') return `${name}.value is not text`;
  if (f.value === '') return f.page === null ? null : `${name} is blank but names a page`;
  if (!Number.isInteger(f.page) || f.page < 1 || f.page > pages.length) return `${name} names no page of the attachment`;
  if (name === 'freight' && norm(f.value) === 'included') return null;  // step 6 checks it
  return norm(pages[f.page - 1]).includes(norm(f.value)) ? null : `${name} "${f.value}" is not on page ${f.page}`;
};
for (const k of HEADER) { const e = checkField(quote[k], k); if (e) return fail(e); }
if (!Array.isArray(quote.lines) || !quote.lines.length) return fail('no lines');
for (const [i, l] of quote.lines.entries()) {
  if (!l || typeof l !== 'object' || Object.keys(l).some(k => !LINE.includes(k))) return fail(`line ${i + 1} does not match the schema`);
  for (const k of LINE) { const e = checkField(l[k], `line ${i + 1} ${k}`); if (e) return fail(e); }
}
const totals = quote.lines.map(l => num(l.line_total.value));
const subtotal = num(quote.subtotal.value);
if (totals.some(x => !Number.isFinite(x))) return fail('a line total is blank or unreadable');
if (!Number.isFinite(subtotal)) return fail('the subtotal is blank or unreadable');
const sum = totals.reduce((s, x) => s + x, 0);
if (Math.round(sum * 100) !== Math.round(subtotal * 100)) return fail(`lines add to ${cents(sum)}, subtotal is ${subtotal}`);
return [{ json: { ok: true, source, quote, pages } }];
"""

STEPS_6_9_JS = HELPERS_JS + r"""
// Steps 6 to 9: rules flag the row; they never send the quote back.
const cfg = $('Config').first().json;
const s5 = $('Step 5: Rules: schema, totals, values on page').first().json;
const q = s5.quote, pages = s5.pages, source = s5.source;
const msg = $('Read the message').first().json;
const fingerprint = $('Step 2: Fingerprint the attachment').first().json.fingerprint;
const vendors = $('Read vendor records').first().json.items || [];
const lastPaid = $('Read last prices paid').first().json.items || [];
const earlier = $('Read rows with this quote number').first().json.items || [];
const iso = d => d.toISOString().slice(0, 10);
const today = new Date(iso(new Date()) + 'T00:00:00Z');
const addWorkingDays = (d, n) => { let x = new Date(d), k = 0; while (k < n) { x = new Date(x.getTime() + 86400000); if (x.getUTCDay() % 6 !== 0) k++; } return x; };
const parseDate = s => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s).trim()); const t = m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : Date.parse(String(s) + ' UTC'); return Number.isFinite(t) ? new Date(t) : null; };
const flags = [];

// Step 6: freight is "included" only if its page carries one of the listed delivery terms.
let freight = 'blank', freightAmount = null;
if (norm(q.freight.value) === 'included') {
  const page = q.freight.page ? norm(pages[q.freight.page - 1]) : '';
  if ((cfg.delivery_terms || []).some(t => page.includes(norm(t)))) freight = 'included';
  else flags.push('freight "included" without a listed delivery term');
} else if (q.freight.value !== '') {
  freightAmount = num(q.freight.value);
  if (Number.isFinite(freightAmount)) freight = 'amount'; else flags.push('freight unreadable');
}

// Step 7: match the supplier to the vendor record.
const vendor = vendors.find(v => norm(v.name) === norm(q.supplier.value));
if (!vendor) flags.push('unknown supplier');

// Step 8: flag another currency.
if (q.currency.value === '') flags.push('currency not stated');
else if (!(cfg.sheet_currency || []).some(c => norm(c) === norm(q.currency.value))) flags.push('other currency');

// Step 9: a quote inside R11.2's margin.
const validUntil = q.valid_until.value ? parseDate(q.valid_until.value) : null;
if (!q.valid_until.value) flags.push('no valid-until date');
else if (!validUntil) flags.push('valid-until unreadable');
else if (validUntil < addWorkingDays(today, cfg.margin_working_days)) flags.push('expires within margin');

const subtotal = num(q.subtotal.value);
const rows = q.lines.map((l, i) => {
  const lineFlags = [];
  // Step 8: convert to base units; landed cost per base unit, or "cannot compute" without freight.
  const unit = (cfg.unit_table || []).find(u => norm(u.unit) === norm(l.unit.value));
  const qty = num(l.quantity.value), price = num(l.unit_price.value), total = num(l.line_total.value);
  let baseQty = null, basePrice = null, landed = 'cannot compute';
  if (!unit) lineFlags.push('unit not in table');
  else if (Number.isFinite(qty) && Number.isFinite(price) && qty > 0) {
    baseQty = qty * Number(unit.factor);
    basePrice = cents(price / Number(unit.factor));
    if (freight === 'included') landed = cents(total / baseQty);
    if (freight === 'amount') landed = cents((total + freightAmount * total / subtotal) / baseQty);
  } else lineFlags.push('quantity or unit price unreadable');
  // Step 9: over the set share off the last price paid.
  const last = lastPaid.find(p => norm(p.item) === norm(l.description.value));
  if (last && basePrice !== null && Math.abs(basePrice - Number(last.price_per_base_unit)) / Number(last.price_per_base_unit) > cfg.price_off_pct / 100) {
    lineFlags.push(`over ${cfg.price_off_pct}% off last price paid`);
  }
  const page = Object.fromEntries([...['supplier', 'quote_number', 'quote_date', 'valid_until', 'currency', 'freight', 'subtotal'].map(k => [k, q[k].page]),
    ...Object.entries(l).map(([k, f]) => [k, f.page])]);
  return {
    id: `${fingerprint.slice(0, 12)}-${i + 1}`,
    supplier: q.supplier.value, vendor_id: vendor ? vendor.id : null, quote_number: q.quote_number.value,
    quote_date: q.quote_date.value, valid_until: q.valid_until.value, currency: q.currency.value,
    line: i + 1, description: l.description.value, quantity: l.quantity.value, unit: l.unit.value,
    unit_price: l.unit_price.value, line_total: l.line_total.value,
    base_unit: unit ? unit.base_unit : null, base_quantity: baseQty, price_per_base_unit: basePrice,
    freight: freight === 'amount' ? q.freight.value : freight === 'included' ? 'included' : '',
    landed_cost_per_base_unit: landed, flags: [...flags, ...lineFlags], page,
    message_link: msg.link || null, message_id: msg.id, fingerprint, filled_by: source,
    // Every AI-filled row starts unchecked (step 12); a response table is read by rule.
    check_status: source === 'AI' ? 'unchecked' : 'checked', status: 'current',
  };
});

// Step 9: a revision supersedes the older row.
const supersedes = earlier.filter(r => norm(r.supplier) === norm(q.supplier.value) && r.fingerprint !== fingerprint && r.status !== 'superseded').map(r => r.id);
return rows.map(r => ({ json: Object.assign(r, { supersedes }) }));
"""

WRITTEN_JS = r"""
// Step 10 succeeded only if every row was written; otherwise the failed write marks the key.
const planned = $('Rules: steps 6 to 9').all();
const written = $input.all();
if (written.length !== planned.length) return [];
const flags = [...new Set(planned.flatMap(i => i.json.flags))];
return [{ json: { rows: written.length, supersedes: planned[0].json.supersedes, flags, source: planned[0].json.filled_by } }];
"""

SHIFT_JS = r"""
// Step 12: tell the stockroom lead which AI-filled rows still wait for a check against their page.
const rows = $('Read unchecked AI-filled rows').first().json.items || [];
if (!rows.length) return [];
const quotes = [...new Set(rows.map(r => `${r.supplier} ${r.quote_number} (${r.message_link || r.message_id})`))];
return [{ json: { count: rows.length, text: `${rows.length} AI-filled rows to check against their pages, then mark "checked": ${quotes.join('; ')}` } }];
"""


def _independent(w: Workflow, *names: str) -> None:
    """Postgres nodes that may receive several items run one query per item."""
    for n in w.nodes:
        if n["name"] in names:
            n["parameters"]["options"]["queryBatching"] = "independently"


def build() -> Workflow:
    w = Workflow("R11.1", "R11.1 Collect supplier quotes into one normalized comparison")
    w.webhook(T, "r11-1-new-quote-message", "Your quotes mailbox calls this for each new message. Body: {message_id}.", pos=[0, 0])
    w.schedule(S, 7, "Step 12: once a shift, the AI-filled rows still unchecked.", pos=[0, 700])
    w.config("Config", {
        "mailbox_url": "https://<your quotes mailbox API>",
        "vendors_url": "https://<your vendor-record export API>",
        "sheet_url": "https://<your comparison sheet API>",
        "messaging_url": "https://<your messaging API>",
        "response_table_marker": {"cell": "<cell holding the response table's title>", "text": "<your response table title>"},
        "response_table_cells": {"supplier": "<cell>", "quote_number": "<cell>", "quote_date": "<cell>", "valid_until": "<cell>",
                                 "currency": "<cell>", "freight": "<cell>", "subtotal": "<cell>"},
        "response_table_lines": {"first_row": "<first line row>",
                                 "columns": {"description": "<column>", "quantity": "<column>", "unit": "<column>",
                                             "unit_price": "<column>", "line_total": "<column>"}},
        "delivery_terms": ["<your delivery terms that include freight>"],
        "sheet_currency": ["<your sheet currency, as quotes print it>"],
        "unit_table": [{"unit": "<unit as quoted>", "base_unit": "<base unit>", "factor": 1}],
        "margin_working_days": 5,
        "price_off_pct": 30,
        "stockroom_lead": "<your stockroom lead>",
        "editor": "<your workflow editor>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 300])
    w.connect(T, "Config")
    w.connect(S, "Config")
    w.if_("Each shift?", f"={{{{ $('{S}').isExecuted }}}}", pos=[520, 300])
    w.connect("Config", "Each shift?")

    # ---- steps 1 to 3 -----------------------------------------------------------
    w.http("Read the message", "GET", f"={{{{ {CFG}.mailbox_url }}}}/messages/{{{{ $('{T}').first().json.body.message_id }}}}",
           write=False, error_output=False, pos=[780, 0], notes="With each attachment's text by page, or its cells for a spreadsheet.")
    w.code(S1, READABLE_JS, mode="runOnceForAllItems", pos=[1040, 0])
    w.if_("Readable?", "={{ $json.readable }}", pos=[1300, 0])
    w.connect("Each shift?", "Read the message", output=1)
    w.chain("Read the message", S1, "Readable?")
    w.exception("Step 1: Exception queue: no readable attachment", f"{MSG}.id", "no readable attachment",
                f"$('{S1}').first().json.detail", f"{CFG}.stockroom_lead", pos=[1560, -200])
    w.decision_log("Decision log: not read", f"{MSG}.id", "'exception queue: ' + " + f"$('{S1}').first().json.detail",
                   "JSON.stringify({ attachments: (" + MSG + ".attachments || []).length })", pos=[1820, -200])
    w.connect("Readable?", "Step 1: Exception queue: no readable attachment", output=1)
    w.connect("Step 1: Exception queue: no readable attachment", "Decision log: not read")

    w.node("Step 2: Fingerprint the attachment", "n8n-nodes-base.crypto", 2,
           {"action": "hash", "type": "SHA256", "value": "={{ $json.content }}", "dataPropertyName": "fingerprint", "encoding": "hex"},
           pos=[1560, 0], notes="SHA-256 of the attachment itself, so a forwarded copy has the same key.")
    w.reserve_key("Step 2: Reserve key", FP, pos=[1820, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[2080, 0])
    w.noop("Duplicate: stop", pos=[2340, -160], notes="This attachment was read before.")
    w.connect("Readable?", "Step 2: Fingerprint the attachment", output=0)
    w.chain("Step 2: Fingerprint the attachment", "Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)
    w.if_("Step 3: Rule: response table?", f"={{{{ $('{S1}').first().json.kind }}}}", op="equals", right="table", pos=[2340, 0])
    w.connect("New key?", "Step 3: Rule: response table?", output=0)
    w.code(S3, TABLE_JS, mode="runOnceForAllItems", pos=[2600, -120], notes="Skips step 4.")
    w.connect("Step 3: Rule: response table?", S3, output=0)

    # ---- step 4: the AI step ------------------------------------------------------
    vars_js = ("{ quote_pages: $('" + S1 + "').first().json.attachment.pages"
               ".map((p, i) => `--- page ${i + 1} ---\\n${p}`).join('\\n') }")
    build_n, call = ai_step(w, "Step 4", ROOT / "recipes/R11.1/prompts/extract-quote.md", vars_js,
                            max_tokens=2048, tries=4, pos_build=[2600, 120], pos_call=[2860, 120])
    w.connect("Step 3: Rule: response table?", build_n, output=1)

    # ---- step 5 and step 11 ------------------------------------------------------
    w.code(S5, STEP5_JS, mode="runOnceForAllItems", pos=[3120, 0], notes="The rule decides, not the AI.")
    w.connect(S3, S5)
    w.connect(call, S5, output=0)
    w.code("Step 11: AI error", "return [{ json: { ok: false, problem: 'AI error after three retries: ' + String(($json.error && $json.error.message) || '') } }];",
           mode="runOnceForAllItems", pos=[3120, 240])
    w.connect(call, "Step 11: AI error", output=1)
    w.if_("Step 5 passed?", "={{ $json.ok }}", pos=[3380, 0])
    w.connect(S5, "Step 5 passed?")
    w.connect("Step 11: AI error", "Step 5 passed?")
    w.exception("Step 11: Exception queue: manual entry", f"{MSG}.id", "needs manual entry",
                "$('Step 5 passed?').first().json.problem + ' (' + " + f"$('{S1}').first().json.name + ')'",
                f"{CFG}.stockroom_lead", pos=[3640, 320])
    w.finish_key("Mark key done: manual entry", FP, "done", "'exception queue: ' + $('Step 5 passed?').first().json.problem", pos=[3900, 320])
    w.decision_log("Decision log: manual entry", f"{MSG}.id", "'manual entry: ' + $('Step 5 passed?').first().json.problem",
                   f"JSON.stringify({{ fingerprint: {FP}, step5: 'failed' }})", pos=[4160, 320])
    w.connect("Step 5 passed?", "Step 11: Exception queue: manual entry", output=1)
    w.chain("Step 11: Exception queue: manual entry", "Mark key done: manual entry", "Decision log: manual entry")

    # ---- steps 6 to 10 -----------------------------------------------------------
    w.http("Read vendor records", "GET", f"={{{{ {CFG}.vendors_url }}}}/records", query={"_wrap": "1"},
           write=False, error_output=False, pos=[3640, 0])
    w.http("Read last prices paid", "GET", f"={{{{ {CFG}.vendors_url }}}}/last_prices", query={"_wrap": "1"},
           write=False, error_output=False, pos=[3900, 0])
    w.http("Read rows with this quote number", "GET", f"={{{{ {CFG}.sheet_url }}}}/rows",
           query={"_wrap": "1", "quote_number": f"={{{{ $('{S5}').first().json.quote.quote_number.value }}}}"},
           write=False, error_output=False, pos=[4160, 0], notes="For step 9: an earlier revision of this quote.")
    w.code(S69, STEPS_6_9_JS, mode="runOnceForAllItems", pos=[4420, 0], notes="One item per quote line, with its flags.")
    w.connect("Step 5 passed?", "Read vendor records", output=0)
    w.chain("Read vendor records", "Read last prices paid", "Read rows with this quote number", S69)
    w.http("Step 10: Write one row per line", "POST", f"={{{{ {CFG}.sheet_url }}}}/rows",
           body="={{ JSON.stringify(Object.fromEntries(Object.entries($json).filter(([k]) => k !== 'supersedes'))) }}",
           write=True, pos=[4680, 0], notes="With flags, page and message link. A write: never retried.")
    w.code("All rows written?", WRITTEN_JS, mode="runOnceForAllItems", pos=[4940, 0])
    w.chain(S69, "Step 10: Write one row per line", "All rows written?")
    w.if_("Revision?", "={{ $json.supersedes.length > 0 }}", pos=[5200, 0])
    w.connect("All rows written?", "Revision?")
    w.code("Older rows", "return $('All rows written?').first().json.supersedes.map(id => ({ json: { id } }));",
           mode="runOnceForAllItems", pos=[5460, -160])
    w.http("Step 9: Mark the older revision superseded", "PATCH", f"={{{{ {CFG}.sheet_url }}}}/rows/{{{{ $json.id }}}}",
           body=f"={{{{ JSON.stringify({{ status: 'superseded', superseded_by: {FP} }}) }}}}", write=True, pos=[5720, -160])
    w.code("Superseded marked", "return [{ json: $('All rows written?').first().json }];", mode="runOnceForAllItems", pos=[5980, -160])
    w.connect("Revision?", "Older rows", output=0)
    w.chain("Older rows", "Step 9: Mark the older revision superseded", "Superseded marked")
    done = "$('All rows written?').first().json"
    w.finish_key("Mark key done", FP, "done", f"'rows written: ' + {done}.rows", pos=[6240, 0])
    w.connect("Revision?", "Mark key done", output=1)
    w.connect("Superseded marked", "Mark key done")
    w.decision_log("Decision log", f"{MSG}.id", f"'rows written: ' + {done}.rows",
                   f"JSON.stringify({{ fingerprint: {FP}, source: {done}.source, flags: {done}.flags, superseded: {done}.supersedes }})",
                   pos=[6500, 0])
    w.connect("Mark key done", "Decision log")

    w.finish_key("Mark key failed", FP, "failed", "'write failed: ' + ($json.error && $json.error.message || 'unknown')", pos=[5200, 320])
    w.exception("Exception queue: write failed", f"{MSG}.id", "write failed",
                "'Comparison sheet write failed; check the sheet before redoing it, never retried'", f"{CFG}.editor", pos=[5460, 320])
    w.connect("Step 10: Write one row per line", "Mark key failed", output=1)
    w.connect("Step 9: Mark the older revision superseded", "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- step 12: each shift --------------------------------------------------------
    w.http("Read unchecked AI-filled rows", "GET", f"={{{{ {CFG}.sheet_url }}}}/rows",
           query={"_wrap": "1", "filled_by": "AI", "check_status": "unchecked", "status": "current"},
           write=False, error_output=False, pos=[780, 700])
    w.code("Rule: unchecked rows?", SHIFT_JS, mode="runOnceForAllItems", pos=[1040, 700])
    w.http("Step 12: Tell the stockroom lead", "POST", f"={{{{ {CFG}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: {CFG}.stockroom_lead, subject: 'Quote rows to check this shift', text: $json.text }}) }}}}",
           write=True, error_output=False, pos=[1300, 700], notes="The lead compares each row with its page and marks it \"checked\".")
    w.connect("Each shift?", "Read unchecked AI-filled rows", output=0)
    w.chain("Read unchecked AI-filled rows", "Rule: unchecked rows?", "Step 12: Tell the stockroom lead")

    _independent(w, "Mark key failed", "Exception queue: write failed")
    return w
