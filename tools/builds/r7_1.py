"""R7.1 Extract supplier invoice fields into a structured record.

Source: book Chapter 7, recipe R7.1, build steps 1 to 6 (recipes/R7.1/build-spec.md);
AI step: recipes/R7.1/prompts/extract-invoice.md. Nothing the AI extracts is saved as
"ready" until every rule passes; anything else is saved "flagged" and added to R7.4's queue.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

T = "Step 1: New attachment"
EV = f"$('{T}').item.json.body"
ATT = "$('Step 1: Read the attachment').first().json"
REC = "$('Step 6: Record to save').first().json"

FIELDS = ["supplier", "invoice_number", "order_number", "bank_account", "invoice_date", "type",
          "invoice_count", "lines", "freight", "tax", "total"]

# Every path that saves a record hands "Step 6: Record to save" the same shape:
# { record: {...}, key: <duplicate key or ''>, decision, rules }.
RECORD_JS = r"""
function record(att, status, reasonCode, reasons, fields) {
  const f = fields || {};
  const out = { status, reason_code: reasonCode || null, reasons: reasons || [],
    attachment_id: att.id, message_id: att.message_id, filename: att.filename, supplier_id: f.supplier_id || null };
  for (const k of FIELDS) out[k] = (k in f) ? f[k] : null;
  out.settles = null;
  return out;
}
"""

FILE_JS = r"""
// Step 2: only a PDF or an image goes to the AI step.
const cfg = $('Config').first().json;
const att = $('Step 1: Read the attachment').first().json;
const type = String(att.content_type || '').toLowerCase();
return [{ json: { pdf_or_image: cfg.file_types.map(t => t.toLowerCase()).includes(type), content_type: type } }];
"""

NOT_FILE_JS = f"const FIELDS = {json.dumps(FIELDS)};\n" + RECORD_JS + r"""
// Step 2: anything not a PDF or image needs a person; no AI call.
const att = $('Step 1: Read the attachment').first().json;
const ct = $('Step 2: Rule: PDF or image?').first().json.content_type || 'none';
return [{ json: { record: record(att, 'flagged', 'needs a person', ['not a PDF or image: ' + ct]), key: '',
  decision: 'flagged: needs a person', rules: { file: 'not a PDF or image' } } }];
"""

ATTACH_JS = r"""
// Step 3: the attachment goes to the model as a document or image block, beside the prompt's text.
const att = $('Step 1: Read the attachment').first().json;
const request = $json.request;
const media = String(att.content_type).toLowerCase();
const source = { type: 'base64', media_type: media, data: att.content_base64 };
const block = media === 'application/pdf' ? { type: 'document', source } : { type: 'image', source };
request.messages[0].content = [block, { type: 'text', text: request.messages[0].content }];
return { json: { request } };
"""

AI_ERROR_JS = f"const FIELDS = {json.dumps(FIELDS)};\n" + RECORD_JS + r"""
// Step 3: an AI error after three tries is flagged for a person, who keys the invoice.
const att = $('Step 1: Read the attachment').first().json;
const msg = String(($json.error && $json.error.message) || 'AI call failed');
return [{ json: { record: record(att, 'flagged', 'needs a person', ['AI error after three tries']), key: '',
  decision: 'flagged: needs a person', rules: { ai: 'error', detail: msg.slice(0, 200) } } }];
