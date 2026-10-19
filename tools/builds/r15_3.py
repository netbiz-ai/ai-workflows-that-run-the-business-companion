"""R15.3 Keep consent and unsubscribes in sync across every list: rules only, no AI step.

Source: book Chapter 15, recipe R15.3, build steps 1 to 8 (recipes/R15.3/build-spec.md).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "n8n"))
from wf import Workflow  # noqa: E402

EVENTS = [  # (trigger node, webhook path, what the event means)
    ("Step 1: Unsubscribe", "r15-3-unsubscribe", "opt_out"),
    ("Step 1: Opt-in", "r15-3-opt-in", "opt_in"),
    ("Step 1: POS sign-up", "r15-3-pos-signup", "opt_in"),
    ("Step 1: Helpdesk opt-out tag", "r15-3-helpdesk-tag", "opt_out"),
]
N = "Step 8: Each night"
EV = "Consent event"
RULES = "Steps 3 and 4: Rules"
LISTS = "Step 6: Lists to update"
RECS = "Step 6: Records to change"
OUT = "Step 7: Outcome"

MATCH_JS = r"""
// Matched on email or phone, never name.
const normEmail = e => String(e || '').trim().toLowerCase();
const normPhone = p => String(p || '').replace(/\D/g, '');
const same = (r, ev) => (normEmail(ev.email) && normEmail(r.email) === normEmail(ev.email))
  || (normPhone(ev.phone) && normPhone(r.phone) === normPhone(ev.phone));
"""

EVENT_JS = "const KINDS = " + json.dumps({n: k for n, _, k in EVENTS}) + ";\n" + r"""
// Step 1: one consent event, whichever source sent it.
for (const [node, kind] of Object.entries(KINDS)) {
  if (!$(node).isExecuted) continue;
  const b = $(node).first().json.body || {};
  return [{ json: { event_id: String(b.event_id || ''), kind, source: node.replace('Step 1: ', ''),
    email: b.email || null, phone: b.phone || null, channel: b.channel || null,
    occurred_at: b.occurred_at || null, wording_version: b.wording_version || null } }];
}
return [];
"""

RULES_JS = MATCH_JS + r"""
// Steps 3 and 4. An opt-out always applies, to every marketing channel; an opt-in needs its proof
// and must be newer than any opt-out for its channel. Consent is never inferred from a purchase.
const cfg = $('Config').first().json;
const ev = $('Consent event').first().json;
const found = [...($('Read the master by email').first().json.items || []), ...($('Read the master by phone').first().json.items || [])]
  .filter(r => same(r, ev));
const contact = found[0] || null;
const consent = Object.assign({}, (contact && contact.consent) || {});
const ignore = reason => [{ json: { apply: false, reason, contact_id: contact ? contact.id : null } }];

if (!ev.email && !ev.phone) return ignore('no email or phone to match on');
const stamp = ev.occurred_at && !isNaN(Date.parse(ev.occurred_at)) ? new Date(ev.occurred_at).toISOString() : null;
let channels;
if (ev.kind === 'opt_in') {
  // Step 3: an opt-in counts only with its wording version and time stamp.
  if (!ev.wording_version || !stamp) return ignore('opt-in without wording version or time stamp');
  if (!cfg.marketing_channels.includes(ev.channel)) return ignore('opt-in channel not in scope');
  // Step 4: order by the event's own time stamp; an opt-in older than an opt-out is ignored.
  const prior = consent[ev.channel];
  if (prior && prior.status === 'opted out' && Date.parse(prior.at) > Date.parse(stamp)) return ignore('opt-in older than an opt-out');
  channels = [ev.channel];
} else {
  channels = cfg.marketing_channels;
}
const status = ev.kind === 'opt_out' ? 'opted out' : 'opted in';
const at = stamp || new Date().toISOString();
for (const ch of channels) {
  consent[ch] = { status, at, event_id: ev.event_id, source: ev.source };
  if (ev.kind === 'opt_in') consent[ch].wording_version = ev.wording_version;
}
// The person is the event's email or phone, joined with the master record's, so a list holding only one still matches.
return [{ json: { apply: true, status, channels, opt_out: ev.kind === 'opt_out', consent,
  email: ev.email || (contact && contact.email) || null, phone: ev.phone || (contact && contact.phone) || null,
  contact_id: contact ? contact.id : null, reason: `${status}: ${channels.join(', ')}` } }];
