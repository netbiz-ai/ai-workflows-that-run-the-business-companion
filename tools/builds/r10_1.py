"""R10.1 Turn a sale into a complete work order, with restricted fields protected.

Source: book Chapter 10, recipe R10.1, build steps 1 to 10 and Table 10.1
(recipes/R10.1/build-spec.md); AI step: recipes/R10.1/prompts/extract-notes.md.

MASK_JS is step 4's masking rule. R10.2 (step 4) and R10.3 (step 6) import it from
here, because the book makes them use "R10.1's step 4 rule".
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, Workflow, ai_step  # noqa: E402

T = "Step 1: Sale with delivery"
CLEARED = "Step 9: Task cleared"
M = "Step 9: Each morning"
EV = "$('Config').item.json.body"
KEY = f"[{EV}.source, {EV}.order_id, {EV}.visit_type, {EV}.visit_number].join(':')"
KEEP = "Step 3: Keep only the Table 10.1 fields"
MASK = "Step 4: Rule: mask codes in the notes"
CHECK = "Step 6: Rules: check every field"

# Step 4 of R10.1, shared by R10.2 and R10.3.
MASK_JS = r"""
// R10.1 step 4: mask any code (digits, letters, "*" or "#") within three words of a
// masking-list word, and any bare run of four or more digits, or digits with "*" or "#",
// not near a floor, unit or street word. "Near" means within three words in the same
// clause (commas and full stops end a clause), so "Entry is 4821, third floor" is masked.
function maskCodes(text, cfg) {
  const s = String(text == null ? '' : text);
  const toks = [];
  const re = /[A-Za-z0-9*#]+/g;
  let m, clause = 0, last = 0;
  while ((m = re.exec(s))) {
    if (/[,.;:!?\n]/.test(s.slice(last, m.index))) clause++;
    toks.push({ t: m[0], lo: m[0].toLowerCase(), i: m.index, end: m.index + m[0].length, clause });
    last = m.index + m[0].length;
  }
  const wordIs = (tok, w) => tok.lo === w || tok.lo === w + 's';
  const anchors = [];
  for (const entry of cfg.masking_list || []) {
    const parts = String(entry).toLowerCase().split(/\s+/).filter(Boolean);
    for (let i = 0; i + parts.length <= toks.length; i++) {
      if (parts.every((p, k) => wordIs(toks[i + k], p))) anchors.push([i, i + parts.length - 1]);
    }
  }
  const addrWords = (cfg.address_words || []).map(w => String(w).toLowerCase());
  const isAddr = tok => addrWords.some(w => wordIs(tok, w));
  const near = (j, a, b) => (j < a ? a - j : j - b) <= 3;
  const hide = new Set();
  toks.forEach((tok, j) => {
    const codeLike = /[0-9*#]/.test(tok.t);
    if (codeLike && anchors.some(([a, b]) => j < a || j > b ? near(j, a, b) : false)) hide.add(j);
    const bare = /^\d{4,}$/.test(tok.t) || (/\d/.test(tok.t) && /[*#]/.test(tok.t) && /^[\d*#]+$/.test(tok.t));
    if (bare && !toks.some((o, k) => o.clause === tok.clause && Math.abs(k - j) <= 3 && isAddr(o))) hide.add(j);
  });
  let out = '', pos = 0;
  [...hide].sort((a, b) => a - b).forEach(j => { out += s.slice(pos, toks[j].i) + cfg.mask_token; pos = toks[j].end; });
  out += s.slice(pos);
  return { text: out, masked: hide.size > 0 };
}
"""

KEEP_JS = r"""
// Step 3: read only Table 10.1's fields. The restricted access-code field is never copied;
// your service account should not be able to read it at all.
const s = $('Step 3: Read the sale').first().json;
const pick = (o, ks) => Object.fromEntries(ks.filter(k => o && o[k] !== undefined).map(k => [k, o[k]]));
return [{ json: {
  customer: pick(s.customer, ['name', 'phone', 'channel']),
  address: pick(s.address, ['building', 'unit', 'floor', 'street', 'postcode']),
  notes: String(s.notes || ''),
  product: s.product || null,
  installation: s.installation === true,
  paid: s.paid === true,
  trade_terms: s.trade_terms || null,
  delivery_date: s.delivery_date || null,
  salesperson: s.salesperson || null,
  updated_at: s.updated_at == null ? null : String(s.updated_at),
} }];
"""

STEP4_JS = MASK_JS + r"""
const cfg = $('Config').first().json;
const m = maskCodes($('""" + KEEP + r"""').first().json.notes, cfg);
return [{ json: { masked_notes: m.text, code_in_notes: m.masked } }];
"""

CHECK_JS = AI_PARSE_JS + r"""
// Step 6: rules, never the AI, decide whether the work order is complete (Table 10.1).
const cfg = $('Config').first().json;
const ev = $('Config').first().json.body;
const sale = $('""" + KEEP + r"""').first().json;
const mask = $('""" + MASK + r"""').first().json;
const notes = mask.masked_notes;
const key = [ev.source, ev.order_id, ev.visit_type, ev.visit_number].join(':');
const reply = $input.first().json;
const lower = v => String(v == null ? '' : v).toLowerCase();
const words = v => lower(v).split(/[^a-z0-9']+/).filter(Boolean);
const gaps = [];
const rules = {};

// Step 5's output: used only if it parses and fits the schema.
let ai = null;
if (reply.error || !reply.content) { rules.ai = 'error'; gaps.push('AI error: details not read from the notes'); }
else {
  const p = parseAi(reply, ['building', 'unit', 'floor', 'stairs', 'lift', 'parking', 'window']);
  if (p.ok) { ai = p.value; rules.ai = 'parsed'; } else { rules.ai = p.problem; gaps.push('AI output failed the check'); }
}
const f = k => (ai && ai[k] && typeof ai[k] === 'object') ? ai[k] : { value: null, source: null };
const inNotes = src => typeof src === 'string' && src.trim() !== '' && notes.includes(src);

// Each value must match its phrase, and the phrase must be in the masked notes.
const ORD = { ground: 0, first: 1, second: 2, third: 3, fourth: 4, fifth: 5, sixth: 6, seventh: 7, eighth: 8, ninth: 9, tenth: 10,
              one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10 };
function floorIn(src) {
  const d = lower(src).match(/\b(\d+)(?:st|nd|rd|th)?\b/);
  if (d) return Number(d[1]);
  const w = words(src).find(x => x in ORD);
  return w === undefined ? null : ORD[w];
}
const has = (src, list) => list.some(w => (' ' + words(src).join(' ') + ' ').includes(' ' + lower(w) + ' '));
function yesNo(k, subject) {
  const v = f(k);
  if (v.value === 'unknown' || v.value == null) { rules[k] = 'unknown'; return null; }
  if (!['yes', 'no'].includes(v.value) || !inNotes(v.source) || !has(v.source, subject)) { rules[k] = 'rejected: no supporting phrase'; return null; }
  const negative = has(v.source, cfg.negative_words);
  if ((v.value === 'no') !== negative) { rules[k] = `rejected: "${v.source}" does not support ${v.value}`; return null; }
  rules[k] = 'notes'; return v.value;
}
function text(k) {
  const a = sale.address[k];
  if (a !== undefined && a !== null && String(a).trim() !== '') { rules[k] = 'address'; return String(a); }
  const v = f(k);
  if (v.value == null) { rules[k] = 'missing'; return null; }
  if (!inNotes(v.source) || !lower(v.source).includes(lower(v.value))) { rules[k] = 'rejected: no supporting phrase'; return null; }
  rules[k] = 'notes'; return String(v.value);
}
const building = text('building');
const unit = text('unit');
let floor = null;
if (typeof sale.address.floor === 'number') { floor = sale.address.floor; rules.floor = 'address'; }
else {
  const v = f('floor');
  if (Number.isInteger(v.value) && inNotes(v.source) && floorIn(v.source) === v.value) { floor = v.value; rules.floor = 'notes'; }
  else rules.floor = v.value == null ? 'missing' : 'rejected: no supporting phrase';
}
const stairs = yesNo('stairs', cfg.stairs_words);
const lift = yesNo('lift', cfg.lift_words);
let parking = null;
{
  const v = f('parking');
  if (lower(v.value).trim() === 'none') { parking = 'none'; rules.parking = 'none'; }
  else if (typeof v.value === 'string' && v.value.trim() && inNotes(v.source)) { parking = v.value; rules.parking = 'notes'; }
  else rules.parking = v.value == null ? 'missing' : 'rejected: no supporting phrase';
}
let window = null;
{
  const v = f('window');
  if (v.value != null && inNotes(v.source)) { window = String(v.value); rules.window = 'notes'; }
  else rules.window = v.value == null ? 'not given' : 'rejected: no supporting phrase';
}

// Mandatory fields filled.
const c = sale.customer || {};
if (!c.name || !c.phone || !c.channel) gaps.push('customer name, phone or preferred channel');
for (const [k, v] of Object.entries({ building, unit, floor, stairs, lift, parking })) if (v === null) gaps.push(k);

// Address in a zone (the zone sheet, by rule).
const postcode = lower(sale.address.postcode).replace(/\s+/g, '');
const zoneRow = ($('Step 3: Read the zone sheet').first().json.items || [])
  .find(z => (z.postcodes || []).some(p => lower(p).replace(/\s+/g, '') === postcode && postcode));
const zone = zoneRow ? zoneRow.zone : null;
rules.zone = zone || 'outside every zone';
if (!zone) gaps.push('address outside every zone');

// Terms in place: paid, or trade terms from the CRM.
const terms = sale.paid ? 'paid' : (sale.trade_terms || null);
rules.terms = terms ? 'in place' : 'missing';
if (!terms) gaps.push('payment or trade terms');

// Installation flag matches the product list.
const product = ($('Step 3: Read the product list').first().json.items || []).find(p => p.id === sale.product || p.sku === sale.product);
const flagOk = !!product && product.installation === sale.installation;
rules.product = !product ? 'not on the product list' : flagOk ? 'matches' : 'installation flag does not match the product';
if (!flagOk) gaps.push(product ? 'installation flag does not match the product' : 'product not on the product list');

if (mask.code_in_notes) gaps.push('code in notes: move it to the restricted access-code field');
const ready = gaps.length === 0;
const status = ready ? 'ready to schedule' : 'missing details';
const work_order = {
  key, source: ev.source, order_id: ev.order_id, visit_type: ev.visit_type, visit_number: ev.visit_number, status,
  customer: { name: c.name || null, phone: c.phone || null, channel: c.channel || null },
  building, unit, floor, stairs, lift, parking, window, zone, terms,
  product: sale.product, installation: sale.installation, delivery_date: sale.delivery_date,
  notes, code_in_notes: mask.code_in_notes, gaps,
};
const today = new Date().toISOString().slice(0, 10);
const task = ready ? null : {
  id: key, to: sale.salesperson, status: 'open', created: today, delivery_date: sale.delivery_date, work_order: key, gaps,
  text: `Work order ${key} is held as "missing details". Fix: ${gaps.join('; ')}.`,
};
return [{ json: { ready, status, work_order, task, gaps, code_in_notes: mask.code_in_notes, out_of_zone: !zone, rules } }];
"""

LATE_JS = r"""
// Step 9: a task open two working days, or a delivery inside three, goes to Tom's team.
const cfg = $('Config').first().json;
const today = new Date().toISOString().slice(0, 10);
function workingDays(a, b) {
  let n = 0, d = new Date(a + 'T00:00:00Z'); const end = new Date(b + 'T00:00:00Z');
  while (d < end) { d = new Date(d.getTime() + 86400000); if (d.getUTCDay() % 6 !== 0) n++; }
  return n;
}
const out = [];
for (const t of $('Step 9: Read open tasks').first().json.items || []) {
  const open = t.created ? workingDays(t.created, today) : 0;
  const soon = t.delivery_date ? workingDays(today, t.delivery_date) <= cfg.near_delivery_working_days : false;
  if (open >= cfg.late_task_working_days) out.push({ json: { task: t.id, work_order: t.work_order, reason: 'task open two working days', detail: `Task ${t.id} open ${open} working days: ${(t.gaps || []).join('; ')}` } });
  else if (soon) out.push({ json: { task: t.id, work_order: t.work_order, reason: 'delivery inside three working days', detail: `Task ${t.id}, delivery ${t.delivery_date}: ${(t.gaps || []).join('; ')}` } });
}
return out;
"""


def build() -> Workflow:
    w = Workflow("R10.1", "R10.1 Turn a sale into a complete work order")
    w.webhook(T, "r10-1-sale", "Your online store, register and CRM call this on a paid online order, store sale or accepted "
              "trade order with delivery, or a change to one. Body: {source (online, store or trade), order_id, visit_type, "
              "visit_number, updated_at}.", pos=[0, 0])
    w.webhook(CLEARED, "r10-1-task-cleared", "Your task system calls this when the salesperson clears a task. "
              "Body: {source, order_id, visit_type, visit_number}.", pos=[0, 200])
    w.schedule(M, 8, "Each morning: tasks open two working days, or deliveries inside three, go to Tom's team.", pos=[0, 400])
    w.config("Config", {
        "sales_url_online": "https://<your online store API>",
        "sales_url_store": "https://<your register API>",
        "sales_url_trade": "https://<your CRM API>",
        "zones_url": "https://<your zone sheet API>",
        "products_url": "https://<your product list API>",
        "scheduling_url": "https://<your scheduling system API>",
        "tasks_url": "https://<your task API>",
        "masking_list": ["code", "gate", "keypad", "PIN", "key safe"],
        "address_words": ["<your floor, unit and street words, such as floor, unit, apartment, street, road>"],
        "mask_token": "<your mask token>",
        "lift_words": ["lift", "elevator"],
        "stairs_words": ["stairs", "stair", "steps", "staircase"],
        "negative_words": ["no", "not", "without", "broken", "isn't", "doesn't", "out of order", "out of service"],
        "late_task_working_days": 2,
        "near_delivery_working_days": 3,
        "ops_team": "<your operations team>",
        "systems_owner": "<your systems owner>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 200])
    for t in (T, CLEARED, M):
        w.connect(t, "Config")
    w.switch("Start", f"={{{{ $('{M}').isExecuted ? 'morning' : $('{CLEARED}').isExecuted ? 'cleared' : 'sale' }}}}",
             ["sale", "cleared", "morning"], pos=[520, 200])
    w.connect("Config", "Start")

    # ---- step 2: the duplicate key per visit -----------------------------------
    w.reserve_key("Step 2: Reserve key", KEY, pos=[780, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1040, 0])
    w.connect("Start", "Step 2: Reserve key", output=0)
    w.connect("Step 2: Reserve key", "New key?")
    w.pg("Step 2: Read the logged visit", "SELECT status, result FROM key_log WHERE recipe = $1 AND key = $2",
         args=['"R10.1"', KEY], pos=[1300, -160])
    w.if_("Changed since logged?", f"={{{{ $json.status === 'done' && $json.result !== String({EV}.updated_at) }}}}",
          pos=[1560, -160], notes="Logged and unchanged (or still in progress, or failed): stop. Changed: update that work order from step 3.")
    w.noop("Duplicate: stop", pos=[1820, -320], notes="This visit was handled and the sale has not changed.")
    w.connect("New key?", "Step 2: Read the logged visit", output=1)
    w.connect("Step 2: Read the logged visit", "Changed since logged?")
    w.connect("Changed since logged?", "Duplicate: stop", output=1)

    # ---- step 3: read only Table 10.1's fields --------------------------------
    fields = "customer,address,notes,product,installation,paid,trade_terms,delivery_date,salesperson,updated_at"
    w.http("Step 3: Read the sale", "GET",
           f"={{{{ $('Config').item.json['sales_url_' + {EV}.source] }}}}/orders/{{{{ {EV}.order_id }}}}",
           query={"fields": fields}, write=False, error_output=False, pos=[1820, 0],
           notes="Asks for Table 10.1's fields only; the restricted access-code field is never requested.")
    w.connect("New key?", "Step 3: Read the sale", output=0)
    w.connect("Changed since logged?", "Step 3: Read the sale", output=0)
    w.connect("Start", "Step 3: Read the sale", output=1)
    w.http("Step 3: Read the zone sheet", "GET", "={{ $('Config').item.json.zones_url }}/zones", query={"_wrap": "1"},
           write=False, error_output=False, pos=[2080, 0])
    w.http("Step 3: Read the product list", "GET", "={{ $('Config').item.json.products_url }}/products", query={"_wrap": "1"},
           write=False, error_output=False, pos=[2340, 0])
    w.code(KEEP, KEEP_JS, mode="runOnceForAllItems", pos=[2600, 0])
    w.code(MASK, STEP4_JS, mode="runOnceForAllItems", pos=[2860, 0],
           notes="Masks before any AI step or log; every masked order is flagged \"code in notes\".")
    w.chain("Step 3: Read the sale", "Step 3: Read the zone sheet", "Step 3: Read the product list", KEEP, MASK)

    # ---- step 5: AI reads the masked notes only --------------------------------
    vars_js = (f"{{ masked_notes: $('{MASK}').first().json.masked_notes, "
               "mask_token: $('Config').first().json.mask_token }")
    build_, call = ai_step(w, "Step 5", ROOT / "recipes/R10.1/prompts/extract-notes.md", vars_js,
                           max_tokens=700, tries=2, pos_build=[3120, 0], pos_call=[3380, 0])
    w.connect(MASK, build_)
    w.code(CHECK, CHECK_JS, mode="runOnceForAllItems", pos=[3640, 0],
           notes="The rules decide, not the AI; an AI error leaves the note fields unfilled, so the order is held.")
    w.connect(call, CHECK, output=0)
    w.connect(call, CHECK, output=1)
    w.if_("Complete, no code in notes?", "={{ $json.ready }}", pos=[3900, 0])
    w.connect(CHECK, "Complete, no code in notes?")

    # ---- steps 7 and 8: create or update the work order ------------------------
    url = f"={{{{ $('Config').item.json.scheduling_url }}}}/work_orders/{{{{ {KEY} }}}}"
    body = "={{ JSON.stringify($json.work_order) }}"
    w.http("Step 7: Work order: ready to schedule", "PUT", url, body=body, write=True, pos=[4160, -120],
           notes="Creates or updates the work order with the masked notes and the key. A write: never retried.")
    w.http("Step 8: Work order: missing details", "PUT", url, body=body, write=True, pos=[4160, 120])
    w.connect("Complete, no code in notes?", "Step 7: Work order: ready to schedule", output=0)
    w.connect("Complete, no code in notes?", "Step 8: Work order: missing details", output=1)
    w.http("Step 8: Task the salesperson", "POST", "={{ $('Config').item.json.tasks_url }}/tasks",
           body=f"={{{{ JSON.stringify($('{CHECK}').item.json.task) }}}}", write=True, pos=[4420, 120],
           notes="The gaps, including any code to move into the restricted field.")
    w.connect("Step 8: Work order: missing details", "Step 8: Task the salesperson")
    w.if_("Outside every zone?", f"={{{{ $('{CHECK}').item.json.out_of_zone }}}}", pos=[4680, 120])
    w.connect("Step 8: Task the salesperson", "Outside every zone?")
    w.exception("Exception queue: Tom's team calls", f"{EV}.order_id", "address outside every zone",
                f"'Work order ' + {KEY} + ' held: the address is outside every zone'", "$('Config').item.json.ops_team",
                pos=[4940, 240])
    w.connect("Outside every zone?", "Exception queue: Tom's team calls", output=0)

    w.finish_key("Mark key done", KEY, "done", f"String($('{KEEP}').item.json.updated_at)", pos=[5200, 0])
    w.decision_log("Decision log", f"{EV}.order_id", f"$('{CHECK}').item.json.status",
                   f"JSON.stringify(Object.assign({{ key: {KEY}, work_order: {KEY}, missing: $('{CHECK}').item.json.gaps }}, $('{CHECK}').item.json.rules))",
                   pos=[5460, 0])
    w.connect("Step 7: Work order: ready to schedule", "Mark key done")
    w.connect("Outside every zone?", "Mark key done", output=1)
    w.connect("Exception queue: Tom's team calls", "Mark key done")
    w.connect("Mark key done", "Decision log")

    w.finish_key("Mark key failed", KEY, "failed", "'write failed: ' + (($json.error && $json.error.message) || 'unknown')",
                 pos=[5200, 400])
    w.exception("Exception queue: write failed", f"{EV}.order_id", "write failed",
                f"'Work-order write failed for ' + {KEY} + '; check the scheduling system, then release or close the key'",
                "$('Config').item.json.systems_owner", pos=[5460, 400])
    for n in ["Step 7: Work order: ready to schedule", "Step 8: Work order: missing details", "Step 8: Task the salesperson"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- step 9: each morning, late tasks go to Tom's team ---------------------
    w.http("Step 9: Read open tasks", "GET", "={{ $('Config').item.json.tasks_url }}/tasks",
           query={"_wrap": "1", "status": "open"}, write=False, error_output=False, pos=[780, 560])
    w.connect("Start", "Step 9: Read open tasks", output=2)
    w.code("Step 9: Rule: open two working days, or delivery inside three?", LATE_JS, mode="runOnceForAllItems", pos=[1040, 560])
    w.reserve_key("Step 9: Reserve key", "'late:' + $json.task", pos=[1300, 560])
    w.if_("Not sent before?", "={{ $json.is_new }}", pos=[1560, 560])
    late = "$('Step 9: Rule: open two working days, or delivery inside three?').item.json"
    w.pg("Exception queue: Tom's team takes the task",
         "INSERT INTO exception_queue (recipe, item, reason, detail, owner) VALUES ($1, $2, $3, $4, $5) RETURNING id",
         args=['"R10.1"', f"{late}.work_order", f"{late}.reason", f"{late}.detail", "$('Config').item.json.ops_team"],
         pos=[1820, 560], notes="Exception queue: a named person works through it (book Chapters 2 and 16).")
    w.chain("Step 9: Read open tasks", "Step 9: Rule: open two working days, or delivery inside three?",
            "Step 9: Reserve key", "Not sent before?")
    w.connect("Not sent before?", "Exception queue: Tom's team takes the task", output=0)
    return w