"""

RULES_JS = f"const FIELDS = {json.dumps(FIELDS)};\n" + AI_PARSE_JS + RECORD_JS + r"""
// Step 4: one invoice, required fields, lines summing to the total, a date within the limit, a listed supplier.
const cfg = $('Config').first().json;
const att = $('Step 1: Read the attachment').first().json;
const p = parseAi($('Step 3: AI call').first().json, FIELDS, { type: ['invoice', 'credit note', 'other', null] });
const num = v => v === null || (typeof v === 'number' && isFinite(v));
const str = v => v === null || typeof v === 'string';
let problem = p.ok ? null : p.problem;
if (!problem) {
  const v = p.value;
  for (const k of ['supplier', 'invoice_number', 'order_number', 'bank_account', 'invoice_date']) if (!str(v[k])) problem = `${k} is not text`;
  for (const k of ['freight', 'tax', 'total']) if (!num(v[k])) problem = `${k} is not a number`;
  if (!(v.invoice_count === null || Number.isInteger(v.invoice_count))) problem = 'invoice_count is not a whole number';
  const LINE = ['description', 'qty', 'unit_price', 'amount'];
  const isLine = x => x && typeof x === 'object' && !Array.isArray(x) && Object.keys(x).length === LINE.length
    && LINE.every(k => k in x) && str(x.description) && num(x.qty) && num(x.unit_price) && num(x.amount);
  if (!(v.lines === null || (Array.isArray(v.lines) && v.lines.every(isLine)))) problem = 'lines is not a list of {description, qty, unit_price, amount}';
  if (v.invoice_date !== null && !/^\d{4}-\d{2}-\d{2}$/.test(v.invoice_date)) problem = 'invoice_date is not YYYY-MM-DD';
}
if (problem) {
  return [{ json: { record: record(att, 'flagged', 'needs a person', ['AI output failed the check: ' + problem]), key: '',
    decision: 'flagged: needs a person', rules: { ai: 'failed the check', detail: problem } } }];
}
const v = p.value;
// Each line is saved as { description, qty, unit_price, amount }, the shape R7.2 pairs and checks.
if (Array.isArray(v.lines)) v.lines = v.lines.map(x => ({ description: x.description, qty: x.qty, unit_price: x.unit_price, amount: x.amount }));
const reasons = [];
const rules = {};

// One invoice: a single invoice or credit note in the file.
rules.one_invoice = v.invoice_count === 1 && ['invoice', 'credit note'].includes(v.type) ? 'passed' : `failed: ${v.invoice_count} ${v.type}`;
if (rules.one_invoice !== 'passed') reasons.push(v.invoice_count === 1 ? 'not an invoice or credit note' : `invoice count ${v.invoice_count}`);

// Required fields.
const missing = cfg.required_fields.filter(k => v[k] === null || v[k] === '' || (Array.isArray(v[k]) && !v[k].length));
rules.required = missing.length ? 'missing ' + missing.join(', ') : 'passed';
if (missing.length) reasons.push('missing ' + missing.join(', '));

// The line amounts, freight and tax sum to the total.
if (Array.isArray(v.lines) && v.lines.some(x => x.amount === null)) {
  rules.sum = 'a line has no amount';
  reasons.push('a line has no amount');
} else if (Array.isArray(v.lines) && v.total !== null) {
  const sum = v.lines.reduce((s, x) => s + x.amount, 0) + (v.freight || 0) + (v.tax || 0);
  const ok = Math.abs(Math.round(sum * 100) - Math.round(v.total * 100)) <= Math.round(cfg.sum_tolerance * 100);
  rules.sum = ok ? 'passed' : `line amounts, freight and tax make ${Math.round(sum * 100) / 100}, total ${v.total}`;
  if (!ok) reasons.push('lines do not sum to the total');
} else rules.sum = 'not checked';

// Invoice date no older than the limit and not in the future.
if (v.invoice_date) {
  const today = new Date(new Date().toISOString().slice(0, 10) + 'T00:00:00Z');
  const age = Math.round((today - new Date(v.invoice_date + 'T00:00:00Z')) / 86400000);
  const ok = age >= 0 && age <= cfg.max_age_days;
  rules.date = ok ? 'passed' : `${age} days old`;
  if (!ok) reasons.push(age < 0 ? 'invoice date in the future' : `invoice date over ${cfg.max_age_days} days old`);
} else rules.date = 'not checked';

// A listed supplier.
const norm = s => String(s || '').toLowerCase().replace(/\s+/g, ' ').trim();
const listed = ($('Step 4: Read supplier list').first().json.items || []).find(s => norm(s.name) === norm(v.supplier));
rules.supplier = listed ? 'listed' : 'not listed';

const fields = Object.assign({}, v, { supplier_id: listed ? listed.id : null });
const reasonCode = !listed ? 'unknown supplier' : (reasons.length ? 'needs a person' : null);
if (!listed) reasons.unshift('supplier not on the supplier list');
const status = reasonCode ? 'flagged' : 'ready';
// Step 5's duplicate key: supplier ID plus invoice number, when both are known.
const key = listed && v.invoice_number ? `${listed.id}:${v.invoice_number}` : '';
return [{ json: { record: record(att, status, reasonCode, reasons, fields), key,
  decision: status === 'ready' ? 'ready' : 'flagged: ' + reasonCode, rules } }];
