"""R7.4 Run the exception queue with reasons, owners and ageing.

Source: book Chapter 7, recipe R7.4, build steps 1 to 8 (recipes/R7.4/build-spec.md);
AI step: recipes/R7.4/prompts/draft-query.md. The AI only drafts; the owner decides. It never
resolves an item, sends a query or promises payment.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "n8n"))
from wf import AI_PARSE_JS, V, Workflow, ai_step  # noqa: E402

T = "Step 1: Exception added"
C = "Step 7: Item closed"
M = "Step 8: Each working morning"
CFG = "$('Config').item.json"
ITEM = "$('Step 1: Read the queue item').first().json"
KEY = f"{ITEM}.invoice_id + ':' + {ITEM}.reason_code"
OWN = "$('Step 3: Rule: assign the owner').first().json"
DRAFT = "$('Step 5: Draft result').first().json"

ROUTE_JS = f"""
// Three events share one Config; this names the one that ran.
const t = {{ item: '{T}', closed: '{C}', morning: '{M}' }};
for (const [path, node] of Object.entries(t)) {{ try {{ if ($(node).isExecuted) return [{{ json: {{ path }} }}]; }} catch (e) {{}} }}
return [{{ json: {{ path: 'none' }} }}];
"""

NOTE_JS = r"""
// Step 2: a repeat adds a note to the first item for this invoice and reason.
const first = $('Step 2: Read the first item').first().json;
const repeat = $('Step 1: Read the queue item').first().json;
const notes = (first.notes || []).concat([{ on: new Date().toISOString().slice(0, 10), from_item: repeat.id,
  raised_by: repeat.raised_by || null, details: repeat.details || '' }]);
return [{ json: { first_id: first.id, notes } }];
"""

OWNER_JS = r"""
// Step 3: the reason code's owner; an unknown code goes to the escalation owner.
const cfg = $('Config').first().json;
const item = $('Step 1: Read the queue item').first().json;
const known = Object.prototype.hasOwnProperty.call(cfg.reason_owners, item.reason_code);
let owner = known ? cfg.reason_owners[item.reason_code] : cfg.escalation_owner;
let rule = known ? 'reason code owner' : 'unknown code: escalation owner';
if (known && cfg.services_codes.includes(item.reason_code) && cfg.services_suppliers.includes(item.supplier_id || item.supplier)) {
  owner = cfg.services_owner; rule = 'services supplier';
}
return [{ json: { owner, rule, known, query: known && cfg.query_codes.includes(item.reason_code) } }];
"""

CHECK_JS = AI_PARSE_JS + r"""
// Step 5: no banned word, no number that is not in the item, at most 100 words; a failure drops the draft, not the item.
const cfg = $('Config').first().json;
const item = $('Step 1: Read the queue item').first().json;
const p = parseAi($('Step 4: AI call').first().json, ['draft']);
if (!p.ok || typeof p.value.draft !== 'string') return [{ json: { draft: null, draft_check: 'dropped: AI output failed the check' } }];
const draft = p.value.draft.trim();
const lower = draft.toLowerCase();
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const banned = cfg.banned_words.filter(w => new RegExp(`\\b${esc(w.toLowerCase())}\\b`).test(lower));
const nums = s => (String(s || '').match(/\d+(?:[.,]\d+)*/g) || []).map(n => n.replace(/,/g, ''));
const known = new Set(nums([item.invoice_id, item.supplier, item.reason_code, item.details].join(' ')));
const fresh = nums(draft).filter(n => !known.has(n));
const words = draft.split(/\s+/).filter(Boolean).length;
if (banned.length) return [{ json: { draft: null, draft_check: 'dropped: banned word ' + banned.join(', ') } }];
if (fresh.length) return [{ json: { draft: null, draft_check: 'dropped: number not in the item ' + fresh.join(', ') } }];
if (!draft || words > 100) return [{ json: { draft: null, draft_check: `dropped: ${words} words` } }];
return [{ json: { draft, draft_check: 'passed' } }];
"""

AGE_JS = r"""
// Step 8: open items past the aging limit, in working days, oldest first.
const cfg = $('Config').first().json;
const day = d => new Date(String(d).slice(0, 10) + 'T00:00:00Z');
const today = day(new Date().toISOString());
const working = from => { let n = 0; for (let d = new Date(from.getTime() + 86400000); d <= today; d = new Date(d.getTime() + 86400000)) if (d.getUTCDay() % 6 !== 0) n++; return n; };
const items = ($('Step 8: Read the open items').first().json.items || []).filter(i => i.status === 'open' && i.raised_at)
  .map(i => Object.assign({}, i, { age: working(day(i.raised_at)) }))
  .filter(i => i.age > Number(cfg.aging_limit_days))
  .sort((a, b) => day(a.raised_at) - day(b.raised_at));