"""

LISTS_JS = r"""
// Step 6: every other list in scope; an opt-out reaches every list, an opt-in only its channel's lists.
const cfg = $('Config').first().json;
const r = $('Steps 3 and 4: Rules').first().json;
return cfg.lists.filter(l => r.opt_out || r.channels.includes(l.channel))
  .map(l => ({ json: { list: l.name, url: l.url, channel: l.channel, opt_out: r.opt_out }, pairedItem: 0 }));
"""

RECS_JS = MATCH_JS + r"""
// Step 6: the person's records on each list, matched on email or phone, never name.
const ev = $('Steps 3 and 4: Rules').first().json;
const out = [];
$input.all().forEach((it, i) => {
  const l = $('Step 6: Lists to update').itemMatching(i).json;
  const rows = [...($('Step 6: Find on the list by email').itemMatching(i).json.items || []), ...(it.json.items || [])];
  const seen = new Set();
  for (const rec of rows) {
    if (seen.has(rec.id) || !same(rec, ev)) continue;
    seen.add(rec.id);
    out.push({ json: Object.assign({}, l, { record_id: rec.id }), pairedItem: i });
  }
  if (!seen.size) out.push({ json: Object.assign({}, l, { record_id: null, outcome: 'not on the list' }), pairedItem: i });
});
return out;
"""

CONFIRM_JS = r"""
// Step 6: the read-back confirms the change only if the list now holds it.
const rec = $('Step 6: Records to change').item.json;
const ok = $json.marketing_opt_out === rec.opt_out;
return { json: Object.assign({}, rec, { outcome: ok ? 'confirmed' : 'not confirmed',
  problem: ok ? null : `read back marketing_opt_out = ${JSON.stringify($json.marketing_opt_out)}` }) };