"""

SETTLE_JS = r"""
// Step 6: a credit note joins the item it settles: the supplier's invoice on the same order.
const prev = $('Step 4: Rule: checks').first().json;
const out = JSON.parse(JSON.stringify(prev));
const invoices = ($('Step 6: Read the item it settles').first().json.items || []).filter(r => r.type === 'invoice');
if (invoices.length) {
  out.record.settles = invoices[invoices.length - 1].id;
  out.rules.settles = 'joined ' + out.record.settles;
} else {
  out.record.status = 'flagged';
  out.record.reason_code = out.record.reason_code || 'needs a person';
  out.record.reasons.push('credit note settles no item on the review list');
  out.rules.settles = 'no item found';
  out.decision = 'flagged: ' + out.record.reason_code;
}
return [{ json: out }];
"""


def build() -> Workflow:
    w = Workflow("R7.1", "R7.1 Extract supplier invoice fields into a structured record")
    w.webhook(T, "r7-1-attachment", "Your AP mailbox calls this for each attachment that arrives. Body: {message_id, attachment_id}.", pos=[0, 0])
    w.config("Config", {
        "mailbox_url": "https://<your AP mailbox API>",
        "review_url": "https://<your review list API>",
        "suppliers_url": "https://<your supplier list API>",
        "queue_url": "https://<your R7.4 queue list API>",
        "file_types": ["application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"],
        "required_fields": ["supplier", "invoice_number", "invoice_date", "type", "lines", "total"],
        "max_age_days": 60,
        "sum_tolerance": 0.01,
        "ap_reviewer": "<your AP reviewer>",
        "workflow_owner": "<your workflow owner>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 0])
    w.http("Step 1: Read the attachment", "GET",
           f"={{{{ $('Config').item.json.mailbox_url }}}}/attachments/{{{{ {EV}.attachment_id }}}}",
           write=False, pos=[520, 0], notes="Retries three times; a mailbox error goes to the AP reviewer to key.")
    w.exception("Exception queue: mailbox error", f"{EV}.attachment_id", "mailbox error",
                "'Attachment could not be read after three tries; key it by hand'", "$('Config').item.json.ap_reviewer", pos=[780, 300])
    w.chain(T, "Config", "Step 1: Read the attachment")
    w.connect("Step 1: Read the attachment", "Exception queue: mailbox error", output=1)

    w.code("Step 2: Rule: PDF or image?", FILE_JS, mode="runOnceForAllItems", pos=[780, 0])
    w.if_("PDF or image?", "={{ $json.pdf_or_image }}", pos=[1040, 0])
    w.code("Step 2: Needs a person", NOT_FILE_JS, mode="runOnceForAllItems", pos=[1300, -300])
    w.connect("Step 1: Read the attachment", "Step 2: Rule: PDF or image?")
    w.connect("Step 2: Rule: PDF or image?", "PDF or image?")
    w.connect("PDF or image?", "Step 2: Needs a person", output=1)

    build_, call = ai_step(w, "Step 3", ROOT / "recipes/R7.1/prompts/extract-invoice.md",
                           f"{{ document: {ATT}.filename }}", max_tokens=4096, tries=3,
                           pos_build=[1300, 0], pos_call=[1820, 0])
    w.code("Step 3: Attach the document", ATTACH_JS, pos=[1560, 0],
           notes="Sends the PDF or image itself; the prompt's {{document}} names the file.")
    w.connections[build_]["main"][0] = []
    w.chain(build_, "Step 3: Attach the document", call)
    w.connect("PDF or image?", build_, output=0)
    w.code("Step 3: AI error", AI_ERROR_JS, mode="runOnceForAllItems", pos=[2080, 300])
    w.connect(call, "Step 3: AI error", output=1)

    w.http("Step 4: Read supplier list", "GET", "={{ $('Config').item.json.suppliers_url }}/suppliers",
           query={"_wrap": "1"}, write=False, error_output=False, pos=[2080, 0])
    w.code("Step 4: Rule: checks", RULES_JS, mode="runOnceForAllItems", pos=[2340, 0], notes="The rules decide, not the AI.")
    w.connect(call, "Step 4: Read supplier list", output=0)
    w.connect("Step 4: Read supplier list", "Step 4: Rule: checks")

    w.if_("Duplicate key known?", "={{ $json.key }}", op="notEmpty", pos=[2600, 0],
          notes="The key needs a listed supplier and an invoice number; without them the record is flagged anyway.")
    w.reserve_key("Step 5: Reserve key", f"$('Step 4: Rule: checks').first().json.key", pos=[2860, -160])
    w.if_("New key?", "={{ $json.is_new }}", pos=[3120, -160])
    w.decision_log("Step 5: Log duplicate", f"{EV}.attachment_id", "'duplicate: stopped'",
                   "JSON.stringify({ key: $('Step 4: Rule: checks').first().json.key, duplicate: true })", pos=[3380, -360])
    w.connect("Step 4: Rule: checks", "Duplicate key known?")
    w.connect("Duplicate key known?", "Step 5: Reserve key", output=0)
    w.connect("Step 5: Reserve key", "New key?")
    w.connect("New key?", "Step 5: Log duplicate", output=1)

    w.if_("Credit note?", "={{ $('Step 4: Rule: checks').first().json.record.type }}", op="equals", right="credit note", pos=[3380, -160])
    w.connect("New key?", "Credit note?", output=0)
    rec4 = "$('Step 4: Rule: checks').first().json.record"
    w.http("Step 6: Read the item it settles", "GET", "={{ $('Config').item.json.review_url }}/records",
           query={"_wrap": "1", "supplier_id": f"={{{{ {rec4}.supplier_id }}}}", "order_number": f"={{{{ {rec4}.order_number }}}}"},
           write=False, error_output=False, pos=[3640, -300])
    w.code("Step 6: Rule: join the item it settles", SETTLE_JS, mode="runOnceForAllItems", pos=[3900, -300])
    w.connect("Credit note?", "Step 6: Read the item it settles", output=0)
    w.connect("Step 6: Read the item it settles", "Step 6: Rule: join the item it settles")

    w.code("Step 6: Record to save",
           "// Paths that pass through an If or the key reservation carry the rule's output by reference.\n"
           "const j = $input.first().json;\n"
           "return [{ json: j.record ? j : $('Step 4: Rule: checks').first().json }];", mode="runOnceForAllItems", pos=[4160, 0],
           notes="Every path meets here: ready, flagged by a rule, not a PDF or image, or an AI error.")
    for src, out in [("Step 6: Rule: join the item it settles", 0), ("Credit note?", 1), ("Duplicate key known?", 1),
                     ("Step 2: Needs a person", 0), ("Step 3: AI error", 0)]:
        w.connect(src, "Step 6: Record to save", output=out)

    w.http("Step 6: Save the record", "POST", "={{ $('Config').item.json.review_url }}/records",
           body="={{ JSON.stringify($json.record) }}", write=True, pos=[4420, 0],
           notes="Saved \"ready\" or \"flagged\"; a write, never retried.")
    w.if_("Flagged?", f"={{{{ {REC}.record.status }}}}", op="equals", right="flagged", pos=[4680, 0])
    w.http("Step 6: Add to the R7.4 queue", "POST", "={{ $('Config').item.json.queue_url }}/items",
           body=("={{ JSON.stringify({ invoice_id: $('Step 6: Save the record').first().json.id, "
                 f"supplier: {REC}.record.supplier, supplier_id: {REC}.record.supplier_id, "
                 f"reason_code: {REC}.record.reason_code, details: {REC}.record.reasons.join('; '), "
                 "raised_by: 'R7.1', raised_at: $now.toISODate(), status: 'open' }) }}"),
           write=True, pos=[4940, 160], notes="R7.4 assigns the owner and the clock.")
    w.chain("Step 6: Record to save", "Step 6: Save the record", "Flagged?")
    w.connect("Flagged?", "Step 6: Add to the R7.4 queue", output=0)

    w.finish_key("Mark key done", f"{REC}.key", "done", f"{REC}.record.status", pos=[5200, 0])
    w.decision_log("Decision log", f"{EV}.attachment_id", f"{REC}.decision",
                   f"JSON.stringify({REC}.rules)", pos=[5460, 0])
    w.connect("Flagged?", "Mark key done", output=1)
    w.connect("Step 6: Add to the R7.4 queue", "Mark key done")
    w.connect("Mark key done", "Decision log")

    w.finish_key("Mark key failed", f"{REC}.key", "failed", "'write failed: ' + (($json.error && $json.error.message) || 'unknown')", pos=[5200, 400])
    w.exception("Exception queue: write failed", f"{EV}.attachment_id", "write failed",
                "'Record save or queue write failed, never retried; save it by hand or close the key'",
                "$('Config').item.json.workflow_owner", pos=[5460, 400])
    w.connect("Step 6: Save the record", "Mark key failed", output=1)
    w.connect("Step 6: Add to the R7.4 queue", "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")
    return w