return [{ json: { any: items.length > 0, items: items.map(i => i.id),
  text: items.map(i => `${i.id}: invoice ${i.invoice_id}, ${i.reason_code}, owner ${i.owner || 'none'}, ${i.age} working days`).join('\n') } }];
"""

CLOSE_JS = r"""
// Step 7: a corrected record or released hold rematches; anything else goes to the payment approver, or is rejected.
const cfg = $('Config').first().json;
const b = $('Step 7: Item closed').first().json.body;
const rec = $('Step 7: Read the invoice record').first().json;
if (['corrected record', 'released hold'].includes(b.resolution)) return [{ json: { route: 'rematch', rules: { resolution: b.resolution } } }];
if (b.resolution === 'rejected') return [{ json: { route: 'reject', rules: { resolution: b.resolution } } }];
let approver = Number(rec.total) <= Number(cfg.approval_limit) ? cfg.approver_to_limit : cfg.approver_above;
let rule = Number(rec.total) <= Number(cfg.approval_limit) ? 'up to the limit' : 'above the limit';
if (approver === b.resolved_by) { approver = cfg.approver_own_items; rule += '; approver resolved the item'; }
return [{ json: { route: 'approve', approver, rules: { resolution: b.resolution, approver: rule } } }];
"""


def build() -> Workflow:
    w = Workflow("R7.4", "R7.4 Run the exception queue with reasons, owners and ageing")
    w.webhook(T, "r7-4-item", "Your queue list calls this when R7.1, R7.2 or R7.3 adds an item. Body: {item_id}.", pos=[0, 0])
    w.webhook(C, "r7-4-closed", "Your queue list calls this when an owner closes an item. Body: {item_id, resolution: corrected record | released hold | resolved | rejected, resolved_by, note}.", pos=[0, 700])
    w.node(M, "n8n-nodes-base.scheduleTrigger", V["schedule"],
           {"rule": {"interval": [{"field": "cronExpression", "expression": "0 8 * * 1-5"}]}}, pos=[0, 1100],
           notes="Each working morning, Monday to Friday at 08:00 (step 8).")
    w.config("Config", {
        "queue_url": "https://<your queue list API>",
        "review_url": "https://<your review list API>",
        "teams_url": "https://<your Teams messaging API>",
        "approvals_url": "https://<your approval list API>",
        "rematch_url": "https://<your n8n>/webhook/r7-2-ready",
        "reason_owners": {
            "needs a person": "<your AP owner>", "unknown supplier": "<your AP owner>",
            "no PO": "<your purchasing approver>", "no receipt": "<your purchasing approver>",
            "outside tolerance": "<your purchasing approver>", "already invoiced": "<your purchasing approver>",
            "pairing rejected": "<your purchasing approver>",
            "lookup error": "<your workflow owner>", "reservation failed": "<your workflow owner>",
            "supplier on hold": "<your caller>",
        },
        "services_codes": ["no PO", "no receipt"],
        "services_suppliers": ["<your rent, utility and carrier supplier IDs>"],
        "services_owner": "<your finance assistant>",
        "escalation_owner": "<your AP owner>",
        "query_codes": ["<your mismatch and missing-document codes>"],
        "banned_words": ["paid", "<your banned query words>"],
        "aging_limit_days": "<your aging limit, working days>",
        "approval_limit": 10000,
        "approver_to_limit": "<your approver up to the limit>",
        "approver_above": "<your approver above the limit>",
        "approver_own_items": "<who approves the approvers' own items>",
        "workflow_owner": "<your workflow owner>",
        "ai_model": "claude-haiku-5-5",
        "ai_inference_geo": "us",
        "ai_url": "https://api.anthropic.com/v1/messages",
    }, pos=[260, 500])
    for t in [T, C, M]:
        w.connect(t, "Config")
    w.code("Which event?", ROUTE_JS, mode="runOnceForAllItems", pos=[520, 500])
    w.switch("Event", "={{ $json.path }}", ["item", "closed", "morning"], pos=[780, 500])
    w.chain("Config", "Which event?", "Event")

    # ---- steps 1 to 3 -------------------------------------------------------------------
    w.http("Step 1: Read the queue item", "GET", f"={{{{ {CFG}.queue_url }}}}/items/{{{{ $('{T}').first().json.body.item_id }}}}",
           write=False, error_output=False, pos=[1040, 0])
    w.reserve_key("Step 2: Reserve key", KEY, pos=[1300, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1560, 0])
    w.connect("Event", "Step 1: Read the queue item", output=0)
    w.chain("Step 1: Read the queue item", "Step 2: Reserve key", "New key?")

    w.pg("Step 2: Find the first item", "SELECT result AS first_id FROM key_log WHERE recipe = $1 AND key = $2",
         args=['"R7.4"', KEY], pos=[1820, -300])
    w.http("Step 2: Read the first item", "GET", f"={{{{ {CFG}.queue_url }}}}/items/{{{{ $json.first_id }}}}",
           write=False, error_output=False, pos=[2080, -300])
    w.code("Step 2: Note for the first item", NOTE_JS, mode="runOnceForAllItems", pos=[2340, -300])
    w.http("Step 2: Add the note", "PATCH", f"={{{{ {CFG}.queue_url }}}}/items/{{{{ $json.first_id }}}}",
           body="={{ JSON.stringify({ notes: $json.notes }) }}", write=True, pos=[2600, -300])
    w.http("Step 2: Close the repeat", "PATCH", f"={{{{ {CFG}.queue_url }}}}/items/{{{{ {ITEM}.id }}}}",
           body="={{ JSON.stringify({ status: 'merged', merged_into: $('Step 2: Note for the first item').first().json.first_id }) }}",
           write=True, pos=[2860, -300], notes="One item per invoice and reason; the repeat is kept as a note.")
    w.decision_log("Step 2: Decision log (repeat)", f"{ITEM}.id",
                   "'repeat: noted on ' + $('Step 2: Note for the first item').first().json.first_id",
                   f"JSON.stringify({{ key: {KEY}, duplicate: true }})", pos=[3120, -300])
    w.connect("New key?", "Step 2: Find the first item", output=1)
    w.chain("Step 2: Find the first item", "Step 2: Read the first item", "Step 2: Note for the first item",
            "Step 2: Add the note", "Step 2: Close the repeat", "Step 2: Decision log (repeat)")

    w.finish_key("Step 2: Remember the first item", KEY, "in progress", f"{ITEM}.id", pos=[1820, 0])
    w.code("Step 3: Rule: assign the owner", OWNER_JS, mode="runOnceForAllItems", pos=[2080, 0])
    w.http("Step 3: Set the owner", "PATCH", f"={{{{ {CFG}.queue_url }}}}/items/{{{{ {ITEM}.id }}}}",
           body=f"={{{{ JSON.stringify({{ owner: $json.owner, status: 'open', assigned_on: $now.toISODate() }}) }}}}",
           write=True, pos=[2340, 0])
    w.if_("Takes a supplier query?", f"={{{{ {OWN}.query }}}}", pos=[2600, 0])
    w.connect("New key?", "Step 2: Remember the first item", output=0)
    w.chain("Step 2: Remember the first item", "Step 3: Rule: assign the owner", "Step 3: Set the owner", "Takes a supplier query?")

    # ---- steps 4 and 5 ------------------------------------------------------------------------
    vars_js = ("{ banned_words: $('Config').first().json.banned_words.join(', '), "
               f"invoice_id: {ITEM}.invoice_id, supplier: {ITEM}.supplier || '', reason_code: {ITEM}.reason_code, item_details: {ITEM}.details || '' }}")
    build_, call = ai_step(w, "Step 4", ROOT / "recipes/R7.4/prompts/draft-query.md", vars_js,
                           max_tokens=2048, tries=3, pos_build=[2860, -120], pos_call=[3120, -120])
    w.connect("Takes a supplier query?", build_, output=0)
    w.code("Step 5: Rule: check the draft", CHECK_JS, mode="runOnceForAllItems", pos=[3380, -120], notes="The rule decides whether the draft is kept.")
    w.connect(call, "Step 5: Rule: check the draft", output=0)
    w.code("Step 5: AI error", "return [{ json: { draft: null, draft_check: 'dropped: AI error after three tries' } }];",
           mode="runOnceForAllItems", pos=[3380, 80])
    w.connect(call, "Step 5: AI error", output=1)
    w.code("Step 4: No draft for this code", "return [{ json: { draft: null, draft_check: 'no query for this reason code' } }];",
           mode="runOnceForAllItems", pos=[3120, 200])
    w.connect("Takes a supplier query?", "Step 4: No draft for this code", output=1)
    w.code("Step 5: Draft result", "return $input.all();", mode="runOnceForAllItems", pos=[3640, 0])
    for n in ["Step 5: Rule: check the draft", "Step 5: AI error", "Step 4: No draft for this code"]:
        w.connect(n, "Step 5: Draft result")

    # ---- step 6 ----------------------------------------------------------------------------------
    w.http("Step 6: Post to the owner in Teams", "POST", f"={{{{ {CFG}.teams_url }}}}/messages",
           body=(f"={{{{ JSON.stringify({{ to: {OWN}.owner, item_id: {ITEM}.id, invoice_id: {ITEM}.invoice_id, "
                 f"reason_code: {ITEM}.reason_code, details: {ITEM}.details || '', draft: $json.draft, draft_check: $json.draft_check }}) }}}}"),
           write=True, pos=[3900, 0], notes="The owner sends, rewrites or ignores the draft; the workflow sends nothing to the supplier.")
    w.finish_key("Mark key done", KEY, "done", f"{ITEM}.id", pos=[4160, 0])
    w.decision_log("Decision log", f"{ITEM}.id", f"'to ' + {OWN}.owner + ({DRAFT}.draft ? ', with a draft' : ', no draft')",
                   f"JSON.stringify({{ reason_code: {ITEM}.reason_code, owner: {OWN}.rule, draft: {DRAFT}.draft_check }})", pos=[4420, 0])
    w.connect("Step 5: Draft result", "Step 6: Post to the owner in Teams")
    w.chain("Step 6: Post to the owner in Teams", "Mark key done", "Decision log")

    w.finish_key("Mark key failed", KEY, "failed", "'write failed: ' + (($json.error && $json.error.message) || 'unknown')", pos=[4160, 400])
    w.exception("Exception queue: write failed", f"{ITEM}.id", "write failed",
                "'Queue or Teams write failed, never retried; tell the owner by hand'", f"{CFG}.workflow_owner", pos=[4420, 400])
    for n in ["Step 3: Set the owner", "Step 6: Post to the owner in Teams", "Step 2: Add the note", "Step 2: Close the repeat"]:
        w.connect(n, "Mark key failed", output=1)
    w.connect("Mark key failed", "Exception queue: write failed")

    # ---- step 7: a closed item --------------------------------------------------------------------
    CB = f"$('{C}').first().json.body"
    w.http("Step 7: Read the closed item", "GET", f"={{{{ {CFG}.queue_url }}}}/items/{{{{ {CB}.item_id }}}}",
           write=False, error_output=False, pos=[1040, 700])
    w.http("Step 7: Read the invoice record", "GET", f"={{{{ {CFG}.review_url }}}}/records/{{{{ $json.invoice_id }}}}",
           write=False, error_output=False, pos=[1300, 700])
    w.code("Step 7: Rule: what happens next", CLOSE_JS, mode="runOnceForAllItems", pos=[1560, 700],
           notes="Nobody approves what they resolved.")
    w.switch("Next", "={{ $json.route }}", ["rematch", "approve", "reject"], pos=[1820, 700])
    w.connect("Event", "Step 7: Read the closed item", output=1)
    w.chain("Step 7: Read the closed item", "Step 7: Read the invoice record", "Step 7: Rule: what happens next", "Next")
    inv = "$('Step 7: Read the closed item').first().json.invoice_id"
    w.http("Step 7: Rematch", "POST", f"={{{{ {CFG}.rematch_url }}}}",
           body=f"={{{{ JSON.stringify({{ record_id: {inv}, resolved_by: {CB}.resolved_by }}) }}}}", write=True, pos=[2080, 560],
           notes="Starts R7.2 again on the corrected record or released hold.")
    w.http("Step 7: Send to the payment approver", "PUT", f"={{{{ {CFG}.approvals_url }}}}/approvals/{{{{ {inv} }}}}",
           body=(f"={{{{ JSON.stringify({{ invoice_id: {inv}, approver: $json.approver, total: $('Step 7: Read the invoice record').first().json.total, "
                 f"note: {CB}.note || '', resolved_by: {CB}.resolved_by, status: 'waiting' }}) }}}}"),
           write=True, pos=[2080, 700], notes="The approver sees the owner's note.")
    w.http("Step 7: Reject the invoice", "PATCH", f"={{{{ {CFG}.review_url }}}}/records/{{{{ {inv} }}}}",
           body=f"={{{{ JSON.stringify({{ status: 'rejected', rejected_by: {CB}.resolved_by, note: {CB}.note || '' }}) }}}}",
           write=True, pos=[2080, 840])
    w.http("Step 7: Close the item", "PATCH", f"={{{{ {CFG}.queue_url }}}}/items/{{{{ {CB}.item_id }}}}",
           body=(f"={{{{ JSON.stringify({{ status: 'closed', resolution: {CB}.resolution, resolved_by: {CB}.resolved_by, "
                 "closed_on: $now.toISODate() }) }}"), write=True, pos=[2340, 700])
    w.decision_log("Step 7: Decision log", f"{CB}.item_id",
                   "'closed: ' + $('Step 7: Rule: what happens next').first().json.route + ($('Step 7: Rule: what happens next').first().json.approver ? ' to ' + $('Step 7: Rule: what happens next').first().json.approver : '')",
                   "JSON.stringify($('Step 7: Rule: what happens next').first().json.rules)", pos=[2600, 700])
    for i, n in enumerate(["Step 7: Rematch", "Step 7: Send to the payment approver", "Step 7: Reject the invoice"]):
        w.connect("Next", n, output=i)
        w.connect(n, "Step 7: Close the item")
    w.connect("Step 7: Close the item", "Step 7: Decision log")
    w.exception("Exception queue: closing write failed", f"{CB}.item_id", "write failed",
                "'Rematch, approval, rejection or close write failed, never retried; finish it by hand'", f"{CFG}.workflow_owner", pos=[2600, 900])
    for n in ["Step 7: Rematch", "Step 7: Send to the payment approver", "Step 7: Reject the invoice", "Step 7: Close the item"]:
        w.connect(n, "Exception queue: closing write failed", output=1)

    # ---- step 8: each working morning ----------------------------------------------------------
    w.http("Step 8: Read the open items", "GET", f"={{{{ {CFG}.queue_url }}}}/items", query={"_wrap": "1", "status": "open"},
           write=False, error_output=False, pos=[1040, 1100])
    w.code("Step 8: Rule: past the aging limit", AGE_JS, mode="runOnceForAllItems", pos=[1300, 1100])
    w.if_("Any overdue?", "={{ $json.any }}", pos=[1560, 1100])
    w.http("Step 8: Post overdue items to the escalation owner", "POST", f"={{{{ {CFG}.teams_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: {CFG}.escalation_owner, subject: 'Overdue exception items, oldest first', items: $json.items, text: $json.text }}) }}}}",
           write=True, error_output=False, pos=[1820, 1100])
    w.connect("Event", "Step 8: Read the open items", output=2)
    w.chain("Step 8: Read the open items", "Step 8: Rule: past the aging limit", "Any overdue?")
    w.connect("Any overdue?", "Step 8: Post overdue items to the escalation owner", output=0)
    return w