"""

UNREACHABLE_JS = r"""
// Step 7: the list could not be read, so it cannot confirm.
const l = $('Step 6: Lists to update').item.json;
return { json: Object.assign({}, l, { record_id: null, problem: 'list unreachable: ' + (($json.error && $json.error.message) || 'no answer') }) };
"""

UNCONFIRMED_JS = r"""
// Step 7: the write failed, the read-back failed, or the read-back differs. Never retried.
const rec = $('Step 6: Records to change').item.json;
const problem = $json.problem || ('write or read-back failed: ' + (($json.error && $json.error.message) || 'no answer'));
return { json: Object.assign({}, rec, { problem }) };
"""

NIGHT_LISTS_JS = r"""
// Step 8: every list, checked against the master each night.
const cfg = $('Config').first().json;
return cfg.lists.map(l => ({ json: { list: l.name, url: l.url, channel: l.channel }, pairedItem: 0 }));
"""

DRIFT_JS = MATCH_JS + r"""
// Step 8: a list record that differs from the master's recorded consent for the list's channel.
const master = $('Step 8: Read the master').first().json.items || [];
const out = [];
$input.all().forEach((it, i) => {
  const l = $('Step 8: Lists to check').itemMatching(i).json;
  for (const rec of it.json.items || []) {
    const m = master.find(c => same(rec, c));
    const c = m && m.consent && m.consent[l.channel];
    if (!c || !['opted out', 'opted in'].includes(c.status)) continue;  // no recorded consent: left as is
    const want = c.status === 'opted out';
    if (rec.marketing_opt_out !== want) {
      out.push({ json: Object.assign({}, l, { record_id: rec.id, contact_id: m.id, opt_out: want }), pairedItem: i });
    }
  }
});
return out;
"""


def build() -> Workflow:
    w = Workflow("R15.3", "R15.3 Keep consent and unsubscribes in sync across every list")
    for i, (name, path, kind) in enumerate(EVENTS):
        w.webhook(name, path, "Body: {event_id, email, phone, occurred_at"
                  + (", channel, wording_version" if kind == "opt_in" else "") + "}.", pos=[0, i * 160])
        w.connect(name, "Config")
    w.schedule(N, 2, "The nightly correction (step 8).", pos=[0, 800])
    w.connect(N, "Config")
    w.config("Config", {
        "crm_url": "https://<your CRM API>",
        "lists": [{"name": "<list name>", "url": "https://<its API>", "channel": "<the channel it sends>"}],
        "marketing_channels": ["email", "<your other marketing channels>"],
        "send_status_url": "https://<your send-status record API>",
        "messaging_url": "https://<your messaging API>",
        "consent_owner": "<your systems owner>",
    }, pos=[260, 240])
    w.if_("Nightly check?", f"={{{{ $('{N}').isExecuted }}}}", pos=[520, 240])
    w.connect("Config", "Nightly check?")

    cfg = "$('Config').first().json"
    ev = f"$('{EV}').first().json"
    r = f"$('{RULES}').first().json"

    # ---- a consent event ------------------------------------------------------
    w.code(EV, EVENT_JS, mode="runOnceForAllItems", pos=[780, 0])
    w.connect("Nightly check?", EV, output=1)
    w.reserve_key("Step 2: Reserve key", f"{ev}.event_id", pos=[1040, 0])
    w.if_("New key?", "={{ $json.is_new }}", pos=[1300, 0])
    w.noop("Duplicate: stop", pos=[1560, -160], notes="This consent event was applied before.")
    w.chain(EV, "Step 2: Reserve key", "New key?")
    w.connect("New key?", "Duplicate: stop", output=1)

    w.http("Read the master by email", "GET", f"={{{{ {cfg}.crm_url }}}}/contacts",
           query={"_wrap": "1", "email": f"={{{{ {ev}.email || '' }}}}"}, write=False, error_output=False, pos=[1560, 0])
    w.http("Read the master by phone", "GET", f"={{{{ {cfg}.crm_url }}}}/contacts",
           query={"_wrap": "1", "phone": f"={{{{ {ev}.phone || '' }}}}"}, write=False, error_output=False, pos=[1820, 0])
    w.code(RULES, RULES_JS, mode="runOnceForAllItems", pos=[2080, 0], notes="Rules decide; R15.3 has no AI step.")
    w.connect("New key?", "Read the master by email", output=0)
    w.chain("Read the master by email", "Read the master by phone", RULES)
    w.if_("Apply it?", "={{ $json.apply }}", pos=[2340, 0])
    w.connect(RULES, "Apply it?")

    w.if_("In the master already?", f"={{{{ {r}.contact_id !== null }}}}", pos=[2600, -80])
    w.connect("Apply it?", "In the master already?", output=0)
    body = f"={{{{ JSON.stringify({{ consent: {r}.consent }}) }}}}"
    w.http("Step 5: Write the change to the CRM", "PATCH", f"={{{{ {cfg}.crm_url }}}}/contacts/{{{{ {r}.contact_id }}}}",
           body=body, write=True, pos=[2860, -160], notes="The master consent record, every channel in scope. A write: never retried.")
    w.http("Step 5: Add the person to the CRM", "POST", f"={{{{ {cfg}.crm_url }}}}/contacts",
           body=f"={{{{ JSON.stringify({{ email: {ev}.email, phone: {ev}.phone, consent: {r}.consent }}) }}}}",
           write=True, pos=[2860, 0])
    w.connect("In the master already?", "Step 5: Write the change to the CRM", output=0)
    w.connect("In the master already?", "Step 5: Add the person to the CRM", output=1)

    w.finish_key("Mark key done", f"{ev}.event_id", "done", f"{r}.reason", pos=[3120, -80])
    w.decision_log("Step 5: Decision log", f"{ev}.event_id", f"'master: ' + {r}.reason",
                   f"JSON.stringify({{ source: {ev}.source, channels: {r}.channels }})", pos=[3380, -80])
    w.connect("Step 5: Write the change to the CRM", "Mark key done")
    w.connect("Step 5: Add the person to the CRM", "Mark key done")
    w.connect("Mark key done", "Step 5: Decision log")

    w.finish_key("Mark ignored event done", f"{ev}.event_id", "done", f"'ignored: ' + {r}.reason", pos=[2600, 160])
    w.decision_log("Steps 3 and 4: Decision log", f"{ev}.event_id", f"'ignored: ' + {r}.reason",
                   f"JSON.stringify({{ source: {ev}.source, kind: {ev}.kind }})", pos=[2860, 160])
    w.connect("Apply it?", "Mark ignored event done", output=1)
    w.connect("Mark ignored event done", "Steps 3 and 4: Decision log")

    w.finish_key("Mark key failed", f"{ev}.event_id", "failed", "'master write failed'", pos=[3120, 320])
    w.exception("Exception queue: master write failed", f"{ev}.event_id", "write failed",
                "'Master consent write failed; no list was changed; apply it by hand, never retried'", f"{cfg}.consent_owner", pos=[3380, 320])
    w.http("Tell Owen: master write failed", "POST", f"={{{{ {cfg}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: {cfg}.consent_owner, subject: 'Consent event ' + {ev}.event_id + ' not applied', text: 'The master consent write failed; no list was changed.' }}) }}}}",
           write=True, error_output=False, pos=[3640, 320])
    w.connect("Step 5: Write the change to the CRM", "Mark key failed", output=1)
    w.connect("Step 5: Add the person to the CRM", "Mark key failed", output=1)
    w.chain("Mark key failed", "Exception queue: master write failed", "Tell Owen: master write failed")

    # ---- step 6: every other list, read back ----------------------------------
    w.code(LISTS, LISTS_JS, mode="runOnceForAllItems", pos=[3640, -80])
    w.connect("Step 5: Decision log", LISTS)
    w.http("Step 6: Find on the list by email", "GET", "={{ $json.url }}/contacts",
           query={"_wrap": "1", "email": f"={{{{ {r}.email || '' }}}}"}, write=False, pos=[3900, -80])
    w.http("Step 6: Find on the list by phone", "GET", f"={{{{ $('{LISTS}').item.json.url }}}}/contacts",
           query={"_wrap": "1", "phone": f"={{{{ {r}.phone || '' }}}}"}, write=False, pos=[4160, -80])
    w.code(RECS, RECS_JS, mode="runOnceForAllItems", pos=[4420, -80])
    w.chain(LISTS, "Step 6: Find on the list by email")
    w.connect("Step 6: Find on the list by email", "Step 6: Find on the list by phone", output=0)
    w.connect("Step 6: Find on the list by phone", RECS, output=0)
    w.if_("On the list?", "={{ $json.record_id !== null }}", pos=[4680, -80])
    w.connect(RECS, "On the list?")
    w.http("Step 6: Apply it to the list", "PATCH", "={{ $json.url }}/contacts/{{ $json.record_id }}",
           body="={{ JSON.stringify({ marketing_opt_out: $json.opt_out }) }}", write=True, pos=[4940, -160],
           notes="Never retried (book Chapter 2); a failure goes to step 7.")
    w.http("Step 6: Read it back", "GET", f"={{{{ $('{RECS}').item.json.url }}}}/contacts/{{{{ $('{RECS}').item.json.record_id }}}}",
           write=False, pos=[5200, -160])
    w.code("Step 6: Rule: did the list confirm?", CONFIRM_JS, pos=[5460, -160])
    w.if_("Confirmed?", "={{ $json.outcome }}", op="equals", right="confirmed", pos=[5720, -160])
    w.connect("On the list?", "Step 6: Apply it to the list", output=0)
    w.connect("Step 6: Apply it to the list", "Step 6: Read it back", output=0)
    w.connect("Step 6: Read it back", "Step 6: Rule: did the list confirm?", output=0)
    w.connect("Step 6: Rule: did the list confirm?", "Confirmed?")
    w.decision_log("Step 6: Decision log", f"{ev}.event_id", "$json.list + ': ' + $json.outcome",
                   "JSON.stringify({ list: $json.list, record: $json.record_id, opt_out: $json.opt_out })", pos=[5980, -240])
    w.connect("Confirmed?", "Step 6: Decision log", output=0)
    w.connect("On the list?", "Step 6: Decision log", output=1)

    # ---- step 7: a list that does not confirm ---------------------------------
    w.code("Step 7: List unreachable", UNREACHABLE_JS, pos=[4420, 240])
    w.connect("Step 6: Find on the list by email", "Step 7: List unreachable", output=1)
    w.connect("Step 6: Find on the list by phone", "Step 7: List unreachable", output=1)
    w.code("Step 7: List did not confirm", UNCONFIRMED_JS, pos=[5460, 240])
    w.connect("Step 6: Apply it to the list", "Step 7: List did not confirm", output=1)
    w.connect("Step 6: Read it back", "Step 7: List did not confirm", output=1)
    w.connect("Confirmed?", "Step 7: List did not confirm", output=1)
    w.if_("Step 7: An opt-out?", "={{ $json.opt_out }}", pos=[5720, 240])
    w.connect("Step 7: List unreachable", "Step 7: An opt-out?")
    w.connect("Step 7: List did not confirm", "Step 7: An opt-out?")
    q = "$('Step 7: An opt-out?').item.json"
    w.http("Step 7: Suppress the person on the list", "POST", "={{ $json.url }}/suppressions",
           body=f"={{{{ JSON.stringify({{ email: {r}.email, phone: {r}.phone, event_id: {ev}.event_id, reason: 'marketing opt-out' }}) }}}}",
           write=True, pos=[5980, 160], notes="The list's own suppression, which overrides its subscription flag. Never retried.")
    w.http("Step 7: Mark the list paused", "PUT", f"={{{{ {cfg}.send_status_url }}}}/lists/{{{{ {q}.list }}}}",
           body=f"={{{{ JSON.stringify({{ status: 'paused', since: new Date().toISOString(), reason: 'opt-out not confirmed: ' + {q}.problem, event_id: {ev}.event_id }}) }}}}",
           write=True, pos=[6240, 320], notes="The send-status record Ben checks before every marketing send. Owen lifts it.")
    w.connect("Step 7: An opt-out?", "Step 7: Suppress the person on the list", output=0)
    w.connect("Step 7: Suppress the person on the list", "Step 7: Mark the list paused", output=1)
    for i, (name, src, out, action) in enumerate([
        ("Step 7: Suppressed", "Step 7: Suppress the person on the list", 0, "suppressed on the list"),
        ("Step 7: Paused", "Step 7: Mark the list paused", 0, "list paused"),
        ("Step 7: Pause failed", "Step 7: Mark the list paused", 1, "suppression and pause both failed; pause the list by hand"),
        ("Step 7: Opt-in not confirmed", "Step 7: An opt-out?", 1, "opt-in not on this list yet; the nightly check corrects it"),
    ]):
        w.code(name, f"return {{ json: Object.assign({{}}, {q}, {{ action: {json.dumps(action)} }}) }};", pos=[6500, 80 + 140 * i])
        w.connect(src, name, output=out)
        w.connect(name, OUT)
    w.code(OUT, "return { json: $json };", pos=[6760, 240])
    o = f"$('{OUT}').item.json"
    w.exception("Exception queue: list did not confirm", f"{ev}.event_id", "list did not confirm",
                f"{o}.list + ': ' + {o}.problem + '; ' + {o}.action", f"{cfg}.consent_owner", pos=[7020, 240])
    w.http("Step 7: Tell Owen", "POST", f"={{{{ {cfg}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: {cfg}.consent_owner, subject: 'Consent change not confirmed on ' + {o}.list, text: {o}.problem + '; ' + {o}.action }}) }}}}",
           write=True, error_output=False, pos=[7280, 240])
    w.decision_log("Step 7: Decision log", f"{ev}.event_id", f"{o}.list + ': not confirmed; ' + {o}.action",
                   f"JSON.stringify({{ list: {o}.list, record: {o}.record_id, problem: {o}.problem }})", pos=[7540, 240])
    w.chain(OUT, "Exception queue: list did not confirm", "Step 7: Tell Owen", "Step 7: Decision log")

    # ---- step 8: each night ---------------------------------------------------
    w.http("Step 8: Read the master", "GET", f"={{{{ {cfg}.crm_url }}}}/contacts", query={"_wrap": "1"},
           write=False, error_output=False, pos=[780, 800])
    w.code("Step 8: Lists to check", NIGHT_LISTS_JS, mode="runOnceForAllItems", pos=[1040, 800])
    w.http("Step 8: Read the list", "GET", "={{ $json.url }}/contacts", query={"_wrap": "1"}, write=False, pos=[1300, 800])
    w.code("Step 8: Rule: records that differ", DRIFT_JS, mode="runOnceForAllItems", pos=[1560, 800])
    w.connect("Nightly check?", "Step 8: Read the master", output=0)
    w.chain("Step 8: Read the master", "Step 8: Lists to check", "Step 8: Read the list")
    w.connect("Step 8: Read the list", "Step 8: Rule: records that differ", output=0)
    d = "$('Step 8: Rule: records that differ').item.json"
    w.http("Step 8: Correct the list", "PATCH", "={{ $json.url }}/contacts/{{ $json.record_id }}",
           body="={{ JSON.stringify({ marketing_opt_out: $json.opt_out }) }}", write=True, pos=[1820, 800])
    w.decision_log("Step 8: Decision log", f"{d}.list + ':' + {d}.record_id", f"'nightly: ' + {d}.list + ' corrected to the master'",
                   f"JSON.stringify({{ list: {d}.list, contact: {d}.contact_id, opt_out: {d}.opt_out }})", pos=[2080, 720])
    w.connect("Step 8: Rule: records that differ", "Step 8: Correct the list")
    w.connect("Step 8: Correct the list", "Step 8: Decision log", output=0)

    w.code("Step 8: List still failing", "const l = $('Step 8: Lists to check').item.json;\n"
           "return { json: { list: l.list, problem: 'nightly read failed: ' + (($json.error && $json.error.message) || 'no answer') } };",
           pos=[1560, 1000])
    w.code("Step 8: Correction failed", f"return {{ json: {{ list: {d}.list, problem: 'nightly correction of ' + {d}.record_id + ' failed' }} }};",
           pos=[2080, 1000])
    w.connect("Step 8: Read the list", "Step 8: List still failing", output=1)
    w.connect("Step 8: Correct the list", "Step 8: Correction failed", output=1)
    w.code("Step 8: Failure", "return { json: $json };", pos=[2340, 1000])
    w.connect("Step 8: List still failing", "Step 8: Failure")
    w.connect("Step 8: Correction failed", "Step 8: Failure")
    f = "$('Step 8: Failure').item.json"
    w.exception("Exception queue: list held", f"{f}.list", "nightly check failed",
                f"{f}.problem + '; the list stays held until it is fixed'", f"{cfg}.consent_owner", pos=[2600, 1000])
    w.http("Step 8: Tell Owen", "POST", f"={{{{ {cfg}.messaging_url }}}}/messages",
           body=f"={{{{ JSON.stringify({{ to: {cfg}.consent_owner, subject: 'Nightly consent check: ' + {f}.list, text: {f}.problem }}) }}}}",
           write=True, error_output=False, pos=[2860, 1000])
    w.chain("Step 8: Failure", "Exception queue: list held", "Step 8: Tell Owen")
    return w
